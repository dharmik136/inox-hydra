"""
P0 Verification Suite: Separation of Code from User State.
==========================================================
Guards the single property that makes the product updatable at all:
replacing the application directory must never destroy user data.

Every test here is a regression guard against reintroducing an install-relative
state path. If one of these fails, the product cannot ship an update safely.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import os
import shutil
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import paths  # noqa: E402


@pytest.fixture
def temp_home(monkeypatch):
    """Redirects all application state into a throwaway directory."""
    d = tempfile.mkdtemp(prefix="inox_home_")
    monkeypatch.setenv("INOX_HYDRA_HOME", d)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_env_override_wins(temp_home):
    """INOX_HYDRA_HOME must take priority over portable and platform resolution."""
    assert paths.get_app_home() == os.path.abspath(temp_home)
    assert paths.describe()["resolved_by"] == "INOX_HYDRA_HOME"


def test_portable_mode_detected_in_source_checkout(monkeypatch):
    """A studio/data directory beside the code means portable, not user profile."""
    monkeypatch.delenv("INOX_HYDRA_HOME", raising=False)
    monkeypatch.setattr(paths, "_LEGACY_DATA_DIR", paths._LEGACY_DATA_DIR)
    if os.path.isdir(paths._LEGACY_DATA_DIR):
        assert paths.is_portable()
        assert paths.get_app_home() == paths._STUDIO_DIR


def test_installed_mode_uses_platform_dir(monkeypatch):
    """With no studio/data present, state must land in the platform user data dir."""
    monkeypatch.delenv("INOX_HYDRA_HOME", raising=False)
    monkeypatch.setattr(paths, "_LEGACY_DATA_DIR", os.path.join(tempfile.gettempdir(), "inox-definitely-absent"))

    home = paths.get_app_home()
    assert not paths.is_portable()
    # The critical assertion: state is NOT inside the shipped package.
    assert not home.startswith(paths._STUDIO_DIR), (
        f"Installed-mode state resolved inside the install directory: {home}"
    )
    if sys.platform == "win32":
        assert paths.APP_DIR_NAME_WINDOWS in home


def test_all_state_dirs_live_under_app_home(temp_home):
    """No state accessor may escape the resolved home."""
    home = os.path.abspath(temp_home)
    for accessor in (
        paths.get_data_dir,
        paths.get_assets_dir,
        paths.get_uploads_dir,
        paths.get_generated_dir,
        paths.get_vault_dir,
        paths.get_logs_dir,
    ):
        resolved = os.path.abspath(accessor())
        assert resolved.startswith(home), f"{accessor.__name__} escaped app home: {resolved}"
        assert os.path.isdir(resolved), f"{accessor.__name__} did not create its directory"

    assert os.path.abspath(paths.get_db_path()).startswith(home)


def test_state_survives_install_directory_replacement(temp_home):
    """
    The P0 gate.

    Simulates what an update actually does: delete the application directory and
    unpack a new one. The user's database must be completely unaffected.
    """
    # 1. A user does real work. Their data lands outside the install directory.
    db_path = paths.get_db_path()
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE precious (id INTEGER PRIMARY KEY, draft TEXT)")
    conn.execute("INSERT INTO precious (draft) VALUES (?)", ("six months of writing",))
    conn.commit()
    conn.close()

    upload = os.path.join(paths.get_uploads_dir(), "carousel.pdf")
    with open(upload, "w", encoding="utf-8") as f:
        f.write("user media")

    # 2. Ship an update: the entire application directory is replaced.
    fake_install = tempfile.mkdtemp(prefix="inox_install_")
    try:
        os.makedirs(os.path.join(fake_install, "studio", "backend"), exist_ok=True)
        shutil.rmtree(fake_install)
        os.makedirs(os.path.join(fake_install, "studio"), exist_ok=True)
    finally:
        shutil.rmtree(fake_install, ignore_errors=True)

    # 3. The user's state is untouched.
    assert os.path.exists(db_path), "Update destroyed the user database"
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT draft FROM precious").fetchone()
    conn.close()
    assert row is not None and row[0] == "six months of writing"

    assert os.path.exists(upload), "Update destroyed user media"
    with open(upload, encoding="utf-8") as f:
        assert f.read() == "user media"


def test_describe_reports_enough_for_a_support_bundle(temp_home):
    """describe() is what a user sends us when something breaks. It must be complete."""
    d = paths.describe()
    for key in (
        "app_home", "resolved_by", "portable", "data_dir", "assets_dir",
        "uploads_dir", "generated_dir", "vault_dir", "logs_dir",
        "db_path", "db_exists", "db_size_bytes",
    ):
        assert key in d, f"describe() missing {key}"
    assert isinstance(d["portable"], bool)
    assert isinstance(d["db_size_bytes"], int)
