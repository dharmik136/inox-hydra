"""
Decorating text does not change what it measures.
=================================================

to_strikethrough and to_underline work by inserting a combining mark after
every character. Those marks are separate code points, and \\w does not match
them, so the word counter counted each decorated letter as its own word and
len() doubled.

Measured before the fix:

    a 220 word post through to_underline      reported 880 words
    an 80 character hook through strikethrough reported 160 pre-fold chars,
                                               flipping mobile_safe to False

Both endpoints ship. A creator who struck a line through and then asked for an
audit was told their fold-safe hook would truncate.

Only the combining-mark formatters do this. Mathematical bold maps each letter
to a single code point and measures correctly with no help, which is why the
fix strips marks rather than trying to undo every formatter.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from formatters import (analyze_hook, calculate_dwell_metrics,
                        clean_text_formatting, to_sans_bold, to_strikethrough,
                        to_underline)

EN_DASH = chr(0x2013)
EM_DASH = chr(0x2014)

BODY = " ".join(["word"] * 220)
HOOK = "This is an opening line that should sit comfortably under the mobile fold limit."


@pytest.mark.parametrize("decorate", [to_strikethrough, to_underline, to_sans_bold])
def test_word_count_is_unchanged_by_decoration(decorate):
    plain = calculate_dwell_metrics(BODY)["word_count"]
    decorated = calculate_dwell_metrics(decorate(BODY))["word_count"]

    assert decorated == plain, (
        f"{decorate.__name__} changed the word count from {plain} to "
        f"{decorated}. Every reading time and dwell verdict derives from it."
    )


@pytest.mark.parametrize("decorate", [to_strikethrough, to_underline, to_sans_bold])
def test_fold_safety_is_unchanged_by_decoration(decorate):
    """
    The fold verdict is the product's central claim. It must not depend on
    whether the creator struck a line through part of the text.
    """
    plain = analyze_hook(HOOK)
    decorated = analyze_hook(decorate(HOOK))

    assert decorated["pre_fold_chars"] == plain["pre_fold_chars"], (
        f"{decorate.__name__} changed pre_fold_chars from "
        f"{plain['pre_fold_chars']} to {decorated['pre_fold_chars']}"
    )
    assert decorated["mobile_safe"] == plain["mobile_safe"], (
        f"{decorate.__name__} flipped mobile_safe, so the studio would warn "
        f"about a hook that fits"
    )


def test_the_decoration_itself_still_works():
    """The fix strips marks for measurement only, never from the output."""
    struck = to_strikethrough("Hello")
    assert struck != "Hello", "the strikethrough stopped producing marks"
    assert len(struck) > len("Hello")


def test_a_genuinely_long_hook_is_still_flagged():
    """Guard against the fix making everything look fold safe."""
    long_hook = "x" * 400
    assert analyze_hook(long_hook)["mobile_safe"] is False


def test_a_numeric_range_survives_cleaning():
    """
    An en-dash between numbers is a range. Turning it into a comma turns
    "2021-2024" into a list of two years, which says something different.
    """
    cleaned = clean_text_formatting("Revenue grew 2021" + EN_DASH + "2024")
    assert cleaned == "Revenue grew 2021-2024", cleaned

    assert clean_text_formatting("pages 10" + EN_DASH + "20") == "pages 10-20"
    assert clean_text_formatting("pages 10 " + EN_DASH + " 20") == "pages 10-20"


def test_an_en_dash_between_words_is_still_a_pause():
    """
    It does two jobs. Between words it is a pause and a comma is right, which
    is why mapping every en-dash the same way got one case wrong whichever way
    it was mapped.
    """
    cleaned = clean_text_formatting("first principles" + EN_DASH + "always")
    assert cleaned == "first principles, always", cleaned


def test_the_em_dash_rule_is_untouched():
    """The anti-slop invariant. An em-dash is always a pause."""
    assert EM_DASH not in clean_text_formatting("A" + EM_DASH + "B")
    assert clean_text_formatting("A" + EM_DASH + "B") == "A, B"


def test_metrics_survive_an_empty_or_null_input():
    for value in (None, "", "   "):
        assert calculate_dwell_metrics(value)["word_count"] == 0
        assert analyze_hook(value)["char_count"] == 0
