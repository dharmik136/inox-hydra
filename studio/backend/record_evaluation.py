"""
From your record: did the cards help? Marks, a comparison, a sentence a month.
==============================================================================
There is no telemetry, by design, and none is needed: the marks are rows in
the creator's own database. Three things can be said, each with the counts
beside it and each able to say that it cannot say anything yet:

  the funnel      for each kind of card and each label: how many were shown,
                  kept against skipped, drafted from, and posted. These are
                  the creator's judgements of the cards, a preference, not an
                  effect: a persuasive card can be a bad one. The sample rules
                  are DATA_ARCHITECTURE's: under 5 the counts and no rate,
                  5 to 19 a tilde with the denominator, 20 or more the rate
                  with its denominator still beside it
  the comparison  the creator's posts that came from a card against their
                  other posts of the same 90 days, at about 48 hours, as a
                  ratio of medians with both counts. Contemporaneous, because
                  selecting their best past posts to reuse guarantees
                  regression toward the mean, and the right comparison is the
                  posts written beside them, not the post the card came from.
                  It abstains under results.MIN_PER_SIDE (8) a side, and when
                  the posts it rests on cannot show a difference smaller than
                  a doubling (n = 16 sigma squared over delta squared, sigma
                  measured from the creator's own readings where it can be)
  the month       one of three sentences: A, the comparison for that month
                  with its caveat; B, too few posts came from a card; C, no
                  readings for that month's posts yet

A/B tests and bandits are not offered: a creator posting three times a
week makes about 150 posts a year, and detecting even a 50 percent lift
needs about 64 a side.

Strict Invariants:
- Zero em-dashes.
- Zero egress.
- No percentage without the counts beside it, and none under 20.
"""

import math
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from . import post_summary, record_daily, results
    from .database import get_db
except ImportError:  # top-level import mode
    import post_summary
    import record_daily
    import results
    from database import get_db

WINDOW_DAYS = 90
FEWEST_FOR_A_RATE = 5
FULL_TREATMENT_AT = 20
FEWEST_FOR_A_MONTH = 5
LARGEST_DETECTABLE = 2.0
GONE_OUT = ("published", "sent")
# Shown without a Keep, Skip or Draft button, so never in the funnel.
UNMARKABLE = ("monday",)

KIND_WORDS = {
    "what_worked": "What worked", "on_this_day": "On this day", "opener": "Openers to reuse",
    "ask": "Your asks", "theme": "Your recurring words", "comment": "Your comments",
    "reaction": "Your reactions", "saved": "Your saved posts", "repost": "Your reposts", "idea": "Your model's ideas",
    "library": "The Inox library",
}


def said_share(part: int, whole: int) -> Dict[str, Any]:
    """A share said under the studio's sample rules: the counts always, a rate only at 20 or more."""
    if whole < FEWEST_FOR_A_RATE:
        return {"part": part, "whole": whole, "said": f"{part} of {whole}, too few to call a rate", "rate": None}
    if whole < FULL_TREATMENT_AT:
        return {"part": part, "whole": whole, "said": f"~{part} of {whole}", "rate": None}
    rate = round(100.0 * part / whole)
    return {"part": part, "whole": whole, "said": f"{part} of {whole} ({rate}%)", "rate": rate}


# ---------------------------------------------------------------------------
# The funnel
# ---------------------------------------------------------------------------

def funnel(conn) -> Dict[str, Any]:
    """Shown, kept against skipped, drafted from and posted, by kind and by label."""
    # The Monday line carries no buttons: it can be neither kept nor drafted
    # from, so counting it as shown would only lower every rate beside it.
    shown: Dict[Tuple[str, str], int] = {}
    for kind, label, count in conn.execute(
            "SELECT kind, label, COUNT(*) FROM (SELECT DISTINCT day, card_id, kind, label FROM daily_view "
            "WHERE status = 'shown' AND kind NOT IN (" + ", ".join("?" for _ in UNMARKABLE) + ")) GROUP BY kind, label",
            UNMARKABLE):
        shown[(kind, label)] = count
    marks: Dict[Tuple[str, str, str], int] = {}
    for kind, label, mark, count in conn.execute(
            "SELECT v.kind, v.label, m.mark, COUNT(DISTINCT m.day || ':' || m.card_id) FROM card_marks m "
            "JOIN daily_view v ON v.day = m.day AND v.card_id = m.card_id "
            "WHERE v.kind NOT IN (" + ", ".join("?" for _ in UNMARKABLE) + ") GROUP BY v.kind, v.label, m.mark",
            UNMARKABLE):
        marks[(kind, label, mark)] = count

    def group(rows: List[Tuple[str, Dict[str, int]]]) -> List[Dict[str, Any]]:
        out = []
        for name, counts in rows:
            out.append({
                "name": name,
                "shown": counts["shown"],
                "kept": said_share(counts["keep"], counts["keep"] + counts["skip"]),
                "drafted": said_share(counts["used"], counts["shown"]),
                "posted": said_share(counts["posted"], counts["used"]),
            })
        return out

    def counts_for(match) -> Dict[str, int]:
        total = {"shown": 0, "keep": 0, "skip": 0, "used": 0, "posted": 0}
        for (kind, label), count in shown.items():
            if match(kind, label):
                total["shown"] += count
        for (kind, label, mark), count in marks.items():
            if match(kind, label) and mark in total:
                total[mark] += count
        return total

    kinds = sorted({kind for kind, _label in shown})
    labels = sorted({label for _kind, label in shown})
    return {
        "by_kind": group([(KIND_WORDS.get(k, k), counts_for(lambda kind, label, k=k: kind == k)) for k in kinds]),
        "by_label": group([(l, counts_for(lambda kind, label, l=l: label == l)) for l in labels]),
        "total": group([("Every card", counts_for(lambda kind, label: True))])[0] if shown else None,
        "note": "Kept, drafted and posted are your judgements of the cards: what you preferred, not what worked.",
    }


# ---------------------------------------------------------------------------
# The comparison at 48 hours
# ---------------------------------------------------------------------------

def _posts_from_cards(conn) -> Dict[str, str]:
    """Each post that came from a card and has gone out, by its LinkedIn id, with the card it came from."""
    out = {}
    for urn, card in conn.execute(
            "SELECT activity_urn, origin_card_id FROM posts WHERE origin_card_id IS NOT NULL AND activity_urn IS NOT NULL "
            f"AND status IN ({', '.join('?' for _ in GONE_OUT)})", GONE_OUT):
        out[urn] = card
    return out


def _reading_48h(conn, urns: List[str]) -> Dict[str, Optional[float]]:
    rows = post_summary.current(conn, urns)
    out = {}
    for urn in urns:
        reading = post_summary.reading_of(rows.get(urn), "reading_48h")
        out[urn] = reading.get("reactions") if reading else None
    return out


def _spread(values: List[float]) -> Tuple[float, str]:
    """The coefficient of variation of the creator's own readings, or 1 when too few to measure, said which."""
    if len(values) >= results.MIN_FOR_MEDIAN and statistics.mean(values) > 0:
        return statistics.pstdev(values) / statistics.mean(values), "measured from your own readings"
    return 1.0, "assumed equal to the mean, since too few of your posts were read to measure it"


def detectable(n_small: int, spread: float) -> float:
    """
    The smallest ratio this many posts a side could show, from n = 16 sigma
    squared over delta squared (about 80 percent power at the 5 percent level).
    """
    if n_small <= 0:
        return math.inf
    return 1.0 + 4.0 * spread / math.sqrt(n_small)


def compare(conn, posts: List[Dict[str, Any]], from_cards: Dict[str, str]) -> Dict[str, Any]:
    """Posts from cards against the others among `posts`, at about 48 hours, or the sentence why not."""
    urns = [p["activity_urn"] for p in posts]
    readings = _reading_48h(conn, urns)
    with_card = [readings[u] for u in urns if u in from_cards and readings[u] is not None]
    without = [readings[u] for u in urns if u not in from_cards and readings[u] is not None]
    spread, spread_said = _spread([v for v in readings.values() if v is not None])
    base = {"n_with": len(with_card), "n_without": len(without), "posts": len(urns),
            "posts_from_cards": sum(1 for u in urns if u in from_cards), "min_per_side": results.MIN_PER_SIDE,
            "spread": round(spread, 2), "spread_said": spread_said}
    if not with_card and not without:
        return {**base, "verdict": "no_readings"}
    if len(with_card) < results.MIN_PER_SIDE or len(without) < results.MIN_PER_SIDE:
        return {**base, "verdict": "too_few_posts"}
    median_with, median_without = statistics.median(with_card), statistics.median(without)
    smallest = detectable(min(len(with_card), len(without)), spread)
    base.update({"median_with": median_with, "median_without": median_without, "detectable": round(smallest, 1)})
    if not median_without:
        return {**base, "verdict": "not_measured"}
    ratio = round(median_with / median_without, 2)
    verdict = results.difference(ratio, len(with_card), len(without))
    return {**base, "ratio": ratio, "verdict": verdict["verdict"],
            "too_small_to_tell": smallest > LARGEST_DETECTABLE}


def comparison(conn, today: Optional[date] = None) -> Dict[str, Any]:
    """The last 90 days, said in a sentence."""
    today = today or record_daily.local_today()
    since = (datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=WINDOW_DAYS)).isoformat()
    posts = [dict(r) for r in conn.execute(
        "SELECT activity_urn, published_at FROM own_posts WHERE published_at >= ?", (since,))]
    answer = compare(conn, posts, _posts_from_cards(conn))
    n_with, n_without = answer["n_with"], answer["n_without"]
    if answer["verdict"] == "no_readings":
        sentence = (f"None of your posts of the last {WINDOW_DAYS} days was read at about two days old, so nothing "
                    "can be compared yet.")
    elif answer["verdict"] == "too_few_posts":
        sentence = (f"{n_with} of your posts from the last {WINDOW_DAYS} days came from a card and were read at about "
                    f"two days old, against {n_without} others. {results.MIN_PER_SIDE} a side are needed before the "
                    "two can be compared, so nothing is said yet.")
    elif answer["verdict"] == "not_measured":
        sentence = "Your other posts' median at about two days is 0 reactions, so no ratio can be measured."
    elif answer["too_small_to_tell"]:
        sentence = (f"{n_with} posts from cards and {n_without} others cannot show a difference smaller than about "
                    f"{answer['detectable']}x (the spread {answer['spread_said']}), so nothing is said yet.")
    else:
        what = {"more": "more", "fewer": "fewer", "none": results.NO_DIFFERENCE}.get(answer["verdict"], answer["verdict"])
        sentence = (f"In the last {WINDOW_DAYS} days, your {n_with} posts from cards drew {answer['ratio']} times your "
                    f"usual reactions at about two days (median {answer['median_with']:g} against {answer['median_without']:g} "
                    f"across {n_without} other posts): {what}. These posts cannot show a difference smaller than about "
                    f"{answer['detectable']}x, and a post built from an earlier best is expected to do less well than "
                    "that best did, so this is a note, not a finding.")
    return {**answer, "sentence": sentence, "window_days": WINDOW_DAYS}


# ---------------------------------------------------------------------------
# A sentence a month
# ---------------------------------------------------------------------------

def _month_bounds(month: str) -> Tuple[str, str]:
    year, number = (int(part) for part in month.split("-"))
    start = datetime(year, number, 1, tzinfo=timezone.utc)
    end = datetime(year + (number == 12), number % 12 + 1, 1, tzinfo=timezone.utc)
    return start.isoformat(), end.isoformat()


def monthly_sentence(conn, month: str) -> Dict[str, Any]:
    """Template A, B or C for one month, as the report words them."""
    start, end = _month_bounds(month)
    name = datetime.fromisoformat(start).strftime("%B %Y")
    posts = [dict(r) for r in conn.execute(
        "SELECT activity_urn, published_at FROM own_posts WHERE published_at >= ? AND published_at < ?", (start, end))]
    answer = compare(conn, posts, _posts_from_cards(conn))
    if answer["verdict"] == "no_readings" or not posts:
        return {"month": month, "template": "C", "sentence": f"The studio has no readings for {name}'s posts yet."}
    if answer["posts_from_cards"] < FEWEST_FOR_A_MONTH:
        return {"month": month, "template": "B",
                "sentence": f"Fewer than {FEWEST_FOR_A_MONTH} posts came from a card in {name}, so nothing can be said "
                            "about their results yet."}
    if answer["verdict"] in ("too_few_posts", "not_measured"):
        return {"month": month, "template": "B",
                "sentence": f"{answer['posts_from_cards']} posts came from a card in {name}, {answer['n_with']} of them "
                            f"read at about two days old against {answer['n_without']} others; {results.MIN_PER_SIDE} a "
                            "side are needed before their results can be compared."}
    return {"month": month, "template": "A",
            "sentence": f"In {name}, {answer['n_with']} posts came from a card. At 48 hours they drew {answer['ratio']} "
                        f"times your usual reactions (median of {answer['median_with']:g} against the median of "
                        f"{answer['median_without']:g} across {answer['n_without']} other posts). "
                        f"{answer['n_with']} posts cannot show a difference smaller than about {answer['detectable']}x, "
                        "so this is a note, not a finding."}


def overview(months: int = 3) -> Dict[str, Any]:
    """Everything "Did these help?" shows, in one read."""
    today = record_daily.local_today()
    conn = get_db()
    try:
        recent = []
        cursor = date(today.year, today.month, 1)
        for _ in range(months):
            recent.append(monthly_sentence(conn, f"{cursor.year:04d}-{cursor.month:02d}"))
            cursor = (cursor - timedelta(days=1)).replace(day=1)
        notes = {r[0]: r[1] for r in conn.execute("SELECT month, text FROM record_notes")}
        return {"funnel": funnel(conn), "comparison": comparison(conn, today), "months": recent,
                "notes": notes, "this_month": f"{today.year:04d}-{today.month:02d}"}
    finally:
        conn.close()
