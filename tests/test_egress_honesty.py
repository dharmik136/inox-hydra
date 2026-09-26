"""
A refusal is not an empty answer, a provider choice means something, and the ledger says what it misses.
=======================================================================================================

Three defects that all took the same shape: the product behaved in a way that
was defensible, and then described it in a way that was not.

  A policy refusal was absorbed as an empty result. model_gateway caught
  EgressRefused in a broad `except Exception`, printed it to stdout, and
  returned "". Every caller reads "" as "the model produced nothing" and falls
  through to deterministic output, so under INOX_NO_EGRESS=1 the studio
  behaved exactly as though the provider had answered with nothing: a
  deterministic draft, no explanation, and the ledger's refused counter as the
  only evidence anywhere that a decision had been made.

  A provider choice was silently overridden. repurposer fell back to a
  hardcoded Google endpoint whenever the configured provider was absent or
  failed, using a key read from GEMINI_API_KEY, GOOGLE_API_KEY or a settings
  row, none of which has anything to do with what the creator chose. An
  Anthropic user with a stale Gemini key in settings had their draft sent to
  Google, unasked.

  The ledger claimed completeness it could not deliver. It said the counters
  came from "the one point every outbound request passes through", while the
  browser launcher and MCP sources both reach the network without passing it.
  A reader would take "Nothing has left this machine" as covering everything.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import egress as egress_module
from agno_agentos.model_gateway import AIProviderConfig, execute_llm_completion

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _read(*parts):
    with open(os.path.join(REPO_ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


# ---------------------------------------------------------------------------
# A refusal reaches the caller
# ---------------------------------------------------------------------------

def test_a_refused_completion_raises_rather_than_returning_empty(monkeypatch):
    """
    The defining case. INOX_NO_EGRESS=1 must be distinguishable from a model
    that answered with nothing, because the two call for different responses
    from the person reading the output.
    """
    monkeypatch.setenv("INOX_NO_EGRESS", "1")

    config = AIProviderConfig(
        provider="gemini", api_key="notarealkey", model="gemini-2.5-flash",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        status="connected",
    )

    with pytest.raises(egress_module.EgressRefused):
        execute_llm_completion(config, "write me a hook", system_prompt="be brief")


def test_the_refusal_names_the_flag_that_caused_it(monkeypatch):
    """
    A creator who sees a deterministic draft needs to be able to find out why.
    """
    monkeypatch.setenv("INOX_NO_EGRESS", "1")
    config = AIProviderConfig(
        provider="gemini", api_key="notarealkey", model="gemini-2.5-flash",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        status="connected",
    )

    with pytest.raises(egress_module.EgressRefused) as caught:
        execute_llm_completion(config, "write me a hook")

    assert "INOX_NO_EGRESS" in str(caught.value)


def test_the_agent_records_a_refusal_in_provenance(monkeypatch):
    """
    The refusal has to survive as far as the record of where the output came
    from, or the honesty stops at the module boundary.
    """
    from agno_agentos.agents.content_copilot_agent import LinkedInContentCopilotAgent

    monkeypatch.setenv("INOX_NO_EGRESS", "1")
    agent = LinkedInContentCopilotAgent(ai_config=AIProviderConfig(
        provider="gemini", api_key="notarealkey", model="gemini-2.5-flash",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        status="connected",
    ))

    hooks, record = agent._generate_llm_hooks(topic="migrations", content="x" * 80)

    assert hooks is None
    assert record["source"] == "deterministic"
    assert "INOX_NO_EGRESS" in record["reason"], (
        f"the refusal did not reach provenance, so the deterministic draft is "
        f"unexplained: {record['reason']}"
    )


def test_an_ordinary_provider_error_is_still_swallowed(monkeypatch):
    """
    Only the refusal changed. A network failure still degrades to the
    deterministic path rather than raising, because that was never dishonest:
    the model genuinely produced nothing.
    """
    monkeypatch.delenv("INOX_NO_EGRESS", raising=False)
    config = AIProviderConfig(
        provider="gemini", api_key="notarealkey", model="gemini-2.5-flash",
        base_url="http://127.0.0.1:59998/v1", status="connected",
    )
    assert execute_llm_completion(config, "write me a hook") == ""


# ---------------------------------------------------------------------------
# A provider choice is not overridden
# ---------------------------------------------------------------------------

def test_the_repurposer_has_no_provider_bypassing_fallback():
    """
    Three call sites read "if not resp: call_gemini_api(...)". The key behind
    that call comes from the environment or a settings row, independent of the
    configured provider, so a stale Gemini key rerouted an Anthropic user's
    content to Google.
    """
    source = _read("studio", "backend", "repurposer.py")

    assert "Fallback to direct Gemini if available" not in source, (
        "the provider bypassing fallback is back"
    )
    # The helper may remain for a caller that has explicitly chosen Gemini;
    # what must not remain is a bare `if not resp` reaching for it.
    for marker in ("if not ai_out:\n        gemini_out", "if not resp:\n        api_key = get_gemini_api_key()"):
        assert marker not in source, f"a provider bypass survives: {marker!r}"


def test_a_configured_provider_is_the_only_one_consulted(monkeypatch):
    """
    With a Gemini key present in the environment and a different provider
    configured, the Gemini key must not be reached for.
    """
    import repurposer

    monkeypatch.setenv("GEMINI_API_KEY", "notarealkey_but_long_enough_to_pass")
    monkeypatch.delenv("INOX_NO_EGRESS", raising=False)

    reached = []
    monkeypatch.setattr(repurposer, "call_gemini_api",
                        lambda *a, **k: reached.append("google") or "from google")
    # A configured provider that fails, which is the case that used to fall
    # through to Google.
    monkeypatch.setattr(repurposer, "get_current_ai_config", lambda: AIProviderConfig(
        provider="anthropic", api_key="notarealkey", model="claude-x",
        base_url="http://127.0.0.1:59997/v1", status="connected",
    ))

    result = repurposer.repurpose_content("a thought worth posting")

    assert reached == [], (
        "an Anthropic user's content was sent to Google because a Gemini key "
        "was in the environment"
    )
    # repurpose_content returns a list of frameworks, so the assertion is on
    # the call never happening rather than on a returned engine label.
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# The ledger says what it does not count
# ---------------------------------------------------------------------------

def test_the_ledger_no_longer_claims_to_see_everything():
    """
    "the one point every outbound request passes through" was false, and it is
    the sentence that would make a reader trust the zero.
    """
    import re

    surface = _read("studio", "ui", "src", "components", "BrandStudioSurface.tsx")
    # Comments are stripped before searching. The note explaining why the claim
    # was removed necessarily quotes it, and a test that cannot tell a comment
    # from rendered text would fail on its own documentation.
    rendered = re.sub(r"/\*.*?\*/", "", surface, flags=re.S)
    rendered = re.sub(r"^\s*//.*$", "", rendered, flags=re.M)

    assert "the one point every outbound request passes" not in rendered, (
        "the completeness claim is back in text the creator reads"
    )
    assert "chokepoint every HTTP request" in rendered, (
        "the replacement wording is missing, so this test would pass against "
        "a sentence that says nothing at all"
    )


def test_the_ledger_names_both_paths_it_cannot_see():
    surface = _read("studio", "ui", "src", "components", "BrandStudioSurface.tsx")
    assert "not counted" in surface.lower()
    for subject in ("LinkedIn in your browser", "MCP"):
        assert subject in surface, (
            f"the interface does not tell the reader that {subject} is outside "
            f"the counter"
        )


def test_the_module_documents_its_own_gaps():
    """
    The docstring said every outbound call passes through the guard. A
    chokepoint that names its exceptions is one; a chokepoint that does not is
    a claim.
    """
    source = _read("studio", "backend", "egress.py")
    assert "What it does not cover" in source
    assert "browser_launcher" in source
    assert "mcp_client" in source


def test_the_mcp_client_still_cannot_invoke_tools():
    """
    This is what bounds the MCP gap. A source that can only answer with text
    it already holds is a much smaller exposure than one the studio can ask to
    act, and the ledger's honesty note depends on that staying true.
    """
    protocol = _read("studio", "backend", "mcp_client", "protocol.py")
    assert '_request("tools/call"' not in protocol
