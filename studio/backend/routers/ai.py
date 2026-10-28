"""
Bring-Your-Own-AI (BYO-AI) and Content Copilot Router.
======================================================
Handles AI provider configurations (Gemini, OpenAI, Anthropic, Groq, Ollama),
AI commands, hook transformations, Content Copilot optimization, and token streaming.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
- 100% local-first, zero cloud egress when local deterministic engine is active.
"""

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    from ..agno_agentos.model_gateway import (
        get_current_ai_config,
        save_ai_config,
        verify_ai_connection,
        SUPPORTED_PROVIDERS,
        AIProviderConfig,
    )
    from ..agno_agentos import orchestrator
    from ..agno_agentos.scar_tissue import BANNED_TROPES
    from ..repurposer import get_ai_status, command_ai_engine
    from .. import voice_pack, writing
    from ..mcp_client import servers as mcp_servers
except ImportError:
    from agno_agentos.model_gateway import (
        get_current_ai_config,
        save_ai_config,
        verify_ai_connection,
        SUPPORTED_PROVIDERS,
        AIProviderConfig,
    )
    from agno_agentos import orchestrator
    from agno_agentos.scar_tissue import BANNED_TROPES
    from repurposer import get_ai_status, command_ai_engine
    import voice_pack
    import writing
    from mcp_client import servers as mcp_servers

router = APIRouter()


@router.get("/api/v1/composer/told", tags=["AI"])
def get_what_the_model_is_told() -> Dict[str, Any]:
    """
    What a writing request from the Composer carries beyond the words you
    give it, each part read from the code that builds the request (sections
    report, batch 8): the voice pack as appended, the phrases the studio will
    not let a model write and where that is checked, whether any request
    carries your grounding sources, and how an image prompt is made.
    """
    config = get_current_ai_config()
    sources = mcp_servers.list_servers()
    return {
        "status": "success",
        "provider": {"configured": bool(config.is_configured), "provider": config.provider if config.is_configured else None,
                     "model": config.model if config.is_configured else None},
        "voice": voice_pack.told(),
        # The things to remember the creator allows, and every request they go with (phase 3).
        "remembered": writing.memory_told(),
        "scar_tissue": {
            "phrases": list(BANNED_TROPES),
            # A model's image description is refused when it holds one, and
            # the studio writes the scene itself instead (briefing.validate_response).
            "checked_on": ["image prompts"],
            # Command's instruction names these, the creator's words to avoid
            # (writing.py, phase 3), as Re-Hook's now does; neither answer is
            # checked against the list.
            "named_in_command": list(writing.preferences()["avoid"]),
        },
        "grounding": {
            "sources": len(sources),
            "sources_on": sum(1 for source in sources if source.get("enabled")),
            # Only the studio's copilot gathers grounding material, and no
            # screen calls it: Re-Hook, Command and image prompts carry none.
            "sent_with": [],
        },
        "images": {
            "model_writes": "the scene description" if config.is_configured else None,
            "studio_adds": ["style", "palette", "lighting", "composition", "the space a quote needs"],
            "refused_when": "the description holds one of the phrases above, explains itself, or is too short or long",
        },
    }


class CopilotRequest(BaseModel):
    raw_content: str
    # No default: an audience nobody gave is not told to the model (F2-N2).
    target_audience: Optional[str] = None
    post_format: Optional[str] = "framework_breakdown"
    attached_media_type: Optional[str] = None


class AIConfigureRequest(BaseModel):
    provider: str
    api_key: Optional[str] = ""
    model: Optional[str] = None
    base_url: Optional[str] = None


class AICommandPayload(BaseModel):
    command: str
    context: Optional[str] = None
    draft_context: Optional[str] = None

    def resolved_context(self) -> Optional[str]:
        return self.context if self.context is not None else self.draft_context


@router.get("/api/ai/status", tags=["AI Command Engine"])
def ai_status():
    """Returns the current operational status of the local and remote AI providers."""
    return get_ai_status()


@router.get("/api/ai/config", tags=["AI Command Engine"])
def get_ai_config_endpoint():
    """Returns active Bring-Your-Own-AI provider, verified model, and available providers."""
    cfg = get_current_ai_config()
    return {
        "status": "success",
        "config": cfg.to_dict(),
        "supported_providers": SUPPORTED_PROVIDERS,
    }


@router.post("/api/ai/configure", tags=["AI Command Engine"])
def configure_ai_endpoint(req: AIConfigureRequest):
    """
    Validates connection to the selected AI provider (Gemini, OpenAI, Claude, Groq, Ollama)
    via live ping. If verified, updates local SQLite configuration.
    If invalid, rejects configuration with 400 Bad Request and preserves existing settings.
    """
    success, message, latency_ms = verify_ai_connection(
        provider=req.provider,
        api_key=req.api_key or "",
        model=req.model,
        base_url=req.base_url,
    )

    if not success:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "AI Provider Verification Failed",
                "message": message,
                "latency_ms": latency_ms,
            },
        )

    saved_cfg = save_ai_config(
        provider=req.provider,
        api_key=req.api_key or "",
        model=req.model,
        base_url=req.base_url,
    )

    return {
        "status": "success",
        "message": message,
        "latency_ms": latency_ms,
        "config": saved_cfg.to_dict(),
    }


@router.post("/api/ai/command", tags=["AI Command Engine"])
def execute_ai_command(payload: AICommandPayload):
    """Executes high-velocity content commands, tone shifts, and hook transformations."""
    return command_ai_engine(payload.command, payload.resolved_context())


@router.post("/api/copilot/optimize", tags=["AI Content Copilot"])
def copilot_optimize(req: CopilotRequest):
    """Agno Content Copilot post drafting, line formatting, and viral hook formulation."""
    result = orchestrator.optimize_content(req.model_dump())
    return {"status": "success", "copilot": result.model_dump()}

