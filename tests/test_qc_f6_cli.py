"""
The Support CLI, Used the Way a Creator Uses It.
================================================

The CLI is the toolkit for a product nobody can log into, so it is run in the
situations the interface cannot help with: before the studio has ever started,
with several creator profiles, on a portable copy. These hold it to telling
the truth in each.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from studio import cli  # noqa: E402
from studio.backend import paths, support, updates  # noqa: E402


@pytest.fixture
def empty_home(tmp_path, monkeypatch):
    """An installation the studio has never been started in."""
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    return tmp_path


# ---------------------------------------------------------------------------
# PLATFORM-24: before the first start
# ---------------------------------------------------------------------------

def test_update_enable_works_before_the_first_start(empty_home, capsys):
    assert cli.main(["update", "enable"]) == 0, capsys.readouterr().out
    assert updates.is_enabled() is True
    assert cli.main(["update", "status"]) == 0


def test_backup_refuses_when_there_is_no_database_yet(empty_home, capsys):
    assert cli.main(["backup"]) == 1
    out = capsys.readouterr().out
    assert paths.get_db_path() in out
    assert "Backup written" not in out
    assert [n for n in os.listdir(paths.get_backups_dir()) if n.endswith(".zip")] == []


@pytest.mark.parametrize("command", [["doctor"], ["migrate"], ["migrate", "--dry-run"], ["update", "status"],
                                     ["export"]])
def test_read_only_commands_do_not_create_an_empty_database(empty_home, capsys, command):
    cli.main(command)
    assert not os.path.exists(paths.get_db_path()), f"{command} left a database file behind"


@pytest.fixture
def studio_home(empty_home):
    from studio.backend import database

    database.init_db()
    return empty_home


def _settings():
    conn = sqlite3.connect(paths.get_db_path())
    try:
        return dict(conn.execute("SELECT key, value FROM settings").fetchall())
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# PLATFORM-15: reset clears the AI setup and LinkedIn session, nothing else
# ---------------------------------------------------------------------------

def test_reset_keeps_the_paused_queue_and_the_brand_profile(studio_home, capsys):
    conn = sqlite3.connect(paths.get_db_path())
    for key, value in (("queue_status", "paused"), ("creator_profile", '{"name": "Jane Creator"}'),
                       ("ai_provider", "openai"), ("ai_api_key", "sealed"), ("ai_model", "gpt-4o"),
                       ("gemini_api_key", "sealed"), ("li_at", "sealed"), ("JSESSIONID", "sealed"),
                       ("session_status", "connected"), ("update_check_enabled", "true")):
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

    assert cli.main(["reset", "--yes"]) == 0
    out = capsys.readouterr().out

    left = _settings()
    assert left.get("queue_status") == "paused", "reset resumed a paused queue"
    assert left.get("creator_profile") == '{"name": "Jane Creator"}', "reset erased the Brand Studio identity"
    assert left.get("update_check_enabled") == "true"
    for gone in ("ai_provider", "ai_api_key", "ai_model", "gemini_api_key", "li_at", "JSESSIONID", "session_status"):
        assert gone not in left, f"{gone} survived the reset"
        assert gone in out, f"the output does not say {gone} was cleared"
    assert "queue_status" not in out


def test_doctor_reports_no_problem_on_a_fresh_install(empty_home, capsys):
    assert cli.main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "no problems found" in out
    assert "not created yet" in out


# ---------------------------------------------------------------------------
# PLATFORM-22: choose the profile, or all of them, and say which was used
# ---------------------------------------------------------------------------

@pytest.fixture
def two_profiles(studio_home):
    """The default profile and Client A, each with its own database."""
    from studio.backend import database

    paths.write_profiles({"active": "default", "profiles": [
        {"id": "client-a", "name": "Client A", "vanity": "", "headline": "", "created_at": "2026-10-19"}]})
    with paths.using_profile("client-a"):
        database.init_db()
        conn = sqlite3.connect(paths.get_db_path())
        conn.execute("INSERT INTO posts (id, content, status) VALUES ('only-in-a', 'x', 'draft')")
        conn.commit()
        conn.close()
    return studio_home


def _manifest_profile(archive):
    import json
    import zipfile

    with zipfile.ZipFile(archive) as z:
        return json.loads(z.read("backup_manifest.json"))["profile"]


def test_backup_names_the_profile_it_backed_up(two_profiles, capsys):
    assert cli.main(["backup"]) == 0
    out = capsys.readouterr().out
    assert "My studio (default)" in out


def test_backup_all_writes_one_archive_per_profile(two_profiles, capsys):
    assert cli.main(["backup", "--all"]) == 0
    out = capsys.readouterr().out
    assert "(default)" in out and "Client A (client-a)" in out
    with paths.using_profile("default"):
        mine = [n for n in os.listdir(paths.get_backups_dir()) if n.endswith(".zip")]
    with paths.using_profile("client-a"):
        theirs = [os.path.join(paths.get_backups_dir(), n) for n in os.listdir(paths.get_backups_dir())
                  if n.endswith(".zip")]
    assert len(mine) == 1 and len(theirs) == 1
    assert _manifest_profile(theirs[0]) == "client-a"


def test_a_profile_can_be_chosen_by_id(two_profiles, capsys):
    # Client A is beyond the free licence, so it is closed in the studio, and
    # can still be backed up and exported here.
    assert "client-a" in paths.locked_profile_ids()
    assert cli.main(["backup", "--profile", "client-a"]) == 0
    assert "Client A (client-a)" in capsys.readouterr().out
    assert cli.main(["export", "--profile", "client-a"]) == 0
    out = capsys.readouterr().out
    assert os.path.join("profiles", "client-a", "exports") in out
    assert cli.main(["doctor", "--profile", "client-a"]) == 0
    assert "Client A (client-a)" in capsys.readouterr().out


def test_an_unknown_profile_is_refused(two_profiles, capsys):
    assert cli.main(["backup", "--profile", "nobody"]) == 1
    out = capsys.readouterr().out
    assert "nobody" in out and "client-a" in out
