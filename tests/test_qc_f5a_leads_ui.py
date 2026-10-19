"""
The Leads screen, driven in a browser against a sandboxed studio.
================================================================

Each test is one finding:

  - AUDIENCE-14: the dossier can edit a lead's notes and forget the person.
  - AUDIENCE-19: times are the creator's own, not UTC printed as local.
  - AUDIENCE-20: a lead scored zero says 0, not "Not scored".
  - AUDIENCE-23: the stream can be searched and filtered, and does not draw
    thousands of rows at once.
  - UX-09: at phone width a chosen lead's dossier is on screen, with a way back.

The server runs in this process on a free loopback port, in a home of its own.
Contexts block service workers: the studio's worker hides requests from
Playwright and from the sandbox.
"""

import os
import shutil
import socket
import sqlite3
import sys
import tempfile
import threading
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
BUILT_UI = os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")

FILLERS = 260


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _seed(db_path):
    conn = sqlite3.connect(db_path)
    rows = [
        # id, name, headline, company, status, lead_status, icp, urn, created_at
        ("lead-asha", "Asha Rao", "Founder at Crumb Co", "Crumb Co", "Meeting Booked", "CONVERTED", 75.0,
         "https://www.linkedin.com/in/asha-rao-ui", "2026-10-19 04:43:00"),
        ("lead-rahul", "Rahul Student", "Student at IIT", None, "New Lead", "NEW", 0.0,
         "https://www.linkedin.com/in/rahul-student-ui", "2026-10-18 10:00:00"),
        ("lead-manual", "Manual Person", "Added by hand", None, "New Lead", "NEW", 0.0, None, "2026-10-17 10:00:00"),
        ("lead-zoe", "Zoë Ångström", "Baker", None, "Connected", "ENGAGED", 40.0,
         "https://www.linkedin.com/in/zoe-ui", "2026-10-16 10:00:00"),
    ]
    rows += [
        (f"lead-filler-{i:03d}", f"Filler {i:03d}", "Someone", None, "New Lead", "NEW", 20.0,
         f"https://www.linkedin.com/in/filler-{i}", "2026-09-01 10:00:00")
        for i in range(FILLERS)
    ]
    conn.executemany(
        "INSERT INTO leads (id, name, full_name, headline, company, status, lead_status, icp_score, linkedin_urn, "
        "profile_url, engagement_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Commented', ?)",
        [(r[0], r[1], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[7], r[8]) for r in rows],
    )
    conn.execute(
        "INSERT INTO lead_interactions (lead_id, interaction_type, comment_text, interacted_at, comment_key) "
        "VALUES ('lead-asha', 'COMMENT', 'We lost a fifth of our flour to this.', '2026-10-19 04:43:00', 'k-asha')"
    )
    conn.execute(
        "INSERT INTO lead_interactions (lead_id, interaction_type, interacted_at, comment_key) "
        "VALUES ('lead-rahul', 'LIKE', '2026-10-18 10:00:00', '')"
    )
    conn.execute(
        "INSERT INTO lead_stage_events (lead_id, from_status, to_status, changed_at) "
        "VALUES ('lead-asha', 'New Lead', 'Meeting Booked', '2026-10-18T19:30:00+00:00')"
    )
    conn.commit()
    conn.close()


@pytest.fixture(scope="module")
def studio_url():
    if not os.path.isfile(BUILT_UI):
        pytest.skip("the UI is not built (npm --prefix studio/ui run build)")
    import uvicorn

    saved = {k: os.environ.get(k) for k in ("INOX_HYDRA_HOME", "INOX_DEMO_DATA")}
    home = tempfile.mkdtemp(prefix="inox_leads_ui_")
    os.environ["INOX_HYDRA_HOME"] = home
    os.environ.pop("INOX_DEMO_DATA", None)
    from database import init_db
    import paths
    from app import app

    init_db()
    _seed(paths.get_db_path())

    port = _free_port()
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


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        instance = p.chromium.launch(headless=True)
        yield instance
        instance.close()


def _leads_page(browser, url, **context):
    ctx = browser.new_context(service_workers="block", **({"viewport": {"width": 1280, "height": 860}} | context))
    page = ctx.new_page()
    page.goto(url, wait_until="networkidle")
    page.click('button[aria-label="Leads"]')
    page.wait_for_selector('section[aria-label="Lead stream"]')
    return ctx, page


def _open(page, name):
    page.locator('section[aria-label="Lead stream"] button', has_text=name).first.click()
    expect(page.locator("article h2")).to_have_text(name)


def test_the_stream_can_be_searched_and_filtered(browser, studio_url):
    ctx, page = _leads_page(browser, studio_url)
    try:
        rows = page.locator("[data-lead-id]")
        assert rows.count() <= 200, f"{rows.count()} rows drawn at once"
        assert page.get_by_role("button", name="Show more").is_visible()

        page.get_by_label("Find a lead").fill("crumb")
        expect(rows).to_have_count(1)
        assert "Asha Rao" in rows.first.inner_text()

        page.get_by_label("Find a lead").fill("zoe angstrom")
        expect(rows).to_have_count(1)

        page.get_by_label("Find a lead").fill("")
        page.get_by_label("Stage").select_option("Meeting Booked")
        expect(rows).to_have_count(1)
        assert "Asha Rao" in rows.first.inner_text()
    finally:
        ctx.close()


def test_at_phone_width_the_dossier_is_on_screen(browser, studio_url):
    ctx, page = _leads_page(browser, studio_url, viewport={"width": 375, "height": 812})
    try:
        page.locator('section[aria-label="Lead stream"] button', has_text="Asha Rao").first.click()
        heading = page.locator("article h2")
        expect(heading).to_have_text("Asha Rao")
        box = heading.bounding_box()
        assert box and box["width"] > 0 and box["x"] >= 0 and box["x"] + box["width"] <= 375, box
        pipeline = page.get_by_role("button", name="Outreach Sent").bounding_box()
        assert pipeline and pipeline["x"] + pipeline["width"] <= 375, pipeline

        page.get_by_role("button", name="Back to the lead stream").click()
        expect(page.locator('section[aria-label="Lead stream"]')).to_be_visible()
    finally:
        ctx.close()
