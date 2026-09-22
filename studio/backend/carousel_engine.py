"""
Vector Carousel Engine: Programmatic Multi-Slide PDF & SVG System (Day 13)
==========================================================================
Produces high-resolution 1080x1350 (4:5 vertical) and 1080x1080 (1:1 square)
vector slide decks for LinkedIn Document Carousels with Swiss typography.

Design Mandates:
1. Zero Em-Dashes: Character \\u2014 is strictly prohibited.
2. Vector Precision: Clean SVG and HTML5 print emulation with zero raster blur.
3. Air-Gapped Localhost: 100% offline generation with zero external SaaS fees.
"""

import html
import math
from typing import List, Dict, Any, Optional

THEMES = {
    "dark_obsidian": {
        "bg": "radial-gradient(circle at top right, #161D2E 0%, #07090E 70%)",
        "bg_color": "#07090E",
        "text_primary": "#F8FAFC",
        "text_secondary": "#94A3B8",
        "text_body": "#CBD5E1",
        "accent": "#6366F1",
        "border": "rgba(255, 255, 255, 0.1)"
    },
    "electric_indigo": {
        "bg": "radial-gradient(circle at top right, #312E81 0%, #0F172A 70%)",
        "bg_color": "#0F172A",
        "text_primary": "#FFFFFF",
        "text_secondary": "#A5B4FC",
        "text_body": "#E2E8F0",
        "accent": "#818CF8",
        "border": "rgba(129, 140, 248, 0.2)"
    },
    "light_minimal": {
        "bg": "#FFFFFF",
        "bg_color": "#FFFFFF",
        "text_primary": "#0F172A",
        "text_secondary": "#64748B",
        "text_body": "#334155",
        "accent": "#4F46E5",
        "border": "#E2E8F0"
    }
}


# -- Validation & Boundary Constants ----------------------------------------
MAX_CAROUSEL_SLIDES = 50
MIN_CAROUSEL_SLIDES = 1
MAX_SLIDE_TITLE_LENGTH = 300
MAX_SLIDE_BODY_LENGTH = 2000
MAX_SLIDE_TAG_LENGTH = 50
MAX_AUTHOR_NAME_LENGTH = 100
MAX_AUTHOR_TITLE_LENGTH = 150


# -- Text Fitting -----------------------------------------------------------
#
# A slide's content sits in a foreignObject 900px wide and 850px tall on 4:5,
# 580px on 1:1. A foreignObject clips. At the fixed 32px body size the box held
# roughly 950 characters on 4:5 and 640 on 1:1, while MAX_SLIDE_BODY_LENGTH
# allows 2000. Everything past the boundary was cut off the rendered slide and
# out of the exported deck with nothing said, so the creator found out from the
# PDF, or from the post.
#
# The type now scales down to fit, and when even the smallest size cannot hold
# the text the deck says so rather than quietly dropping it.

CONTENT_MARGIN_X = 90
CONTENT_TOP = 260
CONTENT_BOTTOM_RESERVE = 240

TITLE_FONT_MAX = 56
TITLE_FONT_MIN = 34
BODY_FONT_MAX = 32
BODY_FONT_MIN = 20

TITLE_LINE_RATIO = 1.15
BODY_LINE_RATIO = 1.5
TITLE_GAP = 36

# Average advance width as a fraction of the font size, for Plus Jakarta Sans
# at weight 800 and Inter at weight 400 over mixed case English.
#
# These are deliberate over-estimates. Erring wide shrinks a slide that would
# just have fitted, which is visible and harmless. Erring narrow clips text,
# which is invisible, and is the failure being fixed.
TITLE_ADVANCE_RATIO = 0.56
BODY_ADVANCE_RATIO = 0.52

# Tried in order, largest first, so a short slide keeps the full display size.
FIT_SCALES = (1.0, 0.92, 0.84, 0.76, 0.68, 0.62, 0.56, 0.5)


def _greedy_line_count(text: str, chars_per_line: int) -> int:
    """
    Counts the lines `text` occupies when wrapped on word boundaries.

    len(text) / chars_per_line under-counts, because a word that does not fit
    moves to the next line and leaves the rest of the current one empty. Since
    under-counting is what clips a slide, the wrap is walked properly.
    """
    if not text:
        return 0

    limit = max(1, int(chars_per_line))
    lines = 0

    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            # A blank line is a deliberate break and still takes its height.
            lines += 1
            continue

        lines += 1
        used = 0
        for word in words:
            if len(word) > limit:
                # An unbroken run longer than the line, such as a URL. CSS
                # overflow-wrap breaks it across lines rather than letting it
                # run past the edge of the box.
                if used > 0:
                    lines += 1
                spans = math.ceil(len(word) / limit)
                lines += spans - 1
                used = len(word) - (spans - 1) * limit
                continue

            needed = len(word) if used == 0 else len(word) + 1
            if used + needed <= limit:
                used += needed
            else:
                lines += 1
                used = len(word)

    return lines


class CarouselDeckEngine:
    """High-performance vector carousel and slide deck compiler."""

    @staticmethod
    def content_box(aspect_ratio: str = "4:5") -> Dict[str, int]:
        """The foreignObject the title and body are rendered into."""
        height = 1350 if str(aspect_ratio).strip() != "1:1" else 1080
        return {
            "width": 1080 - (CONTENT_MARGIN_X * 2),
            "height": height - CONTENT_TOP - CONTENT_BOTTOM_RESERVE,
        }

    @classmethod
    def fit_slide_text(
        cls,
        title: str,
        body: str,
        aspect_ratio: str = "4:5",
    ) -> Dict[str, Any]:
        """
        Chooses type sizes that keep the slide's text inside its box, and
        reports honestly when nothing fits.

        Returns the sizes to render at, the measured height, and, when the
        text still overflows at the smallest size, how much is over and
        roughly how many characters would have to go.
        """
        box = cls.content_box(aspect_ratio)
        box_width = box["width"]
        box_height = box["height"]

        title_text = str(title or "")
        body_text = str(body or "")

        measured: Dict[str, Any] = {}
        for scale in FIT_SCALES:
            title_size = max(TITLE_FONT_MIN, TITLE_FONT_MAX * scale)
            body_size = max(BODY_FONT_MIN, BODY_FONT_MAX * scale)

            title_lines = _greedy_line_count(
                title_text, box_width / (title_size * TITLE_ADVANCE_RATIO)
            )
            body_lines = _greedy_line_count(
                body_text, box_width / (body_size * BODY_ADVANCE_RATIO)
            )

            height = title_lines * title_size * TITLE_LINE_RATIO
            if title_lines and body_lines:
                height += TITLE_GAP
            height += body_lines * body_size * BODY_LINE_RATIO

            measured = {
                "title_font_size": round(title_size, 1),
                "body_font_size": round(body_size, 1),
                "title_lines": title_lines,
                "body_lines": body_lines,
                "estimated_height": int(round(height)),
                "box_height": box_height,
                "box_width": box_width,
                "scale": scale,
            }

            if height <= box_height:
                measured["overflow"] = False
                measured["overflow_px"] = 0
                measured["excess_chars"] = 0
                return measured

            if title_size <= TITLE_FONT_MIN and body_size <= BODY_FONT_MIN:
                break

        # Nothing fits, even at the floor. Say by how much, in the unit the
        # creator can act on: characters to cut.
        over_px = measured["estimated_height"] - box_height
        body_size = measured["body_font_size"]
        line_height = body_size * BODY_LINE_RATIO
        chars_per_line = box_width / (body_size * BODY_ADVANCE_RATIO)
        measured["overflow"] = True
        measured["overflow_px"] = int(round(over_px))
        measured["excess_chars"] = int(math.ceil(over_px / line_height * chars_per_line))
        return measured

    @classmethod
    def render_slide_svg(
        cls,
        slide: Optional[Dict[str, Any]],
        slide_index: int,
        total_slides: int,
        theme_name: str = "dark_obsidian",
        aspect_ratio: str = "4:5",
        author_name: str = "",
        author_title: str = "Enterprise Systems Practitioner"
    ) -> str:
        """
        Renders a standalone 1080x1350 (4:5) or 1080x1080 (1:1) SVG vector slide.
        Guarded against zero division, missing fields, and excessive string lengths.
        """
        aspect_ratio_clean = "1:1" if str(aspect_ratio).strip() == "1:1" else "4:5"
        is_4_5 = (aspect_ratio_clean == "4:5")
        width = 1080
        height = 1350 if is_4_5 else 1080

        theme_key = str(theme_name or "").strip().lower()
        th = THEMES.get(theme_key, THEMES["dark_obsidian"])

        if not isinstance(slide, dict):
            slide = {}

        # Safe bounds on slide numbers to prevent ZeroDivisionError
        safe_total = max(1, int(total_slides) if isinstance(total_slides, (int, float)) else 1)
        safe_index = max(0, min(int(slide_index) if isinstance(slide_index, (int, float)) else 0, safe_total - 1))

        raw_tag = slide.get("tag") or slide.get("category") or "ARCHITECTURE"
        tag = html.escape(str(raw_tag)[:MAX_SLIDE_TAG_LENGTH])

        raw_title = slide.get("title") or slide.get("headline") or ""
        title = html.escape(str(raw_title)[:MAX_SLIDE_TITLE_LENGTH])

        raw_body = slide.get("body") or slide.get("content") or ""
        body = html.escape(str(raw_body)[:MAX_SLIDE_BODY_LENGTH])

        author_name_safe = html.escape(str(author_name or "Creator")[:MAX_AUTHOR_NAME_LENGTH])
        author_title_safe = html.escape(str(author_title or "")[:MAX_AUTHOR_TITLE_LENGTH])

        num_str = f"{safe_index + 1:02d} / {safe_total:02d}"

        # Size the type to the text rather than clipping the text to the type.
        # The escaped strings are measured, not the raw ones, because an
        # ampersand renders as one glyph but occupies five characters here.
        fit = cls.fit_slide_text(
            title=html.unescape(title),
            body=html.unescape(body),
            aspect_ratio=aspect_ratio_clean,
        )
        title_font = fit["title_font_size"]
        body_font = fit["body_font_size"]

        # Progress bar calculation clamped to [0, 100]
        progress_pct = min(100.0, max(0.0, ((safe_index + 1) / safe_total) * 100))
        bar_width = max(0, min(width, int(width * progress_pct / 100)))

        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">
  <defs>
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@600;700;800&amp;family=Inter:wght@400;500;600&amp;family=JetBrains+Mono:wght@500;600&amp;display=swap');
      .tag {{ font-family: 'Plus Jakarta Sans', sans-serif; font-size: 26px; font-weight: 700; fill: {th['accent']}; letter-spacing: 2px; text-transform: uppercase; }}
      .pagination {{ font-family: 'JetBrains Mono', monospace; font-size: 24px; font-weight: 600; fill: {th['text_secondary']}; }}
      .title {{ font-family: 'Plus Jakarta Sans', sans-serif; font-size: {title_font}px; font-weight: 800; fill: {th['text_primary']}; line-height: {TITLE_LINE_RATIO}; letter-spacing: -0.5px; overflow-wrap: break-word; }}
      .body {{ font-family: 'Inter', sans-serif; font-size: {body_font}px; font-weight: 400; fill: {th['text_body']}; line-height: {BODY_LINE_RATIO}; overflow-wrap: break-word; }}
      .author {{ font-family: 'Plus Jakarta Sans', sans-serif; font-size: 24px; font-weight: 700; fill: {th['text_primary']}; }}
      .author-sub {{ font-family: 'Inter', sans-serif; font-size: 18px; font-weight: 500; fill: {th['text_secondary']}; }}
      .swipe-cta {{ font-family: 'Plus Jakarta Sans', sans-serif; font-size: 22px; font-weight: 600; fill: {th['accent']}; }}
    </style>
    <linearGradient id="bgGrad" x1="1" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{th['accent']}" stop-opacity="0.25"/>
      <stop offset="70%" stop-color="{th['bg_color']}"/>
    </linearGradient>
  </defs>

  <!-- Background -->
  <rect width="{width}" height="{height}" fill="{th['bg_color']}"/>
  <rect width="{width}" height="{height}" fill="url(#bgGrad)"/>

  <!-- Top Progress Bar -->
  <rect x="0" y="0" width="{width}" height="8" fill="{th['border']}"/>
  <rect x="0" y="0" width="{bar_width}" height="8" fill="{th['accent']}"/>

  <!-- Slide Header -->
  <g transform="translate(90, 110)">
    <text x="0" y="30" class="tag">{tag}</text>
    <text x="{width - 180}" y="30" text-anchor="end" class="pagination">{num_str}</text>
  </g>

  <!-- Slide Content -->
  <g transform="translate(90, 260)">
    <foreignObject x="0" y="0" width="{width - 180}" height="{height - 500}">
      <div xmlns="http://www.w3.org/1999/xhtml" style="word-break: break-word;">
        <h1 class="title" style="margin: 0 0 {TITLE_GAP}px 0;">{title}</h1>
        <p class="body" style="margin: 0; white-space: pre-wrap;">{body}</p>
      </div>
    </foreignObject>
  </g>

  <!-- Slide Footer -->
  <line x1="90" y1="{height - 130}" x2="{width - 90}" y2="{height - 130}" stroke="{th['border']}" stroke-width="2"/>
  <g transform="translate(90, {height - 85})">
    <text x="0" y="0" class="author">{author_name_safe}</text>
    <text x="0" y="26" class="author-sub">{author_title_safe}</text>
    <text x="{width - 180}" y="12" text-anchor="end" class="swipe-cta">Swipe &gt;&gt;</text>
  </g>
</svg>"""
        return svg

    @classmethod
    def compile_carousel_deck(
        cls,
        slides: List[Dict[str, Any]],
        theme: str = "dark_obsidian",
        aspect_ratio: str = "4:5",
        author_name: str = "",
        author_title: str = "Enterprise Systems Practitioner"
    ) -> Dict[str, Any]:
        """
        Compiles all slides into individual SVGs and a combined HTML printable deck.
        Enforces 1..50 slide boundaries.
        """
        if not isinstance(slides, list) or len(slides) < MIN_CAROUSEL_SLIDES:
            return {
                "status": "error",
                "message": f"Carousel requires at least {MIN_CAROUSEL_SLIDES} slide",
                "slides_count": 0,
                "slides": []
            }

        if len(slides) > MAX_CAROUSEL_SLIDES:
            return {
                "status": "error",
                "message": f"Slides count ({len(slides)}) exceeds maximum allowed of {MAX_CAROUSEL_SLIDES}",
                "slides_count": len(slides),
                "slides": []
            }

        total = len(slides)
        rendered_svgs = []
        warnings: List[Dict[str, Any]] = []

        norm_aspect = "1:1" if str(aspect_ratio).strip() == "1:1" else "4:5"
        norm_theme = str(theme or "").strip().lower()
        if norm_theme not in THEMES:
            norm_theme = "dark_obsidian"

        for idx, s in enumerate(slides):
            slide_dict = s if isinstance(s, dict) else {}
            svg_content = cls.render_slide_svg(
                slide=slide_dict,
                slide_index=idx,
                total_slides=total,
                theme_name=norm_theme,
                aspect_ratio=norm_aspect,
                author_name=author_name,
                author_title=author_title
            )
            raw_tag = slide_dict.get("tag") or slide_dict.get("category") or "SLIDE"
            raw_title = slide_dict.get("title") or slide_dict.get("headline") or ""
            raw_body = slide_dict.get("body") or slide_dict.get("content") or ""

            fit = cls.fit_slide_text(
                title=str(raw_title)[:MAX_SLIDE_TITLE_LENGTH],
                body=str(raw_body)[:MAX_SLIDE_BODY_LENGTH],
                aspect_ratio=norm_aspect,
            )
            if fit["overflow"]:
                # The slide is rendered either way. Clipping silently is what
                # this replaces, so the deck carries the bad news with it.
                warnings.append({
                    "slide_index": idx,
                    "slide_number": f"{idx + 1:02d} / {total:02d}",
                    "reason": "text_overflow",
                    "overflow_px": fit["overflow_px"],
                    "excess_chars": fit["excess_chars"],
                    "message": (
                        f"Slide {idx + 1} holds more text than a "
                        f"{norm_aspect} slide can show, even at the smallest "
                        f"type. Around {fit['excess_chars']} characters will "
                        f"be cut off."
                    ),
                })

            rendered_svgs.append({
                "slide_index": idx,
                "slide_number": f"{idx + 1:02d} / {total:02d}",
                "tag": str(raw_tag)[:MAX_SLIDE_TAG_LENGTH],
                "title": str(raw_title)[:MAX_SLIDE_TITLE_LENGTH],
                "svg": svg_content,
                "fit": fit
            })

        return {
            "status": "success",
            "slides_count": total,
            "theme": norm_theme,
            "aspect_ratio": norm_aspect,
            "dimensions": {"width": 1080, "height": 1350 if norm_aspect == "4:5" else 1080},
            "slides": rendered_svgs,
            "warnings": warnings
        }


# Global singleton
carousel_engine = CarouselDeckEngine()
