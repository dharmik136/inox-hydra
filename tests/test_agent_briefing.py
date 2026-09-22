"""
Tests for the agent briefing layer and the two generating agents that use it.
=============================================================================

The defect this protects against is specific and was real: configuring an AI
provider used to make image prompts worse. The model's reply replaced the whole
engineered prompt, so lighting, composition and the negative space the quote
compositor depends on were silently dropped, and nothing recorded that a model
had been involved.

Validates:
1. A brief carries the direction the old call never mentioned.
2. A model fills a slot; the scaffold survives its answer.
3. Preamble, commentary, banned tropes and forbidden subjects are refused.
4. A refused answer falls back to the deterministic baseline, never below it.
5. Hooks are held to the fold limit the product sells.
6. Provenance is recorded on both paths.
7. Strict Zero Em-Dash invariant.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from agno_agentos.briefing import Brief, provenance, strip_preamble, validate_response
from agno_agentos.contracts import CopilotDraftInput, ImagePromptInput
from agno_agentos.agents.content_copilot_agent import HOOK_FOLD_LIMIT, LinkedInContentCopilotAgent
from agno_agentos.agents.image_prompt_agent import ImagePromptSynthesizerAgent
from agno_agentos.model_gateway import AIProviderConfig

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def configured_provider():
    """A provider that looks configured, so the enhancement path is exercised."""
    return AIProviderConfig(
        provider="openai",
        api_key="sk-test-key-not-used-because-calls-are-stubbed",
        model="gpt-4o-mini",
        base_url="https://api.openai.com/v1",
        verified_at="test",
        status="connected",
    )


# ---------------------------------------------------------------------------
# The brief
# ---------------------------------------------------------------------------

def test_brief_carries_the_direction_that_was_previously_dropped():
    """
    The old image call told the model the concept, the style and the palette.
    It never mentioned lighting or aspect ratio, then discarded the prompt that
    did. A brief states all of it.
    """
    brief = Brief(
        role="You are the visual director.",
        objective="Expand the scene.",
        inputs={"scene": "a quiet room", "lighting_key": "cinematic", "aspect_ratio": "4:5"},
        constraints=["Maximum 60 words."],
        forbidden=["statue"],
        output_contract="the scene description only.",
    )
    system, user = brief.render()

    assert "visual director" in system
    assert "Maximum 60 words." in system
    assert "no preamble" in system.lower()

    assert "Lighting Key: cinematic" in user
    assert "Aspect Ratio: 4:5" in user
    assert "MUST NOT APPEAR" in user
    assert "statue" in user
    assert "OUTPUT: the scene description only." in user


def test_brief_omits_empty_inputs_rather_than_sending_blanks():
    brief = Brief(role="R", objective="O", inputs={"scene": "x", "quote": None, "author": ""})
    assert "Quote" not in brief.user_prompt()
    assert "Author" not in brief.user_prompt()


# ---------------------------------------------------------------------------
# Response validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Here is your prompt: a quiet room", "a quiet room"),
    ("Sure! A quiet room", "A quiet room"),
    ("```\na quiet room\n```", "a quiet room"),
    ('"a quiet room"', "a quiet room"),
    ("Final prompt: a quiet room", "a quiet room"),
])
def test_preamble_is_stripped(raw, expected):
    assert strip_preamble(raw) == expected


def test_commentary_is_refused_not_embedded():
    ok, _, reason = validate_response("As an AI, I cannot depict a real person in this scene.")
    assert ok is False
    assert "commentary" in reason


def test_forbidden_subject_is_refused():
    """
    A model that smuggles a bust into a frame reserved for typography must not
    reach the diffusion engine.
    """
    ok, _, reason = validate_response(
        "A marble bust of a thinker lit from one side in a bare stone room",
        forbidden_terms=["marble bust", "statue"],
    )
    assert ok is False
    assert "marble bust" in reason


def test_banned_tropes_are_refused():
    ok, _, reason = validate_response(
        "A game-changing scene that is a testament to modern design and architecture"
    )
    assert ok is False
    assert "banned tropes" in reason


def test_a_clean_response_is_accepted_and_scrubbed():
    ok, cleaned, reason = validate_response(
        "A bare concrete room " + chr(8212) + " one shaft of light across the floor"
    )
    assert ok is True
    assert reason == "accepted"
    assert chr(8212) not in cleaned


# ---------------------------------------------------------------------------
# Image agent
# ---------------------------------------------------------------------------

def test_scaffold_survives_a_model_answer(monkeypatch):
    """
    The regression that started this. A model reply must enrich the scene and
    leave lighting, palette and the reserved negative space intact.
    """
    monkeypatch.setattr(
        "agno_agentos.agents.image_prompt_agent.execute_llm_completion",
        lambda *a, **k: "A bare concrete gallery with a single shaft of morning light crossing the floor",
    )
    agent = ImagePromptSynthesizerAgent(ai_config=configured_provider())
    result = agent.synthesize(ImagePromptInput(
        concept="Socrates quote about wisdom in a quiet room",
        aspect_ratio="4:5",
        visual_style="minimalist_sketch",
        color_palette="obsidian_monochrome",
        lighting="cinematic",
    ))

    prompt = result.master_prompt
    assert "bare concrete gallery" in prompt, "the model's scene should be used"
    assert "Lighting:" in prompt and "cinematic" in prompt.lower(), "lighting must survive"
    assert "obsidian" in prompt.lower() or "monochrome" in prompt.lower(), "palette must survive"
    assert "negative space" in prompt.lower(), "the quote reservation must survive"
    assert result.technical_parameters["prompt_provenance"]["source"] == "model_assisted"


def test_a_rejected_model_answer_leaves_the_deterministic_prompt_standing(monkeypatch):
    """A bad response costs one call. It must not cost the prompt."""
    monkeypatch.setattr(
        "agno_agentos.agents.image_prompt_agent.execute_llm_completion",
        lambda *a, **k: "A marble bust of Socrates on a plinth, face lit from the side",
    )
    agent = ImagePromptSynthesizerAgent(ai_config=configured_provider())
    result = agent.synthesize(ImagePromptInput(
        concept="Socrates quote about wisdom in a quiet room",
        visual_style="minimalist_sketch",
    ))

    assert "marble bust" not in result.master_prompt.lower()
    assert "negative space" in result.master_prompt.lower()
    assert result.technical_parameters["prompt_provenance"]["source"] == "deterministic"
    assert "rejected" in result.technical_parameters["prompt_provenance"]["reason"]


def test_a_provider_error_does_not_break_generation(monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("agno_agentos.agents.image_prompt_agent.execute_llm_completion", explode)
    agent = ImagePromptSynthesizerAgent(ai_config=configured_provider())
    result = agent.synthesize(ImagePromptInput(concept="event driven architecture"))

    assert len(result.master_prompt) > 40
    assert result.technical_parameters["prompt_provenance"]["source"] == "deterministic"
    assert "provider error" in result.technical_parameters["prompt_provenance"]["reason"]


def test_model_is_briefed_with_lighting_and_aspect_ratio(monkeypatch):
    """The two facts the old call never sent."""
    seen = {}

    def capture(config, prompt, system_prompt=None, **kwargs):
        seen["user"] = prompt
        seen["system"] = system_prompt
        return "A long hall of glass and concrete receding into shadow"

    monkeypatch.setattr("agno_agentos.agents.image_prompt_agent.execute_llm_completion", capture)
    agent = ImagePromptSynthesizerAgent(ai_config=configured_provider())
    agent.synthesize(ImagePromptInput(
        concept="distributed systems", aspect_ratio="16:9", lighting="golden_hour"
    ))

    assert "golden_hour" in seen["user"]
    assert "16:9" in seen["user"]
    assert "visual director" in seen["system"].lower()


def test_deterministic_path_is_unchanged_without_a_provider():
    agent = ImagePromptSynthesizerAgent(ai_config=AIProviderConfig(
        provider="local_deterministic", api_key="", model="local",
        base_url="", verified_at="", status="active",
    ))
    result = agent.synthesize(ImagePromptInput(concept="event driven architecture"))
    assert len(result.master_prompt) > 40
    assert result.technical_parameters["prompt_provenance"]["source"] == "deterministic"


# ---------------------------------------------------------------------------
# Content agent
# ---------------------------------------------------------------------------

def test_hooks_that_break_the_fold_are_refused(monkeypatch):
    """
    The product's central claim is that a hook does not truncate on mobile. A
    model is not exempt from it.
    """
    long_hook = "1. " + ("This hook runs on well past the point LinkedIn stops showing it " * 4)
    monkeypatch.setattr(
        "agno_agentos.agents.content_copilot_agent.execute_llm_completion",
        lambda *a, **k: "\n".join([long_hook, long_hook, long_hook]),
    )
    agent = LinkedInContentCopilotAgent(ai_config=configured_provider())
    result = agent.optimize(CopilotDraftInput(
        raw_content="A long enough draft about platform reliability to trigger the enhancement path."
    ))

    assert all(len(h) <= HOOK_FOLD_LIMIT for h in result.hook_variants)
    assert result.hook_provenance["source"] == "deterministic"


def test_accepted_hooks_lead_and_templates_backfill(monkeypatch):
    """The count must never drop below the deterministic baseline."""
    monkeypatch.setattr(
        "agno_agentos.agents.content_copilot_agent.execute_llm_completion",
        lambda *a, **k: (
            "1. Your platform is not slow, your retries are.\n"
            "2. We deleted 40 percent of our alerts and got faster.\n"
            "3. Nobody is paged at 3am by a system that was designed.\n"
        ),
    )
    agent = LinkedInContentCopilotAgent(ai_config=configured_provider())
    result = agent.optimize(CopilotDraftInput(
        raw_content="A long enough draft about platform reliability to trigger the enhancement path."
    ))

    assert result.hook_variants[0] == "Your platform is not slow, your retries are."
    assert len(result.hook_variants) >= 7, "templates should backfill behind the model hooks"
    assert all(len(h) <= HOOK_FOLD_LIMIT for h in result.hook_variants[:3])
    assert result.hook_provenance["source"] == "model_assisted"


def test_audience_and_format_reach_the_model(monkeypatch):
    """Both sit in the input contract and were previously discarded."""
    seen = {}

    def capture(config, prompt, system_prompt=None, **kwargs):
        seen["user"] = prompt
        return "1. A short hook that fits.\n2. Another short hook.\n3. A third short hook."

    monkeypatch.setattr("agno_agentos.agents.content_copilot_agent.execute_llm_completion", capture)
    agent = LinkedInContentCopilotAgent(ai_config=configured_provider())
    agent.optimize(CopilotDraftInput(
        raw_content="A long enough draft about platform reliability to trigger the enhancement path.",
        target_audience="Founders and CTOs",
        post_format="hard_lesson",
    ))

    assert "Founders and CTOs" in seen["user"]
    assert "hard_lesson" in seen["user"]


def test_banned_vocabulary_never_reaches_the_hook_list(monkeypatch):
    monkeypatch.setattr(
        "agno_agentos.agents.content_copilot_agent.execute_llm_completion",
        lambda *a, **k: (
            "1. This game-changing approach will transform your stack.\n"
            "2. A revolutionary way to think about uptime.\n"
            "3. In today's fast-paced world, latency is everything.\n"
        ),
    )
    agent = LinkedInContentCopilotAgent(ai_config=configured_provider())
    result = agent.optimize(CopilotDraftInput(
        raw_content="A long enough draft about platform reliability to trigger the enhancement path."
    ))

    joined = " ".join(result.hook_variants).lower()
    assert "game-changing" not in joined
    assert "revolutionary" not in joined
    assert result.hook_provenance["source"] == "deterministic"


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------

def test_provenance_shape_is_stable():
    p = provenance("model_assisted", "accepted", "gpt-4o-mini")
    assert set(p.keys()) == {"source", "reason", "model"}


def test_briefing_layer_holds_the_zero_em_dash_invariant():
    targets = [
        os.path.join(REPO_ROOT, "studio", "backend", "agno_agentos", "briefing.py"),
        os.path.join(REPO_ROOT, "studio", "backend", "agno_agentos", "agents", "image_prompt_agent.py"),
        os.path.join(REPO_ROOT, "studio", "backend", "agno_agentos", "agents", "content_copilot_agent.py"),
    ]
    for path in targets:
        content = open(path, encoding="utf-8").read()
        # Never typed literally, or this file would break the rule it enforces.
        assert chr(8212) not in content, f"{os.path.basename(path)} contains an em-dash"
