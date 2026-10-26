"""
What a post did, in one place.
==============================

Six modules answered "which of my posts worked" and no two agreed. Measured
on one creator's three years, 1,417 posts, in the same minute: the Posts
screen named two posts, the Composer's Evidence panel named three, the
Analytics table's first row a fourth and the prose beside that table a fifth,
and the pairs shared no post at all. Six posts were called the best one.

They disagreed because each module carried its own rule: its own denominator,
its own settled filter, its own tie break, its own minimum sample, its own
copy of the seven binary features, and its own copy of SETTLED_AFTER_HOURS,
_age_hours and the qualified cut (60 in four places, 75 and 80 in others).
The Analytics prose printed "116.25% engagement" as a measured fact, because
nothing checked that reactions cannot exceed impressions and the two figures
came from different capture sources.

So the rules live here, once, and every screen reads them:

  settled           how old a post must be before a low number means a weak
                    post rather than a young one, measured from the readings
                    the studio holds rather than assumed (settle_curve)
  figures           a post's figures, from one reading, with the source named
  engagement_rate   clamped, and the impossible case named rather than printed
  rank, best, worst one ranking key and one tie break
  tier, is_qualified  one cut at 80 and 60
  pair              reach and response as a pair, never one number
  difference        a comparison that can answer "no difference"

The precedent is fold.py, which exists because the mobile fold was computed in
four modules with two different limits. tests/test_results_is_one_number.py
fails if a second definition appears, the way test_fold_is_one_number.py does.

Strict Invariants:
- Zero em-dashes.
- Nothing here is estimated. Every number carries where it was read and how
  many posts it rests on; a figure the studio never read is None, never 0.
- This module imports no other studio module, so every module can import it.
"""

import json
import re
import sqlite3
import statistics
import threading
import time
import unicodedata
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple


def _rows(conn, sql: str, params: Sequence[Any] = ()):
    """Rows addressable by column name, whatever the connection's row factory."""
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    return cursor.execute(sql, params)

# ---------------------------------------------------------------------------
# When a post's numbers have settled
# ---------------------------------------------------------------------------
#
# A post's reactions and comments have mostly arrived by a week, so before
# that a low number may just be a young post and is not called weak. That was
# written as an assumption in two modules ("mostly arrived by a week"), with
# nothing to check it against. The studio holds 362,996 readings with the
# post's age at each one, so the curve can be measured instead: settle_curve()
# below reads it, and settled_after_hours() answers from it when the readings
# can say and from this constant when they cannot.

SETTLED_AFTER_HOURS = 7 * 24

# The ages the curve is reported at, and the share of a post's final figures
# that counts as settled.
SETTLE_BUCKETS = (1, 2, 3, 6, 12, 24, 36, 48, 72, 120, 168, 336)
SETTLED_SHARE = 0.90
# A reading counts for a bucket when it is within this much of that age, so
# that a gap in the readings does not invent a point on the curve.
BAND_TOLERANCE = 0.35
# Below this many posts in a bucket the curve is noise, and the assumption
# above is the honest answer.
MIN_POSTS_PER_BUCKET = 20

# A median over fewer posts than this is not a usual.
MIN_FOR_MEDIAN = 3

# Both sides of a comparison need this many posts before it is published. It
# was 3 in Patterns and 8 in the Evidence panel, so Patterns printed a finding
# the panel beside it suppressed on the same posts. One number, the higher
# one: a difference over fewer posts than this is a lead to try, not a finding.
MIN_PER_SIDE = 8

# A ratio inside this band is no difference the creator's history can
# separate. It was 1.25/0.8 in the contrast engine and 1.15/0.85 in the
# evidence brief, so the same split was notable on one screen and not on the
# other.
NOTABLE_HIGH = 1.25
NOTABLE_LOW = 0.8

# Two sides whose typical posts are further apart than this come from
# different periods, and the difference between them may be about when rather
# than how.
DIFFERENT_PERIOD_DAYS = 270

# A period is compared with the one before it only when each has at least this
# share of its days captured. The sums were compared whatever was captured:
# two weeks after install the previous 30 days held 4 captured days, and a
# flat 1,000 impressions a day was reported as +650%.
MIN_CAPTURED_SHARE_TO_COMPARE = 0.8

# ---------------------------------------------------------------------------
# The tiers
# ---------------------------------------------------------------------------
#
# One cut. The same person used to be qualified on one screen and not on
# another: 60 was written out in post_summary, crm and twice in
# evidence_briefing, and the top tier was 80 in two places and 75 in another.

VIP_SCORE = 80.0
QUALIFIED_SCORE = 60.0
NURTURE_SCORE = 30.0

# Lead statuses that mean the creator went on to talk to the person. Someone
# the creator is talking to is qualified whatever a keyword guess about their
# job title says.
CONVERSATION_STATUSES = ("ENGAGED", "CONVERTED")
# The same thing in the Leads screen's own vocabulary, which is a separate
# column (leads.status) with separate values.
CONVERSATION_LABELS = ("connected", "meeting")


def tier(score) -> str:
    """The tier a score falls in: TIER_1_VIP, QUALIFIED, NURTURE or DISQUALIFIED."""
    score = float(score or 0.0)
    if score >= VIP_SCORE:
        return "TIER_1_VIP"
    if score >= QUALIFIED_SCORE:
        return "QUALIFIED"
    if score >= NURTURE_SCORE:
        return "NURTURE"
    return "DISQUALIFIED"


def is_qualified(score, lead_status: Optional[str] = None, status: Optional[str] = None) -> bool:
    """
    Whether a captured person counts as qualified, by their score or by the
    stage the creator put them in.

    The score arm and the stage arm were two separate rules: post_summary
    counted only scores, the topic attribution counted scores or stages, so
    the same person was qualified on Patterns and not on Posts.
    """
    if float(score or 0.0) >= QUALIFIED_SCORE:
        return True
    if (lead_status or "").upper() in CONVERSATION_STATUSES:
        return True
    label = (status or "").lower()
    return any(word in label for word in CONVERSATION_LABELS)


# ---------------------------------------------------------------------------
# Ages
# ---------------------------------------------------------------------------

def age_hours(published_at: Optional[str]) -> Optional[float]:
    """
    How old a post is now, in hours, or None when it has no publication time.

    One implementation. There were two, and only one of them coped with a
    timestamp stored without a zone, so the same post was 40 hours old on one
    screen and raised TypeError on another.
    """
    if not published_at:
        return None
    try:
        when = datetime.fromisoformat(published_at)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when).total_seconds() / 3600.0


def timestamp(published_at: Optional[str]) -> Optional[float]:
    """A post's publication time as a POSIX timestamp, for comparing periods."""
    if not published_at:
        return None
    try:
        when = datetime.fromisoformat(published_at)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.timestamp()


def is_settled(published_at: Optional[str], settled_after: Optional[float] = None) -> bool:
    """Whether a post is old enough for its figures to be judged."""
    age = age_hours(published_at)
    return age is not None and age >= (SETTLED_AFTER_HOURS if settled_after is None else settled_after)


# ---------------------------------------------------------------------------
# A post's figures, from one reading
# ---------------------------------------------------------------------------
#
# The same post read 19,943 impressions on Today and 50,118 on Posts and
# Analytics in the same minute, because Today showed a reading and the other
# two showed the own_posts snapshot. The snapshot is not one reading either:
# the activity page writes its reactions and comments while the post's own
# analytics page overwrites its impressions (onboarding.py), so a rate built
# from it divides one page's reactions by another page's impressions. That is
# how "116.25% engagement" reached the screen as a measured fact.
#
# So a post's figures are one reading: the most recent one the studio holds.
# Where two sources were read in the same hour the post's own analytics page
# wins, because it is the only one carrying members reached, saves and sends.
# A post with no reading at all falls back to the snapshot, which is what a
# fresh install and an archive import have, and the source says so.

FIGURE_FIELDS = ("impressions", "reactions", "comments", "reposts")
SOURCE_RANK = {"post_analytics": "2", "activity_page": "1"}
SNAPSHOT = "snapshot"

# The newest reading of each post. SQLite takes the other columns from the row
# that matched the MAX, which is what makes this one indexed pass rather than
# a correlated subquery per post (measured: 62 ms for 1,417 posts over 362,996
# readings, against 2,349 ms for the subquery shape).
_NEWEST_READING = f"""
    SELECT activity_urn AS urn, source, observed_at, age_hours, precision,
           {', '.join(FIGURE_FIELDS)},
           MAX(observed_at || CASE source WHEN 'post_analytics' THEN '2' ELSE '1' END) AS ordering
    FROM post_metric_observations
    {{where}}
    GROUP BY activity_urn
"""


def _in_clause(urns: Optional[Sequence[str]], column: str) -> Tuple[str, list]:
    if urns is None:
        return "", []
    return f"WHERE {column} IN (SELECT value FROM json_each(?))", [json.dumps(list(urns))]


def _from_summary(conn, urns: Optional[Sequence[str]]) -> Dict[str, Dict[str, Any]]:
    """
    The newest reading per post as the per-post summary already keeps it
    (post_summary.py), which is 1,417 rows rather than 362,996: 5 ms against
    64 ms, and every screen asks for this on every load. Only rows the
    summary's own triggers have not marked stale are taken.
    """
    where, params = _in_clause(urns, "post_urn")
    clause = (where + " AND" if where else "WHERE") + " latest_reading IS NOT NULL AND (stale & 2) = 0"
    out: Dict[str, Dict[str, Any]] = {}
    try:
        rows = _rows(conn, f"SELECT post_urn AS urn, latest_reading FROM post_engagement {clause}",
                     params).fetchall()
    except sqlite3.OperationalError:
        return out
    for row in rows:
        try:
            reading = json.loads(row["latest_reading"])
        except (TypeError, ValueError):
            continue
        if not reading.get("source"):
            # Written before the reading carried the page it came from, so it
            # cannot be named: the readings themselves answer for this post.
            continue
        out[row["urn"]] = {
            **{field: reading.get(field) for field in FIGURE_FIELDS},
            "source": reading["source"],
            "read_at": reading.get("observed_at"),
            "read_at_age_hours": reading.get("age_hours"),
            # How precisely the reading was read (migration 28): 'exact',
            # 'rounded', or None for a reading that did not say.
            "precision": reading.get("precision"),
        }
    return out


def figures(conn, urns: Optional[Sequence[str]] = None) -> Dict[str, Dict[str, Any]]:
    """
    Each post's figures, keyed by activity URN: one reading, with its source
    and when it was read, for the posts named or for every post.

    Every figure in one answer comes from one reading, so a rate's numerator
    and its denominator cannot come from different pages.
    """
    out = _from_summary(conn, urns)
    # The posts the summary could not answer for, read from the readings
    # themselves: a post whose summary row a capture has just marked, and
    # every post on a database whose summary has not been built yet.
    if urns is None:
        try:
            asked = [row[0] for row in conn.execute(
                "SELECT activity_urn FROM own_posts WHERE activity_urn NOT IN "
                "(SELECT post_urn FROM post_engagement WHERE latest_reading IS NOT NULL AND (stale & 2) = 0)")]
        except sqlite3.OperationalError:
            # No summary table on this database: every post is read from the
            # readings, and the unfiltered pass over them is the cheap shape.
            asked = None
    else:
        asked = [urn for urn in urns if urn not in out]
    if asked is None or asked:
        where, params = _in_clause(asked, "activity_urn")
        try:
            rows = _rows(conn, _NEWEST_READING.format(where=where), params).fetchall()
        except sqlite3.OperationalError:
            # No readings table yet: the snapshot below is the whole answer.
            rows = []
        for row in rows:
            if row["urn"] is None:
                continue
            out[row["urn"]] = {
                **{field: row[field] for field in FIGURE_FIELDS},
                "source": row["source"],
                "read_at": row["observed_at"],
                "read_at_age_hours": row["age_hours"],
                "precision": row["precision"],
            }
    where, params = _in_clause(urns, "activity_urn")
    for row in _rows(
            conn, f"SELECT activity_urn AS urn, {', '.join(FIGURE_FIELDS)}, last_seen_at, published_at "
            f"FROM own_posts {where}", params):
        held = out.get(row["urn"])
        if held is not None and any(held[field] is not None for field in FIGURE_FIELDS):
            continue
        # A post nobody has read a reading of: the snapshot is all there is,
        # and a post imported from the archive has no figures at all.
        out[row["urn"]] = {
            **{field: row[field] for field in FIGURE_FIELDS},
            "source": SNAPSHOT,
            "read_at": row["last_seen_at"],
            "read_at_age_hours": None,
            "precision": None,
        }
    return out


def engagement_rate(figure: Optional[Dict[str, Any]]) -> Tuple[Optional[float], Optional[str]]:
    """
    (reactions + comments + reposts) / impressions as a percentage, and the
    reason there is no rate when there is none.

    Returns (None, reason) rather than a number whenever the studio cannot
    stand behind one. Measured on three years: one post of 1,417 held 877
    reactions against 837 impressions, and the screen printed "116.25%
    engagement" beside a table whose every row read under 1.6%.
    """
    if not figure:
        return None, "not_read"
    impressions, reactions = figure.get("impressions"), figure.get("reactions")
    if impressions is None or reactions is None:
        return None, "not_read"
    if impressions <= 0:
        return None, "no_impressions_read"
    engagements = reactions + (figure.get("comments") or 0) + (figure.get("reposts") or 0)
    if engagements > impressions:
        # More engagements than impressions cannot happen on one reading of
        # one post. It means the two figures were read from different pages
        # at different moments, so neither the rate nor a clamped 100% is a
        # measurement, and the screen says that instead of printing one.
        return None, "more_engagements_than_impressions"
    return round(engagements * 100.0 / impressions, 2), None


def rate_reason_sentence(reason: Optional[str]) -> Optional[str]:
    """What a screen says in place of a rate it cannot show."""
    return {
        "not_read": "not read yet",
        "no_impressions_read": "no impressions read for this post",
        "more_engagements_than_impressions": (
            "more engagements than impressions were read for this post, so the two figures came from "
            "different readings and no rate can be measured from them"),
    }.get(reason or "")


# ---------------------------------------------------------------------------
# How precisely a figure was read
# ---------------------------------------------------------------------------
#
# LinkedIn abbreviates: 1.2K is anything from 1,150 to 1,249. The analytics
# page's rows have said 'exact' or 'rounded' since migration 5 and the post
# readings since migration 28. The width of that uncertainty was computed in
# the analytics router alone, so the post side could not say "about"; it
# lives here now and the router reads it.

PRECISION_EXACT = "exact"
PRECISION_ROUNDED = "rounded"


def rounding_half_width(value, precision) -> float:
    """
    How far a stored figure can be from the true one, given how LinkedIn wrote it.

    A row marked 'rounded' holds at least one figure LinkedIn abbreviated,
    such as 1.2K stored as 1200, without saying which. LinkedIn writes compact
    numbers the way the browser's compact number format does: one decimal
    below 10K (1.2K, and 2K for 2.0K), whole thousands up to 999K (12K), one
    decimal below 10M (1.2M), whole millions above. So the step a figure was
    rounded to follows from its size: 100 below 10,000, 1,000 below a
    million, 100,000 below 10 million, 1,000,000 above, and the figure is
    half a step either way. A value that is not a multiple of its step
    cannot be one LinkedIn abbreviated, so it was written out in full and is
    exact. (This replaced reading the last non-zero digit, which gave a bare
    20K a margin of 5,000.) An unknown precision (None) claims nothing.
    """
    if precision != PRECISION_ROUNDED or value is None or value < 1000:
        return 0.0
    step = 100 if value < 10_000 else 1_000 if value < 1_000_000 else 100_000 if value < 10_000_000 else 1_000_000
    return step / 2.0 if value % step == 0 else 0.0


def approximate_fields(figure: Optional[Dict[str, Any]], fields: Sequence[str] = FIGURE_FIELDS) -> List[str]:
    """
    Which of a reading's figures LinkedIn rounded, by name, so a screen can
    say "about" beside those and nothing beside the rest.
    """
    if not figure:
        return []
    return [field for field in fields
            if rounding_half_width(figure.get(field), figure.get("precision")) > 0]


def growth(earlier: Optional[Dict[str, Any]], later: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    The change between two readings of one figure, and whether the readings
    can separate it from their own rounding.

    Each reading is {"value", "precision"}. The change is approximate when
    either reading was rounded, and within rounding when it is no larger
    than the two half widths together: 12K read twice is not "no growth",
    it is a change of up to a thousand that the readings cannot see.
    """
    if not earlier or not later or earlier.get("value") is None or later.get("value") is None:
        return {"change": None, "approximate": False, "within_rounding": False, "slack": 0.0}
    slack = (rounding_half_width(earlier["value"], earlier.get("precision"))
             + rounding_half_width(later["value"], later.get("precision")))
    change = later["value"] - earlier["value"]
    return {"change": change, "approximate": slack > 0, "within_rounding": slack > 0 and abs(change) <= slack,
            "slack": slack}


# ---------------------------------------------------------------------------
# Best and worst
# ---------------------------------------------------------------------------
#
# One ranking key: how a post's reactions compare with the creator's own
# median, over settled posts only, highest first, ties broken by the same
# metric the median is of and then by the post's URN so the answer is the same
# on every screen and in every order the rows arrive in. The Evidence panel
# ranked raw reactions with no settled filter, so a three hour old post could
# be a top exemplar; Analytics ranked by impressions in its table and by
# engagement rate in its prose.

RANKED_METRIC = "reactions"
COMPARED_METRICS = ("reactions", "comments", "impressions")


def median_of(values: Iterable[Optional[float]]) -> Tuple[Optional[float], int]:
    """(median, how many figures it rests on), and None below MIN_FOR_MEDIAN."""
    known = [v for v in values if v is not None]
    return (statistics.median(known), len(known)) if len(known) >= MIN_FOR_MEDIAN else (None, len(known))


def usual_of(posts: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """The creator's own median per metric, with how many figures each rests on."""
    posts = list(posts)
    out = {}
    for metric in COMPARED_METRICS:
        median, count = median_of(post.get(metric) for post in posts)
        out[metric] = {"median": median, "posts": count}
    return out


def against_usual(figure: Optional[Dict[str, Any]], usual: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
    """How one post's figures compare with the creator's own median, per metric."""
    ratios = {}
    if not figure:
        return ratios
    for metric, measure in usual.items():
        value, median = figure.get(metric), measure["median"]
        if median and value is not None:
            ratios[metric] = round(value / median, 2)
    return ratios


def rank(scored: Iterable[Tuple[str, Dict[str, float], Dict[str, Any]]]) -> List[str]:
    """
    The URNs of the posts given, best first.

    Each item is (urn, ratios, figure). A post with no ratio for the ranked
    metric is not ranked at all: it cannot be placed against the others.
    """
    ranked = [(urn, ratios, figure) for urn, ratios, figure in scored if RANKED_METRIC in ratios]
    ranked.sort(key=lambda item: (-item[1][RANKED_METRIC], -(item[2].get(RANKED_METRIC) or 0), item[0]))
    return [urn for urn, _ratios, _figure in ranked]


def ranking(conn, settled_after: Optional[float] = None,
            read: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Every settled post of the creator's, best first, with what the ranking
    rests on: the whole history, never one page of it.

    The Analytics screen picked its strongest post out of the fifty rows the
    page had fetched, so the answer changed with the page and the creator
    could not tell.
    """
    if settled_after is None:
        settled_after = settled_after_hours(conn)["hours"]
    posts = [dict(row) for row in _rows(
        conn, "SELECT activity_urn, published_at FROM own_posts WHERE published_at IS NOT NULL")]
    read = figures(conn) if read is None else read
    settled = [p for p in posts if is_settled(p["published_at"], settled_after)]
    usual = usual_of(read.get(p["activity_urn"]) or {} for p in settled)
    scored = [(p["activity_urn"], against_usual(read.get(p["activity_urn"]), usual),
               read.get(p["activity_urn"]) or {}) for p in settled]
    order = rank(scored)
    sources: Dict[str, int] = {}
    for urn in order:
        source = (read.get(urn) or {}).get("source") or SNAPSHOT
        sources[source] = sources.get(source, 0) + 1
    return {
        "order": order,
        "usual": usual,
        # The figures this ranking was made from, for a caller that wants the
        # named posts' numbers without reading them again.
        "figures": read,
        "posts": len(posts),
        "settled_posts": len(settled),
        "ranked_posts": len(order),
        "not_ranked": len(settled) - len(order),
        "settled_after_hours": settled_after,
        "metric": RANKED_METRIC,
        # Which pages the ranked figures were read from. One source is one
        # scale; where a creator's posts were read from both, the screen can
        # say so rather than let the counts look alike.
        "sources": sources,
    }


def best(conn, limit: int = 2, settled_after: Optional[float] = None,
         read: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    The posts that did best and worst against the creator's own median, from
    the whole history, with each named post's figures beside it.

    The figures travel with the answer because the screen that asks is
    showing one page of a long table, and the post that worked best is
    usually not on it.
    """
    answer = ranking(conn, settled_after, read=read)
    order = answer.pop("order")
    answer["best"] = order[:limit]
    answer["worst"] = list(reversed(order[-limit:])) if len(order) > limit else []
    named = {}
    for urn in answer["best"] + answer["worst"]:
        figure = answer["figures"].get(urn) or {}
        named[urn] = {
            **{field: figure.get(field) for field in FIGURE_FIELDS},
            "source": figure.get("source"),
            "against_usual": against_usual(figure, answer["usual"]),
        }
    answer["named"] = named
    # The whole order and every post's figures are the ranking's working, not
    # a screen's: the order alone is 56 KB of URNs on three years, and this
    # answer is sent with every page of the Analytics table.
    answer.pop("figures")
    return answer


# ---------------------------------------------------------------------------
# Reach and response, as a pair
# ---------------------------------------------------------------------------
#
# A post of this creator's sat at p5 for impressions and p86 for reactions at
# the same moment: almost nobody was shown it, and nearly everyone who was
# reacted. One number calls that a hit or a flop and both readings are wrong,
# so the studio shows the two together or not at all.
#
# A young post is read against the creator's own posts at the same age,
# because a post has only about half of its final reactions at 24 hours.

PAIR_BANDS = (3, 6, 12, 24, 48, 72)
# A post past its settle age is compared with every settled post's final
# figures instead of with an age band, so that a pair can be read for a post
# of any age rather than only for this week's.
FINAL_BAND = 0

_NEAREST_READING = """
SELECT urn, source, band, reactions, impressions, MIN(ABS(age_hours - band)) AS nearest
FROM (
    SELECT activity_urn AS urn, source, reactions, impressions, age_hours,
           CASE {case} END AS band
    FROM post_metric_observations
    WHERE age_hours IS NOT NULL AND age_hours <= {ceiling}
)
WHERE age_hours BETWEEN band * ? AND band * ?
GROUP BY urn, source, band
"""


def _band_sql(bands: Sequence[int]) -> str:
    """
    Each reading placed in the one age band it is nearest to, and the reading
    nearest each band kept, per post and per source.

    SQLite takes the other columns from the row that matched the MIN, which is
    what makes this one scan. It was a join against a list of bands, which
    scanned the readings once per band: 320 ms against 60 ms on 362,996
    readings, paid by whichever screen opened first.
    """
    bands = sorted(int(age) for age in bands)
    cuts = [f"WHEN age_hours < {(low + high) / 2.0:g} THEN {low:d}"
            for low, high in zip(bands, bands[1:])]
    cuts.append(f"ELSE {bands[-1]:d}")
    return _NEAREST_READING.format(case=" ".join(cuts),
                                   ceiling=f"{bands[-1] * (1 + BAND_TOLERANCE):g}")


def _percentile(sorted_values: List[int], value: int) -> int:
    below = sum(1 for other in sorted_values if other < value)
    return round(100.0 * below / len(sorted_values))


def _empty_bands() -> Dict[Tuple[str, int], Dict[str, List[int]]]:
    return {}


def age_bands(conn) -> Dict[Tuple[str, int], Dict[str, List[int]]]:
    """
    Per source and per age in PAIR_BANDS, every post's impressions and
    reactions as they read at about that age, sorted, so a new post can be
    placed among them.

    Kept per source because the activity feed's card and the post's own
    analytics page count different things: on this creator's three years the
    analytics page read 1.99x the reactions of the feed card for the same
    posts. A post is placed only among posts read the same way, and the answer
    says how many those were. Cached for the day: 160 ms on 1,417 posts.
    """
    return _cached(conn, "bands", _build_bands, _empty_bands())


def _build_bands(conn) -> Dict[Tuple[str, int], Dict[str, List[int]]]:
    bands: Dict[Tuple[str, int], Dict[str, List[int]]] = {}

    def band_of(source: str, age: int) -> Dict[str, List[int]]:
        return bands.setdefault((source, age), {"impressions": [], "reactions": []})

    for row in _rows(conn, _band_sql(PAIR_BANDS), (1 - BAND_TOLERANCE, 1 + BAND_TOLERANCE)):
        band = band_of(row["source"], row["band"])
        for metric in ("impressions", "reactions"):
            if row[metric] is not None:
                band[metric].append(row[metric])
    # The final band: every settled post's own figures, so a post past its
    # settle age is placed among the creator's finished posts rather than
    # against nothing.
    settled_after = settled_after_hours(conn)["hours"]
    read = figures(conn)
    for row in _rows(conn, "SELECT activity_urn AS urn, published_at FROM own_posts"):
        if not is_settled(row["published_at"], settled_after):
            continue
        figure = read.get(row["urn"]) or {}
        if not figure.get("source"):
            continue
        band = band_of(figure["source"], FINAL_BAND)
        for metric in ("impressions", "reactions"):
            if figure.get(metric) is not None:
                band[metric].append(figure[metric])
    for band in bands.values():
        for metric in band:
            band[metric].sort()
    return bands


def pair(conn, urns: Sequence[str], read: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Where each post sits among the creator's own posts at the same age, for
    reach and for response, as two percentiles that are read together.

    None for a post the studio has no reading of at a comparable age, which is
    said on screen rather than filled in.
    """
    read = figures(conn, urns) if read is None else read
    bands = age_bands(conn)
    settled_after = settled_after_hours(conn)["hours"]
    out: Dict[str, Any] = {}
    for urn in urns:
        figure = read.get(urn)
        age = (figure or {}).get("read_at_age_hours")
        if not figure or age is None or figure["impressions"] is None or figure["reactions"] is None:
            out[urn] = None
            continue
        band = min(PAIR_BANDS, key=lambda candidate: abs(candidate - age))
        if not (band * (1 - BAND_TOLERANCE) <= age <= band * (1 + BAND_TOLERANCE)):
            band = FINAL_BAND if age >= settled_after else None
        if band is None:
            out[urn] = None
            continue
        values = bands.get((figure["source"], band))
        if not values or len(values["impressions"]) < MIN_FOR_MEDIAN or len(values["reactions"]) < MIN_FOR_MEDIAN:
            out[urn] = None
            continue
        reach = _percentile(values["impressions"], figure["impressions"])
        response = _percentile(values["reactions"], figure["reactions"])
        out[urn] = {
            "band": "final" if band == FINAL_BAND else f"{band}h",
            "band_hours": None if band == FINAL_BAND else band,
            "posts_compared": min(len(values["impressions"]), len(values["reactions"])),
            "read_at_age_hours": round(age, 1),
            "source": figure["source"],
            "reach": {"impressions": figure["impressions"], "percentile": reach},
            "response": {"reactions": figure["reactions"], "percentile": response},
            # The two words that make the pair legible at a glance. They
            # describe the two percentiles and claim nothing beyond them.
            "shape": _shape(reach, response),
        }
    return out


def _shape(reach: int, response: int) -> str:
    if reach >= 50 and response >= 50:
        return "wide and loved"
    if reach >= 50:
        return "wide, thin response"
    if response >= 50:
        return "narrow, strong response"
    return "narrow and quiet"


# ---------------------------------------------------------------------------
# The settle curve, measured
# ---------------------------------------------------------------------------

def settle_curve(conn) -> Dict[str, Any]:
    """
    What share of its final figures a post of this creator's has reached by
    each age, measured from their own readings.

    The denominator is each post's own highest reading in its first fourteen
    days, from the same page the point was read on, and each point is the
    reading nearest that age. A share is scale free, so the two sources are
    counted together here even though their figures are not comparable.
    Cached for the day: 230 ms on 362,996 readings.
    """
    return _cached(conn, "curve", _build_curve, {"points": [], "measured_hours": None, "posts": 0})


def _build_curve(conn) -> Dict[str, Any]:
    rows = _rows(conn, f"""
        WITH nearest AS ({_band_sql(SETTLE_BUCKETS)}),
        peak AS (
            SELECT activity_urn AS urn, source, MAX(reactions) AS reactions, MAX(impressions) AS impressions
            FROM post_metric_observations WHERE age_hours <= ?
            GROUP BY activity_urn, source
        )
        SELECT n.band AS band, COUNT(DISTINCT n.urn) AS posts,
               AVG(CAST(n.reactions AS REAL) / p.reactions) AS reactions_share,
               AVG(CAST(n.impressions AS REAL) / p.impressions) AS impressions_share
        FROM nearest n JOIN peak p ON p.urn = n.urn AND p.source = n.source
        WHERE p.reactions > 0 AND p.impressions > 0 AND n.reactions IS NOT NULL AND n.impressions IS NOT NULL
        GROUP BY n.band ORDER BY n.band
    """, (1 - BAND_TOLERANCE, 1 + BAND_TOLERANCE, max(SETTLE_BUCKETS))).fetchall()
    points = [{"age_hours": row["band"], "posts": row["posts"],
               "reactions_share": round(row["reactions_share"], 3),
               "impressions_share": round(row["impressions_share"], 3)} for row in rows]
    measured = None
    for point in points:
        if point["posts"] >= MIN_POSTS_PER_BUCKET and point["reactions_share"] >= SETTLED_SHARE:
            measured = point["age_hours"]
            break
    return {"points": points, "measured_hours": measured,
            "posts": max((p["posts"] for p in points), default=0)}


def settled_after_hours(conn) -> Dict[str, Any]:
    """
    How old a post of this creator's has to be before its figures are judged,
    measured where the readings can say so and assumed where they cannot.

    The answer carries which it is, so a screen can tell the creator that five
    days is their own measured number rather than the studio's guess.
    """
    curve = settle_curve(conn)
    if curve["measured_hours"]:
        return {"hours": float(curve["measured_hours"]), "measured": True,
                "posts": curve["posts"], "share": SETTLED_SHARE}
    return {"hours": float(SETTLED_AFTER_HOURS), "measured": False, "posts": curve["posts"],
            "share": SETTLED_SHARE}


# ---------------------------------------------------------------------------
# Saying "no difference"
# ---------------------------------------------------------------------------
#
# Measured on this creator: the effect of a topic on how senior the people it
# brings are is 0.26 percentage points between topics against 27 points
# within one topic, and whether someone first liked, commented or reposted
# moves the share who qualify by 0.13 points. A screen that can only rank will
# rank noise, so the engine answers "no difference" and the screen prints it.

def difference(ratio: Optional[float], n_with: int, n_without: int) -> Dict[str, Any]:
    """
    What a two-sided comparison is allowed to say: "more", "fewer", "none", or
    "too few posts", with the counts it rests on.
    """
    if n_with < MIN_PER_SIDE or n_without < MIN_PER_SIDE:
        return {"verdict": "too_few_posts", "notable": False, "n_with": n_with, "n_without": n_without,
                "min_per_side": MIN_PER_SIDE}
    if ratio is None:
        return {"verdict": "not_measured", "notable": False, "n_with": n_with, "n_without": n_without,
                "min_per_side": MIN_PER_SIDE}
    if ratio >= NOTABLE_HIGH:
        verdict = "more"
    elif ratio <= NOTABLE_LOW:
        verdict = "fewer"
    else:
        verdict = "none"
    return {"verdict": verdict, "notable": verdict in ("more", "fewer"), "ratio": ratio,
            "n_with": n_with, "n_without": n_without, "min_per_side": MIN_PER_SIDE}


NO_DIFFERENCE = "no difference your own posts can separate"


def spread(groups: Dict[str, List[float]]) -> Dict[str, Any]:
    """
    Whether several groups differ at all, or whether the difference between
    them is smaller than the difference inside one of them.

    Three or more sides, where `difference` takes two. The verdict is "none"
    whenever the groups are closer together than their own members are, which
    is what a league table hides.
    """
    usable = {name: values for name, values in groups.items() if len(values) >= MIN_FOR_MEDIAN}
    if len(usable) < 2:
        return {"verdict": "too_few_groups", "groups": len(usable), "min_per_group": MIN_FOR_MEDIAN}
    medians = {name: statistics.median(values) for name, values in usable.items()}
    between = max(medians.values()) - min(medians.values())
    within = max(max(values) - min(values) for values in usable.values())
    return {
        "verdict": "none" if between <= within else "differs",
        "between": round(between, 4),
        "within": round(within, 4),
        "groups": len(usable),
        "medians": {name: round(value, 4) for name, value in medians.items()},
        "min_per_group": MIN_FOR_MEDIAN,
    }


def different_periods(with_dates: List[float], without_dates: List[float]) -> Dict[str, Any]:
    """
    Whether two sides of a comparison come from different periods, and which.

    Measured on the first live install: hashtags went with 2.7x the reactions,
    and the hashtag posts were mostly from two years earlier, when the account
    and its audience were different.
    """
    if not with_dates or not without_dates:
        return {"different_period": False}
    typical_with, typical_without = statistics.median(with_dates), statistics.median(without_dates)
    return {
        "different_period": abs(typical_with - typical_without) / 86400.0 > DIFFERENT_PERIOD_DAYS,
        "typical_year_with": datetime.fromtimestamp(typical_with).year,
        "typical_year_without": datetime.fromtimestamp(typical_without).year,
    }


def window_complete(days_captured: int, days_needed: int) -> bool:
    """
    Whether a period was captured well enough to compare with another.

    A percentage over a window that is only part captured is the most damaging
    number this product could print: on this creator's data, the current
    calendar week read as a 2 day stub against a 7 day median reported
    impressions down 63% in a week that was in fact above their median.
    Windows are trailing and whole, or there is no percentage.
    """
    return days_captured >= days_needed


# ---------------------------------------------------------------------------
# Whether a post is still moving, and its reach half-life
# ---------------------------------------------------------------------------
#
# Both are read from the readings a post already has, never from a model of
# how posts behave, and both are printed as readings with their count. What
# is usual at an age is the settle curve's answer, which abstains below
# MIN_POSTS_PER_BUCKET; a comparison between groups of posts' half-lives
# goes through difference and spread, so Patterns cannot say what the Posts
# screen would deny. A post's readings from the feed card and from its own
# analytics page count different things, so only the page of the newest
# reading is read.

# One reading cannot move.
MIN_READINGS_TO_MOVE = 2
# A half-life is interpolated between the two readings that bracket the
# halfway point, under a denominator read at or after the settled age.
MIN_READINGS_FOR_HALF_LIFE = 3
# The denominator is the first reading at or after this age, the settled
# rule's own constant, so "day-7" and "settled" are one number.
HALF_LIFE_AT_HOURS = SETTLED_AFTER_HOURS
MOVING_METRICS = ("impressions", "reactions", "comments", "reposts", "members_reached")
# The figures the settle curve measures a share of.
CURVE_METRICS = ("impressions", "reactions")


def readings_of(conn, urn: str, metric: str = "impressions", source: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    One post's readings of one figure from one page, oldest first: the page
    of the newest reading unless one is named, because the feed card and the
    post's own analytics page count different things.
    """
    if metric not in MOVING_METRICS:
        raise ValueError(f"not a figure the readings carry: {metric}")
    try:
        rows = _rows(conn, f"""
            SELECT observed_at, age_hours, source, precision, {metric} AS value
            FROM post_metric_observations
            WHERE activity_urn = ? AND {metric} IS NOT NULL AND age_hours IS NOT NULL
            ORDER BY observed_at, CASE source WHEN 'post_analytics' THEN 2 ELSE 1 END, id
        """, (urn,)).fetchall()
    except sqlite3.OperationalError:
        # No readings table yet.
        return []
    if not rows:
        return []
    page = source or rows[-1]["source"]
    return [dict(row) for row in rows if row["source"] == page]


def usual_at_age(conn, age_hours: float, metric: str = "impressions") -> Dict[str, Any]:
    """
    What is usual for this creator at an age: the share of a post's two-week
    figure their posts have reached by the nearest point of the settle
    curve, with how many posts that rests on. Abstains when no point is
    within the band of the age, and below MIN_POSTS_PER_BUCKET posts.
    """
    if metric not in CURVE_METRICS:
        raise ValueError(f"the settle curve does not measure {metric}")
    nearest = min(SETTLE_BUCKETS, key=lambda bucket: abs(bucket - age_hours))
    out = {"metric": metric, "age_hours": round(age_hours, 1), "bucket_hours": nearest,
           "min_posts": MIN_POSTS_PER_BUCKET}
    if abs(nearest - age_hours) > nearest * BAND_TOLERANCE:
        return {**out, "verdict": "no_bucket", "posts": 0,
                "sentence": f"no settle point is measured near {age_hours:.0f} hours old"}
    point = next((p for p in settle_curve(conn)["points"] if p["age_hours"] == nearest), None)
    posts = point["posts"] if point else 0
    if posts < MIN_POSTS_PER_BUCKET:
        return {**out, "verdict": "too_few_posts", "posts": posts,
                "sentence": (f"not enough posts read at about {nearest} hours old to say what is usual "
                             f"({posts} of {MIN_POSTS_PER_BUCKET})")}
    share = point[f"{metric}_share"]
    return {**out, "verdict": "measured", "posts": posts, "share": share,
            "sentence": (f"your posts usually have {share:.0%} of their two-week {metric} by {nearest} hours, "
                         f"measured on {posts} posts")}


def _reading_value(reading: Dict[str, Any]) -> Dict[str, Any]:
    return {"value": reading["value"], "precision": reading.get("precision")}


def _ago(read_at: Optional[str]) -> str:
    """When a reading was taken, from now, in the words a sentence uses."""
    hours = age_hours(read_at)
    if hours is None:
        return "at an unknown time"
    if hours < 1:
        return "less than an hour ago"
    if hours < 48:
        return f"{hours:.0f} hour{'s' if round(hours) != 1 else ''} ago"
    return f"{hours / 24:.0f} days ago"


def _rounded_among(readings: Iterable[Dict[str, Any]]) -> bool:
    return any(rounding_half_width(r["value"], r.get("precision")) > 0 for r in readings)


def movement(conn, urn: str, metric: str = "impressions") -> Dict[str, Any]:
    """
    Whether a post is still moving: the change between its last two readings
    of one figure, as readings with their count, and what is usual for this
    creator at that age.

    Abstains below MIN_READINGS_TO_MOVE readings. Says "about" when either
    reading was rounded, and says the readings cannot separate a change that
    is within their rounding rather than call it growth or stillness. The
    usual at this age is usual_at_age's, with its own abstention. Nothing
    here is a cause or a forecast.
    """
    readings = readings_of(conn, urn, metric)
    n = len(readings)
    out = {"metric": metric, "readings": n, "min_readings": MIN_READINGS_TO_MOVE,
           "source": readings[-1]["source"] if readings else None}
    if n < MIN_READINGS_TO_MOVE:
        sentence = (f"one reading of {metric} so far, at {readings[0]['age_hours']:.0f} hours old; "
                    f"a second reading says whether it is still moving" if n == 1
                    else f"no reading of {metric} yet")
        return {**out, "verdict": "too_few_readings", "sentence": sentence}
    earlier, later = readings[-2], readings[-1]
    change = growth(_reading_value(earlier), _reading_value(later))
    hours = round(later["age_hours"] - earlier["age_hours"], 1)
    delta = change["change"]
    # "Since the reading K hours ago", with the latest named too: the change
    # is known only up to the latest reading, which may itself be old.
    since = f"since the reading {_ago(earlier['observed_at'])}"
    count = f"over {n} readings, the latest {_ago(later['observed_at'])}"
    about = "about " if change["approximate"] else ""
    if change["within_rounding"]:
        verdict = "within_rounding"
        sentence = (f"a change of {delta:+,} {metric} {since}, which two rounded readings cannot separate "
                    f"from their rounding (up to {change['slack']:,.0f} either way), {count}")
    elif delta > 0:
        verdict = "moving"
        sentence = f"still moving: {about}{delta:+,} {metric} {since}, {count}"
    elif delta == 0:
        verdict = "unchanged"
        sentence = f"unchanged {since}, {count}"
    else:
        verdict = "fell"
        sentence = (f"fell by {about}{-delta:,} {metric} {since}, {count}; LinkedIn's figures are estimates "
                    f"and a reaction can be withdrawn")
    usual = usual_at_age(conn, later["age_hours"], metric) if metric in CURVE_METRICS else None
    return {
        **out, "verdict": verdict, "change": delta, "approximate": change["approximate"],
        "within_rounding": change["within_rounding"], "slack": change["slack"], "hours_between": hours,
        "earlier": {"value": earlier["value"], "age_hours": earlier["age_hours"], "read_at": earlier["observed_at"],
                    "precision": earlier.get("precision")},
        "latest": {"value": later["value"], "age_hours": later["age_hours"], "read_at": later["observed_at"],
                   "precision": later.get("precision")},
        "sentence": sentence, "usual": usual,
    }


def _half_life_from(readings: List[Dict[str, Any]], metric: str) -> Dict[str, Any]:
    n = len(readings)
    days = HALF_LIFE_AT_HOURS / 24
    out = {"metric": metric, "readings": n, "min_readings": MIN_READINGS_FOR_HALF_LIFE, "at_hours": HALF_LIFE_AT_HOURS}
    if n < MIN_READINGS_FOR_HALF_LIFE:
        return {**out, "verdict": "too_few_readings",
                "sentence": (f"{n} reading{'s' if n != 1 else ''} of {metric}; a half-life needs "
                             f"{MIN_READINGS_FOR_HALF_LIFE}, one of them at or after {days:.0f} days")}
    final = next((r for r in readings if r["age_hours"] >= HALF_LIFE_AT_HOURS), None)
    if final is None:
        latest = readings[-1]["age_hours"]
        return {**out, "verdict": "too_young", "latest_age_hours": latest,
                "sentence": (f"its latest reading is {latest:.0f} hours old; the half-life waits for a reading "
                             f"at or after {days:.0f} days, when the figure it is half of has arrived")}
    if not final["value"] or final["value"] <= 0:
        return {**out, "verdict": "not_measured",
                "sentence": (f"its {metric} read 0 at {final['age_hours']:.0f} hours old, "
                             f"so there is no half to reach")}
    target = final["value"] / 2.0
    base = {**out, "denominator": {"value": final["value"], "age_hours": final["age_hours"],
                                   "precision": final.get("precision")}}
    before = [r for r in readings if r["age_hours"] <= final["age_hours"]]
    first = before[0]
    # The denominator is named by the age it was read at, not called "day 7":
    # the first reading at or after 7 days may be a month old.
    whole = f"half of the {final['value']:,} {metric} it had at {final['age_hours']:.0f} hours old"
    if first["value"] >= target:
        approximate = _rounded_among((first, final))
        return {**base, "verdict": "before_first_reading", "hours": first["age_hours"], "approximate": approximate,
                "sentence": (f"under {first['age_hours']:.0f} hours to {whole}: its first reading already held "
                             f"{'about ' if approximate else ''}half, over {n} readings")}
    index = next(i for i, r in enumerate(before) if r["value"] >= target)
    prev, cur = before[index - 1], before[index]
    hours = prev["age_hours"] + (target - prev["value"]) / (cur["value"] - prev["value"]) * (
        cur["age_hours"] - prev["age_hours"])
    approximate = _rounded_among((prev, cur, final))
    return {**base, "verdict": "measured", "hours": round(hours, 1),
            "between_hours": [prev["age_hours"], cur["age_hours"]], "approximate": approximate,
            "sentence": (f"{'about ' if approximate else ''}{hours:.0f} hours to {whole}, interpolated "
                         f"between readings at {prev['age_hours']:.0f} and {cur['age_hours']:.0f} hours, "
                         f"over {n} readings")}


def half_life(conn, urn: str, metric: str = "impressions") -> Dict[str, Any]:
    """
    Hours until a post had half of its day-7 figure, interpolated between the
    two readings that bracket the halfway point.

    Needs MIN_READINGS_FOR_HALF_LIFE readings of one figure from one page,
    one of them at or after HALF_LIFE_AT_HOURS: a younger post's figure is
    not final, so the answer would move. Partial by the coverage note's
    class: the answer names the readings it was interpolated between, says
    "about" when any of them was rounded, and is an upper bound when the
    first reading already held half. LinkedIn's impressions are estimates.
    """
    return _half_life_from(readings_of(conn, urn, metric), metric)


def _build_half_lives(conn, metric: str) -> Dict[str, Dict[str, Any]]:
    if metric not in MOVING_METRICS:
        raise ValueError(f"not a figure the readings carry: {metric}")
    rows = _rows(conn, f"""
        SELECT activity_urn AS urn, observed_at, age_hours, source, precision, {metric} AS value
        FROM post_metric_observations WHERE {metric} IS NOT NULL AND age_hours IS NOT NULL
        ORDER BY activity_urn, observed_at, CASE source WHEN 'post_analytics' THEN 2 ELSE 1 END, id
    """).fetchall()
    by_post: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_post.setdefault(row["urn"], []).append(dict(row))
    out: Dict[str, Dict[str, Any]] = {}
    for urn, readings in by_post.items():
        page = readings[-1]["source"]
        answer = _half_life_from([r for r in readings if r["source"] == page], metric)
        # An upper bound is not a measurement, so it is not a point in a distribution.
        if answer["verdict"] == "measured":
            out[urn] = answer
    return out


def half_lives(conn, metric: str = "impressions") -> Dict[str, Dict[str, Any]]:
    """
    Every post's measured half-life, keyed by URN; a post whose readings
    cannot answer is absent. Cached per database as the curve and the bands
    are: one pass over the readings, measured at 3 years of one creator.
    """
    return _cached(conn, f"half_lives_{metric}", lambda c: _build_half_lives(c, metric), {})


def half_life_spread(conn, groups: Dict[str, Sequence[str]], metric: str = "impressions") -> Dict[str, Any]:
    """Whether groups of posts differ in half-life at all: results.spread over the measured ones."""
    lives = half_lives(conn, metric)
    return spread({name: [lives[u]["hours"] for u in urns if u in lives] for name, urns in groups.items()})


def half_life_difference(conn, with_urns: Sequence[str], without_urns: Sequence[str],
                         metric: str = "impressions") -> Dict[str, Any]:
    """What a two-sided half-life comparison may say: results.difference over the measured ones."""
    lives = half_lives(conn, metric)
    with_it = [lives[u]["hours"] for u in with_urns if u in lives]
    without = [lives[u]["hours"] for u in without_urns if u in lives]
    median_with = statistics.median(with_it) if with_it else None
    median_without = statistics.median(without) if without else None
    ratio = round(median_with / median_without, 2) if median_with is not None and median_without else None
    return {**difference(ratio, len(with_it), len(without)),
            "median_with": median_with, "median_without": median_without}


# ---------------------------------------------------------------------------
# The seven binary features
# ---------------------------------------------------------------------------
#
# Written out twice in full, with different labels and different thresholds,
# which is why the creator saw two wordings of the same test on two screens.

_ANNOUNCEMENT = re.compile(
    r"\b(excited|thrilled|happy to share|pleased to|proud to|congratulations|new position|starting a new)\b",
    re.IGNORECASE)


def opening_line(text: Optional[str]) -> str:
    """What shows before anything else: the first line, or the first sentence of a one-line post."""
    lines = [line.strip() for line in (text or "").split("\n") if line.strip()]
    if not lines:
        return ""
    first = lines[0]
    if len(lines) == 1:
        match = re.match(r"(.{1,200}?[.!?])(\s|$)", first)
        if match:
            first = match.group(1)
    return first


def opens_with_symbol(line: str) -> bool:
    return bool(line) and unicodedata.category(line[0]) == "So"


def has_bold_unicode(text: str) -> bool:
    return any(0x1D400 <= ord(ch) <= 0x1D7FF for ch in text)


BINARY_FEATURES: List[Tuple[str, str, Callable[[str, str], bool]]] = [
    ("short_opening", "An opening line of 60 characters or fewer",
     lambda text, opening: len(opening) <= 60),
    ("question_opening", "An opening line that asks a question",
     lambda text, opening: "?" in opening),
    ("symbol_opening", "An opening that starts with an emoji or symbol",
     lambda text, opening: opens_with_symbol(opening)),
    ("announcement", "An announcement (excited, thrilled, happy to share, new position)",
     lambda text, opening: bool(_ANNOUNCEMENT.search(opening))),
    ("bold_unicode", "Bold or styled Unicode letters",
     lambda text, opening: has_bold_unicode(text)),
    ("hashtags", "Hashtags",
     lambda text, opening: "#" in text),
    ("long_post", "More than 1,500 characters",
     lambda text, opening: len(text) > 1500),
]


# ---------------------------------------------------------------------------
# Caching the two roll-ups
# ---------------------------------------------------------------------------
#
# The curve and the bands are a day's work on a page load's budget, so they
# are kept per database until the readings change. The signature is what the
# readings are: a new reading changes it, and nothing else does.

_CACHE_LOCK = threading.Lock()
_cache: Dict[str, Dict[str, Any]] = {}
_RECHECK_SECONDS = 2.0
# What counts as the readings having changed enough to measure the curve and
# the bands again: a new hour of readings, or fifty more of them. Measured on
# three years, the curve is 200 ms and the bands 140 ms over 362,996 readings,
# and neither moves when one post is read once more. Without this a capture
# every few minutes would put that work on the next screen every time.
_ROLL_UP_STEP = 50


def _db_path(conn) -> str:
    try:
        for row in conn.execute("PRAGMA database_list"):
            if row[1] == "main":
                return row[2] or ":memory:"
    except Exception:
        pass
    return ":memory:"


def _cached(conn, name: str, build, fallback):
    path = _db_path(conn)
    now = time.monotonic()
    with _CACHE_LOCK:
        held = _cache.get(path, {}).get(name)
        if held and now - held["checked"] < _RECHECK_SECONDS:
            return held["value"]
    try:
        readings, newest = conn.execute(
            "SELECT COUNT(*), MAX(observed_at) FROM post_metric_observations").fetchone()
        signature = (readings // _ROLL_UP_STEP, (newest or "")[:13])
    except sqlite3.OperationalError:
        # No readings table: there is nothing to measure and nothing to cache.
        return fallback
    with _CACHE_LOCK:
        held = _cache.get(path, {}).get(name)
        if held and held["signature"] == signature:
            held["checked"] = now
            return held["value"]
    value = build(conn)
    with _CACHE_LOCK:
        _cache.setdefault(path, {})[name] = {"signature": signature, "checked": now, "value": value}
    return value


def forget_cache() -> None:
    """Drops the roll-ups, for a test or a restore that replaces the database."""
    with _CACHE_LOCK:
        _cache.clear()
