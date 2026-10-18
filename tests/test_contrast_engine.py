"""
Tests for CP1 Contrast Engine (abstaining below n=8 per arm).
=============================================================
Verifies:
1. At n=3 per arm, every contrast abstains with 'not_enough_data'.
2. With n=10 per arm and a planted effect, the contrast is conclusive and detects the ratio.
"""

import pytest
from studio.backend.contrast_engine import (
    evaluate_contrast_for_posts,
    MIN_ARM_SAMPLE_SIZE,
    compute_all_contrasts
)


def test_abstains_below_minimum_sample_size():
    """At n=3 per arm, every contrast must report not_enough_data."""
    small_corpus = [
        {"text": "Why do distributed databases fail? Here is what we found.", "reactions": 150},
        {"text": "Is SQLite enough for 100k users? Let us test it.", "reactions": 180},
        {"text": "Can you run local LLMs offline? A practical guide.", "reactions": 130},
        {"text": "Postgres WAL mode explained simply.", "reactions": 60},
        {"text": "Building clean software without cloud dependencies.", "reactions": 70},
        {"text": "Why simple architectures win in the long term.", "reactions": 80},
    ]

    res = evaluate_contrast_for_posts(small_corpus, "question_opening")
    assert res["status"] == "not_enough_data"
    assert res["n_with"] == 3
    assert res["n_without"] == 3
    assert res["min_required"] == MIN_ARM_SAMPLE_SIZE
    assert "Requires at least 8 posts per arm" in res["reason"]


def test_planted_effect_with_adequate_sample_size():
    """With n=10 per arm, a planted effect is conclusive."""
    planted_corpus = []
    # 10 question posts with higher reactions (median around 200)
    for i in range(10):
        planted_corpus.append({
            "text": f"Why does architecture matter in project {i}? It changes everything.",
            "reactions": 180 + i * 5
        })

    # 10 statement posts with lower reactions (median around 50)
    for i in range(10):
        planted_corpus.append({
            "text": f"Standard statement number {i} regarding database operations.",
            "reactions": 45 + i * 2
        })

    res = evaluate_contrast_for_posts(planted_corpus, "question_opening")
    assert res["status"] == "conclusive"
    assert res["n_with"] == 10
    assert res["n_without"] == 10
    assert res["median_with"] >= 180
    assert res["median_without"] <= 65
    assert res["ratio"] > 2.5
    assert res["planted_or_significant"] is True
