"""
Send to LinkedIn: what the creator is told when it does not go through.
======================================================================

WRITE-24: a refused send answered 502 with the whole result dict as its
detail, which the interface could not read, so the creator saw "502".
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module  # noqa: E402
from database import get_db  # noqa: E402

client = TestClient(app_module.app)
PREFIX = "qcf1b-send-"


def _future(hours=6):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _seed(name, content="A post the author approved for LinkedIn.", status="draft"):
    conn = get_db()
    try:
        conn.execute("INSERT OR REPLACE INTO posts (id, content, status) VALUES (?,?,?)", (PREFIX + name, content, status))
        conn.commit()
    finally:
        conn.close()
    return PREFIX + name


def _row(post_id):
    conn = get_db()
    try:
        return dict(conn.execute("SELECT status, scheduled_for FROM posts WHERE id = ?", (post_id,)).fetchone())
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def clean():
    yield
    conn = get_db()
    try:
        conn.execute("DELETE FROM posts WHERE id LIKE ?", (PREFIX + "%",))
        conn.execute("DELETE FROM settings WHERE key LIKE ?", ("linkedin_send_unanswered:" + PREFIX + "%",))
        conn.commit()
    finally:
        conn.close()


def _send(post_id, **extra):
    return client.post(
        f"/api/v1/posts/{post_id}/stage-to-linkedin",
        json={"scheduled_at": _future(), "confirm": True, **extra},
    )


@pytest.mark.parametrize(
    "result, expected",
    [
        ({"status": "error", "http_status": 403, "error": "<html>forbidden</html>"}, "LinkedIn refused the post (HTTP 403)"),
        ({"status": "error", "error": "Connection refused"}, "could not reach LinkedIn (Connection refused)"),
        ({"status": "refused", "message": "Set INOX_ALLOW_LINKEDIN_EGRESS=1 to allow active requests."}, "INOX_ALLOW_LINKEDIN_EGRESS"),
    ],
)
def test_a_refused_send_says_why_in_a_sentence(monkeypatch, result, expected):
    monkeypatch.setattr(app_module.linkedin_client, "schedule_norm_share", lambda **kwargs: result)
    post_id = _seed("refused")
    response = _send(post_id)
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert isinstance(detail, str), detail
    assert expected in detail
    assert "<html>" not in detail
    assert _row(post_id)["status"] == "draft"
