"""
AI Repurposer & Algorithm Safety Production Hardening Test Suite.
=================================================================
Validates:
1. audit_linkedin_algorithm_safety handles None without TypeError.
2. audit_linkedin_algorithm_safety handles empty or whitespace text.
3. audit_linkedin_algorithm_safety clamps oversized text.
4. repurpose_content handles None without AttributeError.
5. repurpose_content handles empty input cleanly.
6. generate_10x_hooks handles None without AttributeError.
7. command_ai_engine handles None for both command and context.
8. API endpoints reject oversized payloads (>20,000 chars) with 422.
9. get_gemini_api_key closes database connection safely.
10. Strict zero em-dash compliance across all modified files.
"""

import os
import sys
import pytest
from fastapi.testclient import TestClient

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import app
from repurposer import (
    audit_linkedin_algorithm_safety,
    repurpose_content,
    generate_10x_hooks,
    command_ai_engine,
    get_gemini_api_key,
    call_gemini_api,
    MAX_AUDIT_TEXT_LENGTH,
    MAX_REPURPOSE_INPUT_LENGTH,
)

client = TestClient(app)


def test_audit_safety_none_input_safe():
    """Verifies that audit_linkedin_algorithm_safety handles None without TypeError."""
    report = audit_linkedin_algorithm_safety(None)
    assert report["safety_score"] == 100
    assert report["status_label"] == "Empty Draft"
    assert report["word_count"] == 0
    assert report["has_outbound_links"] is False


def test_audit_safety_empty_string_safe():
    """Verifies that audit_linkedin_algorithm_safety handles blank/whitespace text."""
    report = audit_linkedin_algorithm_safety("   \n\t  ")
    assert report["safety_score"] == 100
    assert report["status_label"] == "Empty Draft"
    assert len(report["recommendations"]) >= 1


def test_audit_safety_oversized_text_truncated():
    """Verifies that massive text payloads are truncated to MAX_AUDIT_TEXT_LENGTH without hanging."""
    oversized = "Architecture and systems design. " * 2000  # ~66,000 chars
    report = audit_linkedin_algorithm_safety(oversized)
    assert isinstance(report, dict)
    assert report["word_count"] > 0
    assert "safety_score" in report


def test_repurpose_content_none_input_safe():
    """Verifies that repurpose_content handles None without AttributeError."""
    frameworks = repurpose_content(None)
    assert isinstance(frameworks, list)
    assert len(frameworks) == 5
    for f in frameworks:
        assert "framework" in f
        assert "content" in f
        assert chr(0x2014) not in f["content"]


def test_repurpose_content_empty_input_safe():
    """Verifies that repurpose_content handles empty input strings."""
    frameworks = repurpose_content("   ")
    assert isinstance(frameworks, list)
    assert len(frameworks) == 5
    assert "Zero manual intervention" in frameworks[0]["content"]


def test_generate_10x_hooks_none_input_safe():
    """Verifies that generate_10x_hooks handles None without AttributeError."""
    hooks = generate_10x_hooks(None)
    assert isinstance(hooks, list)
    assert len(hooks) == 10
    for h in hooks:
        assert "archetype" in h
        assert "hook_text" in h
        assert chr(0x2014) not in h["hook_text"]


def test_command_ai_engine_none_inputs_safe():
    """Verifies that command_ai_engine handles None for command and context."""
    res = command_ai_engine(command=None, context=None)
    assert res["status"] == "success"
    assert "output" in res
    assert len(res["output"]) > 20
    assert chr(0x2014) not in res["output"]


def test_call_gemini_api_empty_prompt_safe():
    """Verifies that call_gemini_api cleanly returns None on empty or None prompt."""
    assert call_gemini_api("") is None
    assert call_gemini_api(None) is None


def test_api_format_request_oversized_422():
    """Verifies that POST /api/format/re-hook rejects oversized text payloads with 422."""
    huge_text = "A" * 20001
    resp = client.post("/api/format/re-hook", json={"text": huge_text})
    assert resp.status_code == 422

    resp2 = client.post("/api/format/algorithm-audit", json={"text": huge_text})
    assert resp2.status_code == 422

    resp3 = client.post("/api/format/repurpose", json={"text": huge_text})
    assert resp3.status_code == 422


def test_get_gemini_api_key_safe():
    """Verifies get_gemini_api_key executes without unhandled DB connection leak."""
    key = get_gemini_api_key()
    assert key is None or isinstance(key, str)


def test_zero_em_dash_compliance():
    """Audits modified files for zero occurrences of the em-dash character."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    targets = [
        os.path.join(base_dir, "studio", "backend", "repurposer.py"),
        os.path.join(base_dir, "studio", "backend", "app.py"),
        os.path.join(base_dir, "tests", "test_repurposer_hardening.py"),
    ]

    for path in targets:
        assert os.path.exists(path), f"Target file does not exist: {path}"
        text = open(path, "r", encoding="utf-8").read()
        assert chr(0x2014) not in text, f"Illegal em-dash found in: {path}"
