"""
Photos and voice notes in the collection box, in a browser.
==========================================================

Phase 3 of the Telegram bot, item 4. A photo is shown with words that say
whose it is, a voice note has a player, each says it is kept as it is and
never read, and Add to your media library puts a photo where a post's images
are kept; axe in both themes. Against a studio in a throwaway home.

Strict Invariants:
- Zero em-dashes.
"""

import io
import os
import sys
import uuid

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

if not os.path.isfile(os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")):
    pytest.skip("studio/frontend_next is not built in this checkout", allow_module_level=True)

from test_collection_writing_ui import LEVEL, _collection  # noqa: E402
from test_qc4_t6_analytics_export_ui import _axe, browser, page, studio  # noqa: E402,F401


def _kept(kind, data, ext, caption="", **facts):
    """A file as the bot keeps one: in the profile's phone folder, listed in the collection."""
    import collection
    import phone_media

    name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(phone_media.folder(), name), "wb") as handle:
        handle.write(data)
    media = {"path": f"/assets/phone/{name}", "mime": phone_media.KINDS[kind]["mime"], "bytes": len(data), **facts}
    return collection.add(kind, caption, media=media)


def _jpeg():
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 120, 40)).save(out, format="JPEG")
    return out.getvalue()


def test_a_photo_and_a_voice_note_are_shown_kept_as_they_are(page, studio):
    from database import get_db

    photo = _kept("photo", _jpeg(), ".jpg", caption="the new studio wall", width=64, height=48)
    _kept("voice", b"OggS" + b"\x00" * 64, ".ogg", duration=7)
    _collection(page, studio)
    level = page.locator(LEVEL)
    image = level.get_by_role("img", name="Your photo: the new studio wall")
    expect(image).to_be_visible()
    assert page.evaluate("(img) => img.naturalWidth", image.element_handle()) == 64, "the photo did not load"
    expect(level.locator("audio[aria-label='Your voice note, 7 seconds']")).to_have_count(1)
    expect(level.get_by_text("KEPT AS IT IS: NEVER READ", exact=False)).to_be_visible()
    expect(level.get_by_text("KEPT AS IT IS: NEVER TRANSCRIBED", exact=False)).to_be_visible()
    assert _axe(page, LEVEL) == []

    item = level.locator("li", has_text="the new studio wall")
    item.get_by_role("button", name="Add to your media library").click()
    expect(level.get_by_text("In your media library: the Composer's Media tab lists it", exact=False)).to_be_visible()
    level.get_by_role("navigation", name="Collection by status").get_by_role("button", name="Used (1)").click()
    expect(level.get_by_text("In your media library", exact=True)).to_be_visible()
    conn = get_db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM media_assets WHERE media_type = 'image'").fetchone()[0] == 1
        assert conn.execute("SELECT status FROM collection_items WHERE id = ?", (photo["id"],)).fetchone()[0] == "used"
    finally:
        conn.close()
    assert _axe(page, LEVEL) == []
