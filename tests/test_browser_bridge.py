"""
Browser Bridge Guards
=====================
Leads are captured by an extension watching the LinkedIn pages you open
yourself. Until it is loaded, the Leads surface can only ever be empty, no
matter how long it is left. Four endpoints have existed for this since before
the interface did, none was reachable, and the empty state stated the outcome
without offering the step that changes it.

Wiring it up surfaced a defect in the launcher underneath.

Not every Chromium browser loads an unpacked extension from --load-extension,
and the ones that do not fail silently: the browser opens, the launcher reports
"Successfully launched ... with LinkedIn Studio Bridge loaded", and the bridge
is simply not there. Worse, the automatic choice preferred Chrome by name, so
the default path picked the one option that cannot work.

Probed on this machine, headless, with a throwaway profile, reading the
DevTools target list for the bridge's own service worker:

    chrome   the worker never appears
    edge     chrome-extension://<id>/background.js present
    brave    chrome-extension://<id>/background.js present

The first version of that probe counted any chrome-extension:// worker and
reported Chrome as working, because every Chromium browser ships component
extensions of its own. Matching the bridge's declared background.js is what
told them apart, and it is the reason this file asserts a specific capability
rather than a count.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI_SRC = os.path.join(REPO_ROOT, "studio", "ui", "src")
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

import browser_launcher  # noqa: E402

from app import app  # noqa: E402

client = TestClient(app)


def _read(path):
    if not os.path.exists(path):
        pytest.skip(f"{os.path.basename(path)} is not present in this checkout")
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def test_chrome_is_recorded_as_unable_to_carry_the_bridge():
    """
    The measured fact, pinned.

    If this ever flips, it should flip because someone re-probed and Chrome
    changed, not because the table was edited to make a test pass.
    """
    assert browser_launcher.carries_extension("chrome") is False
    assert browser_launcher.carries_extension("edge") is True
    assert browser_launcher.carries_extension("brave") is True


def test_an_unprobed_browser_is_unknown_rather_than_assumed():
    """
    "We have not checked" is a different statement from "this will not work",
    and the interface renders them differently. Defaulting an unprobed browser
    to either answer would assert something nobody measured.
    """
    assert browser_launcher.carries_extension("opera") is None
    assert browser_launcher.carries_extension("vivaldi") is None


def test_detection_reports_capability_beside_availability():
    """
    Installed and useful are different questions. Chrome is installed on nearly
    every machine and cannot carry the bridge, so a caller must not be able to
    read one without the other.
    """
    response = client.get("/api/v1/browser/status")
    assert response.status_code == 200, response.text
    browsers = response.json().get("browsers", {})
    if not browsers:
        pytest.skip("no Chromium browser on this machine")

    for browser_id, info in browsers.items():
        assert "carries_extension" in info, (
            f"{browser_id} reports availability without saying whether it can carry the bridge"
        )
        assert info["carries_extension"] is browser_launcher.carries_extension(browser_id)


def test_automatic_selection_prefers_a_browser_that_works():
    """
    The defect this found. Preference used to be Chrome, Edge, Brave by name,
    so the automatic choice was the browser that silently does nothing.
    """
    source = _read(os.path.join(REPO_ROOT, "studio", "backend", "browser_launcher.py"))
    assert 'for pref in ["chrome", "edge", "brave", "opera", "vivaldi"]' not in source, (
        "automatic selection prefers Chrome again, which ignores the extension flag"
    )
    assert "carries_extension(b) is not True" in source, (
        "selection no longer sorts by whether the browser can carry the bridge"
    )


def test_the_launcher_does_not_claim_a_bridge_it_did_not_load():
    """
    What happened is that a browser was launched. Whether the bridge came with
    it is a separate fact, and claiming it for a browser that drops the flag is
    how someone waits for leads that cannot arrive.
    """
    source = _read(os.path.join(REPO_ROOT, "studio", "backend", "browser_launcher.py"))
    assert "Successfully launched {selected['name']} with LinkedIn Studio Bridge loaded." not in source
    assert "ignores --load-extension" in source, (
        "the launcher no longer explains why a browser it opened will capture nothing"
    )


def test_the_empty_stream_offers_the_step_that_fills_it():
    """
    The surface half. An empty state that only states the outcome leaves the
    one question a new install has unanswered.
    """
    source = _read(os.path.join(UI_SRC, "components", "LeadsSurface.tsx"))
    assert "fetchBrowserBridge" in source, "the empty stream never looks for a browser"
    assert "launchBridge" in source, "the empty stream cannot start the bridge"
    assert "carries_extension" in source, (
        "the empty stream lists browsers without distinguishing the ones that work"
    )


def test_the_bridge_endpoints_are_reachable_from_the_interface():
    """Three of the four families that had never been called."""
    client_source = _read(os.path.join(UI_SRC, "lib", "api.ts"))
    for route in (
        "/api/v1/browser/status",
        "/api/v1/browser/launch",
        "/api/v1/browser/copy-path",
    ):
        assert route in client_source, f"{route} is still unreachable from the interface"
