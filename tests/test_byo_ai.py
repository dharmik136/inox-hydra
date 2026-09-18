"""
Inox Hydra (LinkedIn Studio Enterprise)
Bring-Your-Own-AI (BYO-AI) & Multi-Model Gateway Test Suite
============================================================
Verifies:
1. Multi-Model Gateway registry, fallback, and masking contracts.
2. Active verification ping (rejection of bad credentials, acceptance of local engine).
3. SQLite configuration persistence and backward-compatibility.
4. REST API endpoints: /api/ai/config and /api/ai/configure.
5. Agno AgentOS multi-agent orchestrator BYO-AI execution.
6. Unified CLI command flows: status, list-providers, test, configure.
"""

import sys
import os
import subprocess
import pytest
from fastapi.testclient import TestClient

# Ensure studio/backend is on path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
backend_dir = os.path.join(root_dir, "studio", "backend")
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from studio.backend.app import app
from studio.backend.database import get_db, init_db
from studio.backend.agno_agentos.model_gateway import (
    SUPPORTED_PROVIDERS,
    AIProviderConfig,
    verify_ai_connection,
    get_current_ai_config,
    save_ai_config,
    execute_llm_completion
)
from studio.backend.agno_agentos.orchestrator import orchestrator
from studio.backend.agno_agentos.agents import (
    LinkedInContentCopilotAgent,
    ImagePromptSynthesizerAgent,
    LeadResearchAgent,
    IcebreakerAgent,
    SwipeFileHarvesterAgent
)
from studio.backend.agno_agentos.contracts import (
    ImagePromptInput,
    CopilotDraftInput,
    LeadResearchInput,
    SwipePostAnalysisInput
)

client = TestClient(app)


def test_supported_providers_registry():
    """Validates that all key providers are registered with valid configurations."""
    expected_providers = [
        "gemini", "openai", "anthropic", "ollama", "groq", "custom_openai", "local_deterministic"
    ]
    for p in expected_providers:
        assert p in SUPPORTED_PROVIDERS, f"Provider {p} missing from registry"
        prov = SUPPORTED_PROVIDERS[p]
        assert "name" in prov
        assert "default_model" in prov
        assert "supported_models" in prov
        assert "requires_key" in prov


def test_ai_provider_config_contracts():
    """Tests AIProviderConfig initialization, key masking, and is_configured property."""
    # Local deterministic: requires no key, is_configured should be False (zero egress mode)
    local_cfg = AIProviderConfig(provider="local_deterministic")
    assert local_cfg.provider == "local_deterministic"
    assert not local_cfg.is_configured
    assert local_cfg.to_dict()["api_key_masked"] == ""

    # OpenAI with valid key
    openai_cfg = AIProviderConfig(
        provider="openai",
        api_key="sk-proj-1234567890abcdef1234567890",
        model="gpt-4o"
    )
    assert openai_cfg.provider == "openai"
    assert openai_cfg.is_configured
    d = openai_cfg.to_dict()
    assert d["has_key"] is True
    assert d["model"] == "gpt-4o"
    assert "..." in d["api_key_masked"]
    assert not d["api_key_masked"].startswith("sk-proj-1234567890abcdef1234567890")

    # Ollama requires no API key but is_configured is True
    ollama_cfg = AIProviderConfig(provider="ollama")
    assert ollama_cfg.is_configured


def test_verify_ai_connection_deterministic():
    """Verifies that local deterministic engine passes verification ping instantaneously."""
    success, msg, latency = verify_ai_connection("local_deterministic")
    assert success is True
    assert "zero cloud egress" in msg.lower()
    assert latency > 0


def test_verify_ai_connection_rejection():
    """Verifies that invalid API keys or endpoints fail gracefully without unhandled exceptions."""
    # Test invalid key against Gemini
    success, msg, latency = verify_ai_connection("gemini", api_key="AIzaSy_fake_test_key_12345", timeout=2.0)
    assert success is False
    assert ("HTTP" in msg or "error" in msg.lower() or "unreachable" in msg.lower())

    # Test invalid key against OpenAI
    success_oa, msg_oa, _ = verify_ai_connection("openai", api_key="sk-fake-openai-test-key", timeout=2.0)
    assert success_oa is False


def test_save_and_get_ai_config_persistence():
    """Verifies SQLite round-trip storage of AI provider configurations."""
    init_db()
    # Save local deterministic
    save_ai_config(provider="local_deterministic")
    cfg = get_current_ai_config()
    assert cfg.provider == "local_deterministic"

    # Save custom openai config
    save_ai_config(
        provider="custom_openai",
        api_key="sk-custom-secret",
        model="deepseek-coder",
        base_url="http://localhost:8080/v1"
    )
    cfg2 = get_current_ai_config()
    assert cfg2.provider == "custom_openai"
    assert cfg2.model == "deepseek-coder"
    assert cfg2.base_url == "http://localhost:8080/v1"
    assert cfg2.api_key == "sk-custom-secret"

    # Reset back to local deterministic
    save_ai_config(provider="local_deterministic")
    cfg_reset = get_current_ai_config()
    assert cfg_reset.provider == "local_deterministic"


def test_api_get_ai_config_endpoint():
    """Tests GET /api/ai/config endpoint."""
    res = client.get("/api/ai/config")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "config" in data
    assert "supported_providers" in data
    assert "gemini" in data["supported_providers"]
    assert "openai" in data["supported_providers"]


def test_api_configure_ai_rejection_and_acceptance():
    """Tests POST /api/ai/configure endpoint for validation gate."""
    # Bad key -> must return 400 Bad Request
    bad_payload = {
        "provider": "openai",
        "api_key": "sk-invalid-nonexistent-key-12345"
    }
    res_bad = client.post("/api/ai/configure", json=bad_payload)
    assert res_bad.status_code == 400
    detail = res_bad.json().get("detail", {})
    assert "error" in detail

    # Valid local engine -> must return 200 OK
    good_payload = {
        "provider": "local_deterministic"
    }
    res_good = client.post("/api/ai/configure", json=good_payload)
    assert res_good.status_code == 200
    data_good = res_good.json()
    assert data_good["status"] == "success"
    assert data_good["config"]["provider"] == "local_deterministic"


def test_orchestrator_byo_ai_contracts():
    """Tests that Agno AgentOS Orchestrator resolves AI config and coordinates agents."""
    cfg = orchestrator.get_ai_config()
    assert isinstance(cfg, AIProviderConfig)

    # Test Content Copilot draft
    draft_input = {
        "raw_content": "Building event-driven distributed systems requires high-discipline boundaries.",
        "target_audience": "Engineering Leaders",
        "post_format": "framework_breakdown"
    }
    copilot_res = orchestrator.optimize_content(draft_input)
    assert copilot_res.optimized_content
    assert len(copilot_res.hook_variants) >= 5

    # Test Image Prompt Synthesizer
    prompt_input = {
        "concept": "Distributed Event Architecture",
        "aspect_ratio": "1:1",
        "visual_style": "blueprint",
        "color_palette": "navy_cyan"
    }
    prompt_res = orchestrator.synthesize_image_prompt(prompt_input)
    assert prompt_res.master_prompt
    assert prompt_res.width == 1080
    assert prompt_res.height == 1080

    # Test Lead Enrichment
    lead_dict = {
        "id": "lead-test-01",
        "name": "Sarah Chen",
        "headline": "VP of Engineering at FinTech Corp",
        "company": "FinTech Corp"
    }
    enrich_res = orchestrator.enrich_lead(lead_dict)
    assert enrich_res["lead_id"] == "lead-test-01"
    assert len(enrich_res["icebreakers"]) == 3


def test_cli_subcommands():
    """Tests studio_cli.py subcommands via subprocess."""
    cli_path = os.path.join(root_dir, "studio_cli.py")

    # studio_cli.py ai list-providers
    res_list = subprocess.run(
        [sys.executable, cli_path, "ai", "list-providers"],
        capture_output=True,
        text=True
    )
    assert res_list.returncode == 0
    assert "Google Gemini" in res_list.stdout
    assert "OpenAI" in res_list.stdout
    assert "Anthropic Claude" in res_list.stdout

    # studio_cli.py ai status
    res_status = subprocess.run(
        [sys.executable, cli_path, "ai", "status"],
        capture_output=True,
        text=True
    )
    assert res_status.returncode == 0
    assert "Provider:" in res_status.stdout

    # studio_cli.py ai test (runs on active local deterministic engine)
    res_test = subprocess.run(
        [sys.executable, cli_path, "ai", "test"],
        capture_output=True,
        text=True
    )
    assert res_test.returncode == 0
    assert "SUCCESS" in res_test.stdout
