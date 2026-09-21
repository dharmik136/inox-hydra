"""
Carousel PDF Document Generator (Taplio Pro $199/mo Equivalent)
================================================================
Programmatic 1080x1080 canvas renderer for swipeable LinkedIn document carousels.
Engineered using Python's native Pillow library with zero third-party cloud API dependencies.

Features:
- Native 1080x1080 pixel-perfect square aspect ratio.
- 3 Curated Enterprise Themes: Dark Slate, Clean Minimalist, Engineering Blueprint.
- Adaptive typography wrapping, header badges, progress bars, and swipe callouts.
- Direct in-memory PDF binary stream output.

Status: SUPERSEDED, retained deliberately.
This Pillow renderer is not wired to any route. The endpoint that used to serve
it, POST /api/carousel/generate, now returns a notice directing callers to the
native PDF dropzone, and vector decks are compiled by carousel_engine.py
instead. The module and its tests are kept because the bitmap path is the only
one that produces a true raster PDF, and removing a tested capability is a
product decision rather than a cleanup. Nothing imports it outside the suite.

The 30 slide cap below is lower than carousel_engine's 50 on purpose: this
renderer holds full 1080x1080 bitmaps in memory, which the SVG compiler does not.

Strict Invariants:
- Zero em-dashes across all rendered slides, comments, and docstrings.
- Bounded input slides (max 30) to prevent memory exhaustion.
"""

import io
import os
from typing import Any, Dict, List
from PIL import Image, ImageDraw, ImageFont

# Constants for 1080x1080 square LinkedIn carousel standard
WIDTH = 1080
HEIGHT = 1080
MAX_CAROUSEL_SLIDES = 30
MAX_SLIDE_TITLE_LEN = 500
MAX_SLIDE_BODY_LEN = 3000

THEMES = {
    "dark_slate": {
        "bg": (10, 15, 29),
        "card_bg": (20, 30, 51),
        "accent": (14, 165, 233),
        "accent_glow": (99, 102, 241),
        "text": (248, 250, 252),
        "text_muted": (148, 163, 184),
        "border": (30, 41, 59),
    },
    "minimalist": {
        "bg": (248, 250, 252),
        "card_bg": (255, 255, 255),
        "accent": (2, 132, 199),
        "accent_glow": (14, 165, 233),
        "text": (15, 23, 42),
        "text_muted": (100, 116, 139),
        "border": (226, 232, 240),
    },
    "engineering_blue": {
        "bg": (15, 23, 42),
        "card_bg": (30, 41, 59),
        "accent": (56, 189, 248),
        "accent_glow": (129, 140, 248),
        "text": (241, 245, 249),
        "text_muted": (148, 163, 184),
        "border": (51, 65, 85),
    },
}


def get_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Fallback font loader with cross-platform system font discovery."""
    bounded_size = max(8, min(int(size), 144))
    font_paths = [
        # Windows
        "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\segoeuib.ttf" if bold else "C:\\Windows\\Fonts\\segoeui.ttf",
        "C:\\Windows\\Fonts\\calibrib.ttf" if bold else "C:\\Windows\\Fonts\\calibri.ttf",
        # Linux / Unix
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        # macOS
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, bounded_size)
            except Exception:
                continue
    return ImageFont.load_default()


def wrap_text(text: Any, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> List[str]:
    """Wraps text into lines that fit within max_width."""
    if text is None:
        return []
    clean_text = str(text).strip()
    words = clean_text.split()
    if not words:
        return []

    lines = []
    current_line = words[0]

    for word in words[1:]:
        test_line = current_line + " " + word
        try:
            bbox = draw.textbbox((0, 0), test_line, font=font)
            line_width = bbox[2] - bbox[0]
        except Exception:
            line_width = len(test_line) * 10

        if line_width <= max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word
    lines.append(current_line)
    return lines


def render_slide(
    slide_index: int,
    total_slides: int,
    title: str,
    body: str,
    author_name: str = "Dharmik Shingala",
    author_title: str = "Content Strategist & Enterprise Systems Practitioner",
    theme_name: str = "dark_slate",
    is_cover: bool = False,
    is_cta: bool = False,
) -> Image.Image:
    """Renders a single 1080x1080 carousel slide with professional aesthetics."""
    theme_key = str(theme_name or "dark_slate").lower()
    theme = THEMES.get(theme_key, THEMES["dark_slate"])
    img = Image.new("RGB", (WIDTH, HEIGHT), theme["bg"])
    draw = ImageDraw.Draw(img)

    # Dynamic em-dash sanitization
    em_dash = chr(0x2014)
    en_dash = chr(0x2013)
    safe_title = str(title or "").replace(em_dash, " -- ").replace(en_dash, "-")[:MAX_SLIDE_TITLE_LEN]
    safe_body = str(body or "").replace(em_dash, " -- ").replace(en_dash, "-")[:MAX_SLIDE_BODY_LEN]
    safe_author = str(author_name or "Dharmik Shingala")[:100]
    safe_author_title = str(author_title or "Enterprise Systems Practitioner")[:150]

    # Outer border & subtle glow frame
    draw.rectangle([24, 24, WIDTH - 24, HEIGHT - 24], outline=theme["border"], width=2)

    # Header Row: Author branding & Slide Index
    avatar_bg = theme["accent"]
    draw.ellipse([64, 60, 114, 110], fill=avatar_bg)
    font_av = get_font(20, bold=True)
    draw.text((76, 74), "DS", fill=(255, 255, 255), font=font_av)

    font_author = get_font(22, bold=True)
    draw.text((130, 64), safe_author, fill=theme["text"], font=font_author)

    font_title = get_font(15, bold=False)
    draw.text((130, 92), safe_author_title, fill=theme["text_muted"], font=font_title)

    # Top-right Slide counter
    total_safe = max(1, total_slides)
    counter_text = f"{slide_index + 1} / {total_safe}"
    font_counter = get_font(16, bold=True)
    draw.text((WIDTH - 150, 76), counter_text, fill=theme["accent"], font=font_counter)

    # Accent divider rule
    draw.line([64, 136, WIDTH - 64, 136], fill=theme["border"], width=1)

    # Central Card Container
    card_top = 180
    card_bottom = HEIGHT - 180
    draw.rounded_rectangle(
        [64, card_top, WIDTH - 64, card_bottom],
        radius=16,
        fill=theme["card_bg"],
        outline=theme["border"],
        width=1,
    )

    # Content within Card
    content_x = 110
    content_width = WIDTH - 220
    content_y = card_top + 60

    if is_cover:
        # Cover Slide: Big Hook Title
        font_hook_tag = get_font(18, bold=True)
        draw.text((content_x, content_y), "EXECUTIVE FRAMEWORK", fill=theme["accent"], font=font_hook_tag)
        content_y += 40

        font_main_title = get_font(44, bold=True)
        title_lines = wrap_text(safe_title, font_main_title, content_width, draw)
        for line in title_lines:
            draw.text((content_x, content_y), line, fill=theme["text"], font=font_main_title)
            content_y += 62

        content_y += 20
        font_body = get_font(24, bold=False)
        body_lines = wrap_text(safe_body, font_body, content_width, draw)
        for line in body_lines:
            draw.text((content_x, content_y), line, fill=theme["text_muted"], font=font_body)
            content_y += 38

        # Bottom Call to Swipe
        swipe_box_y = card_bottom - 90
        draw.rounded_rectangle([content_x, swipe_box_y, content_x + 220, swipe_box_y + 44], radius=8, fill=theme["accent"])
        font_swipe = get_font(16, bold=True)
        draw.text((content_x + 32, swipe_box_y + 12), "Swipe to Read ->", fill=(255, 255, 255), font=font_swipe)

    elif is_cta:
        # Final CTA Slide
        font_num = get_font(18, bold=True)
        draw.text((content_x, content_y), "SUMMARY & NEXT STEPS", fill=theme["accent"], font=font_num)
        content_y += 40

        font_main_title = get_font(40, bold=True)
        title_lines = wrap_text(safe_title, font_main_title, content_width, draw)
        for line in title_lines:
            draw.text((content_x, content_y), line, fill=theme["text"], font=font_main_title)
            content_y += 56

        content_y += 20
        font_body = get_font(24, bold=False)
        body_lines = wrap_text(safe_body, font_body, content_width, draw)
        for line in body_lines:
            draw.text((content_x, content_y), line, fill=theme["text_muted"], font=font_body)
            content_y += 38

        # CTA Bookmark prompt
        cta_box_y = card_bottom - 110
        draw.rounded_rectangle([content_x, cta_box_y, WIDTH - 110, cta_box_y + 60], radius=10, fill=theme["bg"], outline=theme["accent"], width=1)
        font_cta_text = get_font(18, bold=True)
        draw.text((content_x + 30, cta_box_y + 18), "Save this carousel to revisit enterprise system principles.", fill=theme["text"], font=font_cta_text)

    else:
        # Intermediate Slide: Step Number + Title + Body
        step_num_text = f"STEP {slide_index:02d}"
        font_num = get_font(18, bold=True)
        draw.text((content_x, content_y), step_num_text, fill=theme["accent"], font=font_num)
        content_y += 36

        font_main_title = get_font(36, bold=True)
        title_lines = wrap_text(safe_title, font_main_title, content_width, draw)
        for line in title_lines:
            draw.text((content_x, content_y), line, fill=theme["text"], font=font_main_title)
            content_y += 50

        content_y += 24
        font_body = get_font(24, bold=False)
        body_lines = wrap_text(safe_body, font_body, content_width, draw)
        for line in body_lines:
            draw.text((content_x, content_y), line, fill=theme["text_muted"], font=font_body)
            content_y += 38

    # Bottom slide footer
    font_footer = get_font(15, bold=False)
    draw.text((64, HEIGHT - 100), "Dharmik Shingala - Personal LinkedIn Studio", fill=theme["text_muted"], font=font_footer)

    # Progress bar line at the very bottom
    prog_width = int((WIDTH - 128) * ((slide_index + 1) / total_safe))
    draw.line([64, HEIGHT - 64, 64 + prog_width, HEIGHT - 64], fill=theme["accent"], width=4)

    return img


def generate_carousel_pdf(
    slides_data: List[Dict[str, Any]],
    author_name: str = "Dharmik Shingala",
    author_title: str = "Content Strategist & Enterprise Systems Practitioner",
    theme_name: str = "dark_slate",
) -> bytes:
    """
    Generates a multi-page PDF document completely in-memory using Pillow.
    Zero cloud dependencies, zero external network requests.
    """
    if not isinstance(slides_data, list):
        raise TypeError("slides_data must be a list of slide dictionaries")

    total = len(slides_data)
    if total == 0:
        raise ValueError("slides_data must contain at least 1 slide")
    if total > MAX_CAROUSEL_SLIDES:
        raise ValueError(f"Too many slides: maximum allowed is {MAX_CAROUSEL_SLIDES}")

    images = []
    for idx, s in enumerate(slides_data):
        if not isinstance(s, dict):
            raise TypeError(f"Slide item at index {idx} must be a dictionary")

        is_cov = (idx == 0)
        is_last = (idx == total - 1)
        img = render_slide(
            slide_index=idx,
            total_slides=total,
            title=str(s.get("title", f"Slide {idx + 1}")),
            body=str(s.get("body", "")),
            author_name=author_name,
            author_title=author_title,
            theme_name=theme_name,
            is_cover=is_cov,
            is_cta=is_last and total > 1,
        )
        images.append(img)

    # Save to in-memory PDF buffer
    pdf_buffer = io.BytesIO()
    if len(images) == 1:
        images[0].save(pdf_buffer, "PDF", resolution=100.0)
    else:
        images[0].save(pdf_buffer, "PDF", resolution=100.0, save_all=True, append_images=images[1:])

    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()
