"""
A short link from the phone: the LinkedIn app's Copy link.
==========================================================

Found on the owner's install on 2026-10-28, against the real Telegram
service: once the chat was paired, the owner's message was accepted, but the
LinkedIn app's Copy link gives a short link, https://lnkd.in/p/<code>, with
no activity id in it. The ingress did not recognise it, so it became a draft
by the text rule and no desk request was made.

The studio never contacts LinkedIn or lnkd.in to find out where a short link
goes. So:

  1. A message with a short link in it, alone or with text around it, is a
     post sent from the phone: a desk request with the short link and no
     activity id yet, never a draft.
  2. Today shows it as "You sent a post from your phone", with Open, which
     opens the short link in the creator's browser, Done and Not now.
  3. Today opens it with #inox-desk-<request id>. A browser keeps a fragment
     across an HTTP redirect, so the post page the link lands on carries it,
     and the extension reports the request id with the post it landed on;
     the studio attaches that post to the request. Where nothing reports,
     the creator's Done completes it, never a guess.
  4. Once attached, it completes like any other request when that post's
     analytics page is read.

The Telegram side is simulated, as every ingress test is; nothing reaches the
network.

Strict Invariants:
- Zero em-dashes.
"""

import io
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

import app as app_module  # noqa: E402
import desk_requests  # noqa: E402
import ingress  # noqa: E402
from database import get_db  # noqa: E402
from ingress import IngressMessageParser, TelegramIngressDaemon  # noqa: E402

client = TestClient(app_module.app)
ME = "short-link-creator"
TOKEN = "123456789:AAFnotarealkeyZZZZZZZZZZZZZZZZZZZZZZZ"
OWNER = "487215963"
SHORT = "https://lnkd.in/p/dXyZ4bQ7"
TABLES = ("creator_identity", "own_posts", "post_metric_observations", "self_import_requests",
          "bridge_heartbeats", "captures", "desk_requests")


def urn_days_ago(days, salt=0):
    moment = datetime.now(timezone.utc) - timedelta(days=days)
    return "urn:li:activity:" + str((int(moment.timestamp() * 1000) << 22) + salt)


def _read(path):
    with io.open(os.path.join(REPO_ROOT, path), encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture(autouse=True)
def clean():
    def wipe():
        conn = get_db()
        with conn:
            for table in TABLES:
                conn.execute(f"DELETE FROM {table}")
            conn.execute("DELETE FROM posts WHERE tags LIKE '%mobile-ingress%'")
            conn.execute("DELETE FROM drafts WHERE tags LIKE '%mobile-ingress%'")
        conn.close()
    wipe()
    yield
    wipe()


def _confirm():
    client.post("/api/v1/identity/observe", json={"vanity": ME, "self_evidence": ["owner_edit_controls"],
                                                  "display_name": "Short Link Probe"})
    client.post("/api/v1/identity/confirm", json={"vanity": ME})


def _posts(*urns):
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": u, "actor": ME, "text": f"Post {i}"} for i, u in enumerate(urns)]})


def _ready_to_open():
    """Identity confirmed, bridge heard from, history read to the end, the Activity page read today."""
    _confirm()
    client.post("/api/v1/bridge/heartbeat", json={"extension_version": "test"})
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO self_import_requests (kind, requested_at, finished_at, items_seen, outcome) "
                     "VALUES ('posts', ?, ?, 5, 'end_of_list')", (datetime.now(timezone.utc).isoformat(),) * 2)
        conn.execute("INSERT INTO captures (observed_at, extractor, page_kind, items_seen, items_kept) "
                     "VALUES (?, 'activity_posts', 'in', 1, 1)", (datetime.now(timezone.utc).isoformat(),))
    conn.close()


def _read_now(urn):
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, source, "
            "impressions) VALUES (?,?,?,?,?,?)",
            (urn, datetime.now(timezone.utc).isoformat(), f"probe-now-{urn}", 24.0, "post_analytics", 500))
    conn.close()


def _daemon():
    return TelegramIngressDaemon(bot_token=TOKEN, authorized_chat_id=OWNER)


def _message(text, chat_id=OWNER, update_id=7):
    return {"update_id": update_id, "message": {"chat": {"id": int(chat_id), "type": "private"}, "text": text}}


def _requests():
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM desk_requests ORDER BY id")]
    finally:
        conn.close()


def _drafts():
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM drafts WHERE tags LIKE '%mobile-ingress%'").fetchone()[0]
    finally:
        conn.close()


def _today():
    return client.get("/api/v1/today").json()["open_next"]


def _sent_from_phone():
    """A short link sent from the phone, with the latest post read just now so nothing comes before it."""
    _ready_to_open()
    latest, older = urn_days_ago(1, 1), urn_days_ago(9, 2)
    _posts(latest, older)
    _read_now(latest)
    record = _daemon().process_incoming_update(_message(SHORT))
    return record, latest, older


# ---------------------------------------------------------------------------
# 1. The ingress recognises it: a request, never a draft
# ---------------------------------------------------------------------------

def test_a_short_link_alone_is_a_post_sent_from_the_phone():
    parsed = IngressMessageParser.parse_message(SHORT)
    assert parsed["read_request"] == {"url": SHORT, "activity_urn": None, "short_link": SHORT}
    assert parsed["raw_content"] == ""


@pytest.mark.parametrize("message", [
    f"Check out this post {SHORT}",
    f"{SHORT} this one moved overnight",
    f"idea: {SHORT} this one",
    f"Read: {SHORT}.",
    f"({SHORT})",
])
def test_a_short_link_with_text_around_it_is_still_a_request_and_never_a_draft(message):
    parsed = IngressMessageParser.parse_message(message)
    assert parsed["read_request"] and parsed["read_request"]["short_link"] == SHORT
    assert parsed["raw_content"] == "", "the text around a short link became a draft"


def test_a_short_link_keeps_its_address_and_nothing_after_it():
    parsed = IngressMessageParser.parse_message("http://LNKD.IN/p/dXyZ4bQ7?trk=public_post#top")
    assert parsed["read_request"]["short_link"] == SHORT, "the code's letters or the tracking were changed or kept"
    assert IngressMessageParser.parse_message("https://lnkd.in.example.net/p/x")["read_request"] is None


def test_a_post_link_beside_a_short_link_still_names_the_post():
    urn = urn_days_ago(1, 3)
    parsed = IngressMessageParser.parse_message(f"https://www.linkedin.com/feed/update/{urn}/ and {SHORT}")
    assert parsed["read_request"]["activity_urn"] == urn


def test_the_daemon_records_a_short_link_as_an_open_request_and_no_draft():
    _confirm()
    before = _drafts()
    record = _daemon().process_incoming_update(_message(f"Check out this post {SHORT}"))
    assert record["kind"] == "desk_request" and record["state"] == "open"
    assert record["link"] == SHORT and record["activity_urn"] == ""
    rows = _requests()
    assert len(rows) == 1 and rows[0]["link"] == SHORT and rows[0]["activity_urn"] == ""
    assert rows[0]["state"] == "open" and rows[0]["source"] == "telegram"
    assert _drafts() == before, "a short link was saved as a draft"


def test_a_short_link_polled_from_the_simulated_telegram_becomes_a_request(monkeypatch):
    """The whole path a real message takes: getUpdates answered by a fake, the paired chat, a short link."""
    _confirm()
    fetched = []

    class Answer:
        status_code = 200

        def json(self):
            return {"ok": True, "result": [_message(SHORT, update_id=41)]}

    def fake_get(url, params=None, timeout=None):
        fetched.append(url)
        return Answer()

    monkeypatch.setattr(ingress.requests, "get", fake_get)
    monkeypatch.setattr(ingress._egress, "require", lambda url, category: fetched.append(("egress", url)))
    daemon = _daemon()
    processed = daemon.poll_once()
    assert len(processed) == 1 and processed[0]["kind"] == "desk_request"
    assert all("api.telegram.org" in (u[1] if isinstance(u, tuple) else u) for u in fetched)
    assert not [u for u in fetched if "lnkd.in" in str(u)], "the studio fetched the short link"
    assert _requests()[0]["link"] == SHORT


def test_the_studio_never_contacts_lnkd_in(monkeypatch):
    """Nothing that saves or answers a short link reaches the network: every way out records instead."""
    import requests
    reached = []
    for name in ("get", "head", "post", "request"):
        monkeypatch.setattr(requests, name, lambda *a, **k: reached.append(a) or (_ for _ in ()).throw(
            AssertionError("the network was reached")))
    monkeypatch.setattr(ingress._egress, "require", lambda url, category: reached.append(url))
    record, _latest, older = _sent_from_phone()
    _today()
    client.post("/api/v1/desk-requests/landed", json={"request_id": record["id"], "activity_urn": older})
    _today()
    assert reached == []
    sources = "".join(_read(os.path.join("studio", "backend", name)) for name in
                      ("ingress.py", "desk_requests.py", "today.py", os.path.join("routers", "phone.py")))
    assert "lnkd.in" in sources and "requests.get(link" not in sources


# ---------------------------------------------------------------------------
# 2. Today offers it, to open in your browser
# ---------------------------------------------------------------------------

def test_today_offers_the_short_link_to_open_in_your_browser_with_its_fragment():
    record, _latest, _older = _sent_from_phone()
    step = _today()
    assert step["action"] == "open"
    assert step["url"] == f"{SHORT}#inox-desk-{record['id']}"
    assert step["reason"].startswith("You sent a post from your phone.")
    assert step["phone_request"]["id"] == record["id"] and step["phone_request"]["short_link"] == SHORT


def test_not_now_closes_a_short_link_request_too():
    record, _latest, _older = _sent_from_phone()
    assert client.post(f"/api/v1/desk-requests/{record['id']}/dismiss").json()["dismissed"] is True
    assert "from your phone" not in _today()["reason"]


# ---------------------------------------------------------------------------
# 3. The browser says which post it was, or the creator's Done
# ---------------------------------------------------------------------------

def test_the_landing_report_attaches_your_post_and_today_asks_for_its_analytics():
    record, _latest, older = _sent_from_phone()
    res = client.post("/api/v1/desk-requests/landed", json={"request_id": record["id"], "activity_urn": older})
    assert res.status_code == 200, res.text
    assert res.json()["attached"] is True
    row = _requests()[0]
    assert row["activity_urn"] == older and row["link"] == SHORT and row["state"] == "open"
    step = _today()
    assert step["url"] == f"https://www.linkedin.com/analytics/post-summary/{older}/"
    assert step["reason"] == "You asked from your phone to read this post's analytics."
    # 4. It completes like any other request once that post's analytics page is read.
    client.post("/api/v1/self/posts/analytics", json={"author": ME, "activity_urn": older,
                                                      "metrics": {"impressions": 1200, "reactions": 30}})
    assert "from your phone" not in _today()["reason"]
    assert _requests()[0]["state"] == "read"


def test_a_landing_on_a_post_that_is_not_yours_refuses_the_request():
    record, _latest, _older = _sent_from_phone()
    stranger = urn_days_ago(3, 9)
    res = client.post("/api/v1/desk-requests/landed", json={"request_id": record["id"], "activity_urn": stranger})
    assert res.json()["attached"] is False
    row = _requests()[0]
    assert row["state"] == "refused" and row["note"] == desk_requests.NOT_YOURS and row["activity_urn"] == stranger
    assert "from your phone" not in _today()["reason"]


def test_a_landing_that_names_no_activity_is_not_guessed_at():
    record, _latest, older = _sent_from_phone()
    share = "urn:li:share:" + older.rsplit(":", 1)[1]
    res = client.post("/api/v1/desk-requests/landed", json={"request_id": record["id"], "activity_urn": share})
    assert res.json()["attached"] is False
    row = _requests()[0]
    assert row["state"] == "open" and row["activity_urn"] == "", "a post was attached from an id that names none"
    assert _today()["reason"].startswith("You sent a post from your phone.")


@pytest.mark.parametrize("body", [
    {"request_id": "1; DROP TABLE desk_requests", "activity_urn": "urn:li:activity:1"},
    {"request_id": 1},
    {"activity_urn": "urn:li:activity:1"},
])
def test_a_landing_report_of_the_wrong_shape_is_refused(body):
    assert client.post("/api/v1/desk-requests/landed", json=body).status_code == 422


def test_a_landing_report_moves_only_a_short_link_still_waiting_for_its_post():
    record, latest, older = _sent_from_phone()
    conn = get_db()
    full = desk_requests.record(conn, older)
    conn.close()
    # A request made from a full link already names its post.
    assert client.post("/api/v1/desk-requests/landed",
                       json={"request_id": full["id"], "activity_urn": latest}).json()["attached"] is False
    client.post(f"/api/v1/desk-requests/{record['id']}/dismiss")
    assert client.post("/api/v1/desk-requests/landed",
                       json={"request_id": record["id"], "activity_urn": older}).json()["attached"] is False
    assert client.post("/api/v1/desk-requests/landed",
                       json={"request_id": 999999, "activity_urn": older}).json()["attached"] is False
    rows = {r["id"]: r for r in _requests()}
    assert rows[full["id"]]["activity_urn"] == older and rows[record["id"]]["activity_urn"] == ""


def test_done_completes_a_short_link_request_by_the_creators_press():
    record, _latest, older = _sent_from_phone()
    res = client.post(f"/api/v1/desk-requests/{record['id']}/done")
    assert res.status_code == 200 and res.json()["done"] is True
    row = _requests()[0]
    assert row["state"] == "done" and row["done_at"] and row["activity_urn"] == ""
    assert "from your phone" not in _today()["reason"]
    assert client.post(f"/api/v1/desk-requests/{record['id']}/done").json()["done"] is False
    conn = get_db()
    full = desk_requests.record(conn, older)
    conn.close()
    assert client.post(f"/api/v1/desk-requests/{full['id']}/done").json()["done"] is False, (
        "a request that names its post is done when that post is read, not by a press")


def test_a_short_link_request_unread_for_a_week_is_closed_like_any_other():
    _record, _latest, _older = _sent_from_phone()
    conn = get_db()
    with conn:
        conn.execute("UPDATE desk_requests SET asked_at = ?",
                     ((datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),))
    conn.close()
    assert "from your phone" not in _today()["reason"]
    assert _requests()[0]["state"] == "expired"


def test_the_panel_lists_a_short_link_by_its_address_with_what_waits():
    _sent_from_phone()
    link = client.get("/api/v1/ingress/settings").json()["recent_links"][0]
    assert link["link"] == SHORT and link["activity_urn"] == "" and link["state"] == "open"
    assert link["said"].startswith("Waiting: Today asks you to open the link")


# ---------------------------------------------------------------------------
# Opening it, and what the extension may say
# ---------------------------------------------------------------------------

def test_the_launcher_opens_a_short_link_with_its_fragment_and_nothing_like_it():
    import browser_launcher
    url = f"{SHORT}#inox-desk-12"
    assert browser_launcher._validated_target(url) == url
    for refused in ("http://lnkd.in/p/dXyZ4bQ7", "https://lnkd.in.example.net/p/x", "https://example.com/lnkd.in"):
        assert browser_launcher._validated_target(refused) == browser_launcher.DEFAULT_TARGET_URL
    # A running bridge browser is asked over its DevTools port, where a bare #
    # would end the request's address: the fragment goes encoded.
    assert browser_launcher._devtools_new_path(url).endswith("lnkd.in/p/dXyZ4bQ7%23inox-desk-12")


def test_the_extension_may_report_a_landing_and_asks_no_new_permission():
    background = _read("studio/extension/background.js")
    relayable = background[background.index("const RELAYABLE_PATHS"):background.index("]);", background.index(
        "const RELAYABLE_PATHS"))]
    assert '"/api/v1/desk-requests/landed"' in relayable
    manifest = json.loads(_read("studio/extension/manifest.json"))
    every = json.dumps({k: manifest.get(k) for k in ("permissions", "host_permissions", "content_scripts")})
    assert "lnkd.in" not in every, "the extension was given lnkd.in"
    content = _read("studio/extension/content.js")
    assert "inox-desk-" in content and "/api/v1/desk-requests/landed" in content


def test_the_help_says_the_apps_copy_link_gives_a_short_link_and_how_it_is_completed():
    article = " ".join(_read("docs/help/send-a-post-idea-from-telegram.md").split())
    assert "Copy link" in article and "lnkd.in" in article
    assert "You sent a post from your phone" in article and "**Done**" in article
    assert "never fetches" in article or "never contacts" in article
