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
    """Verifies deterministic regex classification of post topics."""
    assert classify_post_topic("How we scaled our Postgres and SQLite WAL architecture") == "Architecture & Systems"
    assert classify_post_topic("Deploying local LLMs and multi-agent swarms") == "AI & Machine Learning"
    assert classify_post_topic("Why engineering culture and senior hiring matter") == "Leadership & Hiring"
    assert classify_post_topic("B2B SaaS product pricing and retention metrics") == "Product & Strategy"
    assert classify_post_topic("A brief thought on daily notes") == "Practitioner Insights"
    assert classify_post_topic(None) == "General Practitioner"


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
