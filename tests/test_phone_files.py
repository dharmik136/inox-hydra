"""
Everything in one box: albums, documents and videos, kept as they are, never read (phase 4, item 10).
=====================================================================================================

Photos sent together (one media_group_id) arrive as one item, with the
caption as its words. Documents (a PDF or any other file) and videos (a
video, a round video message, a GIF Telegram sends as a video) are kept as
photos and voice notes are: getFile, then the file, each through the egress
check under `ingress` and counted without the token, within Telegram's 20 MB
bot download limit; over it, the bot says so plainly and nothing is fetched.
The stored name's extension comes from a short list of types the studio can
show; anything else is kept as a download only, never opened in the studio's
own window. Add to your media library only for what the library takes. A
sticker, a location and a contact keep today's plain answer.

The collection's table is rebuilt to take the two new kinds (migration 42),
keeping every row, its id and the id sequence.

docs/quality/cycle4/bot-phase4.md, item 10. Against the fake Bot API.

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import sqlite3
import sys
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import migrations  # noqa: E402
import paths  # noqa: E402
import telegram_bot  # noqa: E402
from database import get_db  # noqa: E402
from test_collection_box import _items, _labels, _send  # noqa: E402
from test_telegram_bot_e2e import OWNER, STRANGER, TOKEN, _until, bot  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES
PDF = b"%PDF-1.7\n" + b"0 obj stream " * 50
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00moov" * 60
DOCX = b"PK\x03\x04" + b"word/document.xml" * 20
HTML = b"<html><script>alert(document.cookie)</script></html>"
JPEG = b"\xff\xd8\xff\xe0" + b"album" * 30


def _media(item):
    return json.loads(item["media"])


def _on_disk(path):
    return os.path.join(paths.get_assets_dir(), path[len("/assets/"):])


def _document(bot, data, name, mime, caption=None, file_id="doc-1", size=None):
    bot["fake"].add_file(file_id, data, f"documents/{file_id}.bin")
    extra = {"caption": caption} if caption else {}
    return _send(bot, None, document={"file_id": file_id, "file_unique_id": f"u{file_id}", "file_name": name,
                                      "mime_type": mime, "file_size": len(data) if size is None else size}, **extra)


def test_a_pdf_is_kept_as_it_is_with_its_name_and_never_read(bot):
    _saved(bot)
    assert _document(bot, PDF, "Pricing deck.pdf", "application/pdf", caption="the deck for Thursday") == \
        SAID["collected"]
    [item] = _items()
    assert (item["kind"], item["text"]) == ("document", "the deck for Thursday")
    media = _media(item)
    assert (media["name"], media["mime"], media["bytes"]) == ("Pricing deck.pdf", "application/pdf", len(PDF))
    assert media["path"].startswith("/assets/phone/") and media["path"].endswith(".pdf")
    with open(_on_disk(media["path"]), "rb") as handle:
        assert handle.read() == PDF
    res = bot["client"].get(media["path"])
    assert res.status_code == 200 and res.headers["content-type"].startswith("application/pdf")
    assert [c["params"]["file_id"] for c in bot["fake"].calls_of("getFile")] == ["doc-1"]


def test_any_other_file_is_kept_as_a_download_only(bot):
    _saved(bot)
    _document(bot, DOCX, "Proposal v2.docx",
              "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    _document(bot, HTML, "page.html", "text/html", file_id="doc-2")
    first, second = _items()
    for item in (first, second):
        media = _media(item)
        assert media["path"].endswith(".bin"), media
        served = bot["client"].get(media["path"])
        assert served.status_code == 200
        assert "html" not in served.headers["content-type"], "a file from the phone was served as a page"
    assert (_media(first)["name"], _media(second)["name"]) == ("Proposal v2.docx", "page.html")


def test_a_video_a_round_video_and_a_gif_are_videos(bot):
    _saved(bot)
    bot["fake"].add_file("vid-1", MP4, "videos/file_1.mp4")
    bot["fake"].add_file("note-1", MP4, "video_notes/file_2.mp4")
    bot["fake"].add_file("gif-1", MP4, "animations/file_3.mp4")
    _send(bot, None, video={"file_id": "vid-1", "file_unique_id": "v1", "width": 1280, "height": 720,
                            "duration": 12, "mime_type": "video/mp4", "file_name": "standup.mp4",
                            "file_size": len(MP4)}, caption="a clip from the talk")
    _send(bot, None, video_note={"file_id": "note-1", "file_unique_id": "n1", "length": 240, "duration": 9,
                                 "file_size": len(MP4)})
    _send(bot, None, animation={"file_id": "gif-1", "file_unique_id": "g1", "width": 320, "height": 240,
                                "duration": 3, "mime_type": "video/mp4", "file_size": len(MP4)},
          document={"file_id": "gif-1", "file_unique_id": "g1", "mime_type": "video/mp4", "file_size": len(MP4)})
    kinds = [(i["kind"], _media(i)["path"][-4:]) for i in _items()]
    assert kinds == [("video", ".mp4"), ("video", ".mp4"), ("video", ".mp4")], kinds
    first = _media(_items()[0])
    assert (first["duration"], first["width"], first["height"], first["name"]) == (12, 1280, 720, "standup.mp4")
    assert _items()[0]["text"] == "a clip from the talk"


def test_a_file_over_twenty_megabytes_is_refused_before_it_is_fetched(bot):
    _saved(bot)
    answer = _document(bot, PDF, "huge.pdf", "application/pdf", size=21 * 1024 * 1024)
    assert answer == SAID["too_big"]
    assert bot["fake"].calls_of("getFile") == [] and _items() == []


def test_photos_sent_together_arrive_as_one_item_with_the_caption(bot):
    _saved(bot)
    for n in range(3):
        bot["fake"].add_file(f"al-{n}", JPEG + bytes([n]), f"photos/album_{n}.jpg")
    group = "13579246801357924"
    sent_before = len(_texts(bot))
    for n in range(3):
        extra = {"caption": "the workshop, three angles"} if n == 1 else {}
        bot["fake"].push(OWNER, None, media_group_id=group, photo=[{
            "file_id": f"al-{n}", "file_unique_id": f"a{n}", "width": 800, "height": 600,
            "file_size": len(JPEG) + 1}], **extra)
    assert _until(lambda: bot["fake"].waiting() == [] and len(_items()) == 1 and len(
        [1] + (_media(_items()[0]).get("more") or [])) == 3), _items()
    [item] = _items()
    assert (item["kind"], item["text"]) == ("photo", "the workshop, three angles")
    files = [_media(item)["path"]] + [f["path"] for f in _media(item)["more"]]
    assert len(set(files)) == 3 and all(os.path.exists(_on_disk(p)) for p in files)
    time.sleep(0.3)
    assert len(_texts(bot)) == sent_before + 1, "an album was answered once for each of its photos"


def test_undo_takes_every_file_of_an_album(bot):
    import collection
    _saved(bot)
    for n in range(2):
        bot["fake"].add_file(f"al-{n}", JPEG + bytes([n]), f"photos/album_{n}.jpg")
        bot["fake"].push(OWNER, None, media_group_id="g-2", photo=[{
            "file_id": f"al-{n}", "file_unique_id": f"a{n}", "width": 800, "height": 600, "file_size": len(JPEG) + 1}])
    assert _until(lambda: len(_items()) == 1 and len(_media(_items()[0]).get("more") or []) == 1)
    [item] = _items()
    files = [_media(item)["path"]] + [f["path"] for f in _media(item)["more"]]
    assert collection.remove(item["id"])
    assert not any(os.path.exists(_on_disk(p)) for p in files), "a file of the album was left behind"


def test_the_media_library_takes_only_what_it_takes(bot):
    _saved(bot)
    _document(bot, PDF, "deck.pdf", "application/pdf")
    _document(bot, DOCX, "notes.docx", "application/msword", file_id="doc-2")
    bot["fake"].add_file("vid-1", MP4, "videos/file_1.mp4")
    _send(bot, None, video={"file_id": "vid-1", "file_unique_id": "v1", "width": 640, "height": 360, "duration": 4,
                            "mime_type": "video/mp4", "file_size": len(MP4)})
    pdf, docx, video = _items()
    listed = {i["id"]: i for i in bot["client"].get("/api/v1/collection?status=all").json()["items"]}
    assert (listed[pdf["id"]]["media"]["library"], listed[docx["id"]]["media"]["library"],
            listed[video["id"]]["media"]["library"]) == ("carousel", None, "video")
    for item, kind in ((pdf, "carousel"), (video, "video")):
        res = bot["client"].post(f"/api/v1/collection/{item['id']}/media")
        assert res.status_code == 200, res.text
        conn = get_db()
        asset = conn.execute("SELECT media_type FROM media_assets WHERE id = (SELECT media_asset_id FROM "
                             "collection_items WHERE id = ?)", (item["id"],)).fetchone()
        conn.close()
        assert asset[0] == kind
    res = bot["client"].post(f"/api/v1/collection/{docx['id']}/media")
    assert res.status_code == 400 and "media library" in res.json()["detail"]


def test_a_sticker_a_location_and_a_contact_keep_the_plain_answer(bot):
    _saved(bot)
    assert _send(bot, None, sticker={"file_id": "st", "file_unique_id": "st", "width": 512, "height": 512,
                                     "is_animated": False, "is_video": False, "type": "regular"}) == SAID["no_text"]
    assert _send(bot, None, location={"latitude": 51.5, "longitude": -0.1}) == SAID["no_text"]
    assert _send(bot, None, contact={"phone_number": "+440000", "first_name": "Someone"}) == SAID["no_text"]
    assert _items() == [] and bot["fake"].calls_of("getFile") == []


def test_a_strangers_document_is_never_fetched(bot):
    _saved(bot)
    bot["fake"].add_file("doc-x", PDF, "documents/x.pdf")
    bot["fake"].push(STRANGER, None, document={"file_id": "doc-x", "file_unique_id": "x", "file_name": "x.pdf",
                                               "mime_type": "application/pdf", "file_size": len(PDF)})
    assert _until(lambda: bot["fake"].waiting() == [])
    time.sleep(0.3)
    assert bot["fake"].calls_of("getFile") == [] and _items() == []


def test_a_document_with_a_caption_offers_writing_and_one_without_offers_undo(bot):
    _saved(bot)
    _document(bot, PDF, "deck.pdf", "application/pdf", caption="the pricing deck")
    assert _labels(bot) == ["Write it up", "3 angles", "Undo"]
    _document(bot, PDF, "other.pdf", "application/pdf", file_id="doc-2")
    assert _labels(bot) == ["Undo"]


# ---------------------------------------------------------------------------
# Migration 42: the table rebuilt for two more kinds
# ---------------------------------------------------------------------------

def _the_migration():
    found = [m for m in migrations.MIGRATIONS if m[2] is getattr(migrations, "_migrate_files_and_albums", None)]
    assert len(found) == 1
    return found[0]


def test_an_older_table_is_rebuilt_keeping_every_row_its_id_and_the_sequence(bot):
    version, description, payload = _the_migration()
    assert "document" in description.lower() and "video" in description.lower()
    conn = sqlite3.connect(paths.get_db_path())
    conn.execute("DROP TABLE collection_items")
    conn.execute("""CREATE TABLE collection_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, received_at TEXT NOT NULL,
        kind TEXT NOT NULL CHECK (kind IN ('note', 'idea', 'forward', 'post', 'link', 'bookmark', 'photo', 'voice')),
        text TEXT NOT NULL DEFAULT '', link TEXT, activity_urn TEXT, desk_request_id INTEGER,
        tags TEXT NOT NULL DEFAULT '[]', topic TEXT,
        status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'used', 'not_now')),
        post_id TEXT, source TEXT NOT NULL DEFAULT 'telegram', origin_ref TEXT, updated_at TEXT, used_at TEXT,
        offered_at TEXT, angles TEXT, media TEXT, media_asset_id TEXT)""")
    conn.execute("INSERT INTO collection_items (id, received_at, kind, text, status) "
                 "VALUES (7, '2026-10-29T08:00:00+00:00', 'note', 'kept through the rebuild', 'new')")
    conn.execute("INSERT INTO collection_items (id, received_at, kind, text, status) "
                 "VALUES (9, '2026-10-29T09:00:00+00:00', 'photo', 'a photo', 'used')")
    conn.execute("DELETE FROM collection_items WHERE id = 9")
    conn.execute(f"PRAGMA user_version = {version - 1}")
    conn.commit()
    migrations.ensure_schema(conn, take_backup=False)
    rows = conn.execute("SELECT id, kind, text FROM collection_items").fetchall()
    assert rows == [(7, "note", "kept through the rebuild")]
    conn.execute("INSERT INTO collection_items (received_at, kind, text) VALUES ('2026-10-30T08:00:00+00:00', "
                 "'document', 'a document')")
    newest = conn.execute("SELECT MAX(id) FROM collection_items").fetchone()[0]
    assert newest == 10, "a removed item's id was given again, which an old button could reach"
    assert "media_group" in {r[1] for r in conn.execute("PRAGMA table_info(collection_items)")}
    payload(conn.cursor())
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM collection_items").fetchone()[0] == 2
    conn.close()
