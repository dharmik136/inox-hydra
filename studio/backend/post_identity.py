"""
Post Identity
=============
Binding a post the creator wrote to the post LinkedIn published.

Every attribution surface in this product joins on that binding, and none of
them have ever worked, because nothing recorded it. lead_interactions.post_id is
populated on 0 of 842 rows in the install this was written for, and post_urn on
336, all of which hold one of two test fixtures and join to nothing.

The chain has three links:

  1. The creator injects a draft into LinkedIn's composer. The studio caused
     that event, so it can record it: a posts row with a fingerprint of the text
     and a timestamp. This is bookkeeping, not observation.
  2. The creator later opens their own post. The URL contains the activity URN,
     and the page contains the text. If the text matches an armed fingerprint,
     the URN belongs to that row.
  3. Engagers captured from that page carry the URN.

Link 2 is the only one that reads LinkedIn, and it reads a page the creator
opened themselves, from location.pathname rather than from markup. No request is
made, and nothing depends on a CSS class that LinkedIn can rename.

The fingerprint deliberately does not try to be exact. LinkedIn rewrites
whitespace, converts some characters and may append nothing at all, so a hash of
the raw text would never match. What survives is the sequence of word characters
in the opening of the post, which is enough to tell one of a creator's own
drafts from another.
"""

import hashlib
import re
from typing import Optional

# How much of the opening to fingerprint. Long enough that two drafts on the
# same topic do not collide, short enough to survive a truncated render.
FINGERPRINT_CHARS = 140

# A LinkedIn activity URN as it appears in a post permalink.
ACTIVITY_URN_PATTERN = re.compile(r"urn:li:(?:activity|share|ugcPost):\d+")

_NON_WORD = re.compile(r"[^0-9a-z]+")


def normalize_for_fingerprint(text: str) -> str:
    """
    Reduce post text to what survives a round trip through LinkedIn.

    Case, punctuation, emoji, the bold unicode letterforms this studio's
    formatter emits, and every kind of whitespace are all discarded. What is
    left is the lowercase alphanumeric spine of the text.
    """
    if not text:
        return ""
    # Unbold BEFORE folding case. The mathematical alphanumeric block has no
    # case mapping, so casefold leaves it alone; mapping it back to ASCII
    # afterwards yields capitals, which the non-word filter would then strip.
    # This studio's own formatter emits those letterforms, so getting the order
    # wrong means a post injected from the studio never matches itself.
    plain = "".join(_unbold(ch) for ch in text)
    return _NON_WORD.sub("", plain.casefold())


def _unbold(ch: str) -> str:
    """Map a mathematical alphanumeric codepoint back to its ASCII equivalent."""
    o = ord(ch)
    # Bold, italic, bold-italic, script, fraktur, sans and monospace letters.
    for start, base in (
        (0x1D400, "A"), (0x1D434, "A"), (0x1D468, "A"), (0x1D49C, "A"),
        (0x1D504, "A"), (0x1D5A0, "A"), (0x1D5D4, "A"), (0x1D608, "A"),
        (0x1D63C, "A"), (0x1D670, "A"),
    ):
        if start <= o < start + 26:
            return chr(ord(base) + o - start)
        if start + 26 <= o < start + 52:
            return chr(ord("a") + o - start - 26)
    if 0x1D7CE <= o <= 0x1D7FF:  # bold and sans digits
        return str((o - 0x1D7CE) % 10)
    return ch


def content_fingerprint(text: str) -> Optional[str]:
    """
    A stable short identifier for the opening of a piece of post text.

    Formatted "<length>:<hash>", because the length is needed to compare it
    against a candidate. A fingerprint that hashed the whole normalized text
    would not match once LinkedIn or the creator appended anything: a post whose
    spine is shorter than the window would have trailing hashtags fall inside
    the hashed region, and the same post would then fail to match itself.
    Carrying the length lets a comparison slice the candidate to exactly the
    span that was fingerprinted.

    Returns None when there is not enough text to identify anything. A
    fingerprint of two words would match half the creator's drafts, and a wrong
    binding is worse than no binding: it would attribute one post's engagers to
    another.
    """
    opening = normalize_for_fingerprint(text)[:FINGERPRINT_CHARS]
    if len(opening) < 24:
        return None
    digest = hashlib.sha256(opening.encode("utf-8")).hexdigest()[:32]
    return f"{len(opening)}:{digest}"


def fingerprint_matches(candidate_text: str, fingerprint: str) -> bool:
    """
    True when a page's post text opens with the fingerprinted span.

    A post rendered on its permalink carries what the creator wrote, plus
    whatever they or LinkedIn added after it. Comparing openings rather than
    whole texts is what makes the binding survive an edit that appends.
    """
    if not fingerprint or ":" not in fingerprint:
        return False
    length_part, _, digest = fingerprint.partition(":")
    try:
        length = int(length_part)
    except ValueError:
        return False

    candidate = normalize_for_fingerprint(candidate_text)
    if len(candidate) < length:
        return False
    opening = candidate[:length]
    return hashlib.sha256(opening.encode("utf-8")).hexdigest()[:32] == digest


def extract_activity_urn(url_or_path: str) -> Optional[str]:
    """
    Pull the activity URN out of a post permalink.

    LinkedIn writes these three ways:

        /feed/update/urn:li:activity:7504139397143883776/
        /feed/update/urn:li:share:7504139397143883776/
        /posts/someone_slug-activity-7504139397143883776-AbCd

    The first two carry the URN literally. The third carries the numeric id
    after "activity-", which is the same number.
    """
    if not url_or_path:
        return None

    found = ACTIVITY_URN_PATTERN.search(url_or_path)
    if found:
        return found.group(0)

    slug = re.search(r"-activity-(\d{6,})", url_or_path)
    if slug:
        return f"urn:li:activity:{slug.group(1)}"

    return None
