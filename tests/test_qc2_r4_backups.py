"""
Backups That Happen, Are Checked, and Do Not Fill the Disk.
===========================================================
DATA-07, and the backup half of DATA-01. Every backup was full, made only
when the creator pressed the button, never checked when made, and never
expired, nor were the pre-upgrade database copies. So the disk filled, a
creator who never pressed the button had nothing to go back to, and a
forgotten person stayed in every copy for ever.

Now: a daily automatic backup (on by default), each one checked with
integrity_check and read back before it is listed, media stored rather than
deflated again, and rotation that keeps 7 daily, 4 weekly and 3 monthly
automatic backups and the last 2 pre-upgrade copies. Backups the creator made
are never removed by the studio.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import json
import os
import sqlite3
import sys
import zipfile
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from studio.backend import database, migrations, paths, support  # noqa: E402


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    database.init_db()
    for name in os.listdir(paths.get_backups_dir()):
        os.remove(os.path.join(paths.get_backups_dir(), name))
    return tmp_path


def _touch_backup(name, when):
    path = os.path.join(paths.get_backups_dir(), name)
    with open(path, "wb") as handle:
        handle.write(b"x")
    stamp = when.timestamp()
    os.utime(path, (stamp, stamp))
    return path


def _stamp(when):
    return when.strftime("%Y%m%d_%H%M%S")


# ---------------------------------------------------------------------------
# Each backup is checked when it is made
# ---------------------------------------------------------------------------

def test_a_backup_records_that_it_was_checked(home):
    archive = support.create_backup("manual")
    with zipfile.ZipFile(archive) as z:
        manifest = json.loads(z.read("backup_manifest.json"))
        assert z.testzip() is None
    assert manifest["verified"]["integrity_check"] == "ok"
    assert manifest["verified"]["archive_read_back"] is True


def test_a_database_failing_its_check_is_not_listed_as_a_backup(home, monkeypatch):
    monkeypatch.setattr(support, "_integrity_of", lambda path: "row 3 missing from index idx_x")
    with pytest.raises(support.BackupNotVerified, match="row 3 missing"):
        support.create_backup("manual")
    left = [n for n in os.listdir(paths.get_backups_dir())]
    assert left == [], f"an unverified backup or its snapshot was left behind: {left}"


def test_the_copy_inside_a_backup_is_compact(home):
    conn = database.get_db()
    conn.execute("CREATE TABLE filler (x TEXT)")
    conn.executemany("INSERT INTO filler VALUES (?)", [("y" * 2000,)] * 500)
    conn.commit()
    conn.execute("DELETE FROM filler")
    conn.commit()
    conn.close()
    archive = support.create_backup("manual")
    with zipfile.ZipFile(archive) as z:
        copy = z.read("data/linkedin_studio.db")
    page_size = int.from_bytes(copy[16:18], "big")
    free_pages = int.from_bytes(copy[36:40], "big")
    assert free_pages == 0, f"the backup carried {free_pages} free pages of {page_size} bytes"


def test_media_already_compressed_is_stored_not_deflated(home):
    uploads = paths.get_uploads_dir()
    with open(os.path.join(uploads, "photo.jpg"), "wb") as handle:
        handle.write(os.urandom(4096))
    with open(os.path.join(uploads, "notes.txt"), "w") as handle:
        handle.write("words " * 500)
    archive = support.create_backup("manual")
    with zipfile.ZipFile(archive) as z:
        kinds = {info.filename: info.compress_type for info in z.infolist()}
    assert kinds["assets/uploads/photo.jpg"] == zipfile.ZIP_STORED
    assert kinds["assets/uploads/notes.txt"] == zipfile.ZIP_DEFLATED
    assert kinds["data/linkedin_studio.db"] == zipfile.ZIP_DEFLATED


def test_two_backups_in_the_same_second_do_not_overwrite_each_other(home):
    first = support.create_backup("manual")
    second = support.create_backup("manual")
    assert first != second
    assert os.path.exists(first) and os.path.exists(second)


# ---------------------------------------------------------------------------
# Rotation
# ---------------------------------------------------------------------------

def test_rotation_keeps_seven_daily_four_weekly_three_monthly(home):
    now = datetime(2026, 10, 20, 9, 0, 0)
    for day in range(120):
        when = now - timedelta(days=day)
        _touch_backup(f"inox_backup_daily_{_stamp(when)}.zip", when)

    result = support.rotate_backups()

    kept = sorted(n for n in os.listdir(paths.get_backups_dir()))
    assert len(kept) == 14, kept
    newest = f"inox_backup_daily_{_stamp(now)}.zip"
    assert newest in kept
    for day in range(7):
        assert f"inox_backup_daily_{_stamp(now - timedelta(days=day))}.zip" in kept
    oldest_kept = min(datetime.strptime(n[len("inox_backup_daily_"):-4], "%Y%m%d_%H%M%S") for n in kept)
    assert (now - oldest_kept).days >= 90, "the monthly generations were not kept"
    assert (now - oldest_kept).days <= support.ROTATION_REACH_DAYS
    assert len(result["removed"]) == 120 - len(kept)

    again = support.rotate_backups()
    assert again["removed"] == [], "rotation is not idempotent"


def test_rotation_never_removes_a_backup_the_creator_made(home):
    now = datetime(2026, 10, 20, 9, 0, 0)
    old = now - timedelta(days=400)
    mine = [
        _touch_backup(f"inox_backup_manual_{_stamp(old)}.zip", old),
        _touch_backup(f"inox_backup_before_trip_{_stamp(old)}.zip", old),
        _touch_backup(f"inox_backup_pre_restore_{_stamp(old)}.zip", old),
    ]
    support.rotate_backups()
    for path in mine:
        assert os.path.exists(path), f"rotation removed {os.path.basename(path)}"


def test_rotation_keeps_the_last_two_pre_upgrade_copies(home):
    now = datetime(2026, 10, 20, 9, 0, 0)
    for i in range(5):
        when = now - timedelta(days=30 * i)
        _touch_backup(f"linkedin_studio_premigration_{_stamp(when)}.db", when)
    support.rotate_backups()
    kept = sorted(os.listdir(paths.get_backups_dir()))
    assert kept == sorted([
        f"linkedin_studio_premigration_{_stamp(now)}.db",
        f"linkedin_studio_premigration_{_stamp(now - timedelta(days=30))}.db",
    ])


def test_rotation_leaves_a_backup_in_progress_alone(home):
    now = datetime(2026, 10, 20, 9, 0, 0)
    old = now - timedelta(days=300)
    snapshot = _touch_backup(f"linkedin_studio_snapshot_daily_{_stamp(old)}.db", old)
    support.rotate_backups()
    assert os.path.exists(snapshot)


# ---------------------------------------------------------------------------
# The daily backup
# ---------------------------------------------------------------------------

def test_a_daily_backup_is_made_when_none_is_recent_and_then_not_again(home):
    made = support.run_daily_backup()
    assert made is not None and made["ok"], made
    assert os.path.basename(made["archive"]).startswith("inox_backup_daily_")
    assert support.run_daily_backup() is None, "a second daily backup was made within the day"


def test_a_daily_backup_is_due_again_after_a_day(home):
    old = datetime.now() - timedelta(hours=25)
    _touch_backup(f"inox_backup_daily_{_stamp(old)}.zip", old)
    made = support.run_daily_backup()
    assert made is not None and made["ok"]


def test_a_failed_daily_backup_is_reported_not_raised(home, monkeypatch):
    monkeypatch.setattr(support, "_integrity_of", lambda path: "database disk image is malformed")
    made = support.run_daily_backup()
    assert made is not None and made["ok"] is False
    assert "malformed" in made["error"]


def test_the_schedule_names_the_last_and_next_backup(home):
    made = support.run_daily_backup()
    schedule = support.backup_schedule(enabled=True)
    assert schedule["last"]["name"] == os.path.basename(made["archive"])
    assert schedule["last"]["verified"] is True
    next_due = datetime.fromisoformat(schedule["next_due"])
    assert timedelta(hours=23) < next_due - datetime.now() <= timedelta(hours=24)
    assert support.backup_schedule(enabled=False)["next_due"] is None


def test_a_pre_upgrade_copy_is_still_restorable_after_rotation(home):
    copy = migrations.backup_database("premigration")
    support.rotate_backups()
    assert os.path.exists(copy)
    assert support.inspect_backup(copy)["kind"] == "database"


def test_the_backup_snapshot_is_written_with_vacuum_into_not_left_behind(home):
    support.create_backup("manual")
    stray = [n for n in os.listdir(paths.get_backups_dir()) if n.startswith("linkedin_studio_snapshot_")]
    assert stray == []
    conn = sqlite3.connect(paths.get_db_path())
    assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    conn.close()
