"""
The Contrast Engine: pairwise post feature contrasts (CP1).
===========================================================
Computes binary feature contrasts across the creator's settled posts.
Enforces the strict invariant: abstains from asserting any conclusion
whenever either arm has fewer than MIN_ARM_SAMPLE_SIZE posts.

Every rule it used to carry of its own now comes from results.py, which the
Patterns screen reads as well, so the two cannot disagree about the same
posts.

Strict Invariants:
- Zero em-dashes in any comments or strings.
- Abstain below results.MIN_PER_SIDE per arm with the n shown.
- Every comparison carries the sample sizes and a verdict that may be "none".
"""

import sqlite3
import statistics
from typing import Dict, Any, List, Optional, Callable, Tuple

try:
    from . import post_format, results
    from .database import get_db
except ImportError:
    import post_format
    import results
    from database import get_db

# The sample rule, the settled rule, the notable cut, the seven features and
# the period guard are results.py's: this engine and the Patterns screen were
# two copies of them, with different labels and different thresholds, so the
# same split was conclusive on one screen and nothing on the other.
MIN_ARM_SAMPLE_SIZE = results.MIN_PER_SIDE
DIFFERENT_PERIOD_DAYS = results.DIFFERENT_PERIOD_DAYS
BINARY_FEATURES: List[Tuple[str, str, Callable[[str, str], bool]]] = results.BINARY_FEATURES
different_periods = results.different_periods
opening_line = results.opening_line

# The format comparisons (cycle 4, track 5): one per format, the posts of
# that format against the posts of every other known format. A post whose
# format is unknown is on neither side, because counting it as "without"
# would be a guess that it is not that format, and the coverage beside the
# comparisons says how many posts that set aside. The sample rule, the
# notable cut and the period guard are the seven features' own.
FORMAT_FEATURES: List[Tuple[str, str, str]] = [
    (f"format_{name}", post_format.LABELS[name], name) for name in post_format.FORMATS]


def evaluate_contrast_for_posts(posts: List[Dict[str, Any]], feature_key: str) -> Dict[str, Any]:
    """
    Evaluates a single binary feature across a list of post dictionaries.
    Abstains if either side has n < MIN_ARM_SAMPLE_SIZE.
    """
    feature = next((f for f in BINARY_FEATURES if f[0] == feature_key), None)
    if not feature:
        return {
            "status": "unknown_feature",
            "key": feature_key,
            "min_required": MIN_ARM_SAMPLE_SIZE
        }

    key, label, test_func = feature

    with_it: List[float] = []
    without: List[float] = []
    with_dates: List[float] = []
    without_dates: List[float] = []

    for p in posts:
        text = p.get("text") or p.get("content") or ""
        opening = opening_line(text)
        rxn = p.get("reactions")
        if rxn is None:
            continue
        try:
            rxn_float = float(rxn)
        except (ValueError, TypeError):
            continue

        when = results.timestamp(p.get("published_at"))
        if test_func(text, opening):
            with_it.append(rxn_float)
            if when is not None:
                with_dates.append(when)
        else:
            without.append(rxn_float)
            if when is not None:
                without_dates.append(when)

    return _verdict(key, label, with_it, without, with_dates, without_dates)


def _verdict(key: str, label: str, with_it: List[float], without: List[float],
             with_dates: List[float], without_dates: List[float]) -> Dict[str, Any]:
    """
    What a split of posts into two arms may say: abstain below
    MIN_ARM_SAMPLE_SIZE per arm, flag two arms from different periods, and
    otherwise results.difference's verdict, which may be "none".
    """
    n_with = len(with_it)
    n_without = len(without)

    if n_with < MIN_ARM_SAMPLE_SIZE or n_without < MIN_ARM_SAMPLE_SIZE:
        return {
            "key": key,
            "label": label,
            "status": "not_enough_data",
            "reason": f"Requires at least {MIN_ARM_SAMPLE_SIZE} posts per arm (observed {n_with} with, {n_without} without).",
            "n_with": n_with,
            "n_without": n_without,
            "difference": results.difference(None, n_with, n_without),
            "min_required": MIN_ARM_SAMPLE_SIZE,
            "confidence": "insufficient_sample"
        }

    med_with = statistics.median(with_it)
    med_without = statistics.median(without)
    ratio = round(med_with / med_without, 2) if med_without > 0 else None
    verdict = results.difference(ratio, n_with, n_without)
    period = different_periods(with_dates, without_dates)

    if period["different_period"]:
        # Enough posts on each side, but from different years: not a finding.
        return {
            "key": key,
            "label": label,
            "status": "different_period",
            "n_with": n_with,
            "n_without": n_without,
            "median_with": med_with,
            "median_without": med_without,
            "ratio": ratio,
            "planted_or_significant": False,
            "difference": {**verdict, "verdict": "different_period", "notable": False},
            "min_required": MIN_ARM_SAMPLE_SIZE,
            **period,
        }

    return {
        "key": key,
        "label": label,
        "status": "conclusive",
        "n_with": n_with,
        "n_without": n_without,
        "median_with": med_with,
        "median_without": med_without,
        "ratio": ratio,
        # One cut, results.difference's, which the Patterns screen reads too:
        # this engine called a ratio notable at 1.25 while the brief beside it
        # used 1.15, so the same split was a finding on one screen and nothing
        # on the other. "none" is a first class answer.
        "planted_or_significant": verdict["notable"],
        "difference": verdict,
        "min_required": MIN_ARM_SAMPLE_SIZE
    }


def evaluate_format_contrast(posts: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
    """
    One format against every other known format, over posts that carry a
    "format" and "reactions". Posts of unknown format are set aside and
    counted (n_unknown); the verdict is _verdict's, the seven features' own.
    """
    feature = next((f for f in FORMAT_FEATURES if f[2] == name), None)
    if not feature:
        return {"status": "unknown_feature", "key": f"format_{name}", "min_required": MIN_ARM_SAMPLE_SIZE}
    key, label, _name = feature
    with_it: List[float] = []
    without: List[float] = []
    with_dates: List[float] = []
    without_dates: List[float] = []
    unknown = 0
    for p in posts:
        try:
            rxn = float(p.get("reactions"))
        except (TypeError, ValueError):
            continue
        if p.get("format") not in post_format.FORMATS:
            unknown += 1
            continue
        when = results.timestamp(p.get("published_at"))
        if p["format"] == name:
            with_it.append(rxn)
            if when is not None:
                with_dates.append(when)
        else:
            without.append(rxn)
            if when is not None:
                without_dates.append(when)
    return {**_verdict(key, label, with_it, without, with_dates, without_dates), "format": name,
            "n_unknown": unknown}


def compute_all_contrasts(read: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Computes all contrasts against settled posts in SQLite.
    Guarantees clean connection teardown in finally block.

    A caller that has already read the figures passes them in, so one request
    reads them once (the Evidence panel asks for a brief and these contrasts
    together).
    """
    conn = get_db()
    try:
        settle = results.settled_after_hours(conn)
        if read is None:
            read = results.figures(conn)
        rows = conn.execute(
            "SELECT activity_urn, text, published_at FROM own_posts WHERE text IS NOT NULL"
        ).fetchall()
        # The figures come from the one engine, so a contrast and the Posts
        # screen rest on the same reading of each post.
        posts = [dict(r, **{metric: (read.get(r["activity_urn"]) or {}).get(metric)
                            for metric in ("reactions", "comments", "impressions")}) for r in rows]
        # Every post for the format comparisons, captionless ones too: an
        # image or a document posted with no words is still that format,
        # where the seven features read the text and so skip it.
        try:
            format_rows = conn.execute("SELECT activity_urn, published_at, format FROM own_posts").fetchall()
        except sqlite3.OperationalError:
            format_rows = []
        format_posts = [dict(r, reactions=(read.get(r["activity_urn"]) or {}).get("reactions")) for r in format_rows]
    finally:
        conn.close()

    settled = [p for p in posts if results.is_settled(p.get("published_at"), settle["hours"])
               and p.get("reactions") is not None]

    contrasts = [evaluate_contrast_for_posts(settled, key) for key, _label, _test in BINARY_FEATURES]

    settled_formats = [p for p in format_posts if results.is_settled(p.get("published_at"), settle["hours"])
                       and p.get("reactions") is not None]
    known = [p for p in settled_formats if p.get("format") in post_format.FORMATS]
    by_format: Dict[str, int] = {}
    for p in known:
        by_format[p["format"]] = by_format.get(p["format"], 0) + 1

    return {
        "status": "success",
        "settled_posts_count": len(settled),
        "settled_after": settle,
        "min_arm_size": MIN_ARM_SAMPLE_SIZE,
        "contrasts": contrasts,
        "format_contrasts": [evaluate_format_contrast(settled_formats, name) for name in post_format.FORMATS],
        # How many settled posts the format comparisons could use: a post
        # of unknown format is on neither side of any of them.
        "format_coverage": {"settled_posts": len(settled_formats), "format_known": len(known),
                            "format_unknown": len(settled_formats) - len(known),
                            "by_format": {name: by_format[name] for name in post_format.FORMATS if name in by_format}},
    }
