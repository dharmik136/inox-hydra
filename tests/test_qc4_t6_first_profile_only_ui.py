"""
Review finding SF-1, in a browser: the one sentence that says a profile's
old session was removed, on the Local security panel where sessions are
managed.
======================================================================

Drives the built interface against a studio in a throwaway home with an
Agency licence signed by a throwaway key, a second profile open, and a
session written into it the way 2.7.0 could. Nothing reaches LinkedIn.

Strict Invariants:
- Zero em-dashes.
"""

import base64
import os
import sys

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

if not os.path.isfile(os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")):
    pytest.skip("studio/frontend_next is not built in this checkout", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from test_qc4_t6_analytics_export_ui import _axe, browser, page, studio  # noqa: E402,F401
from test_qc4_t6_first_profile_only import SECOND, _write_a_2_7_0_session  # noqa: E402

import ed25519  # noqa: E402
import licensing  # noqa: E402
import linkedin_client  # noqa: E402

THROWAWAY = os.urandom(32)


def test_the_removed_session_is_said_once_on_the_local_security_panel(page, studio, monkeypatch):
    monkeypatch.setattr(licensing, "PUBLIC_KEYS", [base64.b64encode(ed25519.public_key(THROWAWAY)).decode()])
    import app as app_module
    api = TestClient(app_module.app)
    key = licensing.encode({"v": 1, "email": "buyer@example.com", "tier": "agency", "kind": "annual", "profiles": 5,
                            "issued_at": "2026-10-19", "expires_at": "2099-01-01", "updates_until": "2099-01-01"},
                           lambda message: ed25519.sign(THROWAWAY, message))
    assert api.post("/api/v1/licence", json={"key": key}).status_code == 200
    assert api.post("/api/v1/accounts", json={"name": "Client B", "id": SECOND}).status_code == 200
    assert api.post("/api/v1/accounts/switch", json={"account_id": SECOND}).status_code == 200
    _write_a_2_7_0_session(SECOND)
    assert linkedin_client.remove_sessions_beyond_the_first_profile() == [SECOND]

    page.goto(studio["url"] + "/#/settings", wait_until="networkidle")
    page.get_by_role("tab", name="Local security").click()
    notice = page.get_by_text("The LinkedIn session this profile held was removed on", exact=False)
    expect(notice).to_be_visible()
    expect(page.get_by_text("NONE", exact=True)).to_be_visible()
    assert _axe(page, "div[role='status']:has(button)") == []
    page.get_by_role("button", name="Understood").click()
    expect(notice).to_have_count(0)
    assert api.get("/api/auth/status").json()["session_removed"] is None
