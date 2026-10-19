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


def test_doctor_reports_no_problem_on_a_fresh_install(empty_home, capsys):
    assert cli.main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "no problems found" in out
    assert "not created yet" in out
