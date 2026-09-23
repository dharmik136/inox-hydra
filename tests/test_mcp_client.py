"""
The studio reads the creator's own material, only when asked, and says where it goes.
=====================================================================================

MCP as a client rather than a server. An agent driving a local studio is thin,
because both are already on the same machine. A draft grounded in the
creator's notes, repository and calendar is not: it is the one thing a cloud
writing tool structurally cannot do, having never seen their work, and it is
the reason their output reads generic no matter how good the model gets.

Three things are worth failing a build over, and they are what these tests are
mostly about.

  Consent. Adding a server and agreeing to be read are separate acts. A
  configuration pasted from a README must not cause a notes directory to be
  read on the next generation.

  Egress. This bundle tells every user it holds their work "entirely on your
  own machine. No cloud account, no data egress." Grounding puts that under
  real pressure, because gathered material is pasted into a prompt that may go
  to a hosted provider. The studio has to say so, computed from the provider
  actually in force, every time.

  Never a dependency. A notes server that is down produces no grounding and no
  exception. The draft is written without it, exactly as it is today.

The protocol tests run a real server subprocess rather than a mock. A mocked
transport proves the client calls its own functions in order, and nothing
about whether it speaks MCP, which is the only part a user could notice being
wrong.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import mcp_client
from mcp_client import grounding as grounding_module
from mcp_client import servers as servers_module
from mcp_client.protocol import McpServer

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "fake_mcp_server.py")


def server_command(mode=None):
    command = [sys.executable, FIXTURE]
    if mode:
        command.append(mode)
    return command


@pytest.fixture(autouse=True)
def clean_servers():
    """Each test starts with nothing configured, which is also the shipped state."""
    for existing in servers_module.list_servers():
        servers_module.remove_server(existing["name"])
    yield
    for existing in servers_module.list_servers():
        servers_module.remove_server(existing["name"])


# ---------------------------------------------------------------------------
# The protocol, against a real server
# ---------------------------------------------------------------------------

def test_the_client_completes_a_handshake_and_reads_a_resource():
    with McpServer("fixture", server_command()) as server:
        resources = server.list_resources()
        assert len(resources) == 3

        text = server.read_resource("notes://migration")
        assert text and "forward only migrations" in text


def test_a_server_that_refuses_the_handshake_is_not_used():
    server = McpServer("refuser", server_command("refuse"))
    try:
        assert server.start() is False
        assert server.list_resources() == []
    finally:
        server.stop()


def test_noise_on_stdout_does_not_break_the_client():
    """
    Servers print startup banners. A client that treated the first line as the
    reply would fail against half the servers in the wild.
    """
    with McpServer("noisy", server_command("noisy")) as server:
        assert server.list_resources(), "a banner line stopped the client reading"


def test_a_server_that_never_answers_times_out_rather_than_hanging():
    """
    Grounding is an enhancement. A studio that stalls because a notes server
    wedged has made the creator's day worse, not better.
    """
    server = McpServer("slow", server_command("slow"))
    try:
        assert server.start() is False
    finally:
        server.stop()


def test_a_command_that_does_not_exist_fails_quietly():
    server = McpServer("missing", ["a-binary-that-is-not-installed-anywhere"])
    try:
        assert server.start() is False
    finally:
        server.stop()


def test_a_binary_resource_contributes_nothing():
    """There is nothing useful to tell a language model about a base64 PNG."""
    with McpServer("fixture", server_command()) as server:
        assert server.read_resource("notes://binary") is None


def test_one_resource_cannot_exceed_its_budget():
    with McpServer("huge", server_command("huge")) as server:
        text = server.read_resource("notes://long")
        assert text is not None
        assert len(text) <= 64 * 1024


def test_the_client_cannot_call_tools():
    """
    Reading resources grounds a draft. Calling tools performs actions: sending
    mail, writing files, opening pull requests. A writing assistant that can
    act on the world is a different product with a different consent
    conversation, and the absence is deliberate rather than pending.
    """
    source = open(
        os.path.join(os.path.dirname(__file__), "..", "studio", "backend",
                     "mcp_client", "protocol.py"),
        encoding="utf-8",
    ).read()

    # The string appears in the docstring that explains why it is absent, so
    # the assertion is on the call site rather than the word.
    assert '_request("tools/call"' not in source, (
        "the client issues tools/call, which is a much larger grant than "
        "grounding needs"
    )
    assert not hasattr(McpServer, "call_tool")
    assert "resources/read" in source, "the read path is gone entirely"


# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------

def test_a_newly_added_server_is_switched_off():
    """
    The whole consent design in one assertion. Adding tells the studio a
    command exists; enabling is the creator saying "read this and put what you
    find in my drafts".
    """
    result = servers_module.add_server("Notes", server_command())
    assert result["status"] == "success"
    assert result["server"]["enabled"] is False
    assert servers_module.enabled_servers() == []


def test_adding_cannot_enable_in_one_step():
    """
    There is no parameter for it, and an `enabled` key in the payload must not
    become one by accident.
    """
    import inspect
    assert "enabled" not in inspect.signature(servers_module.add_server).parameters

    servers_module.add_server("Notes", server_command())
    assert servers_module.enabled_servers() == []


def test_nothing_is_gathered_from_a_disabled_server():
    servers_module.add_server("Notes", server_command())
    result = grounding_module.gather(provider="local_deterministic")
    assert result["material"] == [], (
        "material was read from a server the creator never switched on"
    )


def test_enabling_reports_the_state_it_achieved():
    servers_module.add_server("Notes", server_command())
    assert servers_module.set_enabled("Notes", True)["enabled"] is True
    assert len(servers_module.enabled_servers()) == 1
    assert servers_module.set_enabled("Notes", False)["enabled"] is False
    assert servers_module.enabled_servers() == []


def test_a_command_given_as_a_string_is_refused():
    """
    Splitting a string into argv is where quoting bugs and injection both
    live. The browser launcher was rewritten for the same reason.
    """
    result = servers_module.add_server("Shell", "python fake_mcp_server.py")
    assert result["status"] == "error"
    assert servers_module.list_servers() == []


def test_an_unreadable_configuration_grounds_nothing(monkeypatch):
    """Fail toward doing nothing, which is the direction that cannot surprise anyone."""
    def broken():
        raise RuntimeError("database is locked")

    monkeypatch.setattr(servers_module, "get_db", broken)
    assert servers_module.list_servers() == []
    assert servers_module.enabled_servers() == []


# ---------------------------------------------------------------------------
# Egress, which is the promise this feature puts under pressure
# ---------------------------------------------------------------------------

def test_a_local_provider_is_reported_as_staying_on_the_machine():
    report = grounding_module.egress_report("local_deterministic")
    assert report["leaves_this_machine"] is False
    assert "stays on this machine" in report["summary"]


@pytest.mark.parametrize("provider", ["gemini", "openai", "anthropic", "something_new"])
def test_any_unrecognised_provider_is_treated_as_leaving_the_machine(provider):
    """
    Deny by default. A provider nobody has classified yet must read as egress,
    because being wrong in the other direction tells someone their private
    notes stayed home when they did not.
    """
    report = grounding_module.egress_report(provider)
    assert report["leaves_this_machine"] is True
    assert "leaves your machine" in report["summary"]


def test_the_report_is_produced_on_every_gather():
    """
    Not cached and not optional. The provider can change between one draft and
    the next, so a stored answer would be a claim about a configuration that
    is no longer in force.
    """
    result = grounding_module.gather(provider="gemini")
    assert result["egress"]["leaves_this_machine"] is True
    result = grounding_module.gather(provider="local_deterministic")
    assert result["egress"]["leaves_this_machine"] is False


# ---------------------------------------------------------------------------
# Gathering, and never becoming a dependency
# ---------------------------------------------------------------------------

def test_material_is_gathered_from_an_enabled_server():
    servers_module.add_server("Engineering Notes", server_command())
    servers_module.set_enabled("Engineering Notes", True)

    result = grounding_module.gather(provider="local_deterministic")

    assert result["material"], "nothing was gathered from an enabled server"
    assert all(item["server"] == "Engineering Notes" for item in result["material"])
    assert any("forward only migrations" in item["text"] for item in result["material"])


def test_a_server_that_is_down_is_named_and_does_not_raise():
    servers_module.add_server("Broken", ["a-binary-that-is-not-installed-anywhere"])
    servers_module.set_enabled("Broken", True)

    result = grounding_module.gather(provider="local_deterministic")

    assert result["material"] == []
    assert result["errors"], (
        "a server failed silently, so the creator wonders why their post reads "
        "generic again"
    )
    assert result["errors"][0]["server"] == "Broken"


def test_the_whole_grounding_block_is_bounded():
    """
    A prompt is a fixed budget shared with the creator's own draft. Material
    that crowds it out makes the output worse, which is the opposite of the
    point.
    """
    servers_module.add_server("Huge", server_command("huge"))
    servers_module.set_enabled("Huge", True)

    result = grounding_module.gather(provider="local_deterministic")

    assert result["bytes_used"] <= grounding_module.MAX_GROUNDING_BYTES
    total = sum(len(item["text"]) for item in result["material"])
    assert total <= grounding_module.MAX_GROUNDING_BYTES


def test_a_server_offering_nothing_is_not_an_error_state():
    servers_module.add_server("Empty", server_command("empty"))
    servers_module.set_enabled("Empty", True)

    result = grounding_module.gather(provider="local_deterministic")
    assert result["material"] == []


# ---------------------------------------------------------------------------
# Handing it to the agent
# ---------------------------------------------------------------------------

def test_material_becomes_labelled_brief_inputs():
    """
    One input per source, not a single blob. Brief renders inputs as titled
    sections, and a model given "Grounding: <6kb>" treats it as background
    noise while a model given "Migration Notes: <text>" treats it as something
    to draw on.
    """
    servers_module.add_server("Notes", server_command())
    servers_module.set_enabled("Notes", True)

    gathered = grounding_module.gather(provider="local_deterministic")
    inputs = grounding_module.as_brief_inputs(gathered)

    assert inputs, "nothing reached the brief"
    assert "migration_notes" in inputs
    assert all(isinstance(value, str) and value for value in inputs.values())


def test_the_inputs_survive_a_brief_render():
    """The real consumer, rather than a shape assumed to be right."""
    from agno_agentos.briefing import Brief

    servers_module.add_server("Notes", server_command())
    servers_module.set_enabled("Notes", True)
    gathered = grounding_module.gather(provider="local_deterministic")

    brief = Brief(
        role="You write LinkedIn posts.",
        objective="Draft a hook.",
        inputs=grounding_module.as_brief_inputs(gathered),
        output_contract="One line.",
    )
    rendered = brief.user_prompt()

    assert "Migration Notes" in rendered, "the section label did not survive"
    assert "forward only migrations" in rendered


def test_provenance_records_what_grounded_the_post():
    servers_module.add_server("Notes", server_command())
    servers_module.set_enabled("Notes", True)

    gathered = grounding_module.gather(provider="gemini")
    record = grounding_module.grounding_provenance(gathered)

    assert record["grounded"] is True
    assert record["source_count"] > 0
    assert record["sources"][0]["server"] == "Notes"
    assert record["left_this_machine"] is True, (
        "provenance does not record that this draft sent the creator's notes "
        "to a hosted provider"
    )


def test_an_ungrounded_draft_says_so():
    record = grounding_module.grounding_provenance(
        grounding_module.gather(provider="local_deterministic")
    )
    assert record["grounded"] is False
    assert record["source_count"] == 0


def test_the_module_declares_no_undeclared_dependency():
    """
    The mcp SDK is importable on the machine this was written on and is
    declared nowhere, which is exactly how a pyyaml gated test passed for
    weeks while never running in CI. build_portable vendors from
    requirements.txt, so an undeclared import is present in development and
    absent in the artifact a user runs.
    """
    root = os.path.join(os.path.dirname(__file__), "..", "studio", "backend", "mcp_client")
    for name in os.listdir(root):
        if not name.endswith(".py"):
            continue
        source = open(os.path.join(root, name), encoding="utf-8").read()
        assert "import mcp\n" not in source and "from mcp " not in source, (
            f"{name} imports the mcp SDK, which is not in requirements.txt"
        )
