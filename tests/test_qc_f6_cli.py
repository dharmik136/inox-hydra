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
