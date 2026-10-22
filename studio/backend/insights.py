"""
Posts and Outbound: what your own history says.
===============================================

Two questions a creator can act on, answered only from what the studio
observed on their own account:

  Posts     Which of my posts worked, and whom did each one bring?
  Outbound  Whose content do I spend my attention on, and does it come back?

Neither screen predicts anything. A post is compared with your own median, not
with a benchmark, and "worked" is said only of posts old enough for their
numbers to have settled. Reciprocity is matched by name, because a reaction
records the author's display name and not their profile, and the screen says
so rather than presenting a name match as an identity.

Strict Invariants:
- Zero em-dashes.
- Every comparison carries the number of posts it rests on.
- A count never read is shown as unknown, not as zero.
"""

import json
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    from .text_cut import clip
except ImportError:
    from text_cut import clip

try:
    from . import contrast_engine, onboarding, post_identity, post_summary
    from .database import get_db
except ImportError:
    import contrast_engine
    import onboarding
    import post_identity
    import post_summary
    from database import get_db

# A post's reactions and comments have mostly arrived by a week. Before that
# a low number may just be a young post, so it is not called weak.
SETTLED_AFTER_HOURS = 7 * 24
MIN_FOR_MEDIAN = 3

# ---------------------------------------------------------------------------
# One page of posts
# ---------------------------------------------------------------------------
#
# Posts and Analytics each answered with every post the creator has ever
# written, each carrying the people who engaged with it: measured on three
# years, 2,201 KB from /api/v1/insights/posts and 2,432 KB from
# /api/analytics/posts, on every load of either screen, and the second
# accepted a `limit` in the URL and ignored it. One page of 50 is 78 KB and
# 83 KB. Both endpoints page through here, so the contract is written once:
# the rows of one page, and what a caller needs to ask for the next.
#
# Only the list of posts is a page. Every figure beside it (the creator's
# usual, which posts are worth repurposing, how many settled posts carry no
# figures) is still computed from the whole history, because a median of the
# first fifty posts is a different number, not the same number read faster.

POSTS_PAGE = 50
POSTS_PAGE_MAX = 200


def page_bounds(limit: Optional[int], offset: Optional[int]) -> tuple:
    """The page a caller asked for, as (size, start), clamped to what one answer carries."""
    size = POSTS_PAGE if limit is None else max(1, min(int(limit), POSTS_PAGE_MAX))
    return size, max(0, int(offset or 0))


def paging(total: int, size: int, start: int, returned: int) -> Dict[str, Any]:
    """What a caller needs to know to ask for the rest, as every paged answer says it."""
    return {"total": total, "limit": size, "offset": start, "returned": returned,
            "has_more": start + returned < total}


def _age_hours(published_at: Optional[str]) -> Optional[float]:
    if not published_at:
        return None
    return (datetime.now(timezone.utc) - datetime.fromisoformat(published_at)).total_seconds() / 3600.0


def _excerpt(text: Optional[str], limit: int = 140) -> Optional[str]:
    return clip(" ".join((text or "").split()), limit) or None


def posts_overview(limit: Optional[int] = None, offset: Optional[int] = None) -> Dict[str, Any]:
    size, start = page_bounds(limit, offset)
    conn = get_db()
    try:
        # Every post's figures, which the usual, the best two and the counts
        # below are all read from, and which carry no text: the text of 1,417
        # posts was most of the 2,201 KB this answer used to be.
        posts = [dict(r) for r in conn.execute(
            "SELECT activity_urn, published_at, published_at_source, reactions, comments, impressions "
            "FROM own_posts ORDER BY published_at DESC")]
        # The page itself, newest first, with the text the screen shows.
        page = [dict(r) for r in conn.execute(
            "SELECT activity_urn, text, published_at, published_at_source, reactions, comments, reposts, impressions "
            "FROM own_posts ORDER BY published_at DESC LIMIT ? OFFSET ?", (size, start))]

        # Who engaged with each post on the page, from the per-post summary.
        # Every interaction used to be read into Python on every load: 1.9 s
        # at 500,000. A post whose engagement was recorded under two spellings
        # of its URN is counted from the raw rows, each person once.
        summary = post_summary.current(conn)
        wanted = {onboarding._activity_id(p["activity_urn"]) for p in page}
        spellings: Dict[str, List[str]] = {}
        for urn, row in summary.items():
            key = onboarding._activity_id(urn)
            if key in wanted and (row["people"] or row["folded_reactions"]):
                spellings.setdefault(key, []).append(urn)
        engagers: Dict[str, Dict[str, Any]] = {
            key: (summary[urns[0]] if len(urns) == 1 else post_summary.combined(conn, urns))
            for key, urns in spellings.items()}
    finally:
        conn.close()

    settled = [p for p in posts if (_age_hours(p["published_at"]) or 0) >= SETTLED_AFTER_HOURS]

    def median_of(metric):
        values = [p[metric] for p in settled if p[metric] is not None]
        return (statistics.median(values), len(values)) if len(values) >= MIN_FOR_MEDIAN else (None, len(values))

    usual = {m: median_of(m) for m in ("reactions", "comments", "impressions")}

    # Settled posts with no figures at all, usually from LinkedIn's archive,
    # which carries none. Counted so the screen can say why there is no
    # usual, rather than blaming the age of posts that are years old.
    unmeasured = [p for p in settled if all(p[m] is None for m in ("reactions", "comments", "impressions"))]

    def against_usual(post, age):
        ratios = {}
        for metric, (median, _n) in usual.items():
            if median and post[metric] is not None and age is not None and age >= SETTLED_AFTER_HOURS:
                ratios[metric] = round(post[metric] / median, 2)
        return ratios

    out = []
    for post in page:
        age = _age_hours(post["published_at"])
        engaged = engagers.get(onboarding._activity_id(post["activity_urn"]))
        ratios = against_usual(post, age)

        out.append({
            "activity_urn": post["activity_urn"],
            "excerpt": _excerpt(post["text"]),
            "published_at": post["published_at"],
            "age_days": round(age / 24, 1) if age is not None else None,
            "settled": age is not None and age >= SETTLED_AFTER_HOURS,
            "reactions": post["reactions"],
            "comments": post["comments"],
            "reposts": post["reposts"],
            "impressions": post["impressions"],
            "against_usual": ratios or None,
            # Commenters first, then by name, at most post_summary.TOP_PEOPLE.
            "people": post_summary.people_of(engaged),
            # Reactions older than 24 months are kept as counts once the
            # retention job folds them (retention.py). The summary's people
            # include the folded reactors who did nothing else on this post;
            # one who also commented is counted once, from the comment.
            # folded_reactions is how many reactions were folded.
            "people_count": engaged["people"] if engaged else 0,
            "folded_reactions": engaged["folded_reactions"] if engaged else 0,
            # People from this post the creator went on to talk to: Connected
            # or Meeting Booked. The question the Posts screen exists for.
            "conversations": engaged["conversations"] if engaged else 0,
            # None for a post published from the studio and not yet seen on
            # LinkedIn: it is recorded under a local key, and a link built
            # from that key would 404.
            "url": post_identity.linkedin_permalink(post["activity_urn"]),
        })

    # The two settled posts that did best against your own median reactions,
    # which is what "repurpose the top two" means: forms that already worked.
    # Read from the whole history, not from the page, so the same two posts
    # are named whichever page the screen is showing.
    with_ratio = [(p["activity_urn"], against_usual(p, _age_hours(p["published_at"]))) for p in posts]
    ranked = sorted(((urn, r["reactions"]) for urn, r in with_ratio if "reactions" in r),
                    key=lambda pair: pair[1], reverse=True)
    return {
        "status": "success",
        "posts": out,
        **paging(len(posts), size, start, len(out)),
        "usual": {m: {"median": v[0], "posts": v[1]} for m, v in usual.items()},
        "best": [urn for urn, _ratio in ranked[:2]],
        "settled_after_days": SETTLED_AFTER_HOURS // 24,
        "settled_without_figures": len(unmeasured),
        "settled_without_figures_from_archive": sum(1 for p in unmeasured if p["published_at_source"] == "archive"),
    }


def _name_key(name: Optional[str]) -> str:
    return " ".join((name or "").lower().split())


def outbound_overview() -> Dict[str, Any]:
    conn = get_db()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT target_author, kind, reaction_kind, my_text, last_seen_at FROM outbound_engagements")]
        own_ids = onboarding._own_activity_ids(conn)
        # People who engaged with your posts, by display name, and on how
        # many of them: a comment and a like on one post is one post, not two.
        #
        # Only the names of accounts you engaged with can be matched, so only
        # leads with one of those names are looked up, and their interactions
        # read by lead. Reading every interaction to build every name's set
        # took 1.1 s at 500,000.
        wanted = {_name_key(r["target_author"]) for r in rows if r["target_author"]}
        named: Dict[str, str] = {}
        if wanted:
            for lead in conn.execute("SELECT id, COALESCE(full_name, name) AS name FROM leads"):
                key = _name_key(lead["name"])
                if key in wanted:
                    named[lead["id"]] = key
        engaged_back: Dict[str, set] = {}
        if named:
            for row in conn.execute(
                "SELECT CAST(lead_id AS TEXT) AS lead_id, post_urn FROM lead_interactions "
                "WHERE lead_id IN (SELECT value FROM json_each(?)) AND post_urn IS NOT NULL",
                (json.dumps(list(named)),)):
                post = onboarding._activity_id(row["post_urn"])
                if post in own_ids and row["lead_id"] in named:
                    engaged_back.setdefault(named[row["lead_id"]], set()).add(post)
        # Which of your posts the studio has read engagers on, for coverage.
        read_posts = {onboarding._activity_id(urn) for urn, row in post_summary.current(conn).items()
                      if row["people"] or row["folded_reactions"]}
    finally:
        conn.close()

    authors: Dict[str, Dict[str, Any]] = {}
    unknown = 0
    for row in rows:
        if not row["target_author"]:
            unknown += 1
            continue
        key = _name_key(row["target_author"])
        entry = authors.setdefault(key, {"name": row["target_author"], "reactions": 0, "comments": 0,
                                         "last_at": None})
        entry["reactions" if row["kind"] == "reaction" else "comments"] += 1
        if (row["last_seen_at"] or "") > (entry["last_at"] or ""):
            entry["last_at"] = row["last_seen_at"]

    for key, entry in authors.items():
        entry["total"] = entry["reactions"] + entry["comments"]
        entry["engaged_back"] = len(engaged_back.get(key, ()))

    ranked = sorted(authors.values(), key=lambda a: (a["total"], a["comments"]), reverse=True)

    # "Never engaged back" is only a finding once the studio has read who
    # engaged with most of your posts. Engagers are captured as you open your
    # posts, so on a new install nobody has, and every account would be listed
    # as one-way on the strength of the studio not having looked. Measured on
    # the first live install: 1 engager captured, and 6 of 6 top accounts
    # would have been called one-way.
    conn = get_db()
    try:
        engaged_posts = [r["activity_urn"] for r in conn.execute(
            "SELECT activity_urn FROM own_posts WHERE COALESCE(reactions, 0) + COALESCE(comments, 0) > 0")]
    finally:
        conn.close()
    covered = sum(1 for urn in engaged_posts if onboarding._activity_id(urn) in read_posts)
    coverage = round(covered / len(engaged_posts), 2) if engaged_posts else 0.0
    judged = coverage >= 0.5

    return {
        "coverage": {"posts_read": covered, "posts_with_engagement": len(engaged_posts), "share": coverage,
                     "one_way_judged": judged},
        "status": "success",
        "totals": {"reactions": sum(1 for r in rows if r["kind"] == "reaction"),
                   "comments": sum(1 for r in rows if r["kind"] == "comment"),
                   "authors": len(authors), "without_author": unknown},
        "authors": ranked[:40],
        # Accounts you engaged with at least three times that have never
        # engaged with a post of yours: where your attention goes one way.
        "one_way": ([a["name"] for a in ranked if a["total"] >= 3 and not a["engaged_back"]][:12]
                    if judged else []),
        "reciprocal": [a["name"] for a in ranked if a["engaged_back"]][:12],
        "matched_by": "display name",
    }


# ---------------------------------------------------------------------------
# Patterns: which forms have gone with more engagement, for you
# ---------------------------------------------------------------------------
#
# Each pattern splits your settled posts in two (has it, does not) and compares
# the median reactions of each side. A pattern is shown only when both sides
# have at least MIN_PER_SIDE posts, and always with both counts, because on a
# few dozen posts a difference is a lead to try, not a finding. The wording is
# "went with", never "causes": this compares posts, it runs no experiment.

import re as _re
import unicodedata as _unicodedata

MIN_PER_SIDE = 3

_ANNOUNCEMENT = _re.compile(
    r"\b(excited|thrilled|happy to share|pleased to|proud to|congratulations|new position|starting a new)\b",
    _re.IGNORECASE)


def opening_line(text: Optional[str]) -> str:
    """What shows before anything else: the first line, or the first sentence of a one-line post."""
    lines = [l.strip() for l in (text or "").split("\n") if l.strip()]
    if not lines:
        return ""
    first = lines[0]
    if len(lines) == 1:
        match = _re.match(r"(.{1,200}?[.!?])(\s|$)", first)
        if match:
            first = match.group(1)
    return first


def _opens_with_symbol(line: str) -> bool:
    return bool(line) and _unicodedata.category(line[0]) == "So"


def _has_bold_unicode(text: str) -> bool:
    return any(0x1D400 <= ord(ch) <= 0x1D7FF for ch in text)


PATTERNS = [
    ("short_opening", "An opening line of 60 characters or fewer",
     lambda text, opening: len(opening) <= 60),
    ("question_opening", "An opening line that asks a question",
     lambda text, opening: "?" in opening),
    ("symbol_opening", "An opening that starts with an emoji or symbol",
     lambda text, opening: _opens_with_symbol(opening)),
    ("announcement", "An announcement (excited, thrilled, happy to share, new position)",
     lambda text, opening: bool(_ANNOUNCEMENT.search(opening))),
    ("bold_unicode", "Bold or styled Unicode letters",
     lambda text, opening: _has_bold_unicode(text)),
    ("hashtags", "Hashtags",
     lambda text, opening: "#" in text),
    ("long_post", "More than 1,500 characters",
     lambda text, opening: len(text) > 1500),
]


def patterns_overview() -> Dict[str, Any]:
    conn = get_db()
    try:
        posts = [dict(r) for r in conn.execute(
            "SELECT text, published_at, reactions FROM own_posts WHERE reactions IS NOT NULL AND text IS NOT NULL")]
        # Left out because no reactions were ever read for them, as for every
        # post imported from LinkedIn's archive. Not because of their age.
        unread = [dict(r) for r in conn.execute(
            "SELECT published_at, published_at_source FROM own_posts WHERE reactions IS NULL")]
    finally:
        conn.close()
    settled = [p for p in posts if (_age_hours(p["published_at"]) or 0) >= SETTLED_AFTER_HOURS]
    unread = [p for p in unread if (_age_hours(p["published_at"]) or 0) >= SETTLED_AFTER_HOURS]

    found, too_few = [], []
    for key, label, test in PATTERNS:
        with_it, without, with_dates, without_dates = [], [], [], []
        for post in settled:
            has = test(post["text"], opening_line(post["text"]))
            (with_it if has else without).append(post["reactions"])
            (with_dates if has else without_dates).append(datetime.fromisoformat(post["published_at"]).timestamp())
        entry = {"key": key, "label": label, "with_posts": len(with_it), "without_posts": len(without)}
        if len(with_it) < MIN_PER_SIDE or len(without) < MIN_PER_SIDE:
            too_few.append(entry)
            continue
        a, b = statistics.median(with_it), statistics.median(without)
        entry.update({"with_median": a, "without_median": b, "ratio": round(a / b, 2) if b else None})
        # When the two sides come from different periods, the difference may
        # be about when rather than how. Measured on the first live install:
        # hashtags went with 2.7x the reactions, and the hashtag posts were
        # mostly from two years earlier, when the account and its audience
        # were different. Flagged rather than hidden.
        entry.update(contrast_engine.different_periods(with_dates, without_dates))
        found.append(entry)

    found.sort(key=lambda e: abs((e["ratio"] or 1) - 1), reverse=True)
    return {
        "status": "success",
        "posts_compared": len(settled),
        "settled_without_reactions": len(unread),
        "settled_without_reactions_from_archive": sum(1 for p in unread if p["published_at_source"] == "archive"),
        "metric": "reactions",
        "patterns": found,
        "not_enough_posts": too_few,
        "min_per_side": MIN_PER_SIDE,
    }


# ---------------------------------------------------------------------------
# Cadence: how steadily you post
# ---------------------------------------------------------------------------
#
# Counts, gaps and the queue. It deliberately does not name a best day or
# time: the studio does not choose when your posts go out, so the days you
# posted on are the days you chose, and a few posts per weekday cannot separate
# the day from everything else about those posts.

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def cadence_overview() -> Dict[str, Any]:
    conn = get_db()
    try:
        dates = [datetime.fromisoformat(r["published_at"]).astimezone()
                 for r in conn.execute("SELECT published_at FROM own_posts WHERE published_at IS NOT NULL "
                                       "ORDER BY published_at")]
        now = datetime.now(timezone.utc)
        horizon = (now + timedelta(days=14)).isoformat()
        scheduled = conn.execute(
            "SELECT COUNT(*) FROM posts WHERE status = 'scheduled' AND scheduled_for IS NOT NULL "
            "AND scheduled_for >= ? AND scheduled_for <= ?", (now.isoformat(), horizon)).fetchone()[0]
        slots = conn.execute("SELECT COUNT(*) FROM queue_slots WHERE is_active = 1").fetchone()[0]
    finally:
        conn.close()

    if not dates:
        return {"status": "success", "posts": 0}

    gaps = [(b - a).total_seconds() / 86400.0 for a, b in zip(dates, dates[1:])]
    months: Dict[str, int] = {}
    cursor = dates[0].replace(day=1)
    end = datetime.now().astimezone()
    while (cursor.year, cursor.month) <= (end.year, end.month):
        months[f"{cursor.year:04d}-{cursor.month:02d}"] = 0
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    for d in dates:
        months[f"{d.year:04d}-{d.month:02d}"] = months.get(f"{d.year:04d}-{d.month:02d}", 0) + 1

    longest = max(range(len(gaps)), key=lambda i: gaps[i]) if gaps else None
    return {
        "status": "success",
        "posts": len(dates),
        "first_post": dates[0].date().isoformat(),
        "last_post": dates[-1].date().isoformat(),
        "days_since_last": round((datetime.now().astimezone() - dates[-1]).total_seconds() / 86400.0, 1),
        "median_gap_days": round(statistics.median(gaps), 1) if gaps else None,
        "longest_gap": ({"days": round(gaps[longest], 1), "from": dates[longest].date().isoformat(),
                         "to": dates[longest + 1].date().isoformat()} if longest is not None else None),
        "by_month": [{"month": m, "posts": n} for m, n in months.items()],
        "by_weekday": [{"day": WEEKDAYS[i], "posts": sum(1 for d in dates if d.weekday() == i)} for i in range(7)],
        "queue": {"scheduled_next_14_days": scheduled, "weekly_slots": slots},
    }
