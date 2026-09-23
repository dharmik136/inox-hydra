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

# Grounding is optional in the strongest sense: the studio has to keep writing
# posts on a machine where this package failed to import for any reason. The
# import is guarded rather than assumed, and everything below treats its
# absence as "no material", which is the same path a creator with no servers
# configured takes anyway.
# The two spellings are both real. The backend is imported as
# `studio.backend.agno_agentos...` from the installed package and as
# `agno_agentos...` when studio/backend is on sys.path directly, which is how
# the app and the tests load it. A three level relative import runs off the
# top of the package in the second case, so it is tried and then fallen back
# from, the same way database and event_bus are imported elsewhere here.
try:
    from ...mcp_client import as_brief_inputs, gather, grounding_provenance
except Exception:  # pragma: no cover - the fallback below is the common path
    try:
        from mcp_client import as_brief_inputs, gather, grounding_provenance
    except Exception:
        as_brief_inputs = None
        gather = None
        grounding_provenance = None

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


def _with_grounding(record: dict, grounded: dict) -> dict:
    """
    Attaches what grounded a generation to the record of where it came from.

    On every path, including the ones where the model was never reached. A
    creator whose notes were gathered and sent to a hosted provider needs that
    written down even when the generation then failed, because the material
    left the machine either way and a record that only covers the successes is
    not a record of what happened.
    """
    merged = dict(record or {})
    merged["grounding"] = (grounded or {}).get("provenance") or {"grounded": False}
    return merged


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

    def _gather_grounding(self) -> dict:
        """
        Material from the creator's own MCP servers, and where it is going.

        Returns `{"inputs": {...}, "provenance": {...}}`, always. A creator
        with nothing connected, a package that failed to import, a notes
        server that is down, and an outright exception all produce the same
        empty result, because none of them is a reason to stop writing the
        post. The briefing module's rule applies here too: enhancement is an
        improvement, never a dependency.

        The provider is passed through rather than defaulted, because the
        egress report is a claim about where this creator's notes are about to
        go, and a stale or guessed provider would make that claim about the
        wrong configuration.
        """
        empty = {"inputs": {}, "provenance": {"grounded": False}}
        if gather is None or as_brief_inputs is None:
            return empty
        try:
            gathered = gather(provider=getattr(self.ai_config, "provider", ""))
            return {
                "inputs": as_brief_inputs(gathered),
                "provenance": grounding_provenance(gathered),
            }
        except Exception:
            return empty

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
        # Defined before the brief because the grounding it gathers becomes
        # Gathered first, because it becomes part of the brief below and its
        # provenance is attached to every path out of this method, including
        # the failures.
        #
        # This is the thing a cloud tool cannot do. It has never read the
        # migration this creator ran or the review they sat in, so its hooks
        # are generic no matter how good its model is.
        grounded = self._gather_grounding()
        grounding_inputs = grounded["inputs"]

        brief_inputs = {
            "audience": audience,
            "post_format": post_format,
            "draft_excerpt": content[:600],
        }
        # The creator's material goes last, so a long note cannot push the
        # audience and the draft out of the model's attention.
        brief_inputs.update(grounding_inputs)

        constraints = [
            f"Every hook must be under {HOOK_FOLD_LIMIT} characters. "
            "LinkedIn truncates the rest behind a 'see more' on mobile.",
            "No em-dashes, en-dashes or double dashes. Use commas or full stops.",
            "No hashtags, no emoji, no links.",
            "Each hook must be able to open the post on its own, not describe it.",
            "Vary the angle across the six: contrarian, concrete number, hard lesson, "
            "direct question, blunt statement, specific scene.",
        ]

        if grounding_inputs:
            # Said explicitly, because a model handed extra sections without
            # being told what they are treats them as background and writes
            # the same generic hook it would have written anyway. Naming the
            # sections is what turns material into specificity.
            constraints.append(
                "The sections after the draft excerpt are the author's own notes and "
                "records. Draw the specifics from them: real numbers, real incidents, "
                "real decisions. Do not invent detail that is not there, and do not "
                "quote them verbatim."
            )

        brief = Brief(
            role=(
                "You are a LinkedIn copywriter who writes openers for practitioners. "
                "You write plainly and never pad."
            ),
            objective=f"Write 6 opening hooks for a post about {topic}.",
            inputs=brief_inputs,
            constraints=constraints,
            forbidden=["game-changing", "revolutionary", "in today's fast-paced world", "delve"],
            output_contract="six hooks, one per line, numbered 1 to 6, nothing else.",
        )

        system_prompt, user_prompt = brief.render()
        try:
            raw = execute_llm_completion(
                self.ai_config, user_prompt, system_prompt=system_prompt, max_tokens=400
            )
        except Exception as err:
            return None, _with_grounding(
                provenance("deterministic", f"provider error: {err}", self.ai_config.model),
                grounded,
            )

        if not raw or not raw.strip():
            return None, _with_grounding(
                provenance("deterministic", "empty response", self.ai_config.model),
                grounded,
            )

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
            return None, _with_grounding(
                provenance(
                    "deterministic",
                    f"only {len(accepted)} of {len(accepted) + rejected} hooks passed the fold and vocabulary rules",
                    self.ai_config.model,
                ),
                grounded,
            )

        return accepted[:7], _with_grounding(
            provenance(
                "model_assisted",
                f"{len(accepted)} accepted, {rejected} rejected",
                self.ai_config.model,
            ),
            grounded,
        )
