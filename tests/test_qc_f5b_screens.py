"""
What Analytics, Patterns and Outbound put on screen, read in a real browser.
===========================================================================

Quality cycle 2026-10, batch F5b. The route tests in test_qc_f5b_*.py hold the
numbers; these hold what the built interface does with them: a number with
too little behind it reads "not measured" and says why, a rounded figure is
marked approximate, and an empty state does not deny an import that happened.

One studio serves the built interface for the whole module. Each test points
it at a throwaway home of its own and seeds that home through the same routes
the extension and the archive import use. Service workers are blocked in
every context: the studio's worker would otherwise answer requests itself.
"""

import datetime as dt
import os
import shutil
import socket
import sys
import tempfile
import threading
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

import uvicorn  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

BUILT = os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")
END = dt.date(2031, 3, 31)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server():
    if not os.path.exists(BUILT):
        pytest.skip("the interface is not built (npm --prefix studio/ui run build)")
    old_home, old_demo = os.environ.get("INOX_HYDRA_HOME"), os.environ.get("INOX_DEMO_DATA")
    first = tempfile.mkdtemp(prefix="inox_qc_f5b_screens_")
    os.environ["INOX_HYDRA_HOME"] = first
    os.environ.pop("INOX_DEMO_DATA", None)
    from database import init_db
    init_db()
    import app as app_module

    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(app=app_module.app, host="127.0.0.1", port=port,
                                        log_level="error", access_log=False))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.05)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield {"url": f"http://127.0.0.1:{port}", "browser": browser, "app": app_module.app}
        browser.close()
    srv.should_exit = True
    thread.join(timeout=3)
    shutil.rmtree(first, ignore_errors=True)
    for key, value in (("INOX_HYDRA_HOME", old_home), ("INOX_DEMO_DATA", old_demo)):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture
def studio(server):
    """A fresh home behind the running server, a client to seed it, and a page on it."""
    home = tempfile.mkdtemp(prefix="inox_qc_f5b_screen_")
    previous = os.environ["INOX_HYDRA_HOME"]
    os.environ["INOX_HYDRA_HOME"] = home
    from database import init_db
    init_db()
    client = TestClient(server["app"])
    context = server["browser"].new_context(viewport={"width": 1440, "height": 900}, service_workers="block")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    yield {"client": client, "page": page, "url": server["url"], "errors": errors}
    context.close()
    os.environ["INOX_HYDRA_HOME"] = previous
    shutil.rmtree(home, ignore_errors=True)


def _open(studio, section):
    page = studio["page"]
    page.goto(studio["url"] + "/", wait_until="networkidle")
    page.locator(f"nav[aria-label='Studio sections'] button[aria-label='{section}']").first.click()
    page.wait_for_load_state("networkidle")
    return page


def _days(client, count, **metrics):
    series = []
    for back in range(count - 1, -1, -1):
        row = {"date": (END - dt.timedelta(days=back)).isoformat(), "period_label": "1d", "precision": "exact"}
        row.update({k: (v(back) if callable(v) else v) for k, v in metrics.items()})
        series.append(row)
    assert client.post("/api/analytics/ingest", json={"series": series}).status_code == 200


def _what_changed(page, label):
    line = page.locator("aside li", has_text=label).first
    # The value is the second of the two spans; a screen reader hears "about" for the "~".
    return " ".join((line.locator(":scope > span").nth(1).text_content() or "").split())


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def test_a_thin_previous_period_reads_not_measured_and_says_why(studio):
    """AUDIENCE-05"""
    _days(studio["client"], 34, impressions=1000, reactions=20, comments=2, shares=1)
    page = _open(studio, "Analytics")
    page.wait_for_selector("text=What changed")
    assert _what_changed(page, "Impressions") == "not measured"
    assert _what_changed(page, "Engagements") == "not measured"
    body = page.inner_text("body")
    assert "THIS ONE HAS 30, THE ONE BEFORE IT 4" in body
    assert "+650" not in body and "rose together" not in body
    assert not studio["errors"], studio["errors"]


def test_a_rounded_follower_count_is_shown_as_approximate(studio):
    """AUDIENCE-10"""
    client = studio["client"]
    _days(client, 34, impressions=1000, followers=lambda back: 2033 - back)
    row = {"date": END.isoformat(), "period_label": "1d", "precision": "rounded", "followers": 2400,
           "impressions": 1037}
    assert client.post("/api/analytics/ingest", json={"series": [row]}).status_code == 200
    page = _open(studio, "Analytics")
    page.wait_for_selector("text=What changed")
    assert _what_changed(page, "Followers") == "~about +396"
    body = page.inner_text("body")
    assert "LINKEDIN ROUNDED, SUCH AS 1.2K, SO IT IS APPROXIMATE" in body
    assert "OF THESE DAYS WAS READ" not in body, "impressions were exact, yet the chart was marked"
    page.get_by_role("button", name="Followers", exact=True).click()
    assert "1 OF THESE DAYS WAS READ FROM A FIGURE LINKEDIN ROUNDED" in page.inner_text("body")
    assert not studio["errors"], studio["errors"]


ME = "f5b-screens"


def _confirm():
    from database import get_db
    conn = get_db()
    with conn:
        conn.execute("INSERT OR REPLACE INTO creator_identity (id, vanity, display_name, confirmed_at) "
                     "VALUES (1, ?, 'F5b Screens', '2026-09-27T00:00:00+00:00')", (ME,))
    conn.close()


def _urn(n, year_ms=1780000000000):
    return f"urn:li:activity:{(year_ms + n * 86400000) << 22}"


def _own_posts(client, posts, year_ms=1780000000000, start=0):
    _confirm()
    items = [{"activity_urn": _urn(start + i, year_ms), "actor": ME, **post} for i, post in enumerate(posts)]
    res = client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": items})
    assert res.status_code == 200, res.text
    return [item["activity_urn"] for item in items]


def test_imported_posts_are_compared_and_unread_figures_say_so(studio):
    """AUDIENCE-09"""
    _own_posts(studio["client"], [{"text": "Why sourdough needs patience", "reactions": 40, "comments": 3}])
    page = _open(studio, "Analytics")
    page.wait_for_selector("text=Post comparison")
    assert "NO PUBLISHED POSTS TO COMPARE" not in page.inner_text("body")
    row = page.locator("tbody tr", has_text="Why sourdough needs patience").first
    cells = [c.strip() for c in row.locator("td").all_inner_texts()]
    assert cells[1:] == ["not measured", "40", "3", "not measured"], cells
    assert not studio["errors"], studio["errors"]
