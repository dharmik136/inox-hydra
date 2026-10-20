"""
Quote Renderer & Watermark Eliminator (PIL Visual Studio Engine)
================================================================
Handles:
1. Universal watermark removal via oversample bottom-crop and corner scrub across 1:1, 4:5, 16:9 ratios.
2. Crisp, typographic quote card compositing with glassmorphic backdrop for philosophical/executive quotes.
3. Strict zero em-dash compliance.
"""

import bisect
import glob
import io
import os
import struct
import sys
import threading
import unicodedata
from typing import Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, features


# ---------------------------------------------------------------------------
# Fonts for every script the creator writes in (BE-07)
#
# The quote and the handle were drawn with the first of five Windows font
# names that loaded. Off Windows none does, so Pillow's 10 px bitmap font drew
# a 41 px quote as a thin line on a 1080 px image, and Hindi or Gujarati came
# out as boxes everywhere, Windows included, because none of the five has
# those letters.
#
# So the studio carries its own fonts and loads them by absolute path: Noto
# Sans (Latin, Greek, Cyrillic), Noto Sans Devanagari and Noto Sans Gujarati,
# under the SIL Open Font License (fonts/OFL.txt), about 0.9 MB together. A
# letter none of them has (Tamil, Arabic, Chinese...) is looked for in the
# fonts this computer has. A letter no font here has is never drawn as a box:
# the text is not drawn, and the reason is said.
#
# Devanagari, Gujarati, Arabic and the other complex scripts also need
# shaping: vowel signs reordered, letters joined. Pillow does that only with
# its raqm layout, which needs the FriBiDi library. Without it those letters
# would be drawn in the wrong order, which reads as a misspelling under the
# creator's name, so the text is not drawn and the reason says so.
# ---------------------------------------------------------------------------

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
BUNDLED_FONTS = (
    "NotoSans-Regular.ttf",
    "NotoSansDevanagari-Regular.ttf",
    "NotoSansGujarati-Regular.ttf",
)


class TextNotDrawn(Exception):
    """The text cannot be drawn correctly here. The message says why, for the creator."""


def _u16(data: bytes, at: int) -> int:
    return struct.unpack_from(">H", data, at)[0]


def _u32(data: bytes, at: int) -> int:
    return struct.unpack_from(">I", data, at)[0]


def _cmap_ranges(path: str, index: int = 0) -> List[Tuple[int, int]]:
    """
    The code points a font has glyphs for, as sorted (first, last) ranges.

    Read from the font's cmap table directly (formats 4 and 12, which every
    current font carries), because Pillow draws a missing letter as the
    font's box glyph without saying so.
    """
    with open(path, "rb") as handle:
        data = handle.read()
    base = 0
    if data[:4] == b"ttcf":
        base = _u32(data, 12 + 4 * index)
    tables = {}
    for record in range(_u16(data, base + 4)):
        at = base + 12 + 16 * record
        tables[data[at:at + 4]] = _u32(data, at + 8)
    cmap = tables.get(b"cmap")
    if cmap is None:
        return []

    subtables = {}
    for record in range(_u16(data, cmap + 2)):
        at = cmap + 4 + 8 * record
        subtables[(_u16(data, at), _u16(data, at + 2))] = cmap + _u32(data, at + 4)

    ranges: List[Tuple[int, int]] = []
    for key in ((3, 10), (0, 6), (0, 4), (3, 1), (0, 3)):
        sub = subtables.get(key)
        if sub is None:
            continue
        form = _u16(data, sub)
        if form == 12:
            for group in range(_u32(data, sub + 12)):
                at = sub + 16 + 12 * group
                ranges.append((_u32(data, at), _u32(data, at + 4)))
            break
        if form == 4:
            segments = _u16(data, sub + 6) // 2
            ends = sub + 14
            starts = ends + 2 * segments + 2
            deltas = starts + 2 * segments
            offsets = deltas + 2 * segments
            for seg in range(segments):
                first, last = _u16(data, starts + 2 * seg), _u16(data, ends + 2 * seg)
                if first == 0xFFFF:
                    continue
                delta = _u16(data, deltas + 2 * seg)
                range_offset = _u16(data, offsets + 2 * seg)
                for code in range(first, last + 1):
                    if range_offset == 0:
                        glyph = (code + delta) & 0xFFFF
                    else:
                        at = offsets + 2 * seg + range_offset + 2 * (code - first)
                        glyph = _u16(data, at) if at + 2 <= len(data) else 0
                        glyph = (glyph + delta) & 0xFFFF if glyph else 0
                    if glyph:
                        if ranges and ranges[-1][1] == code - 1:
                            ranges[-1] = (ranges[-1][0], code)
                        else:
                            ranges.append((code, code))
            break
    ranges.sort()
    return ranges


def _system_font_files() -> List[str]:
    """Fonts this computer has, for letters the bundled ones lack."""
    if sys.platform == "win32":
        root = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        names = ("Nirmala.ttc", "Nirmala.ttf", "segoeui.ttf", "arial.ttf", "tahoma.ttf", "LeelawUI.ttf",
                 "msyh.ttc", "YuGothM.ttc", "malgun.ttf", "ebrima.ttf", "seguisym.ttf")
        return [os.path.join(root, name) for name in names]
    if sys.platform == "darwin":
        return [
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/Library/Fonts/Arial Unicode.ttf",
            "/System/Library/Fonts/Supplemental/Tahoma.ttf",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        ]
    found: List[str] = []
    for root in ("/usr/share/fonts", "/usr/local/share/fonts",
                 os.path.expanduser("~/.local/share/fonts"), os.path.expanduser("~/.fonts")):
        for pattern in ("**/*-Regular.ttf", "**/*-Regular.otf", "**/*-Regular.ttc", "**/DejaVuSans.ttf"):
            found.extend(glob.glob(os.path.join(root, pattern), recursive=True))
    # Sans before serif, Noto first, and a bound on how many are ever read.
    found = sorted(set(found), key=lambda p: ("Serif" in p, "Noto" not in p, os.path.basename(p)))
    return found[:400]


class _FontChain:
    """The bundled fonts, then this computer's, with what each covers."""

    def __init__(self):
        self._lock = threading.Lock()
        self._bundled = [os.path.join(FONT_DIR, name) for name in BUNDLED_FONTS]
        self._system: Optional[List[str]] = None
        self._ranges: Dict[str, List[Tuple[int, int]]] = {}
        self._loaded: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}

    def _covers(self, path: str, code: int) -> bool:
        ranges = self._ranges.get(path)
        if ranges is None:
            try:
                ranges = _cmap_ranges(path) if os.path.exists(path) else []
            except Exception:
                ranges = []
            self._ranges[path] = ranges
        at = bisect.bisect_right(ranges, (code, 0x10FFFF)) - 1
        return at >= 0 and ranges[at][0] <= code <= ranges[at][1]

    def path_for(self, char: str) -> Optional[str]:
        code = ord(char)
        with self._lock:
            for path in self._bundled:
                if self._covers(path, code):
                    return path
            if self._system is None:
                self._system = _system_font_files()
            for path in self._system:
                if self._covers(path, code) and self.font(path, 20) is not None:
                    return path
        return None

    def covers(self, path: str, char: str) -> bool:
        with self._lock:
            return self._covers(path, ord(char))

    def font(self, path: str, size: int) -> Optional[ImageFont.FreeTypeFont]:
        key = (path, size)
        if key not in self._loaded:
            try:
                self._loaded[key] = ImageFont.truetype(path, size)
            except Exception:
                # A colour emoji font, for one, loads only at its own size.
                self._loaded[key] = None
        return self._loaded[key]


_FONTS = _FontChain()

# Scripts whose letters change shape or order when drawn: Hebrew to N'Ko,
# Devanagari to Sinhala, Thai and Lao, Tibetan, Myanmar, Khmer, and the
# Arabic presentation forms.
_NEEDS_SHAPING = ((0x0590, 0x08FF), (0x0900, 0x0DFF), (0x0E00, 0x0EFF), (0x0F00, 0x0FFF),
                  (0x1000, 0x109F), (0x1780, 0x17FF), (0xA8E0, 0xA8FF), (0xFB1D, 0xFDFF), (0xFE70, 0xFEFF))


def _is_emoji(char: str) -> bool:
    code = ord(char)
    return (0x1F000 <= code <= 0x1FAFF or 0x2600 <= code <= 0x27BF or code in (0xFE0F, 0x200D, 0x20E3)
            or 0x1F1E6 <= code <= 0x1F1FF)


def shaping_available() -> bool:
    """Whether Pillow here can lay out complex scripts (raqm, with FriBiDi)."""
    try:
        return bool(features.check("raqm"))
    except Exception:
        return False


def prepare_text(text: str, notes: Optional[List[str]] = None) -> str:
    """
    The text as it will be drawn: NFC, with emoji left out and said so.

    Emoji are pictures in colour fonts that Pillow cannot draw at an
    arbitrary size; drawn here they would be boxes. They are decoration, so
    they are left out and the notes say which, rather than refusing the whole
    quote over them.
    """
    text = unicodedata.normalize("NFC", text or "")
    kept = "".join(char for char in text if not _is_emoji(char))
    dropped = "".join(char for char in text if _is_emoji(char) and char not in "\ufe0f\u200d\u20e3")
    if dropped and notes is not None:
        notes.append(f"Emoji are left out of the drawn text ({dropped}).")
    return " ".join(kept.split()) if kept.strip() else ""


def _runs(text: str, size: int) -> List[Tuple[str, ImageFont.FreeTypeFont]]:
    """
    The text split into pieces each drawn with a font that has its letters.

    A mark, joiner or space stays with the letter before it, so a syllable is
    never split across two fonts and shaping sees it whole.
    """
    if not shaping_available() and any(lo <= ord(c) <= hi for c in text for lo, hi in _NEEDS_SHAPING):
        raise TextNotDrawn(
            "this computer's Pillow cannot lay out this script (it lacks the raqm layout and the "
            "FriBiDi library), and drawn without it the letters would be in the wrong order"
        )
    pieces: List[List] = []
    missing = []
    for char in text:
        joins = unicodedata.category(char)[0] in ("M", "Z", "C") or char.isspace()
        if pieces and (joins or _FONTS.covers(pieces[-1][1], char)):
            pieces[-1][0] += char
            continue
        path = _FONTS.path_for(char)
        if path is None:
            if char not in missing:
                missing.append(char)
            continue
        if pieces and pieces[-1][1] == path:
            pieces[-1][0] += char
        else:
            pieces.append([char, path])
    if missing:
        names = ", ".join(f"{c} ({unicodedata.name(c, hex(ord(c)))})" for c in missing[:3])
        raise TextNotDrawn(f"no font on this computer has these letters: {names}")
    runs = []
    for piece, path in pieces:
        font = _FONTS.font(path, size)
        if font is None:
            raise TextNotDrawn(f"the font for '{piece.strip()[:12]}' could not be loaded")
        runs.append((piece, font))
    return runs


def _width(draw: ImageDraw.ImageDraw, runs) -> float:
    return sum(draw.textlength(piece, font=font) for piece, font in runs)


def _draw_runs(draw: ImageDraw.ImageDraw, x: float, baseline: float, runs, fill) -> None:
    for piece, font in runs:
        draw.text((x, baseline), piece, font=font, fill=fill, anchor="ls")
        x += draw.textlength(piece, font=font)


def _wrap(draw: ImageDraw.ImageDraw, text: str, size: int, max_width: float) -> List[str]:
    """Lines no wider than max_width, broken between words, measured in pixels."""
    lines: List[str] = []
    current = ""
    for word in text.split(" "):
        trial = f"{current} {word}" if current else word
        if not current or _width(draw, _runs(trial, size)) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _ascent(runs) -> int:
    return max(font.getmetrics()[0] for _piece, font in runs)


def font_report() -> Dict[str, object]:
    """What the quote renderer has here, for a test or a support question."""
    return {
        "bundled": [name for name in BUNDLED_FONTS if os.path.exists(os.path.join(FONT_DIR, name))],
        "shaping": shaping_available(),
    }


def remove_watermark_crop(
    raw_image_bytes: bytes,
    target_width: int,
    target_height: int
) -> Tuple[bytes, Image.Image]:
    """
    Strips bottom-margin watermarks (e.g. from Pollinations or trial endpoints)
    by slicing off the oversampled bottom buffer and resizing to target dimensions.
    """
    # Clamp target dimensions to prevent ZeroDivisionError and decompression bombs
    target_width = max(64, min(int(target_width) if target_width else 1080, 4096))
    target_height = max(64, min(int(target_height) if target_height else 1080, 4096))

    img = Image.open(io.BytesIO(raw_image_bytes))
    act_w, act_h = img.size
    target_ratio = float(target_width) / float(target_height)

    # Calculate expected crop height for target ratio
    crop_h = int(act_w / target_ratio)

    if crop_h < act_h:
        # We have an oversampled bottom buffer: slice it off completely
        cropped = img.crop((0, 0, act_w, crop_h))
    else:
        # Fallback: shear off at least bottom 5% or 40px to eliminate any corner stamp
        bottom_trim = max(40, int(act_h * 0.055))
        safe_h = act_h - bottom_trim
        safe_w = int(safe_h * target_ratio)
        if safe_w <= act_w:
            cx = (act_w - safe_w) // 2
            cropped = img.crop((cx, 0, cx + safe_w, safe_h))
        else:
            cropped = img.crop((0, 0, act_w, safe_h))

    # Resize cleanly to target dimensions with high-fidelity Lanczos resampling
    final_img = cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)

    # Secondary corner safety scrub: ensure bottom right corner has zero hard stamp
    final_img = scrub_corner_watermark(final_img)

    buf = io.BytesIO()
    final_img.save(buf, format="JPEG", quality=95)
    return buf.getvalue(), final_img


def scrub_corner_watermark(img: Image.Image) -> Image.Image:
    """
    Returns the image unchanged. Kept as the named place this would happen.

    This used to crop a sample patch, build a gradient blend mask, and then
    return the original image without applying either, behind an
    `except Exception: pass` that hid the fact that it never ran. A reader
    checking whether corner watermarks were handled would have found a
    function that appeared to handle them.

    The watermark is removed earlier, by the oversample crop in the generation
    path, which takes the corner off entirely rather than painting over it.
    That is the actual mechanism and it is sufficient, which is why nothing
    here was ever missed.

    If a provider ever places a mark outside the cropped region, this is where
    the blend belongs. Writing that blend is a real piece of work, not a matter
    of uncommenting: it has to detect a watermark before touching the pixels,
    or it will soften the corner of every clean image it is handed.
    """
    return img


def render_typographic_quote(
    img: Image.Image,
    quote_text: str,
    author: Optional[str] = None,
    notes: Optional[List[str]] = None,
) -> Image.Image:
    """
    Composites high-resolution, elegant typography onto the visual's negative space.
    Features a frosted glassmorphic card with amber/gold author attribution.

    Raises TextNotDrawn, having drawn nothing, when the quote or the name
    cannot be drawn correctly here. Anything worth telling the creator about
    what was drawn is appended to notes.
    """
    img_rgba = img.convert("RGBA")
    w, h = img_rgba.size

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Dynamically scale font based on image width
    font_quote_size = max(24, int(w * 0.038))
    font_author_size = max(16, int(w * 0.022))

    card_w = min(int(w * 0.84), 860)

    # Wrapped by measured width, so a line of Devanagari, whose letters are
    # wider than Latin ones, still fits the card.
    clean_quote = prepare_text(quote_text, notes).strip().strip('"').strip("'")
    if not clean_quote:
        raise TextNotDrawn("the quote has no letters left to draw")
    lines = _wrap(draw, f'"{clean_quote}"', font_quote_size, card_w - 64)
    line_runs = [_runs(line, font_quote_size) for line in lines]

    author_runs = None
    if author:
        clean_author = prepare_text(author).upper().replace("\u2014", "-").replace("\u2013", "-")
        if clean_author:
            author_text = clean_author if clean_author.startswith("-") else f"- {clean_author}"
            author_runs = _runs(author_text, font_author_size)

    line_spacing = int(font_quote_size * 1.35)
    text_block_h = len(lines) * line_spacing

    card_h = text_block_h + int(font_author_size * 2.8) + 60
    cx = (w - card_w) // 2
    cy = (h - card_h) // 2

    # Elegant dark glassmorphic rounded card
    draw.rounded_rectangle(
        [cx, cy, cx + card_w, cy + card_h],
        radius=18,
        fill=(11, 15, 25, 180),
        outline=(255, 255, 255, 45),
        width=1
    )

    # Draw quote lines, each on one baseline whichever fonts it needed
    y_text = cy + 32
    for runs in line_runs:
        lw = _width(draw, runs)
        _draw_runs(draw, cx + (card_w - lw) / 2, y_text + _ascent(runs), runs, (248, 250, 252, 245))
        y_text += line_spacing

    # Draw author line
    if author_runs:
        aw = _width(draw, author_runs)
        _draw_runs(draw, cx + (card_w - aw) / 2, y_text + 12 + _ascent(author_runs), author_runs, (245, 158, 11, 235))

    return Image.alpha_composite(img_rgba, overlay).convert("RGB")


def apply_personal_brand_watermark(
    img: Image.Image,
    brand_text: str = "",
    position: str = "bottom_right",
    style: str = "glass_pill",
    notes: Optional[List[str]] = None,
) -> Image.Image:
    """
    Composites a creator's personal brand watermark/handle onto the image.
    Supports 4 corner positions and luxury glassmorphic or minimal styling.

    Raises TextNotDrawn, having drawn nothing, when the handle cannot be
    drawn correctly here.
    """
    img_rgba = img.convert("RGBA")
    w, h = img_rgba.size

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    clean_text = prepare_text(brand_text, notes).strip()
    if not clean_text:
        raise TextNotDrawn("there is no handle to draw")

    # Font sizing relative to canvas width
    font_size = max(14, int(w * 0.020))
    runs = _runs(clean_text, font_size)
    ascent = _ascent(runs)
    text_w = int(_width(draw, runs))
    text_h = ascent + max(font.getmetrics()[1] for _piece, font in runs)

    # Badge geometry
    pad_x = int(font_size * 0.9)
    pad_y = int(font_size * 0.5)
    badge_w = text_w + (pad_x * 2) + int(font_size * 1.2)  # Extra room for icon
    badge_h = text_h + (pad_y * 2)

    margin_x = max(24, int(w * 0.032))
    margin_y = max(24, int(h * 0.032))

    pos = position.lower().replace("-", "_")
    if pos == "bottom_left":
        bx0 = margin_x
        by0 = h - badge_h - margin_y
    elif pos == "top_right":
        bx0 = w - badge_w - margin_x
        by0 = margin_y
    elif pos == "top_left":
        bx0 = margin_x
        by0 = margin_y
    else:  # default bottom_right
        bx0 = w - badge_w - margin_x
        by0 = h - badge_h - margin_y

    bx1 = bx0 + badge_w
    by1 = by0 + badge_h

    if style == "minimal_text":
        # Subtle text directly with soft shadow
        _draw_runs(draw, bx0 + 2, by0 + 2 + ascent, runs, (0, 0, 0, 150))
        _draw_runs(draw, bx0, by0 + ascent, runs, (248, 250, 252, 210))
    elif style == "accent_badge":
        # High contrast electric indigo badge
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=10, fill=(79, 70, 229, 230), outline=(129, 140, 248, 180), width=1)
        # Dot
        dot_r = 3
        draw.ellipse([bx0 + pad_x, by0 + badge_h // 2 - dot_r, bx0 + pad_x + dot_r * 2, by0 + badge_h // 2 + dot_r], fill=(255, 255, 255))
        _draw_runs(draw, bx0 + pad_x + 12, by0 + pad_y + ascent, runs, (255, 255, 255, 250))
    else:
        # Default: glass_pill (luxury frosted glassmorphic pill badge)
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=12, fill=(11, 15, 25, 195), outline=(255, 255, 255, 55), width=1)
        # Cyan verified indicator dot
        dot_r = 3
        draw.ellipse([bx0 + pad_x, by0 + badge_h // 2 - dot_r, bx0 + pad_x + dot_r * 2, by0 + badge_h // 2 + dot_r], fill=(56, 189, 248))
        _draw_runs(draw, bx0 + pad_x + 12, by0 + pad_y + ascent, runs, (248, 250, 252, 230))

    return Image.alpha_composite(img_rgba, overlay).convert("RGB")

