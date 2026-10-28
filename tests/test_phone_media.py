"""
Photos and voice notes from the phone, kept as they are.
=======================================================

Phase 3 of the Telegram bot, item 4 (docs/quality/cycle4/collection-box.md).
A photo or a voice note sent to the bot is downloaded with getFile, through
the egress check under the `ingress` category and counted under an address
without the token, into the profile's assets folder, and listed in the
collection: never read, no OCR and no transcription. A caption is the
creator's words. A photo can go into the media library, where a post's
image is kept. Against the fake Bot API on loopback; nothing reaches the
network.

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import sqlite3
import sys

import pytest

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
JPEG_SMALL = b"\xff\xd8\xff\xe0" + b"small" * 20
JPEG_LARGE = b"\xff\xd8\xff\xe0" + b"large" * 400
OGG = b"OggS" + b"\x00voice" * 300


def _photo(bot, caption=None):
    bot["fake"].add_file("ph-small", JPEG_SMALL, "photos/file_7.jpg")
    bot["fake"].add_file("ph-large", JPEG_LARGE, "photos/file_8.jpg")
    sizes = [{"file_id": "ph-small", "file_unique_id": "s", "width": 90, "height": 60, "file_size": len(JPEG_SMALL)},
             {"file_id": "ph-large", "file_unique_id": "l", "width": 1280, "height": 853,
              "file_size": len(JPEG_LARGE)}]
    extra = {"caption": caption} if caption else {}
    return _send(bot, None, photo=sizes, **extra)


def _voice(bot):
    bot["fake"].add_file("vo-1", OGG, "voice/file_9.oga")
    return _send(bot, None, voice={"file_id": "vo-1", "file_unique_id": "v", "duration": 7, "mime_type": "audio/ogg",
                                   "file_size": len(OGG)})


def _on_disk(item):
    media = json.loads(item["media"])
    assert media["path"].startswith("/assets/phone/"), media
    return os.path.join(paths.get_assets_dir(), media["path"][len("/assets/"):]), media


# ---------------------------------------------------------------------------
# Kept as they are
# ---------------------------------------------------------------------------

def test_a_photo_is_kept_as_it_is_with_its_caption_as_your_words(bot):
    _saved(bot)
    assert _photo(bot, caption="the new studio wall #office") == SAID["collected"]
    [item] = _items()
    assert (item["kind"], item["text"], item["tags"], item["status"]) == ("photo", "the new studio wall #office",
                                                                          ["office"], "new")
    where, media = _on_disk(item)
    with open(where, "rb") as handle:
        assert handle.read() == JPEG_LARGE, "the largest size was not the one kept, or it was changed"
    assert (media["mime"], media["bytes"], media["width"], media["height"]) == ("image/jpeg", len(JPEG_LARGE),
                                                                               1280, 853)
    assert [c["params"]["file_id"] for c in bot["fake"].calls_of("getFile")] == ["ph-large"]
    # Words to write from: the caption, so Write it up and the angles come with Undo.
    assert _labels(bot) == ["Write it up", "3 angles", "Undo"]


def test_a_voice_note_is_kept_as_it_is_and_never_transcribed(bot):
    _saved(bot)
    assert _voice(bot) == SAID["collected"]
    [item] = _items()
    assert (item["kind"], item["text"]) == ("voice", "")
    where, media = _on_disk(item)
    with open(where, "rb") as handle:
        assert handle.read() == OGG
    assert (media["mime"], media["duration"]) == ("audio/ogg", 7)
    assert where.endswith(".ogg")
    # No words to write from: Undo alone.
    assert _labels(bot) == ["Undo"]
    methods = {c["method"] for c in bot["fake"].calls}
    assert methods <= {"getUpdates", "sendMessage", "getFile", "file"}, methods


def test_the_file_is_fetched_through_the_egress_check_and_counted_without_the_token(bot, monkeypatch):
    import egress
    import phone_media

    asked = []
    real = egress.require
    monkeypatch.setattr(phone_media._egress, "require",
                        lambda destination, category: (asked.append((destination, category)),
                                                       real(destination, category))[1])
    _saved(bot)
    _photo(bot)
    # The one egress module is shared, so the bot's own polls and answers are asked here too.
    fetched = [(destination, category) for destination, category in asked
               if destination.endswith("/getFile") or "/file/" in destination]
    assert [category for _destination, category in fetched] == ["ingress", "ingress"], fetched
    assert all("<token>" in destination and TOKEN not in destination for destination, _c in fetched), fetched
    ledger = repr(egress.describe())
    assert TOKEN not in ledger and TOKEN.split(":")[1] not in ledger
    [item] = _items()
    assert TOKEN.split(":")[1] not in json.dumps(item) and "file_8" not in json.dumps(item), (
        "the token or Telegram's own file path was kept")


def test_with_ingress_off_nothing_is_fetched(bot, monkeypatch):
    import ingress
    import phone_media

    _saved(bot)
    bot["fake"].add_file("ph-off", JPEG_SMALL, "photos/file_1.jpg")
    monkeypatch.setenv("INOX_ALLOW_INGRESS_EGRESS", "0")
    with pytest.raises(phone_media.Unfetched):
        phone_media.fetch(TOKEN, {"kind": "photo", "file_id": "ph-off", "size": len(JPEG_SMALL), "mime": "image/jpeg",
                                  "ext": ".jpg"})
    assert bot["fake"].calls_of("getFile") == []
    assert ingress  # the module the bot runs in, imported for the fixture


def test_a_file_too_big_is_refused_before_it_is_fetched(bot):
    import phone_media

    _saved(bot)
    huge = phone_media.FILE_MAX + 1
    answer = _send(bot, None, photo=[{"file_id": "ph-huge", "width": 9000, "height": 9000, "file_size": huge}])
    assert answer == SAID["too_big"]
    assert bot["fake"].calls_of("getFile") == [] and _items() == []
    # Said too when only getFile tells the size.
    bot["fake"].add_file("vo-huge", OGG, "voice/file_2.oga", file_size=huge)
    assert _send(bot, None, voice={"file_id": "vo-huge", "duration": 900}) == SAID["too_big"]
    assert bot["fake"].calls_of("file") == [] and _items() == []


def test_a_file_telegram_will_not_hand_over_is_said_and_nothing_kept(bot):
    _saved(bot)
    assert _send(bot, None, photo=[{"file_id": "ph-unknown", "width": 10, "height": 10, "file_size": 10}]) == (
        SAID["media_failed"])
    assert _items() == []
    assert os.listdir(os.path.join(paths.get_assets_dir())) in ([], ["phone"])
    phone = os.path.join(paths.get_assets_dir(), "phone")
    assert not os.path.isdir(phone) or os.listdir(phone) == [], "a half file was left behind"


def test_a_strangers_photo_is_never_fetched(bot):
    _saved(bot)
    bot["fake"].add_file("ph-stranger", JPEG_SMALL, "photos/file_4.jpg")
    bot["fake"].push(STRANGER, None, photo=[{"file_id": "ph-stranger", "width": 9, "height": 9,
                                             "file_size": len(JPEG_SMALL)}])
    assert _until(lambda: bot["fake"].waiting() == [])
    assert _until(lambda: len(_texts(bot, STRANGER)) == 1)
    assert bot["fake"].calls_of("getFile") == [] and bot["fake"].calls_of("file") == [] and _items() == []
    phone = os.path.join(paths.get_assets_dir(), "phone")
    assert not os.path.isdir(phone) or os.listdir(phone) == []


def test_a_sticker_or_a_document_is_still_not_kept(bot):
    _saved(bot)
    assert _send(bot, None, sticker={"file_id": "st-1", "emoji": "x"}) == SAID["no_text"]
    assert _send(bot, None, document={"file_id": "doc-1", "file_name": "notes.pdf"}) == SAID["no_text"]
    assert _items() == [] and bot["fake"].calls_of("getFile") == []


def test_a_message_handled_again_fetches_nothing(bot):
    _saved(bot)
    bot["fake"].add_file("ph-again", JPEG_SMALL, "photos/file_3.jpg")
    update = {"update_id": 9001, "message": {"message_id": 9001, "date": 1761700000, "chat": {"id": int(OWNER)},
                                              "photo": [{"file_id": "ph-again", "width": 9, "height": 9,
                                                         "file_size": len(JPEG_SMALL)}]}}
    first = bot["daemon"].process_incoming_update(update)
    again = bot["daemon"].process_incoming_update(update)
    assert first["item"]["id"] == again["item"]["id"] and len(_items()) == 1
    assert len(bot["fake"].calls_of("getFile")) == 1


# ---------------------------------------------------------------------------
# Taken back, removed and forgotten with their files
# ---------------------------------------------------------------------------

def test_undo_and_remove_take_the_file_with_the_item(bot):
    _saved(bot)
    _photo(bot)
    [item] = _items()
    where, _media = _on_disk(item)
    bot["fake"].press_button("Undo", OWNER)
    assert _until(lambda: _items() == []), "Undo did not take the photo back"
    assert not os.path.exists(where), "Undo left the file behind"

    _voice(bot)
    [item] = _items()
    where, _media = _on_disk(item)
    assert bot["client"].delete(f"/api/v1/collection/{item['id']}").status_code == 200
    assert not os.path.exists(where), "Remove left the file behind"


def test_delete_everything_takes_every_file_sent(bot):
    import onboarding

    _saved(bot)
    _photo(bot)
    _voice(bot)
    folder = os.path.join(paths.get_assets_dir(), "phone")
    assert len(os.listdir(folder)) == 2
    onboarding.forget_identity()
    assert _items() == [] and os.listdir(folder) == []


# ---------------------------------------------------------------------------
# In the studio
# ---------------------------------------------------------------------------

def test_the_box_lists_the_file_and_the_studio_serves_it(bot):
    _saved(bot)
    _photo(bot)
    listed = bot["client"].get("/api/v1/collection?status=all").json()["items"]
    media = listed[0]["media"]
    assert media["path"].startswith("/assets/phone/") and media["mime"] == "image/jpeg"
    served = bot["client"].get(media["path"])
    assert served.status_code == 200 and served.content == JPEG_LARGE


def test_a_photo_goes_into_the_media_library_and_says_so(bot):
    _saved(bot)
    _photo(bot, caption="the wall")
    [item] = _items()
    res = bot["client"].post(f"/api/v1/collection/{item['id']}/media")
    assert res.status_code == 200, res.text
    became = res.json()["item"]["became"]
    assert became["kind"] == "media" and became["said"] == "In your media library"
    assets = bot["client"].get("/api/media").json()["assets"]
    assert [(a["media_type"], a["mime_type"]) for a in assets] == [("image", "image/jpeg")]
    copy = os.path.join(paths.get_assets_dir(), assets[0]["storage_path"][len("/assets/"):])
    with open(copy, "rb") as handle:
        assert handle.read() == JPEG_LARGE
    # Twice is once; the item is used, and removing it leaves the library's copy.
    assert bot["client"].post(f"/api/v1/collection/{item['id']}/media").status_code == 200
    assert len(bot["client"].get("/api/media").json()["assets"]) == 1
    assert _items()[0]["status"] == "used"
    bot["client"].delete(f"/api/v1/collection/{item['id']}")
    assert os.path.exists(copy)


def test_a_voice_note_does_not_go_into_the_media_library(bot):
    _saved(bot)
    _voice(bot)
    [item] = _items()
    res = bot["client"].post(f"/api/v1/collection/{item['id']}/media")
    assert res.status_code == 400 and "photo" in res.json()["detail"]


# ---------------------------------------------------------------------------
# Its migration, and what is said about it
# ---------------------------------------------------------------------------

def _the_migration():
    found = [m for m in migrations.MIGRATIONS if "voice note" in m[1].lower()]
    assert len(found) == 1, "the photos and voice notes migration is not in the ledger exactly once"
    return found[0]


def test_the_migration_is_named_for_what_it_changes():
    version, description, payload = _the_migration()
    assert version == 40 and "photo" in description.lower() and callable(payload)


def test_an_older_database_gains_the_columns_and_a_second_run_adds_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path / "studio"))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db

    init_db()
    conn = sqlite3.connect(paths.get_db_path())
    columns = {row[1] for row in conn.execute("PRAGMA table_info(collection_items)")}
    assert {"media", "media_asset_id"} <= columns
    version, _description, payload = _the_migration()
    conn.execute("ALTER TABLE collection_items DROP COLUMN media")
    conn.execute("ALTER TABLE collection_items DROP COLUMN media_asset_id")
    conn.execute(f"PRAGMA user_version = {version - 1}")
    conn.commit()
    migrations.ensure_schema(conn, take_backup=False)
    assert {"media", "media_asset_id"} <= {row[1] for row in conn.execute("PRAGMA table_info(collection_items)")}
    payload(conn.cursor())
    conn.commit()
    conn.close()


def test_the_policy_and_the_help_say_they_are_kept_and_never_read():
    def read(*parts):
        with open(os.path.join(REPO_ROOT, *parts), encoding="utf-8") as handle:
            return " ".join(handle.read().split())

    import phone_media

    policy = read("docs", "PRIVACY_POLICY.md")
    assert "voice note" in policy and "never transcribed" in policy and "never read" in policy
    guide = read("docs", "help", "send-a-post-idea-from-telegram.md")
    assert "Add to your media library" in guide and "never transcribed" in guide
    # The size said is the size kept.
    most = f"{phone_media.FILE_MAX // (1024 * 1024)} MB"
    assert most in policy and most in guide and most in SAID["too_big"]
    for key in ("too_big", "media_failed"):
        assert SAID[key] in guide, key
