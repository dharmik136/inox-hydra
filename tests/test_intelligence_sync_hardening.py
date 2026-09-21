import pytest
import os
import json
import tempfile
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from studio.backend.intelligence_sync import IntelligenceSyncEngine
from studio.backend.app import app

client = TestClient(app)


def test_sync_disallowed_scheme_ssrf_rejected():
    """Verify SSRF protection: non-HTTPS schemes (http, file, ftp) are rejected immediately with status error."""
    engine = IntelligenceSyncEngine()

    for disallowed_url in [
        "http://127.0.0.1:8000/malicious",
        "file:///etc/passwd",
        "ftp://mirror.example.com/bundle.json",
        "javascript:alert(1)"
    ]:
        res = engine.sync(cdn_url=disallowed_url)
        assert res["status"] == "error", f"Expected error status for URL: {disallowed_url}"
        assert "Disallowed URL scheme" in res["message"]


def test_import_bundle_non_dict_rejected():
    """Verify non-dict bundles return error status cleanly."""
    engine = IntelligenceSyncEngine()
    for bad_bundle in [None, "invalid_string", 12345, [1, 2, 3]]:
        res = engine.import_local_bundle(bad_bundle)
        assert res["status"] == "error"
        assert "Empty or invalid" in res["message"]


def test_import_bundle_empty_templates_rejected():
    """Verify bundle with missing or empty templates list returns error status."""
    engine = IntelligenceSyncEngine()
    for empty_bundle in [{"templates": []}, {"categories": []}, {"version": "1.0"}]:
        res = engine.import_local_bundle(empty_bundle)
        assert res["status"] == "error"
        assert "Empty or invalid" in res["message"]


def test_import_bundle_malformed_items_sanitized():
    """Verify malformed items within bundle are safely filtered and sanitized without crashing."""
    engine = IntelligenceSyncEngine()
    bundle = {
        "version": "2026.09.99",
        "templates": [
            "not a dict item",
            None,
            {"hook_text": "", "archetype": "EmptyHook"},
            {
                "hook_text": "Valid hook for hardening test",
                "archetype": "Hardening",
                "velocity_score": "not_a_float",
                "engagement_multiplier": "3.0x"
            },
            {
                "hook_text": "A" * 2000,
                "archetype": "LongHook",
                "velocity_score": 9.9
            }
        ]
    }
    res = engine.import_local_bundle(bundle)
    assert res["status"] == "success"
    assert res["imported_count"] == 2

    # Verify truncated length and sanitized score
    templates = engine.get_templates(archetype="Hardening")
    assert len(templates) == 1
    assert templates[0]["velocity_score"] == 8.0  # fallback on invalid float


def test_sync_http_200_malformed_items_sanitized():
    """Verify HTTP 200 response with corrupted hook items handles safely."""
    with tempfile.TemporaryDirectory() as td:
        engine = IntelligenceSyncEngine(etag_file=os.path.join(td, "etag_cache"))
        _run_sync_malformed_items_assertions(engine)


def _run_sync_malformed_items_assertions(engine):
    mock_payload = {
        "version": "2026.09.3",
        "templates": [
            {"hook_text": "Corrupted non-dict following"},
            12345,
            {"invalid_keys": True},
            {"hook_text": "Clean item through sync", "velocity_score": 9.1}
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload
    mock_resp.headers = {"ETag": '"etag-hardening-test"'}

    with patch("requests.get", return_value=mock_resp):
        res = engine.sync(force=True)
        assert res["status"] == "updated"
        assert res["hooks_count"] == 2


def test_get_templates_limit_clamped():
    """Verify limit parameter is strictly clamped to [1, 500] and non-int defaults safely."""
    engine = IntelligenceSyncEngine()
    
    # Negative limit clamped to 1
    templates_neg = engine.get_templates(limit=-10)
    assert len(templates_neg) <= 1

    # Over-limit clamped to 500
    templates_large = engine.get_templates(limit=5000)
    assert len(templates_large) <= 500

    # Non-int limit defaults safely
    templates_str = engine.get_templates(limit="invalid")
    assert isinstance(templates_str, list)


def test_get_status_safe_and_diagnostics():
    """Verify get_status returns expected diagnostic keys and does not leak DB connection."""
    engine = IntelligenceSyncEngine()
    status = engine.get_status()
    assert status["status"] == "success"
    assert "cdn_url" in status
    assert "cached_etag" in status
    assert "total_templates" in status
    assert "last_synced_at" in status
    assert "is_fresh" in status


def test_api_import_bundle_invalid_returns_400():
    """Verify API POST /api/v1/intelligence/bundle/import returns 400 for empty or malformed bundles."""
    res = client.post("/api/v1/intelligence/bundle/import", json={"bundle": {"templates": []}})
    assert res.status_code == 400
    assert "Empty or invalid" in res.json()["detail"]


def test_api_sync_invalid_scheme_returns_400():
    """Verify API POST /api/v1/intelligence/sync returns 400 for SSRF attempts."""
    res = client.post("/api/v1/intelligence/sync", json={"force": True, "cdn_url": "http://insecure.internal"})
    assert res.status_code == 400
    assert "Disallowed URL scheme" in res.json()["detail"]


def test_zero_em_dash_compliance():
    """Verify complete absence of em-dash character across intelligence_sync.py and test files."""
    files_to_check = [
        os.path.abspath("studio/backend/intelligence_sync.py"),
        os.path.abspath("studio/backend/app.py"),
        os.path.abspath(__file__)
    ]
    em_dash_char = chr(0x2014)
    for path in files_to_check:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            assert em_dash_char not in content, f"Em-dash detected in {path}"


def test_sync_http_200_no_valid_templates_preserves_cache():
    """Verify a 200 payload with zero usable templates neither wipes the local cache nor records the ETag."""
    with tempfile.TemporaryDirectory() as td:
        etag_file = os.path.join(td, "etag_cache")
        engine = IntelligenceSyncEngine(etag_file=etag_file)
        before_count = engine.get_total_count()
        assert before_count > 0

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"templates": [12345, {"hook_text": ""}, "garbage", None]}
        mock_resp.headers = {"ETag": '"etag-empty-payload"'}

        with patch("requests.get", return_value=mock_resp):
            res = engine.sync(force=True)

        assert res["status"] == "error"
        assert res["hooks_count"] == 0
        assert "preserved" in res["message"]
        assert engine.get_total_count() == before_count
        assert not os.path.exists(etag_file), "ETag must not be saved for a payload with no valid templates"
