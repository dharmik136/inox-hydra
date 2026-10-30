"""
Albums, documents and videos in Your collection, in a browser (phase 4, item 10).
================================================================================

A video plays, a document offers View (a PDF) and Download under its own
name, a file the studio cannot show is a download only, an album's photos are
shown together, and Add to your media library is offered only for what the
library takes. Axe in both themes.

docs/quality/cycle4/bot-phase4.md, item 10.

Strict Invariants:
- Zero em-dashes.
"""

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
from test_phone_media_ui import _jpeg  # noqa: E402
from test_qc4_t6_analytics_export_ui import _axe, browser, page, studio  # noqa: E402,F401


def _file(data, ext, mime, **facts):
    import phone_media

    name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(phone_media.folder(), name), "wb") as handle:
        handle.write(data)
    held = {"path": f"/assets/phone/{name}", "mime": mime, "bytes": len(data), **facts}
    if ext == ".bin":
        held["download_only"] = True
    return held


def test_documents_videos_and_albums_are_kept_as_they_are(page, studio):
    import collection

    collection.add("document", "the pricing deck", media=_file(b"%PDF-1.7 deck", ".pdf", "application/pdf",
                                                              name="Pricing deck.pdf"))
    collection.add("document", "", media=_file(b"PK\x03\x04docx", ".bin", "application/msword", name="Notes.docx"))
    collection.add("video", "a clip from the talk", media=_file(b"\x00\x00\x00\x18ftypmp42", ".mp4", "video/mp4",
                                                               name="talk.mp4", duration=12))
    album = _file(_jpeg(), ".jpg", "image/jpeg", width=64, height=48)
    album["more"] = [_file(_jpeg(), ".jpg", "image/jpeg", width=64, height=48)]
    collection.add("photo", "the workshop", media=album)
    _collection(page, studio)
    level = page.locator(LEVEL)
    expect(level.get_by_role("link", name="View Pricing deck.pdf")).to_be_visible()
    expect(level.get_by_role("link", name="Download Pricing deck.pdf")).to_be_visible()
    expect(level.get_by_role("link", name="View Notes.docx")).to_have_count(0)
    expect(level.get_by_role("link", name="Download Notes.docx")).to_be_visible()
    expect(level.get_by_text("A DOWNLOAD ONLY", exact=False)).to_be_visible()
    expect(level.locator("video[aria-label='Your video: a clip from the talk']")).to_have_count(1)
    expect(level.get_by_role("img", name="Your photo 1 of 2: the workshop")).to_be_visible()
    expect(level.get_by_role("img", name="Your photo 2 of 2: the workshop")).to_be_visible()
    assert _axe(page, LEVEL) == []

    offered = [level.locator("li", has_text=words).get_by_role("button", name="Add to your media library").count()
               for words in ("the pricing deck", "Notes.docx", "a clip from the talk", "the workshop")]
    assert offered == [1, 0, 1, 1], offered
    level.locator("li", has_text="the pricing deck").get_by_role("button", name="Add to your media library").click()
    expect(level.get_by_text("In your media library: the Composer's Media tab lists it", exact=False)).to_be_visible()
    assert _axe(page, LEVEL) == []
