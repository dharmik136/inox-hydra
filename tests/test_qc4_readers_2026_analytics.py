"""
The creator analytics reader on LinkedIn's 2026 content page (2.10.1).
=====================================================================

On the owner's own /analytics/creator/content/ (2026-10-28) the reader
reported drift ["metric_cards"]: it looked for card classes LinkedIn now
hashes. The page names its sections ("Content performance", "Discovery",
"Engagement"); in the first two each figure comes before its label ("270"
then "Impressions", "19" then "Members reached"), in Engagement each row is
the label then its figure, and the network split is two rows of a label and
a percentage. The range is read from the page's own words ("Past 28 days"),
and a page that names none is kept as a window the page did not name.

The page fixtures are rebuilt from the owner's sanitised outline with
invented figures, and run the shipped scripts in headless Chromium through
qc_f3_pages.py. The storage tests below them need no browser.
"""

import json
import os
import shutil
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

ME = "ada-example"
SCRIPTS = ("voyager_schema.js", "content.js", "own_pages.js", "own_insights.js")
SIGNED_IN = {"signedInVanity": ME}


@pytest.fixture(scope="module")
def pages():
    # Imported here, so a run without a browser skips these and nothing else.
    pytest.importorskip("playwright.sync_api")
    from qc_f3_pages import Pages
    p = Pages()
    yield p
    p.close()


def page_html(body, title, lang="en"):
    from qc_f3_pages import page_html as html
    return html(body, title=title, lang=lang)


def _captures(pages, page, extractor):
    return [c for c in pages.sent(page, "/api/v1/bridge/capture") if c.get("extractor") == extractor]


def _analytics_page(range_words="<span>Past 28 days</span>", comparison="vs. prior 28 days",
                    split=("Impressions from people in your network", "Out of network"), shares=("91%", "9%")):
    return f"""<main><div componentkey="pg"><div data-testid="lazy-column" data-component-type="LazyColumn">
 <div><div><div role="button"><div><input type="checkbox"><label><svg></svg>{range_words}</label></div></div></div>
      <a><span><svg></svg><span>Export</span></span></a></div>
 <div><div componentkey="s1"><div><div><div><p>Content performance</p><div><div><button aria-label="Learn more" componentkey="b1"></button></div></div></div></div>
   <div><div><div><div role="button"><div><input type="checkbox"><label><svg></svg></label></div></div></div>
     <div><div><p><span>310</span></p></div><p>Impressions</p></div>
     <div><div><svg></svg><p>65%</p></div><p>{comparison}</p></div>
     <div role="region" aria-label="Impressions over the selected range"><div><div><h6>Daily</h6></div></div>
       <svg aria-label="Impressions chart"><g><text>0</text><text>100</text><text>200</text><text>300</text></g></svg></div>
   </div></div></div></div></div>
 <div><div componentkey="s2"><div><div><div><p>Discovery</p><div><div><button aria-label="Learn more" componentkey="b2"></button></div></div></div></div>
   <div><div><div><p><span>310</span></p></div><p>Impressions</p></div>
     <div componentkey="sp"><div>
       <div><svg></svg><div><p>{split[0]}</p></div><div><p>{shares[0]}</p></div></div>
       <div><svg></svg><div><p>{split[1]}</p></div><div><p>{shares[1]}</p></div></div></div></div>
     <div componentkey="mr"><div><div><p><span>23</span></p></div><p>Members reached</p></div></div>
     <div componentkey="nt"><div><svg></svg></div><div><p>Members reached counts each person once.</p></div></div>
   </div></div></div></div>
 <div><div componentkey="s3"><div><div><div><p>Engagement</p><div><div><button aria-label="Learn more" componentkey="b3"></button></div></div></div></div>
   <div><div><div><p><span>18</span></p></div><p>Social engagements</p></div>
     <div><div><svg></svg></div><div><p>Reactions</p></div><div><p>11</p></div></div>
     <div><div><svg></svg></div><div><p>Comments</p></div><div><p>4</p></div></div>
     <div><div><svg></svg></div><div><p>Reposts</p></div><div><p>2</p></div></div>
     <div><div><svg></svg></div><div><p>Saves</p></div><div><p>1</p></div></div>
     <div><div><svg></svg></div><div><p>Sends on LinkedIn</p></div><div><p>0</p></div></div>
   </div></div></div></div>
</div></div></main>"""


def _analytics(pages, body, run=4000):
    page = pages.open("/analytics/creator/content/", page_html(body, title="Analytics | LinkedIn", lang="en"),
                      scripts=SCRIPTS, storage=SIGNED_IN)
    page.clock.run_for(run)
    return page, pages.sent(page, "/api/analytics/ingest")


def test_the_creator_analytics_page_is_read_by_its_sections_words(pages):
    page, sent = _analytics(pages, _analytics_page())
    assert len(sent) == 1, sent
    body = sent[0]
    assert body["author"] == ME and body["period_label"] == "28d"
    day = body["series"][0]
    assert day["period_label"] == "28d" and day["precision"] == "exact"
    assert (day["impressions"], day["members_reached"]) == (310, 23)
    assert (day["reactions"], day["comments"], day["shares"], day["saves"], day["sends"]) == (11, 4, 2, 1, 0)
    assert (day["in_network_pct"], day["out_of_network_pct"]) == (91, 9)
    assert "followers" not in day or day["followers"] is None, "the content page shows no follower count"
    assert not _captures(pages, page, "analytics")[-1]["drift"]


def test_the_change_and_the_chart_are_never_figures(pages):
    _page, sent = _analytics(pages, _analytics_page())
    day = sent[0]["series"][0]
    values = {v for k, v in day.items() if k not in ("date", "period_label", "precision")}
    assert 65 not in values and 300 not in values, "the 65% change and the chart's axis are not figures"


def test_a_24_hour_range_is_a_daily_reading(pages):
    _page, sent = _analytics(pages, _analytics_page(range_words="<span>Past 24 hours</span>", comparison="vs. prior day"))
    assert sent[0]["period_label"] == "1d" and sent[0]["series"][0]["period_label"] == "1d"


def test_the_range_named_only_by_the_comparison_is_that_range(pages):
    _page, sent = _analytics(pages, _analytics_page(range_words="", comparison="vs. prior 7 days"))
    assert sent[0]["period_label"] == "7d"


def test_a_range_the_page_does_not_name_is_kept_as_unnamed(pages):
    _page, sent = _analytics(pages, _analytics_page(range_words="", comparison="vs. the period before"))
    assert sent[0]["period_label"] == "unnamed"


def test_a_split_whose_labels_are_not_read_is_not_sent_and_is_not_drift(pages):
    page, sent = _analytics(pages, _analytics_page(split=("First group", "Second group")))
    day = sent[0]["series"][0]
    assert day.get("in_network_pct") is None and day.get("out_of_network_pct") is None
    assert not _captures(pages, page, "analytics")[-1]["drift"]


def test_a_split_that_does_not_add_up_is_not_sent(pages):
    _page, sent = _analytics(pages, _analytics_page(shares=("91%", "91%")))
    assert sent[0]["series"][0].get("in_network_pct") is None


def test_an_analytics_page_with_none_of_its_words_reports_drift_once_it_has_looked_again(pages):
    page, sent = _analytics(pages, "<main><div><p>Something LinkedIn has not shown before</p><p>42</p></div></main>")
    assert sent == [] and _captures(pages, page, "analytics") == [], "the page may still be drawing"
    page.clock.run_for(12000)
    assert pages.sent(page, "/api/analytics/ingest") == []
    assert _captures(pages, page, "analytics")[-1]["drift"] == ["metric_cards"]


def test_a_content_page_that_draws_its_sections_late_is_read_when_they_arrive(pages):
    late = json.dumps(_analytics_page())
    body = ("<main></main><script>setTimeout(() => { document.querySelector('main').outerHTML = " + late +
            "; }, 5000);</script>")
    page, _sent = _analytics(pages, body, run=12000)
    sent = pages.sent(page, "/api/analytics/ingest")
    assert len(sent) == 1 and sent[0]["series"][0]["impressions"] == 310
    assert all(not c["drift"] for c in _captures(pages, page, "analytics")), "a page still drawing is not drift"


def test_headings_with_no_figure_beside_them_report_drift_by_label(pages):
    body = (_analytics_page().replace("<span>310</span>", "<span>a lot</span>")
            .replace("<p>Impressions</p>", "<p>Views of your posts</p>"))
    page, sent = _analytics(pages, body, run=16000)
    assert _captures(pages, page, "analytics")[-1]["drift"] == ["metric_labels"]
    # What the page did show beside its labels is still kept.
    assert sent and sent[0]["series"][0]["members_reached"] == 23 and sent[0]["series"][0]["impressions"] is None


def test_an_open_range_menu_reads_the_range_it_marks_chosen(pages):
    menu = ('<div role="listbox"><div role="option">Past 7 days</div>'
            '<div role="option" aria-selected="true">Past 90 days</div><div role="option">Past 365 days</div></div>')
    _page, sent = _analytics(pages, _analytics_page(range_words="", comparison="vs. the period before").replace(
        "<a><span><svg></svg><span>Export</span></span></a>", menu + "<a><span><svg></svg><span>Export</span></span></a>"))
    assert sent[0]["period_label"] == "90d"


def test_a_note_or_a_table_cell_is_never_the_range(pages):
    body = _analytics_page(range_words="").replace(
        "<p>Members reached counts each person once.</p>",
        "<p>May take up to 48 hours.</p><table><tr><td>2 days</td></tr></table>")
    _page, sent = _analytics(pages, body)
    assert sent[0]["period_label"] == "28d", "the comparison names the range; the note and the cell do not"


def test_a_custom_range_of_dates_is_unrecognised_and_never_a_window(pages):
    _page, sent = _analytics(pages, _analytics_page(range_words="<span>Oct 1, 2026 - Oct 19, 2026</span>",
                                                    comparison="vs. prior 19 days"))
    assert sent[0]["period_label"] == "unrecognised"


def test_another_creator_analytics_page_without_these_words_is_not_drift(pages):
    page = pages.open("/analytics/creator/audience/", page_html(
        "<main><div><p>Something LinkedIn has not shown before</p><p>42</p></div></main>",
        title="Analytics | LinkedIn"), scripts=SCRIPTS, storage=SIGNED_IN)
    page.clock.run_for(4000)
    assert pages.sent(page, "/api/analytics/ingest") == []
    reports = _captures(pages, page, "analytics")
    assert reports and not reports[-1]["drift"]


# ---------------------------------------------------------------------------
# What the studio keeps: a day for 24 hours, a window for any other range
# ---------------------------------------------------------------------------

DAY = "2031-04-14"
CONTENT = {"impressions": 310, "members_reached": 23, "reactions": 11, "comments": 4, "shares": 2, "saves": 1,
           "sends": 0, "in_network_pct": 91, "out_of_network_pct": 9}


@pytest.fixture
def home(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_readers_2026_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def client(home):
    from fastapi.testclient import TestClient
    import app as app_module
    c = TestClient(app_module.app)
    c.post("/api/v1/identity/observe", json={"vanity": ME, "self_evidence": ["owner_edit_controls"],
                                             "display_name": "Ada Example"})
    c.post("/api/v1/identity/confirm", json={"vanity": ME})
    return c


def _row(table, period=None):
    from database import get_db
    conn = get_db()
    try:
        query = f"SELECT * FROM {table} WHERE date = ?" + (" AND period_label = ?" if period else "")
        row = conn.execute(query, (DAY, period) if period else (DAY,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _ingest(period, **overrides):
    from linkedin_client import linkedin_client
    figures = {**CONTENT, **overrides}
    return linkedin_client.ingest_analytics_payload({"period_label": period, "precision": "exact", "series": [
        {"date": DAY, "period_label": period, "precision": "exact", **figures}]})


def test_the_migration_is_named_for_the_figures_it_adds(home):
    """Found by name, never by number: the coordinator renumbers at integration."""
    import migrations
    from database import get_db
    mine = [m for m in migrations.MIGRATIONS if "network split from the creator analytics page" in m[1].lower()]
    assert len(mine) == 1
    conn = get_db()
    try:
        daily = {r[1] for r in conn.execute("PRAGMA table_info(analytics_daily)")}
        windows = {r[1] for r in conn.execute("PRAGMA table_info(analytics_windows)")}
    finally:
        conn.close()
    assert {"unique_members_reached", "saves", "sends", "in_network_pct", "out_of_network_pct"} <= daily
    assert {"members_reached", "saves", "sends", "in_network_pct", "out_of_network_pct"} <= windows


def test_a_24_hour_reading_is_that_days_row_with_every_figure(home):
    result = _ingest("1d")
    assert result["status"] == "success"
    day = _row("analytics_daily")
    assert (day["impressions"], day["unique_members_reached"], day["reactions"], day["comments"], day["shares"],
            day["saves"], day["sends"], day["in_network_pct"], day["out_of_network_pct"], day["period_label"]) == (
        310, 23, 11, 4, 2, 1, 0, 91, 9, "1d")
    assert _row("analytics_windows") is None, "a day is not a window"
    # A later read that did not show the split keeps the one the day holds.
    _ingest("1d", in_network_pct=None, out_of_network_pct=None, saves=None)
    day = _row("analytics_daily")
    assert (day["in_network_pct"], day["saves"]) == (91, 1)


def test_a_28_day_reading_is_kept_as_that_window_never_as_a_day(home):
    result = _ingest("28d")
    assert result["status"] == "window_mismatch" and result["windows_saved"] == 1
    window = _row("analytics_windows", "28d")
    assert (window["impressions"], window["members_reached"], window["reactions"], window["comments"],
            window["shares"], window["saves"], window["sends"], window["in_network_pct"],
            window["out_of_network_pct"]) == (310, 23, 11, 4, 2, 1, 0, 91, 9)
    day = _row("analytics_daily")
    assert day is None or day["impressions"] is None, "a 28 day figure is not today's"


def test_a_window_the_page_did_not_name_is_kept_as_one(home):
    result = _ingest("unnamed")
    assert result["status"] == "window_mismatch" and result["windows_saved"] == 1
    assert "did not name" in result["message"]
    assert _row("analytics_windows", "unnamed")["impressions"] == 310
    day = _row("analytics_daily")
    assert day is None or day["impressions"] is None


def test_a_share_that_is_no_share_is_not_kept(home):
    _ingest("28d", in_network_pct=140, out_of_network_pct=-40)
    window = _row("analytics_windows", "28d")
    assert window["in_network_pct"] is None and window["out_of_network_pct"] is None


def test_the_content_page_reading_reaches_the_studio_and_its_overview(client):
    answer = client.post("/api/analytics/ingest", json={
        "author": ME, "period_label": "unnamed", "precision": "exact",
        "series": [{"date": DAY, "period_label": "unnamed", "precision": "exact", **CONTENT}]})
    assert answer.status_code == 200 and answer.json()["windows_saved"] == 1
    windows = client.get("/api/analytics/overview?range=30d").json()["windows"]
    assert [(w["period_label"], w["members_reached"], w["saves"], w["in_network_pct"]) for w in windows] == [
        ("unnamed", 23, 1, 91)]
