"""
The archive's saved items, follows, votes, articles and reposts land; searches only behind a tick.
==================================================================================================

Cycle 4, track 7, batch 2 of the personalised daily ideas report, and
decision 6. The importer read eight categories and discarded Saved Items,
Member Follows, Company Follows, Votes, Articles, Instant Reposts (which the
report's batch 2 lists beside them) and Search Queries, which
are the creator's own record of what they chose to see and keep, under the
same sanctioned export. They land now, each row with the file it came from
and the import date, in a table of their own. Search Queries, the most
personal file in the export, is imported only when the creator ticks it at
import time, and is unticked by default.

What the importer does not do: guess about a file that is absent (nothing
is written and nothing is listed), guess columns (a file whose columns are
not the known ones is reported, not read), or invent a date (an unreadable
date stays empty).
"""

import io
import os
import sqlite3
import sys
import zipfile

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import archive_import  # noqa: E402
import paths  # noqa: E402
from app import app  # noqa: E402
from database import init_db  # noqa: E402

SHARES = (
    "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl,Visibility\n"
    '2024-03-05 10:22:11,https://www.linkedin.com/feed/update/urn%3Ali%3Ashare%3A7170000000000000001,'
    '"Compilers are for people.",,,MEMBER_NETWORK\n'
)
PROFILE = (
    "First Name,Last Name,Maiden Name,Address,Birth Date,Headline,Summary,Industry,Zip Code,Geo Location,"
    "Twitter Handles,Websites,Instant Messengers\n"
    "Grace,Hopper,,,,Rear Admiral,Taught machines to read English.,Defense,,Arlington,,,\n"
)
SAVED = (
    "Date,URL\n"
    "2026-10-14 09:10:00,https://www.linkedin.com/posts/someone_hiring-activity-7380000000000000001-abcd\n"
    "not a date,https://www.linkedin.com/pulse/pricing-without-a-recruiter-someone/\n"
)
MEMBER_FOLLOWS = "Date,Status,Full Name\n2025-02-01 08:00:00,Active,Example Member\n"
COMPANY_FOLLOWS = "Organization,Followed On\nExample Engines,Wed Jan 15 10:00:00 UTC 2025\n"
VOTES = "Date,Link,OptionText\n2026-09-02 12:00:00,https://www.linkedin.com/feed/update/urn:li:activity:7360000000000000009,Hire slowly\n"
ARTICLES = "Date,Title,Link\n2025-06-01 07:00:00,Why compilers are for people,https://www.linkedin.com/pulse/why-compilers-grace/\n"
SEARCHES = "Time,Search Query\n2026-10-20 18:00:00,hiring without a recruiter\n2026-10-21 18:00:00,example member\n"
REPOSTS = "Date,Link\n2026-08-01 09:00:00,https://www.linkedin.com/feed/update/urn:li:activity:7350000000000000003\n"

FULL = {
    "Shares.csv": SHARES, "Profile.csv": PROFILE, "Saved_Items.csv": SAVED, "Member_Follows.csv": MEMBER_FOLLOWS,
    "Company Follows.csv": COMPANY_FOLLOWS, "Votes.csv": VOTES, "Articles.csv": ARTICLES, "SearchQueries.csv": SEARCHES,
    "InstantReposts.csv": REPOSTS,
}


def _archive(members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in members.items():
            archive.writestr(name, text)
    return buffer.getvalue()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path / "studio"))
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "user"))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    os.makedirs(tmp_path / "user" / "Downloads")
    init_db()
    return tmp_path


@pytest.fixture
def client(home):
    return TestClient(app)


def _db():
    conn = sqlite3.connect(paths.get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _upload(client, members=FULL, name="Complete_LinkedInDataExport_10-19-2026.zip"):
    res = client.post("/api/v1/archive/upload", content=_archive(members),
                      headers={"Content-Type": "application/zip", "X-Archive-Name": name})
    assert res.status_code == 200, res.text
    return res.json()


def _import(client, source, include=None):
    payload = {"source": source, "confirm_owner": True}
    if include is not None:
        payload["include"] = include
    res = client.post("/api/v1/archive/import", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


def _records(kind=None):
    conn = _db()
    try:
        if kind:
            return [dict(r) for r in conn.execute("SELECT * FROM archive_records WHERE kind = ? ORDER BY id", (kind,))]
        return [dict(r) for r in conn.execute("SELECT * FROM archive_records ORDER BY id")]
    finally:
        conn.close()


def test_the_preview_lists_the_seven_categories_and_only_searches_are_unticked(client):
    preview = _upload(client)
    by_kind = {f["kind"]: f for f in preview["files"]}
    for kind in ("saved_items", "member_follows", "company_follows", "votes", "articles", "instant_reposts",
                 "search_queries"):
        assert kind in by_kind, f"{kind} is not offered"
        assert by_kind[kind]["importable"], by_kind[kind]
    assert by_kind["search_queries"]["default"] is False
    assert all(by_kind[k]["default"] for k in ("saved_items", "member_follows", "company_follows", "votes", "articles",
                                                "instant_reposts"))
    assert "most personal" in by_kind["search_queries"]["label"]
    # Nothing in the "not read" list is one of the six.
    assert not [o for o in preview["not_imported"] if "Saved" in o["file"] or "Votes" in o["file"]]


def test_each_category_lands_with_its_file_and_the_import_date(client):
    preview = _upload(client)
    summary = _import(client, preview["source"])["summary"]
    for kind in ("saved_items", "member_follows", "company_follows", "votes", "articles", "instant_reposts"):
        assert summary[kind]["added"] >= 1, (kind, summary[kind])
    assert summary["search_queries"] == {"left_out": True}, "searches were imported without a tick"

    rows = _records()
    kinds = {r["kind"] for r in rows}
    assert kinds == {"saved_item", "member_follow", "company_follow", "vote", "article", "instant_repost"}
    conn = _db()
    import_id = conn.execute("SELECT id FROM archive_imports ORDER BY id DESC LIMIT 1").fetchone()[0]
    conn.close()
    for row in rows:
        assert row["source_file"].lower().endswith(".csv"), row
        assert row["imported_at"], row
        assert row["import_id"] == import_id, row
    saved = _records("saved_item")
    assert saved[0]["source_file"] == "Saved_Items.csv"
    assert saved[0]["url"].startswith("https://www.linkedin.com/posts/")
    assert saved[0]["happened_at"] == "2026-10-14T09:10:00+00:00"
    # A saved item is a link and a date; the other person's post is not here.
    assert saved[0]["title"] is None and saved[0]["detail"] is None
    vote = _records("vote")[0]
    assert vote["detail"] == "Hire slowly" and vote["url"].endswith("7360000000000000009")
    article = _records("article")[0]
    assert article["title"] == "Why compilers are for people"
    company = _records("company_follow")[0]
    assert company["name"] == "Example Engines"
    member = _records("member_follow")[0]
    assert member["name"] == "Example Member" and member["detail"] == "Active"
    # A repost is the creator's act: a link and a date, never the post that was reposted.
    repost = _records("instant_repost")[0]
    assert repost["url"].endswith("7350000000000000003") and repost["happened_at"] == "2026-08-01T09:00:00+00:00"
    assert repost["title"] is None and repost["detail"] is None and repost["source_file"] == "InstantReposts.csv"


def test_an_unreadable_date_stays_empty_rather_than_today(client):
    preview = _upload(client)
    _import(client, preview["source"])
    saved = _records("saved_item")
    pulse = next(r for r in saved if "pulse" in r["url"])
    assert pulse["happened_at"] is None


def test_searches_land_only_when_ticked(client):
    preview = _upload(client)
    include = [f["kind"] for f in preview["files"] if f["importable"]]
    assert "search_queries" in include
    summary = _import(client, preview["source"], include)["summary"]
    assert summary["search_queries"]["added"] == 2
    rows = _records("search_query")
    assert sorted(r["detail"] for r in rows) == ["example member", "hiring without a recruiter"]
    assert all(r["source_file"] == "SearchQueries.csv" for r in rows)


def test_an_absent_file_is_neither_guessed_nor_listed(client):
    members = {"Shares.csv": SHARES, "Profile.csv": PROFILE, "Votes.csv": VOTES}
    preview = _upload(client, members)
    kinds = {f["kind"] for f in preview["files"]}
    assert "votes" in kinds and "saved_items" not in kinds and "search_queries" not in kinds
    summary = _import(client, preview["source"])["summary"]
    assert "saved_items" not in summary and "search_queries" not in summary
    assert {r["kind"] for r in _records()} == {"vote"}


def test_unknown_columns_are_reported_not_read(client):
    members = dict(FULL, **{"Saved_Items.csv": "When,Where\n1,2\n"})
    preview = _upload(client, members)
    saved = next(f for f in preview["files"] if f["kind"] == "saved_items")
    assert saved["importable"] is False and "not the ones the studio knows" in saved["note"]
    summary = _import(client, preview["source"])["summary"]
    assert summary["saved_items"]["not_understood"] is True
    assert _records("saved_item") == []


def test_the_same_archive_twice_adds_nothing_twice_and_removal_takes_it_out(client):
    preview = _upload(client)
    first = _import(client, preview["source"])["summary"]
    preview = _upload(client)
    again = _import(client, preview["source"])["summary"]
    assert again["votes"]["added"] == 0 and again["votes"]["already_there"] == first["votes"]["added"]
    assert len(_records()) == sum(first[k]["added"] for k in ("saved_items", "member_follows", "company_follows", "votes",
                                                              "articles", "instant_reposts"))

    res = client.post("/api/v1/archive/undo")
    assert res.status_code == 200, res.text
    # The second import brought nothing, so nothing goes; the first still stands.
    assert len(_records()) > 0
    res = client.post("/api/v1/archive/undo")
    assert res.status_code == 200, res.text
    assert _records() == []


def test_the_module_says_an_absent_file_is_not_guessed_about():
    source = open(os.path.join(os.path.dirname(archive_import.__file__), "archive_import.py"), encoding="utf-8").read()
    assert "A file that is absent is not guessed at" in source
    for kind in ("saved_items", "member_follows", "company_follows", "votes", "articles", "instant_reposts",
                 "search_queries"):
        assert kind in archive_import.FILES and kind in archive_import._IMPORTERS
    assert archive_import.FILES["search_queries"]["default"] is False


def test_the_help_names_the_files_and_the_tick():
    article = open(os.path.join(os.path.dirname(__file__), "..", "docs", "help",
                                "set-up-the-studio-from-your-linkedin.md"), encoding="utf-8").read()
    assert "`Saved_Items.csv`" in article and "`SearchQueries.csv`" in article and "`InstantReposts.csv`" in article
    assert "Unticked unless you tick it" in article
