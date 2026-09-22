"""
ImagePromptSynthesizerAgent (Agno AgentOS Visual Director)
===========================================================
Synthesizes professional generative image prompts from user options and creative concept.
Adheres to P1/P6/P7: Strict Pydantic contracts, negative prompt constraints, zero em-dashes.
"""

import os
import re
from typing import Dict, Any, List, Optional
import requests

from ..contracts import ImagePromptInput, SynthesizedImagePrompt
from ..scar_tissue import scrub_em_dashes
from ..briefing import Brief, provenance, validate_response
from ..model_gateway import get_current_ai_config, execute_llm_completion, AIProviderConfig


class ImagePromptSynthesizerAgent:
    """Agent responsible for crafting high-fidelity generative prompts."""

    STYLE_PROFILES: Dict[str, str] = {
        "photorealistic": (
            "Professional Hasselblad H6D-100c commercial photography, 85mm f/1.4 lens, "
            "crisp shallow depth of field, authentic micro-textures, editorial grade, 8k resolution"
        ),
        "blueprint": (
            "Technical engineering schematic and systems blueprint, clean crisp vector linework, "
            "precise geometric layout, isometric topology, architectural drafting precision"
        ),
        "editorial": (
            "Bloomberg and Forbes editorial magazine feature aesthetic, sophisticated corporate composition, "
            "dramatic high-contrast lighting, clean architectural negative space, modern executive tone"
        ),
        "3d_isometric": (
            "3D isometric render, frosted glassmorphism and matte clay materials, Octane Render style, "
            "smooth subsurface scattering, subtle ambient occlusion, sleek modern tech aesthetic"
        ),
        "isometric_3d": (
            "3D isometric render, frosted glassmorphism and matte clay materials, Octane Render style, "
            "smooth subsurface scattering, subtle ambient occlusion, sleek modern tech aesthetic"
        ),
        "minimalist_sketch": (
            "Minimalist architectural composition, clean concrete geometry, austere museum gallery aesthetic, "
            "contemplative zen negative space, dramatic solitary light beam, gallery curation"
        ),
        "sketch": (
            "Architectural pen and ink conceptual drawing with subtle watercolor wash, precise line work, "
            "executive whiteboard diagram feel, artisan craftsmanship, clean background"
        )
    }

    PALETTE_PROFILES: Dict[str, str] = {
        "navy_cyan": "Deep executive navy blue (#0A192F), vibrant electric cyan (#00F2FE), subtle slate accents",
        "slate_emerald": "Deep slate gray, rich muted emerald green (#10B981), crisp white architectural highlights",
        "obsidian_monochrome": "Minimalist high-contrast monochrome, deep obsidian charcoal (#0B0F19) and pure stark white",
        "amber_warmth": "Warm amber glow (#D97706), rich dark charcoal slate, golden hour accents",
        "sunset_gradient": "Deep twilight indigo and radiant sunset warmth, subtle violet and ember tones",
        "obsidian_indigo": "Dark obsidian slate (#0B0F19), electric indigo highlights (#6366F1), subtle charcoal shadows",
        "monochrome": "Minimalist monochrome grayscale, high-contrast charcoal (#121212) and pure titanium white",
        "emerald_gold": "Deep dark emerald forest green (#064E3B), luxury metallic brass/gold (#D97706) highlights",
        "cyber_neon": "Cyberpunk high-contrast black (#000000), neon ultraviolet (#8B5CF6) and hot magenta (#EC4899)"
    }

    LIGHTING_PROFILES: Dict[str, str] = {
        "studio": "Three-point studio softbox lighting, subtle rim lighting, professional photography setup",
        "dramatic_rim": "Dramatic high-contrast rim lighting, sharp edge contours, deep moody shadows",
        "neon_cyber": "Dark atmosphere with subtle edge glow, fiber-optic blue backlighting, glowing circuit traces",
        "golden_hour": "Warm golden hour sunlight raking across surfaces, long soft shadows, ethereal atmosphere",
        "cinematic": "Dramatic high-contrast cinematic lighting, volumetric light rays, moody atmospheric shadows",
        "ambient": "Diffused natural morning daylight filtering through floor-to-ceiling modern architectural glass"
    }

    NEGATIVE_PROMPT: str = (
        "low quality, blurry, deformed fingers, extra limbs, ugly text, artifacts, watermark, distorted, grain, oversaturated"
    )

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

    def synthesize(self, prompt_input: ImagePromptInput) -> SynthesizedImagePrompt:
        """
        Synthesizes a master prompt from creator input.
        Uses deterministic expert heuristics by default, seamlessly enhanced with active AI provider if available.
        Prevents bust/portrait hallucinations on quote requests and decouples background scene from typography.
        """
        raw_concept = scrub_em_dashes(prompt_input.concept.strip())
        
        # Clean common input typos
        clean_concept = raw_concept
        clean_concept = re.sub(r'\bquotee\b', 'quote', clean_concept, flags=re.IGNORECASE)
        clean_concept = re.sub(r'\bdarkand\b', 'dark and', clean_concept, flags=re.IGNORECASE)
        clean_concept = re.sub(r'\blight flowin\b', 'light flowing from', clean_concept, flags=re.IGNORECASE)

        lower_c = clean_concept.lower()
        explicit_statue = any(k in lower_c for k in ["statue", "bust", "portrait", "face of"])

        # Detect and extract quote details
        quote_text = prompt_input.custom_quote_text
        quote_author = prompt_input.custom_quote_author

        if not quote_text:
            if "socrates" in lower_c:
                quote_author = quote_author or "Socrates"
                quote_text = "The only true wisdom is in knowing you know nothing."
            elif "marcus aurelius" in lower_c:
                quote_author = quote_author or "Marcus Aurelius"
                quote_text = "You have power over your mind, not outside events."
            elif "steve jobs" in lower_c:
                quote_author = quote_author or "Steve Jobs"
                quote_text = "Stay hungry, stay foolish."
            elif "seneca" in lower_c:
                quote_author = quote_author or "Seneca"
                quote_text = "Luck is what happens when preparation meets opportunity."
            else:
                m = re.search(r'["\']([^"\']{6,120})["\']', clean_concept)
                if m:
                    quote_text = m.group(1).strip()
                    quote_author = quote_author or "Leadership"

        style_desc = self.STYLE_PROFILES.get(prompt_input.visual_style, self.STYLE_PROFILES["photorealistic"])
        palette_desc = self.PALETTE_PROFILES.get(prompt_input.color_palette, self.PALETTE_PROFILES["navy_cyan"])
        lighting_desc = self.LIGHTING_PROFILES.get(prompt_input.lighting, self.LIGHTING_PROFILES["studio"])

        # Map dimensions based on aspect ratio
        ratio = prompt_input.aspect_ratio
        if ratio == "4:5":
            width, height = 1080, 1350
        elif ratio == "16:9":
            width, height = 1920, 1080
        else:
            ratio = "1:1"
            width, height = 1080, 1080

        # Formulate master prompt avoiding statue/bust hallucinations if a room/setting for a quote was requested
        negative_prompt = self.NEGATIVE_PROMPT
        # The scene the model is allowed to rewrite, kept separate from the
        # scaffold it is not. Set in the quote branch below and reused for the
        # briefing, so the model works on the cleaned environment description
        # rather than on a concept string that still names a person.
        scene_for_brief = clean_concept
        reserve_negative_space = False

        if quote_text and not explicit_statue:
            negative_prompt = f"{self.NEGATIVE_PROMPT}, marble bust, statue of person, human face portrait, distorted text"
            # Formulate scene background
            scene_desc = clean_concept
            scene_desc = re.sub(r'^(i\s+need|create|generate|make|show\s+me)\s+(a\s+|an\s+)?(image|picture|visual|quote)?\s*(based\s+on|with|of)?\s*', '', scene_desc, flags=re.IGNORECASE).strip()
            # Clean philosopher name from scene generation so diffusion engine generates the environment, not a face
            for name in ["socrates", "marcus aurelius", "steve jobs", "seneca"]:
                scene_desc = re.sub(rf'\b{name}\'?s?\b', '', scene_desc, flags=re.IGNORECASE).strip()
            scene_desc = re.sub(r'\b(quote|quotes|based on)\b', '', scene_desc, flags=re.IGNORECASE).strip()
            scene_desc = re.sub(r'^(in|of|with|for)\s+', '', scene_desc, flags=re.IGNORECASE).strip()
            scene_desc = re.sub(r'\s+', ' ', scene_desc).strip()

            if not scene_desc or len(scene_desc) < 8:
                scene_desc = "quiet dark and white room with a light flowing from the corner"

            scene_for_brief = scene_desc
            reserve_negative_space = True

            master_prompt = (
                f"Minimalist architectural photography of {scene_desc}. "
                f"Visual Style: {style_desc}. "
                f"Color Palette: {palette_desc}. "
                f"Lighting: {lighting_desc}, dramatic single sunlight ray casting chiaroscuro shadows. "
                f"Composition: Balanced, quiet contemplative mood, generous negative space for quote typography, 8k uhd."
            )
        else:
            quote_instruction = ""
            if quote_text:
                quote_instruction = f" Featuring negative space displaying quote: '{quote_text}'. "
            master_prompt = (
                f"{clean_concept}.{quote_instruction}"
                f"Visual Style: {style_desc}. "
                f"Color Palette: {palette_desc}. "
                f"Lighting: {lighting_desc}. "
                f"Composition: Centered, balanced negative space for LinkedIn hero visual, photorealistic materials, 8k uhd."
            )

        # Enhancement composes, it does not replace.
        #
        # The model is asked for one thing: a richer description of the scene.
        # Style, palette, lighting, composition and the negative space the quote
        # compositor depends on are appended afterwards from the resolved
        # profiles, so a model that ignores them cannot drop them. This used to
        # overwrite master_prompt wholesale, which meant configuring a provider
        # silently produced worse images than running with none.
        prompt_source = provenance("deterministic", "no provider configured")
        if self.ai_config and self.ai_config.is_configured:
            enhanced_scene, prompt_source = self._describe_scene(
                scene=scene_for_brief,
                style=prompt_input.visual_style,
                palette=prompt_input.color_palette,
                lighting=prompt_input.lighting,
                aspect_ratio=ratio,
                quote_text=quote_text,
                reserve_negative_space=reserve_negative_space,
                is_statue=explicit_statue,
            )
            if enhanced_scene:
                master_prompt = self._compose(
                    scene=enhanced_scene,
                    style_desc=style_desc,
                    palette_desc=palette_desc,
                    lighting_desc=lighting_desc,
                    quote_text=quote_text,
                    reserve_negative_space=reserve_negative_space,
                )

        aesthetic_notes = (
            f"Engineered for {ratio} format ({width}x{height}px) using {prompt_input.visual_style} aesthetic "
            f"and {prompt_input.color_palette} palette."
        )

        return SynthesizedImagePrompt(
            master_prompt=master_prompt,
            negative_prompt=negative_prompt,
            aspect_ratio=ratio,
            width=width,
            height=height,
            technical_parameters={
                "aspect_ratio": ratio,
                "style": prompt_input.visual_style,
                "palette": prompt_input.color_palette,
                "lighting": prompt_input.lighting,
                "quote_text": quote_text,
                "quote_author": quote_author,
                "render_quote_overlay": prompt_input.render_quote_overlay,
                "prompt_provenance": prompt_source
            },
            aesthetic_notes=aesthetic_notes,
            quote_text=quote_text,
            quote_author=quote_author
        )

    def _compose(
        self,
        scene: str,
        style_desc: str,
        palette_desc: str,
        lighting_desc: str,
        quote_text: Optional[str],
        reserve_negative_space: bool,
    ) -> str:
        """
        Builds the final prompt from a scene plus the resolved profiles.

        The single place a master prompt is assembled, whether the scene came
        from the deterministic path or from a model. That is what guarantees
        lighting and composition survive either way.
        """
        composition = (
            "Composition: Balanced, quiet contemplative mood, generous unobstructed negative space "
            "in the lower third reserved for quote typography, nothing important behind it, 8k uhd."
            if reserve_negative_space else
            "Composition: Centered, balanced negative space for LinkedIn hero visual, "
            "photorealistic materials, 8k uhd."
        )
        quote_clause = ""
        if quote_text and not reserve_negative_space:
            quote_clause = f" Featuring negative space displaying quote: '{quote_text}'."

        return scrub_em_dashes(
            f"{scene.rstrip('.')}.{quote_clause} "
            f"Visual Style: {style_desc}. "
            f"Color Palette: {palette_desc}. "
            f"Lighting: {lighting_desc}. "
            f"{composition}"
        )

    def _describe_scene(
        self,
        scene: str,
        style: str,
        palette: str,
        lighting: str,
        aspect_ratio: str,
        quote_text: Optional[str],
        reserve_negative_space: bool,
        is_statue: bool,
    ) -> tuple:
        """
        Asks the model for a richer scene description, and nothing else.

        The brief carries everything already decided, including the lighting and
        aspect ratio the old call never mentioned, so the model enriches within
        the direction instead of inventing a competing one. A response that
        smuggles in a face when the frame is reserved for a quote is rejected
        outright rather than shipped to the diffusion engine.

        Returns (scene or None, provenance).
        """
        forbidden: List[str] = []
        constraints = [
            "Describe only the physical scene, setting, materials and atmosphere.",
            "Never name a person, and never describe a face, portrait, bust or statue "
            "unless the inputs explicitly ask for one.",
            "Do not mention colour palette, lighting setup, camera gear or resolution. "
            "Those are appended separately and repeating them corrupts the prompt.",
            "Write one flowing description, maximum 60 words, no lists, no headings.",
        ]

        if quote_text and not is_statue:
            forbidden = ["marble bust", "statue", "portrait", "human face", "sculpture"]
            constraints.append(
                "The lower third of the frame must stay visually quiet and uncluttered, "
                "because typography is composited over it afterwards."
            )

        brief = Brief(
            role=(
                "You are the visual director for a generative image pipeline that feeds "
                "DALL-E 3, Imagen 3 and Midjourney."
            ),
            objective="Expand the scene into a vivid, concrete description of the environment.",
            inputs={
                "scene": scene,
                "style_key": style,
                "palette_key": palette,
                "lighting_key": lighting,
                "aspect_ratio": aspect_ratio,
                "typography_overlay": "yes, lower third must stay clear" if reserve_negative_space else "no",
            },
            constraints=constraints,
            forbidden=forbidden,
            output_contract="the scene description only, as a single paragraph.",
        )

        system_prompt, user_prompt = brief.render()
        try:
            raw = execute_llm_completion(
                self.ai_config, user_prompt, system_prompt=system_prompt,
                max_tokens=200, temperature=0.4,
            )
        except Exception as err:
            return None, provenance("deterministic", f"provider error: {err}", self.ai_config.model)

        accepted, cleaned, reason = validate_response(
            raw,
            min_chars=20,
            max_chars=700,
            forbidden_terms=forbidden,
        )
        if not accepted:
            return None, provenance("deterministic", f"model response rejected: {reason}", self.ai_config.model)

        return cleaned, provenance("model_assisted", "accepted", self.ai_config.model)
