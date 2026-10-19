"""
Quality cycle 2026-10, batch F4b: history imports and Sync All.
==============================================================

SETUP-14. An import request older than 30 minutes is never picked up by the
extension, but Setup showed it as WAITING FOR THE PAGE TO OPEN forever.

SETUP-16. Sync All's chain lived only in server memory, so a studio restart
in the middle of an import dropped the comments and reactions steps without
a word.

SETUP-11 and SETUP-22. Sync All said "Autonomous activity sync started"
whether or not a browser opened, and the launcher's messages named Chrome as
supported, said "this PC" on a Mac, and pointed at a path Setup never showed.
"""

import importlib
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module
import onboarding
from database import get_db

client = TestClient(app_module.app)

ME = "sample-frank"


def _wipe():
    conn = get_db()
    try:
        with conn:
            for table in ("creator_identity", "own_posts", "self_import_requests", "outbound_engagements",
                          "bridge_heartbeats"):
                conn.execute(f"DELETE FROM {table}")
            conn.execute("DELETE FROM settings WHERE key IN ('creator_profile', 'identity_filled_profile', "
                         "'history_sync_chain')")
    finally:
        conn.close()
    onboarding.cancel_sync_chain()


@pytest.fixture(autouse=True)
def clean():
    _wipe()
    yield
    _wipe()


def _confirm():
    client.post("/api/v1/identity/observe", json={"vanity": ME, "display_name": "Sample Frank",
                                                  "self_evidence": ["owner_edit_controls"]})
    assert client.post("/api/v1/identity/confirm", json={"vanity": ME}).status_code == 200


def _imports():
    return {i["id"]: i for i in client.get("/api/v1/onboarding/state").json()["imports"]}


def _age(request_id, minutes):
    conn = get_db()
    with conn:
        conn.execute("UPDATE self_import_requests SET requested_at = ? WHERE id = ?",
                     ((datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat(), request_id))
    conn.close()


# ---------------------------------------------------------------------------
# SETUP-14
# ---------------------------------------------------------------------------

def test_a_request_the_extension_will_no_longer_take_says_it_expired():
    _confirm()
    request_id = client.post("/api/v1/self/imports", json={"kind": "posts"}).json()["id"]
    _age(request_id, 31)

    assert client.post("/api/v1/self/imports/pending", json={"kind": "posts"}).json()["request"] is None
    entry = _imports()[request_id]
    assert entry["outcome"] == "expired"
    assert entry["finished_at"] is not None


def test_a_recent_request_is_still_waiting():
    _confirm()
    request_id = client.post("/api/v1/self/imports", json={"kind": "posts"}).json()["id"]
    _age(request_id, 5)
    entry = _imports()[request_id]
    assert entry["finished_at"] is None and entry["outcome"] is None


def test_an_import_already_scrolling_is_not_expired_under_it():
    _confirm()
    request_id = client.post("/api/v1/self/imports", json={"kind": "posts"}).json()["id"]
    client.post("/api/v1/self/imports/event", json={"id": request_id, "event": "started"})
    _age(request_id, 45)
    assert _imports()[request_id]["finished_at"] is None
    client.post("/api/v1/self/imports/event", json={"id": request_id, "event": "finished",
                                                    "items_seen": 30, "outcome": "end_of_list"})
    assert _imports()[request_id]["outcome"] == "end_of_list"


# ---------------------------------------------------------------------------
# SETUP-16
# ---------------------------------------------------------------------------

def _take(kind):
    request = client.post("/api/v1/self/imports/pending", json={"kind": kind}).json()["request"]
    assert request is not None, f"no {kind} import is waiting"
    client.post("/api/v1/self/imports/event", json={"id": request["id"], "event": "started"})
    return request["id"]


def _finish(request_id, outcome="end_of_list"):
    return client.post("/api/v1/self/imports/event", json={
        "id": request_id, "event": "finished", "items_seen": 20, "outcome": outcome}).json()


def test_the_chain_carries_on_after_the_studio_restarts():
    _confirm()
    onboarding.start_sync_chain()
    posts_id = _take("posts")

    importlib.reload(onboarding)  # the studio restarts while posts are scrolling

    finished = _finish(posts_id)
    assert finished.get("next_kind") == "comments", finished
    assert "recent-activity/comments" in finished["next_url"]
    assert client.get("/api/v1/onboarding/state").json()["sync_chain"]["current_kind"] == "comments"

    importlib.reload(onboarding)
    assert _finish(_take("comments")).get("next_kind") == "reactions"
    assert _finish(_take("reactions")).get("all_completed") is True
    assert onboarding.get_active_sync_chain() is None
    assert client.get("/api/v1/onboarding/state").json()["sync_chain"] is None


def test_stopping_or_a_single_import_ends_the_chain():
    _confirm()
    onboarding.start_sync_chain()
    _finish(_take("posts"), outcome="stopped")
    assert onboarding.get_active_sync_chain() is None

    onboarding.start_sync_chain()
    client.post("/api/v1/self/imports", json={"kind": "reactions"})
    assert onboarding.get_active_sync_chain() is None


def _launcher(monkeypatch, result):
    """Sync All's launcher, replaced: what it would have reported, and nothing opened."""
    launched = []

    def fake(browser_id="auto", target_url=""):
        launched.append(target_url)
        return dict(result, target_url=target_url)

    monkeypatch.setattr(app_module.browser_router_module, "launch_browser_with_extension", fake)
    return launched


def _bridge_heard_from():
    client.post("/api/v1/bridge/heartbeat", json={"extension_version": "test", "page_kind": "feed"})


NO_BROWSER = {"status": "error", "message": "No Chromium browser was found on this computer."}
CHROME_ONLY = {"status": "success", "browser": "Google Chrome", "browser_id": "chrome", "carries_extension": False,
               "message": "Launched Google Chrome, but it ignores --load-extension."}
BRAVE = {"status": "success", "browser": "Brave Browser", "browser_id": "brave", "carries_extension": True,
         "message": "Launched Brave Browser with the bridge loaded."}


@pytest.mark.parametrize("launch", [NO_BROWSER, CHROME_ONLY], ids=["no_browser", "chrome_only"])
def test_sync_all_never_says_started_when_nothing_can_start(monkeypatch, launch):
    _confirm()
    _launcher(monkeypatch, launch)
    response = client.post("/api/v1/self/sync-all")
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert "started" not in detail.lower()
    assert "nothing was imported" in detail.lower()
    assert onboarding.get_active_sync_chain() is None
    waiting = [i for i in _imports().values() if not i["finished_at"]]
    assert waiting == [], "a request is left waiting for a page that will not open"


def test_chrome_with_the_bridge_running_elsewhere_says_where_to_go(monkeypatch):
    _confirm()
    _bridge_heard_from()
    _launcher(monkeypatch, CHROME_ONLY)
    response = client.post("/api/v1/self/sync-all")
    assert response.status_code == 200
    body = response.json()
    assert "cannot load the bridge" in body["message"]
    assert onboarding.get_active_sync_chain() is not None


def test_sync_all_says_what_it_opened_and_in_which_order(monkeypatch):
    _confirm()
    launched = _launcher(monkeypatch, BRAVE)
    body = client.post("/api/v1/self/sync-all", json={"sequence": ["comments", "posts"]}).json()
    assert body["status"] == "success"
    assert launched and "recent-activity/comments" in launched[0]
    message = body["message"]
    assert "Brave Browser" in message
    assert message.index("comments") < message.index("posts")
    assert "reactions" not in message
    # The bridge has not reported in, so the import has not begun yet.
    assert "starts when the bridge reports in" in message


@pytest.fixture
def launcher(monkeypatch, tmp_path, no_real_browser):
    import browser_launcher
    monkeypatch.setattr(browser_launcher, "get_browser_profile_dir", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(browser_launcher, "_try_open_in_running_browser", lambda *a, **k: None)
    return browser_launcher


def test_with_no_browser_the_launcher_says_what_to_install(launcher, monkeypatch, no_real_browser):
    monkeypatch.setattr(launcher, "detect_installed_browsers", lambda: {})
    result = launcher.launch_browser_with_extension("auto", "https://www.linkedin.com/feed/")
    assert result["status"] == "error"
    message = result["message"]
    assert "this PC" not in message and "this computer" in message
    assert "nothing opened" in message.lower()
    assert "Chrome, Edge" not in message, "Chrome was named as a supported browser, and it cannot load the bridge"
    assert "Edge" in message and "Brave" in message
    assert no_real_browser.launched == []


def test_with_only_chrome_the_launcher_names_the_folder_to_load(launcher, monkeypatch, no_real_browser):
    monkeypatch.setattr(launcher, "detect_installed_browsers", lambda: {
        "chrome": {"id": "chrome", "name": "Google Chrome", "path": "/nonexistent/chrome",
                   "is_available": True, "carries_extension": False}})
    result = launcher.launch_browser_with_extension("auto", "https://www.linkedin.com/feed/")
    assert result["carries_extension"] is False
    assert "path below" not in result["message"], "Setup shows no path below the message"
    assert launcher.get_extension_dir() in result["message"]
    assert len(no_real_browser.launched) == 1  # recorded by the stand-in, nothing started


def test_a_chain_whose_request_expired_is_over():
    _confirm()
    onboarding.start_sync_chain()
    request_id = client.get("/api/v1/onboarding/state").json()["imports"][0]["id"]
    _age(request_id, 31)
    assert client.get("/api/v1/onboarding/state").json()["sync_chain"] is None
