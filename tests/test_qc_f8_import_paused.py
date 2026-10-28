"""
Quality cycle 2026-10, batch F8 [SETUP-15 rest]: an import paused because its
LinkedIn tab is hidden says so in Setup.

own_pages.js runImport waits while its tab is hidden (a hidden tab does not
scroll), and the launcher opens the studio as a tab beside LinkedIn, so
reading Setup is exactly what pauses it. Setup went on saying SCROLLING NOW
for an import that was not moving. Now the extension reports "paused" and
"resumed" through the import event, the studio holds that on the open
request, and Setup says it is paused and that the tab must be in front.
"""

import os
import socket
import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module  # noqa: E402
import onboarding  # noqa: E402
from database import get_db  # noqa: E402

client = TestClient(app_module.app)
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ME = "test-creator"


def _wipe():
    conn = get_db()
    try:
        with conn:
            for table in ("creator_identity", "self_import_requests", "settings_sync_probe"):
                try:
                    conn.execute(f"DELETE FROM {table}")
                except Exception:
                    pass
            conn.execute("DELETE FROM settings WHERE key IN ('creator_profile', 'identity_filled_profile', "
                         "'sync_chain', 'self_sync_chain')")
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def clean():
    _wipe()
    yield
    _wipe()


def _confirm():
    client.post("/api/v1/identity/observe", json={"vanity": ME, "display_name": "Test Creator",
                                                  "self_evidence": ["owner_edit_controls"]})
    assert client.post("/api/v1/identity/confirm", json={"vanity": ME}).status_code == 200


def _started_import():
    request_id = client.post("/api/v1/self/imports", json={"kind": "posts"}).json()["id"]
    assert client.post("/api/v1/self/imports/event", json={"id": request_id, "event": "started"}).status_code == 200
    return request_id


def _row(request_id):
    return next(i for i in onboarding.onboarding_state()["imports"] if i["id"] == request_id)


# ---------------------------------------------------------------------------
# The studio's half: the import event carries the pause
# ---------------------------------------------------------------------------

def test_a_paused_event_marks_the_open_import_paused_and_resumed_clears_it():
    _confirm()
    request_id = _started_import()
    response = client.post("/api/v1/self/imports/event", json={"id": request_id, "event": "paused", "items_seen": 12})
    assert response.status_code == 200, response.text
    row = _row(request_id)
    assert row["finished_at"] is None and row["outcome"] == onboarding.IMPORT_PAUSED_HIDDEN
    assert row["items_seen"] == 12

    assert client.post("/api/v1/self/imports/event", json={"id": request_id, "event": "resumed"}).status_code == 200
    row = _row(request_id)
    assert row["finished_at"] is None and row["outcome"] is None


def test_a_paused_import_still_finishes_with_its_real_outcome():
    _confirm()
    request_id = _started_import()
    client.post("/api/v1/self/imports/event", json={"id": request_id, "event": "paused", "items_seen": 3})
    client.post("/api/v1/self/imports/event", json={"id": request_id, "event": "finished", "items_seen": 40,
                                                    "outcome": "end_of_list"})
    row = _row(request_id)
    assert row["outcome"] == "end_of_list" and row["items_seen"] == 40
    # A late pause from a tab that was closed does not reopen a finished import.
    client.post("/api/v1/self/imports/event", json={"id": request_id, "event": "paused"})
    assert _row(request_id)["outcome"] == "end_of_list"


def test_an_unknown_event_is_still_refused():
    _confirm()
    request_id = _started_import()
    assert client.post("/api/v1/self/imports/event", json={"id": request_id, "event": "napping"}).status_code == 409


# ---------------------------------------------------------------------------
# The bridge's half: runImport in a hidden tab reports the pause
# ---------------------------------------------------------------------------

def test_run_import_in_a_hidden_tab_reports_paused_then_resumed():
    from qc_f3_pages import Pages, page_html

    pages = Pages()
    try:
        page = pages.open(
            f"/in/{ME}/recent-activity/all/", page_html("<main></main>"),
            scripts=("content.js", "own_pages.js"), me=ME,
            before=(
                "() => { window.__hidden = true;"
                " Object.defineProperty(document, 'visibilityState', { configurable: true,"
                "   get: () => (window.__hidden ? 'hidden' : 'visible') });"
                " window.__answers['/api/v1/self/imports/pending'] = { status: 'success', request: { id: 77 } }; }"
            ),
        )
        page.clock.run_for(15_000)
        events = pages.sent(page, "/api/v1/self/imports/event")
        assert {"id": 77, "event": "started"} in events, events
        paused = [e for e in events if e.get("event") == "paused"]
        assert paused and paused[0]["id"] == 77, f"a hidden tab paused without telling the studio: {events}"
        assert not any(e.get("event") in ("resumed", "finished") for e in events), events

        page.evaluate("() => { window.__hidden = false; document.dispatchEvent(new Event('visibilitychange')); }")
        page.clock.run_for(5_000)
        events = pages.sent(page, "/api/v1/self/imports/event")
        assert any(e.get("event") == "resumed" and e["id"] == 77 for e in events), events
    finally:
        pages.close()


# ---------------------------------------------------------------------------
# What Setup shows
# ---------------------------------------------------------------------------

def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def studio_url():
    if not os.path.exists(os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")):
        pytest.fail("studio/frontend_next is not built: run npm --prefix studio/ui run build")
    import uvicorn

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app=app_module.app, host="127.0.0.1", port=port,
                                           log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=3.0)


def test_setup_says_a_paused_import_is_paused_and_why(studio_url):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    _confirm()
    request_id = _started_import()
    client.post("/api/v1/self/imports/event", json={"id": request_id, "event": "paused", "items_seen": 12})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1"])
        try:
            context = browser.new_context(service_workers="block")
            context.route("**/*", lambda r: r.continue_() if r.request.url.startswith(studio_url) else r.abort())
            page = context.new_page()
            page.goto(studio_url + "/#/setup", wait_until="networkidle")
            line = page.get_by_text("PAUSED AT 12")
            line.wait_for(timeout=10000)
            text = line.inner_text()
            assert "LINKEDIN TAB TO THE FRONT" in text
            assert "SCROLLING NOW" not in page.locator("body").inner_text()
        finally:
            browser.close()
