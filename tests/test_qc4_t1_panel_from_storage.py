"""
The side panel and popup say "captured just now" from the worker's storage.
===========================================================================

Cycle 4, track 1, items 8 and 9 (the pages). Both pages read the studio
once when opened and never refreshed, and the capture confirmation lived on
LinkedIn's page. They now render the worker's lastCapture, the waiting count
and the drift notice from chrome.storage, and follow storage.onChanged, so a
capture shows the moment it lands with no studio call and nothing drawn into
LinkedIn's document. The panel's Health tab printed the studio's own
network-reading sentence until network reading was retired in 2.10.2; it
now says nothing of network reading, even to a studio that still answers it.
"""

import json
import os

import pytest

from qc_f3_pages import EXT, Pages

with open(os.path.join(EXT, "sidepanel.html"), encoding="utf-8") as handle:
    PANEL = handle.read().replace('<script src="sidepanel.js"></script>', "")
with open(os.path.join(EXT, "popup.html"), encoding="utf-8") as handle:
    POPUP = handle.read().replace('<script src="popup.js"></script>', "")

LAST = {"path": "/api/v1/crm/interactions/ingest", "at": "2026-10-26T10:00:00.000Z", "ok": True, "kept": False,
        "stored": True, "httpStatus": 200, "outcome": "accepted", "tabId": 3}
DRIFT = {"extractor": "engagers", "page_kind": "feed", "fields": ["commenter_name"], "at": "2026-10-26T10:01:00.000Z"}
NOTICE = {"message": "Inox Hydra: could not reach your studio, so nothing was saved.", "kind": "warning",
          "page_kind": "feed", "at": "2026-10-26T10:02:00.000Z", "seen": False}

HEALTH = {
    "bridge": {"connected": True}, "extractors": [], "recent_drift": [], "voyager_active": False,
    "voyager_24h_captures": 0, "schema_version": "x", "contract": {},
    "network_reading": {"state": "matching_nothing", "switch": True,
                        "sentence": "Network reading is on and matching nothing: the last page read made 12 LinkedIn data calls and none matched the bridge's patterns.",
                        "voyager_calls": {"/voyager/api/graphql voyagerFeedDashMainFeed": 9,
                                          "/voyager/api/identity/dash/profiles": 3}},
}


def _fake(health=HEALTH):
    return """() => {
      chrome.tabs = { query: async () => [{ id: 3, url: 'https://www.linkedin.com/feed/' }], sendMessage: () => {}, create: () => {} };
      chrome.cookies = { get: (q, cb) => cb(null) };
      chrome.windows = { getCurrent: async () => ({ id: 7 }) };
      chrome.sidePanel = { open: async () => {} };
      window.__answer = (m) => {
        if (m.action === 'PANEL_API' && m.path === '/api/v1/extension/health') return { ok: true, httpStatus: 200, data: %s };
        if (m.action === 'PANEL_API' && m.path === '/api/v1/onboarding/state') return { ok: true, httpStatus: 200, data: { identity: null, session: null } };
        if (m.action === 'PANEL_API') return { ok: true, httpStatus: 200, data: { posts: [], leads: [] } };
        return { ok: true };
      };
    }""" % json.dumps(health)


@pytest.fixture(scope="module")
def pages():
    p = Pages()
    yield p
    p.close()


def _open(pages, html, script, storage, session=None):
    page = pages.open("/" + script.replace(".js", ".html"), html, scripts=(script,), before=_fake(), storage=storage,
                      session=session)
    page.evaluate("() => document.dispatchEvent(new Event('DOMContentLoaded'))")
    page.clock.run_for(300)
    return page


def _text(page, element_id):
    return page.evaluate(f"() => {{ const e = document.getElementById('{element_id}'); return e ? e.innerText.replace(/\\s+/g, ' ').trim() : null; }}")


def test_the_panel_names_the_last_capture_from_storage(pages):
    page = _open(pages, PANEL, "sidepanel.js", {"lastCapture": LAST, "waitingCaptures": {"waiting": 0}})
    line = _text(page, "sp-last-capture")
    assert line and "engager" in line.lower() and "captured" in line.lower()


def test_a_relay_that_stored_nothing_is_never_called_a_capture(pages):
    page = _open(pages, PANEL, "sidepanel.js", {"lastCapture": {**LAST, "stored": False, "outcome": "nothing_new"}})
    line = _text(page, "sp-last-capture")
    assert "captured" not in line.lower() and "engager" not in line.lower()
    assert "nothing new" in line.lower()


def test_the_panel_follows_storage_without_a_studio_call(pages):
    page = _open(pages, PANEL, "sidepanel.js", {})
    assert _text(page, "sp-last-capture") in (None, "", "No capture yet.")
    page.evaluate("(last) => chrome.storage.local.set({ lastCapture: last })", {**LAST, "path": "/api/v1/self/posts/analytics"})
    page.clock.run_for(50)
    line = _text(page, "sp-last-capture")
    assert line and "analytics" in line.lower()
    panel_calls = page.evaluate("() => window.__sent.filter((m) => m.action === 'PANEL_API').length")
    page.evaluate("(last) => chrome.storage.local.set({ lastCapture: last })", LAST)
    page.clock.run_for(50)
    assert page.evaluate("() => window.__sent.filter((m) => m.action === 'PANEL_API').length") == panel_calls


def test_a_kept_capture_is_said_as_waiting_not_as_captured(pages):
    page = _open(pages, PANEL, "sidepanel.js", {"lastCapture": {**LAST, "ok": False, "kept": True}, "waitingCaptures": {"waiting": 2}})
    line = _text(page, "sp-last-capture")
    assert "waiting" in line.lower() and "captured" not in line.lower()


def test_the_drift_notice_is_in_the_panel_header(pages):
    page = _open(pages, PANEL, "sidepanel.js", {}, session={"lastDrift": DRIFT})
    notice = _text(page, "sp-drift-notice")
    assert notice and "commenter name" in notice.lower() and "health" in notice.lower()
    assert "noticed" in notice.lower(), "the notice does not say when it was measured"


def test_a_drift_kept_in_local_storage_is_not_shown(pages):
    """The notice is this session's; a record left in local storage is not one."""
    page = _open(pages, PANEL, "sidepanel.js", {"lastDrift": DRIFT})
    assert not _text(page, "sp-drift-notice")


def test_opening_the_panel_tells_the_worker(pages):
    page = _open(pages, PANEL, "sidepanel.js", {})
    assert page.evaluate("() => window.__sent.some((m) => m.action === 'PANEL_OPENED')")


def test_the_health_tab_says_nothing_of_network_reading_or_voyager(pages):
    """An older studio still answers network reading and the Voyager figures; the panel shows none of it."""
    page = _open(pages, PANEL, "sidepanel.js", {})
    page.click("#tab-health-btn")
    page.clock.run_for(300)
    health = _text(page, "health-mini-list")
    badge = _text(page, "sp-health-badge")
    for gone in ("Network reading", "voyager", "Voyager", "Schema Registry", "Network Captures", "drift detected"):
        assert gone not in health and gone not in (badge or ""), f"the panel still says {gone!r}"
    assert badge == "Connected"


def test_the_popup_names_the_last_capture_and_follows_storage(pages):
    page = _open(pages, POPUP, "popup.js", {"lastCapture": LAST})
    assert "captured" in (_text(page, "popup-last-capture") or "").lower()
    page.evaluate("(drift) => chrome.storage.session.set({ lastDrift: drift })", DRIFT)
    page.clock.run_for(50)
    assert "commenter name" in (_text(page, "popup-drift-notice") or "").lower()


def test_the_popup_says_a_kept_capture_without_a_count(pages):
    """
    The popup closes when it loses focus, and the privacy policy says Today is
    where the waiting count is shown (tests/test_privacy_policy_matches_the_code.py
    holds the popup to that); the side panel and the badge carry the count.
    """
    page = _open(pages, POPUP, "popup.js", {"lastCapture": {**LAST, "ok": False, "kept": True},
                                            "waitingCaptures": {"waiting": 4}})
    line = _text(page, "popup-last-capture") or ""
    assert "kept for the studio" in line and "sent again" in line
    assert "4" not in line, "the popup shows the waiting count"


# ---------------------------------------------------------------------------
# The review's S7: what the page used to draw is said at the top of the panel
# ---------------------------------------------------------------------------

def test_a_notice_from_linkedins_page_is_the_first_line_of_the_panel(pages):
    page = _open(pages, PANEL, "sidepanel.js", {}, session={"pageNotice": NOTICE})
    line = _text(page, "sp-page-notice")
    assert line and line.startswith("Inox Hydra: could not reach your studio, so nothing was saved."), line
    assert "noticed" in line.lower(), "the notice does not say when it was said"
    order = page.evaluate("() => Array.from(document.querySelectorAll('.header-line')).map((e) => e.id)")
    assert order[0] == "sp-page-notice", order
    assert page.evaluate("() => window.__sent.some((m) => m.action === 'PANEL_OPENED')")
    # The worker marks it seen when told; this panel keeps it in view.
    page.evaluate("(n) => chrome.storage.session.set({ pageNotice: Object.assign({}, n, { seen: true }) })", NOTICE)
    page.clock.run_for(50)
    assert _text(page, "sp-page-notice") == line


def test_a_notice_already_seen_is_not_shown_on_the_next_opening(pages):
    page = _open(pages, PANEL, "sidepanel.js", {}, session={"pageNotice": {**NOTICE, "seen": True}})
    assert not _text(page, "sp-page-notice")


def test_a_notice_that_arrives_while_the_panel_is_open_is_shown_and_seen(pages):
    page = _open(pages, PANEL, "sidepanel.js", {})
    opened = page.evaluate("() => window.__sent.filter((m) => m.action === 'PANEL_OPENED').length")
    page.evaluate("(n) => chrome.storage.session.set({ pageNotice: n })", NOTICE)
    page.clock.run_for(50)
    assert (_text(page, "sp-page-notice") or "").startswith("Inox Hydra: could not reach your studio")
    assert page.evaluate("() => window.__sent.filter((m) => m.action === 'PANEL_OPENED').length") == opened + 1
