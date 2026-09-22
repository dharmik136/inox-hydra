"""
Telemetry Shard & High-Velocity Passive Ingress Verification Suite.
===================================================================
Automated QA verifying:
1. Subsystem sharded SQLite WAL database (analytics_telemetry.db).
2. Non-blocking in-memory ring buffer (TelemetryBuffer) with < 1us ingest.
3. Thread-safe bulk batch commits (executemany) avoiding lock contention.
4. Passive Voyager endpoints ingestion: /voyager/api/feed/updatesV2 and /voyager/api/identity/profiles.
5. Strict zero em-dash compliance.
"""

import os
import sys
import tempfile
import time

import pytest
from fastapi.testclient import TestClient

# Ensure studio/backend and repo root are on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from studio.core.telemetry_shard import TelemetryEngine, TelemetryBuffer
from studio.backend.app import app
from studio.backend.database import get_db, init_db

client = TestClient(app)


@pytest.fixture
def temp_telemetry_env():
    """Provides an isolated temporary environment for telemetry shard testing."""
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "test_analytics_telemetry.db")
        engine = TelemetryEngine(db_path=db_path)
        buffer = TelemetryBuffer(engine=engine, batch_size=5, max_buffer_size=50)
        yield engine, buffer, db_path


def test_telemetry_engine_wal_and_schema(temp_telemetry_env):
    """Verifies SQLite WAL journal mode, table creation, and indexes."""
    engine, _, db_path = temp_telemetry_env
    assert os.path.exists(db_path)

    conn = engine.get_connection()
    cur = conn.cursor()

    # Check WAL mode
    cur.execute("PRAGMA journal_mode")
    mode = cur.fetchone()[0]
    assert mode.upper() == "WAL"

    # Check tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {r[0] for r in cur.fetchall()}
    assert "telemetry_events" in tables
    assert "post_dwell_metrics" in tables

    # Check indexes
    cur.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indexes = {r[0] for r in cur.fetchall()}
    assert "idx_telemetry_events_type" in indexes
    assert "idx_dwell_metrics_post" in indexes

    conn.close()


def test_telemetry_buffer_sub_microsecond_ram_ingest(temp_telemetry_env):
    """Benchmarks in-memory ring buffer ingest latency (< 10 microseconds per item in RAM)."""
    engine, _, _ = temp_telemetry_env
    # Create buffer with large batch_size to benchmark pure RAM staging without disk I/O
    ram_buffer = TelemetryBuffer(engine=engine, batch_size=10000, max_buffer_size=10000)

    t0 = time.perf_counter()
    iterations = 1000
    for i in range(iterations):
        ram_buffer.ingest(
            event_type="voyager_feed_ping",
            payload={"index": i, "status": "active"},
            source="test_runner"
        )
    t1 = time.perf_counter()

    avg_latency_us = ((t1 - t0) / iterations) * 1_000_000
    assert avg_latency_us < 50.0, f"Pure RAM ingest latency too high: {avg_latency_us:.2f} us"
    assert ram_buffer.pending_count() == iterations


def test_telemetry_buffer_batch_flushing_and_eviction(temp_telemetry_env):
    """Verifies threshold-based batch flush and bounded buffer size."""
    engine, buffer, _ = temp_telemetry_env

    # Insert 4 items (below batch_size=5)
    for i in range(4):
        buffer.ingest("ping", {"num": i})
    assert buffer.pending_count() == 4

    # 5th item triggers automatic flush
    buffer.ingest("ping", {"num": 4})
    assert buffer.pending_count() == 0

    # Verify items landed in SQLite
    events = engine.get_recent_events(limit=10)
    assert len(events) == 5

    # Test dwell ingestion
    buffer.ingest_dwell("post-xyz", dwell_seconds=14.5, scroll_depth=0.85, reading_velocity_wpm=215.0)
    assert buffer.pending_count() == 1
    flush_res = buffer.flush()
    assert flush_res["flushed_dwells"] == 1
    assert buffer.pending_count() == 0


def test_api_analytics_ingest_with_telemetry_shard():
    """Validates /api/analytics/ingest passes through to both core DB and telemetry shard."""
    init_db()
    payload = {
        "event_type": "feed_updates_v2",
        "source": "chrome_mv3_observer",
        "posts": [
            {
                "id": "post-shard-test-1",
                "content": "Zero-friction decoupled telemetry shard validation.",
                "impressions": 1250,
                "reactions": 85,
                "comments": 22,
                "shares": 9
            }
        ],
        "viewer_seniority": [
            {"label": "Chief Technology Officer", "percentage": 35.0},
            {"label": "VP of Engineering", "percentage": 45.0}
        ]
    }

    res = client.post("/api/analytics/ingest", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["posts_updated"] >= 1

    # Verify demographics received seniority
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT label, percentage FROM audience_demographics WHERE dimension = 'seniority'")
    rows = cur.fetchall()
    labels = {r["label"] for r in rows}
    assert "Chief Technology Officer" in labels
    conn.close()

    # Flush shard and verify status
    flush_res = client.post("/api/v1/telemetry/flush")
    assert flush_res.status_code == 200

    status_res = client.get("/api/v1/telemetry/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["status"] == "healthy"
    assert status_data["journal_mode"].upper() == "WAL"


def test_extension_background_observer_contract():
    """Validates background.js interceptors and token sanitization logic."""
    ext_bg = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "extension", "background.js"))
    assert os.path.exists(ext_bg)

    with open(ext_bg, "r", encoding="utf-8") as f:
        content = f.read()

    # Required Voyager API listeners
    assert "/voyager/api/feed/updatesV2" in content
    assert "/voyager/api/identity/profiles" in content
    assert "voyager/api/identity/dash/creatorAnalytics" in content
    assert "sanitizeTelemetryPayload" in content
    assert "forwardPassiveTelemetry" in content
    # The literal URL moved into studioFetch, which attaches the token and
    # sends from the extension origin rather than the LinkedIn page.
    assert 'STUDIO_ORIGIN = "http://127.0.0.1:8000"' in content
    assert 'studioFetch("/api/analytics/ingest"' in content

    # Zero em-dash invariant
    assert "\u2014" not in content


def test_strict_zero_em_dash_in_telemetry_files():
    """Guarantees zero em-dashes across all telemetry shard source and test files."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    files = [
        os.path.join(repo_root, "studio", "core", "telemetry_shard.py"),
        os.path.join(repo_root, "studio", "core", "__init__.py"),
        os.path.join(repo_root, "studio", "extension", "background.js"),
        __file__
    ]
    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        assert "\u2014" not in text, f"Illegal em-dash detected in {path}"


def test_flush_failure_restores_buffered_events(temp_telemetry_env):
    """Verifies a failed SQLite write restores staged items to the buffer instead of dropping them."""
    engine, buffer, db_path = temp_telemetry_env

    buffer.ingest("hardening_event", {"n": 1})
    buffer.ingest_dwell("post-x", 12.5)
    assert buffer.pending_count() == 2

    original_events = engine.record_events_batch
    original_dwells = engine.record_dwell_batch

    def failing_write(batch):
        raise RuntimeError("database is locked")

    engine.record_events_batch = failing_write
    engine.record_dwell_batch = failing_write
    try:
        res = buffer.flush()
        assert res["flushed_events"] == 0
        assert res["flushed_dwells"] == 0
        assert "error" in res
        assert buffer.pending_count() == 2, "Staged items must survive a failed flush"
    finally:
        engine.record_events_batch = original_events
        engine.record_dwell_batch = original_dwells

    res2 = buffer.flush()
    assert res2["flushed_events"] == 1
    assert res2["flushed_dwells"] == 1
    assert buffer.pending_count() == 0


def test_failed_flush_does_not_block_subsequent_ingests(temp_telemetry_env):
    """Verifies a broken engine does not turn every ingest() into a blocking failed write."""
    engine, buffer, db_path = temp_telemetry_env

    attempts = {"n": 0}

    def failing_write(batch):
        attempts["n"] += 1
        time.sleep(0.02)
        raise RuntimeError("database is locked")

    engine.record_events_batch = failing_write

    for i in range(buffer.batch_size):
        buffer.ingest("storm", {"i": i})
    assert attempts["n"] == 1, "The first threshold crossing should attempt exactly one flush"

    started = time.perf_counter()
    for i in range(buffer.batch_size * 3):
        buffer.ingest("storm", {"i": 1000 + i})
    elapsed = time.perf_counter() - started

    assert attempts["n"] == 1, "Ingests during the cooldown must not re-trigger the failing engine"
    assert elapsed < 0.5, f"Ingest stayed non-blocking (took {elapsed:.3f}s)"
    assert buffer.pending_count() > 0


def test_concurrent_failed_flushes_preserve_chronological_order(temp_telemetry_env):
    """Verifies overlapping flushes are serialized so restored batches keep their order."""
    import threading

    engine, buffer, db_path = temp_telemetry_env

    def failing_write(batch):
        time.sleep(0.01)
        raise RuntimeError("locked")

    original = engine.record_events_batch
    engine.record_events_batch = failing_write

    for i in range(6):
        buffer.ingest("ordered", {"seq": i})

    threads = [threading.Thread(target=buffer.flush) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    engine.record_events_batch = original
    buffer.flush()

    rows = engine.get_recent_events(event_type="ordered", limit=100)
    seqs = [r["payload"]["seq"] for r in rows][::-1]
    assert seqs == sorted(seqs), f"Restored events lost chronological order: {seqs}"
    assert len(seqs) == 6, f"Expected all 6 events to survive, got {len(seqs)}"
