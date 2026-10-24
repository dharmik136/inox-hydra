"""
Send to LinkedIn: the one-time account-risk acknowledgement (cycle 3, D2).
=========================================================================

The owner's decision for cycle 3 was to keep Send to LinkedIn and say plainly
what it does. It POSTs a scheduled share to LinkedIn's private, undocumented
`contentcreation/normShares` endpoint with the member's own session cookies,
which is the highest terms of service exposure in the product, while
`docs/ARCHITECTURE.md` claimed "Zero automated bot activity". The docs are
corrected, the risk register names the path, and the code half is this: before
the first send on an installation, the creator acknowledges that risk once.

What this is not: the per-send confirmation. `StagePostRequest.confirm` and
`confirm_account` already ask on every send, and they name the account and the
time, not the risk. This gate is separate, is asked once per installation
rather than once per send, and is recorded, so an owner or a reviewer can see
that it was answered and when.

The suite's sandbox is an installation that has already answered it (see
tests/conftest.py), so every other test about what gates a send still tests
that. These tests clear the row to meet the gate itself, and put it back
afterwards so nothing that runs later inherits an unacknowledged install.
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

PREFIX = "qc3t8-ack-"
# Named here rather than read from the module, so that a build without the gate
# fails these tests on their own assertions rather than on a missing attribute.
ACK_KEY = "linkedin_send_risk_ack"
# The words themselves, which are the deliverable here: the same sentence is in
# the risk register, docs/ARCHITECTURE.md, the privacy policy's LinkedIn row in
# summary, and the prompt the creator answers.
RISK_SENTENCE = (
    "Send to LinkedIn writes to LinkedIn's private, undocumented scheduling API, a use "
    "outside LinkedIn's published terms, and it could affect your account's standing if "
    "LinkedIn's systems treat it as automation."
)
ACCOUNT = {
    "vanity": "t8-creator",
    "member_urn": "urn:li:fsd_profile:ACoAAT8CREATOR001",
    "saved_at": "2026-10-23T00:00:00+00:00",
}


@pytest.fixture(autouse=True)
def ready_to_send(monkeypatch):
    """Everything except the acknowledgement already satisfied."""
    monkeypatch.setattr(app_module.linkedin_client, "session_account", lambda: dict(ACCOUNT))
    monkeypatch.setattr(app_module.linkedin_client, "is_authenticated", lambda: True)
    monkeypatch.setattr(app_module.onboarding, "confirmed_vanity", lambda: "t8-creator")
    monkeypatch.setenv("INOX_ALLOW_LINKEDIN_EGRESS", "1")
    monkeypatch.delenv("INOX_NO_EGRESS", raising=False)
    # Nothing in this file reaches LinkedIn: the client is replaced, so a test
    # that got past the gate records a send without one leaving the machine.
    monkeypatch.setattr(
        app_module.linkedin_client, "schedule_norm_share",
        lambda **kwargs: {"status": "success", "mode": "live", "scheduled_urn": "urn:li:share:7200000000000000001"},
    )


@pytest.fixture(autouse=True)
def fresh_install():
    """
    An installation that has not acknowledged anything, restored afterwards.

    The row is what the gate reads, so clearing it is what makes this a first
    use. It is restored rather than left cleared, because the sandbox database
    is shared with every other test in the session.
    """
    before = _acknowledged_at()
    _forget_acknowledgement()
    yield
    _forget_acknowledgement()
    if before:
        conn = get_db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (ACK_KEY, before),
            )
            conn.commit()
        finally:
            conn.close()
    conn = get_db()
    try:
        conn.execute("DELETE FROM posts WHERE id LIKE ?", (PREFIX + "%",))
        conn.execute("DELETE FROM settings WHERE key LIKE ?", ("%" + PREFIX + "%",))
        conn.commit()
    finally:
        conn.close()


def _acknowledged_at():
    """What the installation has on record, read as the gate reads it."""
    conn = get_db()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (ACK_KEY,)).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def _forget_acknowledgement():
    conn = get_db()
    try:
        conn.execute("DELETE FROM settings WHERE key = ?", (ACK_KEY,))
        conn.commit()
    finally:
        conn.close()


def _seed(name, content="A post the creator approved for LinkedIn."):
    conn = get_db()
    try:
        conn.execute("INSERT OR REPLACE INTO posts (id, content, status) VALUES (?,?,'draft')", (PREFIX + name, content))
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


def _future(hours=6):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _send(post_id, **extra):
    return client.post(
        f"/api/v1/posts/{post_id}/stage-to-linkedin",
        json={"scheduled_at": _future(), "confirm": True, "confirm_account": "t8-creator", **extra},
    )


def _acknowledge(**body):
    return client.post("/api/v1/linkedin/risk-ack", json=body)


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def test_the_first_send_is_refused_until_the_risk_is_acknowledged():
    """
    The defect this exists for: everything else was ready and the post went to
    LinkedIn's private API without the creator ever being told that is what it
    is. A per-send confirmation naming the account and the time is not that.
    """
    post_id = _seed("firstsend")

    response = _send(post_id)

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "risk_not_acknowledged"
    assert _row(post_id)["status"] == "draft", "the post was staged without the acknowledgement"


def test_the_refusal_names_the_account_risk_itself():
    """
    The words matter, not just the refusal. The register, the architecture
    document and this sentence have to say the same thing, so a creator who
    reads one of them has read all three.
    """
    post_id = _seed("words")

    detail = _send(post_id).json()["detail"]["message"]

    assert detail == RISK_SENTENCE
    assert app_module.LINKEDIN_SEND_RISK_SENTENCE == RISK_SENTENCE, (
        "the backend's sentence and the one the documents quote have drifted apart"
    )
    assert "private" in detail and "undocumented" in detail
    assert "outside LinkedIn's published terms" in detail
    assert "account's standing" in detail
    assert "automation" in detail


def test_readiness_says_so_before_the_creator_presses_send():
    """
    The dialog greys the button out and shows the reason, rather than letting
    a creator press Send and meet a refusal. So readiness carries the code and
    the sentence for a post that is otherwise ready to go.
    """
    state = client.get(f"/api/v1/posts/{PREFIX}none/linkedin-send").json()

    assert state["ready"] is False
    assert state["code"] == "risk_not_acknowledged"
    assert state["reason"] == RISK_SENTENCE
    # Still names the account, so the dialog can say who it would send as.
    assert state["account"]["vanity"] == "t8-creator"


def test_an_acknowledgement_that_acknowledges_nothing_is_refused():
    """A default is not consent: the field has to be sent, and sent true."""
    assert _acknowledge().status_code == 400
    assert _acknowledge(acknowledge=False).status_code == 400
    assert _acknowledged_at() is None, "nothing was acknowledged, and something was recorded"


def test_acknowledging_is_recorded_with_when():
    """
    Recorded, not merely allowed. The owner testing on a real account, and
    anyone auditing the install later, can see that it was answered and when.
    """
    response = _acknowledge(acknowledge=True)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["acknowledged"] is True
    at = _acknowledged_at()
    assert at == body["at"]
    assert datetime.fromisoformat(at) <= datetime.now(timezone.utc), "the record is in the future"


def test_once_acknowledged_the_send_goes_through():
    post_id = _seed("afterack")
    _acknowledge(acknowledge=True)

    response = _send(post_id)

    assert response.status_code == 200, response.text
    assert _row(post_id)["status"] == "scheduled"


def test_it_is_asked_once_per_installation_not_once_per_send():
    """
    A gate asked on every send would be a second confirmation dialog, which is
    not what was decided and is how a warning becomes furniture. Two posts,
    one acknowledgement.
    """
    _acknowledge(acknowledge=True)
    acknowledged_at = _acknowledged_at()

    first = _send(_seed("one"))
    second = _send(_seed("two"))

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert client.get(f"/api/v1/posts/{PREFIX}one/linkedin-send").json()["ready"] is True
    assert _acknowledged_at() == acknowledged_at, "the acknowledgement was asked for again"


def test_the_per_send_confirmation_is_still_required_as_well():
    """
    This gate is in addition to the per-send confirmation, never instead of
    it. An acknowledged installation still cannot send without confirming the
    account and the time for this post.
    """
    post_id = _seed("stillconfirms")
    _acknowledge(acknowledge=True)

    unconfirmed = client.post(
        f"/api/v1/posts/{post_id}/stage-to-linkedin",
        json={"scheduled_at": _future(), "confirm_account": "t8-creator"},
    )

    assert unconfirmed.status_code == 400
    assert "cannot be undone" in unconfirmed.json()["detail"]
    assert _row(post_id)["status"] == "draft"


# ---------------------------------------------------------------------------
# The sentence is one sentence, in one place
# ---------------------------------------------------------------------------

def _repo_file(*parts):
    path = os.path.join(os.path.dirname(__file__), "..", *parts)
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def test_the_documents_name_the_same_risk_as_the_code():
    """
    The reason this batch exists. ARCHITECTURE.md claimed zero automated
    activity while this shipped, and the risk register did not name the path
    at all. If either stops naming it, this fails.
    """
    architecture = _repo_file("docs", "ARCHITECTURE.md")
    register = _repo_file("planning", "7 Roadmap", "Risk - LinkedIn terms and detection.md")

    assert "Zero automated bot activity" not in architecture
    for document in (architecture, register):
        assert "schedule_norm_share" in document
        assert "private" in document
        assert "published terms" in document
        assert "standing" in document
    assert "Risk - LinkedIn terms and detection.md" in architecture, (
        "the architecture document does not point at the risk register"
    )


def test_the_extension_document_does_not_claim_the_scripts_never_click():
    """
    `own_pages.js` clicks LinkedIn's load-more control and scrolls for up to
    250 rounds during a history import. The document said they never click.
    """
    extension_doc = _repo_file("docs", "EXTENSION_AND_SYNC.md")

    assert "They never click, type" not in extension_doc, "the unconditional claim is back"
    assert "Outside the one exception below, they never click" in extension_doc
    assert "250 rounds" in extension_doc
    assert "Import your history" in extension_doc
