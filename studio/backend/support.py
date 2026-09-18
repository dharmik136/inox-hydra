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
import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from . import paths
    from .migrations import describe as describe_schema, backup_database
    from ..__version__ import __version__
except ImportError:  # top-level import mode
    import paths
    from migrations import describe as describe_schema, backup_database
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
EXPORTABLE_TABLES = ("drafts", "posts", "leads", "lead_interactions",
                     "analytics_daily", "audience_demographics", "queue_items")


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
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = os.path.join(paths.get_backups_dir(), f"inox_backup_{label}_{stamp}.zip")

    consistent_db = backup_database(reason=f"snapshot_{label}")

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
            "label": label,
        }, indent=2, default=str))

    # The intermediate consistent copy is now inside the archive.
    if consistent_db and os.path.exists(consistent_db):
        os.remove(consistent_db)
    return archive


def inspect_backup(archive: str) -> Dict[str, Any]:
    """Reads a backup's manifest without restoring it, so a user can check first."""
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        manifest = {}
        if "backup_manifest.json" in names:
            manifest = json.loads(z.read("backup_manifest.json").decode("utf-8"))
    return {
        "archive": archive,
        "has_database": "data/linkedin_studio.db" in names,
        "asset_count": len([n for n in names if n.startswith("assets/")]),
        "manifest": manifest,
    }


def restore_backup(archive: str, take_safety_backup: bool = True) -> Dict[str, Any]:
    """
    Replaces current state with a backup's contents.

    Takes a safety backup of the CURRENT state first, because a user restoring
    the wrong archive would otherwise have destroyed their present data with no
    way back. That is the exact situation nobody can rescue them from.
    """
    info = inspect_backup(archive)
    if not info["has_database"]:
        raise ValueError(f"{archive} contains no database and cannot be restored")

    safety = create_backup("pre_restore") if take_safety_backup else None

    with zipfile.ZipFile(archive) as z:
        db_bytes = z.read("data/linkedin_studio.db")
        target_db = paths.get_db_path()
        # Remove WAL sidecars so the restored file is not merged with stale pages.
        for sidecar in (target_db + "-wal", target_db + "-shm"):
            if os.path.exists(sidecar):
                os.remove(sidecar)
        with open(target_db, "wb") as f:
            f.write(db_bytes)

        assets_root = paths.get_assets_dir()
        restored_assets = 0
        for name in z.namelist():
            if not name.startswith("assets/") or name.endswith("/"):
                continue
            relative = name[len("assets/"):]
            destination = os.path.join(assets_root, relative.replace("/", os.sep))
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            with open(destination, "wb") as f:
                f.write(z.read(name))
            restored_assets += 1

    return {
        "restored_from": archive,
        "safety_backup": safety,
        "assets_restored": restored_assets,
        "manifest": info["manifest"],
    }


def export_data(destination: Optional[str] = None, fmt: str = "json") -> str:
    """
    Writes the user's content to a portable file.

    This is the anti lock-in guarantee. A creator must be able to leave with
    their drafts, leads and analytics without asking anyone's permission.
    """
    if fmt not in ("json", "csv"):
        raise ValueError(f"unsupported export format: {fmt}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if destination is None:
        suffix = "json" if fmt == "json" else "zip"
        destination = os.path.join(paths.get_app_home(), f"inox_export_{stamp}.{suffix}")

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
                    writer.writerow(row)
            z.writestr(f"{table}.csv", buffer.getvalue())
    return destination


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
