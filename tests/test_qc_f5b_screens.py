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
    _confirm()  # analytics must name a confirmed account (PLATFORM-04)
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
    _confirm()  # analytics must name a confirmed account (PLATFORM-04)
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
    assert client.post("/api/analytics/ingest", json={"series": series, "author": ME}).status_code == 200


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
    assert client.post("/api/analytics/ingest", json={"series": [row], "author": ME}).status_code == 200
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


def test_a_range_change_keeps_the_screen_and_reads_the_posts_once(studio):
    """AUDIENCE-22"""
    _days(studio["client"], 34, impressions=1000)
    _own_posts(studio["client"], [{"text": "Why sourdough needs patience", "reactions": 40}])
    reads = []
    studio["page"].on("request", lambda req: reads.append(req.url) if "/api/analytics/posts" in req.url else None)
    page = _open(studio, "Analytics")
    page.locator("tbody tr", has_text="Why sourdough needs patience").first.wait_for()
    page.evaluate("""() => { window.__blanked = false; new MutationObserver(() => {
        if (document.body.innerText.includes('LOADING ANALYTICS')) window.__blanked = true; })
        .observe(document.body, {subtree: true, childList: true, characterData: true}); }""")
    for target in ("7d", "90d", "30d"):
        page.get_by_role("button", name=target, exact=True).click()
        page.wait_for_function(
            "document.querySelector('[aria-label=\"Date range\"]').getAttribute('aria-busy') === 'false'")
    page.wait_for_load_state("networkidle")
    assert not page.evaluate("window.__blanked"), "a range change blanked the screen to LOADING ANALYTICS"
    assert len(reads) == 1, f"the posts were read {len(reads)} times for one visit"
    assert not studio["errors"], studio["errors"]


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

def _engaged(lead_id, name, urn, *kinds, score=80.0):
    from database import get_db
    conn = get_db()
    with conn:
        conn.execute("INSERT OR IGNORE INTO leads (id, name, full_name, icp_score) VALUES (?, ?, ?, ?)",
                     (lead_id, name, name, score))
        for kind in kinds:
            conn.execute("INSERT INTO lead_interactions (lead_id, post_urn, interaction_type) VALUES (?, ?, ?)",
                         (lead_id, urn, kind))
    conn.close()


def test_topic_attribution_counts_people_and_no_share_passes_100(studio):
    """AUDIENCE-12"""
    urns = _own_posts(studio["client"], [{"text": "Why we moved our database to Postgres", "reactions": 50}])
    for k in range(3):
        _engaged(f"lead-founder-{k}", f"Founder {k}", urns[0], "COMMENT", "LIKE")
    _engaged("lead-student", "A Student", urns[0], "LIKE", score=10.0)
    page = _open(studio, "Patterns")
    page.wait_for_selector("text=Which topics bring qualified pipeline")
    row = page.locator("section", has_text="Which topics").locator("tbody tr").first
    cells = [c.strip() for c in row.locator("td").all_inner_texts()]
    assert cells[1:] == ["1", "50", "4", "3", "75%"], cells
    assert "600" not in page.inner_text("body")
    assert not studio["errors"], studio["errors"]


MARCH_2024 = 1709283600000
AUGUST_2026 = 1785574800000


def test_a_contrast_mixed_up_with_time_is_not_shown_as_a_finding(studio):
    """AUDIENCE-13"""
    client = studio["client"]
    _own_posts(client, [{"text": f"Weekly notes {i}\nSome thoughts #leadership", "reactions": 300 + i}
                        for i in range(9)], year_ms=MARCH_2024)
    _own_posts(client, [{"text": f"Field notes {i}\nSome thoughts without tags", "reactions": 100 + i}
                        for i in range(10)], year_ms=AUGUST_2026)
    page = _open(studio, "Patterns")
    page.wait_for_selector("text=Binary feature comparisons")
    row = page.locator("section", has_text="Binary feature comparisons").locator("li", has_text="Contains hashtags")
    text = row.inner_text()
    assert "MOSTLY 2024 AGAINST MOSTLY 2026: MIXED UP WITH WHEN YOU POSTED, NOT A FINDING" in text, text
    assert row.locator(".text-signal-green-text").count() == 0, "the confounded ratio is still coloured as a finding"
    assert not studio["errors"], studio["errors"]


def test_topics_are_the_creators_own_words_and_say_so(studio):
    """AUDIENCE-27"""
    texts = ["Are you pricing your croissants right?", "Croissant Friday recap", "Why I write every morning",
             "What nobody tells you about early mornings", "Short one today.", "On saying no to wholesale"]
    _own_posts(studio["client"], [{"text": text, "reactions": 10 + i} for i, text in enumerate(texts)])
    page = _open(studio, "Patterns")
    page.wait_for_selector("text=Which topics bring qualified pipeline")
    section = page.locator("section", has_text="Which topics bring qualified pipeline")
    topics = [t.strip() for t in section.locator("tbody tr td:first-child").all_inner_texts()]
    assert set(topics) == {"Croissant", "Morning", "Other posts"}, topics
    assert "keywords and hashtags that recur across your own posts" in section.inner_text()
    assert "keyword grouping, not a reading of what a post means" in section.inner_text()
    assert not studio["errors"], studio["errors"]


def _archive_posts(n):
    """Posts as the archive import writes them: dated, with text, and no figures at all."""
    import datetime as _dt
    from database import get_db
    conn = get_db()
    with conn:
        for i in range(n):
            when = _dt.datetime(2021, 2, 4, 9, tzinfo=_dt.timezone.utc) + _dt.timedelta(days=i)
            conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, "
                         "first_seen_at, last_seen_at) VALUES (?, ?, ?, 'archive', '2026-10-01', '2026-10-01')",
                         (f"urn:li:activity:{(int(when.timestamp() * 1000) << 22) + i}",
                          f"Synthetic sample post {i}", when.isoformat()))
    conn.close()


def test_posts_and_patterns_name_missing_figures_not_post_age(studio):
    """SETUP-23"""
    _archive_posts(30)
    page = _open(studio, "Posts")
    page.wait_for_selector("h1:has-text('What worked, and who it brought')")
    body = page.inner_text("body")
    assert "Not enough settled posts yet" not in body
    assert ("No usual yet: 30 of your posts older than 7 days have no reactions, comments or impressions "
            "recorded, because LinkedIn's archive does not include them.") in body
    page.locator("nav[aria-label='Studio sections'] button[aria-label='Patterns']").first.click()
    page.wait_for_selector("h1:has-text('What your own posts suggest')")
    body = page.inner_text("body")
    assert "across your 0 posts at least a week old." not in body
    assert "30 MORE POSTS ARE LEFT OUT: NO REACTIONS ARE RECORDED FOR THEM, AS LINKEDIN’S ARCHIVE DOES NOT" in body
    assert "SAME PERIOD ON BOTH SIDES" not in body, "the period was blamed for a lack of figures"
    assert not studio["errors"], studio["errors"]


# ---------------------------------------------------------------------------
# Outbound
# ---------------------------------------------------------------------------

def _archive_outbound(reactions, comments, authored=0):
    """Outbound rows as the archive import writes them, with no post author; `authored` more with one."""
    from database import get_db
    conn = get_db()
    with conn:
        for i in range(reactions):
            conn.execute("INSERT INTO outbound_engagements (target_activity_urn, kind, reaction_kind, my_text_key, "
                         "first_seen_at, last_seen_at) VALUES (?, 'reaction', 'like', '', '2025-01-01', '2025-01-01')",
                         (f"urn:li:activity:73{i:017d}",))
        for i in range(comments):
            conn.execute("INSERT INTO outbound_engagements (target_activity_urn, kind, my_text, my_text_key, "
                         "first_seen_at, last_seen_at) VALUES (?, 'comment', ?, ?, '2025-01-01', '2025-01-01')",
                         (f"urn:li:activity:74{i:017d}", f"Great point {i}", f"great point {i}"))
        for i in range(authored):
            conn.execute("INSERT INTO outbound_engagements (target_activity_urn, target_author, kind, my_text_key, "
                         "first_seen_at, last_seen_at) VALUES (?, 'Grace Hopper', 'reaction', '', '2026-10-01', "
                         "'2026-10-01')", (f"urn:li:activity:75{i:017d}",))
    conn.close()


def test_outbound_after_an_archive_import_says_what_was_imported(studio):
    """SETUP-10"""
    _archive_outbound(25, 15)
    page = _open(studio, "Outbound")
    page.wait_for_selector("text=Where your attention goes")
    body = page.inner_text("body")
    assert "None of your reactions or comments have been imported yet" not in body
    assert "25 reactions and 15 comments are imported" in body, body
    assert "does not name the author" in body
    assert "Posts you reacted to" in body and "Comments you left" in body
    assert not studio["errors"], studio["errors"]


def test_outbound_counts_the_rows_it_cannot_rank_yet(studio):
    """SETUP-10"""
    _archive_outbound(25, 15, authored=3)
    page = _open(studio, "Outbound")
    page.wait_for_selector("text=Most engaged with")
    assert "40 more, from LinkedIn’s archive or without an author recorded, are not ranked" in page.inner_text("body")
    assert not studio["errors"], studio["errors"]


AXE_JS = os.path.join(REPO_ROOT, "studio", "ui", "node_modules", "axe-core", "axe.min.js")


@pytest.mark.parametrize("width", [1440, 390])
def test_patterns_can_be_scrolled_from_the_keyboard(studio, width):
    """AUDIENCE-25"""
    if not os.path.exists(AXE_JS):
        pytest.skip("axe-core is not installed with the UI dependencies")
    urns = _own_posts(studio["client"], [{"text": f"Croissant notes {i}\n" + "A longer line. " * 40, "reactions": 10 + i}
                                         for i in range(12)])
    _engaged("lead-founder-0", "Founder 0", urns[0], "COMMENT")
    page = studio["page"]
    page.set_viewport_size({"width": width, "height": 844})
    page = _open(studio, "Patterns")
    page.wait_for_selector("text=Which topics bring qualified pipeline")
    page.add_script_tag(path=AXE_JS)
    flagged = page.evaluate("""async () => {
        const r = await axe.run(document, { runOnly: ['scrollable-region-focusable'] });
        return r.violations.flatMap(v => v.nodes.map(n => n.target.join(' ')));
    }""")
    assert flagged == [], f"regions a keyboard cannot scroll: {flagged}"
    assert not studio["errors"], studio["errors"]
