"""
The Leads list reads a page at a time and filters on the server.
===============================================================

Cycle 2, batch R3 (DATA-09).

/api/leads returned every lead, SELECT * of all of them: 49,142 leads and
24.3 MB after three years, 0.8 s, read in full on every visit to the Leads
screen so the browser could filter it and draw 200. With limit it now returns
one page, newest first, filtered by stage and by the search box on the server
(through the search index), with how many match, how many exist and a cursor
for the next page. Without limit it answers exactly as before.
"""

import os
import shutil
import socket
import sys
import tempfile
import threading
import time

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

import qc2_r3_data  # noqa: E402

BUILT_UI = os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")


@pytest.fixture
def client(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_qc2_r3_leads_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    init_db()
    conn = get_db()
    qc2_r3_data.build(conn)
    with conn:
        # Ties on created_at, as a bulk capture writes them.
        conn.execute("UPDATE leads SET created_at = '2026-01-01 00:00:00' WHERE rowid % 4 = 0")
    conn.close()
    from fastapi.testclient import TestClient
    import app as app_module
    yield TestClient(app_module.app)
    shutil.rmtree(path, ignore_errors=True)


def _all_pages(client, **params):
    rows, cursor, pages = [], None, 0
    while True:
        query = {"limit": 50, **params}
        if cursor:
            query["cursor"] = cursor
        body = client.get("/api/leads", params=query).json()
        assert len(body["leads"]) <= 50
        rows += body["leads"]
        pages += 1
        cursor = body["next_cursor"]
        if not cursor:
            return rows, body, pages


def test_without_a_limit_the_answer_is_unchanged(client):
    import leads
    assert client.get("/api/leads").json() == {"status": "success", "leads": leads.list_leads()}


def test_the_pages_put_together_are_the_whole_list_in_its_order(client):
    import leads
    rows, body, pages = _all_pages(client)
    assert pages > 3
    assert rows == leads.list_leads(), "a page boundary lost, repeated or reordered a lead"
    assert body["matching"] == body["total"] == len(rows)


def test_a_stage_is_filtered_on_the_server(client):
    import leads
    rows, body, _pages = _all_pages(client, status="Connected")
    assert rows == leads.list_leads("Connected")
    assert body["matching"] == len(rows) < body["total"]


def test_the_search_box_matches_the_start_of_words_on_the_server(client):
    rows, body, _pages = _all_pages(client, q="head grow")
    assert rows and body["matching"] == len(rows)
    assert all("head of growth" in (r["headline"] or "").lower() for r in rows)
    # Accents folded, as the box did in the browser.
    names = {r["full_name"] for r in _all_pages(client, q="zoe olander")[0]}
    assert names == {"Zoë Ölander"}
    assert _all_pages(client, q="%")[1]["matching"] == 0


def test_one_page_is_small(client):
    body = client.get("/api/leads", params={"limit": 200}).json()
    assert len(body["leads"]) == 200 and body["next_cursor"]
    assert len(client.get("/api/leads", params={"limit": 10 ** 9}).json()["leads"]) <= 2000


# ---------------------------------------------------------------------------
# The screen asks for pages
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def studio_url():
    pytest.importorskip("playwright.sync_api")
    if not os.path.isfile(BUILT_UI):
        pytest.skip("the UI is not built (npm --prefix studio/ui run build)")
    import uvicorn
    saved = {k: os.environ.get(k) for k in ("INOX_HYDRA_HOME", "INOX_DEMO_DATA")}
    home = tempfile.mkdtemp(prefix="inox_qc2_r3_leads_ui_")
    os.environ["INOX_HYDRA_HOME"] = home
    os.environ.pop("INOX_DEMO_DATA", None)
    from database import init_db, get_db
    from app import app
    init_db()
    conn = get_db()
    qc2_r3_data.build(conn, leads=520, interactions=600)
    conn.close()
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    server = uvicorn.Server(uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="error"))
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
    thread.join(timeout=5)
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    shutil.rmtree(home, ignore_errors=True)


def test_the_screen_reads_a_page_and_asks_for_the_next(studio_url):
    from playwright.sync_api import expect, sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(service_workers="block", viewport={"width": 1280, "height": 860})
            page = ctx.new_page()
            asked = []
            page.on("request", lambda r: asked.append(r.url) if "/api/leads?" in r.url or r.url.endswith("/api/leads")
                    else None)
            page.goto(studio_url, wait_until="networkidle")
            page.click('button[aria-label="Leads"]')
            page.wait_for_selector('section[aria-label="Lead stream"]')
            rows = page.locator("[data-lead-id]")
            expect(rows).to_have_count(200)
            assert asked and all("limit=" in url for url in asked), f"the whole list was asked for: {asked}"
            assert "520" in page.locator('section[aria-label="Lead stream"] p').first.inner_text()

            page.get_by_role("button", name="Show more").click()
            expect(rows).to_have_count(400)
            assert any("cursor=" in url for url in asked), asked

            page.get_by_label("Find a lead").fill("zoe olander")
            expect(rows.first).to_contain_text("Zoë Ölander")
            assert any("q=zoe+olander" in url or "q=zoe%20olander" in url for url in asked), asked
            names = set(rows.all_inner_texts())
            assert all("Zoë Ölander" in name for name in names), names
            ctx.close()
        finally:
            browser.close()
