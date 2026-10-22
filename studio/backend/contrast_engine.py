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

import statistics
from typing import Dict, Any, List, Optional, Callable, Tuple

try:
    from . import results
    from .database import get_db
except ImportError:
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
    finally:
        conn.close()

    settled = [p for p in posts if results.is_settled(p.get("published_at"), settle["hours"])
               and p.get("reactions") is not None]

    contrasts = [evaluate_contrast_for_posts(settled, key) for key, _label, _test in BINARY_FEATURES]

    return {
        "status": "success",
        "settled_posts_count": len(settled),
        "settled_after": settle,
        "min_arm_size": MIN_ARM_SAMPLE_SIZE,
        "contrasts": contrasts
    }
