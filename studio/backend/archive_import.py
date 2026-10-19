"""
LinkedIn Data Archive Import: the Creator's Own Record, Handed Over by LinkedIn.
================================================================================
LinkedIn lets every member download their data: Settings, Data privacy, "Get a
copy of your data". It is the creator's own record, sanctioned by LinkedIn, and
it carries years of history in one file: no scrolling, no page reading, and no
terms question. That is why it leads onboarding (planning/7 Roadmap/Risk -
LinkedIn terms and detection.md, mitigation 1).

The flow keeps the creator in charge of every step:

  1. request   The Setup screen opens LinkedIn's download page in the bridge
               browser. The creator asks for the archive there; LinkedIn
               emails a link, usually within minutes for the first part and
               within a day for the full archive.
  2. find      Once they have said they asked for it, the Setup screen looks
               in their Downloads folder for a file named like LinkedIn's
               exports, and offers it. They can also choose the file by hand.
  3. preview   Nothing is written until they have seen what the archive holds
               and what will be imported from it, file by file.
  4. import    What they kept ticked is imported. Messages are never imported.

What is read, by file:

  Shares.csv       their posts                  -> own_posts (no figures: the
                                                    archive has none, so they
                                                    stay "not measured")
  Comments.csv     comments they wrote          -> outbound_engagements
  Reactions.csv    posts they reacted to        -> outbound_engagements
  Profile.csv      name, headline, about        -> creator_identity, filling
                                                    only what is empty
  Positions.csv,   roles, schools, skills       -> creator_positions,
  Education.csv,                                   creator_education (only
  Skills.csv                                       when empty), creator_skills
  Connections.csv  first-degree connections     -> connections (names,
                                                    company, position, date;
                                                    never email addresses)

Column names are matched loosely and every file's outcome is reported,
including files the importer does not understand, with the columns it found,
so a change in LinkedIn's export is visible rather than silent.

Strict Invariants:
- Zero em-dashes in any code, docstring or comment.
- Zero egress: reads a local file, writes the local database.
- Nothing invented: no figure is created for an imported post, and a row that
  cannot be read is counted as skipped, never guessed at.
- Bridge-captured data is never overwritten by the archive.
"""

import bisect
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
import unicodedata
import uuid
import zipfile
import zlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import unquote

try:
    from . import paths
    from .database import get_db
except ImportError:
    import paths
    from database import get_db

DOWNLOAD_PAGE = "https://www.linkedin.com/mypreferences/d/download-my-data"
ARCHIVE_NAME = re.compile(r"linkedin.*data.*export.*\.zip$|linkedindataexport.*\.zip$", re.IGNORECASE)
REQUESTED_KEY = "archive_requested_at"
# What browsers write while a download is still arriving, beside or instead of
# the final file: Firefox (.part, next to an empty file with the final name),
# Chrome and Edge (.crdownload), Safari (.download), Opera (.opdownload).
PARTIAL_SUFFIXES = (".part", ".crdownload", ".download", ".opdownload", ".partial")
STILL_DOWNLOADING = "That file is still downloading. Wait for the download to finish, then try again."
# A file in Downloads that changed this recently and does not open may still be arriving.
FRESH_FOR = timedelta(minutes=2)
# When the creator said their account has no posts, so no archive will bring any.
NO_POSTS_KEY = "archive_no_posts_at"
# settings key + archive_imports.id -> what that import brought, so it can be
# removed again on its own (remove_last_import).
BROUGHT_KEY = "archive_import_brought:"
PROFILE_COLUMNS = ("display_name", "headline", "about", "location")

MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
# LinkedIn's CSVs are small: years of posts are a few megabytes. These bound
# what a crafted file can make the parser hold, which runs to many times the
# file's own size once it is rows and dictionaries.
MAX_MEMBER_BYTES = 50 * 1024 * 1024
MAX_RATIO = 100
MAX_ROWS = 200_000
MAX_HEADER_SCAN = 50
MAX_MEMBERS = 5000
# An archive a browser unpacked into a folder (Safari does, by default) is read
# to this many folders deep; LinkedIn's has one level of subfolders.
MAX_FOLDER_DEPTH = 3
UPLOAD_TTL = timedelta(hours=24)
# A post is at most 3,000 characters and a comment 1,250; csv's default field
# limit (131,072) is enough for those, but not for the odd long "about".
csv.field_size_limit(max(csv.field_size_limit(), 1_000_000))
# Two posts by one creator whose ids decode to within this much of each other,
# and whose text agrees, are the same post seen two ways: LinkedIn's archive
# names a post by its share or ugcPost id, the page by its activity id.
TWIN_WINDOW = timedelta(minutes=10)
# An import writes in batches of about this long, and pauses between them for
# longer than SQLite's longest sleep between retries (100 ms), so a draft saved
# or a capture read meanwhile waits a fraction of a second, not the whole import.
BATCH_SECONDS = 0.25
BATCH_PAUSE = 0.12
# The words the bridge uses for reaction types, for LinkedIn's internal ones.
REACTION_WORDS = {"LIKE": "like", "PRAISE": "celebrate", "APPRECIATION": "support", "EMPATHY": "love",
                  "INTEREST": "insightful", "ENTERTAINMENT": "funny", "MAYBE": "curious"}

_URN = re.compile(r"urn:li:(activity|share|ugcPost):(\d{6,25})")

# kind -> (file name, label, imported by default, required columns, aliases)
FILES: Dict[str, Dict[str, Any]] = {
    "posts": {
        "file": "shares.csv", "label": "Posts you wrote", "default": True,
        "columns": {"date": ["date"], "link": ["sharelink", "share link", "link"],
                    "text": ["sharecommentary", "share commentary", "commentary"]},
        "optional": {"shared": ["sharedurl", "shared url"], "media": ["mediaurl", "media url"]},
    },
    "comments": {
        "file": "comments.csv", "label": "Comments you wrote", "default": True,
        "columns": {"date": ["date"], "link": ["link"], "message": ["message", "comment"]},
    },
    "reactions": {
        "file": "reactions.csv", "label": "Posts you reacted to", "default": True,
        "columns": {"date": ["date"], "type": ["type", "reaction type"], "link": ["link"]},
    },
    "profile": {
        "file": "profile.csv", "label": "Your name, headline and about", "default": True,
        "columns": {"first": ["first name"], "last": ["last name"], "headline": ["headline"]},
        "optional": {"summary": ["summary", "about"], "location": ["geo location", "location"],
                     "profile_url": ["profile url", "public profile url"]},
    },
    "positions": {
        "file": "positions.csv", "label": "Your roles", "default": True,
        "columns": {"company": ["company name", "company"], "title": ["title"]},
        "optional": {"description": ["description"], "location": ["location"],
                     "started": ["started on", "start date"], "finished": ["finished on", "end date"]},
    },
    "education": {
        "file": "education.csv", "label": "Your education", "default": True,
        "columns": {"school": ["school name", "school"]},
        "optional": {"degree": ["degree name", "degree"], "start": ["start date"], "end": ["end date"]},
    },
    "skills": {
        "file": "skills.csv", "label": "Your skills", "default": True,
        "columns": {"name": ["name", "skill"]},
    },
    "connections": {
        "file": "connections.csv", "label": "Your connections (names, company, position; no email addresses)",
        "default": True,
        "columns": {"first": ["first name"], "last": ["last name"], "url": ["url", "profile url"]},
        "optional": {"company": ["company"], "position": ["position"], "connected": ["connected on"]},
    },
}
NEVER_IMPORTED = {
    "messages.csv": "Messages stay in the archive. They are other people's words, and nothing in the studio needs them.",
}


class ArchiveError(ValueError):
    """The archive cannot be read, or a source is not one the studio offered."""


class _Unreadable(ArchiveError):
    """The file does not open as a ZIP, or a file in it is cut short: damaged, or not finished downloading."""


class OwnerUnconfirmed(ArchiveError):
    """The archive may be another member's, and the creator has not said to import it as theirs."""


# ---------------------------------------------------------------------------
# Finding the archive
# ---------------------------------------------------------------------------

# Windows' Known Folder id for Downloads, under which Explorer records where the
# folder is when the creator has moved it (Properties, Location) or OneDrive has.
WINDOWS_DOWNLOADS = "{374DE290-123F-4565-9164-39C4925E467B}"


def _windows_downloads() -> Optional[str]:
    """Where Windows keeps this user's Downloads folder, from the registry, or None."""
    try:
        import winreg
    except ImportError:
        return None
    for path in (r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
                 r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                value, _kind = winreg.QueryValueEx(key, WINDOWS_DOWNLOADS)
        except OSError:
            continue
        if value:
            # "User Shell Folders" holds it unexpanded, as %USERPROFILE%\Downloads.
            return os.path.expandvars(str(value))
    return None


def downloads_dirs() -> List[str]:
    """
    The creator's Downloads folder: where Windows says it is when it has
    been moved, the one in their home folder, and the one their Linux desktop
    names, if different.
    """
    home = os.path.expanduser("~")
    found = [os.path.join(home, "Downloads")]
    if sys.platform.startswith("win"):
        moved = _windows_downloads()
        if moved and os.path.normcase(moved) != os.path.normcase(found[0]):
            found.insert(0, moved)
    try:
        with open(os.path.join(home, ".config", "user-dirs.dirs"), "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("XDG_DOWNLOAD_DIR="):
                    value = line.split("=", 1)[1].strip().strip('"').replace("$HOME", home)
                    if value not in found:
                        found.append(value)
    except OSError:
        pass
    return [d for d in found if os.path.isdir(d)]


def _partial(name: str) -> Tuple[str, bool]:
    """(the final name, whether this is a browser's file for a download still arriving)."""
    for suffix in PARTIAL_SUFFIXES:
        if name.lower().endswith(suffix):
            return name[: -len(suffix)], True
    return name, False


def _unpacked_size(folder: str) -> Optional[int]:
    """
    The size of the CSVs in a folder that is LinkedIn's archive unpacked, or
    None when it is not one: a real folder, not a link, holding at least one
    of the files the studio reads.
    """
    if os.path.islink(folder) or not os.path.isdir(folder):
        return None
    wanted = {spec["file"] for spec in FILES.values()}
    try:
        entries = [e for e in os.scandir(folder) if e.is_file(follow_symlinks=False)]
    except OSError:
        return None
    if not any(e.name.lower() in wanted for e in entries):
        return None
    return sum(e.stat(follow_symlinks=False).st_size for e in entries if e.name.lower().endswith(".csv"))


def find_archives(limit: int = 5) -> List[Dict[str, Any]]:
    """
    LinkedIn export files in Downloads, newest first. Names and sizes only.

    A download still arriving is listed under its final name with
    `downloading`, so it is shown as such rather than offered and then
    refused as a broken archive. An archive the browser unpacked into a
    folder of the same name (Safari's "Open safe files after downloading"
    does, and removes the ZIP) is listed too, with `folder`.
    """
    hits = []
    for directory in downloads_dirs():
        try:
            names = os.listdir(directory)
        except OSError:
            continue
        listed = set(names)
        for name in names:
            final, partial = _partial(name)
            zip_named = bool(ARCHIVE_NAME.search(final))
            if not zip_named and (partial or not ARCHIVE_NAME.search(final + ".zip")):
                continue
            if partial and final in listed:
                continue
            full = os.path.join(directory, name)
            try:
                stat = os.stat(full)
            except OSError:
                continue
            is_file = os.path.isfile(full)
            folder_bytes = None if partial or zip_named else _unpacked_size(full)
            if not partial and folder_bytes is None and not (zip_named and is_file):
                continue
            hits.append({
                "name": final,
                "path": full,
                "folder": folder_bytes is not None,
                "bytes": folder_bytes if folder_bytes is not None else stat.st_size if is_file else 0,
                "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                # Only a file can be an empty placeholder: Windows reports every folder as 0 bytes.
                "downloading": partial or (is_file and stat.st_size == 0)
                               or any(final + s in listed for s in PARTIAL_SUFFIXES),
            })
    hits.sort(key=lambda h: h["modified"], reverse=True)
    return hits[:limit]


def _uploads_dir() -> str:
    return paths._ensure(os.path.join(paths.get_data_dir(), "archive_uploads"))


def _sweep_uploads() -> None:
    """An uploaded archive is kept only until it is imported or set aside, or for a day."""
    directory = _uploads_dir()
    cutoff = datetime.now().timestamp() - UPLOAD_TTL.total_seconds()
    for name in os.listdir(directory):
        full = os.path.join(directory, name)
        try:
            if os.path.getmtime(full) < cutoff:
                os.remove(full)
        except OSError:
            pass


class UploadWriter:
    """
    Writes an uploaded archive to the profile's uploads folder as it arrives.

    The cap is checked chunk by chunk, so an oversized upload stops at the
    cap instead of landing on disk in full first.
    """

    def __init__(self, filename: str):
        _sweep_uploads()
        self.token = uuid.uuid4().hex
        self.path = os.path.join(_uploads_dir(), f"{self.token}.zip")
        self.filename = os.path.basename(filename or "archive.zip")[:200]
        self.written = 0
        self._handle = open(self.path, "wb")

    def write(self, chunk: bytes) -> None:
        self.written += len(chunk)
        if self.written > MAX_ARCHIVE_BYTES:
            self.abort()
            raise ArchiveError("That file is larger than any LinkedIn archive the studio expects.")
        self._handle.write(chunk)

    def finish(self) -> str:
        self._handle.close()
        with open(self.path + ".name", "w", encoding="utf-8") as handle:
            handle.write(self.filename)
        return f"upload:{self.token}"

    def abort(self) -> None:
        self._handle.close()
        if os.path.exists(self.path):
            os.remove(self.path)


def store_upload(stream, filename: str) -> str:
    """Keeps an uploaded archive until it is imported. Returns its source token."""
    writer = UploadWriter(filename)
    try:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            writer.write(chunk)
    except BaseException:
        writer.abort()
        raise
    return writer.finish()


def _resolve(source: str) -> Tuple[str, str]:
    """(path, display name) for a source the studio itself offered."""
    source = source or ""
    if source.startswith("upload:"):
        token = source.split(":", 1)[1]
        if not re.fullmatch(r"[0-9a-f]{32}", token):
            raise ArchiveError("That upload is not one the studio kept.")
        path = os.path.join(_uploads_dir(), f"{token}.zip")
        if not os.path.isfile(path):
            raise ArchiveError("That upload has expired. Choose the file again.")
        try:
            with open(path + ".name", "r", encoding="utf-8") as handle:
                name = handle.read().strip()
        except OSError:
            name = "archive.zip"
        return path, name
    if source.startswith("downloads:"):
        wanted = source.split(":", 1)[1]
        for hit in find_archives(limit=50):
            if hit["path"] == wanted:
                if hit["downloading"]:
                    raise ArchiveError(STILL_DOWNLOADING)
                return hit["path"], hit["name"]
        raise ArchiveError("That file is no longer in your Downloads folder.")
    raise ArchiveError("Choose an archive from your Downloads folder, or upload one.")


def _discard(source: str) -> None:
    if source.startswith("upload:"):
        try:
            path, _name = _resolve(source)
        except ArchiveError:
            return
        for leftover in (path, path + ".name"):
            try:
                os.remove(leftover)
            except OSError:
                pass


def discard(source: str) -> Dict[str, Any]:
    """Deletes an uploaded copy the creator decided not to import. A Downloads file is never touched."""
    _discard(source or "")
    return {"status": "success"}


def preview_upload(stream, filename: str) -> Dict[str, Any]:
    """Keeps an upload and previews it, deleting the copy again if it cannot be read."""
    source = store_upload(stream, filename)
    try:
        return preview(source)
    except BaseException:
        _discard(source)
        raise


# ---------------------------------------------------------------------------
# Reading the archive
# ---------------------------------------------------------------------------

def _norm(header: str) -> str:
    return " ".join((header or "").replace("﻿", "").strip().strip('"').lower().split())


class _FolderFile:
    """A file of an archive unpacked into a folder, read the way a ZIP member is."""

    def __init__(self, filename: str, path: str, file_size: int):
        self.filename, self.path, self.file_size = filename, path, file_size


def _folder_members(folder: str) -> Dict[str, _FolderFile]:
    """
    The CSVs of an unpacked archive by lower-case base name, shallowest first.

    Held to the limits a ZIP is: as many files, as many bytes in all, each
    file no larger. Links are not followed, so nothing outside the folder is
    read.
    """
    found: Dict[str, _FolderFile] = {}
    count = total = 0
    for directory, subdirs, names in os.walk(folder):
        rel = os.path.relpath(directory, folder)
        if (0 if rel == "." else rel.count(os.sep) + 1) >= MAX_FOLDER_DEPTH:
            subdirs[:] = []
        subdirs.sort()
        for name in sorted(names):
            full = os.path.join(directory, name)
            try:
                stat = os.lstat(full)
            except OSError:
                continue
            if os.path.islink(full) or not os.path.isfile(full):
                continue
            count, total = count + 1, total + stat.st_size
            if count > MAX_MEMBERS:
                raise ArchiveError("That archive holds far more files than LinkedIn's does.")
            if total > MAX_ARCHIVE_BYTES:
                raise ArchiveError("That archive unpacks to more than any LinkedIn archive the studio expects.")
            base = name.lower()
            if base.endswith(".csv") and base not in found:
                found[base] = _FolderFile(os.path.relpath(full, folder).replace(os.sep, "/"), full, stat.st_size)
    return found


def _members(path: str) -> Dict[str, Any]:
    """CSV members by lower-case base name. Refuses archives built to exhaust memory or that cannot be opened."""
    if os.path.isdir(path):
        return _folder_members(path)
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError, ValueError) as error:
        raise _Unreadable("That file is not a ZIP archive LinkedIn produced.") from error
    with archive:
        infos = archive.infolist()
    if len(infos) > MAX_MEMBERS:
        raise ArchiveError("That archive holds far more files than LinkedIn's does.")
    if sum(i.file_size for i in infos) > MAX_ARCHIVE_BYTES:
        raise ArchiveError("That archive unpacks to more than any LinkedIn archive the studio expects.")
    found: Dict[str, zipfile.ZipInfo] = {}
    for info in infos:
        if info.is_dir():
            continue
        base = os.path.basename(info.filename).lower()
        if not base.endswith(".csv"):
            continue
        if info.flag_bits & 0x1:
            raise ArchiveError("That archive is password-protected. LinkedIn's is not; download it again.")
        if info.file_size > 1024 * 1024 and info.file_size > MAX_RATIO * max(info.compress_size, 1):
            raise ArchiveError(f"{info.filename} unpacks to far more than its size. LinkedIn's files do not.")
        if base not in found:
            found[base] = info
    return found


def _read_text(path: str, info: Any) -> str:
    if info.file_size > MAX_MEMBER_BYTES:
        raise ArchiveError(f"{info.filename} is larger than any file in LinkedIn's archive.")
    try:
        if isinstance(info, _FolderFile):
            with open(info.path, "rb") as handle:
                raw = handle.read(MAX_MEMBER_BYTES + 1)
        else:
            with zipfile.ZipFile(path) as archive:
                with archive.open(info) as handle:
                    raw = handle.read(MAX_MEMBER_BYTES + 1)
    except (zipfile.BadZipFile, zlib.error, RuntimeError, OSError, EOFError, NotImplementedError, ValueError) as error:
        raise _Unreadable(f"{info.filename} is damaged and cannot be read. Download the archive again.") from error
    if len(raw) > MAX_MEMBER_BYTES:
        raise ArchiveError(f"{info.filename} is larger than any file in LinkedIn's archive.")
    return raw.decode("utf-8-sig", errors="replace")


def _table(text: str, spec: Dict[str, Any]) -> Tuple[Optional[List[Dict[str, str]]], List[str], str]:
    """
    (rows keyed by the spec's own names, the header found, a problem or "").

    LinkedIn puts a few lines of notes above the header in some files, so the
    header is the first line naming every required column. A row that cannot
    be parsed stops the file there, and the problem says so: what was read is
    kept, and nothing after it is guessed at.
    """
    required: Dict[str, List[str]] = spec["columns"]
    optional: Dict[str, List[str]] = spec.get("optional", {})
    stream = io.StringIO(text)
    first: List[str] = []
    for index in range(MAX_HEADER_SCAN):
        start = stream.tell()
        line = stream.readline()
        if not line:
            break
        try:
            cells = [_norm(c) for c in next(csv.reader([line]))]
        except (csv.Error, StopIteration):
            continue
        if index == 0:
            first = cells
        if not all(any(alias in cells for alias in aliases) for aliases in required.values()):
            continue
        stream.seek(start)
        # Strict, so a stray quote stops the file at that row rather than
        # quietly swallowing every row after it into one field.
        reader = csv.reader(stream, strict=True)
        header = [_norm(c) for c in next(reader)]
        where = {}
        for key, aliases in {**required, **optional}.items():
            for alias in aliases:
                if alias in header:
                    where[key] = header.index(alias)
                    break
        rows: List[Dict[str, str]] = []
        problem = ""
        try:
            for cells in reader:
                if not any(c.strip() for c in cells):
                    continue
                if len(rows) >= MAX_ROWS:
                    problem = f"Only the first {MAX_ROWS:,} rows were read."
                    break
                rows.append({key: (cells[i].strip() if i < len(cells) else "") for key, i in where.items()})
        except csv.Error:
            problem = (f"Row {reader.line_num} could not be read, so the {len(rows)} rows before it were "
                       "read and the rest of the file was not.")
        return rows, header, problem
    return None, first, ""


def _read_source(source: str) -> Tuple[str, str, Dict[str, Any]]:
    """
    (path, display name, what the archive holds) for a source the studio offered.

    A file in Downloads that changed moments ago and does not open is more
    likely still arriving than broken, so it is called that.
    """
    path, name = _resolve(source)
    try:
        return path, name, _parse(path)
    except _Unreadable:
        try:
            fresh = datetime.now().timestamp() - os.path.getmtime(path) < FRESH_FOR.total_seconds()
        except OSError:
            fresh = False
        if source.startswith("downloads:") and fresh:
            raise ArchiveError("This file may still be downloading. Wait for the download to finish, "
                               "then try again.") from None
        raise


def _parse(path: str) -> Dict[str, Any]:
    members = _members(path)
    parsed: Dict[str, Any] = {}
    for kind, spec in FILES.items():
        info = members.get(spec["file"])
        if info is None:
            continue
        rows, header, problem = _table(_read_text(path, info), spec)
        parsed[kind] = {"file": info.filename, "rows": rows, "header": header, "problem": problem}
    others = sorted(
        info.filename for base, info in members.items()
        if base not in {s["file"] for s in FILES.values()}
    )
    size = os.path.getsize(path) if os.path.isfile(path) else sum(i.file_size for i in members.values())
    return {"parsed": parsed, "others": others, "bytes": size}


# ---------------------------------------------------------------------------
# Whose archive it is
# ---------------------------------------------------------------------------

def _words(name: str) -> List[str]:
    """A name as compared: accents, case and punctuation set aside."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", name or "") if not unicodedata.combining(c))
    return re.findall(r"[^\W_]+", plain.casefold())


def _owner(parsed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The member LinkedIn made the archive for, from its Profile.csv, or None when it does not say."""
    rows = (parsed.get("profile") or {}).get("rows")
    if not rows:
        return None
    row = rows[0]
    name = " ".join(p for p in (row.get("first", ""), row.get("last", "")) if p).strip()
    if not name:
        return None
    return {"name": name, "headline": row.get("headline") or None, "profile_url": row.get("profile_url") or None}


def _creator() -> Optional[Dict[str, Any]]:
    """The creator the studio knows: the profile they confirmed is theirs, or None before they have."""
    conn = get_db()
    try:
        row = conn.execute("SELECT vanity, display_name FROM creator_identity "
                           "WHERE id = 1 AND confirmed_at IS NOT NULL").fetchone()
    finally:
        conn.close()
    if not row or not row["vanity"]:
        return None
    return {"name": row["display_name"] or None, "vanity": row["vanity"]}


def _same_person(owner: Dict[str, Any], creator: Dict[str, Any]) -> bool:
    """
    Whether the archive's member is the confirmed creator.

    The profile address decides when the archive gives one. Otherwise the
    names must hold the same words, whatever their case, accents or order: a
    name that only shares a word ("Sample", or "Sample Bob-Jones" for Sample
    Bob) is another person as far as this check knows, so the creator is
    asked. When the studio holds no name for the creator, their profile
    address stands in for it ("sample-bob", "samplebob42").
    """
    match = re.search(r"linkedin\.com/in/([^/?#]+)", owner.get("profile_url") or "")
    if match:
        return _words(unquote(match.group(1))) == _words(creator["vanity"])
    theirs = sorted(_words(owner["name"]))
    if not theirs:
        return False
    if creator["name"]:
        return theirs == sorted(_words(creator["name"]))
    vanity = [w for w in _words(creator["vanity"]) if not w.isdigit()]
    return theirs == sorted(vanity) or "".join(vanity).rstrip("0123456789") == "".join(_words(owner["name"]))


def _ownership(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """
    Whose archive it is, who the studio knows the creator as, and, when they
    are not plainly one person, what the creator must agree to before it is
    imported: everything in an archive fills the creator's own record.
    """
    owner, creator = _owner(parsed), _creator()
    statement = label = ""
    if creator:
        known = creator["name"] or f"linkedin.com/in/{creator['vanity']}"
        known_as = f"{creator['name']} (linkedin.com/in/{creator['vanity']})" if creator["name"] else known
        if owner is None:
            statement = f"This archive does not say whose it is, and the studio knows you as {known_as}."
            label = f"Import this archive as {known}'s own record"
        elif not _same_person(owner, creator):
            statement = f"This archive belongs to {owner['name']}, but the studio knows you as {known_as}."
            label = f"Import {owner['name']}'s archive as {known}'s own record"
    elif owner:
        statement = (f"This archive belongs to {owner['name']}. No profile is confirmed in the studio yet, "
                     "so it cannot check that this is you.")
        label = f"This is my archive: import {owner['name']}'s archive as my own record"
    else:
        statement = "This archive does not say whose it is, and no profile is confirmed in the studio yet."
        label = "This is my archive: import it as my own record"
    return {"owner": owner, "creator": creator, "needs_confirmation": statement, "confirm_label": label}


def preview(source: str) -> Dict[str, Any]:
    """What the archive holds, whose it is, and what would be imported. Writes nothing."""
    path, name, result = _read_source(source)
    files = []
    for kind, spec in FILES.items():
        entry = result["parsed"].get(kind)
        if entry is None:
            continue
        understood = entry["rows"] is not None
        files.append({
            "kind": kind,
            "label": spec["label"],
            "file": entry["file"],
            "rows": len(entry["rows"]) if understood else None,
            "importable": understood and len(entry["rows"]) > 0,
            "default": spec["default"],
            "note": entry["problem"] if understood else
                    "The columns are not the ones the studio knows: " + ", ".join(entry["header"][:12]),
        })
    not_imported = []
    for other in result["others"]:
        base = os.path.basename(other).lower()
        not_imported.append({"file": other, "note": NEVER_IMPORTED.get(base, "Not read by the studio.")})
    return {
        "status": "success",
        "source": source,
        "archive": {"name": name, "bytes": result["bytes"]},
        "files": files,
        "not_imported": not_imported,
        "recognised": bool(files),
        **_ownership(result["parsed"]),
    }


# ---------------------------------------------------------------------------
# Writing it
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _when(text: str) -> Optional[str]:
    """
    A timestamp from LinkedIn's export, as UTC ISO, or None when it cannot be read.

    The export writes UTC as 2024-03-05 10:22:11; a few other spellings are
    accepted. An unreadable date is never replaced with today's.
    """
    text = (text or "").strip()
    for suffix in (" UTC", " GMT", "Z"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M",
                    "%Y/%m/%d %H:%M:%S", "%Y-%m-%d", "%d %b %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def _moment(urn: str) -> Optional[datetime]:
    """When a post was created, from its id: activity, share and ugcPost ids carry milliseconds in their high bits."""
    match = _URN.search(urn or "")
    if not match:
        return None
    try:
        moment = datetime.fromtimestamp((int(match.group(2)) >> 22) / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return moment if datetime(2003, 1, 1, tzinfo=timezone.utc) < moment < datetime(2100, 1, 1, tzinfo=timezone.utc) else None


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _urn(link: str) -> Optional[str]:
    match = _URN.search(unquote(link or ""))
    return f"urn:li:{match.group(1)}:{match.group(2)}" if match else None


def _fingerprint(text: str) -> str:
    """Text as compared: whitespace collapsed, lower case, the page's "...more" cut off."""
    text = " ".join((text or "").split()).lower()
    for tail in ("\u2026more", "...more", "\u2026 more", "... more", "\u2026", "..."):
        if text.endswith(tail):
            text = text[: -len(tail)].rstrip()
    return text


def _texts_agree(a: str, b: str) -> bool:
    """
    Whether two readings of a post's text can be the same post.

    The page shows a post cut before "...more", the archive in full, so the
    shorter must begin the longer. Empty text says nothing either way.
    """
    a, b = _fingerprint(a), _fingerprint(b)
    if not a or not b:
        return True
    shorter = min(len(a), len(b), 160)
    return a[:shorter] == b[:shorter]


# A row the archive brought that no bridge reading has joined yet: it still
# carries the archive's share or ugcPost id.
_ARCHIVE_ROW = "(COALESCE(published_at_source, '') = 'archive' AND activity_urn NOT LIKE 'urn:li:activity:%')"


class _Twins:
    """
    The posts a twin is looked for among, read once and kept in time order.

    A post can only be another reading of one created within TWIN_WINDOW of
    it, so each lookup bisects to that window instead of comparing every post
    the studio holds: an archive of thousands of posts, imported into a studio
    the bridge has filled, is matched in n log n rather than n squared.
    """

    def __init__(self, conn, archive_only: bool = False, from_archive: bool = False,
                 near: Optional[List[float]] = None):
        self._where, self._params = "", []
        if archive_only:
            self._where += " AND published_at_source = 'archive' AND activity_urn NOT LIKE 'urn:li:activity:%'"
        if from_archive:
            self._where += f" AND NOT {_ARCHIVE_ROW}"
        if near:
            # For one lookup, only the posts whose stored date or whose id's
            # moment falls near it are read, and those with no date at all.
            low, high = near[0] - TWIN_WINDOW.total_seconds(), near[-1] + TWIN_WINDOW.total_seconds()
            self._where += (" AND (published_at IS NULL OR substr(published_at, 1, 19) BETWEEN ? AND ?"
                            " OR CAST(substr(activity_urn, length(rtrim(activity_urn, '0123456789')) + 1)"
                            " AS INTEGER) BETWEEN ? AND ?)")
            self._params = [datetime.fromtimestamp(low, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                            datetime.fromtimestamp(high, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                            # SQLite's integers are signed 64-bit; an id read as
                            # a moment late this century would not fit.
                            min(int(low * 1000) << 22, 2 ** 63 - 1), min((int(high * 1000) + 1) << 22, 2 ** 63 - 1)]
        self._times: List[Tuple[float, str]] = []
        self._moments: Dict[str, List[float]] = {}
        self._texts: Dict[str, str] = {}
        self._by_text: Dict[str, List[str]] = {}
        self._last = 0
        self.refresh(conn)

    def refresh(self, conn) -> None:
        """Adds the posts written since the last read, by the bridge or anyone else."""
        added = False
        for rowid, urn, text, published_at in conn.execute(
                "SELECT rowid, activity_urn, text, published_at FROM own_posts WHERE rowid > ?" + self._where,
                (self._last, *self._params)):
            self._last = max(self._last, rowid)
            # Either reading of its time: the date it was stored with, or the
            # moment its own id carries.
            moments = sorted({m.timestamp() for m in (_parse_iso(published_at), _moment(urn)) if m})
            self._moments[urn] = moments
            self._texts[urn] = text or ""
            self._times.extend((at, urn) for at in moments)
            self._by_text.setdefault(_fingerprint(text or ""), []).append(urn)
            added = True
        if added:
            self._times.sort()
        self._last = max(self._last, conn.execute("SELECT COALESCE(MAX(rowid), 0) FROM own_posts").fetchone()[0])

    def find(self, urn: str, text: str, when: Optional[str] = None) -> Optional[str]:
        mine_at = _times_of(urn, when)
        mine = _fingerprint(text)
        best: Optional[Tuple[float, str]] = None
        window = TWIN_WINDOW.total_seconds()
        if mine_at:
            for index in range(bisect.bisect_left(self._times, (mine_at[0] - window, "")), len(self._times)):
                at, other = self._times[index]
                if at > mine_at[-1] + window:
                    break
                if other == urn or other not in self._moments:
                    continue
                gap = min(abs(a - b) for a in mine_at for b in self._moments[other])
                if gap > window or (best and best[0] <= gap):
                    continue
                theirs = self._texts[other]
                # A post with no words to compare (an image, a video, a
                # document with no caption) is matched on its id's moment
                # alone, so it must be close.
                if (not mine or not _fingerprint(theirs)) and gap > 120:
                    continue
                if _texts_agree(text, theirs):
                    best = (gap, other)
        if best:
            return best[1]
        # With no time on one side, only the same words in full, long enough
        # not to be a one-liner anyone might post twice, can say it is the
        # same post.
        if len(mine) >= 30:
            for other in self._by_text.get(mine, []):
                if other != urn and (not mine_at or not self._moments.get(other)):
                    return other
        return None


def _times_of(urn: str, when: Optional[str]) -> List[float]:
    """A post's moments, as timestamps: the date given for it (or its id's), and its id's own."""
    return sorted({m.timestamp() for m in (_parse_iso(when) or _moment(urn), _moment(urn)) if m})


def find_twin(conn, urn: str, text: str, when: Optional[str] = None, archive_only: bool = False,
              from_archive: bool = False) -> Optional[str]:
    """
    The own_posts row that is this post under another id, if one is.

    Used both ways: the archive import looks for a post the bridge already
    read (`from_archive`), and the bridge, reading a post, looks for the
    archive's row of it (`archive_only`), so the two become one row whichever
    came first. Two rows the archive itself brought are never one post: the
    archive gives each post its own id, so a creator who posts the same words
    every week has that many posts.
    """
    near = _times_of(urn, when)
    return _Twins(conn, archive_only=archive_only, from_archive=from_archive, near=near).find(urn, text, when)


class _Batches:
    """
    Writes an import in short transactions, with a pause between them.

    SQLite lets one connection write at a time, and a writer kept waiting gives
    up after the busy timeout. An import that held the lock for all its rows
    made a draft saved meanwhile, or a capture from the bridge, fail. Each
    batch here holds the lock for at most BATCH_SECONDS, and the pause after
    it outlasts SQLite's longest sleep between retries, so a waiting writer
    always gets its turn.

    It also keeps what the import brought (`brought`: kind -> the keys of the
    rows it added), so the import can be removed again, and so a failed one
    takes back what its earlier batches committed.
    """

    def __init__(self, conn):
        self.conn = conn
        self.brought: Dict[str, Any] = {}
        self._kept: Dict[str, Any] = {}
        self._begin()

    def _begin(self) -> None:
        self.conn.execute("BEGIN IMMEDIATE")
        self._started = time.monotonic()

    def add(self, kind: str, key: Any) -> None:
        self.brought.setdefault(kind, []).append(key)

    def row(self) -> bool:
        """Called after each row written. True when a new batch has begun, so what was read may be stale."""
        if time.monotonic() - self._started < BATCH_SECONDS:
            return False
        self.conn.commit()
        self._kept = {k: len(v) if isinstance(v, list) else v for k, v in self.brought.items()}
        time.sleep(BATCH_PAUSE)
        self._begin()
        return True

    def committed(self) -> Dict[str, Any]:
        """What the batches committed so far brought, leaving out the one in progress."""
        return {k: self.brought[k][:kept] if isinstance(kept, int) else kept for k, kept in self._kept.items()}


def _text_key(text: str) -> str:
    # The same key the bridge gives a comment, so one comment read both ways is one row.
    return hashlib.sha256(" ".join(text.split()).lower().encode()).hexdigest()[:24] if text else ""


def _counter() -> Dict[str, int]:
    return {"added": 0, "already_there": 0, "skipped": 0}


def _import_posts(conn, rows: Iterable[Dict[str, str]], batches: _Batches) -> Dict[str, int]:
    tally = _counter()
    now = _now()
    twins = _Twins(conn, from_archive=True)
    for row in rows:
        if batches.row():
            twins.refresh(conn)
        text, urn = row.get("text", ""), _urn(row.get("link", ""))
        if not urn or (not text.strip() and row.get("shared") and not row.get("media")):
            # A row with no post link, or a repost with nothing written. A
            # post with no caption (an image, a video, a document) is still
            # the creator's post, and is kept with no text.
            tally["skipped"] += 1
            continue
        when = _when(row.get("date", "")) or (_moment(urn).isoformat() if _moment(urn) else None)
        existing = conn.execute("SELECT published_at FROM own_posts WHERE activity_urn = ?", (urn,)).fetchone()
        same = urn if existing else twins.find(urn, text, when)
        if same:
            # The bridge's row stays, with its figures. The archive adds what
            # it alone has: the date, and the text in full where the page cut it.
            conn.execute(
                "UPDATE own_posts SET "
                "published_at = COALESCE(published_at, ?), "
                "published_at_source = CASE WHEN published_at IS NULL THEN 'archive' ELSE published_at_source END, "
                "text = CASE WHEN text IS NULL OR length(text) < length(?) THEN ? ELSE text END "
                "WHERE activity_urn = ?",
                (when, text[:10000] or None, text[:10000] or None, same),
            )
            tally["already_there"] += 1
            continue
        conn.execute(
            "INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, reactions, comments, "
            "reposts, impressions, first_seen_at, last_seen_at) VALUES (?, ?, ?, 'archive', NULL, NULL, NULL, NULL, ?, ?)",
            (urn, text[:10000] or None, when, now, now),
        )
        batches.add("posts", urn)
        tally["added"] += 1
    return tally


def _import_comments(conn, rows: Iterable[Dict[str, str]], batches: _Batches) -> Dict[str, int]:
    """One row per comment on a post, keyed as the bridge keys it: the post and the text."""
    tally = _counter()
    for row in rows:
        batches.row()
        message, urn, when = row.get("message", ""), _urn(row.get("link", "")), _when(row.get("date", ""))
        if not message.strip() or not urn or not when:
            # No text, no post, or no date the studio can read: a comment
            # dated today because its date was unreadable would be invented.
            tally["skipped"] += 1
            continue
        cursor = conn.execute(
            "INSERT OR IGNORE INTO outbound_engagements (target_activity_urn, target_author, target_excerpt, kind, "
            "reaction_kind, my_text, my_text_key, first_seen_at, last_seen_at) "
            "VALUES (?, NULL, NULL, 'comment', NULL, ?, ?, ?, ?)",
            (urn, message[:4000], _text_key(message), when, when),
        )
        if cursor.rowcount:
            batches.add("comments", cursor.lastrowid)
        tally["added" if cursor.rowcount else "already_there"] += 1
    return tally


def _import_reactions(conn, rows: Iterable[Dict[str, str]], batches: _Batches) -> Dict[str, int]:
    tally = _counter()
    for row in rows:
        batches.row()
        urn, when = _urn(row.get("link", "")), _when(row.get("date", ""))
        if not urn or not when:
            tally["skipped"] += 1
            continue
        kind = (row.get("type") or "").strip().upper()
        cursor = conn.execute(
            "INSERT OR IGNORE INTO outbound_engagements (target_activity_urn, target_author, target_excerpt, kind, "
            "reaction_kind, my_text, my_text_key, first_seen_at, last_seen_at) "
            "VALUES (?, NULL, NULL, 'reaction', ?, NULL, '', ?, ?)",
            (urn, REACTION_WORDS.get(kind, kind.lower()[:40] or None), when, when),
        )
        if cursor.rowcount:
            batches.add("reactions", cursor.lastrowid)
        tally["added" if cursor.rowcount else "already_there"] += 1
    return tally


def _import_profile(conn, rows: List[Dict[str, str]], batches: _Batches) -> Dict[str, Any]:
    if not rows:
        return {"filled": []}
    row = rows[0]
    values = {
        "display_name": " ".join(p for p in (row.get("first", ""), row.get("last", "")) if p).strip(),
        "headline": row.get("headline", ""),
        "about": row.get("summary", ""),
        "location": row.get("location", ""),
    }
    current = conn.execute(
        "SELECT display_name, headline, about, location, profile_observed_at FROM creator_identity WHERE id = 1"
    ).fetchone()
    if current is None:
        conn.execute("INSERT INTO creator_identity (id) VALUES (1)")
        current = {k: None for k in (*values, "profile_observed_at")}
    filled = []
    for column, value in values.items():
        if value and not (current[column] or "").strip():
            conn.execute(f"UPDATE creator_identity SET {column} = ? WHERE id = 1", (value[:4000],))
            filled.append(column)
            batches.brought.setdefault("profile", {})[column] = value[:4000]
    if filled and not current["profile_observed_at"]:
        observed = _now()
        conn.execute("UPDATE creator_identity SET profile_observed_at = ? WHERE id = 1", (observed,))
        batches.brought["observed_at"] = observed
    return {"filled": filled}


def _span(start: str, end: str) -> str:
    start, end = (start or "").strip(), (end or "").strip()
    if start and end:
        return f"{start} - {end}"
    if start:
        return f"{start} - Present"
    return end


def _import_positions(conn, rows: List[Dict[str, str]], batches: _Batches) -> Dict[str, int]:
    tally = _counter()
    if conn.execute("SELECT COUNT(*) FROM creator_positions").fetchone()[0]:
        tally["already_there"] = len(rows)
        return tally
    now = _now()
    for ordinal, row in enumerate(rows):
        cursor = conn.execute(
            "INSERT INTO creator_positions (ordinal, title, company, date_range, location, description, observed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ordinal, row.get("title") or None, row.get("company") or None,
             _span(row.get("started", ""), row.get("finished", "")) or None,
             row.get("location") or None, (row.get("description") or "")[:4000] or None, now),
        )
        batches.add("positions", cursor.lastrowid)
        tally["added"] += 1
    return tally


def _import_education(conn, rows: List[Dict[str, str]], batches: _Batches) -> Dict[str, int]:
    tally = _counter()
    if conn.execute("SELECT COUNT(*) FROM creator_education").fetchone()[0]:
        tally["already_there"] = len(rows)
        return tally
    now = _now()
    for ordinal, row in enumerate(rows):
        cursor = conn.execute(
            "INSERT INTO creator_education (ordinal, school, degree, date_range, observed_at) VALUES (?, ?, ?, ?, ?)",
            (ordinal, row.get("school") or None, row.get("degree") or None,
             _span(row.get("start", ""), row.get("end", "")) or None, now),
        )
        batches.add("education", cursor.lastrowid)
        tally["added"] += 1
    return tally


def _import_skills(conn, rows: List[Dict[str, str]], batches: _Batches) -> Dict[str, int]:
    tally = _counter()
    now = _now()
    for row in rows:
        batches.row()
        skill = (row.get("name") or "").strip()[:200]
        if not skill:
            tally["skipped"] += 1
            continue
        cursor = conn.execute("INSERT OR IGNORE INTO creator_skills (skill, observed_at) VALUES (?, ?)", (skill, now))
        if cursor.rowcount:
            batches.add("skills", skill)
        tally["added" if cursor.rowcount else "already_there"] += 1
    return tally


def _import_connections(conn, rows: List[Dict[str, str]], batches: _Batches) -> Dict[str, int]:
    tally = _counter()
    now = _now()
    for row in rows:
        batches.row()
        url = (row.get("url") or "").strip()
        if not url.lower().startswith("https://www.linkedin.com/in/"):
            # LinkedIn leaves the URL empty for members who restrict it.
            tally["skipped"] += 1
            continue
        exists = conn.execute("SELECT 1 FROM connections WHERE profile_url = ?", (url,)).fetchone()
        conn.execute(
            "INSERT INTO connections (profile_url, first_name, last_name, company, position, connected_on, "
            "source, imported_at) VALUES (?, ?, ?, ?, ?, ?, 'archive', ?) "
            "ON CONFLICT(profile_url) DO UPDATE SET first_name = excluded.first_name, "
            "last_name = excluded.last_name, company = excluded.company, position = excluded.position, "
            "connected_on = excluded.connected_on, imported_at = excluded.imported_at",
            (url, row.get("first") or None, row.get("last") or None, row.get("company") or None,
             row.get("position") or None, row.get("connected") or None, now),
        )
        if not exists:
            batches.add("connections", url)
        tally["already_there" if exists else "added"] += 1
    return tally


_IMPORTERS = {
    "posts": _import_posts,
    "comments": _import_comments,
    "reactions": _import_reactions,
    "profile": _import_profile,
    "positions": _import_positions,
    "education": _import_education,
    "skills": _import_skills,
    "connections": _import_connections,
}


def import_archive(source: str, include: Optional[List[str]] = None, confirm_owner: bool = False) -> Dict[str, Any]:
    """
    Imports the kinds the creator kept ticked, in short batches (_Batches).

    `include` defaults to every kind marked default. An archive that may be
    another member's is imported only with `confirm_owner`, the creator's
    word that it is theirs. An uploaded copy of the archive is deleted once
    it has been imported.
    """
    path, name, result = _read_source(source)
    wanted = set(include) if include is not None else {k for k, s in FILES.items() if s["default"]}
    unknown = wanted - set(FILES)
    if unknown:
        raise ArchiveError("Not something the archive import reads: " + ", ".join(sorted(unknown)))
    ownership = _ownership(result["parsed"])
    if ownership["needs_confirmation"] and not confirm_owner:
        raise OwnerUnconfirmed(ownership["needs_confirmation"] + " Nothing was imported. Say that it is yours "
                               "to import it.")

    summary: Dict[str, Any] = {}
    conn = get_db()
    try:
        batches = _Batches(conn)
        try:
            for kind, entry in result["parsed"].items():
                if kind == "posts" and entry["rows"] == []:
                    # A Shares.csv with no rows is LinkedIn saying the account
                    # has no posts, which the step needs to know as much as posts.
                    summary[kind] = _counter()
                    continue
                if kind not in wanted:
                    summary[kind] = {"left_out": True}
                    continue
                if entry["rows"] is None:
                    summary[kind] = {"not_understood": True, "columns": entry["header"][:12]}
                    continue
                summary[kind] = _IMPORTERS[kind](conn, entry["rows"], batches)
            cursor = conn.execute(
                "INSERT INTO archive_imports (archive_name, archive_bytes, imported_at, summary) VALUES (?, ?, ?, ?)",
                (name[:200], result["bytes"], _now(), json.dumps(summary, sort_keys=True)),
            )
            if ownership["owner"]:
                batches.brought["owner"] = ownership["owner"]["name"]
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                         (f"{BROUGHT_KEY}{cursor.lastrowid}", json.dumps(batches.brought)))
            conn.commit()
        except BaseException:
            conn.rollback()
            # What the earlier batches committed is taken out again, so an
            # import that fails leaves nothing of itself behind.
            try:
                _remove(conn, batches.committed())
                conn.commit()
            except Exception:
                conn.rollback()
            raise
    finally:
        conn.close()
    _discard(source)
    return {"status": "success", "archive": {"name": name, "bytes": result["bytes"]}, "summary": summary}


def _remove(conn, brought: Dict[str, Any], batches: Optional[_Batches] = None) -> Dict[str, int]:
    """Deletes the rows an import added, by the keys it kept. Returns how many of each went."""
    removed: Dict[str, int] = {}
    deletes = {
        # A post the bridge has since joined carries its activity id, so it is not in this list any more.
        "posts": "DELETE FROM own_posts WHERE activity_urn = ? AND published_at_source = 'archive'",
        "comments": "DELETE FROM outbound_engagements WHERE id = ? AND kind = 'comment'",
        "reactions": "DELETE FROM outbound_engagements WHERE id = ? AND kind = 'reaction'",
        "positions": "DELETE FROM creator_positions WHERE id = ?",
        "education": "DELETE FROM creator_education WHERE id = ?",
        "skills": "DELETE FROM creator_skills WHERE skill = ?",
        "connections": "DELETE FROM connections WHERE profile_url = ?",
    }
    for kind, sql in deletes.items():
        removed[kind] = 0
        for key in brought.get(kind) or []:
            if batches:
                batches.row()
            removed[kind] += conn.execute(sql, (key,)).rowcount
    # A profile field is emptied again only if it still holds what the archive put there.
    removed["profile"] = 0
    for column, value in (brought.get("profile") or {}).items():
        if column in PROFILE_COLUMNS:
            removed["profile"] += conn.execute(
                f"UPDATE creator_identity SET {column} = NULL WHERE id = 1 AND {column} = ?", (value,)).rowcount
    if brought.get("observed_at"):
        conn.execute("UPDATE creator_identity SET profile_observed_at = NULL WHERE id = 1 AND profile_observed_at = ?",
                     (brought["observed_at"],))
    return removed


def remove_last_import() -> Dict[str, Any]:
    """
    Deletes what the last import added, and the record of it.

    For an archive that turns out not to be the creator's, or not the one
    they meant, whether or not a profile has been confirmed. What the import
    found already there is left as it was, and so is a post the bridge has
    since read as the creator's own.
    """
    conn = get_db()
    try:
        last = conn.execute("SELECT id, archive_name FROM archive_imports ORDER BY id DESC LIMIT 1").fetchone()
        if last is None:
            raise ArchiveError("No archive has been imported, so there is nothing to remove.")
        key = f"{BROUGHT_KEY}{last['id']}"
        held = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if held is None:
            raise ArchiveError("This import was made before the studio kept a list of what each import added, "
                               "so it cannot be removed on its own.")
        batches = _Batches(conn)
        try:
            removed = _remove(conn, json.loads(held["value"]), batches)
            conn.execute("DELETE FROM archive_imports WHERE id = ?", (last["id"],))
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    finally:
        conn.close()
    return {"status": "success", "archive": {"name": last["archive_name"]}, "removed": removed}


# ---------------------------------------------------------------------------
# State for the Setup screen
# ---------------------------------------------------------------------------

def mark_requested() -> Dict[str, Any]:
    conn = get_db()
    try:
        with conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (REQUESTED_KEY, _now()))
    finally:
        conn.close()
    return archive_state(look=True)


def mark_no_posts() -> Dict[str, Any]:
    """The creator says their account has no posts, so the archive step is done without any."""
    conn = get_db()
    try:
        with conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (NO_POSTS_KEY, _now()))
    finally:
        conn.close()
    return archive_state(look=True)


def _held_posts(archive_name: str, summary: Dict[str, Any]) -> bool:
    """
    Whether an import brought the creator's posts, or showed there are none.

    LinkedIn sends the archive in two parts: a basic one within minutes
    (profile, connections, no Shares.csv) and the complete one within a day.
    An import held the posts when its Shares.csv was read, or when it was the
    complete archive and had no Shares.csv at all.
    """
    posts = summary.get("posts")
    if isinstance(posts, dict) and "added" in posts:
        return True
    return posts is None and (archive_name or "").lower().startswith("complete")


def archive_state(look: bool = False) -> Dict[str, Any]:
    """
    When it was asked for, what is waiting in Downloads, and the last import.

    Downloads is looked in only when the caller asks (the Setup step, while it
    is open), only once the creator has said they asked LinkedIn for the
    archive, only until an archive with their posts has been imported since
    (LinkedIn's first, basic part has none), and only for LinkedIn's export
    names. `complete` is when the step is done: an import brought the posts,
    or the creator said their account has none.
    """
    conn = get_db()
    try:
        held = {r["key"]: r["value"] for r in conn.execute(
            "SELECT key, value FROM settings WHERE key IN (?, ?)", (REQUESTED_KEY, NO_POSTS_KEY))}
        imports = conn.execute(
            "SELECT archive_name, imported_at, summary FROM archive_imports ORDER BY id").fetchall()
    finally:
        conn.close()
    _sweep_uploads()
    requested_at, no_posts_at = held.get(REQUESTED_KEY), held.get(NO_POSTS_KEY)
    readings = [(r["archive_name"], r["imported_at"], json.loads(r["summary"])) for r in imports]
    with_posts = [at for name, at, summary in readings if _held_posts(name, summary)]
    covered = with_posts + ([no_posts_at] if no_posts_at else [])
    waiting = bool(requested_at) and not any(at >= requested_at for at in covered)
    found = find_archives() if look and waiting else []
    imported_names = {name for name, _at, _summary in readings}
    for hit in found:
        hit["imported"] = hit["name"] in imported_names
    last = readings[-1] if readings else None
    return {
        "download_page": DOWNLOAD_PAGE,
        "requested_at": requested_at,
        "waiting": waiting,
        "found": found,
        # The folders looked in, so the step can say where it is looking.
        "watching": downloads_dirs() if look and waiting else [],
        "complete": bool(covered),
        "no_posts_at": no_posts_at,
        "last_import": {
            "archive_name": last[0],
            "imported_at": last[1],
            "summary": last[2],
            "held_posts": _held_posts(last[0], last[2]),
        } if last else None,
    }


def forget(conn) -> None:
    """Everything the archive brought, for when the creator deletes what the studio holds about them."""
    for table in ("connections", "archive_imports"):
        conn.execute(f"DELETE FROM {table}")
    conn.execute("DELETE FROM settings WHERE key IN (?, ?) OR key LIKE ?",
                 (REQUESTED_KEY, NO_POSTS_KEY, BROUGHT_KEY + "%"))
    for name in os.listdir(_uploads_dir()):
        try:
            os.remove(os.path.join(_uploads_dir(), name))
        except OSError:
            pass


