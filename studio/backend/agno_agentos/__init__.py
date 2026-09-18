"""
Agno AgentOS Package Root
=========================
Exports the unified Agno AgentOS intelligence engine adhering to
~/agno-agentos-rulebook-kit DNA (P1/P6/P7 Structure-as-Law).
"""

from .contracts import (
    ImagePromptInput, SynthesizedImagePrompt,
    CopilotDraftInput, CopilotDraftResponse,
    LeadResearchInput, LeadResearchDossier, IcebreakerAngles,
    SwipePostAnalysisInput, SwipePostPattern
)
from .scar_tissue import scrub_em_dashes, validate_banned_vocabulary, validate_pre_fold_hook
from .registry import AGENT_REGISTRY, get_agent_spec
from .agents import (
    ImagePromptSynthesizerAgent,
    LinkedInContentCopilotAgent,
    LeadResearchAgent, IcebreakerAgent,
    SwipeFileHarvesterAgent
)
from .orchestrator import AgnoAgentOSOrchestrator, orchestrator

__all__ = [
    "ImagePromptInput",
    "SynthesizedImagePrompt",
    "CopilotDraftInput",
    "CopilotDraftResponse",
    "LeadResearchInput",
    "LeadResearchDossier",
    "IcebreakerAngles",
    "SwipePostAnalysisInput",
    "SwipePostPattern",
    "scrub_em_dashes",
    "validate_banned_vocabulary",
    "validate_pre_fold_hook",
    "AGENT_REGISTRY",
    "get_agent_spec",
    "ImagePromptSynthesizerAgent",
    "LinkedInContentCopilotAgent",
    "LeadResearchAgent",
    "IcebreakerAgent",
    "SwipeFileHarvesterAgent",
    "AgnoAgentOSOrchestrator",
    "orchestrator"
]
