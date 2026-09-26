"""
The one route that reaches LinkedIn on the author's behalf.
==========================================================

Until now nothing in this product posted to LinkedIn. The composer marked a
local row and said so, and `linkedin_client.schedule_norm_share` existed,
worked, and had never been called by anything. Wiring it was deliberately left
as a product decision rather than a bug fix, because it posts to a real
account.

It is wired now, and these tests are the terms.

It schedules rather than posts. The Voyager payload carries lifecycleState
SCHEDULED and a scheduledAt, so LinkedIn holds the post and publishes it
itself. That is the whole value: it solves the sleeping laptop, which a local
scheduler by definition cannot.

Four things guard it, and each is asserted here rather than described:

  Confirmation is required, not defaulted. The call cannot be undone from this
  side; once LinkedIn has the post, cancelling means going to LinkedIn.

  The content comes from the stored row, never from the request body. The
  author approved what is in the record, and a body carrying its own text
  could post something they never read.

  The record is written only after LinkedIn accepts. Writing first would leave
  a post marked as handed over when it was not, which is the exact failure
  this project has found in itself repeatedly.

  Refusals are returned intact. The egress guard refuses the linkedin category
  by default, and its message names the flag that changes that. Rewording it
  would remove the one thing an author needs in order to act.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module
from database import get_db

client = TestClient(app_module.app)

PREFIX = "stageprobe-"


def _future(hours=6):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _seed(post_id, content="A draft the author actually approved.", status="draft"):
    conn = get_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO posts (id, content, status) VALUES (?,?,?)",
            (PREFIX + post_id, content, status),
        )
        conn.commit()
    finally:
        conn.close()
    return PREFIX + post_id


def _row(post_id):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT status, scheduled_for FROM posts WHERE id = ?", (post_id,)
        ).fetchone()
    finally:
        conn.close()


def _stage(post_id, **body):
    return client.post(f"/api/v1/posts/{post_id}/stage-to-linkedin", json=body)


@pytest.fixture(autouse=True)
def clean_probes():
    yield
    conn = get_db()
    try:
        conn.execute("DELETE FROM posts WHERE id LIKE ?", (PREFIX + "%",))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------

def test_it_will_not_send_without_confirmation():
    """
    The defining guard. An interface that can fire this by accident is the
    wrong interface, so the absence of confirmation is a refusal rather than a
    default.
    """
    post_id = _seed("needsconfirm")
    response = _stage(post_id, scheduled_at=_future())

    assert response.status_code == 400
    assert "cannot be undone" in response.json()["detail"]
    assert _row(post_id)["status"] == "draft", "the record moved without consent"


def test_the_body_cannot_supply_its_own_text():
    """
    The author approved the row. A request that carried content could post
    something they never saw, so the field does not exist.
    """
    assert "content" not in app_module.StagePostRequest.model_fields


# ---------------------------------------------------------------------------
# It refuses what LinkedIn would refuse, before asking LinkedIn
# ---------------------------------------------------------------------------

def test_a_time_in_the_past_is_refused_here():
    """
    LinkedIn will not hold a post for a time that has gone. Catching it here
    costs one comparison and saves a request against the author's account,
    which is the thing worth not spending.
    """
    post_id = _seed("past")
    past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

    response = _stage(post_id, scheduled_at=past, confirm=True)

    assert response.status_code == 400
    assert "passed" in response.json()["detail"]


def test_an_unparseable_time_is_refused():
    post_id = _seed("badtime")
    response = _stage(post_id, scheduled_at="tomorrow afternoon", confirm=True)
    assert response.status_code == 400


def test_an_empty_post_is_not_sent():
    post_id = _seed("empty", content="   ")
    response = _stage(post_id, scheduled_at=_future(), confirm=True)
    assert response.status_code == 400
    assert "no content" in response.json()["detail"]


def test_a_missing_post_is_a_404():
    assert _stage(PREFIX + "absent", scheduled_at=_future(), confirm=True).status_code == 404


def test_an_already_published_post_is_not_sent_again():
    post_id = _seed("done", status="published")
    assert _stage(post_id, scheduled_at=_future(), confirm=True).status_code == 400


# ---------------------------------------------------------------------------
# The refusal an author will actually meet
# ---------------------------------------------------------------------------

def test_a_mock_result_is_never_reported_as_a_send(monkeypatch):
    """
    The defect this route introduced and its own test caught.

    schedule_norm_share returns status "success" with mode "mock" when there is
    no saved li_at, which is the default state of a fresh install. Checking
    only the status told a creator with no session that "LinkedIn is holding
    this post" and moved the row to scheduled while nothing left the machine.
    """
    monkeypatch.delenv("INOX_ALLOW_LINKEDIN_EGRESS", raising=False)
    # Stated rather than assumed. The sandbox is shared, and an earlier test
    # saving a session turned this into a different scenario entirely, which is
    # how it passed alone and failed in the suite.
    monkeypatch.setattr(app_module.linkedin_client, "get_tokens", lambda: {})
    post_id = _seed("nosession")

    response = _stage(post_id, scheduled_at=_future(), confirm=True)

    assert response.status_code == 409, (
        f"a mock run was reported as a real one: {response.status_code} "
        f"{response.text[:120]}"
    )
    assert "Nothing was sent" in response.json()["detail"]
    assert _row(post_id)["status"] == "draft", (
        "the post was recorded as scheduled even though nothing was sent"
    )


def test_egress_off_refuses_and_names_the_flag(monkeypatch):
    """
    With a real session present, the linkedin category still refuses by
    default, so this is the response a creator meets next. It has to tell them
    how to proceed, or the feature reads as broken.
    """
    monkeypatch.delenv("INOX_ALLOW_LINKEDIN_EGRESS", raising=False)
    # A session that does not look like a mock, so the live path is taken and
    # the egress guard is the thing that answers.
    monkeypatch.setattr(
        app_module.linkedin_client, "get_tokens",
        lambda: {"li_at": "AQEDAnotarealkey_live_shaped", "JSESSIONID": "ajax:1234567890"},
    )
    post_id = _seed("egressoff")

    response = _stage(post_id, scheduled_at=_future(), confirm=True)

    assert response.status_code == 502
    body = str(response.json()["detail"])
    assert "INOX_ALLOW_LINKEDIN_EGRESS" in body, (
        f"the refusal does not name the flag that would allow it: {body}"
    )
    assert _row(post_id)["status"] == "draft", (
        "the post was recorded as scheduled even though nothing was sent"
    )


def test_the_record_is_written_only_after_linkedin_accepts(monkeypatch):
    """
    The failure this project keeps finding in itself: a row that claims an
    action which did not happen.
    """
    monkeypatch.setattr(
        app_module.linkedin_client, "schedule_norm_share",
        lambda **kwargs: {"status": "error", "error": "LinkedIn said no"},
    )
    post_id = _seed("refused")

    response = _stage(post_id, scheduled_at=_future(), confirm=True)

    assert response.status_code == 502
    assert _row(post_id)["status"] == "draft"
    assert _row(post_id)["scheduled_for"] is None


def test_a_successful_stage_records_the_time_and_returns_the_urn(monkeypatch):
    """The happy path, with the real call replaced rather than really made."""
    monkeypatch.setattr(
        app_module.linkedin_client, "schedule_norm_share",
        lambda **kwargs: {
            "status": "success", "mode": "live",
            "scheduled_urn": "urn:li:share:7000000000000000001",
            "scheduled_at_ms": kwargs.get("scheduled_at_ms"),
        },
    )
    post_id = _seed("accepted")
    when = _future()

    response = _stage(post_id, scheduled_at=when, confirm=True)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scheduled_urn"].startswith("urn:li:share:")
    assert "LinkedIn is holding this post" in body["message"]

    row = _row(post_id)
    assert row["status"] == "scheduled"
    assert row["scheduled_for"], "the time LinkedIn was given was not recorded"


def test_the_content_sent_is_the_content_stored(monkeypatch):
    """Proves the row is the source, not the request."""
    seen = {}

    def capture(**kwargs):
        seen.update(kwargs)
        return {"status": "success", "mode": "live", "scheduled_urn": "urn:li:share:1"}

    monkeypatch.setattr(app_module.linkedin_client, "schedule_norm_share", capture)
    post_id = _seed("exact", content="The exact words in the record.")

    _stage(post_id, scheduled_at=_future(), confirm=True)

    assert seen.get("content") == "The exact words in the record."
