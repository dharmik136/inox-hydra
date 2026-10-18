"""
The Contrast Engine: pairwise post feature contrasts (CP1).
===========================================================
Computes binary feature contrasts across the creator's settled posts.
Enforces the strict invariant: abstains from asserting any conclusion
whenever either arm has fewer than MIN_ARM_SAMPLE_SIZE (8) posts.

Strict Invariants:
- Zero em-dashes in any comments or strings.
- Abstain below n=8 per arm with the n shown.
- Every comparison carries the sample sizes.
"""

import re
import unicodedata
import statistics
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Callable

try:
    from .database import get_db
except ImportError:
    from database import get_db

MIN_ARM_SAMPLE_SIZE = 8
SETTLED_AFTER_HOURS = 7 * 24

_ANNOUNCEMENT = re.compile(
    r"\b(excited|thrilled|happy to share|pleased to|proud to|congratulations|new position|starting a new)\b",
    re.IGNORECASE
)


def _age_hours(published_at: Optional[str]) -> Optional[float]:
    if not published_at:
        return None
    try:
        dt = datetime.fromisoformat(published_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    except Exception:
        return None


def opening_line(text: Optional[str]) -> str:
    lines = [line.strip() for line in (text or "").split("\n") if line.strip()]
    if not lines:
        return ""
    first = lines[0]
    if len(lines) == 1:
        match = re.match(r"(.{1,200}?[.!?])(\s|$)", first)
        if match:
            first = match.group(1)
    return first


def _opens_with_symbol(line: str) -> bool:
    return bool(line) and unicodedata.category(line[0]) == "So"


def _has_bold_unicode(text: str) -> bool:
    return any(0x1D400 <= ord(ch) <= 0x1D7FF for ch in text)


BINARY_FEATURES: List[Tuple[str, str, Callable[[str, str], bool]]] = [
    ("short_opening", "Opening line <= 60 characters",
     lambda text, opening: len(opening) <= 60),
    ("question_opening", "Opening line asks a question",
     lambda text, opening: "?" in opening),
    ("symbol_opening", "Opening starts with an emoji or symbol",
     lambda text, opening: _opens_with_symbol(opening)),
    ("announcement", "Announcement wording (excited, thrilled, proud to)",
     lambda text, opening: bool(_ANNOUNCEMENT.search(opening))),
    ("bold_unicode", "Bold or styled Unicode letters",
     lambda text, opening: _has_bold_unicode(text)),
    ("hashtags", "Contains hashtags",
     lambda text, opening: "#" in text),
    ("long_post", "More than 1,500 characters",
     lambda text, opening: len(text) > 1500),
]


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

        if test_func(text, opening):
            with_it.append(rxn_float)
        else:
            without.append(rxn_float)

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
            "min_required": MIN_ARM_SAMPLE_SIZE,
            "confidence": "insufficient_sample"
        }

    med_with = statistics.median(with_it)
    med_without = statistics.median(without)
    ratio = round(med_with / med_without, 2) if med_without > 0 else None

    return {
        "key": key,
        "label": label,
        "status": "conclusive",
        "n_with": n_with,
        "n_without": n_without,
        "median_with": med_with,
        "median_without": med_without,
        "ratio": ratio,
        "planted_or_significant": ratio is not None and (ratio >= 1.25 or ratio <= 0.8),
        "min_required": MIN_ARM_SAMPLE_SIZE
    }


def compute_all_contrasts() -> Dict[str, Any]:
    """
    Computes all contrasts against settled posts in SQLite.
    Guarantees clean connection teardown in finally block.
    """
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT text, published_at, reactions, comments, impressions FROM own_posts "
            "WHERE text IS NOT NULL AND reactions IS NOT NULL"
        ).fetchall()
        posts = [dict(r) for r in rows]
    finally:
        conn.close()

    settled = [p for p in posts if (_age_hours(p.get("published_at")) or 0) >= SETTLED_AFTER_HOURS]

    results = []
    for key, _, _ in BINARY_FEATURES:
        res = evaluate_contrast_for_posts(settled, key)
        results.append(res)

    return {
        "status": "success",
        "settled_posts_count": len(settled),
        "min_arm_size": MIN_ARM_SAMPLE_SIZE,
        "contrasts": results
    }
