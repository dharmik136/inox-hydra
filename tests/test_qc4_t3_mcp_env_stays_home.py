"""
A grounding server's environment is not sent to the browser.
============================================================

GET /api/v1/mcp/servers returned each server's `env` and `cwd`, and no screen
rendered them (cycle 4, track 3, batch 0, from the sections report's defects
table). An MCP server's environment is where a creator puts the token a
notes server needs, so a page that holds it holds a credential it never
shows and never needed. The launcher reads the environment from the settings
row; the browser is told only that an environment is set and how many
variables it holds.
"""

import os
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "fake_mcp_server.py")
# Reads as fake on sight, so the credential scan in test_distribution_hygiene
# knows it for a fixture (its allowlist names "notarealkey").
PLANTED = "sk-notarealkey-mcp-env-PLANTED"


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t3_mcp_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    import app as app_module
    from fastapi.testclient import TestClient
    yield TestClient(app_module.app)
    shutil.rmtree(home, ignore_errors=True)


def _add(client):
    answer = client.post("/api/v1/mcp/servers", json={
        "name": "Notes", "command": [sys.executable, FIXTURE], "cwd": "/notes",
        "env": {"NOTES_TOKEN": PLANTED, "NOTES_DIR": "/notes"},
    })
    assert answer.status_code == 200, answer.text
    return answer


def test_the_listing_does_not_carry_the_environment(studio):
    _add(studio)
    answer = studio.get("/api/v1/mcp/servers")
    assert answer.status_code == 200, answer.text
    servers = answer.json()["servers"]
    assert len(servers) == 1
    assert "env" not in servers[0], "the environment, where a token lives, was sent to the browser"
    assert PLANTED not in answer.text
    # What the screen may say instead: that an environment is set, and how big.
    assert servers[0]["env_vars"] == 2


def test_adding_a_server_does_not_echo_the_environment_back(studio):
    answer = _add(studio)
    assert PLANTED not in answer.text
    assert "env" not in answer.json()["server"]


def test_the_launcher_still_reads_the_environment(studio):
    """The environment is kept for the child process; only the browser is spared it."""
    from mcp_client import servers as servers_module
    _add(studio)
    stored = servers_module.list_servers()
    assert stored[0]["env"] == {"NOTES_TOKEN": PLANTED, "NOTES_DIR": "/notes"}
