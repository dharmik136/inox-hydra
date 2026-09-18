"""
ImagePromptSynthesizerAgent (Agno AgentOS Visual Director)
===========================================================
Synthesizes professional generative image prompts from user options and creative concept.
Adheres to P1/P6/P7: Strict Pydantic contracts, negative prompt constraints, zero em-dashes.
"""

import os
import re
from typing import Dict, Any, Optional
import requests

from ..contracts import ImagePromptInput, SynthesizedImagePrompt
from ..scar_tissue import scrub_em_dashes
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

        # Enhance with configured AI provider if active
        if self.ai_config and self.ai_config.is_configured:
            try:
                enhanced = self._call_llm_enhancer(clean_concept, prompt_input.visual_style, prompt_input.color_palette, quote_text=quote_text, is_statue=explicit_statue)
                if enhanced:
                    master_prompt = enhanced
            except Exception as e:
                print(f"[ImagePromptSynthesizerAgent] LLM enhancement failed: {e}. Falling back to deterministic prompt.")

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
                "render_quote_overlay": prompt_input.render_quote_overlay
            },
            aesthetic_notes=aesthetic_notes,
            quote_text=quote_text,
            quote_author=quote_author
        )

    def _call_llm_enhancer(self, concept: str, style: str, palette: str, quote_text: Optional[str] = None, is_statue: bool = False) -> Optional[str]:
        """Calls configured AI provider to enrich prompt with cinematic detail while respecting constraints."""
        bust_guard = ""
        if quote_text and not is_statue:
            bust_guard = "CRITICAL: Describe the architectural room and dramatic lighting with negative space. Do NOT include a marble bust, statue, or face. "

        prompt = (
            f"You are an expert generative AI image prompt engineer for Midjourney, DALL-E 3, and Imagen 3. "
            f"Transform this concept into a single descriptive prompt (maximum 75 words): '{concept}'. "
            f"Style: {style}. Palette: {palette}. {bust_guard}"
            f"Do not write conversational filler or preamble. Return ONLY the final prompt."
        )
        res_text = execute_llm_completion(self.ai_config, prompt, max_tokens=200, temperature=0.4)
        if res_text and len(res_text.strip()) > 10:
            return scrub_em_dashes(res_text.strip())
        return None
