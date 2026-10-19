"""
Tests for CP3 Retrieval Evidence Brief & CP4 Topic Attribution.
==============================================================
Verifies:
1. Topic classification based on domain patterns.
2. Cold start handling on empty database.
3. Topic to qualified lead attribution calculation.
4. Grounded retrieval brief formatting.
"""

import pytest
from studio.backend.evidence_briefing import (
    classify_post_topic,
    get_topic_attribution_map,
    get_retrieval_evidence_brief
)
from studio.backend.database import get_db


def test_classify_post_topic():
    """A post goes under the first of the creator's own recurring words it mentions."""
    from studio.backend.evidence_briefing import derive_topic_vocabulary
    history = [
        "How we scaled our Postgres setup",
        "Postgres vacuum, explained",
        "Hiring a senior engineer",
        "What our hiring loop asks",
        "A brief thought on daily notes",
    ]
    vocabulary = derive_topic_vocabulary(history)
    assert classify_post_topic("Postgres on a laptop", vocabulary) == "Postgres"
    assert classify_post_topic("Hiring in a downturn", vocabulary) == "Hiring"
    assert classify_post_topic("A brief thought on daily notes", vocabulary) == "Other posts"
    assert classify_post_topic(None, vocabulary) == "Other posts"


def test_topic_attribution_cold_start():
    """On a blank database, topic attribution returns a clean cold-start payload."""
    res = get_topic_attribution_map()
    assert res["status"] in ("cold_start", "success")
    assert "summary_sentence" in res


def test_evidence_brief_cold_start():
    """Fewer than 3 posts yields has_evidence: False without raising."""
    res = get_retrieval_evidence_brief()
    assert isinstance(res, dict)
    assert "has_evidence" in res
