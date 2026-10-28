"""
A short link from the phone, on Today, in a browser.
====================================================

Drives the built interface against a studio in a throwaway home. The request
is written as the ingress writes it. Open is pressed, but the browser launch
route is never reached: the page's request to it is answered inside the
browser, which records the address Today asked to open. The extension's
landing report is sent as its worker relays it.

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

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

from test_qc4_t6_analytics_export_ui import browser, page, studio  # noqa: E402,F401
from test_qc4_t6_phone_requests_ui import _axe_section_with  # noqa: E402

import desk_requests  # noqa: E402
from database import get_db  # noqa: E402

ME = "short-link-ui-creator"
SHORT = "https://lnkd.in/p/dXyZ4bQ7"
SENT = "You sent a post from your phone."


def _urn_days_ago(days, salt):
    moment = datetime.now(timezone.utc) - timedelta(days=days)
    return "urn:li:activity:" + str((int(moment.timestamp() * 1000) << 22) + salt)


def _ready_with_a_short_link():
    import app as app_module
    api = TestClient(app_module.app)
    api.post("/api/v1/identity/observe", json={"vanity": ME, "self_evidence": ["owner_edit_controls"],
                                               "display_name": "Short Link Probe"})
    api.post("/api/v1/identity/confirm", json={"vanity": ME})
    latest, older = _urn_days_ago(1, 1), _urn_days_ago(9, 2)
    api.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": urn, "actor": ME, "text": f"Post {n}"} for n, urn in enumerate((latest, older))]})
    api.post("/api/v1/bridge/heartbeat", json={"extension_version": "test"})
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO self_import_requests (kind, requested_at, finished_at, items_seen, outcome) "
                     "VALUES ('posts', ?, ?, 5, 'end_of_list')", (now, now))
        conn.execute("INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, "
                     "source, impressions) VALUES (?, ?, 'probe-now', 24.0, 'post_analytics', 500)", (latest, now))
        conn.execute("INSERT INTO captures (observed_at, extractor, page_kind, items_seen, items_kept) "
                     "VALUES (?, 'activity_posts', 'in', 1, 1)", (now,))
    asked = desk_requests.record_short(conn, SHORT)
    conn.close()
    return api, asked, older


def _launches(page):
    """Today's Open, answered in the browser: the launch route is never reached."""
    asked = []

    def answer(route):
        asked.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"status": "success", "browser": "Test browser", "carries_extension": True,
                                       "message": "Opened in the test browser."}))

    page.route("**/api/v1/browser/launch", answer)
    return asked


def test_today_opens_the_short_link_with_its_fragment_and_then_asks_for_the_post(page, studio):
    api, asked, older = _ready_with_a_short_link()
    launches = _launches(page)
    page.goto(studio["url"] + "/#/today", wait_until="networkidle")
    expect(page.get_by_text(SENT, exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="Done")).to_be_visible()
    expect(page.get_by_role("button", name="Not now")).to_be_visible()
    assert _axe_section_with(page, "ONE THING TO OPEN") == []
    page.get_by_role("button", name="Open it in the bridge browser").click()
    expect(page.get_by_text("Opened in the test browser.")).to_be_visible()
    assert [launch["url"] for launch in launches] == [f"{SHORT}#inox-desk-{asked['id']}"]
    # The page the link landed on kept the fragment, and the extension says so.
    # Today reads again when the studio says the desk changed, at most once
    # in its fifteen-second gap.
    res = api.post("/api/v1/desk-requests/landed", json={"request_id": asked["id"], "activity_urn": older})
    assert res.json()["attached"] is True
    expect(page.get_by_text("You asked from your phone to read this post's analytics.")).to_be_visible(timeout=25000)
    expect(page.get_by_role("button", name="Done")).to_have_count(0)


def test_done_on_today_closes_a_short_link_the_browser_never_reported(page, studio):
    _api, asked, _older = _ready_with_a_short_link()
    page.goto(studio["url"] + "/#/today", wait_until="networkidle")
    expect(page.get_by_text(SENT, exact=False)).to_be_visible()
    page.get_by_role("button", name="Done").click()
    expect(page.get_by_text(SENT, exact=False)).to_have_count(0)
    expect(page.get_by_text("Opening your latest post picks up anyone who has commented since.")).to_be_visible()
    conn = get_db()
    assert conn.execute("SELECT state FROM desk_requests WHERE id = ?", (asked["id"],)).fetchone()[0] == "done"
    conn.close()
