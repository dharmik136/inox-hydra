"""
The toolbar popup reports only what it checked.
===============================================

BRIDGE-17  "LinkedIn Session: Active" came from the browser's own li_at cookie,
           so it said Active while the studio held no session and the live
           send would refuse. And the side panel button shadowed `window` with
           chrome.windows' Window, so closing the popup threw, and the catch
           said "Side panel opened in active tab!", which it also said when the
           side panel failed to open.

This runs the shipped popup.html and popup.js in headless Chromium with a fake
chrome (see qc_f3_pages.py).
"""

import os

import pytest

from qc_f3_pages import EXT, Pages

with open(os.path.join(EXT, "popup.html"), encoding="utf-8") as handle:
    POPUP = handle.read().replace('<script src="popup.js"></script>', "")


def _fake(stored, li_at, panel_fails=False):
    return """() => {
      chrome.cookies = { get: (q, cb) => cb(%(li_at)s && q.name === "li_at" ? { value: "x" } : null) };
      chrome.windows = { getCurrent: async () => ({ id: 7 }) };
      chrome.sidePanel = { open: async () => { if (%(fails)s) throw new Error("sidePanel.open() may only be called in response to a user gesture."); window.__panelOpened = true; } };
      chrome.tabs = { create: () => {} };
      window.close = () => { window.__closed = true; };
      window.__answer = (m) => {
        if (m.action !== "PANEL_API") return { status: "error" };
        if (m.path === "/api/v1/onboarding/state") return { ok: true, httpStatus: 200, data: {
          identity: { vanity: "test-creator" }, session: { stored: %(stored)s, saved_at: %(saved_at)s } } };
        return { ok: true, httpStatus: 200, data: { leads: [] } };
      };
    }""" % {"li_at": "true" if li_at else "false", "fails": "true" if panel_fails else "false",
            "stored": "true" if stored else "false",
            "saved_at": '"2026-10-18T09:00:00+00:00"' if stored else "null"}


@pytest.fixture(scope="module")
def pages():
    p = Pages()
    yield p
    p.close()


def _popup(pages, **kwargs):
    page = pages.open("/popup.html", POPUP, scripts=("popup.js",), before=_fake(**kwargs))
    page.evaluate("() => document.dispatchEvent(new Event('DOMContentLoaded'))")
    page.clock.run_for(500)
    return page


def _text(page, element_id):
    return page.evaluate(f"() => document.getElementById('{element_id}').innerText")


def test_a_browser_cookie_is_not_reported_as_a_session_the_studio_holds(pages):
    page = _popup(pages, stored=False, li_at=True)
    status = _text(page, "session-status")
    assert status != "Active"
    assert "Not saved in the studio" in status


def test_a_session_the_studio_holds_is_reported_as_saved(pages):
    page = _popup(pages, stored=True, li_at=True)
    assert "Saved in the studio" in _text(page, "session-status")


def test_opening_the_side_panel_closes_the_popup(pages):
    page = _popup(pages, stored=False, li_at=True)
    page.evaluate("() => document.getElementById('btn-open-sidepanel').click()")
    page.clock.run_for(200)
    assert page.evaluate("() => window.__panelOpened === true && window.__closed === true")
    assert "opened" not in _text(page, "status-text")


def test_a_side_panel_that_did_not_open_says_so(pages):
    page = _popup(pages, stored=False, li_at=True, panel_fails=True)
    page.evaluate("() => document.getElementById('btn-open-sidepanel').click()")
    page.clock.run_for(200)
    text = _text(page, "status-text")
    assert "opened" not in text
    assert "Could not open the side panel" in text
    assert not page.evaluate("() => window.__closed === true")
