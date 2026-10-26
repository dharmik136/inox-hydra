"""
Item 28: LinkedIn's analytics export, imported with a preview, every figure
exact and named as the export's.
==========================================================================

Built against LinkedIn's documented export (Help a701208, a704175) and this
track's best understanding of its sheets, in tests/linkedin_export_fixtures.py,
because no real file has been supplied. So the rules held here are the ones
that do not depend on the guess being right:

- nothing is written until the creator has previewed it;
- a sheet or a column the studio does not know is reported as not
  recognised and left out, never guessed at;
- two tables side by side are read each by its own post column, never a row
  across both;
- a day the analytics page already read is kept as it was read;
- a top post's figure that covers only part of its life is not a reading;
- a date whose day and month order cannot be told is no date;
- what is written carries the source linkedin_export and precision exact;
- nothing opens a connection.

Strict Invariants:
- Zero em-dashes.
"""

import io
import os
import re
import sys
import zipfile
from datetime import date, datetime, timezone
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

import analytics_export  # noqa: E402
import linkedin_export_fixtures as fx  # noqa: E402

EXPORTED_AT = datetime(2026, 10, 26, 9, 30, tzinfo=timezone.utc)


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path / "studio"))
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "user"))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    os.makedirs(tmp_path / "user" / "Downloads")
    from database import get_db, init_db
    from app import app
    init_db()
    conn = get_db()
    with conn:
        for urn, day in ((fx.INSIDE, date(2026, 10, 2)), (fx.BEFORE, date(2026, 9, 20))):
            conn.execute(
                "INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, first_seen_at, "
                "last_seen_at) VALUES (?, ?, ?, 'urn', ?, ?)",
                (urn, f"A post of mine from {day}", f"{day.isoformat()}T12:00:00+00:00",
                 "2026-10-26T00:00:00+00:00", "2026-10-26T00:00:00+00:00"))
    conn.close()
    return {"client": TestClient(app), "downloads": tmp_path / "user" / "Downloads", "db": get_db}


def _upload(client, data, name=fx.DASHBOARD_NAME, modified=EXPORTED_AT):
    headers = {"Content-Type": "application/octet-stream", "X-Export-Name": quote(name)}
    if modified is not None:
        headers["X-File-Modified"] = str(int(modified.timestamp() * 1000))
    return client.post("/api/v1/analytics-export/upload", content=data, headers=headers)


def _rows(get_db, sql, params=()):
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def _sheet(preview, name):
    return next(s for s in preview["sheets"] if s["name"] == name)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def test_the_reader_reads_shared_strings_inline_strings_and_numbers(tmp_path):
    for inline in (False, True):
        path = tmp_path / f"book-{inline}.xlsx"
        path.write_bytes(fx.build([("ENGAGEMENT", [["Date", "Impressions"], ["10/2/2026", 1200]])], inline=inline))
        sheets = analytics_export.read_workbook(str(path))["sheets"]
        assert sheets[0]["name"] == "ENGAGEMENT"
        assert sheets[0]["rows"] == [["Date", "Impressions"], ["10/2/2026", 1200]]


def test_the_preview_names_every_sheet_and_writes_nothing(studio):
    data = fx.build(fx.dashboard_sheets() + [("Sheet9", [["Something", "else"], [1, 2]])])
    res = _upload(studio["client"], data)
    assert res.status_code == 200, res.text
    preview = res.json()
    kinds = {s["name"]: s["kind"] for s in preview["sheets"]}
    assert kinds == {"DISCOVERY": "discovery", "ENGAGEMENT": "engagement", "TOP POSTS": "top_posts",
                     "FOLLOWERS": "followers", "DEMOGRAPHICS": "demographics", "Sheet9": None}
    unknown = _sheet(preview, "Sheet9")
    assert unknown["importable"] is False and unknown["note"].startswith("Not recognised:")
    assert "Something, else" in unknown["note"], "the preview does not show what it could not read"
    assert _sheet(preview, "DEMOGRAPHICS")["importable"] is False
    assert preview["range"] == {"start": "2026-09-26", "end": "2026-10-25", "from": "the file's name"}
    assert preview["verified_against_real_file"] is False
    assert "not yet" in preview["verification"]
    assert _rows(studio["db"], "SELECT * FROM analytics_daily") == []
    assert _rows(studio["db"], "SELECT * FROM post_metric_observations") == []


def test_an_unknown_column_is_listed_as_not_recognised_and_left_out(studio):
    preview = _upload(studio["client"], fx.build(fx.dashboard_sheets(extra_engagement_column=True))).json()
    engagement = _sheet(preview, "ENGAGEMENT")
    assert engagement["not_recognised"] == ["Engagement rate"]
    assert "Not recognised, and left out: Engagement rate." in engagement["note"]
    studio["client"].post("/api/v1/analytics-export/import", json={"source": preview["source"]})
    row = _rows(studio["db"], "SELECT engagement_rate FROM analytics_daily WHERE date = '2026-10-02'")[0]
    assert row["engagement_rate"] is None, "a column the studio does not know was written somewhere"


# ---------------------------------------------------------------------------
# Writing the days
# ---------------------------------------------------------------------------

def test_the_days_land_exact_with_their_source(studio):
    preview = _upload(studio["client"], fx.build(fx.dashboard_sheets())).json()
    res = studio["client"].post("/api/v1/analytics-export/import", json={"source": preview["source"]})
    assert res.status_code == 200, res.text
    rows = _rows(studio["db"], "SELECT * FROM analytics_daily ORDER BY date")
    assert len(rows) == 30
    first = rows[0]
    assert first["date"] == "2026-09-26"
    assert (first["impressions"], first["reactions"], first["new_followers"]) == (1000, 20, 0)
    assert (first["source"], first["precision"], first["period_label"]) == ("linkedin_export", "exact", "1d")
    # What the export does not carry stays unmeasured, never the table's 0.
    assert first["comments"] is None and first["shares"] is None and first["engagement_rate"] is None
    last = rows[-1]
    assert last["followers"] == 1543, "the follower total on the day it names was not kept"
    assert res.json()["summary"]["days"] == {"added": 30, "updated": 0, "kept_as_read": 0}


def test_a_day_the_analytics_page_read_is_kept_as_it_was_read(studio):
    conn = studio["db"]()
    with conn:
        conn.execute("INSERT INTO analytics_daily (date, impressions, reactions, followers, source, period_label, "
                     "precision) VALUES ('2026-10-02', 1200, 31, 1500, 'observed', '1d', 'rounded')")
    conn.close()
    preview = _upload(studio["client"], fx.build(fx.dashboard_sheets())).json()
    summary = studio["client"].post("/api/v1/analytics-export/import",
                                    json={"source": preview["source"]}).json()["summary"]
    assert summary["days"]["kept_as_read"] == 1
    row = _rows(studio["db"], "SELECT * FROM analytics_daily WHERE date = '2026-10-02'")[0]
    assert (row["impressions"], row["reactions"], row["source"], row["precision"]) == (1200, 31, "observed", "rounded")
    assert row["new_followers"] is None, "the export wrote into a row another source owns"


def test_importing_twice_adds_nothing_twice(studio):
    for _ in range(2):
        preview = _upload(studio["client"], fx.build(fx.dashboard_sheets())).json()
        summary = studio["client"].post("/api/v1/analytics-export/import",
                                        json={"source": preview["source"]}).json()["summary"]
    assert summary["days"] == {"added": 0, "updated": 30, "kept_as_read": 0}
    assert len(_rows(studio["db"], "SELECT date FROM analytics_daily")) == 30
    assert len(_rows(studio["db"], "SELECT id FROM post_metric_observations")) == 1


def test_only_the_ticked_sheets_are_imported(studio):
    preview = _upload(studio["client"], fx.build(fx.dashboard_sheets())).json()
    studio["client"].post("/api/v1/analytics-export/import",
                          json={"source": preview["source"], "include": ["TOP POSTS"]})
    assert _rows(studio["db"], "SELECT * FROM analytics_daily") == []
    assert len(_rows(studio["db"], "SELECT * FROM post_metric_observations")) == 1


# ---------------------------------------------------------------------------
# Writing the posts
# ---------------------------------------------------------------------------

def test_tables_side_by_side_are_read_each_by_its_own_post_column(studio):
    """
    The engagements table lists INSIDE first; the impressions table lists
    BEFORE first. Read across the row, INSIDE would have been credited with
    BEFORE's 3,000 impressions.
    """
    preview = _upload(studio["client"], fx.build(fx.dashboard_sheets())).json()
    summary = studio["client"].post("/api/v1/analytics-export/import",
                                    json={"source": preview["source"]}).json()["summary"]["TOP POSTS"]
    reading = _rows(studio["db"], "SELECT * FROM post_metric_observations WHERE activity_urn = ?", (fx.INSIDE,))
    assert len(reading) == 1
    assert (reading[0]["impressions"], reading[0]["engagements"]) == (2100, 45)
    assert reading[0]["reactions"] is None, "a total was written as reactions"
    assert reading[0]["source"] == "linkedin_export"
    assert reading[0]["observed_at"].startswith("2026-10-25T23:59:59")
    assert 23 * 24 < reading[0]["age_hours"] < 24 * 24
    assert summary["added"] == 1 and summary["published_outside_the_range"] == 1 and summary["not_yours"] == 1
    assert summary["not_yours_because"] == analytics_export.NOT_YOURS


def test_a_post_published_before_the_range_gets_no_reading(studio):
    preview = _upload(studio["client"], fx.build(fx.dashboard_sheets())).json()
    studio["client"].post("/api/v1/analytics-export/import", json={"source": preview["source"]})
    assert _rows(studio["db"], "SELECT * FROM post_metric_observations WHERE activity_urn = ?", (fx.BEFORE,)) == []


def test_without_a_range_no_top_post_is_read(studio):
    """No range in the name and no daily sheet: whether a figure covers a post's life cannot be told."""
    sheets = [s for s in fx.dashboard_sheets() if s[0] == "TOP POSTS"]
    preview = _upload(studio["client"], fx.build(sheets), name="analytics.xlsx").json()
    summary = studio["client"].post("/api/v1/analytics-export/import",
                                    json={"source": preview["source"]}).json()["summary"]["TOP POSTS"]
    assert "could not be read" in summary["left_out"]
    assert _rows(studio["db"], "SELECT * FROM post_metric_observations") == []


def test_a_posts_own_export_is_read_from_its_label_and_value_rows(studio):
    preview = _upload(studio["client"], fx.build(fx.post_sheets()), name="PostAnalytics_export.xlsx").json()
    performance = _sheet(preview, "PERFORMANCE")
    assert performance["kind"] == "post" and performance["importable"] is True
    assert "Post Publish Time" in performance["not_recognised"]
    assert set(performance["left_out"]) == {"Profile viewers from this post", "Followers gained from this post"}
    summary = studio["client"].post("/api/v1/analytics-export/import",
                                    json={"source": preview["source"]}).json()["summary"]["PERFORMANCE"]
    assert summary == {"added": 1, "not_yours": 0}
    reading = _rows(studio["db"], "SELECT * FROM post_metric_observations WHERE activity_urn = ?", (fx.INSIDE,))[0]
    assert (reading["impressions"], reading["members_reached"], reading["reactions"], reading["comments"],
            reading["reposts"], reading["saves"], reading["sends"]) == (2100, 1500, 40, 5, 2, 4, 1)
    assert reading["observed_at"].startswith("2026-10-26T09:30"), "the reading is not dated when it was exported"


def test_a_posts_own_export_with_no_date_of_export_is_not_imported(studio):
    preview = _upload(studio["client"], fx.build(fx.post_sheets()), name="PostAnalytics_export.xlsx",
                      modified=None).json()
    performance = _sheet(preview, "PERFORMANCE")
    assert performance["importable"] is False
    assert "cannot be dated" in performance["note"]


def test_a_posts_own_export_that_does_not_say_which_post_is_not_imported(studio):
    preview = _upload(studio["client"], fx.build(fx.post_sheets(with_url=False)),
                      name="PostAnalytics_export.xlsx").json()
    assert "does not say which post" in _sheet(preview, "PERFORMANCE")["note"]
    named = fx.INSIDE.rsplit(":", 1)[1]
    preview = _upload(studio["client"], fx.build(fx.post_sheets(with_url=False)),
                      name=f"PostAnalytics_{named}.xlsx").json()
    assert _sheet(preview, "PERFORMANCE")["importable"] is True, "the post's number in the file's name was not read"


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

def _engagement(dates):
    return [("ENGAGEMENT", [["Date", "Impressions", "Engagements"]] + [[d, 100, 5] for d in dates])]


def test_slashed_dates_whose_order_cannot_be_told_are_refused(studio):
    preview = _upload(studio["client"], fx.build(_engagement(["10/5/2026"])), name="analytics.xlsx").json()
    engagement = _sheet(preview, "ENGAGEMENT")
    assert engagement["importable"] is False
    assert "whether the day or the month comes first" in engagement["note"]


def test_the_rows_or_the_range_settle_the_order(studio):
    # Rows a day apart only month first: October 4, 5, 6.
    preview = _upload(studio["client"], fx.build(_engagement(["10/4/2026", "10/5/2026", "10/6/2026"])),
                      name="analytics.xlsx").json()
    assert preview["range"]["start"] == "2026-10-04" and preview["range"]["end"] == "2026-10-06"
    # One row, settled by the range in the file's name.
    preview = _upload(studio["client"], fx.build(_engagement(["10/5/2026"]))).json()
    assert _sheet(preview, "ENGAGEMENT")["importable"] is True
    # A part over 12 settles it day first.
    preview = _upload(studio["client"], fx.build(_engagement(["13/10/2026", "14/10/2026"])),
                      name="analytics.xlsx").json()
    assert preview["range"]["start"] == "2026-10-13"


def test_excel_serial_dates_and_iso_dates_are_read(studio):
    serial = (date(2026, 10, 2) - date(1899, 12, 30)).days
    preview = _upload(studio["client"], fx.build(_engagement([serial, "2026-10-03"])), name="analytics.xlsx").json()
    assert preview["range"]["start"] == "2026-10-02" and preview["range"]["end"] == "2026-10-03"


# ---------------------------------------------------------------------------
# What is refused
# ---------------------------------------------------------------------------

def test_a_file_that_is_not_a_spreadsheet_is_refused_with_a_sentence(studio):
    res = _upload(studio["client"], b"not a spreadsheet at all")
    assert res.status_code == 400 and "not an .xlsx spreadsheet" in res.json()["detail"]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><workbook/>')
    res = _upload(studio["client"], buffer.getvalue())
    assert res.status_code == 400 and "markup a spreadsheet never does" in res.json()["detail"]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", "<a>" + "x" * 5_000_000 + "</a>")
    res = _upload(studio["client"], buffer.getvalue())
    assert res.status_code == 400 and "far larger than a spreadsheet should be" in res.json()["detail"]


def test_an_upload_that_fails_to_read_leaves_no_copy(studio):
    _upload(studio["client"], b"not a spreadsheet at all")
    assert os.listdir(analytics_export._uploads_dir()) == []


NETWORK = re.compile(r"^\s*(?:import|from)\s+(?:requests|httpx|socket|urllib\.request|http\.client|aiohttp)\b", re.M)


EGRESS_CALL = re.compile(r"\b\w*egress\w*\.(?:require|guard)\(|^\s*(?:from\s+\S+\s+)?import\s+egress\b|"
                         r"import egress as", re.M)


def _opens_connections(source):
    """An outbound library imported, or a request put through the egress guard: either means it leaves."""
    return bool(NETWORK.search(source)) or bool(EGRESS_CALL.search(source))


def test_the_import_opens_no_connection():
    for path in ("studio/backend/analytics_export.py", "studio/backend/routers/analytics_export_routes.py"):
        with io.open(os.path.join(REPO_ROOT, path), encoding="utf-8") as handle:
            assert not _opens_connections(handle.read()), f"{path} reaches for the network"


def test_the_no_connection_guard_can_fail():
    assert _opens_connections("import requests\n")
    assert _opens_connections("from urllib.request import urlopen\n")
    assert _opens_connections("    _egress.require(url, 'ingress')\n")
    assert not _opens_connections("import zipfile\n")
    assert not _opens_connections('"""Zero egress: reads a local file."""\n')


# ---------------------------------------------------------------------------
# Finding it, and the record
# ---------------------------------------------------------------------------

def test_downloads_is_looked_in_only_after_the_creator_says_they_exported(studio):
    (studio["downloads"] / fx.DASHBOARD_NAME).write_bytes(fx.build(fx.dashboard_sheets()))
    (studio["downloads"] / "budget.xlsx").write_bytes(b"x")
    state = studio["client"].get("/api/v1/analytics-export").json()
    assert state["found"] == [] and state["waiting"] is False
    state = studio["client"].post("/api/v1/analytics-export/requested").json()
    assert [hit["name"] for hit in state["found"]] == [fx.DASHBOARD_NAME]
    source = "downloads:" + state["found"][0]["path"]
    studio["client"].post("/api/v1/analytics-export/import", json={"source": source})
    state = studio["client"].get("/api/v1/analytics-export").json()
    assert state["waiting"] is False and state["last_import"]["file"] == fx.DASHBOARD_NAME
    assert os.path.exists(studio["downloads"] / fx.DASHBOARD_NAME), "a file in Downloads was moved or deleted"


def test_the_discovery_totals_are_kept_with_the_record_not_plotted(studio):
    preview = _upload(studio["client"], fx.build(fx.dashboard_sheets())).json()
    summary = studio["client"].post("/api/v1/analytics-export/import",
                                    json={"source": preview["source"]}).json()["summary"]
    assert summary["DISCOVERY"]["kept"]["impressions"] == 31435
    assert summary["DISCOVERY"]["kept"]["members_reached"] == 18002


def test_deleting_everything_forgets_the_record_and_the_phones_requests(studio):
    preview = _upload(studio["client"], fx.build(fx.dashboard_sheets())).json()
    studio["client"].post("/api/v1/analytics-export/import", json={"source": preview["source"]})
    import desk_requests
    conn = studio["db"]()
    desk_requests.record(conn, fx.INSIDE)
    conn.close()
    import onboarding
    onboarding.forget_identity()
    assert analytics_export.imports() == []
    assert _rows(studio["db"], "SELECT * FROM desk_requests") == []
    assert _rows(studio["db"], "SELECT * FROM post_metric_observations") == []


# ---------------------------------------------------------------------------
# What the creator reads
# ---------------------------------------------------------------------------

def _read(path):
    with io.open(os.path.join(REPO_ROOT, path), encoding="utf-8") as handle:
        return handle.read()


def test_the_help_says_it_has_not_been_checked_against_a_real_file():
    article = _read("docs/help/import-linkedins-analytics-export.md")
    assert "Verified against a real file: not yet." in article
    assert "not recognised" in article


def test_the_policy_says_what_the_import_keeps_and_that_nothing_leaves():
    policy = " ".join(_read("docs/PRIVACY_POLICY.md").split())
    assert "LinkedIn's analytics export" in policy
    assert "nothing in the file is sent anywhere" in policy


def test_setup_and_analytics_carry_the_two_entry_points():
    setup = _read("studio/ui/src/components/OnboardingSurface.tsx")
    assert "<AnalyticsExportImport" in setup
    analytics = _read("studio/ui/src/components/AnalyticsSurface.tsx")
    assert 'href="#/setup"' in analytics and "analytics export" in analytics.lower()


# ---------------------------------------------------------------------------
# Review round, SF-4: the 1904 date system
# ---------------------------------------------------------------------------

def test_a_workbook_in_the_1904_date_system_lands_on_its_own_days(studio):
    """
    The reviewer's file: serials 44853 to 44855 in a workbook marked
    date1904 are 20 to 22 October 2026. Read in the 1900 system they were
    imported four years and a day early, as exact figures.
    """
    sheets = [("ENGAGEMENT", [["Date", "Impressions", "Engagements"], [44853, 100, 5], [44854, 110, 6],
                              [44855, 120, 7]])]
    preview = _upload(studio["client"], fx.build(sheets, date1904=True), name="analytics.xlsx").json()
    assert preview["range"] == {"start": "2026-10-20", "end": "2026-10-22", "from": "the days in the file"}
    studio["client"].post("/api/v1/analytics-export/import", json={"source": preview["source"]})
    days = [r["date"] for r in _rows(studio["db"], "SELECT date FROM analytics_daily ORDER BY date")]
    assert days == ["2026-10-20", "2026-10-21", "2026-10-22"]


def test_the_1900_system_is_still_read_as_before(studio):
    sheets = [("ENGAGEMENT", [["Date", "Impressions", "Engagements"], [46315, 100, 5], [46317, 120, 7]])]
    preview = _upload(studio["client"], fx.build(sheets), name="analytics.xlsx").json()
    assert preview["range"]["start"] == "2026-10-20" and preview["range"]["end"] == "2026-10-22"

