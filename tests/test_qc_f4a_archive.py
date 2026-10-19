"""
Quality cycle 2026-10, batch F4a: LinkedIn's archive import.
============================================================

Each section holds the regression test for one finding of the Setup review.
Every name and text here is invented.
"""

import io
import os
import sqlite3
import sys
import zipfile
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import archive_import  # noqa: E402
import paths  # noqa: E402
from app import app  # noqa: E402
from database import init_db  # noqa: E402

COMPLETE = "Complete_LinkedInDataExport_10-19-2026.zip"
SHARES_HEADER = "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl,Visibility\n"


def _snow(moment: datetime, salt: int) -> int:
    """A LinkedIn-style id: the high bits are the millisecond timestamp."""
    return (int(moment.timestamp() * 1000) << 22) | (salt & ((1 << 22) - 1))


def _share_row(moment: datetime, salt: int, text: str = "", shared: str = "", media: str = "",
               kind: str = "share") -> str:
    link = f"https://www.linkedin.com/feed/update/urn%3Ali%3A{kind}%3A{_snow(moment, salt)}"
    quoted = '"' + text.replace('"', '""') + '"' if text else ""
    return f"{moment.strftime('%Y-%m-%d %H:%M:%S')},{link},{quoted},{shared},{media},MEMBER_NETWORK\n"


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


def _upload(client, members, name=COMPLETE):
    res = client.post("/api/v1/archive/upload", content=_archive(members),
                      headers={"Content-Type": "application/zip", "X-Archive-Name": name})
    assert res.status_code == 200, res.text
    return res.json()


def _import(client, source, **extra):
    return client.post("/api/v1/archive/import", json={"source": source, **extra})


# ---------------------------------------------------------------------------
# SETUP-06: the same words on different days are different posts, and a post
# with no caption is still a post
# ---------------------------------------------------------------------------

OFFICE_HOURS = "Our weekly office hours are open again this Thursday at 5pm. Bring your questions."


def test_same_text_a_week_apart_imports_as_separate_posts(client):
    days = [datetime(2024, 1, d, 11, 0, tzinfo=timezone.utc) for d in (4, 11, 18)]
    shares = SHARES_HEADER + "".join(_share_row(day, i, OFFICE_HOURS) for i, day in enumerate(days))
    source = _upload(client, {"Shares.csv": shares})["source"]
    summary = _import(client, source, include=["posts"]).json()["summary"]
    assert summary["posts"] == {"added": 3, "already_there": 0, "skipped": 0}, summary
    dates = [r[0] for r in _db().execute("SELECT published_at FROM own_posts ORDER BY published_at")]
    assert dates == [d.isoformat() for d in days]


def test_same_text_as_a_bridge_post_on_another_day_is_not_that_post(client):
    bridge_day = datetime(2024, 1, 4, 11, 0, tzinfo=timezone.utc)
    conn = _db()
    conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, reactions, "
                 "first_seen_at, last_seen_at) VALUES (?, ?, ?, 'urn_decode', 9, 'x', 'x')",
                 (f"urn:li:activity:{_snow(bridge_day, 5)}", OFFICE_HOURS, bridge_day.isoformat()))
    conn.commit()
    conn.close()
    later = datetime(2024, 1, 11, 11, 0, tzinfo=timezone.utc)
    source = _upload(client, {"Shares.csv": SHARES_HEADER + _share_row(later, 1, OFFICE_HOURS)})["source"]
    summary = _import(client, source, include=["posts"]).json()["summary"]
    assert summary["posts"]["added"] == 1, "a post a week later was merged into the bridge's row"
    assert _db().execute("SELECT COUNT(*) FROM own_posts").fetchone()[0] == 2


def test_a_post_with_media_and_no_caption_is_imported(client):
    day = datetime(2024, 2, 1, 9, 0, tzinfo=timezone.utc)
    media = _share_row(day, 77, media="https://media.licdn.com/dms/image/sample/1", kind="ugcPost")
    repost = _share_row(datetime(2024, 2, 2, 9, 0, tzinfo=timezone.utc), 78,
                        shared="https://www.linkedin.com/feed/update/urn:li:activity:7100000000000000000")
    source = _upload(client, {"Shares.csv": SHARES_HEADER + media + repost})["source"]
    summary = _import(client, source, include=["posts"]).json()["summary"]
    assert summary["posts"] == {"added": 1, "already_there": 0, "skipped": 1}, summary
    row = _db().execute("SELECT activity_urn, published_at FROM own_posts").fetchone()
    assert row["activity_urn"] == f"urn:li:ugcPost:{_snow(day, 77)}" and row["published_at"] == day.isoformat()


def test_a_captionless_post_matches_the_bridge_row_by_id_and_time(client):
    day = datetime(2024, 2, 1, 9, 0, tzinfo=timezone.utc)
    activity = f"urn:li:activity:{_snow(day, 4242)}"
    conn = _db()
    conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, reactions, "
                 "first_seen_at, last_seen_at) VALUES (?, NULL, ?, 'urn_decode', 3, 'x', 'x')",
                 (activity, day.isoformat()))
    conn.commit()
    conn.close()
    media = _share_row(day, 77, media="https://media.licdn.com/dms/image/sample/1", kind="ugcPost")
    source = _upload(client, {"Shares.csv": SHARES_HEADER + media})["source"]
    summary = _import(client, source, include=["posts"]).json()["summary"]
    assert summary["posts"] == {"added": 0, "already_there": 1, "skipped": 0}, summary
    assert _db().execute("SELECT reactions FROM own_posts").fetchone()[0] == 3
