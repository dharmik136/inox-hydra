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

# Cleared by `reset --keep-data`. Content tables are never touched.
CONFIG_TABLES = ("settings",)

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


def _connect() -> sqlite3.Connection:
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
        conn = _connect()
        try:
            for name in _table_names(conn):
                try:
                    count = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
                    report["tables"][name] = count
                except Exception as exc:
                    report["tables"][name] = f"unreadable: {exc}"
            if "settings" in report["tables"]:
                rows = conn.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
                report["settings"] = redact_settings(rows)
        finally:
            conn.close()
    except Exception as exc:
        report["errors"].append(f"database unreadable: {exc}")

    try:
        backups_dir = paths.get_backups_dir()
        for name in sorted(os.listdir(backups_dir))[-10:]:
            full = os.path.join(backups_dir, name)
            report["backups"].append({"name": name, "bytes": os.path.getsize(full)})
    except Exception as exc:
        report["errors"].append(f"backups unreadable: {exc}")

    # Log tail. Absence is normal, not an error: the application logs to the
    # console today, and the directory only fills once file logging is enabled.
    try:
        logs_dir = paths.get_logs_dir()
        for name in sorted(os.listdir(logs_dir))[-3:]:
            full = os.path.join(logs_dir, name)
            with open(full, encoding="utf-8", errors="replace") as f:
                tail = f.readlines()[-200:]
            report["logs"].append({"name": name, "last_lines": [line.rstrip() for line in tail]})
    except Exception as exc:
        report["errors"].append(f"logs unreadable: {exc}")

    return report


def write_diagnostics_bundle(destination: Optional[str] = None) -> str:
    """Writes the diagnostics report to a file the user can attach to an issue."""
    report = collect_diagnostics()
    if destination is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = os.path.join(paths.get_logs_dir(), f"inox_diagnostics_{stamp}.json")
    with open(destination, "w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, indent=2, default=str)
    return destination


def create_backup(label: str = "manual") -> str:
    """
    Full state snapshot: database plus user media, in one ZIP.

    The database is copied through the SQLite backup API first so the captured
    file is internally consistent under WAL, rather than a torn file copy.
    """
    clean_label = re.sub(r"[^a-zA-Z0-9_-]", "_", str(label))[:40] or "manual"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = os.path.join(paths.get_backups_dir(), f"inox_backup_{clean_label}_{stamp}.zip")

    consistent_db = backup_database(reason=f"snapshot_{clean_label}")

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

    # The intermediate consistent copy is now inside the archive.
    if consistent_db and os.path.exists(consistent_db):
        os.remove(consistent_db)
    return archive


SQLITE_HEADER = b"SQLite format 3\x00"


def _schema_version_of(header: bytes) -> Optional[int]:
    """PRAGMA user_version, read from a database file's first 100 bytes without opening it."""
    if len(header) < 64 or not header.startswith(SQLITE_HEADER):
        return None
    return int.from_bytes(header[60:64], "big")


def inspect_backup(archive: str) -> Dict[str, Any]:
    """Reads a backup's manifest without restoring it, so a user can check first."""
    if not os.path.exists(archive) or not zipfile.is_zipfile(archive):
        return {
            "archive": archive,
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
            manifest = json.loads(z.read("backup_manifest.json").decode("utf-8"))
        if "data/linkedin_studio.db" in names:
            with z.open("data/linkedin_studio.db") as handle:
                schema_version = _schema_version_of(handle.read(100))
    return {
        "archive": archive,
        "has_database": "data/linkedin_studio.db" in names,
        "asset_count": len([n for n in names if n.startswith("assets/")]),
        "manifest": manifest,
        "schema_version": schema_version,
    }


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
    """
    if not os.path.exists(archive) or not zipfile.is_zipfile(archive):
        raise ValueError(f"{archive} does not exist or is not a valid zip archive")

    info = inspect_backup(archive)
    if not info["has_database"]:
        raise ValueError(f"{archive} contains no database and cannot be restored")
    # A backup is one creator profile's. Restoring it into another would put
    # one client's data in another's place, so that takes asking for.
    origin = (info.get("manifest") or {}).get("profile")
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
        plan = _stage_archive(archive, staging, assets_root)
        _verify_staged_database(plan[0][0], archive)
        for staged, target in plan:
            if staged is not None and os.path.isdir(target):
                raise RestoreFailed(
                    f"{target} is a folder, so the backup's file of that name cannot be put there. "
                    f"Move or rename that folder, then restore again. Nothing was changed."
                )

        safety = create_backup("pre_restore") if take_safety_backup else None

        try:
            _swap(plan, staging)
        except RestoreFailed as failed:
            keep_staging = "could not be put back" in str(failed)
            raise RestoreFailed(str(failed), safety_backup=safety) from failed.__cause__
    finally:
        if not keep_staging:
            shutil.rmtree(staging, ignore_errors=True)

    return {
        "restored_from": archive,
        "safety_backup": safety,
        "assets_restored": len([1 for staged, _ in plan[3:] if staged is not None]),
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
    default and the only mode the CLI exposes. Clearing settings also clears the
    stored session cookies and AI key, which is the point: those are exactly
    what tends to be wrong.
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
        for table in CONFIG_TABLES:
            if table in available:
                before = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
                conn.execute(f"DELETE FROM [{table}]")
                cleared[table] = before
        conn.commit()
    finally:
        conn.close()
    return {"cleared": cleared, "safety_backup": safety, "data_preserved": True}
