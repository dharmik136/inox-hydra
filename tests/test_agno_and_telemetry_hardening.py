import os
import sys
import tempfile
import time
from datetime import datetime, timezone
import pytest

# Ensure studio/backend and studio/core are on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "studio", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "studio", "core"))

from agno_agent import (
    clean_no_em_dashes,
    LeadResearchAgent,
    IcebreakerAgent,
    EnrichmentOrchestrator,
    agno_orchestrator,
)
from telemetry_shard import (
    TelemetryEngine,
    TelemetryBuffer,
)


def test_agno_clean_no_em_dashes_null_and_variations():
    """clean_no_em_dashes handles None, numbers, em-dashes, and double dashes cleanly."""
    assert clean_no_em_dashes(None) == ""
    assert clean_no_em_dashes(12345) == "12345"

    em_dash = chr(0x2014)
    en_dash = chr(0x2013)
    raw = f"Enterprise{em_dash}architecture{en_dash}always -- first--principles"
    cleaned = clean_no_em_dashes(raw)
    assert em_dash not in cleaned
    assert en_dash not in cleaned
    assert "--" not in cleaned
    assert "Enterprise, architecture, always, first, principles" == cleaned


def test_agno_researcher_null_and_malformed_lead():
    """LeadResearchAgent handles None, non-dict, and empty leads gracefully."""
    agent = LeadResearchAgent()
    res_none = agent.research(None)  # type: ignore
    assert res_none["name"] == "Prospect"
    assert res_none["company"] == "Enterprise Organization"

    res_empty = agent.research({})
    assert res_empty["name"] == "Prospect"
    assert isinstance(res_empty["key_topics"], list)


def test_agno_enricher_invalid_lead_id_and_types():
    """EnrichmentOrchestrator enforces type safety on lead arguments."""
    orch = EnrichmentOrchestrator()
    with pytest.raises(TypeError, match="must be a dictionary"):
        orch.enrich_lead_payload(None)  # type: ignore

    with pytest.raises(ValueError, match="not found in CRM database"):
        orch.enrich_lead("non_existent_lead_id_999999")


def test_agno_enricher_corrupted_json_in_db():
    """get_enrichment handles corrupted JSON strings in database without raising exceptions."""
    from database import get_db, init_db
    init_db()
    conn = get_db()
    test_id = "test-corrupted-json-lead"
    try:
        with conn:
            conn.execute("""
            INSERT OR REPLACE INTO leads (id, name, headline, company, status, created_at)
            VALUES (?, 'Test User', 'Architect', 'TestCorp', 'New Lead', CURRENT_TIMESTAMP)
            """, (test_id,))
            conn.execute("""
            INSERT OR REPLACE INTO lead_enrichments 
            (lead_id, company_intelligence, estimated_tech_stack, key_topics, friction_points, icebreakers, enriched_by, enriched_at)
            VALUES (?, 'Intel', 'Stack', '{bad_json:', 'Friction', 'not-json-array', 'local', CURRENT_TIMESTAMP)
            """, (test_id,))
    finally:
        conn.close()

    enrichment = agno_orchestrator.get_enrichment(test_id)
    assert enrichment is not None
    assert enrichment["key_topics"] == []
    assert enrichment["icebreakers"] == []


def test_telemetry_shard_get_recent_events_limit_clamping():
    """get_recent_events bounds limit parameter within [1, 500]."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_telemetry.db")
        engine = TelemetryEngine(db_path=db_path)

        # Seed 5 events
        events = [(f"type_{i}", "test", "{}") for i in range(5)]
        engine.record_events_batch(events)

        # Negative limit clamps to 1
        res_neg = engine.get_recent_events(limit=-5)
        assert len(res_neg) == 1

        # Huge limit query executes without error
        res_huge = engine.get_recent_events(limit=99999)
        assert len(res_huge) == 5


def test_telemetry_buffer_ingest_complex_unserializable_payload():
    """TelemetryBuffer ingests complex non-JSON types (e.g. datetime) safely using default=str."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_telemetry_complex.db")
        engine = TelemetryEngine(db_path=db_path)
        buffer = TelemetryBuffer(engine=engine, batch_size=2)

        complex_payload = {
            "time": datetime.now(timezone.utc),
            "custom_set": {10, 20},
        }

        # Should not throw TypeError
        success = buffer.ingest("complex_event", complex_payload)
        assert success is True
        assert buffer.pending_count() == 1


def test_telemetry_buffer_dwell_clamping():
    """ingest_dwell defensive checks clamp dwell_seconds and scroll_depth."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_telemetry_dwell.db")
        engine = TelemetryEngine(db_path=db_path)
        buffer = TelemetryBuffer(engine=engine, batch_size=10)

        # Negative dwell seconds clamped to 0.0
        buffer.ingest_dwell("post_1", dwell_seconds=-10.0, scroll_depth=2.5, reading_velocity_wpm=-50.0)
        assert len(buffer._dwell_buffer) == 1
        _, dwell_s, scroll, vel = buffer._dwell_buffer[0]
        assert dwell_s == 0.0
        assert scroll == 1.0
        assert vel == 1.0


def test_zero_em_dash_compliance_module13():
    """Verify zero em-dash (0x2014) characters exist in Module 13 files."""
    em_dash = chr(0x2014)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_files = [
        os.path.join(base_dir, "studio", "backend", "agno_agent.py"),
        os.path.join(base_dir, "studio", "core", "telemetry_shard.py"),
        os.path.abspath(__file__),
    ]

    for file_path in target_files:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert em_dash not in content, f"Em-dash found in {file_path}"
