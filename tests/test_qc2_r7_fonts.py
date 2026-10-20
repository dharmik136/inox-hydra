"""
Quote overlays and watermarks at their intended size, in every script. [BE-07]

The quote and the @handle were drawn with the first of five Windows font names
that loaded. Off Windows none does, so Pillow's 10 px bitmap font drew a 41 px
quote as a thin line on a 1080 px image, and Hindi or Gujarati came out as
boxes on every OS.

The studio now carries Noto Sans, Noto Sans Devanagari and Noto Sans Gujarati
(OFL) and loads them by path, so these tests mean the same on Linux, macOS and
Windows. A letter no font has, or a complex script without Pillow's shaping
library, is not drawn at all, and the reason is said; it is never a box.
"""

import io
import os
import sys
import unicodedata

import pytest
from PIL import Image, ImageDraw

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import quote_renderer  # noqa: E402
from quote_renderer import apply_personal_brand_watermark, render_typographic_quote  # noqa: E402

LATIN = "Ship the boring version first, then make it interesting."
HINDI = "पहले सरल संस्करण भेजें, फिर उसे रोचक बनाएं"
GUJARATI = "પહેલાં સરળ આવૃત્તિ મોકલો"
CARD = (11, 15, 25)


def _bright_rows(image, box=None):
    """Rows holding near-white quote pixels, inside box if given."""
    px = image.load()
    x0, y0, x1, y1 = box or (0, 0) + image.size
    return [y for y in range(y0, y1) if any(min(px[x, y]) > 200 for x in range(x0, x1, 2))]


def _first_line_height(image):
    """Height in pixels of the first run of rows holding quote glyphs."""
    rows = _bright_rows(image)
    assert rows, "nothing was drawn"
    first = [rows[0]]
    for y in rows[1:]:
        if y - first[-1] > 3:
            break
        first.append(y)
    return first[-1] - first[0] + 1


@pytest.mark.parametrize("width", [1080, 1920])
def test_the_quote_is_drawn_at_its_intended_size(width):
    """Glyphs at least 0.03 x the image width tall; the bitmap fallback drew 10 px."""
    base = Image.new("RGB", (width, 1080), CARD)
    drawn = render_typographic_quote(base, LATIN, "Sample Author")
    height = _first_line_height(drawn)
    assert height >= 0.03 * width, f"quote glyphs are {height} px on a {width} px image"


def test_the_watermark_is_drawn_at_its_intended_size():
    base = Image.new("RGB", (1080, 1080), (40, 40, 40))
    stamped = apply_personal_brand_watermark(base, "@mycreatorhandle", position="top_left", style="minimal_text")
    rows = _bright_rows(stamped, (0, 0, 540, 200))
    height = rows[-1] - rows[0] + 1
    # font size 0.020 x width = 21 px; '@' and 'y' span most of it.
    assert height >= 0.015 * 1080, f"the handle is {height} px tall"


@pytest.mark.parametrize("text", [HINDI, GUJARATI, "Hindi: पहले, Gujarati: પહેલાં"])
def test_every_letter_of_an_indic_quote_has_a_glyph(text, monkeypatch):
    """No .notdef: each piece is drawn with a font whose cmap has every letter."""
    # Which font carries a letter is the same question on every machine, but
    # _runs refuses a complex script first where Pillow has no raqm layout
    # (the python.org macOS build has none). The refusal has its own test
    # below, so here the gate is held open and the font choice is what is read.
    monkeypatch.setattr(quote_renderer, "shaping_available", lambda: True)
    runs = quote_renderer._runs(text, 41)
    assert "".join(piece for piece, _font in runs) == unicodedata.normalize("NFC", text)
    for piece, font in runs:
        ranges = quote_renderer._cmap_ranges(font.path)
        for char in piece:
            if char.isspace():
                continue
            code = ord(char)
            assert any(lo <= code <= hi for lo, hi in ranges), (
                f"{char!r} (U+{code:04X}) is drawn with {os.path.basename(font.path)}, which has no glyph for it"
            )


@pytest.mark.skipif(not quote_renderer.shaping_available(), reason="Pillow here has no raqm layout")
@pytest.mark.parametrize("text", [HINDI, GUJARATI])
def test_an_indic_quote_and_name_are_drawn(text):
    base = Image.new("RGB", (1080, 1080), CARD)
    drawn = render_typographic_quote(base, text, "धर्मिक")
    assert _first_line_height(drawn) >= 0.03 * 1080


@pytest.mark.skipif(not quote_renderer.shaping_available(), reason="Pillow here has no raqm layout")
def test_the_vowel_sign_i_is_drawn_before_its_consonant():
    """
    Shaped, not just present: in "कि" the sign ि is drawn to the left of क.

    Drawn without shaping, the sign lands after the letter, which reads as a
    misspelling. Measured as where the ink starts: shaped, the sign's stem is
    left of where क alone starts.
    """
    font = quote_renderer._runs("क", 80)[0][1]
    canvas = Image.new("L", (300, 200), 0)
    draw = ImageDraw.Draw(canvas)
    draw.text((100, 150), "क", font=font, fill=255, anchor="ls")
    alone = canvas.getbbox()[0]
    canvas = Image.new("L", (300, 200), 0)
    draw = ImageDraw.Draw(canvas)
    draw.text((100, 150), "कि", font=font, fill=255, anchor="ls")
    shaped = canvas.getbbox()[0]
    assert shaped <= alone, "the vowel sign was drawn after the consonant"


def test_without_shaping_a_hindi_quote_is_refused_not_misdrawn(monkeypatch):
    monkeypatch.setattr(quote_renderer, "shaping_available", lambda: False)
    base = Image.new("RGB", (1080, 1080), CARD)
    with pytest.raises(quote_renderer.TextNotDrawn) as refused:
        render_typographic_quote(base, HINDI, None)
    assert "FriBiDi" in str(refused.value)
    # Latin needs no shaping, so it still draws.
    assert _first_line_height(render_typographic_quote(base, LATIN, None)) >= 32


def test_a_letter_no_font_has_is_refused_by_name(monkeypatch):
    # Tamil needs shaping too, and without raqm that refusal comes first and
    # says something else true. The letter is what is being tested, so the
    # shaping gate is held open, as it is on a machine that has raqm.
    monkeypatch.setattr(quote_renderer, "shaping_available", lambda: True)
    monkeypatch.setattr(quote_renderer, "_FONTS", quote_renderer._FontChain())
    monkeypatch.setattr(quote_renderer, "_system_font_files", lambda: [])
    base = Image.new("RGB", (1080, 1080), CARD)
    with pytest.raises(quote_renderer.TextNotDrawn) as refused:
        render_typographic_quote(base, "வணக்கம் Tamil", None)
    assert "TAMIL LETTER" in str(refused.value)


def test_emoji_are_left_out_and_said_so():
    notes = []
    base = Image.new("RGB", (1080, 1080), CARD)
    render_typographic_quote(base, "Ship it 🚀 today", None, notes=notes)
    assert notes and "🚀" in notes[0]


def test_the_fonts_ship_with_their_licence():
    font_dir = os.path.join(BACKEND, "fonts")
    total = 0
    for name in quote_renderer.BUNDLED_FONTS:
        path = os.path.join(font_dir, name)
        assert os.path.exists(path), name
        total += os.path.getsize(path)
    assert total < 1.2 * 1024 * 1024, f"the bundled fonts grew to {total} bytes"
    licence = io.open(os.path.join(font_dir, "OFL.txt"), encoding="utf-8").read()
    assert "SIL OPEN FONT LICENSE Version 1.1" in licence

    pyproject = io.open(os.path.join(REPO_ROOT, "pyproject.toml"), encoding="utf-8").read()
    assert '"fonts/*.ttf"' in pyproject and '"fonts/OFL.txt"' in pyproject, (
        "a wheel would ship without the fonts"
    )


def test_no_font_is_looked_up_by_a_bare_windows_name():
    source = io.open(os.path.join(BACKEND, "quote_renderer.py"), encoding="utf-8").read()
    for name in ('"georgia.ttf"', '"times.ttf"', '"calibri.ttf"', "load_default("):
        assert name not in source, f"{name} is back"
