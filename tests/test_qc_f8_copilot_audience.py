"""
Quality cycle 2026-10, batch F8 [F2-N2]: the copilot does not tell the model
who the creator's audience is when nobody said.

Every default named "Engineering & Product Leaders", so a bakery owner's hooks
were briefed for engineering leaders. Brand Studio has no audience field, so
the brief carries an audience only when the caller gives one.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from agno_agentos.agents.content_copilot_agent import LinkedInContentCopilotAgent  # noqa: E402
from agno_agentos.contracts import CopilotDraftInput  # noqa: E402
from agno_agentos.model_gateway import AIProviderConfig  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DRAFT = "A long enough draft about the sourdough we bake every morning before the shop opens."


def _provider():
    return AIProviderConfig(
        provider="openai",
        api_key="sk-notarealkey-calls-are-stubbed-000000",
        model="gpt-4o-mini",
        base_url="https://api.openai.com/v1",
        verified_at="test",
        status="connected",
    )


def _brief_for(monkeypatch, **fields):
    seen = {}

    def capture(config, prompt, system_prompt=None, **kwargs):
        seen["user"] = prompt
        return "1. A short hook that fits.\n2. Another short hook.\n3. A third short hook."

    monkeypatch.setattr("agno_agentos.agents.content_copilot_agent.execute_llm_completion", capture)
    LinkedInContentCopilotAgent(ai_config=_provider()).optimize(CopilotDraftInput(raw_content=DRAFT, **fields))
    return seen["user"]


def test_no_audience_is_invented_when_none_is_given(monkeypatch):
    prompt = _brief_for(monkeypatch)
    assert "Engineering" not in prompt, "the model is told the audience is engineering leaders"
    assert "Audience:" not in prompt, "the brief names an audience nobody gave"


def test_an_audience_the_caller_gives_still_reaches_the_model(monkeypatch):
    prompt = _brief_for(monkeypatch, target_audience="Neighbourhood bakery regulars")
    assert "Audience: Neighbourhood bakery regulars" in prompt


def test_a_null_audience_is_accepted_and_omitted(monkeypatch):
    prompt = _brief_for(monkeypatch, target_audience=None)
    assert "Audience:" not in prompt


def test_no_request_model_defaults_to_another_creators_audience():
    for rel in ("studio/backend/app.py", "studio/backend/routers/ai.py",
                "studio/backend/agno_agentos/contracts.py",
                "studio/backend/agno_agentos/agents/content_copilot_agent.py"):
        with open(os.path.join(REPO_ROOT, rel), encoding="utf-8") as handle:
            assert "Engineering & Product Leaders" not in handle.read(), rel


def test_the_endpoint_request_without_an_audience_briefs_none(monkeypatch):
    """What /api/copilot/optimize hands the agent when the caller sends only the draft."""
    from routers.ai import CopilotRequest
    from app import CopilotRequest as AppCopilotRequest

    for model in (CopilotRequest, AppCopilotRequest):
        payload = model(raw_content=DRAFT).model_dump()
        prompt = _brief_for(monkeypatch, **{k: v for k, v in payload.items() if k != "raw_content"})
        assert "Audience:" not in prompt, model.__module__
