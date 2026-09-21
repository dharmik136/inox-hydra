import pytest
import os
from fastapi.testclient import TestClient

from studio.backend.gstack_governance import GStackGovernanceEngine, gstack_engine
from studio.backend.app import app

client = TestClient(app)


def test_gstack_add_task_empty_title_rejected():
    """Verify empty or whitespace-only task title raises ValueError and is rejected."""
    engine = GStackGovernanceEngine()
    for empty_title in ["", "   ", None]:
        with pytest.raises(ValueError, match="title"):
            engine.add_backlog_task(
                role="CEO",
                title=empty_title,
                specification="Valid spec"
            )


def test_gstack_add_task_empty_specification_rejected():
    """Verify empty or whitespace-only specification raises ValueError."""
    engine = GStackGovernanceEngine()
    for empty_spec in ["", "   ", None]:
        with pytest.raises(ValueError, match="specification"):
            engine.add_backlog_task(
                role="CEO",
                title="Valid Title",
                specification=empty_spec
            )


def test_gstack_add_task_invalid_role_rejected():
    """Verify invalid role raises ValueError in engine and returns 400 in API."""
    engine = GStackGovernanceEngine()
    with pytest.raises(ValueError, match="Invalid G-Stack role"):
        engine.add_backlog_task(
            role="NON_EXISTENT_ROLE",
            title="Valid Title",
            specification="Valid spec"
        )

    res = client.post("/api/v1/gstack/backlog", json={
        "role": "HACKER",
        "title": "Valid Title",
        "specification": "Valid spec"
    })
    assert res.status_code == 400
    assert "Invalid G-Stack role" in res.json()["detail"]


def test_gstack_add_task_invalid_status_rejected():
    """Verify invalid status raises ValueError."""
    engine = GStackGovernanceEngine()
    with pytest.raises(ValueError, match="Invalid status"):
        engine.add_backlog_task(
            role="CSO",
            title="Security audit",
            specification="Run DPAPI check",
            status="INVALID_STATUS"
        )


def test_gstack_update_status_invalid_task_id():
    """Verify negative, zero, or non-existent task ID returns False without crashing."""
    engine = GStackGovernanceEngine()
    assert engine.update_backlog_status(-1, "VERIFIED") is False
    assert engine.update_backlog_status(0, "VERIFIED") is False
    assert engine.update_backlog_status(99999999, "VERIFIED") is False


def test_gstack_update_status_invalid_status_rejected():
    """Verify invalid status update raises ValueError in engine and returns 400 in API."""
    engine = GStackGovernanceEngine()
    with pytest.raises(ValueError, match="Invalid status"):
        engine.update_backlog_status(1, "BOGUS_STATUS")

    res = client.patch("/api/v1/gstack/backlog/1", json={"status": "BOGUS_STATUS"})
    assert res.status_code == 400
    assert "Invalid status" in res.json()["detail"]


def test_gstack_audit_none_or_non_string_content_handled():
    """Verify audit_content_or_feature handles None, int, and non-string content safely without AttributeError."""
    engine = GStackGovernanceEngine()
    for bad_content in [None, 12345, [], {}]:
        res = engine.audit_content_or_feature(bad_content)
        assert res["passed"] is False
        assert "score" in res
        assert "gates" in res
        assert len(res["violations"]) > 0


def test_gstack_audit_huge_content_truncated():
    """Verify huge content (>50k chars) is bounded safely without memory explosion."""
    engine = GStackGovernanceEngine()
    huge_text = "Line of text\n" * 10000
    res = engine.audit_content_or_feature(huge_text)
    assert res["passed"] is False
    # Gate 2 fails because content exceeds 3000 chars
    assert res["gates"]["gate_2_eng_manager"]["passed"] is False


def test_gstack_backlog_clamped_limit():
    """Verify get_backlog handles negative or excessive limit arguments safely."""
    engine = GStackGovernanceEngine()
    res_neg = engine.get_backlog(limit=-5)
    assert isinstance(res_neg, list)
    assert len(res_neg) <= 1

    res_large = engine.get_backlog(limit=50000)
    assert isinstance(res_large, list)


def test_gstack_zero_em_dash_compliance():
    """Verify complete absence of em-dash character across gstack_governance.py and test file."""
    files_to_check = [
        os.path.abspath("studio/backend/gstack_governance.py"),
        os.path.abspath("studio/backend/app.py"),
        os.path.abspath(__file__)
    ]
    em_dash_char = chr(0x2014)
    for path in files_to_check:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            assert em_dash_char not in content, f"Em-dash detected in {path}"
