"""
SwipeFileHarvesterAgent (Agno AgentOS Pattern Analyzer)
=======================================================
Dissects viral LinkedIn posts into core psychological formulas, tension points,
and reusable templates. Adheres to P1/P6/P7.
"""

import os
import re
from typing import List, Optional
import requests

from ..contracts import SwipePostAnalysisInput, SwipePostPattern
from ..scar_tissue import scrub_em_dashes
from ..model_gateway import get_current_ai_config, AIProviderConfig


class SwipeFileHarvesterAgent:
    """Agent for viral swipe file pattern extraction and architectural templating."""

    def __init__(self, ai_config: Optional[AIProviderConfig] = None, gemini_api_key: Optional[str] = None):
        if ai_config:
            self.ai_config = ai_config
        elif gemini_api_key:
            self.ai_config = AIProviderConfig(
                provider="gemini",
                api_key=gemini_api_key,
                model="gemini-2.5-flash",
                base_url="https://generativelanguage.googleapis.com/v1beta",
                verified_at="manual",
                status="connected"
            )
        else:
            self.ai_config = get_current_ai_config()
        self.gemini_api_key = self.ai_config.api_key if self.ai_config.provider == "gemini" else None

    def harvest_pattern(self, swipe_input: SwipePostAnalysisInput) -> SwipePostPattern:
        """Analyzes a viral post and returns structured SwipePostPattern."""
        content = scrub_em_dashes(swipe_input.content.strip())
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        first_line = lines[0] if lines else "Viral Post Hook"

        # Detect hook archetype
        fl_lower = first_line.lower()
        if any(w in fl_lower for w in ["mistake", "wrong", "stop", "never", "don't", "fail"]):
            archetype = "Contrarian Warning"
            tension = "Conventional industry dogma vs operational failure reality."
        elif any(w in fl_lower for w in ["years", "taught me", "lessons", "learned"]):
            archetype = "Longitudinal Authority"
            tension = "Theoretical best practices vs hard-won battle scars."
        elif any(w in fl_lower for w in ["how to", "step", "framework", "blueprint"]):
            archetype = "Actionable Blueprint"
            tension = "Complexity and overwhelm vs reproducible step-by-step clarity."
        elif any(w in fl_lower for w in ["%", "$", "10x", "million", "revenue"]):
            archetype = "Quantitative Proof"
            tension = "Vague promises vs verified benchmark metrics."
        else:
            archetype = "Curiosity Gap"
            tension = "Surface symptoms vs root cause architecture."

        blueprint = (
            "1. Hook: Disrupt scroll with strong contrarian assertion or metric.\n"
            "2. Tension: Explain why standard industry playbook fails under pressure.\n"
            "3. Body: Break down the 3 systemic pillars that resolve the tension.\n"
            "4. Takeaway: One actionable insight the reader can implement immediately.\n"
            "5. CTA: Open-ended question prompting peer practitioner discussion."
        )

        template = (
            f"{first_line}\n\n"
            f"Here is why most teams get [TOPIC] wrong:\n\n"
            f"1. [COMMON PITFALL A]\n"
            f"They focus on [SURFACE METRIC] instead of [UNDERLYING ARCHITECTURE].\n\n"
            f"2. [COMMON PITFALL B]\n"
            f"They add [MORE TOOLS] instead of establishing [CLEAN BOUNDARIES].\n\n"
            f"The fix is simple, but requires discipline:\n"
            f"-> [PILLAR 1]\n"
            f"-> [PILLAR 2]\n\n"
            f"What is your team's stance on [TOPIC]?"
        )

        takeaways = [
            "Open with a high-contrast tension line before the 180-char fold.",
            "Use line breaks to maintain reading momentum on mobile screens.",
            "End with a practitioner question rather than generic self-promotion."
        ]

        return SwipePostPattern(
            post_id=swipe_input.post_id,
            hook_archetype=archetype,
            tension_point=tension,
            structural_blueprint=blueprint,
            reusable_template=template,
            key_takeaways=takeaways
        )
