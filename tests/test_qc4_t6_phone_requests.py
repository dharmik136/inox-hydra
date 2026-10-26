"""
A post link shared from the phone becomes a desk request Today surfaces.
========================================================================

Programme item 24 of the capture report, built on what exists: the Telegram
ingress parses the message, post_identity reads the activity URN out of the
link, the request is one row in desk_requests, and Today's one page to open
answers it ahead of the latest-post rule. The request is done once that
post's own analytics page has been read after it was asked, and closed with
a note after a week unread.

The phone sends a link, never a figure: nothing here writes a reading.

Strict Invariants:
- Zero em-dashes.
- The Telegram side is simulated, as every ingress test is; nothing reaches
  the network.
"""

import io
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

import app as app_module  # noqa: E402
import desk_requests  # noqa: E402
import today  # noqa: E402
from database import get_db  # noqa: E402
from ingress import IngressMessageParser, TelegramIngressDaemon  # noqa: E402

client = TestClient(app_module.app)
ME = "phone-probe-creator"
TOKEN = "123456789:AAFnotarealkeyZZZZZZZZZZZZZZZZZZZZZZZ"
OWNER = "555000111"
TABLES = ("creator_identity", "own_posts", "post_metric_observations", "self_import_requests",
          "bridge_heartbeats", "captures", "desk_requests")


def urn_days_ago(days, salt=0):
    moment = datetime.now(timezone.utc) - timedelta(days=days)
    return "urn:li:activity:" + str((int(moment.timestamp() * 1000) << 22) + salt)


def share_link(urn):
    """What the LinkedIn app's share menu writes, tracking parameters included."""
    return f"https://www.linkedin.com/posts/someone_slug-activity-{urn.rsplit(':', 1)[1]}-AbCd?utm_source=share&utm_medium=android_app"


@pytest.fixture(autouse=True)
def clean():
    def wipe():
        conn = get_db()
        with conn:
            for table in TABLES:
                conn.execute(f"DELETE FROM {table}")
            conn.execute("DELETE FROM posts WHERE id IN (SELECT CAST(id AS TEXT) FROM drafts WHERE tags LIKE '%mobile-ingress%')")
            conn.execute("DELETE FROM posts WHERE tags LIKE '%mobile-ingress%'")
            conn.execute("DELETE FROM drafts WHERE tags LIKE '%mobile-ingress%'")
        conn.close()
    wipe()
    yield
    wipe()


def _confirm():
    client.post("/api/v1/identity/observe", json={"vanity": ME, "self_evidence": ["owner_edit_controls"],
                                                  "display_name": "Phone Probe"})
    client.post("/api/v1/identity/confirm", json={"vanity": ME})


def _posts(*urns):
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": u, "actor": ME, "text": f"Post {i}"} for i, u in enumerate(urns)]})


def _ready_to_open():
    """Identity confirmed, bridge heard from, history read to the end: the open rules apply."""
    _confirm()
    client.post("/api/v1/bridge/heartbeat", json={"extension_version": "test"})
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO self_import_requests (kind, requested_at, finished_at, items_seen, outcome) "
                     "VALUES ('posts', ?, ?, 5, 'end_of_list')", (datetime.now(timezone.utc).isoformat(),) * 2)
    conn.close()


def _daemon():
    return TelegramIngressDaemon(bot_token=TOKEN, authorized_chat_id=OWNER)


def _message(text, chat_id=OWNER):
    return {"update_id": 7, "message": {"chat": {"id": chat_id}, "text": text}}


def _requests():
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM desk_requests ORDER BY id")]
    finally:
        conn.close()


def _drafts_tagged_mobile():
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM drafts WHERE tags LIKE '%mobile-ingress%'").fetchone()[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# The parser reads the link
# ---------------------------------------------------------------------------

def test_a_share_menu_link_names_the_post():
    urn = urn_days_ago(1, 3)
    parsed = IngressMessageParser.parse_message(share_link(urn))
    assert parsed["read_request"] == {"url": share_link(urn), "activity_urn": urn}
    assert parsed["raw_content"] == "", "a link alone is not a draft"


def test_the_read_prefix_and_a_feed_link_are_read_too():
    urn = urn_days_ago(1, 4)
    parsed = IngressMessageParser.parse_message(f"Read: https://www.linkedin.com/feed/update/{urn}/")
    assert parsed["read_request"]["activity_urn"] == urn
    assert "read" in parsed["tags"]
    assert parsed["raw_content"] == ""


def test_text_beside_the_link_is_kept_without_the_link():
    urn = urn_days_ago(1, 5)
    parsed = IngressMessageParser.parse_message(f"Look at this one {share_link(urn)} it moved overnight")
    assert parsed["read_request"]["activity_urn"] == urn
    assert parsed["raw_content"] == "Look at this one it moved overnight"


def test_a_short_link_names_nothing_and_the_text_is_kept_whole():
    parsed = IngressMessageParser.parse_message("idea: https://lnkd.in/abc123 this one")
    assert parsed["read_request"] is None
    assert parsed["raw_content"] == "https://lnkd.in/abc123 this one"


def test_a_profile_link_is_not_a_post():
    parsed = IngressMessageParser.parse_message("https://www.linkedin.com/in/someone/")
    assert parsed["read_request"] is None
    assert parsed["raw_content"] == "https://www.linkedin.com/in/someone/"


# ---------------------------------------------------------------------------
# The daemon records the request
# ---------------------------------------------------------------------------

def test_a_link_to_your_own_post_becomes_a_request_and_no_draft():
    _confirm()
    urn = urn_days_ago(1, 6)
    _posts(urn)
    before = _drafts_tagged_mobile()
    record = _daemon().process_incoming_update(_message(share_link(urn)))
    assert record["kind"] == "desk_request" and record["activity_urn"] == urn and record["known_post"]
    rows = _requests()
    assert len(rows) == 1 and rows[0]["activity_urn"] == urn and rows[0]["done_at"] is None
    assert rows[0]["note"] is None and rows[0]["source"] == "telegram"
    assert _drafts_tagged_mobile() == before, "a link alone was saved as a draft"


def test_a_link_to_a_post_the_studio_does_not_hold_carries_the_refusal_sentence():
    urn = urn_days_ago(1, 7)
    record = _daemon().process_incoming_update(_message(share_link(urn)))
    assert record["known_post"] is False
    assert _requests()[0]["note"] == desk_requests.UNKNOWN_POST


def test_text_with_the_link_is_still_a_draft():
    _confirm()
    urn = urn_days_ago(1, 8)
    _posts(urn)
    before = _drafts_tagged_mobile()
    record = _daemon().process_incoming_update(_message(f"Draft: this did well {share_link(urn)}"))
    assert record["desk_request"]["activity_urn"] == urn
    assert record["raw_content"] == "this did well"
    assert _drafts_tagged_mobile() == before + 1
    assert len(_requests()) == 1


def test_the_refusal_sentence_is_the_one_the_reading_uses():
    with io.open(os.path.join(REPO_ROOT, "studio", "backend", "onboarding.py"), encoding="utf-8") as handle:
        assert desk_requests.UNKNOWN_POST in handle.read()


def test_the_simulate_route_carries_a_link_too(monkeypatch):
    monkeypatch.setenv("INOX_DEV_MODE", "1")
    _confirm()
    urn = urn_days_ago(1, 9)
    _posts(urn)
    res = client.post("/api/v1/ingress/simulate", json={"text": share_link(urn)})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "success"
    assert res.json()["record"]["kind"] == "desk_request"
    assert len(_requests()) == 1


# ---------------------------------------------------------------------------
# Today answers it
# ---------------------------------------------------------------------------

def _today():
    return client.get("/api/v1/today").json()


def test_today_offers_the_requested_post_ahead_of_the_latest_post_rule():
    _ready_to_open()
    latest, older = urn_days_ago(1, 10), urn_days_ago(9, 11)
    _posts(latest, older)
    conn = get_db()
    desk_requests.record(conn, older)
    conn.close()
    step = _today()["open_next"]
    assert step["action"] == "open"
    assert step["url"] == f"https://www.linkedin.com/analytics/post-summary/{older}/"
    assert "from your phone" in step["reason"]
    assert step["phone_request"]["activity_urn"] == older


def test_the_request_is_done_once_that_post_is_read_at_the_desk():
    _ready_to_open()
    latest, older = urn_days_ago(1, 12), urn_days_ago(9, 13)
    _posts(latest, older)
    conn = get_db()
    desk_requests.record(conn, older)
    conn.close()
    assert "from your phone" in _today()["open_next"]["reason"]
    # The extension reads the post's own analytics page, as it does at the desk.
    res = client.post("/api/v1/self/posts/analytics", json={"author": ME, "activity_urn": older,
                                                            "metrics": {"impressions": 1200, "reactions": 30}})
    assert res.status_code == 200, res.text
    step = _today()["open_next"]
    assert "from your phone" not in step["reason"]
    rows = _requests()
    assert rows[0]["done_at"] is not None and rows[0]["note"] is None


def test_a_reading_from_before_the_request_does_not_settle_it():
    _ready_to_open()
    latest, older = urn_days_ago(1, 14), urn_days_ago(9, 15)
    _posts(latest, older)
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, source, "
            "impressions) VALUES (?,?,?,?,?,?)",
            (older, (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(), "probe-before", 200.0,
             "post_analytics", 900))
    desk_requests.record(conn, older)
    conn.close()
    assert "from your phone" in _today()["open_next"]["reason"]


def test_a_post_the_studio_does_not_hold_sends_you_to_setup_with_the_reason():
    _ready_to_open()
    _posts(urn_days_ago(1, 16))
    conn = get_db()
    desk_requests.record(conn, urn_days_ago(3, 17))
    conn.close()
    step = _today()["open_next"]
    assert step["action"] == "setup"
    assert desk_requests.UNKNOWN_POST in step["reason"] and "from your phone" in step["reason"]


def test_a_request_unread_for_a_week_is_closed_with_a_note():
    _ready_to_open()
    latest, older = urn_days_ago(1, 18), urn_days_ago(20, 19)
    _posts(latest, older)
    conn = get_db()
    desk_requests.record(conn, older)
    with conn:
        conn.execute("UPDATE desk_requests SET asked_at = ?",
                     ((datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),))
    conn.close()
    step = _today()["open_next"]
    assert "from your phone" not in step["reason"]
    rows = _requests()
    assert rows[0]["done_at"] is not None and desk_requests.EXPIRED_NOTE in rows[0]["note"]


def test_the_rule_is_what_surfaces_it(monkeypatch):
    """Falsified: with the rule answering None, the latest-post rule answers as before."""
    _ready_to_open()
    latest, older = urn_days_ago(1, 20), urn_days_ago(9, 21)
    _posts(latest, older)
    conn = get_db()
    desk_requests.record(conn, older)
    conn.close()
    monkeypatch.setattr(today, "_phone_request_rule", lambda conn: None)
    step = _today()["open_next"]
    assert step["url"].endswith(f"/analytics/post-summary/{latest}/")


def test_setup_blocks_still_come_first():
    """Before the identity is confirmed, a request cannot send anyone to a page."""
    conn = get_db()
    desk_requests.record(conn, urn_days_ago(2, 22))
    conn.close()
    assert _today()["open_next"]["action"] == "setup"
    assert "from your phone" not in _today()["open_next"]["reason"]


def test_the_analytics_url_is_the_one_the_latest_post_rule_builds():
    urn = urn_days_ago(2, 23)
    assert desk_requests.analytics_url(urn) == f"https://www.linkedin.com/analytics/post-summary/{urn}/"
    assert desk_requests.analytics_url("local:draft-1") is None
