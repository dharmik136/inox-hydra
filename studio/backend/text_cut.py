"""
Cutting text to a length without cutting a character in half.

Python slices by code point, so a slice never splits a UTF-16 surrogate pair,
but what a reader sees as one character is often several code points: an
emoji with a skin tone or a variation selector, a family joined by zero-width
joiners, a flag (two regional indicators), a keycap, or a Devanagari or
Gujarati letter with its vowel sign or virama. A plain `text[:n]` that lands
inside one of those leaves a stray modifier, a lone regional indicator shown
as a letter in a box, or a dangling half-letter.

clip(text, n) returns at most n code points and backs off to the start of the
character the cut would have split. Kept dependency free: the rules below
cover the sequences creators' audiences actually write, not the whole of
Unicode's segmentation algorithm.
"""

import unicodedata
from typing import Optional

_ZWJ = "‍"


def _extends(ch: str) -> bool:
    """True for a code point that belongs to the character before it."""
    code = ord(ch)
    if ch == _ZWJ or ch == "⃣":  # joiner, combining keycap
        return True
    if 0xFE00 <= code <= 0xFE0F or 0xE0100 <= code <= 0xE01EF:  # variation selectors
        return True
    if 0x1F3FB <= code <= 0x1F3FF:  # skin tone modifiers
        return True
    if 0xE0020 <= code <= 0xE007F:  # tag characters (subdivision flags)
        return True
    return unicodedata.category(ch) in ("Mn", "Mc", "Me")


def _joins_next(ch: str) -> bool:
    """True for a code point after which the next one is part of the same character."""
    return ch == _ZWJ or unicodedata.combining(ch) == 9  # a virama joins a conjunct


def _regional(ch: str) -> bool:
    return 0x1F1E6 <= ord(ch) <= 0x1F1FF


def _splits_flag(text: str, i: int) -> bool:
    """True when position i falls between the two halves of a flag."""
    if not (_regional(text[i]) and _regional(text[i - 1])):
        return False
    run = 0
    j = i - 1
    while j >= 0 and _regional(text[j]):
        run += 1
        j -= 1
    return run % 2 == 1


def clip(text: Optional[str], limit: int) -> Optional[str]:
    """At most `limit` code points of `text`, ending on a whole character."""
    if text is None or limit is None:
        return text
    if limit <= 0:
        return text[:0]
    if len(text) <= limit:
        return text
    i = limit
    while i > 0 and (_extends(text[i]) or _joins_next(text[i - 1]) or _splits_flag(text, i)):
        i -= 1
    # A run of nothing but joined marks has no boundary to back off to; the
    # plain cut is the best there is.
    return text[:i] if i > 0 else text[:limit]
