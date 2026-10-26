"""
Self-Service Support: Diagnostics, Backup, Restore, Export, Reset.
==================================================================
What replaces observability in a product with zero cloud egress.

We never receive a crash report, a log line, or a usage metric. So the user has
to be able to produce all of it on demand, and to recover on their own. Every
function here exists because there is no support engineer who can log in.

The diagnostics bundle is the important one. It is written to be pasted into a
public GitHub issue, which means redaction is a security property, not a
courtesy: this database holds the user's LinkedIn session cookies (li_at,
JSESSIONID) and their AI provider API key.

Redaction uses an ALLOWLIST, not a denylist. A denylist fails open. The day
somebody adds `gemini_api_key` to the settings table, a denylist quietly starts
leaking it, and nobody finds out until a user has already posted their key in
public. An allowlist fails closed: an unrecognised key is redacted by default.

Strict Invariants:
- Zero em-dashes in any code, docstring, or comment.
- Never widen SAFE_SETTING_KEYS without considering what the new key can hold.
- The bundle must remain safe to publish, unmodified, by a non-technical user.
"""

import csv
import errno
import functools
import io
import json
import logging
import os
import platform
import re
import shutil
import sqlite3
import sys
import threading
import zipfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    from . import paths, sqlite_open, changes
    from .migrations import describe as describe_schema, backup_database, SCHEMA_VERSION, MIN_SUPPORTED_SCHEMA
    from ..__version__ import __version__
except ImportError:  # top-level import mode
    import paths
    import sqlite_open
    import changes
    from migrations import describe as describe_schema, backup_database, SCHEMA_VERSION, MIN_SUPPORTED_SCHEMA
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from __version__ import __version__

REDACTED = "<redacted>"

# Settings safe to include in a bundle a user may publish. Anything absent from
# this set is redacted, including keys that do not exist yet.
SAFE_SETTING_KEYS = frozenset({
    "ai_provider",
    "ai_model",
    "ai_status",
    "ai_verified_at",
    "auto_sync_interval_mins",
    "session_status",
    "last_sync",
    "last_token_update",
    "update_check_enabled",
    "update_last_checked",
    "update_last_seen_version",
})

# Cleared by `reset --keep-data`: the AI provider setup and the stored
# LinkedIn session, which are what tends to be wrong. Content tables are never
# touched, and neither is the rest of the settings table.
#
# It used to empty the whole table, which also resumed a paused queue (a
# missing queue_status reads as running, so due posts went out within 30
# seconds) and erased the Brand Studio identity bylines are made from.
CONFIG_TABLES = ("settings",)
RESET_SETTING_KEYS = (
    "ai_provider", "ai_api_key", "ai_model", "ai_base_url", "ai_verified_at", "ai_status",
    "gemini_api_key",
    "li_at", "JSESSIONID", "last_token_update", "session_status",
    # The account those cookies belonged to: the creator's LinkedIn vanity and
    # member URN, stored beside them for Send to LinkedIn. Clearing the cookies
    # and leaving the name of whose they were says who used this computer long
    # after the session itself is gone (noted by the R6 review).
    "linkedin_session_account",
)
# Any later provider setting is named ai_<something>, and goes with the rest.
RESET_SETTING_PREFIX = "ai_"

# Included in a data export. Content the user authored or accumulated, which
# they must be able to take elsewhere.
#
# The second line is the creator's own LinkedIn record, which the bridge reads
# into the studio. It was missing, so the most valuable thing a creator has
# here, their posts with every reading and the history of each lead, could not
# be taken anywhere. creator_identity holds their own contact details, which is
# theirs to export; settings, which holds credentials, is still never listed.
EXPORTABLE_TABLES = ("drafts", "posts", "leads", "lead_interactions",
                     "analytics_daily", "audience_demographics",
                     "creator_identity", "creator_positions", "creator_education", "creator_skills",
                     "own_posts", "post_metric_observations", "outbound_engagements", "lead_stage_events",
                     "connections", "archive_imports",
                     # Cycle 4: each post's viewer demographics by day, and the
                     # creator analytics page read over a longer range.
                     "audience_demographic_readings", "analytics_windows",
                     # From your record (cycle 4, track 7): the creator's asks, the
                     # daily batches built for them, their marks and notes, and what
                     # their archive says they saved and followed.
                     "asks", "daily_view", "daily_run", "card_marks", "record_notes", "archive_records",
                     # Phase 2: account and own content readings, graph points,
                     # and the creator's own reposts.
                     "insight_readings", "insight_daily_points", "own_reposts")

EXPORT_FORMATS = ("json", "csv", "obsidian")


def _has_database() -> bool:
    db_path = paths.get_db_path()
    return os.path.exists(db_path) and os.path.getsize(db_path) > 0


def _no_database_message(doing: str) -> str:
    return (f"There is no studio database at {paths.get_db_path()} yet, so there is nothing to {doing}. "
            f"It is created the first time the studio starts. If your data is somewhere else, run "
            f"`paths` to see why this location was chosen.")


def _connect() -> sqlite3.Connection:
    """
    The active profile's database. ValueError when there is none yet.

    sqlite3.connect creates a missing file, so every command run before the
    first start used to leave an empty database behind and then report on it.
    """
    if not os.path.exists(paths.get_db_path()):
        raise ValueError(_no_database_message("read"))
    conn = sqlite_open.connect(paths.get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _table_names(conn: sqlite3.Connection) -> List[str]:
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]


def redact_settings(rows) -> Dict[str, Any]:
    """
    Applies the allowlist. Returns key -> value or the redaction marker.

    Redacted entries still report whether a value was present, because "the API
    key is empty" and "the API key is set but wrong" are different bugs and we
    need to tell them apart without seeing the key.
    """
    out: Dict[str, Any] = {}
    for row in rows:
        key = row["key"] if isinstance(row, sqlite3.Row) else row[0]
        value = row["value"] if isinstance(row, sqlite3.Row) else row[1]
        if key in SAFE_SETTING_KEYS:
            out[key] = value
        else:
            out[key] = {"redacted": True, "is_set": bool(value), "length": len(value or "")}
    return out


DIAGNOSTICS_PREFIX = "inox_diagnostics_"


def _account_folders() -> List[tuple]:
    """
    (path, placeholder) pairs for the OS account folder, longest first.

    On most machines the account folder is named after the person, first and
    last name, and every path in the bundle starts with it. The placeholder
    still tells us where the state is, relative to it.
    """
    pairs = []
    if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        pairs.append((os.environ["LOCALAPPDATA"], "%LOCALAPPDATA%"))
    home = os.path.expanduser("~")
    if home and len(home.strip("/\\")) > 0 and home != "~":
        pairs.append((home, "~"))
    for path, placeholder in list(pairs):
        if "\\" in path:
            pairs.append((path.replace("\\", "/"), placeholder))
    return sorted(pairs, key=lambda pair: len(pair[0]), reverse=True)


def _without_account_folder(value: Any, pairs: List[tuple]) -> Any:
    if isinstance(value, str):
        for path, placeholder in pairs:
            value = value.replace(path, placeholder)
        return value
    if isinstance(value, dict):
        return {key: _without_account_folder(item, pairs) for key, item in value.items()}
    if isinstance(value, list):
        return [_without_account_folder(item, pairs) for item in value]
    return value


# A log line can carry what somebody typed or who somebody is: a search or a
# message topic in a query string, a name or a comment quoted in an error, a
# LinkedIn profile address, an email. None of that explains a fault, and the
# people it names never agreed to be in a file posted to a public issue. So
# every line the bundle tails is reduced to its shape before it is included.
# The request line of an access entry and a traceback's file names are kept,
# because they are what a maintainer reads.
LOG_REDACTED = "<redacted>"
_REQUEST_LINE = re.compile(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) \S+ HTTP/\d(\.\d)?$")
_SOURCE_FILE = re.compile(r"^[^\s]*\.py$")
_QUERY = re.compile(r"\?[^\s\"']*")
_QUOTED = re.compile(r"\"([^\"]*)\"|'([^']*)'")
_PROFILE = re.compile(r"(/in/|/company/)[^/\s\"'?#]+", re.IGNORECASE)
_MEMBER_URN = re.compile(r"urn:li:(person|member|fsd_profile|fs_miniProfile|fsd_company):[^\s\"',)]+", re.IGNORECASE)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _keep_quoted(match) -> str:
    inner = match.group(1) if match.group(1) is not None else match.group(2)
    quote = '"' if match.group(1) is not None else "'"
    if _REQUEST_LINE.match(inner) or _SOURCE_FILE.match(inner):
        return match.group(0)
    return f"{quote}{LOG_REDACTED}{quote}"


# An exception's message can carry a name without quotes ("ValueError: no
# lead called Esmeralda Winterbottom"). In such a line the exception type and
# the message's shape are kept, and every word that looks like a proper noun
# and does not start a sentence is removed: one starting with a capital and continuing in
# lower case, or one in a script without case, which cannot be told apart from
# a name. Identifiers, numbers, paths and ALL-CAPS codes stay, so "database is
# locked" or "no such table: lead_interactions" read as they did.
_EXCEPTION_LINE = re.compile(r"^(\s*(?:[\w.]+\.)?\w*(?:Error|Exception|Warning|Exit|Interrupt|Failed|Refused)\w*: )(.+)$")
# Letters, with the combining marks of Indic scripts and of accented Latin.
_LETTER_WORD = re.compile(r"(?<![\w<./\\-])(?:[^\W\d_]|[\u0900-\u0DFF\u0300-\u036F])+(?![\w>./\\-])")


def _proper_noun(match) -> str:
    word = match.group(0)
    before = match.string[:match.start()].rstrip()
    if not before or before[-1] in ".:;!?[])":
        return word  # a capital that starts a sentence, or "Errno" in "[Errno 111]"
    caseless = all(ch.lower() == ch.upper() for ch in word)
    title = word[0].isupper() and not word.isupper()
    return LOG_REDACTED if caseless or title else word


def _without_proper_nouns(message: str) -> str:
    message = _LETTER_WORD.sub(_proper_noun, message)
    return re.sub(rf"{re.escape(LOG_REDACTED)}(?:\s+{re.escape(LOG_REDACTED)})+", LOG_REDACTED, message)


def scrub_log_line(line: str) -> str:
    """One log line with nothing anybody typed and nobody's identity left in it."""
    text = _QUERY.sub("?" + LOG_REDACTED, str(line))
    text = _QUOTED.sub(_keep_quoted, text)
    text = _PROFILE.sub(lambda m: m.group(1) + LOG_REDACTED, text)
    text = _MEMBER_URN.sub(lambda m: f"urn:li:{m.group(1)}:{LOG_REDACTED}", text)
    text = _EMAIL.sub(LOG_REDACTED, text)
    exception = _EXCEPTION_LINE.match(text)
    if exception:
        text = exception.group(1) + _without_proper_nouns(exception.group(2))
    return text


# A backup's name carries the label it was given, which can be anything the
# creator typed ("before the Acme pitch"). The studio's own labels are kept.
_BACKUP_NAME = re.compile(r"^(inox_backup_|linkedin_studio_(?:snapshot_)?)(.+?)(_\d{8}_\d{6}.*)$")
_STUDIO_BACKUP_LABELS = frozenset({
    "manual", "pre_restore", "pre_reset", "premigration", "migration", "daily", "auto", "automatic",
    "scheduled", "snapshot",
})


def _backup_name(name: str) -> str:
    match = _BACKUP_NAME.match(name)
    if not match or match.group(2) in _STUDIO_BACKUP_LABELS:
        return name
    return f"{match.group(1)}{LOG_REDACTED}{match.group(3)}"


def collect_diagnostics() -> Dict[str, Any]:
    """
    Everything needed to diagnose a problem on a machine we cannot reach.

    Safe to publish. See the module docstring for why that is a hard property.
    """
    report: Dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "app_version": __version__,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
            "frozen_or_embedded": "runtime" in os.path.normcase(sys.prefix),
        },
        "paths": paths.describe(),
        "schema": None,
        "tables": {},
        "settings": {},
        "backups": [],
        "logs": [],
        "errors": [],
    }

    try:
        report["schema"] = describe_schema()
    except Exception as exc:
        report["errors"].append(f"schema status unavailable: {exc}")

    try:
        # A fresh install has no database yet, which is not a problem to report.
        conn = _connect() if os.path.exists(paths.get_db_path()) else None
        try:
            for name in (_table_names(conn) if conn else []):
                try:
                    count = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
                    report["tables"][name] = count
                except Exception as exc:
                    report["tables"][name] = f"unreadable: {exc}"
            if "settings" in report["tables"]:
                rows = conn.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
                report["settings"] = redact_settings(rows)
        finally:
            if conn:
                conn.close()
    except Exception as exc:
        report["errors"].append(f"database unreadable: {exc}")

    try:
        backups_dir = paths.get_backups_dir()
        for name in sorted(os.listdir(backups_dir))[-10:]:
            full = os.path.join(backups_dir, name)
            report["backups"].append({"name": _backup_name(name), "bytes": os.path.getsize(full)})
    except Exception as exc:
        report["errors"].append(f"backups unreadable: {exc}")

    # Log tail. Absence is normal, not an error: the application logs to the
    # console today, and the directory only fills once file logging is enabled.
    #
    # Earlier bundles are written to the same folder and are not logs: tailing
    # them put 200 lines of the previous bundle inside every new one.
    try:
        logs_dir = paths.get_logs_dir()
        names = [n for n in sorted(os.listdir(logs_dir)) if not n.startswith(DIAGNOSTICS_PREFIX)]
        for name in names[-3:]:
            full = os.path.join(logs_dir, name)
            with open(full, encoding="utf-8", errors="replace") as f:
                tail = f.readlines()[-200:]
            report["logs"].append({"name": name, "last_lines": [scrub_log_line(line.rstrip()) for line in tail]})
    except Exception as exc:
        report["errors"].append(f"logs unreadable: {exc}")

    return _without_account_folder(report, _account_folders())


def write_diagnostics_bundle(destination: Optional[str] = None) -> str:
    """Writes the diagnostics report to a file the user can attach to an issue."""
    report = collect_diagnostics()
    if destination is None:
        # A counter after the stamp, so two bundles in one second do not
        # overwrite each other.
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = os.path.join(paths.get_logs_dir(), f"{DIAGNOSTICS_PREFIX}{stamp}")
        destination, counter = base + ".json", 1
        while os.path.exists(destination):
            counter += 1
            destination = f"{base}_{counter}.json"
    with open(destination, "w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, indent=2, default=str)
    return destination


class BackupNotVerified(sqlite3.DatabaseError):
    """The copy of the database failed SQLite's own check, so no backup was kept."""


# Media that is already compressed. Deflating it again cost 1.8 s per 124 MB
# on the three-year dataset and saved nothing; storing it costs 0.08 s.
STORED_EXTENSIONS = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".heic",
    ".mp4", ".mov", ".webm", ".mp3", ".m4a", ".zip", ".gz", ".pdf",
})


def _unique_path(directory: str, stem: str, extension: str) -> str:
    """A path that does not exist yet: two backups in one second used to share a name."""
    candidate = os.path.join(directory, f"{stem}{extension}")
    counter = 1
    while os.path.exists(candidate):
        counter += 1
        candidate = os.path.join(directory, f"{stem}_{counter}{extension}")
    return candidate


def _compact_copy(clean_label: str, stamp: str) -> Optional[str]:
    """
    A consistent, compact copy of the database, or None when there is none.

    VACUUM INTO reads one snapshot, so the copy is consistent under WAL like
    the backup API's, and it leaves free pages behind: the copy is smaller,
    and bytes freed before secure_delete was on are not carried into it.
    """
    db_path = paths.get_db_path()
    if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
        return None
    target = _unique_path(paths.get_backups_dir(), f"linkedin_studio_snapshot_{clean_label}_{stamp}", ".db")
    source = sqlite_open.connect(db_path, timeout=30.0)
    try:
        source.execute("PRAGMA busy_timeout = 30000")
        source.execute("VACUUM INTO ?", (target,))
    except Exception:
        if os.path.exists(target):
            os.remove(target)
        raise
    finally:
        source.close()
    return target


def _integrity_of(path: str) -> str:
    """PRAGMA integrity_check on a copy: "ok", or what SQLite found."""
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = conn.execute("PRAGMA integrity_check").fetchall()
        finally:
            conn.close()
    except sqlite3.DatabaseError as error:
        # A copy too damaged to check is a copy that failed its check.
        return str(error)
    verdict = "; ".join(str(r[0]) for r in rows[:5])
    return verdict or "no answer"


def _read_back(archive: str, with_database: bool) -> None:
    """Opens the written archive and checks every entry against its checksum."""
    with zipfile.ZipFile(archive) as z:
        broken = z.testzip()
        if broken is not None:
            raise BackupNotVerified(f"the backup could not be read back: {broken} does not match its checksum")
        if with_database:
            with z.open("data/linkedin_studio.db") as handle:
                if not handle.read(16).startswith(SQLITE_HEADER):
                    raise BackupNotVerified("the backup could not be read back: its database is not a database")


def create_backup(label: str = "manual", require_database: bool = True) -> str:
    """
    Full state snapshot: database plus user media, in one ZIP.

    The database is copied with VACUUM INTO first so the captured file is
    internally consistent under WAL, rather than a torn file copy, and compact.

    Each backup is checked as it is made: the copy passes integrity_check
    before it goes in, and the archive is read back against its checksums
    after. One that fails either is removed and BackupNotVerified raised, so a
    damaged copy is never listed beside the good ones. The manifest records
    both checks.

    With no database yet this is refused: it used to write an archive of a few
    hundred bytes, call it a backup and print the command to restore it. Only
    the safety copy before a restore passes require_database=False, to keep any
    media files a database-less install already has.
    """
    if require_database and not _has_database():
        raise ValueError(_no_database_message("back up"))
    clean_label = re.sub(r"[^a-zA-Z0-9_-]", "_", str(label))[:40] or "manual"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = _unique_path(paths.get_backups_dir(), f"inox_backup_{clean_label}_{stamp}", ".zip")

    consistent_db = _compact_copy(clean_label, stamp)

    try:
        verified: Dict[str, Any] = {"checked_at": datetime.now().isoformat(timespec="seconds")}
        if consistent_db:
            verdict = _integrity_of(consistent_db)
            if verdict != "ok":
                raise BackupNotVerified(
                    f"The database failed SQLite's integrity check ({verdict}), so no backup was kept. "
                    f"Your earlier backups are unchanged."
                )
            verified["integrity_check"] = verdict
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            if consistent_db and os.path.exists(consistent_db):
                z.write(consistent_db, "data/linkedin_studio.db")
            assets = paths.get_assets_dir()
            for dirpath, _, filenames in os.walk(assets):
                for name in filenames:
                    full = os.path.join(dirpath, name)
                    stored = os.path.splitext(name)[1].lower() in STORED_EXTENSIONS
                    z.write(full, os.path.join("assets", os.path.relpath(full, assets)),
                            compress_type=zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED)
            # True of every archive that is kept: one failing the read back below is removed.
            verified["archive_read_back"] = True
            z.writestr("backup_manifest.json", json.dumps({
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "app_version": __version__,
                "schema": describe_schema(),
                "label": clean_label,
                # Which creator profile this is. A backup holds one profile only.
                "profile": paths.get_active_profile_id(),
                "verified": verified,
            }, indent=2, default=str))
        _read_back(archive, with_database=bool(consistent_db))
    except Exception:
        # Half an archive is worse than none: it is listed as a backup.
        if os.path.exists(archive):
            os.remove(archive)
        raise
    finally:
        # The intermediate consistent copy is now inside the archive, or useless.
        if consistent_db and os.path.exists(consistent_db):
            os.remove(consistent_db)
    return archive


# ---------------------------------------------------------------------------
# Daily backups and rotation
# ---------------------------------------------------------------------------

# Backups the studio makes on its own, which rotation may remove. One the
# creator made with Back up now or the command line, and the safety copies
# taken before a restore or a reset, are never removed by the studio.
AUTOMATIC_BACKUP_LABELS = ("daily", "pre_cleanup")
KEEP_DAILY, KEEP_WEEKLY, KEEP_MONTHLY = 7, 4, 3
# Bare database copies (before an upgrade, before the demo cleanup): the newest
# of each kind are kept. The newest is the one every upgrade error points at.
DATABASE_COPIES_KEPT = 2
DAILY_BACKUP_EVERY = timedelta(hours=24)
# When the newest backup is old enough to be a fault rather than a wait. One
# whole missed day: the hourly job takes a backup as soon as a day has passed,
# so two days without one means the schedule is not running.
STALE_BACKUP_AFTER = 2 * DAILY_BACKUP_EVERY

_ZIP_NAME = re.compile(r"^inox_backup_(?P<label>.+?)_(?P<stamp>\d{8}_\d{6})(?:_\d+)?\.zip$")
_COPY_NAME = re.compile(r"^linkedin_studio_(?P<reason>.+?)_(?P<stamp>\d{8}_\d{6})(?:_\d+)?\.db$")


def _made_at(name: str, path: str, pattern: "re.Pattern") -> datetime:
    """When a backup was made: the stamp in its name, or the file's time."""
    match = pattern.match(name)
    if match:
        try:
            return datetime.strptime(match.group("stamp"), "%Y%m%d_%H%M%S")
        except ValueError:
            pass
    return datetime.fromtimestamp(os.path.getmtime(path))


def _backups_by_kind() -> Dict[str, List[tuple]]:
    """{"automatic": [(made_at, path)], "zip": [...every backup ZIP], "copy:<reason>": [...]}, newest first."""
    directory = paths.get_backups_dir()
    found: Dict[str, List[tuple]] = {"automatic": [], "zip": []}
    for name in os.listdir(directory):
        full = os.path.join(directory, name)
        if not os.path.isfile(full):
            continue
        zipped = _ZIP_NAME.match(name)
        if zipped:
            entry = (_made_at(name, full, _ZIP_NAME), full)
            if "damaged" not in zipped.group("label"):
                found["zip"].append(entry)
            if zipped.group("label") in AUTOMATIC_BACKUP_LABELS:
                found["automatic"].append(entry)
            continue
        copied = _COPY_NAME.match(name)
        # A snapshot_ copy belongs to a backup being written right now.
        if copied and not copied.group("reason").startswith("snapshot"):
            found.setdefault(f"copy:{copied.group('reason')}", []).append((_made_at(name, full, _COPY_NAME), full))
    for entries in found.values():
        entries.sort(key=lambda entry: entry[0], reverse=True)
    return found


def _generations(entries: List[tuple]) -> set:
    """
    The newest backup of each of 7 days, then of 4 weeks before those, then of
    3 months before those: 14 at most, reaching back about four months.
    """
    keep = set()
    older_than = None
    for count, period in ((KEEP_DAILY, lambda d: d.date()),
                          (KEEP_WEEKLY, lambda d: d.isocalendar()[:2]),
                          (KEEP_MONTHLY, lambda d: (d.year, d.month))):
        # A period the tier before already holds a backup from is not counted again.
        covered = {period(made_at) for made_at, path in entries if path in keep}
        seen: List[Any] = []
        for made_at, path in entries:  # newest first, so the first of a period is its newest
            if len(seen) == count:
                break
            key = period(made_at)
            if (older_than is not None and made_at >= older_than) or key in covered or key in seen:
                continue
            seen.append(key)
            keep.add(path)
        if keep:
            older_than = min(made_at for made_at, path in entries if path in keep)
    return keep


# How long a backup can outlive what it holds: the oldest generation rotation
# keeps. Used to tell a creator when a forgotten person leaves the last backup.
ROTATION_REACH_DAYS = KEEP_DAILY + 7 * (KEEP_WEEKLY + 1) + 31 * KEEP_MONTHLY


def rotate_backups() -> Dict[str, Any]:
    """
    Removes automatic backups beyond 7 daily, 4 weekly and 3 monthly, and bare
    database copies beyond the newest 2 of each kind. Idempotent.

    The newest automatic backup is always kept, and so is every backup the
    creator made. Generations are counted back from the newest backup, not
    from today, so a studio left closed for a month keeps its last good
    copies rather than finding them all too old.
    """
    found = _backups_by_kind()
    keep = _generations(found["automatic"])
    doomed = [path for _, path in found["automatic"] if path not in keep]
    for kind, entries in found.items():
        if kind.startswith("copy:"):
            doomed.extend(path for _, path in entries[DATABASE_COPIES_KEPT:])
    removed, freed = [], 0
    for path in doomed:
        try:
            size = os.path.getsize(path)
            os.remove(path)
        except OSError:
            continue
        removed.append(os.path.basename(path))
        freed += size
    return {"removed": sorted(removed), "freed_bytes": freed, "kept_automatic": len(keep)}


def _manifest_of(archive: str) -> Dict[str, Any]:
    try:
        with zipfile.ZipFile(archive) as z:
            manifest = json.loads(z.read("backup_manifest.json").decode("utf-8"))
        return manifest if isinstance(manifest, dict) else {}
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return {}


def _describe(entry: Optional[tuple]) -> Optional[Dict[str, Any]]:
    if not entry:
        return None
    made_at, path = entry
    verified = _manifest_of(path).get("verified") or {}
    return {
        "name": os.path.basename(path),
        "made_at": made_at.isoformat(timespec="seconds"),
        "bytes": os.path.getsize(path),
        # Backups made before checking began carry no record of it.
        "verified": verified.get("integrity_check") == "ok" if verified else None,
    }


def _dated_sensibly(entries: List[tuple]) -> List[tuple]:
    """
    Backups not dated in the future. One stamped years ahead (a wrong clock
    once, a copy from another machine) used to count as made "within the
    day" until that date, so no daily backup was made at all.
    """
    limit = datetime.now() + timedelta(minutes=5)
    return [entry for entry in entries if entry[0] <= limit]


def backup_schedule(enabled: bool) -> Dict[str, Any]:
    """The newest backup, whether it is overdue, when the next one is due, and how many are kept."""
    found = _backups_by_kind()
    sensible = _dated_sensibly(found["zip"])
    newest = sensible[0] if sensible else None
    next_due = None
    if enabled:
        due = (newest[0] + DAILY_BACKUP_EVERY) if newest else datetime.now()
        next_due = max(due, datetime.now()).isoformat(timespec="seconds")
    # Whether the schedule has stopped producing backups. The hourly job takes
    # one as soon as DAILY_BACKUP_EVERY has passed, so a newest backup older
    # than twice that is the schedule itself not running rather than a day not
    # yet over. Nothing used to treat an old date as a problem, which is how a
    # machine that slept across every hour could go weeks with nothing to
    # restore from. "never" is kept apart from "stale": a profile that has
    # never had a backup may simply have been open for less than the first
    # ten minutes.
    age = (datetime.now() - newest[0]) if newest else None
    return {
        "enabled": enabled,
        "last": _describe(newest),
        "next_due": next_due,
        "age_hours": round(age.total_seconds() / 3600.0, 1) if age else None,
        "stale": bool(enabled and age is not None and age >= STALE_BACKUP_AFTER),
        "never": newest is None,
        "stale_after_hours": round(STALE_BACKUP_AFTER.total_seconds() / 3600.0, 1),
        "automatic_count": len(found["automatic"]),
        "zip_count": len(found["zip"]),
        "keeps": {"daily": KEEP_DAILY, "weekly": KEEP_WEEKLY, "monthly": KEEP_MONTHLY,
                  "database_copies": DATABASE_COPIES_KEPT},
        "directory": paths.get_backups_dir(),
    }


def run_daily_backup(force: bool = False) -> Optional[Dict[str, Any]]:
    """
    The automatic daily backup of the active profile, then rotation.

    None when no backup is due: any backup ZIP made in the last 24 hours, the
    creator's own included, counts. A failure is returned, not raised, so the
    schedule can say what went wrong; rotation does not run after one, so a
    failed day never costs a good older backup.
    """
    if not _has_database():
        return None
    at = datetime.now().isoformat(timespec="seconds")
    try:
        with maintenance_turn():
            found = _dated_sensibly(_backups_by_kind()["zip"])
            if not force and found and datetime.now() - found[0][0] < DAILY_BACKUP_EVERY:
                return None
            try:
                archive = create_backup("daily")
            except Exception as error:
                return {"ok": False, "at": at, "archive": None, "bytes": None, "error": str(error),
                        "rotation": None, "skipped": None}
            return {"ok": True, "at": at, "archive": archive, "bytes": os.path.getsize(archive), "error": None,
                    "rotation": rotate_backups(), "skipped": None}
    except MaintenanceBusy as busy:
        return {"ok": False, "at": at, "archive": None, "bytes": None, "error": None, "rotation": None,
                "skipped": str(busy)}


# ---------------------------------------------------------------------------
# Taking turns: a restore, an archive import, and the studio's own backups
# and cleanups never run at once
# ---------------------------------------------------------------------------

# Held by a restore while it swaps files, and by each backup run or cleanup.
# Reentrant, so the daily run can hold it across its backup and its cleanups.
FILES_LOCK = threading.RLock()
# How long a restore waits for a backup or cleanup that is running to finish.
RESTORE_WAIT_SECONDS = 300
# A restore from the command line works in a .restore-* folder in the
# profile home; one younger than this means a restore is under way there.
RESTORE_STAGING_FRESH = timedelta(hours=2)


class MaintenanceBusy(RuntimeError):
    """A restore or an archive import is running; the job waits for its next turn."""


def _other_work() -> Optional[str]:
    try:
        from . import archive_import
    except ImportError:
        import archive_import
    if archive_import._BUSY.locked():
        return "an archive import is running"
    home = paths.get_profile_home()
    try:
        names = os.listdir(home)
    except OSError:
        names = []
    for name in names:
        full = os.path.join(home, name)
        if name.startswith(".restore-") and os.path.isdir(full) and \
                datetime.now() - datetime.fromtimestamp(os.path.getmtime(full)) < RESTORE_STAGING_FRESH:
            return "a restore is in progress"
    return None


@contextmanager
def maintenance_turn():
    """
    Holds FILES_LOCK for a backup run or a cleanup, or raises MaintenanceBusy
    at once: the job does not wait, it says why and tries again next hour.
    """
    if not FILES_LOCK.acquire(blocking=False):
        raise MaintenanceBusy("a restore, or another backup or cleanup, is running")
    try:
        reason = _other_work()
        if reason:
            raise MaintenanceBusy(reason)
        yield
    finally:
        FILES_LOCK.release()


def _waits_for_maintenance(func):
    """A restore waits for a running backup or cleanup, then holds the others off."""
    @functools.wraps(func)
    def holding(*args, **kwargs):
        if not FILES_LOCK.acquire(timeout=RESTORE_WAIT_SECONDS):
            raise ValueError("A backup or cleanup is still running, so the restore did not start. "
                             "Try again in a few minutes. Nothing was changed.")
        try:
            return func(*args, **kwargs)
        finally:
            FILES_LOCK.release()
    return holding


def reusable_backup(within: timedelta) -> Optional[str]:
    """
    The newest backup made within `within` that holds the studio as it is
    now, so a cleanup can run behind it instead of writing another full copy:
    checked when made, not dated in the future, not a restore's safety copy
    and not older than the last restore (both hold a state that is gone).
    """
    found = _dated_sensibly(_backups_by_kind()["zip"])

    def label(path: str) -> str:
        return _ZIP_NAME.match(os.path.basename(path)).group("label")

    restores = [made_at for made_at, path in found if label(path).startswith("pre_restore")]
    last_restore = max(restores) if restores else None
    for made_at, path in found:
        if datetime.now() - made_at > within:
            break
        if label(path).startswith("pre_restore") or (last_restore and made_at <= last_restore):
            continue
        if ((_manifest_of(path).get("verified") or {}).get("integrity_check")) == "ok":
            return path
    return None


SQLITE_HEADER = b"SQLite format 3\x00"


def _schema_version_of(header: bytes) -> Optional[int]:
    """PRAGMA user_version, read from a database file's first 100 bytes without opening it."""
    if len(header) < 64 or not header.startswith(SQLITE_HEADER):
        return None
    return int.from_bytes(header[60:64], "big")


def _database_header(path: str) -> bytes:
    try:
        with open(path, "rb") as handle:
            return handle.read(100)
    except OSError:
        return b""


def _is_database_copy(path: str) -> bool:
    """A bare SQLite file, such as the copy taken before every schema upgrade."""
    return os.path.isfile(path) and _database_header(path).startswith(SQLITE_HEADER)


def inspect_backup(archive: str) -> Dict[str, Any]:
    """Reads a backup's manifest without restoring it, so a user can check first."""
    if _is_database_copy(archive):
        # linkedin_studio_premigration_<stamp>.db: the database alone, no media
        # and no manifest. It is the only backup the studio takes on its own,
        # and the one every upgrade error points at.
        return {
            "archive": archive,
            "kind": "database",
            "has_database": True,
            "asset_count": 0,
            "manifest": {},
            "created_at": datetime.fromtimestamp(os.path.getmtime(archive)).isoformat(timespec="seconds"),
            "schema_version": _schema_version_of(_database_header(archive)),
        }
    if not os.path.exists(archive) or not zipfile.is_zipfile(archive):
        return {
            "archive": archive,
            "kind": None,
            "has_database": False,
            "asset_count": 0,
            "manifest": {},
            "schema_version": None,
        }
    schema_version = None
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        manifest = {}
        if "backup_manifest.json" in names:
            try:
                manifest = json.loads(z.read("backup_manifest.json").decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                manifest = None
            if not isinstance(manifest, dict):
                # Hand-edited or cut short: nothing in it can be trusted, so
                # the file is refused here rather than half read later.
                raise ValueError("this backup's description file (backup_manifest.json) is damaged, "
                                 "so it cannot be checked or restored")
        if "data/linkedin_studio.db" in names:
            with z.open("data/linkedin_studio.db") as handle:
                schema_version = _schema_version_of(handle.read(100))
    return {
        "archive": archive,
        "kind": "backup",
        "has_database": "data/linkedin_studio.db" in names,
        "asset_count": len([n for n in names if n.startswith("assets/")]),
        "manifest": manifest,
        "created_at": manifest.get("created_at"),
        "schema_version": schema_version,
    }


def _profile_whose_backups_hold(path: str) -> Optional[str]:
    """The profile whose backups folder a file sits in, or None."""
    folder = os.path.normcase(os.path.realpath(os.path.dirname(os.path.abspath(path))))
    for pid in paths.registered_profile_ids():
        home = os.path.join(paths.get_profile_home(pid), "backups")
        if os.path.normcase(os.path.realpath(home)) == folder:
            return pid
    return None


def _refuse_incompatible(info: Dict[str, Any]) -> None:
    """
    ValueError for a backup this build could restore but then not start from.

    A backup made by a newer build used to be restored and reported as done,
    after which the studio refused to start with SchemaTooNewError, and in the
    portable build the window holding that message closed by itself.
    """
    version = info.get("schema_version")
    if version is None:
        return
    made_by = (info.get("manifest") or {}).get("app_version")
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"This backup was made by a newer version of Inox Hydra ({made_by or 'unknown version'}, "
            f"database schema {version}). This studio is {__version__} and reads schemas up to "
            f"{SCHEMA_VERSION}. Update the studio to {made_by or 'that version'} or newer first, then "
            f"restore this backup. Nothing was changed."
        )
    if 0 < version < MIN_SUPPORTED_SCHEMA:
        raise ValueError(
            f"This backup's database (schema {version}) is older than this studio can upgrade "
            f"(schema {MIN_SUPPORTED_SCHEMA} or newer). Nothing was changed."
        )


def restorable_backups() -> List[Dict[str, Any]]:
    """
    The active profile's backups that restore_backup would accept, best first.

    Full backups before bare database copies, each newest first, which is the
    order a creator recovering from a damaged database should try them in.
    A safety copy of a damaged database holds it under damaged/ and is not
    restorable, so it is never offered.
    """
    directory = paths.get_backups_dir()
    found = []
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    for name in names:
        full = os.path.join(directory, name)
        if not os.path.isfile(full):
            continue
        try:
            info = inspect_backup(full)
        except Exception:
            continue
        if not info.get("has_database") or info.get("kind") not in ("backup", "database"):
            continue
        found.append({"path": full, "name": name, "kind": info["kind"],
                      "modified": datetime.fromtimestamp(os.path.getmtime(full)).isoformat(timespec="minutes"),
                      "_mtime": os.path.getmtime(full)})
    found.sort(key=lambda entry: (entry["kind"] != "backup", -entry["_mtime"]))
    for entry in found:
        del entry["_mtime"]
    return found


def restore_command(archive: str) -> str:
    """The exact command that restores `archive`, as doctor and the safe-mode page print it."""
    return f'python -m studio.cli restore "{archive}" --yes'


class ProfileMismatch(ValueError):
    """The backup is of another creator profile than the one it would replace."""


class RestoreFailed(RuntimeError):
    """
    A restore that stopped part way. Everything it had changed was put back.

    Carries the safety backup's path, because a user told only "Error" believes
    nothing happened and never learns that a copy of their state exists.
    """

    def __init__(self, message: str, safety_backup: Optional[str] = None, safety_note: str = ""):
        super().__init__(message)
        self.safety_backup = safety_backup
        self.safety_note = safety_note


def _stage_archive(archive: str, staging: str, assets_root: str) -> List[tuple]:
    """
    Extracts a backup into `staging` and returns the swap plan.

    The plan is (staged file or None, live file) pairs: the database first,
    then its WAL sidecars (None, so stale pages are moved aside rather than
    merged into the restored file), then each media file.
    """
    target_db = paths.get_db_path()
    staged_db = os.path.join(staging, "new", "data", paths.DB_FILENAME)
    os.makedirs(os.path.dirname(staged_db), exist_ok=True)
    plan: List[tuple] = [(staged_db, target_db), (None, target_db + "-wal"), (None, target_db + "-shm")]

    abs_assets_root = os.path.abspath(assets_root)
    with zipfile.ZipFile(archive) as z:
        with z.open("data/linkedin_studio.db") as source, open(staged_db, "wb") as out:
            shutil.copyfileobj(source, out, 1024 * 1024)
        for name in z.namelist():
            if not name.startswith("assets/") or name.endswith("/"):
                continue
            relative = name[len("assets/"):]
            destination = os.path.abspath(os.path.join(assets_root, relative.replace("/", os.sep)))
            if not destination.startswith(abs_assets_root + os.sep) and destination != abs_assets_root:
                continue  # Skip Zip Slip directory traversal
            staged = os.path.join(staging, "new", "assets", os.path.relpath(destination, abs_assets_root))
            os.makedirs(os.path.dirname(staged), exist_ok=True)
            with z.open(name) as source, open(staged, "wb") as out:
                shutil.copyfileobj(source, out, 1024 * 1024)
            plan.append((staged, destination))
    return plan


def _safety_snapshot() -> tuple:
    """
    (archive, note): a backup of the current state, taken before a restore.

    A live database too damaged to read is the commonest reason to restore,
    and the SQLite backup API cannot copy it, which used to stop the restore
    it was protecting. Then the safety copy keeps the database files byte for
    byte under damaged/, where restore will not pick them up by mistake.
    """
    if not _has_database():
        # Restoring onto a new computer: there is nothing to keep but media.
        if not any(files for _, _, files in os.walk(paths.get_assets_dir())):
            return None, "There was no database here yet, so there was nothing to keep a copy of."
        return create_backup("pre_restore", require_database=False), ""
    try:
        return create_backup("pre_restore"), ""
    except sqlite3.DatabaseError as error:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive = os.path.join(paths.get_backups_dir(), f"inox_backup_pre_restore_damaged_{stamp}.zip")
        db = paths.get_db_path()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for path in (db, db + "-wal", db + "-shm"):
                if os.path.exists(path):
                    z.write(path, "damaged/" + os.path.basename(path))
            assets = paths.get_assets_dir()
            for dirpath, _, filenames in os.walk(assets):
                for name in filenames:
                    full = os.path.join(dirpath, name)
                    z.write(full, os.path.join("assets", os.path.relpath(full, assets)))
            z.writestr("backup_manifest.json", json.dumps({
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "app_version": __version__,
                "label": "pre_restore_damaged",
                "profile": paths.get_active_profile_id(),
                "damaged_database": str(error),
            }, indent=2))
        return archive, (f"The current database could not be read ({error}), so the safety copy keeps "
                         f"its files exactly as they were, under damaged/ in that archive.")


def _verify_staged_database(staged_db: str, archive: str) -> None:
    """The extracted database opens and passes SQLite's own check, or ValueError."""
    try:
        conn = sqlite_open.connect(staged_db)
        try:
            verdict = conn.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.DatabaseError as error:
        verdict = str(error)
    if verdict != "ok":
        raise ValueError(f"The database in {archive} is damaged ({verdict}), so it was not restored. "
                         f"Nothing was changed.")


_restore_log = logging.getLogger("studio.support")

# Windows refuses to replace a file another process holds: WinError 32 when
# something has it open, WinError 5 when something has it mapped, which is
# what a virus scanner or the search indexer does for a moment after a file
# is written. Such a holder is gone a moment later, and a restore that gave
# up at the first refusal left the creator where CI's Windows job left it:
# told the restore stopped part way, with nothing they could do. Five tries
# over about three seconds, and every step is still undone if they all fail.
REPLACE_ATTEMPTS = 5
REPLACE_WAIT_S = 0.2


def _someone_holds_it(error: BaseException) -> bool:
    """Whether this failure is another handle on the file rather than a real fault."""
    if not isinstance(error, OSError):
        return False
    if getattr(error, "winerror", None) in (5, 32):
        return True
    return isinstance(error, PermissionError) or error.errno in (errno.EACCES, errno.EPERM, errno.EBUSY)


def _replace(source: str, target: str) -> None:
    """os.replace, tried again while something else holds either file."""
    import time
    for attempt in range(1, REPLACE_ATTEMPTS + 1):
        try:
            os.replace(source, target)
            return
        except OSError as refused:
            if not _someone_holds_it(refused) or attempt == REPLACE_ATTEMPTS:
                raise
            _restore_log.warning("%s is held by something else (%s), attempt %d of %d.",
                                 os.path.basename(target), refused, attempt, REPLACE_ATTEMPTS)
            time.sleep(REPLACE_WAIT_S * attempt)


def _swap(plan: List[tuple], staging: str) -> None:
    """
    Moves each live file aside and the staged one into its place.

    os.replace within one drive is atomic per file. If any step fails, every
    step already taken is undone in reverse, so the live state is either the
    backup's or exactly what it was. Nothing in the studio may hold the
    database while this runs (see restore_backup), and each move is tried
    again while anything outside the studio does.
    """
    done: List[list] = []
    try:
        for index, (staged, target) in enumerate(plan):
            aside = None
            if os.path.lexists(target):
                aside = os.path.join(staging, "old", str(index))
                os.makedirs(os.path.dirname(aside), exist_ok=True)
                _replace(target, aside)
            step = [target, aside, False]
            done.append(step)
            if staged is not None:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                _replace(staged, target)
                step[2] = True
    except Exception as error:
        stuck = []
        for target, aside, placed in reversed(done):
            try:
                if placed and os.path.lexists(target):
                    os.remove(target)
                if aside is not None:
                    _replace(aside, target)
            except OSError:
                stuck.append(target)
        if stuck:
            raise RestoreFailed(
                f"The restore stopped part way ({error}), and {len(stuck)} file(s) could not be put back. "
                f"The originals are in {os.path.join(staging, 'old')}."
            ) from error
        raise RestoreFailed(f"The restore stopped part way ({error}). Everything it had changed was put back.") from error


def _put_the_database_down() -> None:
    """
    Stops the studio's background database work and waits for it to let go.

    The summary catch-up keeps a connection open for as long as it has rows
    to recompute, which is exactly what Windows will not let a restore
    replace. Rows left marked are recomputed by the restored database's
    readers, so stopping costs nothing.
    """
    try:
        from . import post_summary
    except ImportError:
        import post_summary
    if not post_summary.stop_catch_up(30.0):
        _restore_log.warning("The background summary catch-up did not stop before the restore.")
    changes.put_down()


def _let_the_database_go() -> None:
    """Lets the background database work run again, after the swap."""
    try:
        from . import post_summary
    except ImportError:
        import post_summary
    post_summary.resume_catch_up()
    changes.let_go()


@_waits_for_maintenance
def restore_backup(archive: str, take_safety_backup: bool = True, into_active_profile: bool = False) -> Dict[str, Any]:
    """
    Replaces current state with a backup's contents, all or nothing.

    Takes a safety backup of the CURRENT state first, because a user restoring
    the wrong archive would otherwise have destroyed their present data with no
    way back. That is the exact situation nobody can rescue them from.

    The backup is extracted beside the live files and checked before anything
    live is touched, then swapped in file by file. A failure at any point puts
    back what was swapped and raises RestoreFailed naming the safety backup.
    It used to write the database in place and then the media, so a failure
    while writing media left the database already replaced and the user told
    only "Error".

    `archive` is a backup ZIP, or a bare database copy such as the one taken
    before every schema upgrade, which replaces the database and leaves the
    media alone.
    """
    info = inspect_backup(archive)
    if info["kind"] is None:
        raise ValueError(f"{archive} does not exist or is not a valid zip archive or database copy")
    if not info["has_database"]:
        raise ValueError(f"{archive} contains no database and cannot be restored")
    # A backup is one creator profile's. Restoring it into another would put
    # one client's data in another's place, so that takes asking for. A bare
    # database copy has no manifest, so the folder it sits in says whose it is.
    if info["kind"] == "database":
        origin = _profile_whose_backups_hold(archive)
    else:
        manifest = info.get("manifest")
        origin = manifest.get("profile") if isinstance(manifest, dict) else None
    active = paths.get_active_profile_id()
    if origin and origin != active and not into_active_profile:
        raise ProfileMismatch(
            f"This backup is of creator profile '{origin}', and the active profile is '{active}'. "
            f"Switch to '{origin}' first, or restore it into '{active}' on purpose."
        )
    _refuse_incompatible(info)

    assets_root = paths.get_assets_dir()
    staging = os.path.join(paths.get_profile_home(), f".restore-{datetime.now().strftime('%Y%m%d_%H%M%S')}-{os.getpid()}")
    keep_staging = False
    safety = None
    try:
        os.makedirs(staging)
        if info["kind"] == "database":
            target_db = paths.get_db_path()
            staged_db = os.path.join(staging, "new", "data", paths.DB_FILENAME)
            os.makedirs(os.path.dirname(staged_db))
            shutil.copyfile(archive, staged_db)
            plan = [(staged_db, target_db), (None, target_db + "-wal"), (None, target_db + "-shm")]
        else:
            plan = _stage_archive(archive, staging, assets_root)
        _verify_staged_database(plan[0][0], archive)
        for staged, target in plan:
            if staged is not None and os.path.isdir(target):
                raise RestoreFailed(
                    f"{target} is a folder, so the backup's file of that name cannot be put there. "
                    f"Move or rename that folder, then restore again. Nothing was changed."
                )

        safety, safety_note = _safety_snapshot() if take_safety_backup else (None, "")

        try:
            # Every connection in the studio is put down and kept down while
            # the files are swapped. Windows refuses to replace a file any
            # handle holds, and the background summary catch-up, or a screen
            # being read at that moment, was enough to answer "Access is
            # denied" and leave the creator in safe mode with no way out.
            _put_the_database_down()
            try:
                with sqlite_open.files_held():
                    _swap(plan, staging)
            finally:
                _let_the_database_go()
        except RestoreFailed as failed:
            keep_staging = "could not be put back" in str(failed)
            raise RestoreFailed(str(failed), safety_backup=safety, safety_note=safety_note) from failed.__cause__
    finally:
        if not keep_staging:
            shutil.rmtree(staging, ignore_errors=True)

    return {
        "restored_from": archive,
        "safety_backup": safety,
        "safety_note": safety_note,
        "assets_restored": len([1 for staged, _ in plan[3:] if staged is not None]),
        "kind": info["kind"],
        "manifest": info["manifest"],
    }


def export_data(destination: Optional[str] = None, fmt: str = "json") -> str:
    """
    Writes the user's content to a portable file.

    This is the anti lock-in guarantee. A creator must be able to leave with
    their drafts, leads and analytics without asking anyone's permission.

    "obsidian" writes a folder rather than a file: the same record as linked
    notes, see obsidian_export.py.
    """
    if fmt not in EXPORT_FORMATS:
        raise ValueError(f"unsupported export format: {fmt}")
    if fmt == "obsidian":
        try:
            from .obsidian_export import export_obsidian_vault
        except ImportError:
            from obsidian_export import export_obsidian_vault
        return export_obsidian_vault(destination)["path"]

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if destination is None:
        suffix = "json" if fmt == "json" else "zip"
        destination = os.path.join(paths.get_exports_dir(), f"inox_export_{stamp}.{suffix}")

    # Written row by row from the cursor. Every table used to be read into a
    # list of dicts first: 1.1 GB of memory for the JSON export of three
    # years (500,000 interactions), 1.5 GB for the CSV ZIP, on the laptop the
    # creator is leaving with. The files are the same, byte for byte apart
    # from the time they were written.
    #
    # Written under a name that does not look finished and renamed only once
    # complete, so an export that fails part way (a read error, a full disk)
    # leaves nothing behind that could be taken for the whole of it. And read
    # in one transaction, so a capture during the seconds an export takes
    # cannot make two of its tables disagree.
    partial = destination + ".partial"
    conn = _connect()
    try:
        conn.execute("BEGIN")
        available = set(_table_names(conn))
        tables = [table for table in EXPORTABLE_TABLES if table in available]
        # Session cookies and API keys live in `settings`, which is deliberately not
        # exportable. An export is content, not credentials.
        if fmt == "json":
            with open(partial, "w", encoding="utf-8", newline="\n") as f:
                _write_json_export(conn, tables, f)
        else:
            with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as z:
                for table in tables:
                    with z.open(f"{table}.csv", "w") as raw, \
                            io.TextIOWrapper(raw, encoding="utf-8", newline="") as text:
                        writer = None
                        for rows in _row_batches(conn, table):
                            if writer is None:
                                writer = csv.writer(text)
                                writer.writerow(rows[0].keys())
                            writer.writerows([_cell(v) for v in row] for row in rows)
        os.replace(partial, destination)
        return destination
    except BaseException:
        try:
            os.remove(partial)
        except OSError:
            pass
        raise
    finally:
        if conn.in_transaction:
            conn.rollback()
        conn.close()


EXPORT_BATCH_ROWS = 500


def _row_batches(conn: sqlite3.Connection, table: str):
    """The table's rows, EXPORT_BATCH_ROWS at a time, so no table is ever held whole."""
    cursor = conn.execute(f"SELECT * FROM [{table}]")
    while True:
        rows = cursor.fetchmany(EXPORT_BATCH_ROWS)
        if not rows:
            return
        yield rows


def _write_json_export(conn: sqlite3.Connection, tables: List[str], f) -> None:
    """
    What json.dump(..., indent=2, default=str) wrote for the whole export,
    written a row at a time: the same nesting, the same indentation.
    """
    head = json.dumps({"exported_at": datetime.now().isoformat(timespec="seconds"),
                       "app_version": __version__}, indent=2, default=str)
    f.write(head[:-2] + ",\n  \"tables\": {")
    for t, table in enumerate(tables):
        f.write(("," if t else "") + "\n    " + json.dumps(table) + ": [")
        first = True
        for rows in _row_batches(conn, table):
            for row in rows:
                body = json.dumps(dict(row), indent=2, default=str).replace("\n", "\n      ")
                f.write(("\n      " if first else ",\n      ") + body)
                first = False
        f.write("]" if first else "\n    ]")
    f.write("\n  }\n}" if tables else "}\n}")


def _cell(value: Any) -> Any:
    """
    A CSV cell a spreadsheet will show as text.

    Names, headlines and comments come from other people, and a cell that
    begins with =, +, - or @ runs as a formula when the file is opened in a
    spreadsheet. Such a cell is prefixed with an apostrophe, the spreadsheet
    convention for "this is text". JSON exports are left exactly as stored.
    """
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def reset_configuration(keep_data: bool = True) -> Dict[str, Any]:
    """
    Clears configuration so a broken setup can be recovered without data loss.

    Content tables are never touched when keep_data is true, which is the
    default and the only mode the CLI exposes. It clears the settings named in
    RESET_SETTING_KEYS: the AI provider setup and the stored session cookies,
    which is the point, since those are exactly what tends to be wrong. The
    queue's pause, the Brand Studio profile and every other preference stay.
    """
    if not keep_data:
        raise NotImplementedError(
            "Destructive reset is deliberately not implemented. Delete the application "
            f"home at {paths.get_app_home()} manually if that is really what you want."
        )

    safety = create_backup("pre_reset")
    conn = _connect()
    try:
        available = set(_table_names(conn))
        cleared = {}
        cleared_keys: List[str] = []
        if "settings" in available:
            keys = [row[0] for row in conn.execute("SELECT key FROM settings ORDER BY key")]
            cleared_keys = [k for k in keys if k in RESET_SETTING_KEYS or k.startswith(RESET_SETTING_PREFIX)]
            conn.executemany("DELETE FROM settings WHERE key = ?", [(k,) for k in cleared_keys])
            cleared["settings"] = len(cleared_keys)
        conn.commit()
    finally:
        conn.close()
    return {"cleared": cleared, "cleared_keys": cleared_keys, "safety_backup": safety, "data_preserved": True}
