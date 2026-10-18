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

import csv
import hashlib
import io
import json
import os
import re
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

MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
# LinkedIn's CSVs are small: years of posts are a few megabytes. These bound
# what a crafted file can make the parser hold, which runs to many times the
# file's own size once it is rows and dictionaries.
MAX_MEMBER_BYTES = 50 * 1024 * 1024
MAX_RATIO = 100
MAX_ROWS = 200_000
MAX_HEADER_SCAN = 50
MAX_MEMBERS = 5000
UPLOAD_TTL = timedelta(hours=24)
# A post is at most 3,000 characters and a comment 1,250; csv's default field
# limit (131,072) is enough for those, but not for the odd long "about".
csv.field_size_limit(max(csv.field_size_limit(), 1_000_000))
# Two posts by one creator whose ids decode to within this much of each other,
# and whose text agrees, are the same post seen two ways: LinkedIn's archive
# names a post by its share or ugcPost id, the page by its activity id.
TWIN_WINDOW = timedelta(minutes=10)
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
        "optional": {"summary": ["summary", "about"], "location": ["geo location", "location"]},
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


# ---------------------------------------------------------------------------
# Finding the archive
# ---------------------------------------------------------------------------

def downloads_dirs() -> List[str]:
    """The creator's Downloads folder, and the one their desktop says, if different."""
    home = os.path.expanduser("~")
    found = [os.path.join(home, "Downloads")]
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


def find_archives(limit: int = 5) -> List[Dict[str, Any]]:
    """LinkedIn export files in Downloads, newest first. Names and sizes only."""
    hits = []
    for directory in downloads_dirs():
        try:
            names = os.listdir(directory)
        except OSError:
            continue
        for name in names:
            if not ARCHIVE_NAME.search(name):
                continue
            full = os.path.join(directory, name)
            try:
                stat = os.stat(full)
            except OSError:
                continue
            if not os.path.isfile(full):
                continue
            hits.append({
                "name": name,
                "path": full,
                "bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
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


def _members(path: str) -> Dict[str, zipfile.ZipInfo]:
    """CSV members by lower-case base name. Refuses archives built to exhaust memory or that cannot be opened."""
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError, ValueError) as error:
        raise ArchiveError("That file is not a ZIP archive LinkedIn produced.") from error
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


def _read_text(path: str, info: zipfile.ZipInfo) -> str:
    if info.file_size > MAX_MEMBER_BYTES:
        raise ArchiveError(f"{info.filename} is larger than any file in LinkedIn's archive.")
    try:
        with zipfile.ZipFile(path) as archive:
            with archive.open(info) as handle:
                raw = handle.read(MAX_MEMBER_BYTES + 1)
    except (zipfile.BadZipFile, zlib.error, RuntimeError, OSError, EOFError, NotImplementedError, ValueError) as error:
        raise ArchiveError(f"{info.filename} is damaged and cannot be read. Download the archive again.") from error
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
    return {"parsed": parsed, "others": others, "bytes": os.path.getsize(path)}


def preview(source: str) -> Dict[str, Any]:
    """What the archive holds and what would be imported. Writes nothing."""
    path, name = _resolve(source)
    result = _parse(path)
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


def find_twin(conn, urn: str, text: str, when: Optional[str] = None, archive_only: bool = False) -> Optional[str]:
    """
    The own_posts row that is this post under another id, if one is.

    Used both ways: the archive import looks for a post the bridge already
    read, and the bridge, reading a post, looks for the archive's row of it,
    so the two become one row whichever came first.
    """
    moment = _parse_iso(when) or _moment(urn)
    mine = _fingerprint(text)
    query = "SELECT activity_urn, text, published_at FROM own_posts WHERE activity_urn != ?"
    if archive_only:
        query += " AND published_at_source = 'archive' AND activity_urn NOT LIKE 'urn:li:activity:%'"
    for row in conn.execute(query, (urn,)):
        # The same words in full, long enough not to be a one-liner anyone
        # might post twice, are the same post whenever it was read.
        if len(mine) >= 30 and _fingerprint(row[1] or "") == mine:
            return row[0]
        # Either reading of the other row's time: the date it was stored with,
        # or the moment its own id carries.
        gaps = [abs(other - mine_at) for other in (_parse_iso(row[2]), _moment(row[0])) if other
                for mine_at in (moment, _moment(urn)) if mine_at]
        if not gaps or min(gaps) > TWIN_WINDOW:
            continue
        if not text and not row[1] and min(gaps) > timedelta(minutes=2):
            continue
        if _texts_agree(text, row[1] or ""):
            return row[0]
    return None


def _text_key(text: str) -> str:
    # The same key the bridge gives a comment, so one comment read both ways is one row.
    return hashlib.sha256(" ".join(text.split()).lower().encode()).hexdigest()[:24] if text else ""


def _counter() -> Dict[str, int]:
    return {"added": 0, "already_there": 0, "skipped": 0}


def _import_posts(conn, rows: Iterable[Dict[str, str]]) -> Dict[str, int]:
    tally = _counter()
    now = _now()
    for row in rows:
        text, urn = row.get("text", ""), _urn(row.get("link", ""))
        if not text.strip() or not urn:
            # A repost with nothing written, or a row with no post link.
            tally["skipped"] += 1
            continue
        when = _when(row.get("date", "")) or (_moment(urn).isoformat() if _moment(urn) else None)
        existing = conn.execute("SELECT published_at FROM own_posts WHERE activity_urn = ?", (urn,)).fetchone()
        same = urn if existing else find_twin(conn, urn, text, when)
        if same:
            # The bridge's row stays, with its figures. The archive adds what
            # it alone has: the date, and the text in full where the page cut it.
            conn.execute(
                "UPDATE own_posts SET "
                "published_at = COALESCE(published_at, ?), "
                "published_at_source = CASE WHEN published_at IS NULL THEN 'archive' ELSE published_at_source END, "
                "text = CASE WHEN text IS NULL OR length(text) < length(?) THEN ? ELSE text END "
                "WHERE activity_urn = ?",
                (when, text[:10000], text[:10000], same),
            )
            tally["already_there"] += 1
            continue
        conn.execute(
            "INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, reactions, comments, "
            "reposts, impressions, first_seen_at, last_seen_at) VALUES (?, ?, ?, 'archive', NULL, NULL, NULL, NULL, ?, ?)",
            (urn, text[:10000], when, now, now),
        )
        tally["added"] += 1
    return tally


def _import_comments(conn, rows: Iterable[Dict[str, str]]) -> Dict[str, int]:
    """One row per comment on a post, keyed as the bridge keys it: the post and the text."""
    tally = _counter()
    for row in rows:
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
        tally["added" if cursor.rowcount else "already_there"] += 1
    return tally


def _import_reactions(conn, rows: Iterable[Dict[str, str]]) -> Dict[str, int]:
    tally = _counter()
    for row in rows:
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
        tally["added" if cursor.rowcount else "already_there"] += 1
    return tally


def _import_profile(conn, rows: List[Dict[str, str]]) -> Dict[str, Any]:
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
        "SELECT display_name, headline, about, location FROM creator_identity WHERE id = 1").fetchone()
    if current is None:
        conn.execute("INSERT INTO creator_identity (id) VALUES (1)")
        current = {k: None for k in values}
    filled = []
    for column, value in values.items():
        if value and not (current[column] or "").strip():
            conn.execute(f"UPDATE creator_identity SET {column} = ? WHERE id = 1", (value[:4000],))
            filled.append(column)
    if filled:
        conn.execute("UPDATE creator_identity SET profile_observed_at = COALESCE(profile_observed_at, ?) WHERE id = 1",
                     (_now(),))
    return {"filled": filled}


def _span(start: str, end: str) -> str:
    start, end = (start or "").strip(), (end or "").strip()
    if start and end:
        return f"{start} - {end}"
    if start:
        return f"{start} - Present"
    return end


def _import_positions(conn, rows: List[Dict[str, str]]) -> Dict[str, int]:
    tally = _counter()
    if conn.execute("SELECT COUNT(*) FROM creator_positions").fetchone()[0]:
        tally["already_there"] = len(rows)
        return tally
    now = _now()
    for ordinal, row in enumerate(rows):
        conn.execute(
            "INSERT INTO creator_positions (ordinal, title, company, date_range, location, description, observed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ordinal, row.get("title") or None, row.get("company") or None,
             _span(row.get("started", ""), row.get("finished", "")) or None,
             row.get("location") or None, (row.get("description") or "")[:4000] or None, now),
        )
        tally["added"] += 1
    return tally


def _import_education(conn, rows: List[Dict[str, str]]) -> Dict[str, int]:
    tally = _counter()
    if conn.execute("SELECT COUNT(*) FROM creator_education").fetchone()[0]:
        tally["already_there"] = len(rows)
        return tally
    now = _now()
    for ordinal, row in enumerate(rows):
        conn.execute(
            "INSERT INTO creator_education (ordinal, school, degree, date_range, observed_at) VALUES (?, ?, ?, ?, ?)",
            (ordinal, row.get("school") or None, row.get("degree") or None,
             _span(row.get("start", ""), row.get("end", "")) or None, now),
        )
        tally["added"] += 1
    return tally


def _import_skills(conn, rows: List[Dict[str, str]]) -> Dict[str, int]:
    tally = _counter()
    now = _now()
    for row in rows:
        skill = (row.get("name") or "").strip()[:200]
        if not skill:
            tally["skipped"] += 1
            continue
        cursor = conn.execute("INSERT OR IGNORE INTO creator_skills (skill, observed_at) VALUES (?, ?)", (skill, now))
        tally["added" if cursor.rowcount else "already_there"] += 1
    return tally


def _import_connections(conn, rows: List[Dict[str, str]]) -> Dict[str, int]:
    tally = _counter()
    now = _now()
    for row in rows:
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


def import_archive(source: str, include: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Imports the kinds the creator kept ticked, in one transaction.

    `include` defaults to every kind marked default. An uploaded copy of the
    archive is deleted once it has been imported.
    """
    path, name = _resolve(source)
    result = _parse(path)
    wanted = set(include) if include is not None else {k for k, s in FILES.items() if s["default"]}
    unknown = wanted - set(FILES)
    if unknown:
        raise ArchiveError("Not something the archive import reads: " + ", ".join(sorted(unknown)))

    summary: Dict[str, Any] = {}
    conn = get_db()
    try:
        with conn:
            for kind, entry in result["parsed"].items():
                if kind not in wanted:
                    summary[kind] = {"left_out": True}
                    continue
                if entry["rows"] is None:
                    summary[kind] = {"not_understood": True, "columns": entry["header"][:12]}
                    continue
                summary[kind] = _IMPORTERS[kind](conn, entry["rows"])
            conn.execute(
                "INSERT INTO archive_imports (archive_name, archive_bytes, imported_at, summary) VALUES (?, ?, ?, ?)",
                (name[:200], result["bytes"], _now(), json.dumps(summary, sort_keys=True)),
            )
    finally:
        conn.close()
    _discard(source)
    return {"status": "success", "archive": {"name": name, "bytes": result["bytes"]}, "summary": summary}


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


def archive_state(look: bool = False) -> Dict[str, Any]:
    """
    When it was asked for, what is waiting in Downloads, and the last import.

    Downloads is looked in only when the caller asks (the Setup step, while it
    is open), only once the creator has said they asked LinkedIn for the
    archive, only until an archive has been imported since, and only for
    LinkedIn's export names.
    """
    conn = get_db()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (REQUESTED_KEY,)).fetchone()
        last = conn.execute(
            "SELECT archive_name, imported_at, summary FROM archive_imports ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        conn.close()
    _sweep_uploads()
    requested_at = row["value"] if row else None
    waiting = bool(requested_at) and (last is None or last["imported_at"] < requested_at)
    return {
        "download_page": DOWNLOAD_PAGE,
        "requested_at": requested_at,
        "waiting": waiting,
        "found": find_archives() if look and waiting else [],
        "last_import": {
            "archive_name": last["archive_name"],
            "imported_at": last["imported_at"],
            "summary": json.loads(last["summary"]),
        } if last else None,
    }


def forget(conn) -> None:
    """Everything the archive brought, for when the creator deletes what the studio holds about them."""
    for table in ("connections", "archive_imports"):
        conn.execute(f"DELETE FROM {table}")
    conn.execute("DELETE FROM settings WHERE key = ?", (REQUESTED_KEY,))
    for name in os.listdir(_uploads_dir()):
        try:
            os.remove(os.path.join(_uploads_dir(), name))
        except OSError:
            pass


