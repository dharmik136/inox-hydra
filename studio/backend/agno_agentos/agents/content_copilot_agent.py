"""
LinkedInContentCopilotAgent (Agno AgentOS Post Strategist)
===========================================================
Structures raw ideas into viral, high-dwell LinkedIn posts with scroll-stopping hooks.
Enforces P6 Anti-Pattern Memory: strict zero em-dashes, fold-safe hooks, media callouts.
"""

import os
import re
from typing import List, Optional
import requests

from ..contracts import CopilotDraftInput, CopilotDraftResponse
from ..scar_tissue import scrub_em_dashes, validate_pre_fold_hook
from ..model_gateway import get_current_ai_config, execute_llm_completion, AIProviderConfig


def to_sans_bold(text: str) -> str:
    """Converts standard ASCII characters to mathematical sans-bold characters for LinkedIn."""
    normal = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    bold = "𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
    trans = str.maketrans(normal, bold)
    return text.translate(trans)


class LinkedInContentCopilotAgent:
    """Agent for LinkedIn post optimization, hook generation, and dwell optimization."""

    HOOK_TEMPLATES = [
        "Most teams fail at {topic} because they optimize for the wrong metric.",
        "Here is what 10 years in enterprise architecture taught me about {topic}:",
        "The uncomfortable truth about {topic} nobody wants to say out loud:",
        "Stop treating {topic} like a tooling problem. It is a systems problem.",
        "3 counter-intuitive lessons on {topic} that saved our team hundreds of hours:",
        "How to scale {topic} without breaking production (and without burning out your team):",
        "If your {topic} architecture requires 24/7 fire-drills, it is already broken."
    ]

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

    def optimize(self, draft_input: CopilotDraftInput) -> CopilotDraftResponse:
        """
        Processes draft input and returns structured CopilotDraftResponse.
        Enforces zero em-dashes and provides media-specific callouts.
        """
        raw = scrub_em_dashes(draft_input.raw_content.strip())
        media_type = draft_input.attached_media_type

        # Extract topic from first line
        first_line = raw.split("\n")[0].strip()
        topic = re.sub(r'[^a-zA-Z0-9 ]', '', first_line)[:40].strip() or "engineering systems"

        # Generate 5-7 hooks
        hook_variants = [
            scrub_em_dashes(tmpl.format(topic=topic))
            for tmpl in self.HOOK_TEMPLATES
        ]

        # Structure post content with clean paragraphs and line spacing
        paragraphs = [p.strip() for p in raw.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [raw]

        # Check fold safety of hook
        opening_hook = paragraphs[0] if paragraphs else ""
        fold_safe, pre_fold_chars = validate_pre_fold_hook(opening_hook, max_chars=180)

        # Contextual media callout based on media type
        media_callout = None
        if media_type == "carousel":
            media_callout = "📌 Swipe through the multi-slide breakdown below ➡️"
        elif media_type == "video":
            media_callout = "▶️ Watch the 45-second walkthrough below 🎬"
        elif media_type == "image":
            media_callout = "📊 Architecture schematic attached below 👇"

        # Assemble optimized post
        optimized_body = "\n\n".join(paragraphs)
        if media_callout and media_callout not in optimized_body:
            optimized_body += f"\n\n{media_callout}"

        # Estimate reading dwell time (average 200 words per minute)
        word_count = len(optimized_body.split())
        dwell_seconds = max(15, int((word_count / 200) * 60))

        # Attempt LLM enhancement if configured
        if self.ai_config and self.ai_config.is_configured and len(raw) > 30:
            try:
                llm_hooks = self._generate_llm_hooks(topic, raw)
                if llm_hooks:
                    hook_variants = llm_hooks
            except Exception as e:
                print(f"[LinkedInContentCopilotAgent] LLM hook generation failed: {e}")

        return CopilotDraftResponse(
            optimized_content=optimized_body,
            hook_variants=hook_variants,
            dwell_time_seconds=dwell_seconds,
            fold_safe=fold_safe,
            pre_fold_chars=pre_fold_chars,
            media_callout=media_callout
        )

    def _generate_llm_hooks(self, topic: str, content: str) -> Optional[List[str]]:
        """Invokes configured AI provider (Gemini, OpenAI, Claude, Groq, Ollama) to synthesize 5 high-converting hook variants."""
        prompt_text = (
            f"Generate 5 viral, scroll-stopping LinkedIn hook openers (each under 140 characters) "
            f"for this post draft on '{topic}'.\n\n"
            f"Post draft:\n{content[:500]}\n\n"
            f"Rules:\n"
            f"1. Zero em-dashes (\u2014 or – or --). Use commas or periods.\n"
            f"2. Return ONLY the 5 hooks numbered 1 to 5, nothing else."
        )
        system_prompt = "You are an elite LinkedIn copywriter. Strictly follow formatting rules and return only numbered hooks."
        res_text = execute_llm_completion(self.ai_config, prompt_text, system_prompt=system_prompt, max_tokens=300)
        if res_text:
            lines = [re.sub(r'^\d+[\.\)]\s*', '', l).strip() for l in res_text.split("\n") if l.strip()]
            cleaned_lines = [scrub_em_dashes(l) for l in lines if len(l) > 10]
            if len(cleaned_lines) >= 3:
                return cleaned_lines[:7]
        return None
