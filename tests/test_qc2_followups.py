"""
The notes two reviewers left, closed.
=====================================

R6's review: `reset` cleared the LinkedIn session cookies and left the row
naming whose account they were (the creator's vanity and member URN), so the
studio still said who had used this computer.

F3's review (AUDIENCE-26): new analytics readings no longer store an unread
"members reached" as 0, but rows written by older versions keep theirs, and
0 there was never measured: nothing else writes that column.
"""

import json
import os
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from studio.backend import database, linkedin_client, migrations, support  # noqa: E402


@pytest.fixture
def home(monkeypatch):
    folder = tempfile.mkdtemp(prefix="inox_followups_")
    monkeypatch.setenv("INOX_HYDRA_HOME", folder)
    database.init_db()
    return folder


def _settings(key):
    conn = database.get_db()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def test_reset_forgets_whose_linkedin_session_it_was(home):
    conn = database.get_db()
    try:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (linkedin_client.SESSION_ACCOUNT_KEY,
                 json.dumps({"vanity": "sample-creator", "urn": "urn:li:fsd_profile:ACoAASAMPLE"})),
            )
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('li_at', 'cookie')")
    finally:
        conn.close()

    support.reset_configuration()

    assert _settings("li_at") is None
    assert _settings(linkedin_client.SESSION_ACCOUNT_KEY) is None, (
        "reset cleared the cookies and left the account they belonged to"
    )


def test_an_unread_members_reached_is_cleared_and_a_real_one_kept(home):
    """
    Nothing has ever read "members reached" from LinkedIn, and every insert
    now names it NULL. The old schema default put a 0 on every earlier row,
    which Analytics would show as measured.
    """
    conn = database.get_db()
    try:
        with conn:
            conn.execute("DELETE FROM analytics_daily")
            conn.execute("INSERT INTO analytics_daily (date, unique_members_reached) VALUES ('2026-01-01', 0)")
            conn.execute("INSERT INTO analytics_daily (date, unique_members_reached) VALUES ('2026-01-02', 1234)")
            conn.execute("INSERT INTO analytics_daily (date, unique_members_reached) VALUES ('2026-01-03', NULL)")
            conn.execute("PRAGMA user_version = 24")
    finally:
        conn.close()

    conn = database.get_db()
    try:
        migrations.ensure_schema(conn)
    finally:
        conn.close()

    conn = database.get_db()
    try:
        rows = dict(conn.execute(
            "SELECT date, unique_members_reached FROM analytics_daily ORDER BY date").fetchall())
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()
    assert rows["2026-01-01"] is None, "an invented 0 was left where Analytics reads a figure"
    assert rows["2026-01-02"] == 1234, "a figure that was really read must stay"
    assert rows["2026-01-03"] is None
    assert version == migrations.SCHEMA_VERSION


def test_a_fresh_database_never_defaults_members_reached_to_zero(home):
    conn = database.get_db()
    try:
        with conn:
            conn.execute("INSERT INTO analytics_daily (date) VALUES ('2026-02-02')")
        value = conn.execute(
            "SELECT unique_members_reached FROM analytics_daily WHERE date = '2026-02-02'").fetchone()[0]
    finally:
        conn.close()
    assert value is None, "a row written without the column read as 0 members reached"


def test_sync_version_covers_every_file_that_states_a_version():
    """
    The bump tool missed two files the desktop shell states its version in, so
    a release left them behind and the suite caught it after the push. Every
    place a test checks must be a place the tool syncs.
    """
    import subprocess

    checked = {
        "studio/extension/manifest.json",
        "release/latest.json",
        "desktop/src-tauri/tauri.conf.json",
        "desktop/src-tauri/Cargo.toml",
    }
    tool = os.path.join(REPO_ROOT, "tools", "sync_version.py")
    with open(tool, encoding="utf-8") as handle:
        source = handle.read()
    for path in checked:
        name = os.path.basename(path)
        assert name in source, f"{path} states a version that sync_version.py does not keep in step"

    run = subprocess.run([sys.executable, tool, "--check"], cwd=REPO_ROOT,
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stdout + run.stderr
    for path in checked:
        assert os.path.basename(path) in run.stdout, f"--check says nothing about {path}"
