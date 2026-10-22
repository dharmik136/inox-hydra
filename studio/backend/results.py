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
    SELECT activity_urn AS urn, source, observed_at, age_hours,
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
