"""
Quality cycle 2026-10, batch F4a, SETUP-05: a large archive imports quickly
and lets the rest of the studio write while it does.
===========================================================================

A prolific creator's Shares.csv holds thousands of posts, and by the time they
import it the bridge has often read thousands of them already. Matching each
archive row against every post the studio holds made the import quadratic,
and doing it in one transaction held SQLite's write lock for the whole of it,
so a draft saved meanwhile failed with "database is locked". Every name and
text here is invented.
"""

import io
import os
import sqlite3
import sys
import threading
import time
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import archive_import  # noqa: E402
import paths  # noqa: E402
from app import app  # noqa: E402
from database import init_db  # noqa: E402

POSTS = 3000
START = datetime(2018, 1, 1, 9, 0, tzinfo=timezone.utc)


def _snow(moment: datetime, salt: int) -> int:
    return (int(moment.timestamp() * 1000) << 22) | (salt & ((1 << 22) - 1))


def _when(i: int) -> datetime:
    return START + timedelta(hours=23 * i, minutes=i % 50)


def _text(i: int) -> str:
    return f"Synthetic post number {i}, about compilers and the people who use them. " + "More words. " * (i % 20)


def _shares() -> str:
    lines = ["Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl,Visibility"]
    for i in range(POSTS):
        link = f"https://www.linkedin.com/feed/update/urn%3Ali%3Ashare%3A{_snow(_when(i), i)}"
        lines.append(f'{_when(i).strftime("%Y-%m-%d %H:%M:%S")},{link},"{_text(i)}",,,MEMBER_NETWORK')
    return "\n".join(lines) + "\n"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path / "studio"))
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "user"))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    init_db()
    return TestClient(app)


def _seed_bridge_posts(every: int = 2) -> None:
    """Half the archive's posts, as the bridge read them first: activity ids, cut text, figures."""
    conn = sqlite3.connect(paths.get_db_path())
    conn.executemany(
        "INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, reactions, "
        "first_seen_at, last_seen_at) VALUES (?, ?, ?, 'urn_decode', 5, 'x', 'x')",
        [(f"urn:li:activity:{_snow(_when(i), i + 999)}", _text(i)[:60] + "…more",
          _when(i).replace(microsecond=0).isoformat()) for i in range(0, POSTS, every)])
    conn.commit()
    conn.close()


def _upload(client) -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Shares.csv", _shares())
    res = client.post("/api/v1/archive/upload", content=buffer.getvalue(),
                      headers={"Content-Type": "application/zip",
                               "X-Archive-Name": "Complete_LinkedInDataExport_10-19-2026.zip"})
    assert res.status_code == 200, res.text
    return res.json()["source"]


def test_three_thousand_posts_import_in_seconds_and_match_what_the_bridge_read(client):
    _seed_bridge_posts()
    source = _upload(client)
    started = time.monotonic()
    res = client.post("/api/v1/archive/import", json={"source": source, "include": ["posts"]})
    took = time.monotonic() - started
    assert res.status_code == 200, res.text
    assert res.json()["summary"]["posts"] == {"added": POSTS // 2, "already_there": POSTS // 2, "skipped": 0}
    assert took < 5, f"a {POSTS}-post archive took {took:.1f} s to import"
    conn = sqlite3.connect(paths.get_db_path())
    assert conn.execute("SELECT COUNT(*) FROM own_posts").fetchone()[0] == POSTS
    assert conn.execute("SELECT COUNT(*) FROM own_posts WHERE reactions = 5").fetchone()[0] == POSTS // 2


class _Slow:
    """
    The import's connection, stalling on every 200th post it writes.

    Fifteen stalls of 0.4 s make an import that writes for six seconds: longer
    than SQLite's busy timeout (5 s), as a real import of a large archive was.
    """

    def __init__(self, conn):
        self._conn = conn
        self._posts = 0

    def execute(self, sql, *args):
        if sql.lstrip().startswith("INSERT INTO own_posts"):
            self._posts += 1
            if self._posts % 200 == 0:
                time.sleep(0.4)
        return self._conn.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, *exc):
        return self._conn.__exit__(*exc)


def test_a_draft_saved_during_a_large_import_is_saved(client, monkeypatch):
    real = archive_import.get_db
    monkeypatch.setattr(archive_import, "get_db", lambda: _Slow(real()))
    source = _upload(client)
    outcome = {}

    def run():
        outcome["import"] = client.post("/api/v1/archive/import", json={"source": source, "include": ["posts"]})

    worker = threading.Thread(target=run)
    worker.start()
    try:
        time.sleep(0.3)
        assert worker.is_alive(), "the import ended before the draft was saved, so this proves nothing"
        started = time.monotonic()
        saved = client.post("/api/posts", json={"content": "A draft typed while the archive imports",
                                                "status": "draft"})
        took = time.monotonic() - started
    finally:
        worker.join(120)
    assert saved.status_code == 200, f"the draft failed with {saved.status_code} after {took:.1f} s: {saved.text[:200]}"
    assert took < 2, f"the draft waited {took:.1f} s for the import"
    assert outcome["import"].status_code == 200
    assert outcome["import"].json()["summary"]["posts"]["added"] == POSTS
