"""
A slide shows the text it was given, or says what it could not show.
====================================================================

The content sits in a foreignObject 900px wide and 850px tall on 4:5, 580px
on 1:1, at a fixed 32px body size with 1.5 line height. A foreignObject clips.

Measured against the old fixed sizing:

    a 2000 character body on 4:5    needed 1878px of a 850px box
    the same body on 1:1           needed 1878px of a 580px box

MAX_SLIDE_BODY_LENGTH permits 2000 characters, so the engine accepted text it
had no room for and cut the remainder off the rendered slide and the exported
deck without a word. The creator found out from the PDF, or from the post.

The type now scales down to fit, and when even the smallest size cannot hold
the text the deck carries a warning naming the slide and how many characters
are over.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from carousel_engine import (BODY_FONT_MAX, BODY_FONT_MIN, BODY_LINE_RATIO,
                             MAX_SLIDE_BODY_LENGTH, TITLE_FONT_MAX,
                             CarouselDeckEngine, carousel_engine)

SHORT_BODY = "Cut the review queue.\nShip behind a flag.\nMeasure the rollout."
LONG_BODY = (
    "The creator pastes an entire section of an essay into one slide and "
    "expects every word of it to appear on the exported deck. " * 20
)[:MAX_SLIDE_BODY_LENGTH]

TITLE = "Three ways to ship faster"


def _slide(body, title=TITLE):
    return {"title": title, "body": body}


@pytest.mark.parametrize("aspect_ratio", ["4:5", "1:1"])
def test_the_longest_permitted_body_does_not_silently_overrun_its_box(aspect_ratio):
    """
    Either it fits after scaling, or the fit reports that it does not. What
    must not happen is a fit that claims success while measuring taller than
    the box.
    """
    fit = CarouselDeckEngine.fit_slide_text(TITLE, LONG_BODY, aspect_ratio)

    if not fit["overflow"]:
        assert fit["estimated_height"] <= fit["box_height"], (
            f"the slide reported a clean fit at {fit['estimated_height']}px in "
            f"a {fit['box_height']}px box"
        )
    else:
        assert fit["excess_chars"] > 0, "an overflow was reported with nothing over"


def test_a_short_slide_keeps_the_full_display_size():
    """
    The fix must not shrink everything. A slide with room to spare is still
    set at the sizes the design calls for.
    """
    fit = CarouselDeckEngine.fit_slide_text(TITLE, SHORT_BODY, "4:5")

    assert fit["title_font_size"] == TITLE_FONT_MAX
    assert fit["body_font_size"] == BODY_FONT_MAX
    assert fit["overflow"] is False


def test_a_long_slide_is_set_smaller_than_a_short_one():
    short = CarouselDeckEngine.fit_slide_text(TITLE, SHORT_BODY, "4:5")
    long = CarouselDeckEngine.fit_slide_text(TITLE, LONG_BODY, "4:5")

    assert long["body_font_size"] < short["body_font_size"], (
        "the type did not scale at all, so the long slide is still clipped"
    )
    assert long["body_font_size"] >= BODY_FONT_MIN, (
        "the type scaled past its floor, which trades a clipped slide for an "
        "unreadable one"
    )


def test_the_square_format_warns_where_the_tall_one_fits():
    """
    A 1:1 slide has 580px of content height against 850px on 4:5. The same
    body is fine on one and does not fit on the other, and the creator is the
    one who has to know that.
    """
    tall = carousel_engine.compile_carousel_deck([_slide(LONG_BODY)], aspect_ratio="4:5")
    square = carousel_engine.compile_carousel_deck([_slide(LONG_BODY)], aspect_ratio="1:1")

    assert tall["status"] == "success" and square["status"] == "success"
    assert square["warnings"], (
        "2000 characters were compiled onto a square slide with 580px of room "
        "and nothing was said"
    )

    warning = square["warnings"][0]
    assert warning["slide_index"] == 0
    assert warning["excess_chars"] > 0
    assert "cut off" in warning["message"]


def test_a_deck_that_fits_carries_no_warnings():
    """Guard against a warning that fires on every deck and is then ignored."""
    deck = carousel_engine.compile_carousel_deck(
        [_slide(SHORT_BODY), _slide(SHORT_BODY)], aspect_ratio="4:5"
    )
    assert deck["warnings"] == []


def test_the_rendered_svg_uses_the_fitted_size():
    """
    The measurement is worth nothing if the SVG still hard codes 32px.
    """
    deck = carousel_engine.compile_carousel_deck([_slide(LONG_BODY)], aspect_ratio="4:5")
    svg = deck["slides"][0]["svg"]
    fitted = deck["slides"][0]["fit"]["body_font_size"]

    assert f"font-size: {fitted}px" in svg
    assert "font-size: 32px" not in svg, "the body is still set at the fixed size"


def test_an_unbroken_url_is_broken_rather_than_run_past_the_edge():
    """
    A word longer than the line has nowhere to wrap. Without break-word it
    runs horizontally out of the box instead of down it, and the line count
    that assumed it wrapped is wrong too.
    """
    url = "https://example.com/" + ("path" * 60)
    fit = CarouselDeckEngine.fit_slide_text("", url, "4:5")

    box = CarouselDeckEngine.content_box("4:5")
    chars_per_line = box["width"] / (fit["body_font_size"] * 0.52)
    assert fit["body_lines"] >= len(url) / chars_per_line, (
        "the long run was counted as a single line, so its height was under "
        "measured"
    )

    svg = carousel_engine.compile_carousel_deck([_slide(url)])["slides"][0]["svg"]
    assert "break-word" in svg


def test_blank_lines_are_counted_as_height():
    """
    white-space: pre-wrap keeps them, so they occupy a line each. Dropping
    them from the count under measures exactly the posts creators write, which
    are mostly one line paragraphs.
    """
    spaced = "\n\n".join(["A single line."] * 12)
    packed = "\n".join(["A single line."] * 12)

    spaced_fit = CarouselDeckEngine.fit_slide_text("", spaced, "4:5")
    packed_fit = CarouselDeckEngine.fit_slide_text("", packed, "4:5")

    assert spaced_fit["body_lines"] > packed_fit["body_lines"]


def test_empty_and_missing_text_do_not_break_the_fit():
    for body in (None, "", "   "):
        fit = CarouselDeckEngine.fit_slide_text(None, body, "4:5")
        assert fit["overflow"] is False
        assert fit["estimated_height"] >= 0

    deck = carousel_engine.compile_carousel_deck([{}])
    assert deck["status"] == "success"
    assert deck["warnings"] == []
