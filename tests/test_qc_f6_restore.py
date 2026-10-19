"""
Restore: All or Nothing, Whatever State the Studio Is In.
=========================================================
Restore is the recovery path for a product nobody can log into, so it has to
work in exactly the situations that send a creator to it: a damaged database,
a failed upgrade, a backup from another machine. These hold it to that:

- a restore that fails part way leaves everything as it was, and says where
  the safety copy is;
- a backup written by a newer build is refused before anything changes;
- a damaged live database does not stop the restore that would replace it;
- the automatic pre-upgrade .db copies can be restored too.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import os
import sqlite3
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from studio import cli  # noqa: E402
from studio.backend import database, migrations, paths, support  # noqa: E402


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    database.init_db()
    return tmp_path


def _add_post(post_id):
    conn = sqlite3.connect(paths.get_db_path())
    conn.execute("INSERT INTO posts (id, content, status) VALUES (?, ?, 'draft')", (post_id, post_id))
    conn.commit()
    conn.close()


def _post_ids():
    conn = sqlite3.connect(paths.get_db_path())
    try:
        return {row[0] for row in conn.execute("SELECT id FROM posts")}
    finally:
        conn.close()


def _images(count=3):
    uploads = paths.get_uploads_dir()
    for i in range(count):
        with open(os.path.join(uploads, f"img{i}.png"), "wb") as handle:
            handle.write(b"\x89PNG\r\n\x1a\n" + bytes([i]) * 2000)
    return uploads


# ---------------------------------------------------------------------------
# PLATFORM-09: stage, then swap; any failure puts everything back
# ---------------------------------------------------------------------------

def test_a_restore_blocked_by_a_media_file_changes_nothing(home):
    uploads = _images()
    _add_post("old-state")
    archive = support.create_backup("before")
    _add_post("new-work")
    # Something occupies one media file's name, so it cannot be written back.
    os.remove(os.path.join(uploads, "img1.png"))
    os.makedirs(os.path.join(uploads, "img1.png"))

    with pytest.raises(support.RestoreFailed) as failed:
        support.restore_backup(archive)

    assert "img1.png" in str(failed.value)
    assert _post_ids() == {"old-state", "new-work"}, "the database was replaced by a restore that failed"
    assert os.path.isdir(os.path.join(uploads, "img1.png"))


def test_a_restore_that_fails_while_swapping_puts_everything_back(home, monkeypatch):
    uploads = _images()
    _add_post("old-state")
    archive = support.create_backup("before")
    _add_post("new-work")
    with open(os.path.join(uploads, "img2.png"), "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\nchanged since the backup")

    real_replace = os.replace

    def replace(src, dst):
        if os.path.basename(dst) == "img2.png" and os.sep + "new" + os.sep in src:
            raise OSError(28, "No space left on device")
        return real_replace(src, dst)

    monkeypatch.setattr(support.os, "replace", replace)
    with pytest.raises(support.RestoreFailed) as failed:
        support.restore_backup(archive)
    monkeypatch.setattr(support.os, "replace", real_replace)

    safety = failed.value.safety_backup
    assert safety and os.path.exists(safety), "the failure did not name the safety backup"
    assert _post_ids() == {"old-state", "new-work"}, "work done since the backup was lost"
    with open(os.path.join(uploads, "img2.png"), "rb") as handle:
        assert handle.read().endswith(b"changed since the backup")
    leftovers = [n for n in os.listdir(paths.get_profile_home()) if n.startswith(".restore-")]
    assert leftovers == [], f"staging was left behind: {leftovers}"


def test_a_successful_restore_replaces_database_and_media(home):
    uploads = _images()
    _add_post("old-state")
    archive = support.create_backup("before")
    _add_post("new-work")
    with open(os.path.join(uploads, "img0.png"), "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\nnewer")

    result = support.restore_backup(archive)

    assert _post_ids() == {"old-state"}
    assert result["assets_restored"] == 3
    with open(os.path.join(uploads, "img0.png"), "rb") as handle:
        assert handle.read() == b"\x89PNG\r\n\x1a\n" + bytes([0]) * 2000
    assert not [n for n in os.listdir(paths.get_profile_home()) if n.startswith(".restore-")]


def test_the_cli_names_the_safety_backup_when_a_restore_fails(home, monkeypatch, capsys):
    _images()
    _add_post("old-state")
    archive = support.create_backup("before")

    def broken_swap(*args, **kwargs):
        raise support.RestoreFailed("could not write a media file", safety_backup="/backups/safety.zip")

    monkeypatch.setattr(support, "restore_backup", broken_swap)
    assert cli.main(["restore", archive, "--yes"]) == 1
    out = capsys.readouterr().out
    assert "/backups/safety.zip" in out
    assert "--into-active-profile" not in out


# ---------------------------------------------------------------------------
# PLATFORM-10: a backup from a newer build is refused before anything changes
# ---------------------------------------------------------------------------

def _stamped_copy(archive, version, app_version):
    """The same backup, its database stamped as a newer build would leave it."""
    import json
    import tempfile

    work = tempfile.mkdtemp(prefix="inox_newer_", dir=paths.get_app_home())
    with zipfile.ZipFile(archive) as z:
        z.extractall(work)
    db = os.path.join(work, "data", "linkedin_studio.db")
    conn = sqlite3.connect(db)
    conn.execute(f"PRAGMA user_version = {version:d}")
    conn.commit()
    conn.close()
    manifest_path = os.path.join(work, "backup_manifest.json")
    with open(manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    manifest["app_version"] = app_version
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle)
    newer = os.path.join(os.path.dirname(work), f"inox_backup_from_laptop_{app_version}.zip")
    with zipfile.ZipFile(newer, "w") as z:
        for base, _dirs, files in os.walk(work):
            for name in files:
                full = os.path.join(base, name)
                z.write(full, os.path.relpath(full, work).replace(os.sep, "/"))
    return newer


def test_a_backup_from_a_newer_build_is_refused_and_nothing_changes(home, capsys):
    _add_post("from-laptop")
    archive = support.create_backup("laptop")
    newer = _stamped_copy(archive, migrations.SCHEMA_VERSION + 1, "9.9.0")
    _add_post("this-machine")
    before = sorted(os.listdir(paths.get_backups_dir()))

    with pytest.raises(ValueError, match="newer") as refused:
        support.restore_backup(newer)
    assert "9.9.0" in str(refused.value) and "Update" in str(refused.value)
    assert _post_ids() == {"from-laptop", "this-machine"}
    assert sorted(os.listdir(paths.get_backups_dir())) == before, "a refused restore still took a safety copy"

    assert cli.main(["restore", newer, "--yes"]) == 1
    out = capsys.readouterr().out
    assert "9.9.0" in out and "--into-active-profile" not in out
    # The studio still starts: the live database is still this build's.
    database.init_db()


# ---------------------------------------------------------------------------
# PLATFORM-01: a damaged live database does not block the restore
# ---------------------------------------------------------------------------

def _damage_header(db):
    with open(db, "r+b") as handle:
        handle.write(b"\x00garbage" * 12)
    with pytest.raises(sqlite3.DatabaseError):
        conn = sqlite3.connect(db)
        try:
            conn.execute("SELECT COUNT(*) FROM posts").fetchone()
        finally:
            conn.close()


def test_a_good_backup_restores_over_a_damaged_database(home, capsys):
    _add_post("good-1")
    archive = support.create_backup("good")
    db = paths.get_db_path()
    _damage_header(db)
    with open(db, "rb") as handle:
        damaged_bytes = handle.read()

    assert cli.main(["restore", archive, "--yes"]) == 0, capsys.readouterr().out
    out = capsys.readouterr().out
    assert "could not be read" in out

    conn = sqlite3.connect(db)
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()
    assert _post_ids() == {"good-1"}

    # The damaged original is kept, byte for byte, and cannot be restored by mistake.
    safety = [n for n in os.listdir(paths.get_backups_dir()) if n.startswith("inox_backup_pre_restore")]
    assert len(safety) == 1, safety
    with zipfile.ZipFile(os.path.join(paths.get_backups_dir(), safety[0])) as z:
        assert z.read("damaged/linkedin_studio.db") == damaged_bytes
        assert "data/linkedin_studio.db" not in z.namelist()
    stray = [n for n in os.listdir(paths.get_backups_dir()) if n.startswith("linkedin_studio_snapshot_")]
    assert stray == [], f"a failed snapshot left a file behind: {stray}"


# ---------------------------------------------------------------------------
# PLATFORM-08: the automatic pre-upgrade .db copies can be restored
# ---------------------------------------------------------------------------

def test_a_pre_upgrade_database_copy_can_be_restored(home, capsys):
    _add_post("before-upgrade")
    conn = sqlite3.connect(paths.get_db_path())
    conn.execute(f"PRAGMA user_version = {migrations.SCHEMA_VERSION - 1}")
    conn.commit()
    conn.close()
    copy = migrations.backup_database("premigration")
    assert os.path.basename(copy).startswith("linkedin_studio_premigration_")
    database.init_db()
    _add_post("after-upgrade")
    uploads = _images(1)

    assert cli.main(["restore", copy]) == 1
    preview = capsys.readouterr().out
    assert "database     yes" in preview

    assert cli.main(["restore", copy, "--yes"]) == 0, capsys.readouterr().out
    out = capsys.readouterr().out
    assert "--into-active-profile" not in out
    assert _post_ids() == {"before-upgrade"}
    conn = sqlite3.connect(paths.get_db_path())
    assert conn.execute("PRAGMA user_version").fetchone()[0] == migrations.SCHEMA_VERSION - 1
    conn.close()
    assert os.path.exists(os.path.join(uploads, "img0.png")), "a database-only restore touched the media"


def test_a_database_copy_from_another_profile_is_not_restored_by_accident(home, monkeypatch):
    other = os.path.join(paths.get_profiles_root(), "client-a")
    monkeypatch.setattr(paths, "read_profiles", lambda: {
        "active": "default", "profiles": [{"id": "client-a", "name": "Client A"}]})
    with paths.using_profile("client-a"):
        database.init_db()
        copy = migrations.backup_database("premigration")
    assert copy.startswith(other)
    with pytest.raises(support.ProfileMismatch, match="client-a"):
        support.restore_backup(copy, take_safety_backup=False)
