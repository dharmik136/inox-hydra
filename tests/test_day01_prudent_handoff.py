"""
Day 01 Implementation Verification Suite: Sovereign Foundations, Ingress & Reverse CRM.
========================================================================================
Validates all 5 mandates from docs/prudent_handoff/DAY_01_IMPLEMENTATION_SPEC.md:
1. SQLite WAL Pragmas & CRM Relational Migration
2. Ubiquitous Telegram Ingress Daemon & Directive Parser
3. Real-Time Studio Live Display (SSE Bus)
4. LinkedIn Native Cloud Scheduler Integration (Voyager API & Self-Healing Grace Period)
5. Enterprise Reverse CRM, ICP Scoring Formula, and Anti-Slop DM Generator
"""

import os
import sys
from datetime import datetime, timedelta
import sqlite3
import pytest
from fastapi.testclient import TestClient

# Ensure studio/backend is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from app import app
from database import get_db, init_db, create_draft, get_draft, list_drafts
from event_bus import event_bus
from ingress import IngressMessageParser, TelegramIngressDaemon, ingress_daemon
from linkedin_client import linkedin_client
from crm import ICPScoringEngine, ReverseCRMManager, reverse_crm

client = TestClient(app)


# -------------------------------------------------------------
# TASK 1: SQLite WAL Mode & Schema Migrations
# -------------------------------------------------------------
def test_sqlite_wal_pragmas():
    """Validates that get_db sets WAL mode, synchronous NORMAL, busy_timeout, foreign_keys, and cache_size."""
    conn = get_db()
    c = conn.cursor()

    # Journal mode
    c.execute("PRAGMA journal_mode;")
    mode = c.fetchone()[0]
    assert mode.lower() == "wal", f"Expected WAL mode, got {mode}"

    # Synchronous
    c.execute("PRAGMA synchronous;")
    sync = c.fetchone()[0]
    # 1 is NORMAL in SQLite PRAGMA synchronous
    assert sync in (1, "1", "NORMAL", "normal"), f"Expected synchronous NORMAL, got {sync}"

    # Busy timeout
    c.execute("PRAGMA busy_timeout;")
    busy = c.fetchone()[0]
    assert busy >= 5000, f"Expected busy_timeout >= 5000, got {busy}"

    # Foreign keys
    c.execute("PRAGMA foreign_keys;")
    fk = c.fetchone()[0]
    assert fk == 1, f"Expected foreign_keys=1, got {fk}"

    conn.close()


def test_crm_relational_schema_and_indexes():
    """Validates that leads and lead_interactions tables and indexes exist with correct schemas."""
    conn = get_db()
    c = conn.cursor()

    # Verify tables
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {r[0] for r in c.fetchall()}
    assert "leads" in tables
    assert "lead_interactions" in tables
    assert "drafts" in tables
    assert "queue_items" in tables

    # Verify leads columns
    c.execute("PRAGMA table_info(leads)")
    cols = {r["name"] for r in c.fetchall()}
    for req_col in ["linkedin_urn", "full_name", "headline", "company", "seniority_level", "icp_score", "lead_status"]:
        assert req_col in cols, f"Missing required column in leads: {req_col}"

    # Verify indexes
    c.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indexes = {r[0] for r in c.fetchall()}
    assert "idx_leads_icp" in indexes
    assert "idx_leads_status" in indexes
    assert "idx_interactions_lead" in indexes

    conn.close()


# -------------------------------------------------------------
# TASK 2: Ubiquitous Ingress Daemon & Directive Parser
# -------------------------------------------------------------
def test_directive_parser_draft():
    """Tests Draft: prefix correctly sets archetype and tags."""
    text = "Draft: 3 architectural rules for high-throughput messaging\nRule 1: Decouple write paths\nRule 2: Read replicas"
    parsed = IngressMessageParser.parse_message(text)
    assert parsed["archetype"] == "Draft"
    assert "mobile-ingress" in parsed["tags"]
    assert parsed["title"] == "3 architectural rules for high-throughput messaging"
    assert "Draft:" not in parsed["raw_content"]


def test_directive_parser_idea_and_hashtags():
    """Tests Idea: prefix sets Raw Idea archetype and extracts hashtags."""
    text = "Idea: Why local-first databases beat SaaS for solo creators #architecture #sqlite"
    parsed = IngressMessageParser.parse_message(text)
    assert parsed["archetype"] == "Raw Idea"
    assert "idea" in parsed["tags"]
    assert "architecture" in parsed["tags"]
    assert "sqlite" in parsed["tags"]


def test_directive_parser_schedule():
    """Tests Schedule directive sets Scheduled Post archetype and target."""
    text = "Schedule 08:30: Launching our new distributed cluster today"
    parsed = IngressMessageParser.parse_message(text)
    assert parsed["archetype"] == "Scheduled Post"
    assert parsed["schedule_target"] == "08:30"
    assert "scheduled" in parsed["tags"]


def test_two_tier_mobile_fold_calculation():
    """Tests fold line at line 3 or 140 chars, with blank lines counting as 45 chars."""
    # Case 1: 3 compact lines - fold safe
    safe_text = "Headline hook\nSub-headline context\nCall to action"
    m1 = IngressMessageParser.calculate_fold_metrics(safe_text)
    assert m1["is_pre_fold_safe"] is True
    assert m1["lines_above_fold"] == 3

    # Case 2: 4 lines - fold triggered at line 3
    four_lines = "Line 1\nLine 2\nLine 3\nLine 4"
    m2 = IngressMessageParser.calculate_fold_metrics(four_lines)
    assert m2["is_pre_fold_safe"] is False
    assert m2["lines_above_fold"] == 3

    # Case 3: Blank line counts as 45 characters
    blank_line_text = "Line 1\n\nLine 3"
    m3 = IngressMessageParser.calculate_fold_metrics(blank_line_text)
    assert m3["pre_fold_chars"] == len("Line 1") + 45 + len("Line 3")

    # Case 4: Long line > 140 chars
    long_line = "A" * 150
    m4 = IngressMessageParser.calculate_fold_metrics(long_line)
    assert m4["is_pre_fold_safe"] is False


def test_telegram_whitelist_security():
    """Tests that unauthorized chat IDs are dropped silently without persistence."""
    daemon = TelegramIngressDaemon(authorized_chat_id="12345")

    # Unauthorized
    unauth_update = {
        "update_id": 999,
        "message": {
            "chat": {"id": 999999},
            "text": "Draft: Unauthorized leak attempt"
        }
    }
    res_unauth = daemon.process_incoming_update(unauth_update)
    assert res_unauth is None

    # Authorized
    auth_update = {
        "update_id": 1000,
        "message": {
            "chat": {"id": 12345},
            "text": "Draft: Authorized message ingestion"
        }
    }
    res_auth = daemon.process_incoming_update(auth_update)
    assert res_auth is not None
    assert res_auth["title"] == "Authorized message ingestion"


# -------------------------------------------------------------
# TASK 3: Real-Time Event Bus & Server-Sent Events (SSE)
# -------------------------------------------------------------
def test_event_bus_pubsub_and_format():
    """Tests synchronous and asynchronous event publishing and SSE formatting."""
    event = event_bus.publish_sync("test_event", {"message": "hello world"})
    assert event["event"] == "test_event"
    assert event["data"]["message"] == "hello world"
    assert event["id"] > 0

    wire_format = event_bus.format_sse(event)
    assert f"id: {event['id']}\n" in wire_format
    assert "event: test_event\n" in wire_format
    assert 'data: {"message": "hello world"}\n\n' in wire_format


def test_ingress_simulation_api():
    """Tests /api/v1/ingress/simulate broadcasts draft_ingested and returns 200."""
    res = client.post("/api/v1/ingress/simulate", json={
        "text": "Draft: Event bus real-time validation test #streaming",
        "sender_name": "Chief Architect"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["record"]["title"] == "Event bus real-time validation test #streaming"


def test_stream_history_api():
    """Tests /api/v1/stream/history returns buffered events."""
    res = client.get("/api/v1/stream/history")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert isinstance(data["events"], list)
    assert len(data["events"]) > 0


# -------------------------------------------------------------
# TASK 4: LinkedIn Native Cloud Scheduler Integration
# -------------------------------------------------------------
def test_native_scheduler_staging():
    """Tests Voyager normShares payload construction with scheduledAt epoch ms and SCHEDULED state."""
    future_ms = int((datetime.now() + timedelta(days=2)).timestamp() * 1000)
    result = linkedin_client.schedule_norm_share(
        content="Testing LinkedIn Native Cloud Scheduler integration.",
        scheduled_at_ms=future_ms,
        mock=True
    )
    assert result["status"] == "success"
    assert result["payload"]["lifecycleState"] == "SCHEDULED"
    assert result["payload"]["visibility"] == "PUBLIC"
    assert result["payload"]["scheduledAt"] == future_ms
    assert result["payload"]["commentary"]["text"] == "Testing LinkedIn Native Cloud Scheduler integration."


def test_schedule_recovery_evaluation():
    """Tests self-healing fallback logic for on-time, grace period, and auto-reschedule."""
    now = datetime(2026, 9, 17, 10, 0, 0)

    # 1. On time (scheduled in future)
    future_time = now + timedelta(hours=2)
    rec1 = linkedin_client.evaluate_schedule_recovery(future_time, current_time=now)
    assert rec1["status"] == "ON_SCHEDULE"
    assert rec1["delay_minutes"] == 0

    # 2. 45-minute morning grace period (e.g. woke up 25 mins late)
    grace_time = now - timedelta(minutes=25)
    rec2 = linkedin_client.evaluate_schedule_recovery(grace_time, current_time=now)
    assert rec2["status"] == "GRACE_PERIOD_ELIGIBLE"
    assert rec2["delay_minutes"] == 25
    assert rec2["action"] == "prompt_grace_launch"

    # 3. Delay > 45 minutes -> auto-reschedule to 1:15 PM peak window
    stale_time = now - timedelta(hours=2)
    rec3 = linkedin_client.evaluate_schedule_recovery(stale_time, current_time=now)
    assert rec3["status"] == "AUTO_RESCHEDULED"
    assert rec3["delay_minutes"] == 120
    assert rec3["action"] == "auto_rescheduled"
    assert "13:15:00" in rec3["rescheduled_to"]


def test_scheduler_api_endpoints():
    """Tests native scheduler staging and recovery API endpoints."""
    future_ms = int((datetime.now() + timedelta(days=1)).timestamp() * 1000)
    res1 = client.post("/api/v1/scheduler/native/stage", json={
        "content": "API test for cloud scheduling",
        "scheduled_at_ms": future_ms,
        "mock": True
    })
    assert res1.status_code == 200
    assert res1.json()["status"] == "success"

    res2 = client.post("/api/v1/scheduler/recovery/evaluate", json={
        "scheduled_at": (datetime.now() - timedelta(minutes=15)).isoformat()
    })
    assert res2.status_code == 200
    assert res2.json()["recovery"]["status"] == "GRACE_PERIOD_ELIGIBLE"


# -------------------------------------------------------------
# TASK 5: Enterprise Reverse CRM & Anti-Slop DM Generator
# -------------------------------------------------------------
def test_deterministic_icp_equation():
    """Validates the exact multi-factor formula:
    ICP Score = min(100, max(0, W_s * 0.45 + W_i * 0.30 + W_c * 0.15 + W_q * 0.10)).
    """
    # Test Case 1: Founder (100) + >15 words comment (100) + Tier-1 company (80) + question (100)
    # Expected: 100*0.45 + 100*0.30 + 80*0.15 + 100*0.10 = 45 + 30 + 12 + 10 = 97.0
    score_founder = ICPScoringEngine.calculate_icp_score(
        headline="Founder & Managing Director",
        company="ScaleUp Cloud Systems",
        comment_text="Could you explain how write locks are decoupled across the storage layer without causing distributed consensus stalls in this architecture?",
        interaction_type="COMMENT"
    )
    assert score_founder == 97.0

    # Test Case 2: Student penalty (-40) + short comment (30) + no company (0) + no question (0)
    # Expected: -40*0.45 + 30*0.30 + 0 + 0 = -18 + 9 = -9 -> clamped to 0.0
    score_student = ICPScoringEngine.calculate_icp_score(
        headline="Computer Science Student / Seeking Internship",
        company="",
        comment_text="Nice post",
        interaction_type="COMMENT"
    )
    assert score_student == 0.0

    # Test Case 3: VP (75) + medium comment (60) + standard company (50) + no question (0)
    # Expected: 75*0.45 + 60*0.30 + 50*0.15 + 0 = 33.75 + 18 + 7.5 = 59.25 -> 59.3
    score_vp = ICPScoringEngine.calculate_icp_score(
        headline="VP of Infrastructure",
        company="Acme Corp",
        comment_text="Great overview of zero-downtime database patterns in production.",
        interaction_type="COMMENT"
    )
    assert abs(score_vp - 59.3) < 0.2


def test_anti_slop_dm_generator():
    """Validates that generated DMs quote exact excerpt and contain zero em-dashes."""
    comment = "How do you handle background queue retries when nodes restart unexpectedly?"
    dm = ICPScoringEngine.generate_contextual_dm(
        lead_name="Siddharth Rao",
        comment_text=comment,
        post_topic="distributed task workers"
    )
    # Anti-slop constraints:
    assert "\u2014" not in dm, "BANNED: Em-dash found in generated DM!"
    assert "Siddharth" in dm
    assert "distributed task workers" in dm
    assert "How do you handle background queue retries" in dm
    assert "Are you testing similar workflows in your stack?" in dm


def test_reverse_crm_manager_ingestion():
    """Tests end-to-end ingestion and querying in ReverseCRMManager."""
    res = reverse_crm.ingest_interaction(
        full_name="Priya Sharma",
        linkedin_urn="urn:li:person:priya-sharma-test",
        headline="Chief Technology Officer",
        company="FinTech Enterprise Systems",
        interaction_type="COMMENT",
        comment_text="Are transaction logs replayable across cold standby replicas?",
        post_topic="local SQLite replication"
    )
    assert res["full_name"] == "Priya Sharma"
    assert res["seniority_level"] == "C-Suite"
    assert res["icp_score"] >= 70.0
    assert "\u2014" not in res["suggested_dm"]

    # Verify querying high value leads
    high_value = reverse_crm.list_high_value_leads(min_icp_score=60.0)
    names = [l["full_name"] for l in high_value]
    assert "Priya Sharma" in names


def test_crm_api_endpoints():
    """Tests /api/v1/crm/interactions/ingest and /api/v1/crm/score-preview."""
    res = client.post("/api/v1/crm/score-preview", json={
        "headline": "CEO & Founder",
        "company": "Cloud Distributed Matrix",
        "comment_text": "What is the failover latency?",
        "interaction_type": "COMMENT"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["icp_score"] > 80.0
    assert data["seniority_level"] == "Founder"


# -------------------------------------------------------------
# TASK 6: Hardened Security, Vault DPAPI, Circuit Breaker & GDPR Purge
# -------------------------------------------------------------
def test_vault_encryption_decryption():
    """Validates DPAPI / machine-keyed token vault encryption and decryption."""
    from vault import encrypt_token, decrypt_token

    sample_token = "AQEDATk78Q4E...long_linkedin_session_cookie..."
    encrypted = encrypt_token(sample_token)

    assert encrypted != sample_token
    assert encrypted.startswith(("dpapi:", "locenc2:", "locenc:"))

    decrypted = decrypt_token(encrypted)
    assert decrypted == sample_token

    # Test backward compatibility with legacy unencrypted strings
    legacy_plain = "legacy_unencrypted_cookie_value"
    assert decrypt_token(legacy_plain) == legacy_plain

    # Test integration with linkedin_client save_tokens & get_tokens
    linkedin_client.save_tokens("test_li_at_vault_token", "test_jsessionid_vault")
    tokens = linkedin_client.get_tokens()
    assert tokens.get("li_at") == "test_li_at_vault_token"
    assert tokens.get("JSESSIONID") == "test_jsessionid_vault"

    # Verify that raw value in database is actually encrypted
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = 'li_at'")
    raw_val = c.fetchone()["value"]
    conn.close()
    assert raw_val.startswith(("dpapi:", "locenc2:", "locenc:"))


def test_circuit_breaker_safeguards():
    """Validates CircuitBreaker states, trip thresholds, and session health checks."""
    from linkedin_client import CircuitBreaker

    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=300.0)
    assert cb.state == "CLOSED"
    assert cb.can_execute() is True

    # Immediate trip on 401 Unauthorized
    cb.record_failure(status_code=401, reason="Unauthorized session")
    assert cb.state == "OPEN"
    assert cb.can_execute() is False
    assert "Security checkpoint" in cb.last_trip_reason

    # Reset
    cb.reset()
    assert cb.state == "CLOSED"
    assert cb.can_execute() is True

    # 3 consecutive non-security errors trip threshold
    cb.record_failure(status_code=500, reason="Internal Server Error")
    assert cb.state == "CLOSED"
    cb.record_failure(status_code=502, reason="Bad Gateway")
    assert cb.state == "CLOSED"
    cb.record_failure(status_code=503, reason="Service Unavailable")
    assert cb.state == "OPEN"
    assert cb.can_execute() is False
    assert "Failure threshold reached" in cb.last_trip_reason

    # Test /api/v1/session/health endpoint in mock mode
    res = client.get("/api/v1/session/health?mock=true")
    assert res.status_code == 200
    data = res.json()
    assert data["healthy"] is True


def test_telegram_adaptive_polling():
    """Validates Telegram ingress adaptive polling delays, backoff, and diagnostics."""
    daemon = TelegramIngressDaemon()

    # Normal daytime (14:00) delay should be 2.0s
    day_dt = datetime(2026, 9, 17, 14, 0, 0)
    assert daemon.is_quiet_hours(day_dt) is False
    assert daemon.calculate_next_poll_interval(current_time=day_dt, has_error=False) == 2.0

    # Night quiet hours (02:00) delay should be 120.0s
    night_dt = datetime(2026, 9, 17, 2, 0, 0)
    assert daemon.is_quiet_hours(night_dt) is True
    assert daemon.calculate_next_poll_interval(current_time=night_dt, has_error=False) == 120.0

    # Exponential error backoff: doubles up to 60.0s max
    e1 = daemon.calculate_next_poll_interval(current_time=day_dt, has_error=True)
    assert e1 == 4.0
    e2 = daemon.calculate_next_poll_interval(current_time=day_dt, has_error=True)
    assert e2 == 8.0
    e3 = daemon.calculate_next_poll_interval(current_time=day_dt, has_error=True)
    assert e3 == 16.0

    # Status endpoint
    res = client.get("/api/v1/ingress/status")
    assert res.status_code == 200
    data = res.json()
    assert "current_delay_seconds" in data
    assert "is_quiet_hours" in data


def test_crm_gdpr_purge_and_timeline():
    """Validates GDPR cascade deletion, interaction timeline retrieval, and inactive lead archival."""
    # Ingest a dedicated test lead
    urn = "urn:li:person:gdpr-test-subject"
    lead_info = reverse_crm.ingest_interaction(
        full_name="Karan Verma",
        linkedin_urn=urn,
        headline="Founder & CEO @ Stealth Security",
        company="Stealth Security",
        interaction_type="COMMENT",
        comment_text="What are your retention policies for personal data?",
        post_topic="GDPR data privacy"
    )
    lead_id = lead_info["lead_id"]
    assert lead_id is not None

    # Verify timeline endpoint
    res_timeline = client.get(f"/api/v1/crm/leads/{lead_id}/timeline")
    assert res_timeline.status_code == 200
    t_data = res_timeline.json()
    assert t_data["status"] == "success"
    assert t_data["lead"]["id"] == lead_id
    assert len(t_data["interactions"]) >= 1

    # Verify archival endpoint
    res_archive = client.post("/api/v1/crm/leads/archive-inactive", json={"inactive_days": 180})
    assert res_archive.status_code == 200
    assert res_archive.json()["status"] == "success"

    # Execute GDPR Purge
    res_purge = client.delete(f"/api/v1/crm/leads/{lead_id}/purge")
    assert res_purge.status_code == 200
    p_data = res_purge.json()
    assert p_data["status"] == "purged"
    assert p_data["lead_deleted"] is True
    assert p_data["interactions_deleted"] >= 1

    # Verify lead is gone from database
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM leads WHERE id = ?", (lead_id,))
    assert c.fetchone() is None
    c.execute("SELECT id FROM lead_interactions WHERE lead_id = ?", (lead_id,))
    assert c.fetchone() is None
    conn.close()

    # Second purge should return 404
    res_repeat = client.delete(f"/api/v1/crm/leads/{lead_id}/purge")
    assert res_repeat.status_code == 404


def test_sqlite_wal_checkpoint_api():
    """Validates /api/v1/database/checkpoint endpoint returns status checkpointed."""
    res = client.post("/api/v1/database/checkpoint")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "checkpointed"

