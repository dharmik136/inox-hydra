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
import io
import json
import os
import platform
import re
import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from . import paths
    from .migrations import describe as describe_schema, backup_database, SCHEMA_VERSION, MIN_SUPPORTED_SCHEMA
    from ..__version__ import __version__
except ImportError:  # top-level import mode
    import paths
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
                     "analytics_daily", "audience_demographics", "queue_items",
                     "creator_identity", "creator_positions", "creator_education", "creator_skills",
                     "own_posts", "post_metric_observations", "outbound_engagements", "lead_stage_events",
                     "connections", "archive_imports")

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
    conn = sqlite3.connect(paths.get_db_path())
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


def scrub_log_line(line: str) -> str:
    """One log line with nothing anybody typed and nobody's identity left in it."""
    text = _QUERY.sub("?" + LOG_REDACTED, str(line))
    text = _QUOTED.sub(_keep_quoted, text)
    text = _PROFILE.sub(lambda m: m.group(1) + LOG_REDACTED, text)
    text = _MEMBER_URN.sub(lambda m: f"urn:li:{m.group(1)}:{LOG_REDACTED}", text)
    return _EMAIL.sub(LOG_REDACTED, text)


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


def create_backup(label: str = "manual", require_database: bool = True) -> str:
    """
    Full state snapshot: database plus user media, in one ZIP.

    The database is copied through the SQLite backup API first so the captured
    file is internally consistent under WAL, rather than a torn file copy.

    With no database yet this is refused: it used to write an archive of a few
    hundred bytes, call it a backup and print the command to restore it. Only
    the safety copy before a restore passes require_database=False, to keep any
    media files a database-less install already has.
    """
    if require_database and not _has_database():
        raise ValueError(_no_database_message("back up"))
    clean_label = re.sub(r"[^a-zA-Z0-9_-]", "_", str(label))[:40] or "manual"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = os.path.join(paths.get_backups_dir(), f"inox_backup_{clean_label}_{stamp}.zip")

    consistent_db = backup_database(reason=f"snapshot_{clean_label}")

    try:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            if consistent_db and os.path.exists(consistent_db):
                z.write(consistent_db, "data/linkedin_studio.db")
            assets = paths.get_assets_dir()
            for dirpath, _, filenames in os.walk(assets):
                for name in filenames:
                    full = os.path.join(dirpath, name)
                    z.write(full, os.path.join("assets", os.path.relpath(full, assets)))
            z.writestr("backup_manifest.json", json.dumps({
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "app_version": __version__,
                "schema": describe_schema(),
                "label": clean_label,
                # Which creator profile this is. A backup holds one profile only.
                "profile": paths.get_active_profile_id(),
            }, indent=2, default=str))
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
        conn = sqlite3.connect(staged_db)
        try:
            verdict = conn.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.DatabaseError as error:
        verdict = str(error)
    if verdict != "ok":
        raise ValueError(f"The database in {archive} is damaged ({verdict}), so it was not restored. "
                         f"Nothing was changed.")


def _swap(plan: List[tuple], staging: str) -> None:
    """
    Moves each live file aside and the staged one into its place.

    os.replace within one drive is atomic per file. If any step fails, every
    step already taken is undone in reverse, so the live state is either the
    backup's or exactly what it was.
    """
    done: List[list] = []
    try:
        for index, (staged, target) in enumerate(plan):
            aside = None
            if os.path.lexists(target):
                aside = os.path.join(staging, "old", str(index))
                os.makedirs(os.path.dirname(aside), exist_ok=True)
                os.replace(target, aside)
            step = [target, aside, False]
            done.append(step)
            if staged is not None:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                os.replace(staged, target)
                step[2] = True
    except Exception as error:
        stuck = []
        for target, aside, placed in reversed(done):
            try:
                if placed and os.path.lexists(target):
                    os.remove(target)
                if aside is not None:
                    os.replace(aside, target)
            except OSError:
                stuck.append(target)
        if stuck:
            raise RestoreFailed(
                f"The restore stopped part way ({error}), and {len(stuck)} file(s) could not be put back. "
                f"The originals are in {os.path.join(staging, 'old')}."
            ) from error
        raise RestoreFailed(f"The restore stopped part way ({error}). Everything it had changed was put back.") from error


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
            _swap(plan, staging)
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

    conn = _connect()
    try:
        available = set(_table_names(conn))
        payload: Dict[str, List[Dict[str, Any]]] = {}
        for table in EXPORTABLE_TABLES:
            if table not in available:
                continue
            rows = conn.execute(f"SELECT * FROM [{table}]").fetchall()
            payload[table] = [dict(r) for r in rows]
    finally:
        conn.close()

    # Session cookies and API keys live in `settings`, which is deliberately not
    # exportable. An export is content, not credentials.
    if fmt == "json":
        with open(destination, "w", encoding="utf-8", newline="\n") as f:
            json.dump({
                "exported_at": datetime.now().isoformat(timespec="seconds"),
                "app_version": __version__,
                "tables": payload,
            }, f, indent=2, default=str)
        return destination

    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as z:
        for table, rows in payload.items():
            buffer = io.StringIO()
            if rows:
                writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: _cell(v) for k, v in row.items()})
            z.writestr(f"{table}.csv", buffer.getvalue())
    return destination


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
