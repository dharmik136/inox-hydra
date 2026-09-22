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
from ..briefing import Brief, provenance, strip_preamble, validate_response
from ..model_gateway import get_current_ai_config, execute_llm_completion, AIProviderConfig

# LinkedIn truncates the opening line on mobile at roughly this width. A hook
# that crosses it loses its payoff behind a "see more", which is the one failure
# this product exists to prevent, so a model is not permitted to cross it either.
HOOK_FOLD_LIMIT = 140


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

        # Model hooks are merged, not substituted.
        #
        # Every hook the model returns is checked against the fold limit and the
        # banned vocabulary before it is allowed into the list, and the
        # deterministic templates backfill whatever is rejected. The old code
        # accepted any three lines over ten characters, which meant a model
        # could quietly replace ten fold safe hooks with three that truncate on
        # mobile, in a product whose whole claim is that it stops exactly that.
        hook_source = provenance("deterministic", "no provider configured")
        if self.ai_config and self.ai_config.is_configured and len(raw) > 30:
            model_hooks, hook_source = self._generate_llm_hooks(
                topic=topic,
                content=raw,
                audience=draft_input.target_audience,
                post_format=draft_input.post_format,
            )
            if model_hooks:
                # Model hooks lead because they are written against this draft.
                # Templates follow so the count never drops below the baseline.
                deterministic_fill = [h for h in hook_variants if h not in model_hooks]
                hook_variants = (model_hooks + deterministic_fill)[:10]

        return CopilotDraftResponse(
            optimized_content=optimized_body,
            hook_variants=hook_variants,
            dwell_time_seconds=dwell_seconds,
            fold_safe=fold_safe,
            pre_fold_chars=pre_fold_chars,
            media_callout=media_callout,
            hook_provenance=hook_source
        )

    def _generate_llm_hooks(
        self,
        topic: str,
        content: str,
        audience: str = "Engineering & Product Leaders",
        post_format: str = "framework_breakdown",
    ) -> tuple:
        """
        Asks the configured provider for hooks, then holds each one to the rules.

        The brief carries the audience and the post format, both of which are
        already in the input contract and were previously discarded before the
        model ever saw them. A hook written for the wrong reader is worse than a
        template written for the right one.

        Returns (accepted hooks or None, provenance).
        """
        brief = Brief(
            role=(
                "You are a LinkedIn copywriter who writes openers for practitioners. "
                "You write plainly and never pad."
            ),
            objective=f"Write 6 opening hooks for a post about {topic}.",
            inputs={
                "audience": audience,
                "post_format": post_format,
                "draft_excerpt": content[:600],
            },
            constraints=[
                f"Every hook must be under {HOOK_FOLD_LIMIT} characters. "
                "LinkedIn truncates the rest behind a 'see more' on mobile.",
                "No em-dashes, en-dashes or double dashes. Use commas or full stops.",
                "No hashtags, no emoji, no links.",
                "Each hook must be able to open the post on its own, not describe it.",
                "Vary the angle across the six: contrarian, concrete number, hard lesson, "
                "direct question, blunt statement, specific scene.",
            ],
            forbidden=["game-changing", "revolutionary", "in today's fast-paced world", "delve"],
            output_contract="six hooks, one per line, numbered 1 to 6, nothing else.",
        )

        system_prompt, user_prompt = brief.render()
        try:
            raw = execute_llm_completion(
                self.ai_config, user_prompt, system_prompt=system_prompt, max_tokens=400
            )
        except Exception as err:
            return None, provenance("deterministic", f"provider error: {err}", self.ai_config.model)

        if not raw or not raw.strip():
            return None, provenance("deterministic", "empty response", self.ai_config.model)

        accepted: List[str] = []
        rejected = 0
        for line in raw.split("\n"):
            candidate = re.sub(r'^\s*\d+[\.\)]\s*', '', strip_preamble(line)).strip()
            if not candidate:
                continue

            ok, cleaned, _reason = validate_response(
                candidate, min_chars=15, max_chars=HOOK_FOLD_LIMIT
            )
            if not ok:
                rejected += 1
                continue

            # Checked again through the product's own fold rule rather than
            # trusting the character count alone, so this cannot drift from what
            # the rest of the studio calls fold safe.
            is_fold_safe, _chars = validate_pre_fold_hook(cleaned, max_chars=HOOK_FOLD_LIMIT)
            if not is_fold_safe:
                rejected += 1
                continue

            if cleaned not in accepted:
                accepted.append(cleaned)

        if len(accepted) < 3:
            return None, provenance(
                "deterministic",
                f"only {len(accepted)} of {len(accepted) + rejected} hooks passed the fold and vocabulary rules",
                self.ai_config.model,
            )

        return accepted[:7], provenance(
            "model_assisted",
            f"{len(accepted)} accepted, {rejected} rejected",
            self.ai_config.model,
        )
