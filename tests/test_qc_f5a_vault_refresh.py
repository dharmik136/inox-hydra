"""
Export to Obsidian in Brand Studio refreshes the vault the creator opened.
=========================================================================

The button took no folder and every press wrote a new
exports/obsidian_vault_<timestamp>. A creator who opened the first export in
Obsidian and wrote in it never saw fresh data there: the refresh promised in
the release notes existed only in the CLI's --output. Now the button writes one
vault per profile, at the same place each time, and says what it kept.
"""

import os
import sys
import tempfile
import time

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))


@pytest.fixture
def client(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_vault_refresh_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    from fastapi.testclient import TestClient
    import app as app_module

    init_db()
    return TestClient(app_module.app)


def test_pressing_it_again_refreshes_the_same_vault(client):
    first = client.post("/api/v1/support/export", json={"format": "obsidian"}).json()
    home_note = os.path.join(first["path"], "Home.md")
    with open(home_note, "a", encoding="utf-8") as handle:
        handle.write("Ideas for next month.\n")
    time.sleep(1.1)  # the old folder name carried the second it was written

    second = client.post("/api/v1/support/export", json={"format": "obsidian"}).json()
    assert second["path"] == first["path"], "each press wrote a new vault instead of refreshing the one in use"
    assert "Ideas for next month." in open(home_note, encoding="utf-8").read()
    assert "kept" in second["note"].lower(), second["note"]


def test_the_request_still_cannot_choose_the_folder(client, tmp_path):
    import paths

    elsewhere = str(tmp_path / "somewhere")
    result = client.post("/api/v1/support/export", json={"format": "obsidian", "destination": elsewhere}).json()
    assert result["path"].startswith(paths.get_app_home())
    assert not os.path.exists(elsewhere)


def test_a_folder_it_may_not_write_is_refused_with_the_reason(client):
    import paths

    vault = os.path.join(paths.get_exports_dir(), "obsidian_vault")
    os.makedirs(vault, exist_ok=True)
    with open(os.path.join(vault, "Journal.md"), "w", encoding="utf-8") as handle:
        handle.write("private")
    response = client.post("/api/v1/support/export", json={"format": "obsidian"})
    assert response.status_code == 409, response.text
    assert "not an earlier Inox Hydra export" in response.json()["detail"]
    assert os.listdir(vault) == ["Journal.md"]
