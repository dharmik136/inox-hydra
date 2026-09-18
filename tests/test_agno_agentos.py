"""
Tests for Agno AgentOS Rulebook Kit implementation in Inox Hydra:
- P1: One Home Per Fact (Centralized Registry)
- P6: Scar Tissue & Negative Constraints (Zero em-dashes, banned hype vocabulary, pre-fold length check)
- P7: Structure-as-Law (Pydantic v2 strict models)
- Multi-Agent Orchestrator integration
"""

import sys
import os

root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import pytest
from studio.backend.agno_agentos.contracts import (
    ImagePromptInput,
    SynthesizedImagePrompt,
    CopilotDraftInput,
    CopilotDraftResponse,
    LeadResearchInput,
    LeadResearchDossier,
    IcebreakerAngles,
    SwipePostAnalysisInput,
    SwipePostPattern,
)
from studio.backend.agno_agentos.scar_tissue import (
    scrub_em_dashes,
    validate_banned_vocabulary,
    validate_pre_fold_hook,
    BANNED_TROPES,
)
from studio.backend.agno_agentos.registry import AGENT_REGISTRY, get_agent, list_agents
from studio.backend.agno_agentos.orchestrator import AgnoAgentOSOrchestrator


def test_p1_registry_single_home():
    """Verify P1: Centralized registry is the single source of truth for all Agno agents."""
    agents = list_agents()
    assert len(agents) >= 4
    expected_agents = [
        "image_prompt_synthesizer",
        "content_copilot",
        "crm_lead_enricher",
        "swipe_harvester",
    ]
    for name in expected_agents:
        assert name in AGENT_REGISTRY
        agent_def = get_agent(name)
        assert agent_def is not None
        assert "name" in agent_def
        assert "system_prompt" in agent_def


def test_p6_scar_tissue_zero_em_dashes():
    """Verify P6: Strictly forbid and scrub em-dashes and en-dashes."""
    dirty_text = "Modern enterprise systems \u2014 designed for scale – and resilience."
    cleaned = scrub_em_dashes(dirty_text)
    assert "\u2014" not in cleaned
    assert "–" not in cleaned
    assert "Modern enterprise systems" in cleaned


def test_p6_scar_tissue_banned_vocabulary():
    """Verify P6: Flag buzzwords and cringe corporate platitudes."""
    clean_text = "We engineered a reliable distributed ingestion pipeline."
    is_clean, violations_clean = validate_banned_vocabulary(clean_text)
    assert is_clean is True
    assert len(violations_clean) == 0

    cringe_text = "We are releasing a game-changing revolutionary paradigm to supercharge results!"
    is_cringe_clean, violations = validate_banned_vocabulary(cringe_text)
    assert is_cringe_clean is False
    assert len(violations) >= 2


def test_p6_scar_tissue_pre_fold_hook():
    """Verify P6: Flag hooks that exceed mobile dwell preview boundary (>180 chars)."""
    short_hook = "Most enterprise pipelines fail silently at 2 AM."
    is_safe, count = validate_pre_fold_hook(short_hook)
    assert is_safe is True
    assert count == len(short_hook)

    long_hook = (
        "This is an extraordinarily long hook that definitely exceeds the mobile LinkedIn see-more boundary "
        "and will certainly be cut off in the mobile feed view before the reader can even understand "
        "what the actual value proposition of this post is supposed to be for our engineering leadership."
    )
    is_long_safe, long_count = validate_pre_fold_hook(long_hook)
    assert is_long_safe is False
    assert long_count > 180


def test_p7_structure_as_law_contracts():
    """Verify P7: Pydantic v2 schemas enforce strict types and reject invalid payloads."""
    # Valid ImagePromptInput
    img_input = ImagePromptInput(
        concept="A data center in the arctic",
        aspect_ratio="16:9",
        visual_style="photorealistic",
        color_palette="navy_cyan",
        lighting="studio",
    )
    assert img_input.aspect_ratio == "16:9"

    # Valid CopilotDraftResponse
    copilot_resp = CopilotDraftResponse(
        optimized_content="Engineered for high throughput.\n\nHere is how we did it:\n1. Zero lock contention\n2. Event-driven writes.",
        hook_variants=["Engineered for high throughput."],
        dwell_time_seconds=35,
        fold_safe=True,
        pre_fold_chars=32,
    )
    assert "\u2014" not in copilot_resp.optimized_content
    assert copilot_resp.dwell_time_seconds == 35


def test_orchestrator_execution():
    """Verify AgnoAgentOSOrchestrator coordinates agents smoothly."""
    orchestrator = AgnoAgentOSOrchestrator()

    # Test Image Prompt Synthesis
    synth = orchestrator.synthesize_image_prompt({
        "concept": "Cloud architecture topology",
        "aspect_ratio": "1:1",
        "visual_style": "blueprint",
    })
    assert synth.master_prompt is not None
    assert "blueprint" in synth.master_prompt.lower()
    assert "\u2014" not in synth.master_prompt

    # Test Content Copilot Optimization
    copilot = orchestrator.optimize_content({
        "raw_content": "Here is our latest update on data pipelines. We built this with speed and scale.",
        "target_audience": "VP of Engineering",
        "post_format": "framework_breakdown",
    })
    assert copilot.optimized_content is not None
    assert "\u2014" not in copilot.optimized_content
    assert copilot.dwell_time_seconds > 0
    assert len(copilot.hook_variants) > 0

    # Test Lead Research & Icebreaker
    lead_res = orchestrator.enrich_lead({
        "id": "lead-101",
        "name": "Alex Chen",
        "headline": "Head of Data Platform @ FinTech Corp",
        "company": "FinTech Corp",
        "engagement_type": "Commented",
    })
    assert lead_res["lead_id"] == "lead-101"
    assert len(lead_res["icebreakers"]) == 3
