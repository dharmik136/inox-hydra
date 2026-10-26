"""
What kind of post it was: text, image, document, video, poll, article,
newsletter or repost, or unknown.
=========================================================================

own_posts had no column for it (migration 28 adds own_posts.format), so the
one comparison the creator most often asks for, "do my document posts do
better than my image posts", could not be made at all. The format comes from
evidence the studio already receives: the archive's media and shared-link
fields on each post, and the markers a card reader sees on the creator's
activity page.

Neither is verified against a 2026 page or a real export (the capture
report's gaps table), so the rule is that only a marker which says what the
post carries names a format, and everything else is "unknown". A post with
no media and no shared link could be a text post, a poll or an event, and
nothing here guesses which; "text" is named only by a reader that says so.
A comparison then sets unknown posts aside rather than counting them on
either side (contrast_engine.py).

Strict Invariants:
- Zero em-dashes.
- Unknown is stored as "unknown", never guessed.
- A known format is never overwritten: the first evidence names it.
- This module imports no other studio module.
"""

import re
from typing import Any, Iterable, Optional

UNKNOWN = "unknown"
# "document" covers LinkedIn's carousels, which are uploaded documents.
FORMATS = ("text", "image", "document", "video", "poll", "article", "newsletter", "repost")
LABELS = {
    "text": "Text posts",
    "image": "Posts with an image",
    "document": "Document or carousel posts",
    "video": "Video posts",
    "poll": "Polls",
    "article": "Posts carrying a LinkedIn article",
    "newsletter": "Posts carrying a newsletter edition",
    "repost": "Reposts with your own words",
}

# The archive's MediaUrl, by what its address says it is. Unverified against
# a real export: an address matching none of these is unknown.
_MEDIA = (
    ("document", re.compile(r"/document/|\.(pdf|pptx?|docx?|key)(\?|$)", re.IGNORECASE)),
    ("video", re.compile(r"/vid/|/video/|/playlist/|\.(mp4|mov|m4v|webm)(\?|$)", re.IGNORECASE)),
    ("image", re.compile(r"/image/|\.(jpe?g|png|gif|webp)(\?|$)", re.IGNORECASE)),
)
# The archive's SharedUrl: what the post carried that someone wrote. An
# address outside LinkedIn is a link, which is not one of the formats here.
_SHARED = (
    ("article", re.compile(r"^https?://(www\.)?linkedin\.com/pulse/", re.IGNORECASE)),
    ("newsletter", re.compile(r"^https?://(www\.)?linkedin\.com/newsletters/", re.IGNORECASE)),
    ("repost", re.compile(r"^https?://(www\.)?linkedin\.com/(feed/update/|posts/)|urn:li:(activity|share|ugcPost):",
                          re.IGNORECASE)),
)


def _first(rules, value: str) -> Optional[str]:
    for name, pattern in rules:
        if pattern.search(value):
            return name
    return None


def from_archive(media_url: Any, shared_url: Any) -> str:
    """
    A post's format from its row in the archive's Shares file, or unknown.

    The media decides when it names one; then the shared link. Neither field
    present says nothing either way.
    """
    media = str(media_url or "").strip()
    shared = str(shared_url or "").strip()
    if media:
        found = _first(_MEDIA, media)
        if found:
            return found
    if shared:
        found = _first(_SHARED, shared)
        if found:
            return found
    return UNKNOWN


def from_markers(markers: Optional[Iterable[Any]]) -> str:
    """
    A post's format from the markers a card reader saw on it, or unknown.

    The contract for the activity page's card reader: it sends the format
    words it found ("image", "document", ...). One format named, however
    often, is that format; none, a word that is not a format, or two that
    disagree, is unknown.
    """
    named = {str(m).strip().lower() for m in (markers or []) if str(m).strip().lower() in FORMATS}
    return named.pop() if len(named) == 1 else UNKNOWN


def record(conn, activity_urn: str, found: str) -> bool:
    """
    Stores a post's format when it was unknown. A known format is never
    overwritten, so a later, vaguer reading cannot erase it, and removing an
    archive import leaves it as the import's other fills are left.
    """
    if found not in FORMATS:
        return False
    cursor = conn.execute("UPDATE own_posts SET format = ? WHERE activity_urn = ? AND format = ?",
                          (found, activity_urn, UNKNOWN))
    return bool(cursor.rowcount)
