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
    from ..repurposer import get_ai_status, command_ai_engine
except ImportError:
    from agno_agentos.model_gateway import (
        get_current_ai_config,
        save_ai_config,
        verify_ai_connection,
        SUPPORTED_PROVIDERS,
        AIProviderConfig,
    )
    from agno_agentos import orchestrator
    from repurposer import get_ai_status, command_ai_engine

router = APIRouter()


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

