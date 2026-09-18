"""
Agno AgentOS Multi-Agent Orchestrator
=====================================
Coordinates execution across Agno agents with dual-mode intelligence:
- Local deterministic intelligence engine by default (100% zero-egress).
- Upgrades dynamically to configured Bring-Your-Own-AI (BYO-AI) provider (OpenAI, Gemini, Claude, Ollama, Groq).
"""

import os
import sqlite3
from typing import Dict, Any, Optional

try:
    from ..database import get_db
except ImportError:
    try:
        from database import get_db
    except ImportError:
        get_db = None

from .contracts import (
    ImagePromptInput, SynthesizedImagePrompt,
    CopilotDraftInput, CopilotDraftResponse,
    LeadResearchInput, LeadResearchDossier, IcebreakerAngles,
    SwipePostAnalysisInput, SwipePostPattern
)
from .agents import (
    ImagePromptSynthesizerAgent,
    LinkedInContentCopilotAgent,
    LeadResearchAgent, IcebreakerAgent,
    SwipeFileHarvesterAgent
)
from .model_gateway import get_current_ai_config, AIProviderConfig, execute_llm_completion


class AgnoAgentOSOrchestrator:
    """
    Master orchestrator for all Agno AgentOS intelligence operations.
    Supports Bring-Your-Own-AI (BYO-AI) across OpenAI, Gemini, Claude, Groq, Ollama,
    and local zero-egress deterministic fallback.
    """

    def __init__(self):
        self._cached_config: Optional[AIProviderConfig] = None

    def get_ai_config(self) -> AIProviderConfig:
        """Resolves active verified AI configuration from local SQLite vault or environment."""
        return get_current_ai_config()

    def get_gemini_api_key(self) -> Optional[str]:
        """Resolves Gemini API key for backward compatibility."""
        cfg = self.get_ai_config()
        if cfg.provider == "gemini" and cfg.api_key:
            return cfg.api_key
        return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    def synthesize_image_prompt(self, payload: Dict[str, Any]) -> SynthesizedImagePrompt:
        """Synthesizes structured generative image prompt from creator options."""
        ai_config = self.get_ai_config()
        prompt_input = ImagePromptInput(**payload)
        agent = ImagePromptSynthesizerAgent(ai_config=ai_config)
        return agent.synthesize(prompt_input)

    def optimize_content(self, payload: Dict[str, Any]) -> CopilotDraftResponse:
        """Drafts and optimizes LinkedIn post content with mobile dwell telemetry."""
        ai_config = self.get_ai_config()
        draft_input = CopilotDraftInput(**payload)
        agent = LinkedInContentCopilotAgent(ai_config=ai_config)
        return agent.optimize(draft_input)

    def enrich_lead(self, lead_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Performs deep enterprise research and generates icebreaker angles for a prospect."""
        ai_config = self.get_ai_config()
        lead_input = LeadResearchInput(
            lead_id=str(lead_dict.get("id") or lead_dict.get("lead_id") or "lead-unknown"),
            name=lead_dict.get("name", "Prospect"),
            headline=lead_dict.get("headline", ""),
            company=lead_dict.get("company", "Enterprise Organization"),
            profile_url=lead_dict.get("profile_url", ""),
            engagement_type=lead_dict.get("engagement_type", "Commented"),
            post_id=lead_dict.get("post_id", ""),
            notes=lead_dict.get("notes", "")
        )
        research_agent = LeadResearchAgent()
        icebreaker_agent = IcebreakerAgent(ai_config=ai_config)

        dossier = research_agent.research(lead_input)
        angles = icebreaker_agent.generate_angles(lead_input, dossier)

        provider_label = f"{ai_config.provider}_{ai_config.model}" if ai_config.is_configured else "agno_local"

        return {
            "lead_id": dossier.lead_id,
            "role_category": dossier.role_category,
            "company_intelligence": dossier.company_intelligence,
            "estimated_tech_stack": dossier.estimated_tech_stack,
            "key_topics": dossier.key_topics,
            "friction_points": dossier.friction_points,
            "icebreakers": [
                {"style": "value_add", "label": "Technical Architecture", "text": angles.angle_technical},
                {"style": "resource_share", "label": "Resource Blueprint", "text": angles.angle_resource},
                {"style": "quick_chat", "label": "Quick Coffee Chat", "text": angles.angle_conversational}
            ],
            "enriched_by": provider_label
        }

    def analyze_swipe(self, swipe_dict: Dict[str, Any]) -> SwipePostPattern:
        """Reverse-engineers viral post into structural blueprint."""
        ai_config = self.get_ai_config()
        swipe_input = SwipePostAnalysisInput(
            post_id=str(swipe_dict.get("id") or "swipe-unknown"),
            author_name=swipe_dict.get("author_name", "Author"),
            content=swipe_dict.get("content", ""),
            topic=swipe_dict.get("topic", "General")
        )
        agent = SwipeFileHarvesterAgent(ai_config=ai_config)
        return agent.harvest_pattern(swipe_input)


# Singleton orchestrator instance
orchestrator = AgnoAgentOSOrchestrator()
