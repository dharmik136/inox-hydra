"""
Grounding reaches the draft, and never becomes something the draft depends on.
==============================================================================

The client existed and nothing called it. This is the wiring: material from
the creator's own MCP servers becomes labelled sections on the brief the hook
generator sends, and the record of what grounded a post travels back out with
the hooks.

Two properties matter more than the feature working.

  It cannot break generation. A creator with no servers, a package that failed
  to import, a notes server that is down, and an outright exception inside the
  gather all produce the same thing: a post written exactly as it is written
  today. The briefing module already states this rule for model enhancement,
  and grounding is held to it too.

  It cannot lie about egress. The provenance records whether this creator's
  notes left the machine, on every path including the ones where the model was
  never reached, because the material left either way and a record that covers
  only the successes is not a record of what happened.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from agno_agentos.agents import content_copilot_agent as copilot_module
from agno_agentos.agents.content_copilot_agent import LinkedInContentCopilotAgent
from agno_agentos.model_gateway import AIProviderConfig
from mcp_client import servers as servers_module

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "fake_mcp_server.py")

DRAFT = (
    "We moved the migration ledger to forward only this quarter and it changed "
    "how the team thinks about rollbacks entirely. Here is what we learned "
    "about schema changes under load."
)


def server_command(mode=None):
    command = [sys.executable, FIXTURE]
    if mode:
        command.append(mode)
    return command


@pytest.fixture(autouse=True)
def clean_servers():
    for existing in servers_module.list_servers():
        servers_module.remove_server(existing["name"])
    yield
    for existing in servers_module.list_servers():
        servers_module.remove_server(existing["name"])


def _agent(provider="local_deterministic"):
    return LinkedInContentCopilotAgent(ai_config=AIProviderConfig(
        provider=provider,
        api_key="notarealkey",
        model="test-model",
        status="connected",
    ))


# ---------------------------------------------------------------------------
# It reaches the brief
# ---------------------------------------------------------------------------

def test_enabled_material_reaches_the_prompt(monkeypatch):
    """
    The point of the whole feature: the model is shown the creator's own
    record rather than being asked to invent a specific from nothing.
    """
    servers_module.add_server("Engineering Notes", server_command())
    servers_module.set_enabled("Engineering Notes", True)

    seen = {}

    def capture(config, user_prompt, system_prompt="", **kwargs):
        seen["user"] = user_prompt
        seen["system"] = system_prompt
        return "\n".join(f"{n}. Hook {n} on forward only migrations and what broke" for n in range(1, 7))

    monkeypatch.setattr(copilot_module, "execute_llm_completion", capture)

    _agent()._generate_llm_hooks(topic="migrations", content=DRAFT)

    assert "forward only migrations" in seen["user"], (
        "the creator's notes never reached the prompt"
    )
    assert "Migration Notes" in seen["user"], (
        "material arrived unlabelled, so the model reads it as background noise"
    )


def test_the_model_is_told_what_the_material_is(monkeypatch):
    """
    Extra sections with no explanation get treated as background and the model
    writes the same generic hook anyway. Naming them is what converts material
    into specificity.
    """
    servers_module.add_server("Notes", server_command())
    servers_module.set_enabled("Notes", True)

    seen = {}
    monkeypatch.setattr(
        copilot_module, "execute_llm_completion",
        lambda c, u, system_prompt="", **k: seen.update(system=system_prompt, user=u) or "",
    )

    _agent()._generate_llm_hooks(topic="migrations", content=DRAFT)

    combined = seen.get("system", "") + seen.get("user", "")
    assert "author's own notes" in combined, (
        "the model was handed the material without being told whose it is or "
        "what to do with it"
    )


def test_no_grounding_instruction_when_there_is_no_material(monkeypatch):
    """
    An instruction to draw on sections that are not there invites invention,
    which is the one thing this feature exists to avoid.
    """
    seen = {}
    monkeypatch.setattr(
        copilot_module, "execute_llm_completion",
        lambda c, u, system_prompt="", **k: seen.update(system=system_prompt, user=u) or "",
    )

    _agent()._generate_llm_hooks(topic="migrations", content=DRAFT)

    combined = seen.get("system", "") + seen.get("user", "")
    assert "author's own notes" not in combined


# ---------------------------------------------------------------------------
# It cannot break generation
# ---------------------------------------------------------------------------

def test_a_server_that_is_down_does_not_stop_the_post(monkeypatch):
    servers_module.add_server("Broken", ["a-binary-that-is-not-installed-anywhere"])
    servers_module.set_enabled("Broken", True)

    monkeypatch.setattr(
        copilot_module, "execute_llm_completion",
        lambda *a, **k: "\n".join(f"{n}. Hook number {n} about systems that stands alone" for n in range(1, 7)),
    )

    hooks, record = _agent()._generate_llm_hooks(topic="migrations", content=DRAFT)

    assert hooks, "a dead notes server stopped the studio writing a post"
    assert record["grounding"]["grounded"] is False


def test_an_exception_inside_gather_does_not_stop_the_post(monkeypatch):
    """
    gather is documented as never raising. This asserts the caller does not
    rely on that documentation being true.
    """
    def explode(**kwargs):
        raise RuntimeError("something inside grounding broke")

    monkeypatch.setattr(copilot_module, "gather", explode)
    monkeypatch.setattr(
        copilot_module, "execute_llm_completion",
        lambda *a, **k: "\n".join(f"{n}. Hook number {n} about systems that stands alone" for n in range(1, 7)),
    )

    hooks, record = _agent()._generate_llm_hooks(topic="migrations", content=DRAFT)

    assert hooks, "an exception in grounding took the whole generation with it"
    assert record["grounding"]["grounded"] is False


def test_the_agent_works_when_the_package_is_absent(monkeypatch):
    """
    The import is guarded. This proves the guard is load bearing rather than
    decorative, by removing the package the way a broken install would.
    """
    monkeypatch.setattr(copilot_module, "gather", None)
    monkeypatch.setattr(copilot_module, "as_brief_inputs", None)
    monkeypatch.setattr(
        copilot_module, "execute_llm_completion",
        lambda *a, **k: "\n".join(f"{n}. Hook number {n} about systems that stands alone" for n in range(1, 7)),
    )

    hooks, record = _agent()._generate_llm_hooks(topic="migrations", content=DRAFT)

    assert hooks
    assert record["grounding"]["grounded"] is False


def test_a_disabled_server_contributes_nothing_to_a_real_draft(monkeypatch):
    servers_module.add_server("Notes", server_command())

    seen = {}
    monkeypatch.setattr(
        copilot_module, "execute_llm_completion",
        lambda c, u, system_prompt="", **k: seen.update(user=u) or "",
    )

    _agent()._generate_llm_hooks(topic="migrations", content=DRAFT)

    assert "forward only migrations" not in seen["user"], (
        "a server the creator never switched on was read into their prompt"
    )


# ---------------------------------------------------------------------------
# It cannot lie about where the material went
# ---------------------------------------------------------------------------

def test_provenance_records_that_notes_left_the_machine(monkeypatch):
    servers_module.add_server("Notes", server_command())
    servers_module.set_enabled("Notes", True)

    monkeypatch.setattr(
        copilot_module, "execute_llm_completion",
        lambda *a, **k: "\n".join(f"{n}. Hook {n} about migrations and the rollback we ran" for n in range(1, 7)),
    )

    _hooks, record = _agent(provider="gemini")._generate_llm_hooks(
        topic="migrations", content=DRAFT
    )

    assert record["grounding"]["grounded"] is True
    assert record["grounding"]["left_this_machine"] is True, (
        "the creator's notes were sent to a hosted provider and the record "
        "does not say so"
    )


def test_a_local_provider_records_that_nothing_left(monkeypatch):
    servers_module.add_server("Notes", server_command())
    servers_module.set_enabled("Notes", True)

    monkeypatch.setattr(
        copilot_module, "execute_llm_completion",
        lambda *a, **k: "\n".join(f"{n}. Hook {n} about migrations and the rollback we ran" for n in range(1, 7)),
    )

    _hooks, record = _agent(provider="local_deterministic")._generate_llm_hooks(
        topic="migrations", content=DRAFT
    )

    assert record["grounding"]["left_this_machine"] is False


@pytest.mark.parametrize("failure", ["provider error", "empty response"])
def test_egress_is_recorded_even_when_the_generation_failed(monkeypatch, failure):
    """
    The material left the machine before the model was ever called. A record
    that only covers the successful paths is not a record of what happened.
    """
    servers_module.add_server("Notes", server_command())
    servers_module.set_enabled("Notes", True)

    def fail(*args, **kwargs):
        if failure == "provider error":
            raise RuntimeError("the provider is down")
        return ""

    monkeypatch.setattr(copilot_module, "execute_llm_completion", fail)

    hooks, record = _agent(provider="gemini")._generate_llm_hooks(
        topic="migrations", content=DRAFT
    )

    assert hooks is None
    assert record["grounding"]["left_this_machine"] is True, (
        f"on the '{failure}' path the notes still went to the provider and "
        f"nothing recorded it"
    )


def test_every_generation_carries_a_grounding_record(monkeypatch):
    """Absent is not the same as false, and a reader cannot tell them apart."""
    monkeypatch.setattr(
        copilot_module, "execute_llm_completion",
        lambda *a, **k: "\n".join(f"{n}. Hook {n} about systems thinking in practice" for n in range(1, 7)),
    )

    _hooks, record = _agent()._generate_llm_hooks(topic="migrations", content=DRAFT)

    assert "grounding" in record
    assert record["grounding"]["grounded"] is False
