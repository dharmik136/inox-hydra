"""
The grounding feature is reachable, and reaching it is not a free command execution.
====================================================================================

The MCP client was built, tested and wired into hook generation, and had no
API route and no interface. A server could only be added by calling Python, so
the feature a creator would actually want was unreachable to them.

These routes are that surface. One property decides their shape: adding a
server stores a command this studio will execute. That is not incidental, it
is what MCP is, and it is a larger grant than anything else in this API.

So the tests here are mostly about the boundary rather than the feature.

  The extension must never be able to reach these. RELAYABLE_PATHS in
  background.js lists three ingest endpoints, and adding a fourth would be a
  one line change whose consequence nobody would notice.

  A command stays a list. The browser launcher was rewritten after
  "--gpu-launcher=cmd.exe /c calc.exe" turned a URL field into arbitrary
  execution, and this field is openly a command.

  Adding does not enable, over the API as well as in the module.
"""

import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module
from mcp_client import servers as servers_module

client = TestClient(app_module.app)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "fake_mcp_server.py")


def server_command():
    return [sys.executable, FIXTURE]


@pytest.fixture(autouse=True)
def clean_servers():
    for existing in servers_module.list_servers():
        servers_module.remove_server(existing["name"])
    yield
    for existing in servers_module.list_servers():
        servers_module.remove_server(existing["name"])


# ---------------------------------------------------------------------------
# The boundary
# ---------------------------------------------------------------------------

def test_the_extension_cannot_reach_these_routes():
    """
    A content script on linkedin.com relays through the service worker, and
    the worker refuses any path not on its allowlist. These routes execute
    commands, so they must never appear on it.
    """
    background = open(
        os.path.join(REPO_ROOT, "studio", "extension", "background.js"), encoding="utf-8"
    ).read()

    block = background[background.index("RELAYABLE_PATHS"):]
    block = block[:block.index("]")]

    assert "/api/v1/mcp" not in block, (
        "an MCP route is relayable, so a page on linkedin.com can ask the "
        "studio to run a command"
    )
    assert block.count("/api/") == 3, (
        "the relay allowlist changed size; every entry on it is reachable "
        "from a LinkedIn page and needs to be looked at"
    )


def test_a_command_given_as_a_string_is_refused():
    """
    Splitting a string into argv is where quoting bugs and injection both
    live, and this field is a command rather than something that merely
    becomes one.
    """
    response = client.post("/api/v1/mcp/servers", json={
        "name": "Shell", "command": "python -c print(1)",
    })
    assert response.status_code == 422, "a string command was accepted as a command"
    assert servers_module.list_servers() == []


def test_an_empty_command_is_refused():
    response = client.post("/api/v1/mcp/servers", json={"name": "Empty", "command": []})
    assert response.status_code == 422
    assert servers_module.list_servers() == []


def test_adding_over_the_api_does_not_enable():
    """
    The consent rule has to hold at the route too, or the module's guarantee
    is decorative.
    """
    response = client.post("/api/v1/mcp/servers", json={
        "name": "Notes", "command": server_command(),
    })
    assert response.status_code == 200
    assert response.json()["server"]["enabled"] is False
    assert servers_module.enabled_servers() == []


def test_the_request_model_has_no_enabled_field():
    """A payload cannot smuggle it in, because there is nowhere for it to go."""
    assert "enabled" not in app_module.McpServerRequest.model_fields


# ---------------------------------------------------------------------------
# The feature
# ---------------------------------------------------------------------------

def test_a_server_can_be_added_listed_enabled_and_removed():
    """The whole loop a creator performs, over the API they will actually use."""
    assert client.post("/api/v1/mcp/servers", json={
        "name": "Engineering Notes", "command": server_command(),
        "description": "My working notes",
    }).status_code == 200

    listing = client.get("/api/v1/mcp/servers").json()
    assert len(listing["servers"]) == 1
    assert listing["servers"][0]["enabled"] is False

    toggled = client.post("/api/v1/mcp/servers/Engineering Notes/enabled", json={"enabled": True})
    assert toggled.status_code == 200
    assert toggled.json()["enabled"] is True
    assert len(servers_module.enabled_servers()) == 1

    assert client.delete("/api/v1/mcp/servers/Engineering Notes").status_code == 200
    assert client.get("/api/v1/mcp/servers").json()["servers"] == []


def test_a_duplicate_name_is_refused_rather_than_silently_replacing():
    payload = {"name": "Notes", "command": server_command()}
    assert client.post("/api/v1/mcp/servers", json=payload).status_code == 200
    assert client.post("/api/v1/mcp/servers", json=payload).status_code == 400
    assert len(servers_module.list_servers()) == 1


def test_enabling_something_that_does_not_exist_is_an_error():
    response = client.post("/api/v1/mcp/servers/Nothing/enabled", json={"enabled": True})
    assert response.status_code == 400


def test_removing_something_that_does_not_exist_is_a_404():
    assert client.delete("/api/v1/mcp/servers/Nothing").status_code == 404


# ---------------------------------------------------------------------------
# The honesty surface, which is the reason the preview route exists
# ---------------------------------------------------------------------------

def test_the_listing_says_where_material_would_go():
    """
    The backend has been computing this on every gather and telling nobody.
    An interface cannot warn about egress it is never shown.
    """
    body = client.get("/api/v1/mcp/servers").json()
    assert "egress" in body
    assert "leaves_this_machine" in body["egress"]
    assert body["egress"]["summary"]


def test_preview_shows_the_material_before_a_draft_uses_it():
    """
    Showing the creator what their notes server handed over, before it is
    pasted into a prompt, is the difference between consent and a setting.
    """
    client.post("/api/v1/mcp/servers", json={"name": "Notes", "command": server_command()})
    client.post("/api/v1/mcp/servers/Notes/enabled", json={"enabled": True})

    body = client.get("/api/v1/mcp/preview").json()

    assert body["material"], "the preview gathered nothing from an enabled server"
    assert any("forward only migrations" in item["text"] for item in body["material"])
    assert body["material"][0]["server"] == "Notes"
    assert "egress" in body


def test_preview_reads_only_enabled_servers():
    """It previews the path a draft takes, not a different one."""
    client.post("/api/v1/mcp/servers", json={"name": "Notes", "command": server_command()})

    body = client.get("/api/v1/mcp/preview").json()
    assert body["material"] == []


def test_preview_reports_a_server_that_is_down():
    """
    Naming the broken one is the difference between a creator fixing it and
    wondering why their posts read generic again.
    """
    client.post("/api/v1/mcp/servers", json={
        "name": "Broken", "command": ["a-binary-that-is-not-installed-anywhere"],
    })
    client.post("/api/v1/mcp/servers/Broken/enabled", json={"enabled": True})

    body = client.get("/api/v1/mcp/preview").json()

    assert body["material"] == []
    assert body["errors"] and body["errors"][0]["server"] == "Broken"


def test_preview_reports_its_budget():
    """A creator who sees a truncated note should be able to tell why."""
    body = client.get("/api/v1/mcp/preview").json()
    assert body["bytes_budget"] > 0
    assert body["bytes_used"] <= body["bytes_budget"]
