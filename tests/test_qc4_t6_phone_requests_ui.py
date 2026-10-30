"""
Review finding SF-2, in a browser: Today's Not now for a post the phone
asked for, and the Telegram panel's list of links.
=====================================================================

Drives the built interface against a studio in a throwaway home. Nothing
reaches Telegram or LinkedIn: the request is written as the ingress writes
it, and no button that opens a browser is pressed.

Strict Invariants:
- Zero em-dashes.
"""

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

from test_qc4_t6_analytics_export_ui import AXE_JS, browser, page, studio  # noqa: E402,F401

import desk_requests  # noqa: E402
from database import get_db  # noqa: E402

ME = "phone-ui-creator"


def _urn_days_ago(days, salt):
    moment = datetime.now(timezone.utc) - timedelta(days=days)
    return "urn:li:activity:" + str((int(moment.timestamp() * 1000) << 22) + salt)


def _ready_with_a_request():
    """Identity, bridge and history ready; the latest post read just now; an older post asked for."""
    import app as app_module
    api = TestClient(app_module.app)
    api.post("/api/v1/identity/observe", json={"vanity": ME, "self_evidence": ["owner_edit_controls"],
                                               "display_name": "Phone Probe"})
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
        # The Activity page read today, so the weekly ask for it (track 1's
        # cadence, which comes after the phone's request) has nothing to ask.
        conn.execute("INSERT INTO captures (observed_at, extractor, page_kind, items_seen, items_kept) "
                     "VALUES (?, 'activity_posts', 'in', 1, 1)", (now,))
    asked = desk_requests.record(conn, older)
    refused = desk_requests.record(conn, _urn_days_ago(3, 3))
    conn.close()
    return asked, refused


def _axe_section_with(page, words):
    """axe over the section holding these words, in both themes, settled before measuring."""
    if not os.path.exists(AXE_JS):
        pytest.skip("axe-core is not installed with the UI dependencies")
    page.add_script_tag(path=AXE_JS)
    # Colours are measured at rest. With transitions running, a theme change
    # was measured halfway on slow runners (macOS on CI), so they are stilled
    # while axe measures, and allowed again after.
    still = page.add_style_tag(content="*, *::before, *::after { transition: none !important; "
                                       "animation: none !important; }")
    found = []
    for theme in ("dark", "light"):
        page.evaluate("(t) => document.documentElement.setAttribute('data-theme', t)", theme)
        page.wait_for_timeout(100)
        found += page.evaluate("""async (words) => {
            const el = [...document.querySelectorAll('section')].find(s => s.textContent.includes(words));
            if (!el) return ['no section holds: ' + words];
            const r = await axe.run(el, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] } });
            return r.violations.map(v => v.id + ': ' + v.nodes.map(n => n.target.join(' ')).join(', '));
        }""", words)
    still.evaluate("(el) => el.remove()")
    return found


def test_not_now_on_today_closes_the_phones_request(page, studio):
    asked, _refused = _ready_with_a_request()
    page.goto(studio["url"] + "/#/today", wait_until="networkidle")
    expect(page.get_by_text("You asked from your phone to read this post's analytics.")).to_be_visible()
    assert _axe_section_with(page, "ONE THING TO OPEN") == []
    page.get_by_role("button", name="Not now").click()
    expect(page.get_by_text("You asked from your phone to read this post's analytics.")).to_have_count(0)
    expect(page.get_by_text("Opening your latest post picks up anyone who has commented since.")).to_be_visible()
    conn = get_db()
    assert conn.execute("SELECT state FROM desk_requests WHERE id = ?", (asked["id"],)).fetchone()[0] == "dismissed"
    conn.close()


def test_the_telegram_panel_lists_a_refused_link_with_its_reason(page, studio):
    _ready_with_a_request()
    page.goto(studio["url"] + "/#/settings", wait_until="networkidle")
    page.get_by_role("tab", name="Local security").click()
    expect(page.get_by_text("LINKS FROM YOUR PHONE, NEWEST FIRST")).to_be_visible()
    expect(page.get_by_text("Not one of your posts:", exact=False)).to_be_visible()
    expect(page.get_by_text("Waiting: Today asks you to open its analytics page at this computer.")).to_be_visible()
    assert _axe_section_with(page, "Your phone, through Telegram") == []
