"""
The Backups List Shows the Newest Restorable Backups First.
===========================================================

Brand Studio lists the first five entries of the backups folder. Sorted by
file name in reverse, the automatic pre-upgrade copies always came first and
inox_backup_pre_* sorted ahead of inox_backup_manual_*, so after a few
upgrades the list showed no backup the creator had made.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import os
import sys
import zipfile

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from studio.backend import app as app_module  # noqa: E402
from studio.backend import database, paths  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    database.init_db()
    for name in os.listdir(paths.get_backups_dir()):
        os.remove(os.path.join(paths.get_backups_dir(), name))
    return TestClient(app_module.app)


def _file(name, mtime, kind):
    path = os.path.join(paths.get_backups_dir(), name)
    if kind == "backup":
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("data/linkedin_studio.db", b"SQLite format 3\x00" + b"\x00" * 84)
    elif kind == "database":
        with open(path, "wb") as handle:
            handle.write(b"SQLite format 3\x00" + b"\x00" * 84)
    else:
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("damaged/linkedin_studio.db", b"junk")
    os.utime(path, (mtime, mtime))


def test_the_newest_restorable_backups_come_first(client):
    base = 1_800_000_000
    _file("inox_backup_manual_20261019_103323.zip", base + 50, "backup")       # the newest
    _file("inox_backup_pre_restore_20261019_102001.zip", base + 20, "backup")
    _file("inox_backup_before_20261019_101951.zip", base + 10, "backup")
    _file("linkedin_studio_premigration_20261019_101548.db", base + 40, "database")
    _file("inox_backup_pre_restore_damaged_20261019_101000.zip", base + 30, "other")
    os.makedirs(os.path.join(paths.get_backups_dir(), "not-a-backup-folder"))

    listing = client.get("/api/v1/support/backups").json()
    names = [entry["name"] for entry in listing["backups"]]
    assert names == [
        "inox_backup_manual_20261019_103323.zip",
        "inox_backup_pre_restore_20261019_102001.zip",
        "inox_backup_before_20261019_101951.zip",
        "linkedin_studio_premigration_20261019_101548.db",
        "inox_backup_pre_restore_damaged_20261019_101000.zip",
    ], names
    kinds = {entry["name"]: (entry["kind"], entry["restorable"]) for entry in listing["backups"]}
    assert kinds["linkedin_studio_premigration_20261019_101548.db"] == ("database", True)
    assert kinds["inox_backup_pre_restore_damaged_20261019_101000.zip"] == ("other", False)
    assert listing["count"] == 5


def test_one_unreadable_archive_does_not_hide_the_rest(client):
    base = 1_800_000_000
    _file("inox_backup_manual_20261019_103323.zip", base + 50, "backup")
    broken = os.path.join(paths.get_backups_dir(), "inox_backup_broken_20261019_100000.zip")
    with zipfile.ZipFile(broken, "w") as z:
        z.writestr("data/linkedin_studio.db", b"SQLite format 3\x00" + b"\x00" * 84)
        z.writestr("backup_manifest.json", "{not json")
    truncated = os.path.join(paths.get_backups_dir(), "inox_backup_cut_20261019_090000.zip")
    with open(truncated, "wb") as handle:
        handle.write(b"PK\x03\x04 cut short")

    res = client.get("/api/v1/support/backups")
    assert res.status_code == 200, res.text
    entries = {entry["name"]: entry for entry in res.json()["backups"]}
    assert entries["inox_backup_manual_20261019_103323.zip"]["restorable"] is True
    assert entries["inox_backup_broken_20261019_100000.zip"]["kind"] == "unreadable"
    assert entries["inox_backup_broken_20261019_100000.zip"]["restorable"] is False
    assert entries["inox_backup_cut_20261019_090000.zip"]["restorable"] is False
    assert res.json()["backups"][0]["name"] == "inox_backup_manual_20261019_103323.zip"
