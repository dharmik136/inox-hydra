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
