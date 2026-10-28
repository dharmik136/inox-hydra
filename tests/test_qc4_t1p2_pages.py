"""
The page side of the coordination block.
========================================

Cycle 4, track 1, phase 2 (the capture report's Appendix B, days 1 to 4 and
10). Drives the shipped content scripts in headless Chromium (qc_f3_pages.py).

  one request   a read of a post's people is one message carrying items[],
                and each person is answered from it, in read order
  hidden tabs   a hidden tab's body observer is off; it reads once on
                becoming visible
  page state    a tab tells the worker its kind of page and network reading,
                and never sends the studio a heartbeat of its own
  version       the readers say which version they are, so the worker can
                tell a tab carrying this version from one that needs it
  orphans       readers cut off from their extension by an update stop
  one scroller  two visible tabs on one activity page, against a real
                studio: one tab claims the history import and scrolls; the
                other reads what is on screen and does not scroll

Every name here is invented.

Strict Invariants:
- Zero em-dashes.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

from qc_f3_pages import Pages, page_html

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

INGEST = "/api/v1/crm/interactions/ingest"
HIDE = """() => { window.__hidden = true;
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => (window.__hidden ? 'hidden' : 'visible') }); }"""
SHOW = "() => { window.__hidden = false; document.dispatchEvent(new Event('visibilitychange')); }"


@pytest.fixture(scope="module")
def pages():
    p = Pages()
    yield p
    p.close()


def _engager_messages(pages, page):
    return [m for m in pages.sent(page) if m.get("action") == "STUDIO_API" and m.get("path") == INGEST]


def _open_reactions(pages, before=None):
    from test_qc_f3_engagers import FEED, MODAL, OPEN_MODAL
    page = pages.open("/feed/", FEED, before=before)
    page.clock.run_for(5000)
    page.evaluate("() => document.getElementById('mine-count').click()")
    page.evaluate(OPEN_MODAL, MODAL)
    return page


def test_a_read_of_a_post_is_one_message_with_its_people(pages):
    page = _open_reactions(pages)
    page.clock.run_for(6000)
    messages = _engager_messages(pages, page)
    assert len(messages) == 1, f"{len(messages)} messages for one read"
    names = [item["full_name"] for item in messages[0]["body"]["items"]]
    assert names == ["Reactor One", "Reactor Two"]


ANSWERS_BY_ITEM = """() => {
  const base = window.__answer;
  window.__answer = (m) => (m.path === '/api/v1/crm/interactions/ingest'
    ? { status: 'success', httpStatus: 200, data: { status: 'success', outcome: 'accepted', items_accepted: 1, items: [
        { status: 'success', outcome: 'accepted' },
        { status: 'refused', outcome: 'refused', reason: 'import_posts_first', show: true,
          message: 'Import your posts from the studio Setup screen first.' }] } }
    : base(m));
}"""


def test_each_person_is_answered_from_the_reads_answer(pages):
    page = _open_reactions(pages, before=ANSWERS_BY_ITEM)
    page.clock.run_for(6000)
    assert len(_engager_messages(pages, page)) == 1
    # The second person was refused, so is offered again 30 s later; the first was taken.
    page.evaluate("() => document.getElementById('artdeco-modal-outlet').innerHTML += ''")
    page.clock.run_for(31000)
    page.evaluate("() => document.body.appendChild(document.createElement('span'))")
    page.clock.run_for(6000)
    messages = _engager_messages(pages, page)
    assert len(messages) == 2, f"{len(messages)} messages"
    assert [item["full_name"] for item in messages[1]["body"]["items"]] == ["Reactor Two"], (
        "the person the studio took was offered again, or the refused one was not")


def test_a_hidden_tab_reads_nothing_and_reads_once_on_return(pages):
    page = _open_reactions(pages, before=HIDE)
    page.clock.run_for(8000)
    assert _engager_messages(pages, page) == [], "a hidden tab read the post"
    page.evaluate(SHOW)
    page.clock.run_for(6000)
    assert len(_engager_messages(pages, page)) == 1, "the tab did not read on becoming visible"


def test_a_page_tells_the_worker_its_state_and_sends_the_studio_no_heartbeat(pages):
    page = pages.open("/feed/", page_html("<main></main>"), scripts=("content.js", "own_pages.js"),
                      storage={"networkReading": True})
    page.clock.run_for(70000)
    states = [m for m in pages.sent(page) if m.get("action") == "PAGE_STATE"]
    assert states, "the page never told the worker its state"
    assert states[-1]["page_kind"] == "feed" and states[-1]["visible"] is True
    # Network reading was retired in 2.10.2: a switch an earlier version left
    # stored is not reported.
    assert not [m for m in states if "network_reading" in m or "voyager_calls" in m]
    assert pages.sent(page, "/api/v1/bridge/heartbeat") == [], "a tab sent the studio a heartbeat of its own"


def test_the_readers_say_which_version_they_are(pages):
    page = pages.open("/feed/", page_html("<main></main>"))
    assert page.evaluate("() => window.__inoxBridgeVersion") == "test"


def test_readers_cut_off_by_an_update_stop_reading(pages):
    from test_qc_f3_engagers import FEED, MODAL, OPEN_MODAL
    page = pages.open("/feed/", FEED)
    page.clock.run_for(5000)
    page.evaluate("() => { Object.defineProperty(chrome.runtime, 'id', { configurable: true, get: () => undefined }); }")
    page.evaluate("() => document.getElementById('mine-count').click()")
    page.evaluate(OPEN_MODAL, MODAL)
    page.clock.run_for(8000)
    assert _engager_messages(pages, page) == [], "a reader cut off from its extension went on reading"


# ---------------------------------------------------------------------------
# Two visible tabs, one real studio: one scroller
# ---------------------------------------------------------------------------

ME = "test-creator"
POSTS = page_html("""
<main>
 <div id="expanded-2-FeedType_MEMBER_ACTIVITY" data-urn="urn:li:activity:7386000000000000006">
   <div><a href="https://www.linkedin.com/in/test-creator/"><span>Test Creator</span></a></div>
   <div data-testid="expandable-text-box">My own post about shipping a local-first app, written by me.</div>
   <button aria-label="9 reactions">9</button>
 </div>
</main>""", title="Test Creator | Activity | LinkedIn", lang="en")

THROUGH_A_REAL_STUDIO = """() => {
  chrome.runtime.sendMessage = (message, callback) => {
    window.__sent.push(JSON.parse(JSON.stringify(message)));
    if (message.action !== 'STUDIO_API') { setTimeout(() => callback && callback({ status: 'noted' }), 0); return; }
    window.realStudio(message).then((answer) => { if (callback) callback(answer); });
  };
}"""


@pytest.fixture
def real_studio(monkeypatch, tmp_path):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    from app import app
    from fastapi.testclient import TestClient
    from security import TOKEN_HEADER, get_or_create_token
    client = TestClient(app, base_url="http://127.0.0.1:8000", headers={TOKEN_HEADER: get_or_create_token()})
    assert client.post("/api/v1/identity/observe", json={"vanity": ME, "self_evidence": ["owner_edit_controls"],
                                                         "display_name": "T"}).status_code == 200
    assert client.post("/api/v1/identity/confirm", json={"vanity": ME}).status_code == 200
    assert client.post("/api/v1/self/imports", json={"kind": "posts"}).status_code == 200
    return client


def _worker_for(client, tab_id):
    """What the worker does with a relay, for one tab: stamp it, send it, answer as relayToStudio does."""
    def relay(message):
        body = dict(message.get("body") or {})
        body["stamp"] = {"browser_instance_id": "b1a2c3d4-0000-4000-8000-00000000000a", "tab_id": tab_id,
                         "window_id": 1, "document_id": f"doc-{tab_id}"}
        response = client.post(message["path"], json=body)
        data = response.json() if response.content else {}
        if response.status_code < 300:
            return {"status": "success", "httpStatus": response.status_code, "data": data}
        return {"status": "error", "httpStatus": response.status_code, "data": data}
    return relay


def test_two_visible_tabs_on_one_activity_page_scroll_once(pages, real_studio):
    tabs = []
    for tab_id in (1, 2):
        tabs.append(pages.open(f"/in/{ME}/recent-activity/all/", POSTS,
                               scripts=("content.js", "own_pages.js"), me=ME,
                               before=THROUGH_A_REAL_STUDIO, expose={"realStudio": _worker_for(real_studio, tab_id)}))
    for _ in range(4):
        for tab in tabs:
            tab.clock.run_for(2500)
    started = [m for tab in tabs for m in pages.sent(tab)
               if m.get("path") == "/api/v1/self/imports/event" and (m.get("body") or {}).get("event") == "started"]
    scrolling = [tab.evaluate("() => !!document.getElementById('studio-import-banner')") for tab in tabs]
    assert len(started) == 1, f"{len(started)} tabs started the same import"
    assert scrolling.count(True) == 1, "both tabs scroll the import, or neither does"


def _advance(tab, ms, step=1000):
    """The page's clock forward in steps, with real time between them for the studio's answers to arrive."""
    for _ in range(max(1, ms // step)):
        tab.clock.run_for(step)
        tab.wait_for_timeout(15)


def _import_tab(pages, real_studio, before=None):
    script = THROUGH_A_REAL_STUDIO if before is None else (
        "() => { (" + THROUGH_A_REAL_STUDIO + ")(); (" + before + ")(); }")
    tab = pages.open(f"/in/{ME}/recent-activity/all/", POSTS, scripts=("content.js", "own_pages.js"),
                     me=ME, before=script, expose={"realStudio": _worker_for(real_studio, 1)})
    _advance(tab, 6000)
    return tab


def _claim():
    from database import get_db
    conn = get_db()
    try:
        return tuple(conn.execute("SELECT claimed_by, finished_at FROM self_import_requests ORDER BY id DESC LIMIT 1").fetchone())
    finally:
        conn.close()


def _events(pages, tab):
    return [(m.get("body") or {}).get("event") for m in pages.sent(tab) if m.get("path") == "/api/v1/self/imports/event"]


def test_a_tab_whose_claim_was_taken_over_stops_scrolling(pages, real_studio):
    """Hidden for a while, its claim taken by a tab in front: back in front, it stops rather than scroll twice."""
    from database import get_db
    tab = _import_tab(pages, real_studio, before=HIDE.replace("window.__hidden = true", "window.__hidden = false"))
    assert "started" in _events(pages, tab)
    tab.evaluate("() => { window.__hidden = true; }")
    _advance(tab, 5000)
    assert "paused" in _events(pages, tab)
    conn = get_db()
    with conn:
        conn.execute("UPDATE self_import_requests SET claimed_by = 'another-browser:9', claimed_at = ?",
                     (datetime.now(timezone.utc).isoformat(),))
    conn.close()
    tab.evaluate(SHOW)
    _advance(tab, 4000)
    banner = tab.evaluate("() => { const b = document.getElementById('studio-import-banner'); return b ? b.innerText : ''; }")
    assert "Another tab is importing" in banner, banner
    assert "finished" not in _events(pages, tab), "a tab that lost the import finished it anyway"


def test_a_tab_that_leaves_gives_its_claim_back(pages, real_studio):
    tab = _import_tab(pages, real_studio)
    assert _claim()[0] is not None
    tab.evaluate("() => window.dispatchEvent(new Event('pagehide'))")
    tab.wait_for_timeout(200)
    assert "released" in _events(pages, tab)
    assert _claim()[0] is None, "the claim was not given back when the tab left"


def test_a_tab_hidden_past_the_limit_gives_its_claim_back(pages, real_studio):
    tab = _import_tab(pages, real_studio, before=HIDE)
    _advance(tab, 70000)
    events = _events(pages, tab)
    assert "paused" in events and "released" in events, events
    claimed_by, finished_at = _claim()
    assert claimed_by is None and finished_at is None, "the import was finished, or its claim kept"
