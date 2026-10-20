"""
Restore From Brand Studio, With a Safety Backup First (D-6, decision D4).
=========================================================================

Restore had no interface: the help sent a creator to a terminal opened in a
checkout folder, which a portable or desktop install does not have. Brand
Studio's Your data now lists a Restore control on each restorable archive. The
route takes a file name from the backups folder, never a path, and restores it
through support.restore_backup, which takes the safety backup first.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import os
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from studio.backend import app as app_module  # noqa: E402
from studio.backend import database, migrations, paths, support  # noqa: E402

ROUTE = "/api/v1/support/restore"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    database.init_db()
    for name in os.listdir(paths.get_backups_dir()):
        os.remove(os.path.join(paths.get_backups_dir(), name))
    return TestClient(app_module.app)


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


def test_restore_puts_back_the_state_in_the_backup_and_keeps_a_safety_copy(client):
    _add_post("before-backup")
    archive = support.create_backup("manual")
    _add_post("after-backup")

    answer = client.post(ROUTE, json={"name": os.path.basename(archive)})
    assert answer.status_code == 200, answer.text
    body = answer.json()

    assert "before-backup" in _post_ids()
    assert "after-backup" not in _post_ids(), "the restore did not replace the database"
    assert body["restored_from"] == os.path.basename(archive)
    safety = body["safety_backup"]
    assert safety and os.path.exists(safety), "no safety backup of the state before the restore"
    assert "pre_restore" in os.path.basename(safety)
    # The safety backup really holds the state from just before.
    support.restore_backup(safety, take_safety_backup=False)
    assert "after-backup" in _post_ids()


def test_the_restored_database_is_brought_up_to_this_build(client, monkeypatch):
    """A backup from an older build is migrated in place, so the running studio can read it."""
    archive = support.create_backup("manual")
    called = []
    real = app_module.init_db
    monkeypatch.setattr(app_module, "init_db", lambda: (called.append(1), real())[1])
    assert client.post(ROUTE, json={"name": os.path.basename(archive)}).status_code == 200
    assert called, "the restored database was not brought up to the current schema"
    conn = sqlite3.connect(paths.get_db_path())
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == migrations.SCHEMA_VERSION
    finally:
        conn.close()


def test_an_unknown_name_is_404_and_changes_nothing(client):
    _add_post("kept")
    answer = client.post(ROUTE, json={"name": "inox_backup_manual_20990101_000000.zip"})
    assert answer.status_code == 404
    assert "kept" in _post_ids()


@pytest.mark.parametrize("name", [
    "../linkedin_studio.db",
    "..\\data\\linkedin_studio.db",
    "/etc/passwd",
    "",
    "backups/x.zip",
])
def test_a_request_never_names_a_path(client, name):
    _add_post("kept")
    support.create_backup("manual")
    answer = client.post(ROUTE, json={"name": name})
    assert answer.status_code in (400, 404), answer.text
    assert "kept" in _post_ids()


def test_a_backup_of_another_profile_is_refused_with_the_reason(client, monkeypatch):
    _add_post("kept")
    archive = support.create_backup("manual")
    real = support.inspect_backup

    def other_profile(path):
        info = real(path)
        info["manifest"] = dict(info.get("manifest") or {}, profile="client-a")
        return info

    monkeypatch.setattr(support, "inspect_backup", other_profile)
    answer = client.post(ROUTE, json={"name": os.path.basename(archive)})
    assert answer.status_code == 409, answer.text
    assert "client-a" in answer.json()["detail"]
    assert "kept" in _post_ids()


def test_a_failed_restore_names_the_safety_backup(client, monkeypatch):
    archive = support.create_backup("manual")

    def fails(*_args, **_kwargs):
        raise support.RestoreFailed("The restore stopped part way (disk full). Everything it had changed was put back.",
                                    safety_backup="/somewhere/inox_backup_pre_restore_x.zip")

    monkeypatch.setattr(support, "restore_backup", fails)
    answer = client.post(ROUTE, json={"name": os.path.basename(archive)})
    assert answer.status_code == 500
    assert "inox_backup_pre_restore_x.zip" in answer.json()["detail"]


def _lead(name):
    from studio.backend.crm import reverse_crm

    reverse_crm.ingest_interaction(full_name=name, linkedin_urn=f"https://www.linkedin.com/in/{name.lower()}-x",
                                   headline="Engineer at Example", company="Example",
                                   interaction_type="COMMENT", comment_text="Good one.")
    conn = sqlite3.connect(paths.get_db_path())
    try:
        return conn.execute("SELECT id FROM leads WHERE full_name = ? OR name = ?", (name, name)).fetchone()[0]
    finally:
        conn.close()


def _lead_ids():
    conn = sqlite3.connect(paths.get_db_path())
    try:
        return {row[0] for row in conn.execute("SELECT id FROM leads")}
    finally:
        conn.close()


def test_a_person_forgotten_since_the_backup_stays_forgotten(client):
    """Review: restoring an older backup brought back someone forgotten after it was made."""
    from studio.backend.crm import reverse_crm

    kept, gone = _lead("Keptperson"), _lead("Goneperson")
    archive = support.create_backup("manual")
    assert reverse_crm.purge_lead(gone)["lead_deleted"]

    answer = client.post(ROUTE, json={"name": os.path.basename(archive)})
    assert answer.status_code == 200, answer.text
    assert answer.json()["forgotten_again"] == 1, answer.json()
    assert gone not in _lead_ids(), "the restore brought back a person forgotten since the backup"
    assert kept in _lead_ids()
    conn = sqlite3.connect(paths.get_db_path())
    try:
        assert conn.execute("SELECT COUNT(*) FROM lead_interactions WHERE lead_id = ?", (gone,)).fetchone()[0] == 0
        # Still noted for removal from the other backups that hold them.
        assert conn.execute("SELECT COUNT(*) FROM forgotten_in_backups WHERE lead_id = ?", (gone,)).fetchone()[0] == 1
    finally:
        conn.close()


def test_the_button_and_safe_mode_finish_a_restore_the_same_way(client, monkeypatch):
    """Keys re-sealed and the docs index rebuilt, by the one function safe mode also uses."""
    archive = support.create_backup("manual")
    done = []
    monkeypatch.setattr(app_module, "_seal_plaintext_secrets", lambda: done.append("seal"))
    monkeypatch.setattr(app_module, "init_docs_search_index", lambda *a, **k: done.append("docs"))
    assert client.post(ROUTE, json={"name": os.path.basename(archive)}).status_code == 200
    assert "seal" in done and "docs" in done, done
    import inspect

    assert "_bring_up_restored(" in inspect.getsource(app_module._open_after_restore)
    assert "_bring_up_restored(" in inspect.getsource(app_module.restore_support_backup)


def test_another_profiles_backup_points_to_the_switcher_not_the_command_line(client, monkeypatch):
    archive = support.create_backup("manual")
    real = support.inspect_backup
    monkeypatch.setattr(support, "inspect_backup",
                        lambda path: dict(real(path), manifest=dict(real(path).get("manifest") or {}, profile="client-a")))
    detail = client.post(ROUTE, json={"name": os.path.basename(archive)}).json()["detail"]
    assert "on purpose" not in detail and "profile switcher" in detail, detail


def test_the_question_names_everything_a_restore_replaces():
    with open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "BrandStudioSurface.tsx"), encoding="utf-8") as handle:
        surface = handle.read()
    question = surface.split("const question", 1)[1].split("window.confirm", 1)[0]
    for part in ("identity", "settings and stored keys", "media", "people you forgot", "forgotten again"):
        assert part in question, f"the question does not say a restore replaces {part!r}"


def test_brand_studio_offers_restore_on_each_restorable_archive():
    with open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "BrandStudioSurface.tsx"), encoding="utf-8") as handle:
        surface = handle.read()
    with open(os.path.join(REPO_ROOT, "studio", "ui", "src", "lib", "api.ts"), encoding="utf-8") as handle:
        client_source = handle.read()
    assert ROUTE in client_source
    assert "restoreBackup" in surface
    assert "archive.restorable" in surface, "the control is not limited to archives that can be restored"
    assert "window.confirm" in surface and "safety backup" in surface


def test_the_help_offers_the_button_before_the_terminal():
    with open(os.path.join(REPO_ROOT, "docs", "help", "back-up-restore-and-export.md"), encoding="utf-8") as handle:
        article = handle.read()
    assert "The interface has no restore button" not in article
    section = article.split("## Restore a backup", 1)[1].split("\n## ", 1)[0]
    assert section.index("**Restore**") < section.index("python -m studio.cli restore")


def test_the_restore_button_restores_from_the_interface(tmp_path, monkeypatch):
    """Brand Studio, Local security, Restore, OK: the backup's state is back and the note says so."""
    pytest.importorskip("playwright.sync_api")
    if not os.path.exists(os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")):
        pytest.skip("the interface is not built")
    import socket
    import threading
    import time

    import uvicorn
    from playwright.sync_api import sync_playwright

    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    database.init_db()
    _add_post("before-backup")
    archive = support.create_backup("manual")
    _add_post("after-backup")

    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    server = uvicorn.Server(uvicorn.Config(app=app_module.app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
                break
            except OSError:
                time.sleep(0.05)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(service_workers="block")
                page = context.new_page()
                page.goto(f"http://127.0.0.1:{port}/#/settings", wait_until="networkidle")
                page.get_by_role("tab", name="Local security").click()
                questions = []
                page.on("dialog", lambda dialog: (questions.append(dialog.message), dialog.accept()))
                page.get_by_role("button", name=f"Restore {os.path.basename(archive)}").click()
                page.get_by_role("button", name="Reload the studio").wait_for(timeout=10000)
                assert questions and "safety backup" in questions[0]
                assert page.get_by_text(f"Restored {os.path.basename(archive)}").count() == 1
                context.close()
            finally:
                browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
    assert "after-backup" not in _post_ids() and "before-backup" in _post_ids()
