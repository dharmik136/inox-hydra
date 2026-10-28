"""
Item 28: LinkedIn's analytics export, imported with a preview, every figure
exact and named as the export's.
==========================================================================

Built against LinkedIn's documented export (Help a701208, a704175) and this
track's best understanding of its sheets, in tests/linkedin_export_fixtures.py.
A real aggregate export met the importer on 2026-10-28; its sheet names and
its demographics header are in the fixtures exactly, its values are not. So
the rules held here are the ones that do not depend on the guess being right:

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
    assert preview["verified_against_real_file"] is True
    assert "2026-10-28" in preview["verification"] and "post's own export has not been checked" in preview["verification"]
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


def test_the_help_says_when_it_was_checked_and_that_the_unknown_is_left_out():
    article = _read("docs/help/import-linkedins-analytics-export.md")
    assert "Verified against a real file: yes, on 2026-10-28" in article
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


# ---------------------------------------------------------------------------
# Review round, SF-5: a damaged or unusual member is a sentence, never a 500
# ---------------------------------------------------------------------------

def _patched_central_directory(data, offset, value):
    """Every central directory entry's two bytes at `offset` set to `value` (8 = flags, 10 = method)."""
    out = bytearray(data)
    at = out.find(b"PK\x01\x02")
    while at != -1:
        out[at + offset:at + offset + 2] = value.to_bytes(2, "little")
        at = out.find(b"PK\x01\x02", at + 4)
    return bytes(out)


def _damaged(kind):
    import zipfile as _zip
    stored = fx.build(fx.dashboard_sheets(), compression=_zip.ZIP_STORED)
    if kind == "bad_crc":
        at = stored.find(b"<sheetData>")
        return stored[:at] + b"<sheetDatA>" + stored[at + len(b"<sheetData>"):]
    if kind == "encrypted":
        return _patched_central_directory(stored, 8, 0x0001)
    return _patched_central_directory(stored, 10, 99)


@pytest.mark.parametrize("kind, words", [
    ("bad_crc", "damaged"),
    ("encrypted", "password"),
    ("unsupported_method", "packed in a way"),
])
def test_a_damaged_or_unusual_member_is_refused_with_a_sentence(studio, kind, words):
    res = _upload(studio["client"], _damaged(kind))
    assert res.status_code == 400, f"{kind}: {res.status_code} {res.text[:200]}"
    assert words in res.json()["detail"], res.json()["detail"]
    assert os.listdir(analytics_export._uploads_dir()) == [], "the uploaded copy was left behind"


# ---------------------------------------------------------------------------
# Review round, notes N-9 to N-15
# ---------------------------------------------------------------------------

def _zip_with(members):
    import zipfile as _zip
    buffer = io.BytesIO()
    with _zip.ZipFile(buffer, "w", _zip.ZIP_STORED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_a_part_larger_than_a_real_export_needs_is_refused(studio):
    """N-9: a part far below the old 40 MB cap still cost the reader a gigabyte; real exports' parts are small."""
    data = _zip_with({"xl/workbook.xml": os.urandom(11 * 1024 * 1024)})
    res = _upload(studio["client"], data)
    assert res.status_code == 400 and "far larger than a spreadsheet should be" in res.json()["detail"]


def test_a_part_not_written_in_utf8_is_refused(studio):
    """N-10: the DOCTYPE check read bytes, so a UTF-16 part slipped past it to the parser."""
    workbook = '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE w [<!ENTITY a "x">]><workbook/>'.encode("utf-16")
    res = _upload(studio["client"], _zip_with({"xl/workbook.xml": workbook}))
    assert res.status_code == 400 and "UTF-8" in res.json()["detail"]


@pytest.mark.parametrize("text, expected", [
    ("1,234", 1234), ("12,345,678", 12345678), ("1234", 1234),
    ("1,2,3", None), ("12,34", None), ("1.234", None), ("1.2K", None), ("-5", None),
])
def test_a_figure_with_commas_is_read_only_as_thousands(text, expected):
    """N-11: every comma was stripped, so "1,2,3" read as 123."""
    assert analytics_export._count(text) == expected


def test_an_empty_workbook_says_so(studio):
    """N-12: a workbook with no sheets previewed as a blank list."""
    empty = _zip_with({"xl/workbook.xml": '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                                         '<sheets/></workbook>'})
    res = _upload(studio["client"], empty)
    assert res.status_code == 400 and "no sheets" in res.json()["detail"]


def test_a_sheet_whose_part_is_missing_is_listed_not_dropped(studio):
    """N-12: a sheet the workbook names but the file does not hold vanished from the preview."""
    data = fx.build(fx.dashboard_sheets())
    import zipfile as _zip
    source = _zip.ZipFile(io.BytesIO(data))
    kept = {name: source.read(name) for name in source.namelist() if name != "xl/worksheets/sheet2.xml"}
    preview = _upload(studio["client"], _zip_with(kept)).json()
    engagement = _sheet(preview, "ENGAGEMENT")
    assert engagement["importable"] is False and "holds no contents for it" in engagement["note"]


def test_a_top_post_reading_is_never_dated_after_now(studio):
    """N-14: a range ending today dated its readings 23:59:59 today, later than now."""
    from datetime import datetime as _dt, timezone as _tz
    today = _dt.now(_tz.utc).date()
    conn = studio["db"]()
    with conn:
        conn.execute("UPDATE own_posts SET published_at = ? WHERE activity_urn = ?",
                     (f"{today.isoformat()}T00:00:01+00:00", fx.INSIDE))
    conn.close()
    sheets = [s for s in fx.dashboard_sheets() if s[0] == "TOP POSTS"]
    name = f"Content_{today.isoformat()}_{today.isoformat()}_SampleCreator.xlsx"
    preview = _upload(studio["client"], fx.build(sheets), name=name).json()
    studio["client"].post("/api/v1/analytics-export/import", json={"source": preview["source"]})
    reading = _rows(studio["db"], "SELECT observed_at FROM post_metric_observations WHERE activity_urn = ?",
                    (fx.INSIDE,))[0]
    assert _dt.fromisoformat(reading["observed_at"]) <= _dt.now(_tz.utc)


def test_the_setup_block_does_not_state_the_unverified_layout_as_fact():
    """N-15: the intro said, as fact, what the file holds; that is the studio's best understanding."""
    block = _read("studio/ui/src/components/AnalyticsExportImport.tsx")
    assert "the file it writes holds your impressions, engagements and new followers by day" not in block
    assert "help says the file holds your impressions and engagements" in block
    assert "preview.recognised" in block, "a file with nothing recognised is not said to be so"


def test_a_copy_older_than_a_day_is_removed_when_the_studio_starts(studio):
    """N-13: the policy says a copy chosen by hand is kept for a day at most; it was swept only when Setup opened."""
    import time as _time
    old = os.path.join(analytics_export._uploads_dir(), "0" * 32 + ".xlsx")
    with open(old, "wb") as handle:
        handle.write(b"x")
    two_days_ago = _time.time() - 2 * 24 * 3600
    os.utime(old, (two_days_ago, two_days_ago))
    import app as app_module
    with TestClient(app_module.app):
        pass
    assert not os.path.exists(old), "a copy older than a day outlived the studio's start"



# ---------------------------------------------------------------------------
# The real aggregate export (2.10.1): MOST RECENT POSTS and the demographics
# ---------------------------------------------------------------------------

def _hold(studio, *posts):
    """The creator's recorded posts, as the posts import or the archive would hold them."""
    conn = studio["db"]()
    with conn:
        for urn, day in posts:
            conn.execute(
                "INSERT OR REPLACE INTO own_posts (activity_urn, text, published_at, published_at_source, "
                "first_seen_at, last_seen_at) VALUES (?, ?, ?, 'urn', ?, ?)",
                (urn, f"A post of mine from {day}", f"{day.isoformat()}T12:00:00+00:00",
                 "2026-10-28T00:00:00+00:00", "2026-10-28T00:00:00+00:00"))
    conn.close()


def _demographics(studio, source=None):
    sql = ("SELECT observed_on, activity_urn, source, dimension, label, percentage "
           "FROM audience_demographic_readings")
    if source:
        return _rows(studio["db"], sql + " WHERE source = ? ORDER BY dimension, label", (source,))
    return _rows(studio["db"], sql + " ORDER BY source, dimension, label")


def test_the_aggregate_exports_sheets_are_each_recognised(studio):
    preview = _upload(studio["client"], fx.build(fx.aggregate_sheets()), name=fx.AGGREGATE_NAME).json()
    kinds = {s["name"]: s["kind"] for s in preview["sheets"]}
    assert kinds == {"DISCOVERY": "discovery", "ENGAGEMENT": "engagement", "MOST RECENT POSTS": "recent_posts",
                     "TOP POSTS": "top_posts", "FOLLOWERS": "followers",
                     "AUDIENCE DEMOGRAPHICS": "audience_demographics",
                     "CONTENT DEMOGRAPHICS": "content_demographics"}
    assert preview["range"] == {"start": "2025-09-24", "end": "2026-10-28", "from": "the file's name"}
    for name in ("MOST RECENT POSTS", "AUDIENCE DEMOGRAPHICS", "CONTENT DEMOGRAPHICS"):
        assert _sheet(preview, name)["importable"] is True, _sheet(preview, name)["note"]


def test_most_recent_posts_are_read_like_top_posts(studio):
    """
    The real file's MOST RECENT POSTS was refused as a post's own export with
    three rows. It is a list of the creator's recent posts, one per row: each
    is matched to a recorded post by its link, never creating one.
    """
    _hold(studio, (fx.RECENT_A, date(2026, 10, 20)), (fx.RECENT_B, date(2026, 10, 10)))
    end = date(2026, 10, 25)
    name = f"AggregateAnalytics_Sample Creator_2025-09-24_{end.isoformat()}.xlsx"
    preview = _upload(studio["client"], fx.build(fx.aggregate_sheets(end=end)), name=name).json()
    res = studio["client"].post("/api/v1/analytics-export/import",
                                json={"source": preview["source"], "include": ["MOST RECENT POSTS"]})
    summary = res.json()["summary"]["MOST RECENT POSTS"]
    assert summary["added"] == 2 and summary["not_yours"] == 1
    readings = {r["activity_urn"]: r for r in _rows(
        studio["db"], "SELECT * FROM post_metric_observations WHERE source = 'linkedin_export'")}
    assert set(readings) == {fx.RECENT_A, fx.RECENT_B}, "a post the studio does not hold was written"
    a = readings[fx.RECENT_A]
    assert (a["impressions"], a["engagements"], a["precision"]) == (1830, 61, "exact")
    assert a["observed_at"].startswith("2026-10-25T23:59:59"), "not dated by the export's end"
    held = [r["activity_urn"] for r in _rows(studio["db"], "SELECT activity_urn FROM own_posts")]
    assert fx.STRANGER not in held, "a post was created from the export"


def test_a_list_of_posts_without_their_links_is_not_matched_by_anything_else(studio):
    """A row is one of the creator's posts only by its link: not by its date, not by its figures."""
    recent = [["Post publish date", "Impressions", "Engagements"], ["10/20/2026", 1830, 61]]
    sheets = [(n, recent if n == "MOST RECENT POSTS" else rows) for n, rows in fx.aggregate_sheets()]
    preview = _upload(studio["client"], fx.build(sheets), name=fx.AGGREGATE_NAME).json()
    sheet = _sheet(preview, "MOST RECENT POSTS")
    assert sheet["importable"] is False and "without a link to each post" in sheet["note"]


def test_the_audience_and_content_demographics_are_kept_apart_and_dated(studio):
    preview = _upload(studio["client"], fx.build(fx.aggregate_sheets()), name=fx.AGGREGATE_NAME).json()
    res = studio["client"].post("/api/v1/analytics-export/import", json={
        "source": preview["source"], "include": ["AUDIENCE DEMOGRAPHICS", "CONTENT DEMOGRAPHICS"]})
    summary = res.json()["summary"]
    assert summary["AUDIENCE DEMOGRAPHICS"]["shares_kept"] == 5
    assert summary["AUDIENCE DEMOGRAPHICS"]["left_out_as_bounds"] == 1
    assert summary["AUDIENCE DEMOGRAPHICS"]["dated"] == "2026-10-28"
    audience = _demographics(studio, "linkedin_export_audience")
    content = _demographics(studio, "linkedin_export_content")
    assert len(audience) == 5 and len(content) == 3
    assert {r["observed_on"] for r in audience + content} == {"2026-10-28"}, "not dated by the export's end"
    assert {r["activity_urn"] for r in audience + content} == {""}, "an account's demographics were filed under a post"
    first = next(r for r in audience if r["label"] == "Software Engineer")
    assert (first["dimension"], first["percentage"]) == ("job titles", 12.0)
    assert next(r for r in audience if r["label"] == "Product Manager")["percentage"] == 6.5
    assert not [r for r in audience if r["label"] == "10,001+ employees"], "a bound (< 1%) was stored as a figure"
    assert next(r for r in content if r["label"] == "Mumbai")["percentage"] == 14.0


def test_importing_the_demographics_twice_keeps_one_reading_a_day(studio):
    for _ in range(2):
        preview = _upload(studio["client"], fx.build(fx.aggregate_sheets()), name=fx.AGGREGATE_NAME).json()
        studio["client"].post("/api/v1/analytics-export/import", json={
            "source": preview["source"], "include": ["AUDIENCE DEMOGRAPHICS", "CONTENT DEMOGRAPHICS"]})
    assert len(_demographics(studio)) == 8


def test_a_later_export_ending_the_same_day_replaces_that_days_shares_rather_than_mixing_them(studio):
    """A 7-day and a 365-day export can end on the same day; one day's set is one export's."""
    preview = _upload(studio["client"], fx.build(fx.aggregate_sheets()), name=fx.AGGREGATE_NAME).json()
    studio["client"].post("/api/v1/analytics-export/import",
                          json={"source": preview["source"], "include": ["CONTENT DEMOGRAPHICS"]})
    shorter = [["Job titles", "Founder", "11%"], ["Locations", "Pune", "8%"]]
    name = "AggregateAnalytics_Sample Creator_2026-10-22_2026-10-28.xlsx"
    preview = _upload(studio["client"], fx.build(fx.aggregate_sheets(content=shorter)), name=name).json()
    studio["client"].post("/api/v1/analytics-export/import",
                          json={"source": preview["source"], "include": ["CONTENT DEMOGRAPHICS"]})
    got = {(r["dimension"], r["label"]): r["percentage"] for r in _demographics(studio, "linkedin_export_content")}
    assert got == {("job titles", "Founder"): 11.0, ("locations", "Pune"): 8.0}


def test_no_post_screen_shows_the_accounts_demographics(studio):
    """Only per-post readers read this table, by post; the export's rows are the account's."""
    _hold(studio, (fx.RECENT_A, date(2026, 10, 20)), (fx.RECENT_B, date(2026, 10, 10)))
    preview = _upload(studio["client"], fx.build(fx.aggregate_sheets()), name=fx.AGGREGATE_NAME).json()
    studio["client"].post("/api/v1/analytics-export/import", json={"source": preview["source"]})
    assert len(_demographics(studio)) == 8
    import onboarding
    for row in _rows(studio["db"], "SELECT activity_urn FROM own_posts"):
        assert onboarding.post_demographics(row["activity_urn"]) == [], "a post's screen shows the account's shares"


def test_a_share_stored_as_a_percent_formatted_number_is_read_as_a_percentage(studio):
    shares = [["Job titles", "Designer", fx.Pct(0.25)], ["Locations", "Pune", fx.Pct(0.075)]]
    preview = _upload(studio["client"], fx.build(fx.aggregate_sheets(audience=shares)), name=fx.AGGREGATE_NAME).json()
    studio["client"].post("/api/v1/analytics-export/import",
                          json={"source": preview["source"], "include": ["AUDIENCE DEMOGRAPHICS"]})
    got = {r["label"]: r["percentage"] for r in _demographics(studio, "linkedin_export_audience")}
    assert got == {"Designer": 25.0, "Pune": 7.5}


def test_plain_numbers_that_could_be_fractions_or_percentages_are_not_guessed(studio):
    """0.3 with no percent sign and no percent format could be 30 percent or 0.3 percent."""
    shares = [["Job titles", "Designer", 0.3], ["Locations", "Pune", 0.2]]
    preview = _upload(studio["client"], fx.build(fx.aggregate_sheets(audience=shares)), name=fx.AGGREGATE_NAME).json()
    sheet = _sheet(preview, "AUDIENCE DEMOGRAPHICS")
    assert sheet["importable"] is False and "30 percent or 0.3 percent" in sheet["note"]
    shares = [["Job titles", "Designer", 31], ["Locations", "Pune", 0.4]]
    preview = _upload(studio["client"], fx.build(fx.aggregate_sheets(audience=shares)), name=fx.AGGREGATE_NAME).json()
    assert _sheet(preview, "AUDIENCE DEMOGRAPHICS")["importable"] is True, "a column with 31 in it is percentages"


def test_deleting_everything_forgets_the_exports_demographics(studio):
    preview = _upload(studio["client"], fx.build(fx.aggregate_sheets()), name=fx.AGGREGATE_NAME).json()
    studio["client"].post("/api/v1/analytics-export/import", json={"source": preview["source"]})
    assert _demographics(studio)
    import onboarding
    onboarding.forget_identity()
    assert _demographics(studio) == []


def test_the_preview_and_the_help_say_a_real_export_was_checked():
    import analytics_export as module
    assert module.VERIFIED_AGAINST_REAL_FILE is True
    assert "2026-10-28" in module.VERIFICATION and "AUDIENCE DEMOGRAPHICS" in module.VERIFICATION
    article = " ".join(_read("docs/help/import-linkedins-analytics-export.md").split())
    assert "Verified against a real file: yes, on 2026-10-28" in article
    for sheet in ("DISCOVERY", "ENGAGEMENT", "MOST RECENT POSTS", "TOP POSTS", "FOLLOWERS",
                  "AUDIENCE DEMOGRAPHICS", "CONTENT DEMOGRAPHICS"):
        assert sheet in article, f"the help does not name {sheet}"


def test_the_policy_names_the_demographics_the_export_keeps():
    policy = " ".join(_read("docs/PRIVACY_POLICY.md").split())
    assert "the demographics of your audience and of who engaged with your posts" in policy
