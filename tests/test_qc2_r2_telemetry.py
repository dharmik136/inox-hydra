"""
The telemetry shard is bounded and loses nothing at a stop. [BE-13]

Every analytics payload the bridge sent was copied whole into
analytics_telemetry.db, so one request with an extra 10 MB field grew the file
by 10 MB, and up to a batch of buffered events was lost at every stop. The
same missing limits let the creator profile store a 10 MB name. (How long the
shard keeps anything is batch R4's retention work.)
"""

import json
import os
import sys

import pytest

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend"))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402

TEN_MB = "Z" * (10 * 1024 * 1024)


def _shard():
    return app_module.telemetry_engine, app_module.telemetry_buffer


def test_an_oversized_payload_is_not_kept():
    engine, buffer = _shard()
    buffer.flush()
    before = os.path.getsize(engine.db_path)
    buffer.ingest("analytics_ingest", {"series": [], "padding": TEN_MB})
    buffer.flush()
    conn = engine.get_connection()
    try:
        payload = conn.execute("SELECT payload FROM telemetry_events ORDER BY id DESC LIMIT 1").fetchone()[0]
    finally:
        conn.close()
    assert len(payload) < 1024
    assert json.loads(payload)["characters"] > 10 * 1024 * 1024
    assert os.path.getsize(engine.db_path) - before < 1024 * 1024


def test_a_normal_payload_is_kept_whole():
    engine, buffer = _shard()
    buffer.ingest("analytics_ingest", {"series": [{"date": "2026-10-20", "impressions": 120}]})
    buffer.flush()
    conn = engine.get_connection()
    try:
        payload = conn.execute("SELECT payload FROM telemetry_events ORDER BY id DESC LIMIT 1").fetchone()[0]
    finally:
        conn.close()
    assert json.loads(payload)["series"][0]["impressions"] == 120


def test_buffered_events_are_written_at_shutdown():
    engine, buffer = _shard()
    buffer.flush()
    before = engine.get_status()["total_events"]
    with TestClient(app_module.app):
        for n in range(3):
            buffer.ingest("probe_event", {"n": n})
        assert buffer.pending_count() == 3
    assert buffer.pending_count() == 0
    assert engine.get_status()["total_events"] == before + 3


@pytest.mark.parametrize("field", ["name", "headline", "company", "brand_watermark_text"])
def test_a_huge_profile_field_is_refused(field):
    client = TestClient(app_module.app)
    before = client.get("/api/settings/profile").json()["profile"].get(field)
    res = client.post("/api/settings/profile", json={field: TEN_MB})
    assert res.status_code == 422
    assert TEN_MB[:100] not in res.text
    assert client.get("/api/settings/profile").json()["profile"].get(field) == before
