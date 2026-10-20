"""
A damaged database starts the studio in safe mode, which says how to restore. [BE-11]

The lifespan raised "database disk image is malformed" and uvicorn never
served, so the desktop splash said to quit and start again, doctor listed
"database unreadable" without a next step, and the help article that explains
recovery was served by the studio that would not start. And on a fresh
install the only backup on disk was the empty copy taken before the very
first migrations, so any advice to restore the newest backup pointed at it.
"""

import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import database  # noqa: E402
import paths  # noqa: E402
import safe_mode  # noqa: E402
import support  # noqa: E402


def _damage(db_path):
    for leftover in ("-wal", "-shm"):
        if os.path.exists(db_path + leftover):
            os.remove(db_path + leftover)
    with open(db_path, "r+b") as handle:  # page 1: the header and the schema root
        handle.seek(100)
        handle.write(b"\x00" * 3000)


@pytest.fixture
def damaged_home(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    database.init_db()
    conn = database.get_db()
    with conn:
        conn.execute("INSERT INTO posts (id, content, status) VALUES ('post-keep', 'keep me', 'draft')")
    conn.close()
    backup = support.create_backup("manual")
    _damage(paths.get_db_path())
    yield backup
    safe_mode.leave()


def test_a_fresh_install_takes_no_empty_pre_migration_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path / "fresh"))
    database.init_db()
    names = os.listdir(paths.get_backups_dir())
    assert not [n for n in names if "premigration" in n], names


def test_the_studio_starts_in_safe_mode_and_says_how_to_restore(damaged_home):
    from fastapi.testclient import TestClient
    from app import app

    name = os.path.basename(damaged_home)
    with TestClient(app, raise_server_exceptions=False) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["status"] == "safe_mode" and health.json()["app"] == "inox-hydra"

        page = client.get("/")
        assert page.status_code == 503
        assert "text/html" in page.headers["content-type"]
        assert "database is damaged" in page.text
        assert name in page.text
        assert f'restore &quot;{damaged_home}&quot; --yes' in page.text
        assert "Restore this backup" in page.text

        api = client.get("/api/posts")
        assert api.status_code == 503
        assert api.json()["detail"]["code"] == "database_damaged"
        assert name in api.json()["detail"]["message"]

        state = client.get("/api/v1/safe-mode").json()
        assert state["backups"][0]["name"] == name
        assert state["backups"][0]["command"] == f'python -m studio.cli restore "{damaged_home}" --yes'

        refused = client.post("/api/v1/safe-mode/restore", json={"name": "../../etc/passwd"})
        assert refused.status_code == 409

        restored = client.post("/api/v1/safe-mode/restore", json={"name": name})
        assert restored.status_code == 200, restored.text
        assert restored.json()["safety_backup"]

        assert not safe_mode.is_active()
        posts = client.get("/api/posts")
        assert posts.status_code == 200
        assert any(p["content"] == "keep me" for p in posts.json()["posts"])
        assert client.get("/api/v1/health").json()["status"] == "ok"


def test_safe_mode_needs_the_token_to_restore(damaged_home):
    from fastapi.testclient import TestClient
    from app import app
    from security import TOKEN_HEADER

    with TestClient(app, raise_server_exceptions=False) as client:
        res = client.post("/api/v1/safe-mode/restore", json={"name": os.path.basename(damaged_home)},
                          headers={TOKEN_HEADER: "wrong"})
        assert res.status_code == 401
        assert safe_mode.is_active()


def test_doctor_prints_the_exact_restore_command(damaged_home):
    env = dict(os.environ)
    result = subprocess.run([sys.executable, "-m", "studio.cli", "doctor"], cwd=REPO_ROOT, env=env,
                            capture_output=True, text=True, timeout=120)
    out = result.stdout + result.stderr
    assert "database unreadable" in out
    assert f'python -m studio.cli restore "{damaged_home}" --yes' in out


def test_with_no_backup_doctor_says_what_to_do(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path / "nobackup"))
    database.init_db()
    _damage(paths.get_db_path())
    result = subprocess.run([sys.executable, "-m", "studio.cli", "doctor"], cwd=REPO_ROOT, env=dict(os.environ),
                            capture_output=True, text=True, timeout=120)
    out = result.stdout + result.stderr
    assert "no backup to restore" in out
    assert "start the studio again" in out
