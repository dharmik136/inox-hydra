"""
Photos and voice notes from the phone, kept as they are.
========================================================

Phase 3 of the Telegram bot, item 4 (docs/quality/cycle4/collection-box.md).
A photo or a voice note the creator sends their bot is downloaded from
Telegram (getFile, then the file itself), each request through egress.py
under the `ingress` category and counted under an address without the token
(telegram_bot.ledger_url and ledger_file_url), into the profile's assets
folder, under assets/phone, named by a random id and never by Telegram's own
file path. The collection lists it beside its caption, which is the
creator's own words; the studio serves it at /assets/phone/ to show or play.

Never read: no OCR, no transcription, and nothing of a file is sent
anywhere. A file over FILE_MAX is refused before it is fetched, and one that
grows past it while it is fetched is dropped, with no half file left behind.
A photo can be copied into the media library (media_assets), where the
images for a post are kept, and that copy is then the creator's like any
upload.

Phase 4, item 10: documents (a PDF or any other file) and videos (a video, a
round video message, a GIF Telegram sends as a video) are kept the same way,
with the file's own name kept to show and to download under. The stored
name's extension comes from SHOWN, the types the studio can show or play;
anything else is stored as .bin and served as bytes, a download only, never
opened in the studio's own window. The media library takes what its own
upload takes (an image, a PDF as a document carousel, an MP4 or WebM video),
each checked by its first bytes as the upload checks it.

Strict Invariants:
- Zero em-dashes.
- The token is in a request's address only: never logged, kept or shown.
"""

import json
import logging
import os
import shutil
import uuid
from typing import Any, Dict, Optional

import requests

try:
    from . import egress as _egress
    from . import paths
except ImportError:
    import egress as _egress
    import paths


def _bot():
    """telegram_bot, read when a file is fetched: it imports the collection, which imports this module."""
    try:
        from . import telegram_bot
    except ImportError:
        import telegram_bot
    return telegram_bot

logger = logging.getLogger("studio.phone_media")

FOLDER = "phone"
# The Bot API lets a bot download files of up to 20 MB, and the studio keeps
# none larger.
FILE_MAX = 20 * 1024 * 1024
CHUNK = 64 * 1024
TIMEOUT = 30
KINDS = {"photo": {"mime": "image/jpeg", "ext": ".jpg"}, "voice": {"mime": "audio/ogg", "ext": ".ogg"}}
# The types the studio shows or plays from its own folder, by the extension
# it stores them under. An image never as SVG, which can carry a script.
SHOWN = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
         "image/gif": ".gif", "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov",
         "audio/mpeg": ".mp3", "audio/ogg": ".ogg", "audio/mp4": ".m4a", "audio/x-m4a": ".m4a",
         "text/plain": ".txt"}
DOWNLOAD_ONLY = ".bin"
NAME_MAX = 120
# What the media library takes, as its own upload does, and its kind there.
LIBRARY = {"image/jpeg": "image", "image/png": "image", "image/webp": "image", "application/pdf": "carousel",
           "video/mp4": "video", "video/webm": "video"}


def _looks_like(mime: str, start: bytes) -> bool:
    """Whether a file's first bytes are what its type says, as the media library's upload checks them."""
    if mime == "image/jpeg":
        return start.startswith(b"\xff\xd8")
    if mime == "image/png":
        return start.startswith(b"\x89PNG\r\n\x1a\n")
    if mime == "image/webp":
        return start.startswith(b"RIFF") and b"WEBP" in start[:16]
    if mime == "application/pdf":
        return b"%PDF-" in start[:1024]
    if mime == "video/mp4":
        return b"ftyp" in start[:64]
    if mime == "video/webm":
        return start.startswith(b"\x1aE\xdf\xa3")
    return False


class TooBig(ValueError):
    """A file larger than the studio keeps from the phone."""


class Unfetched(RuntimeError):
    """
    A file Telegram did not hand over. `lasting` when asking again will not
    help (Telegram refused it); otherwise the message is tried again.
    """

    def __init__(self, reason: str, lasting: bool = False):
        super().__init__(reason)
        self.lasting = lasting


def _int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _name(value: Any) -> Optional[str]:
    """A file's own name as it is kept: the last part of it, no control character, at most NAME_MAX."""
    name = os.path.basename(str(value or "").replace("\\", "/")).strip()
    name = "".join(c for c in name if c.isprintable() and c not in '<>:"|?*')
    return name[:NAME_MAX] or None


def _mime(value: Any, fallback: str) -> str:
    mime = str(value or "").strip().lower()
    return mime if 0 < len(mime) <= 100 and "/" in mime else fallback


def _file(kind: str, held: Dict[str, Any], mime: str, name_default: str) -> Dict[str, Any]:
    """A document's or a video's file as the collection keeps it: what it is, and where the studio may show it."""
    return {"kind": kind, "file_id": str(held["file_id"]), "size": _int(held.get("file_size")) or None,
            "mime": mime, "ext": SHOWN.get(mime, DOWNLOAD_ONLY),
            "name": _name(held.get("file_name")) or name_default + SHOWN.get(mime, ""),
            "duration": _int(held.get("duration")) or None,
            "width": _int(held.get("width") or held.get("length")) or None,
            "height": _int(held.get("height") or held.get("length")) or None}


def wanted(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    What a message carries that the collection keeps as it is: a photo (the
    largest size that fits under FILE_MAX, or the largest there is, which
    is then refused), a voice note, or since phase 4 a video (a video, a
    round video message, a GIF, which Telegram also marks as a document) or
    a document (any file, a music file among them). None for anything else,
    such as a sticker, a location or a contact, which is not kept.
    """
    photo = message.get("photo") if isinstance(message, dict) else None
    if isinstance(photo, list):
        sizes = [p for p in photo if isinstance(p, dict) and p.get("file_id")]
        if sizes:
            fitting = [p for p in sizes if _int(p.get("file_size")) <= FILE_MAX] or sizes
            best = max(fitting, key=lambda p: (_int(p.get("width")) * _int(p.get("height")), _int(p.get("file_size"))))
            return {"kind": "photo", "file_id": str(best["file_id"]), "size": _int(best.get("file_size")) or None,
                    "width": _int(best.get("width")) or None, "height": _int(best.get("height")) or None,
                    **KINDS["photo"]}
    voice = message.get("voice") if isinstance(message, dict) else None
    if isinstance(voice, dict) and voice.get("file_id"):
        return {"kind": "voice", "file_id": str(voice["file_id"]), "size": _int(voice.get("file_size")) or None,
                "duration": _int(voice.get("duration")) or None, **KINDS["voice"]}
    if not isinstance(message, dict):
        return None
    # A GIF first: Telegram sets its document too, "for backward compatibility".
    for field, default in (("animation", "A GIF from your phone"), ("video", "A video from your phone"),
                           ("video_note", "A round video from your phone")):
        held = message.get(field)
        if isinstance(held, dict) and held.get("file_id"):
            return _file("video", held, _mime(held.get("mime_type"), "video/mp4"), default)
    for field, default in (("audio", "A sound file from your phone"), ("document", "A file from your phone")):
        held = message.get(field)
        if isinstance(held, dict) and held.get("file_id"):
            return _file("document", held, _mime(held.get("mime_type"), "application/octet-stream"), default)
    return None


def folder() -> str:
    """Where the phone's files are kept: the open profile's assets folder, under phone."""
    where = os.path.join(paths.get_assets_dir(), FOLDER)
    os.makedirs(where, exist_ok=True)
    return where


def _lasting(status: int) -> bool:
    """Whether Telegram's answer means asking again will not help: a refusal, not a busy or broken server."""
    return 400 <= status < 500 and status != 429


def fetch(token: str, file: Dict[str, Any]) -> Dict[str, Any]:
    """
    Downloads one file the creator sent, and returns what the collection
    keeps of it: where it is, its type and size, and a photo's width and
    height or a voice note's length. Raises TooBig or Unfetched, and leaves
    no half file behind.
    """
    if (file.get("size") or 0) > FILE_MAX:
        raise TooBig("larger than the studio keeps")
    telegram_bot = _bot()
    try:
        _egress.require(telegram_bot.ledger_url("getFile"), "ingress")
    except _egress.EgressRefused as refused:
        raise Unfetched(f"refused here: {refused}")
    try:
        res = requests.get(telegram_bot.method_url(token, "getFile"), params={"file_id": file["file_id"]},
                           timeout=TIMEOUT)
    except requests.RequestException as error:
        raise Unfetched(f"getFile did not answer: {type(error).__name__}")
    try:
        body = res.json()
    except ValueError:
        body = {}
    body = body if isinstance(body, dict) else {}
    if res.status_code != 200 or not body.get("ok"):
        raise Unfetched(f"getFile answered {res.status_code}", lasting=_lasting(res.status_code))
    result = body.get("result") if isinstance(body.get("result"), dict) else {}
    file_path = result.get("file_path")
    if not isinstance(file_path, str) or not file_path or ".." in file_path or file_path.startswith("/"):
        raise Unfetched("getFile named no file", lasting=True)
    if _int(result.get("file_size")) > FILE_MAX:
        raise TooBig("larger than the studio keeps")
    try:
        _egress.require(telegram_bot.ledger_file_url(), "ingress")
    except _egress.EgressRefused as refused:
        raise Unfetched(f"refused here: {refused}")

    name = f"{uuid.uuid4().hex}{file['ext']}"
    final = os.path.join(folder(), name)
    partial = final + ".part"
    written = 0
    try:
        with requests.get(telegram_bot.file_url(token, file_path), stream=True, timeout=TIMEOUT) as answer:
            if answer.status_code != 200:
                raise Unfetched(f"the file answered {answer.status_code}", lasting=_lasting(answer.status_code))
            with open(partial, "wb") as out:
                for chunk in answer.iter_content(CHUNK):
                    written += len(chunk)
                    if written > FILE_MAX:
                        raise TooBig("larger than the studio keeps")
                    out.write(chunk)
        if written == 0:
            raise Unfetched("the file was empty", lasting=True)
        os.replace(partial, final)
    except requests.RequestException as error:
        _discard_path(partial)
        raise Unfetched(f"the file did not arrive: {type(error).__name__}")
    except BaseException:
        _discard_path(partial)
        raise
    kept: Dict[str, Any] = {"path": f"/assets/{FOLDER}/{name}", "mime": file["mime"], "bytes": written}
    for key in ("width", "height", "duration", "name"):
        if file.get(key):
            kept[key] = file[key]
    if file.get("ext") == DOWNLOAD_ONLY:
        # Kept as bytes: the studio serves it as a download, never as a page.
        kept["download_only"] = True
    return kept


def files_of(media: Any) -> list:
    """Every file an item's media names: the first, and an album's others."""
    if isinstance(media, str):
        try:
            media = json.loads(media)
        except ValueError:
            return []
    if not isinstance(media, dict):
        return []
    return [media] + [f for f in media.get("more") or [] if isinstance(f, dict)]


def library_kind(file: Any) -> Optional[str]:
    """What the media library would keep a file as (image, carousel or video), or None when it takes no such file."""
    if not isinstance(file, dict) or file.get("download_only"):
        return None
    return LIBRARY.get(str(file.get("mime") or ""))


def on_disk(media: Any) -> Optional[str]:
    """The file an item's media names, inside the profile's phone folder, or None."""
    if isinstance(media, str):
        try:
            media = json.loads(media)
        except ValueError:
            return None
    path = media.get("path") if isinstance(media, dict) else None
    prefix = f"/assets/{FOLDER}/"
    if not isinstance(path, str) or not path.startswith(prefix):
        return None
    name = path[len(prefix):]
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    return os.path.join(paths.get_assets_dir(), FOLDER, name)


def _discard_path(where: Optional[str]) -> None:
    if where and os.path.exists(where):
        try:
            os.remove(where)
        except OSError as error:
            logger.warning("A file the phone sent could not be removed: %s", error.strerror or type(error).__name__)


def discard(media: Any) -> None:
    """Removes an item's files, every one of an album's, if they are still there."""
    for file in files_of(media):
        _discard_path(on_disk(file))


def forget() -> None:
    """Delete everything: every file the phone sent. A copy in the media library is the creator's, and stays."""
    where = os.path.join(paths.get_assets_dir(), FOLDER)
    if not os.path.isdir(where):
        return
    for name in os.listdir(where):
        _discard_path(os.path.join(where, name))


def to_library(conn, media: Any) -> str:
    """
    A copy of each file of an item the media library takes, where a post's
    images, document carousels and videos are kept: copied into uploads and
    listed as its kind, each checked by its first bytes as the library's own
    upload checks it. Returns the first copy's id. The copies are the
    creator's like any upload, so removing the item leaves them. Raises
    FileNotFoundError when nothing it takes is on this computer.
    """
    made: list = []
    try:
        for held in files_of(media):
            kind = library_kind(held)
            source = on_disk(held)
            if kind is None or not source or not os.path.exists(source):
                continue
            with open(source, "rb") as handle:
                start = handle.read(1024)
            if not _looks_like(held["mime"], start):
                continue
            ext = SHOWN.get(held["mime"], ".bin")
            shown = held.get("name") or {"image": "Photo", "carousel": "Document", "video": "Video"}[kind] + \
                " from your phone" + ext
            name = f"{uuid.uuid4().hex[:8]}_from_your_phone{ext}"
            target = os.path.join(paths.get_uploads_dir(), name)
            shutil.copyfile(source, target)
            asset_id = f"asset_{uuid.uuid4().hex[:10]}"
            dimensions = ({"width": held["width"], "height": held["height"]}
                          if kind == "image" and held.get("width") and held.get("height") else None)
            try:
                conn.execute(
                    "INSERT INTO media_assets (id, filename, storage_path, media_type, mime_type, size_bytes, "
                    "dimensions, page_count) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                    (asset_id, shown, f"/assets/uploads/{name}", kind, held["mime"], os.path.getsize(target),
                     json.dumps(dimensions) if dimensions else None))
            except BaseException:
                _discard_path(target)
                raise
            made.append((asset_id, target))
    except BaseException:
        for _asset, target in made:
            _discard_path(target)
        raise
    if not made:
        raise FileNotFoundError("nothing the media library takes is on this computer")
    return made[0][0]
