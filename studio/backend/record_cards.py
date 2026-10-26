"""
From your record, stage 1: the daily cards from the creator's own rows.
=======================================================================
The section "From your record" answers one question at one cadence: what
from my own record, and from what I asked, is worth writing from today? It
shows a batch of five slots, computed once a day by the daily job
(record_daily.py) into a dated table and only ever read by the screen.

This module is the local stage: it reads the creator's rows and nothing
else, needs no key, makes no request, and works on day 0 with an archive
imported. Every card names the rows it came from, the date they were read
and the rule that chose it, or says in a sentence why it cannot. The slots:

  1  Working for you    the post that did best against the creator's own
                        median, through results.ranking and nothing else;
                        abstains in words until the engine's minimums are
                        met ("not enough settled posts yet: N of 3")
  2  Working for you    a post of theirs from this day in an earlier year,
                        or an opener of theirs drawn by the resurfacing
                        rule: the pool is their own first lines, a shown one
                        is held back 7, 14 then 28 days and its chance halves
                        each time, the draw's seed is stored on the run
  3  You asked          an ask they typed, matched to their own posts by the
                        words they share (the search index, bm25), or, when
                        nothing was asked, one of their recurring topics
  4  You engaged with   a comment of theirs on somebody else's post, as a
                        link, the date and their own words; or a post they
                        saved, as a link and a date. Never the other
                        person's text
  5  the model (stage 2) or the Inox library (stage 3): left to those stages

The Monday card (decision 4) carries the week's counts and no comparison.
Abstentions are rows too, labelled "abstained", shown as a sentence that
says what is missing and what will fill it; they never pad the batch.

Labels (ideas report, "Cards carry one of six labels"): measured, a figure
read from a row with an observed_at; derived, computed from measured rows
by a stated rule; typed, a classification by rule with no outcome behind
it; suggested, model text (stage 2); retrieved (stage 4, never built here);
curated, the signed library; abstained.

Strict Invariants:
- Zero em-dashes.
- Zero egress: this module imports no client and opens no socket.
- Nothing invented: every figure carries the table, the row and the time it
  was read; a figure nobody read is absent, never 0.
- No ranking of people. Comments are the creator's own words; nobody is
  ordered by a score here.
- One ranking: "what worked" is results.ranking, called, never restated.
"""

import hashlib
import json
import math
import random
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from . import evidence_briefing, post_identity, results, universal_search
    from .text_cut import clip
except ImportError:  # top-level import mode
    import evidence_briefing
    import post_identity
    import results
    import universal_search
    from text_cut import clip

SLOTS = 5
EXCERPT_CHARS = 140
# An opener shorter than this, or made of a link alone, is not one worth resurfacing.
MIN_OPENER_WORDS = 6
# How long a shown item is held back after its first, second and third showing.
HOLD_DAYS = (7, 14, 28)
# Its chance after each showing, and what the two creator marks do to it.
DECAY_PER_SHOWING = 0.5
KEEP_WEIGHT = 2.0
SKIP_WEIGHT = 0.5
SKIP_HOLD_DAYS = 14
# With this many ranked posts the resurfacing pool is their top quartile; below it, every post.
POOL_FROM_RANKING_AT = 8
POOL_QUARTILE = 0.25
# A comment made longer ago than this is still the creator's, but the recent ones come first.
ENGAGED_RECENT_DAYS = 90
# The studio's own playbook, in Docs under Write and publish, which an ask is
# matched to beside the creator's posts (the report's batch 6).
PLAYBOOK_FILE = "strategy_playbook.md"

LABELS = ("measured", "derived", "typed", "suggested", "retrieved", "curated", "abstained")
# What a mark can do depends on how a card was arrived at. A drawn card's
# chance moves with keep and skip; a card the record chooses (the best post,
# the post of this day) is not drawn, so a mark can only set it aside: hide
# for good, skip for SKIP_HOLD_DAYS. A model's idea or the Monday card is
# never shown twice in any case.
DRAWN_KINDS = ("opener", "ask", "theme", "comment", "reaction", "saved", "repost", "library")
CHOSEN_KINDS = ("what_worked", "on_this_day")
BLOCKS = {"working_for_you": "Working for you", "you_asked": "You asked", "you_engaged_with": "You engaged with",
          "monday": "This week", "model": "Suggested by your model", "library": "From the Inox library"}

_LINK_ONLY = re.compile(r"^\s*(?:https?://\S+\s*)+$", re.IGNORECASE)
_DATED = re.compile(
    r"\b(?:19|20)\d\d\b|\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b"
    r"|\b(?:today|yesterday|tomorrow|this week|last week|this month|next week)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rows(conn, sql: str, params: Iterable[Any] = ()) -> List[sqlite3.Row]:
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    try:
        return cursor.execute(sql, tuple(params)).fetchall()
    except sqlite3.OperationalError:
        return []


def _scalar(conn, sql: str, params: Iterable[Any] = ()) -> Optional[Any]:
    try:
        row = conn.execute(sql, tuple(params)).fetchone()
    except sqlite3.OperationalError:
        return None
    return row[0] if row else None


def _excerpt(text: Optional[str], chars: int = EXCERPT_CHARS) -> str:
    return clip(" ".join((text or "").split()), chars)


def _first_line(text: Optional[str]) -> str:
    return next((line.strip() for line in (text or "").splitlines() if line.strip()), "")


def _day_of(stamp: Optional[str]) -> Optional[date]:
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _said_date(stamp: Optional[str]) -> str:
    """A date as a card says it: "12 March 2026"."""
    when = _day_of(stamp)
    return f"{when.day} {when.strftime('%B %Y')}" if when else "a date the row does not carry"


def _said_weekday(stamp: Optional[str]) -> str:
    when = _day_of(stamp)
    return f"{when.strftime('%A')} {when.day} {when.strftime('%B')}" if when else "a day the row does not carry"


def seed_for(day: date, reroll: int = 0) -> int:
    """The draw's seed for a day: from the date, so the same day draws the same cards until re-rolled."""
    return int(hashlib.sha256(day.isoformat().encode("ascii")).hexdigest()[:8], 16) + reroll


def _opener_is_worth_it(line: str) -> bool:
    if not line or _LINK_ONLY.match(line):
        return False
    words = [w for w in re.split(r"\s+", line) if w and not w.lower().startswith(("http://", "https://"))]
    return len(words) >= MIN_OPENER_WORDS


def _verification(**overrides) -> Dict[str, Any]:
    out = {"ids_exist": True, "excerpt_is_substring": True, "digits_in_model_text": False, "dropped_reason": None}
    out.update(overrides)
    return out


def _card(card_id: str, slot: int, block: str, kind: str, label: str, method: str, payload: Dict[str, Any],
          source_rows: List[Dict[str, Any]], figures: Optional[List[Dict[str, Any]]] = None,
          status: str = "shown") -> Dict[str, Any]:
    assert label in LABELS, label
    return {
        "card_id": card_id,
        "slot": slot,
        "block": block,
        "kind": kind,
        "label": label,
        "method": method,
        "status": status,
        "payload": payload,
        "provenance": {
            "kind": kind,
            "label": label,
            "method": method,
            "source_rows": source_rows,
            "figures": figures or [],
            "model": None,
            "retrieved": None,
            "bundle": None,
            "verification": _verification(),
        },
    }


def _abstained(slot: int, block: str, kind: str, sentence: str, rule: str) -> Dict[str, Any]:
    """A sentence saying what is missing and what will fill it. It fills no slot."""
    return _card(f"abstain:{kind}", slot, block, kind, "abstained", rule,
                 {"sentence": sentence, "block_label": BLOCKS[block]}, [], status="abstained")


# ---------------------------------------------------------------------------
# What has been shown, kept, skipped and hidden before today
# ---------------------------------------------------------------------------

def _history(conn, day: date) -> Dict[str, Any]:
    """
    Per card id: the days it was shown before today, and the creator's marks.

    Hide excludes an item for good (until "Unhide all"); keep doubles its
    weight; skip halves it and holds it back; a showing halves it and holds
    it back for 7, 14 then 28 days. All of it selection, none of it figures.
    """
    shown: Dict[str, List[date]] = {}
    for row in _rows(conn, "SELECT card_id, day FROM daily_view WHERE day < ? AND status = 'shown'", (day.isoformat(),)):
        when = _day_of(row["day"])
        if when:
            shown.setdefault(row["card_id"], []).append(when)
    marks: Dict[str, Dict[str, date]] = {}
    for row in _rows(conn, "SELECT card_id, mark, MAX(at) AS at FROM card_marks GROUP BY card_id, mark"):
        when = _day_of(row["at"]) or day
        marks.setdefault(row["card_id"], {})[row["mark"]] = when
    return {"shown": shown, "marks": marks}


def _weight(card_id: str, history: Dict[str, Any], day: date) -> float:
    """An item's chance of being drawn today, or 0 when it is held back or hidden."""
    marks = history["marks"].get(card_id, {})
    if "hide" in marks:
        return 0.0
    showings = sorted(history["shown"].get(card_id, []))
    weight = 1.0
    if showings:
        hold = HOLD_DAYS[min(len(showings), len(HOLD_DAYS)) - 1]
        if (day - showings[-1]).days < hold:
            return 0.0
        weight *= DECAY_PER_SHOWING ** len(showings)
    if "skip" in marks:
        if (day - marks["skip"]).days < SKIP_HOLD_DAYS:
            return 0.0
        weight *= SKIP_WEIGHT
    if "keep" in marks:
        weight *= KEEP_WEIGHT
    return weight


def _set_aside(card_id: str, history: Optional[Dict[str, Any]], day: Optional[date]) -> bool:
    """
    Whether the creator hid this card, or skipped it within SKIP_HOLD_DAYS.

    For the cards the record chooses rather than draws: Hide said "do not
    show me this again" on every card, and a card that ignored it would make
    the button a lie.
    """
    if not history or day is None:
        return False
    marks = history["marks"].get(card_id, {})
    if "hide" in marks:
        return True
    return "skip" in marks and (day - marks["skip"]).days < SKIP_HOLD_DAYS


def _draw(items: List[Tuple[Any, ...]], history: Dict[str, Any], day: date, seed: int) -> Optional[Tuple[str, Any]]:
    """
    One weighted draw with a seed that is stored on the run, so the day can be
    reproduced. Each item is (card id, item) or (card id, item, base weight);
    the base weight is the share Readwise's rule names (an opener's topic's
    share of the creator's posts), and the history's holds and marks scale it.
    """
    weighted = []
    for entry in items:
        card_id, item = entry[0], entry[1]
        base = entry[2] if len(entry) > 2 else 1.0
        weighted.append((card_id, item, base * _weight(card_id, history, day)))
    weighted = [w for w in weighted if w[2] > 0]
    if not weighted:
        return None
    picker = random.Random(seed)
    total = sum(w for _, _, w in weighted)
    point = picker.random() * total
    running = 0.0
    for card_id, item, weight in weighted:
        running += weight
        if point <= running:
            return card_id, item
    return weighted[-1][0], weighted[-1][1]


# ---------------------------------------------------------------------------
# The creator's posts, topics and figures
# ---------------------------------------------------------------------------

def _posts(conn) -> List[Dict[str, Any]]:
    return [dict(r) for r in _rows(
        conn, "SELECT activity_urn, text, published_at FROM own_posts WHERE activity_urn NOT LIKE ? ORDER BY published_at",
        (post_identity.LOCAL_URN_PREFIX + "%",))]


def _topics(posts: List[Dict[str, Any]]) -> Tuple[List[Tuple[str, str]], Dict[str, str], Dict[str, int]]:
    """The creator's vocabulary, each post's topic and the count per topic label."""
    vocabulary = evidence_briefing.derive_topic_vocabulary([p.get("text") for p in posts])
    of_post: Dict[str, str] = {}
    counts: Dict[str, int] = {}
    for post in posts:
        label = evidence_briefing.classify_post_topic(post.get("text"), vocabulary)
        of_post[post["activity_urn"]] = label
        counts[label] = counts.get(label, 0) + 1
    return vocabulary, of_post, counts


def _reading_of(figure: Dict[str, Any], name: str) -> Dict[str, Any]:
    """
    The reading one figure was taken from. Each figure is the newest reading
    that has it (results.figures, "by_figure"), which need not be the post's
    newest reading: an activity page read last has reactions and no
    impressions, so the impressions are an older page's.
    """
    own = (figure.get("by_figure") or {}).get(name) or {}
    return {"source": own.get("source") or figure.get("source"), "read_at": own.get("read_at") or figure.get("read_at")}


def _figure_rows(urn: str, figure: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Each figure of a post as a record naming the reading it was read from and when, its own."""
    if not figure or not figure.get("source"):
        return []
    rows = []
    for name in results.FIGURE_FIELDS:
        if figure.get(name) is None:
            continue
        reading = _reading_of(figure, name)
        rows.append({"name": name, "value": figure[name],
                     "table": "own_posts" if reading["source"] == results.SNAPSHOT else "post_metric_observations",
                     "id": urn, "observed_at": reading["read_at"], "source": reading["source"]})
    return rows


def _said_figures(figures: List[Dict[str, Any]]) -> str:
    """The figures in words, each with the day it was read, said once when they share it."""
    days = {_said_date(f["observed_at"]) for f in figures}
    if len(days) == 1:
        return " and ".join(f"{f['value']} {f['name']}" for f in figures) + f" (read {days.pop()})"
    return " and ".join(f"{f['value']} {f['name']} (read {_said_date(f['observed_at'])})" for f in figures)


# ---------------------------------------------------------------------------
# Slot 1: what worked, through results.ranking
# ---------------------------------------------------------------------------

def what_worked(conn, posts: List[Dict[str, Any]], history: Optional[Dict[str, Any]] = None,
                day: Optional[date] = None) -> Dict[str, Any]:
    """
    The post that did best against the creator's own median reactions, with
    every figure from the row it was read from, or the sentence that says
    why there is none yet. results.best is the one definition of "worked".

    A post the creator hid, or skipped in the last SKIP_HOLD_DAYS, is passed
    over for the next one in the same order, and the card says so.
    """
    block, kind = "working_for_you", "what_worked"
    rule = ("ranked by results.ranking: settled posts only, reactions against your own median; "
            f"abstains under {results.MIN_FOR_MEDIAN} settled posts with figures")
    if not posts:
        return _abstained(1, block, kind, "No posts yet. Import your archive in Setup, and this card fills from "
                          "your own posts.", rule)
    every = results.figures(conn)
    answer = results.best(conn, limit=1, read=every)
    usual = answer["usual"][results.RANKED_METRIC]
    settle = results.settled_after_hours(conn)
    if not answer["best"]:
        with_figures = sum(1 for figure in every.values() if figure.get(results.RANKED_METRIC) is not None)
        if with_figures == 0:
            return _abstained(1, block, kind, "No readings yet: figures arrive as the studio reads your posts. "
                              "Press Import your history in Setup.", rule)
        return _abstained(1, block, kind, f"Not enough settled posts yet: {usual['posts']} of "
                          f"{results.MIN_FOR_MEDIAN}. {with_figures} of your posts have figures, and a post is "
                          f"judged once it is {settle['hours'] / 24:g} days old; the studio ranks nothing on fewer.",
                          rule)
    urn = answer["best"][0]
    passed_over = 0
    if _set_aside(f"worked:{urn}", history, day):
        # The same ranking's order, not a second one: only what the creator
        # set aside is stepped over.
        order = results.ranking(conn, read=every)["order"]
        free = [u for u in order if not _set_aside(f"worked:{u}", history, day)]
        if not free:
            return _abstained(1, block, kind, "You hid or skipped every post the ranking holds. Unhide all on What the "
                              f"studio knows brings back what you hid; a skip lasts {SKIP_HOLD_DAYS} days.", rule)
        passed_over = order.index(free[0])
        answer = results.best(conn, limit=passed_over + 1, read=every)
        urn = answer["best"][passed_over]
    named = answer["named"][urn]
    text = next((p.get("text") for p in posts if p["activity_urn"] == urn), None)
    published = next((p.get("published_at") for p in posts if p["activity_urn"] == urn), None)
    read = every.get(urn) or {}
    figures = _figure_rows(urn, read)
    # The ranked figure's own reading, which may be older than the post's newest.
    ranked = _reading_of(read, results.RANKED_METRIC)
    ratio = named["against_usual"].get(results.RANKED_METRIC)
    reactions = named.get(results.RANKED_METRIC)
    because = (f"Because this post drew {ratio} times your usual reactions: {reactions} against your median "
               f"{usual['median']:g} across {usual['posts']} settled posts, read from the "
               f"{'post analytics' if ranked['source'] == 'post_analytics' else 'activity' if ranked['source'] == 'activity_page' else 'archive snapshot'} page on "
               f"{_said_date(ranked['read_at'])}")
    if passed_over:
        because += (f"; the best of your posts you have not hidden or skipped, with {passed_over} "
                    f"{'post' if passed_over == 1 else 'posts'} above it set aside")
    payload = {
        "title": "What worked",
        "badge": "measured",
        "excerpt": _excerpt(text),
        "date": published,
        "url": post_identity.linkedin_permalink(urn),
        "figures": figures,
        "figure_sentence": (f"{ratio} times your usual reactions: {reactions} against your median {usual['median']:g} "
                            f"across {usual['posts']} settled posts"),
        "because": f"{because} · rule: Working for you",
        "source_sentence": f"from your post of {_said_date(published)} (its reactions as read on "
                           f"{_said_date(ranked['read_at'])}, {ranked['source'] or 'no source'})",
        "method_sentence": (f"{rule}; a post is judged once it is {settle['hours'] / 24:g} days old"
                            f"{', measured from your own readings' if settle['measured'] else ', assumed until your readings can say'}; "
                            f"{answer['ranked_posts']} posts ranked"),
        "draft_text": text or "",
        "block_label": BLOCKS[block],
    }
    return _card(f"worked:{urn}", 1, block, kind, "measured", rule, payload,
                 [{"table": "own_posts", "id": urn}], figures)


# ---------------------------------------------------------------------------
# Slot 2: on this day, or a resurfaced opener
# ---------------------------------------------------------------------------

def on_this_day(conn, posts: List[Dict[str, Any]], day: date,
                history: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """
    A post of theirs from this calendar day in an earlier year, with its
    measured date; one the creator hid or skipped lately is passed over.
    """
    same_day = [p for p in posts if (when := _day_of(p.get("published_at"))) and when.month == day.month
                and when.day == day.day and when.year < day.year and (p.get("text") or "").strip()
                and not _set_aside(f"otd:{p['activity_urn']}", history, day)]
    if not same_day:
        return None
    post = same_day[-1]
    urn = post["activity_urn"]
    read = results.figures(conn, [urn]).get(urn) or {}
    figures = _figure_rows(urn, read)
    years = day.year - _day_of(post["published_at"]).year
    rule = "a calendar match on published_at across earlier years"
    payload = {
        "title": "On this day",
        "badge": "measured date",
        "excerpt": _excerpt(post.get("text")),
        "date": post.get("published_at"),
        "url": post_identity.linkedin_permalink(urn),
        "figures": figures,
        "figure_sentence": _said_figures(figures) if figures else "figures not measured",
        "because": f"Because you posted this on {_said_date(post.get('published_at'))}, {years} "
                   f"{'year' if years == 1 else 'years'} ago today · rule: On this day",
        "source_sentence": f"from your post of {_said_date(post.get('published_at'))}",
        "method_sentence": rule + "; the date is the row's, the figures only where a page was read",
        "draft_text": post.get("text") or "",
        "block_label": BLOCKS["working_for_you"],
    }
    return _card(f"otd:{urn}", 2, "working_for_you", "on_this_day", "measured", rule, payload,
                 [{"table": "own_posts", "id": urn}], figures)


def resurfaced_opener(conn, posts: List[Dict[str, Any]], topics_of: Dict[str, str], history: Dict[str, Any],
                      day: date, seed: int) -> Optional[Dict[str, Any]]:
    """
    One of the creator's own first lines, drawn by a stated and reproducible rule.

    The pool is the top quartile of results.ranking when at least
    POOL_FROM_RANKING_AT posts are ranked, else every post with words. The
    label says which: with readings behind it the opener is derived from a
    measured ranking; without, it is typed, resurfaced and not a measurement.
    """
    by_urn = {p["activity_urn"]: p for p in posts}
    ranked = results.ranking(conn)["order"]
    from_ranking = len(ranked) >= POOL_FROM_RANKING_AT
    pool_urns = ranked[: max(1, math.ceil(len(ranked) * POOL_QUARTILE))] if from_ranking else [p["activity_urn"] for p in posts]
    share: Dict[str, int] = {}
    for label in topics_of.values():
        share[label] = share.get(label, 0) + 1
    total = max(1, sum(share.values()))
    items = []
    for urn in pool_urns:
        line = _first_line((by_urn.get(urn) or {}).get("text"))
        if _opener_is_worth_it(line):
            topic = topics_of.get(urn, evidence_briefing.OTHER_TOPIC)
            items.append((f"opener:{urn}", (urn, line), share.get(topic, 1) / total))
    drawn = _draw(items, history, day, seed)
    if not drawn:
        return None
    card_id, (urn, line) = drawn
    post = by_urn[urn]
    label = "derived" if from_ranking else "typed"
    pool = (f"the top quarter of your {len(ranked)} ranked posts" if from_ranking
            else f"every one of your {len(posts)} posts, since fewer than {POOL_FROM_RANKING_AT} are ranked")
    rule = (f"drawn from your own first lines ({MIN_OPENER_WORDS} words or more, not a link alone) out of {pool}, "
            f"each with the chance of its topic's share of your posts, and the seed stored on today's run; a shown opener is held back {HOLD_DAYS[0]}, {HOLD_DAYS[1]} then "
            f"{HOLD_DAYS[2]} days and its chance halves each time; keep doubles it, skip halves it and holds it "
            f"{SKIP_HOLD_DAYS} days, hide removes it")
    evergreen = not _DATED.search(post.get("text") or "")
    payload = {
        "title": "Opener to reuse",
        "badge": "resurfaced, not measured" if not from_ranking else "resurfaced from your ranked posts",
        "excerpt": _excerpt(line),
        "date": post.get("published_at"),
        "url": post_identity.linkedin_permalink(urn),
        "figures": [],
        "figure_sentence": "not a measurement",
        "because": (f"Because this is the first line of your post of {_said_date(post.get('published_at'))}"
                    f"{', one of your top-quarter posts by your own median' if from_ranking else ''}, drawn by the "
                    f"resurfacing rule; topic {topics_of.get(urn, evidence_briefing.OTHER_TOPIC)}"
                    f"{'; evergreen by the text rule (no dated reference in it)' if evergreen else ''} · rule: Working for you"),
        "source_sentence": f"from your post of {_said_date(post.get('published_at'))}, resurfaced; not a measurement",
        "method_sentence": rule,
        "draft_text": line,
        "seed": seed,
        "block_label": BLOCKS["working_for_you"],
    }
    return _card(card_id, 2, "working_for_you", "opener", label, rule, payload, [{"table": "own_posts", "id": urn}])


# ---------------------------------------------------------------------------
# Slot 3: you asked, matched to your own posts by their words
# ---------------------------------------------------------------------------

def _open_asks(conn) -> List[Dict[str, Any]]:
    return [dict(r) for r in _rows(
        conn, "SELECT id, text, source, field, created_at FROM asks WHERE status != 'retired' AND hidden_at IS NULL "
              "AND (field IS NULL OR field = 'topics') ORDER BY created_at DESC")]


def matches_in_own_posts(conn, text: str, limit: int = 3) -> List[Dict[str, Any]]:
    """
    The creator's own posts that share words with a text, best match first.

    One index: the search_posts FTS5 table universal_search keeps in step
    with own_posts (migrations 22 and 24), ordered by bm25. No second index,
    no second tokenizer.
    """
    # The words that carry meaning, as the topic vocabulary reads them: the
    # same stopwords, length and plural rules (evidence_briefing), so "the",
    # "a" and "without" never match every post. Any of them may match; bm25
    # puts the post that shares the most, and the rarest, first.
    keys = list(dict.fromkeys(key for key, _form, _tag in evidence_briefing._words(text or "")))[:8]
    match = universal_search._searchable(keys)
    if not match:
        return []
    found = []
    for row in _rows(conn, """
            SELECT d.ref AS activity_urn, o.text, o.published_at, bm25(search_posts) AS score
            FROM search_posts f JOIN search_docs d ON d.docid = f.rowid AND d.kind = 'own_post'
            JOIN own_posts o ON o.activity_urn = d.ref
            WHERE search_posts MATCH ? ORDER BY score LIMIT ?""", (" OR ".join(match), limit)):
        found.append({"activity_urn": row["activity_urn"], "excerpt": _excerpt(row["text"]),
                      "date": row["published_at"], "url": post_identity.linkedin_permalink(row["activity_urn"])})
    return found


def playbook_section(conn, text: str) -> Optional[Dict[str, str]]:
    """
    The section of the studio's playbook that shares the most of a text's
    meaningful words, by the Docs search index (the same FTS5 table and
    stemming Docs searches with, bm25 order), or None.

    Only the section's heading and where it lives are kept: the card names
    the section and links to it in Docs, and quotes nothing of it. The index
    is read, never built here: a profile whose Docs index does not exist yet
    gets no playbook line rather than a rebuild inside the daily job.
    """
    keys = list(dict.fromkeys(key for key, _form, _tag in evidence_briefing._words(text or "")))[:8]
    words = [re.sub(r'[^\w]', '', key) for key in keys]
    words = [word for word in words if word]
    if not words:
        return None
    # How many of the words each section holds, by the index's own stemming,
    # so one shared word in a long text is not a match: at least half of
    # them must be there.
    shared: Dict[int, int] = {}
    for word in words:
        for row in _rows(conn, "SELECT rowid FROM docs_index WHERE docs_index MATCH ? AND filename = ?",
                         ('{section content} : "' + word + '"', PLAYBOOK_FILE)):
            shared[row["rowid"]] = shared.get(row["rowid"], 0) + 1
    needed = max(1, math.ceil(len(words) / 2))
    match = "{section content} : (" + " OR ".join(f'"{word}"' for word in words) + ")"
    for row in _rows(conn, "SELECT rowid, section, content FROM docs_index WHERE docs_index MATCH ? AND filename = ? "
                           "ORDER BY rank LIMIT 20", (match, PLAYBOOK_FILE)):
        # The title's own section is the playbook's introduction, which says
        # nothing about any one ask.
        if str(row["content"] or "").lstrip().startswith("# ") or not row["section"]:
            continue
        if shared.get(row["rowid"], 0) >= needed:
            return {"document_id": PLAYBOOK_FILE[:-3], "section": row["section"]}
    return None


def you_asked(conn, posts: List[Dict[str, Any]], topic_counts: Dict[str, int], history: Dict[str, Any],
              day: date, seed: int) -> Dict[str, Any]:
    """
    An ask of theirs with the posts of theirs that share its words, or a
    recurring topic of theirs when nothing was asked, or the sentence that
    says what to type.
    """
    block = "you_asked"
    asks = _open_asks(conn)
    if asks:
        drawn = _draw([(f"ask:{a['id']}", a) for a in asks], history, day, seed + 1)
        if drawn:
            card_id, ask = drawn
            matches = matches_in_own_posts(conn, ask["text"])
            playbook = playbook_section(conn, ask["text"])
            where = {"setup": "at Setup", "ask_box": "on this section", "composer": "in the Composer",
                     "telegram": "from Telegram", "archive_search": "on LinkedIn, in your archive",
                     "more_of_this": "with More of this"}.get(ask["source"], "")
            rule = ("your own asks, in turn, each matched to your own posts by the words they share (the studio's "
                    "search index, bm25), and to the section of the studio's playbook that shares the most of them "
                    "(the Docs index); nothing is read from anywhere else")
            payload = {
                "title": "Something you asked for",
                "badge": "typed",
                "excerpt": _excerpt(ask["text"]),
                "date": ask.get("created_at"),
                "url": None,
                "figures": [],
                "figure_sentence": (f"{len(matches)} of your own posts share its words" if matches
                                    else "none of your own posts shares its words yet"),
                "matches": matches,
                "playbook": playbook,
                "because": (f"Because you asked for “{_excerpt(ask['text'], 80)}” {where} on "
                            f"{_said_weekday(ask.get('created_at'))}"
                            f"{', and ' + str(len(matches)) + ' of your own posts share its words' if matches else ''} "
                            f"· rule: You asked"),
                "source_sentence": f"from the ask you made on {_said_weekday(ask.get('created_at'))}",
                "method_sentence": rule,
                "draft_text": ask["text"],
                "ask_id": ask["id"],
                "block_label": BLOCKS[block],
            }
            rows = [{"table": "asks", "id": ask["id"]}] + [{"table": "own_posts", "id": m["activity_urn"]} for m in matches]
            return _card(card_id, 3, block, "ask", "typed", rule, payload, rows)
    if topic_counts:
        total_posts = max(1, sum(topic_counts.values()))
        named = [(f"theme:{label.casefold()}", (label, count), count / total_posts)
                 for label, count in topic_counts.items() if label != evidence_briefing.OTHER_TOPIC]
        drawn = _draw(named, history, day, seed + 2)
        if drawn:
            card_id, (label, count) = drawn
            matches = matches_in_own_posts(conn, label)
            playbook = playbook_section(conn, label)
            rule = (f"{evidence_briefing.TOPIC_GROUPING}; a post goes under the first of up to "
                    f"{evidence_briefing.MAX_TOPICS} topics it mentions; a keyword grouping, not a reading of what a post means")
            total = sum(topic_counts.values())
            payload = {
                "title": "Your recurring words",
                "badge": "typed",
                "excerpt": label,
                "date": None,
                "url": None,
                "figures": [{"name": "posts_under_topic", "value": count, "table": "own_posts", "id": None,
                             "observed_at": None, "source": f"count of your posts whose topic is {label}"}],
                "figure_sentence": f"{count} of your {total} posts go under it",
                "matches": matches,
                "playbook": playbook,
                "because": f"Because {count} of your {total} posts go under {label}; nothing was asked yet, so your own "
                           f"recurring words stand in · rule: You asked",
                "source_sentence": f"from the words that recur across your {total} posts",
                "method_sentence": rule,
                "draft_text": label,
                "topic": label,
                "block_label": BLOCKS[block],
            }
            return _card(card_id, 3, block, "theme", "typed", rule, payload,
                         [{"table": "own_posts", "id": m["activity_urn"]} for m in matches])
    return _abstained(3, block, "ask", "Nothing asked yet, and too few posts to find your recurring words. Type what "
                      "you want to write about in the ask box, or at Setup.", "your own asks and your recurring words")


# ---------------------------------------------------------------------------
# Slot 4: you engaged with, in your own words
# ---------------------------------------------------------------------------

def you_engaged_with(conn, vocabulary: List[Tuple[str, str]], history: Dict[str, Any], day: date,
                     seed: int) -> Dict[str, Any]:
    """
    A post of somebody else's the creator commented on, reacted to, saved or
    reposted: the link, the date, the kind, and for a comment their own words.

    outbound_engagements.target_author and .target_excerpt are never read:
    other people's posts do not belong on a card any more than in the
    database (migration 2's reason), and a card quotes nothing of the other
    person's beyond what the creator's own comment already does. A comment is
    preferred, because it carries what the creator thinks; a reaction, a
    saved post or a repost is a link, a kind and a date. "Because" counts the creator's
    own comments by the topic of their own words, never by person.
    """
    block = "you_engaged_with"
    month_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    since = (datetime.now(timezone.utc) - timedelta(days=ENGAGED_RECENT_DAYS)).isoformat()

    def comments(where: str, params: Tuple[Any, ...]) -> List[Dict[str, Any]]:
        return [dict(r) for r in _rows(
            conn, "SELECT id, target_activity_urn, my_text, first_seen_at FROM outbound_engagements "
                  "WHERE kind = 'comment' AND my_text IS NOT NULL AND TRIM(my_text) != '' " + where +
                  " ORDER BY first_seen_at DESC LIMIT 200", params)]

    pool = comments("AND first_seen_at >= ?", (since,)) or comments("", ())
    if pool:
        drawn = _draw([(f"eng:{c['id']}", c) for c in pool], history, day, seed + 3)
        if drawn:
            card_id, comment = drawn
            recent = [r["my_text"] for r in _rows(
                conn, "SELECT my_text FROM outbound_engagements WHERE kind = 'comment' AND my_text IS NOT NULL "
                      "AND first_seen_at >= ? LIMIT 2000", (month_ago,))]
            topic = evidence_briefing.classify_post_topic(comment["my_text"], vocabulary) if vocabulary else None
            if topic and topic != evidence_briefing.OTHER_TOPIC:
                same = sum(1 for text in recent if evidence_briefing.classify_post_topic(text, vocabulary) == topic)
                count_said = (f", and {same} comments of yours in the last 30 days were about {topic}, "
                              f"by your own words" if same else "")
            else:
                same = len(recent)
                count_said = f", one of {same} comments of yours in the last 30 days" if same > 1 else ""
            rule = ("your own comments on other people's posts, drawn in turn: the link, the date and your own words; "
                    "the other person's post is never read into the card; counted by the topic of your words, "
                    "never by person")
            payload = {
                "title": "You engaged with",
                "badge": "your comment",
                "excerpt": _excerpt(comment["my_text"]),
                "date": comment["first_seen_at"],
                "url": post_identity.linkedin_permalink(comment["target_activity_urn"]),
                "figures": [{"name": "comments_in_30_days", "value": same, "table": "outbound_engagements",
                             "id": None, "observed_at": None,
                             "source": f"count of your comments since {month_ago[:10]}"
                                       + (f" about {topic}" if topic and topic != evidence_briefing.OTHER_TOPIC else "")}],
                "figure_sentence": "",
                "because": (f"Because you commented on this post on {_said_date(comment['first_seen_at'])}"
                            f"{count_said} · rule: You engaged with"),
                "source_sentence": f"your comment of {_said_date(comment['first_seen_at'])}",
                "method_sentence": rule,
                "draft_text": comment["my_text"],
                "topic": topic,
                "block_label": BLOCKS[block],
            }
            return _card(card_id, 4, block, "comment", "measured", rule, payload,
                         [{"table": "outbound_engagements", "id": comment["id"]}])

    others: List[Tuple[str, Dict[str, Any]]] = []
    for row in _rows(conn, "SELECT id, target_activity_urn, reaction_kind, first_seen_at FROM outbound_engagements "
                           "WHERE kind = 'reaction' ORDER BY first_seen_at DESC LIMIT 200"):
        others.append((f"eng:{row['id']}", {"what": "reaction", **dict(row)}))
    for row in _rows(conn, "SELECT id, url, happened_at FROM archive_records WHERE kind = 'saved_item' AND url IS NOT NULL "
                           "ORDER BY happened_at DESC LIMIT 200"):
        others.append((f"saved:{row['id']}", {"what": "saved", **dict(row)}))
    for row in _rows(conn, "SELECT id, url, happened_at FROM archive_records WHERE kind = 'instant_repost' "
                           "AND url IS NOT NULL ORDER BY happened_at DESC LIMIT 200"):
        others.append((f"repost:{row['id']}", {"what": "reposted", **dict(row)}))
    drawn = _draw(others, history, day, seed + 4) if others else None
    if drawn:
        card_id, item = drawn
        if item["what"] == "reaction":
            word = item.get("reaction_kind") or "a reaction"
            rule = "posts you reacted to: the link, the date and the reaction you used; never the post's text"
            payload = {
                "title": "You reacted to this",
                "badge": f"your reaction: {word}",
                "excerpt": "",
                "date": item.get("first_seen_at"),
                "url": post_identity.linkedin_permalink(item["target_activity_urn"]),
                "figures": [],
                "figure_sentence": "",
                "because": f"Because you reacted ({word}) to this post on {_said_date(item.get('first_seen_at'))} "
                           f"· rule: You engaged with",
                "source_sentence": f"your reaction of {_said_date(item.get('first_seen_at'))}",
                "method_sentence": rule,
                "draft_text": "",
                "block_label": BLOCKS[block],
            }
            return _card(card_id, 4, block, "reaction", "measured", rule, payload,
                         [{"table": "outbound_engagements", "id": item["id"]}])
        if item["what"] == "reposted":
            rule = "the posts you reposted without adding words, from your archive: a link and a date, never the post's text"
            payload = {
                "title": "You reposted this",
                "badge": "from your archive",
                "excerpt": "",
                "date": item.get("happened_at"),
                "url": item["url"],
                "figures": [],
                "figure_sentence": "",
                "because": f"Because you reposted this post on {_said_date(item.get('happened_at'))} · rule: You engaged with",
                "source_sentence": f"reposted on {_said_date(item.get('happened_at'))}, from your archive",
                "method_sentence": rule,
                "draft_text": "",
                "block_label": BLOCKS[block],
            }
            return _card(card_id, 4, block, "repost", "measured", rule, payload,
                         [{"table": "archive_records", "id": item["id"]}])
        rule = "the posts you saved on LinkedIn, from your archive: a link and a date, never the post's text"
        payload = {
            "title": "You saved this",
            "badge": "from your archive",
            "excerpt": "",
            "date": item.get("happened_at"),
            "url": item["url"],
            "figures": [],
            "figure_sentence": "",
            "because": f"Because you saved this post on {_said_date(item.get('happened_at'))} · rule: You engaged with",
            "source_sentence": f"saved on {_said_date(item.get('happened_at'))}, from your archive",
            "method_sentence": rule,
            "draft_text": "",
            "block_label": BLOCKS[block],
        }
        return _card(card_id, 4, block, "saved", "measured", rule, payload, [{"table": "archive_records", "id": item["id"]}])
    if pool or others:
        return _abstained(4, block, "comment", "Every post you engaged with was shown in the last few days or hidden. "
                          "One comes back as its hold ends, and Unhide all on What the studio knows brings back what "
                          "you hid.", "your own comments, reactions, reposts and saved posts, each held back after a showing")
    return _abstained(4, block, "comment", "No comments, reactions, reposts or saved posts of yours imported yet. Import "
                      "your archive in Setup, or run Comments you left; this card fills from your own activity.",
                      "your own comments, reactions, reposts and saved posts")


# ---------------------------------------------------------------------------
# Verification: every card's cited row exists
# ---------------------------------------------------------------------------

# How each kind of cited row is looked up. A row of a table not named here
# cannot be cited at all, which is the allowlist the model stage relies on.
ROW_KEYS = {
    "own_posts": "activity_urn",
    "outbound_engagements": "id",
    "asks": "id",
    "archive_records": "id",
    "library_entries": "entry_id",
}


def missing_rows(conn, source_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The cited rows that do not exist, or cite a table no card may cite."""
    missing = []
    for row in source_rows:
        key = ROW_KEYS.get(row.get("table"))
        if key is None:
            missing.append(row)
            continue
        if _scalar(conn, f"SELECT 1 FROM {row['table']} WHERE {key} = ?", (row.get("id"),)) is None:
            missing.append(row)
    return missing


def verify(conn, card: Dict[str, Any]) -> Dict[str, Any]:
    """
    Marks a card dropped when a row it cites does not exist, and records the
    check on its provenance either way. Nothing is repaired: a dropped card
    is counted on the day's run and never shown.
    """
    gone = missing_rows(conn, card["provenance"].get("source_rows") or [])
    verification = card["provenance"].setdefault("verification", _verification())
    verification["ids_exist"] = not gone
    if gone and card["status"] == "shown":
        card["status"] = "dropped"
        verification["dropped_reason"] = (f"{len(gone)} cited row{'s' if len(gone) != 1 else ''} not found: "
                                          + ", ".join(f"{r.get('table')}:{r.get('id')}" for r in gone[:3]))
    return card


# ---------------------------------------------------------------------------
# The Monday card: counts only, no comparison (decision 4)
# ---------------------------------------------------------------------------

def monday_card(conn, day: date) -> Optional[Dict[str, Any]]:
    if day.weekday() != 0:
        return None
    start = datetime.combine(day - timedelta(days=7), datetime.min.time(), tzinfo=timezone.utc).isoformat()
    end = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc).isoformat()

    def count(sql: str) -> Optional[int]:
        value = _scalar(conn, sql, (start, end))
        return None if value is None else int(value)

    counts = {
        "posts_published": count("SELECT COUNT(*) FROM own_posts WHERE published_at >= ? AND published_at < ?"),
        "comments_given": count("SELECT COUNT(*) FROM outbound_engagements WHERE kind = 'comment' AND first_seen_at >= ? AND first_seen_at < ?"),
        "reactions_given": count("SELECT COUNT(*) FROM outbound_engagements WHERE kind = 'reaction' AND first_seen_at >= ? AND first_seen_at < ?"),
        "captures": count("SELECT COUNT(*) FROM captures WHERE observed_at >= ? AND observed_at < ?"),
        # Replies answered are a creator-set mark in reply_marks (sections decision 9,
        # track 4); on a database without the table the count is not measured.
        "replies_answered": count("SELECT COUNT(*) FROM reply_marks WHERE marked_at >= ? AND marked_at < ?"),
    }
    rule = "counts of your own rows in the seven days before today; no figure unless measured, no comparison"
    said = {"posts_published": ("post published", "posts published"),
            "comments_given": ("comment given", "comments given"),
            "reactions_given": ("reaction given", "reactions given"),
            "captures": ("page read by the bridge", "pages read by the bridge"),
            "replies_answered": ("reply answered", "replies answered")}
    figures = [{"name": name, "value": value, "table": {"posts_published": "own_posts", "comments_given": "outbound_engagements",
                                                           "reactions_given": "outbound_engagements", "captures": "captures",
                                                           "replies_answered": "reply_marks"}[name],
                "id": None, "observed_at": end, "source": f"count of rows from {start[:10]} to {end[:10]}"}
               for name, value in counts.items() if value is not None]
    sentence = ", ".join(f"{value} {said[name][0] if value == 1 else said[name][1]}" if value is not None
                         else f"{said[name][1]} not measured" for name, value in counts.items())
    payload = {
        "title": "Your week",
        "badge": "measured counts",
        "excerpt": sentence,
        "date": end,
        "url": None,
        "figures": figures,
        "figure_sentence": sentence,
        "because": f"Because it is Monday: what the studio recorded from {_said_date(start)} to {_said_date(end)} · rule: counts only",
        "source_sentence": f"your own rows, {start[:10]} to {end[:10]}",
        "method_sentence": rule,
        "draft_text": "",
        "counts": counts,
        "block_label": BLOCKS["monday"],
    }
    # A count over a week cites no single row: its figures name the tables they count.
    return _card(f"monday:{day.isocalendar()[0]}-W{day.isocalendar()[1]:02d}", 0, "monday", "monday", "measured", rule,
                 payload, [], figures)


# ---------------------------------------------------------------------------
# The batch
# ---------------------------------------------------------------------------

def compute_local(conn, day: date, seed: int) -> Dict[str, Any]:
    """
    Stage 1 for one day: the slots this module can fill, the abstentions it
    cannot, and what it rested on. Nothing here opens a socket.
    """
    posts = _posts(conn)
    _vocabulary, topics_of, topic_counts = _topics(posts) if posts else ([], {}, {})
    history = _history(conn, day)
    cards: List[Dict[str, Any]] = []
    cards.append(what_worked(conn, posts, history, day))
    second = on_this_day(conn, posts, day, history) or resurfaced_opener(conn, posts, topics_of, history, day, seed)
    if second is None and posts:
        second = _abstained(2, "working_for_you", "opener", "No opener of yours is free to resurface today: every one "
                            "is held back after a showing, or was hidden. Unhide all on What the studio knows brings them back.",
                            "the resurfacing rule")
    if second is not None:
        cards.append(second)
    cards.append(you_asked(conn, posts, topic_counts, history, day, seed))
    cards.append(you_engaged_with(conn, _vocabulary, history, day, seed))
    monday = monday_card(conn, day)
    if monday is not None:
        cards.append(monday)
    cards = [verify(conn, card) for card in cards]
    shown = [c for c in cards if c["status"] == "shown"]
    return {
        "day": day.isoformat(),
        "seed": seed,
        "cards": cards,
        "filled_slots": sorted({c["slot"] for c in shown if 1 <= c["slot"] <= SLOTS}),
        "dropped": sum(1 for c in cards if c["status"] == "dropped"),
        "inputs": {"posts": len(posts), "topics": len(topic_counts), "asks": len(_open_asks(conn))},
    }


def store_batch(conn, day: date, batch: Dict[str, Any], replace: bool = True) -> int:
    """Writes a day's rows into daily_view, as the daily job's one write of them."""
    now = _now_iso()
    if replace:
        conn.execute("DELETE FROM daily_view WHERE day = ?", (day.isoformat(),))
    written = 0
    for card in batch["cards"]:
        conn.execute(
            "INSERT OR REPLACE INTO daily_view (day, card_id, slot, block, kind, label, method, payload_json, "
            "provenance_json, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (day.isoformat(), card["card_id"], card["slot"], card["block"], card["kind"], card["label"], card["method"],
             json.dumps(card["payload"], sort_keys=True), json.dumps(card["provenance"], sort_keys=True),
             card["status"], now))
        written += 1
    return written


def read_batch(conn, day: date) -> List[Dict[str, Any]]:
    """A day's rows as the screen reads them: a SELECT, never a computation."""
    out = []
    for row in _rows(conn, "SELECT * FROM daily_view WHERE day = ? ORDER BY slot, card_id", (day.isoformat(),)):
        item = dict(row)
        item["payload"] = json.loads(item.pop("payload_json") or "{}")
        item["provenance"] = json.loads(item.pop("provenance_json") or "{}")
        out.append(item)
    return out
