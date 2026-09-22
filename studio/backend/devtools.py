"""
Developer Tools: The Maintainer Surface, Absent From The Consumer Build.
=======================================================================

Inox Hydra carries a visual element picker, an annotation ledger, and a set of
inspectors that exist so the people building this product can triage what they
see without leaving the running application. None of that belongs in front of a
creator who bought a scheduler.

This module is the single authority on whether those surfaces exist at all.

The gate model:

  - `INOX_DEV_MODE=1` in the environment turns the maintainer surface on. It is
    off in every artifact `tools/build_portable.py` produces, and off on any
    machine that does not deliberately set it.
  - A database override exists so a maintainer can toggle without restarting a
    long running session. It can only be written while the environment already
    permits dev mode, so a consumer install cannot be talked into enabling
    itself through the API.
  - `require_dev_mode` answers 404, not 403. A consumer build should be
    indistinguishable from a build where these routes were never compiled in.
    403 advertises that something is there.

Why annotations capture so much context:

  A selector and a sentence do not reproduce a bug. The visual bug reporting
  tools that engineers actually keep using (Jam, Marker, Sentry) all converged
  on the same answer: capture the console, the failed requests, the sequence of
  actions that preceded it, and the exact build and schema the user was on. The
  annotation is the human part. Everything around it is the machine part, and
  the machine part is what makes the report actionable a week later.

  Everything captured stays in the local SQLite file. It is scrubbed on the way
  in regardless, because a console line can contain a draft, a lead name, or a
  key, and an exported sheet is a file a person can mail to somebody.

Screens and sections:

  A CSS selector is not a location. It changes the moment somebody restyles a
  card, which orphans every annotation filed against it. A screen key does not.

  The eight screens are real: they are the tab panes in `index.html`, verified
  by id. Sections are resolved from the DOM ancestry of the picked element, and
  a region that has not been labelled with `data-section` is recorded as
  unmapped rather than guessed at. `section_coverage` reports which screens are
  labelled and which are not, so the gap is a number somebody can close instead
  of an invisible inaccuracy.

Strict Invariants:
- Zero em-dashes in any code, docstring, or comment.
- Off by default. A build that ships with this on is a defect.
- Captured context is scrubbed and bounded before it reaches the database.
"""

import hashlib
import json
import os
import platform
import re
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Tuple

try:
    from .database import get_db
    from . import paths
except ImportError:  # pragma: no cover - direct module execution
    from database import get_db
    import paths

try:
    from ..__version__ import __version__ as APP_VERSION
except ImportError:  # pragma: no cover - direct module execution
    try:
        from studio.__version__ import __version__ as APP_VERSION
    except ImportError:
        APP_VERSION = "unknown"


DEV_MODE_ENV_FLAG = "INOX_DEV_MODE"
DEV_MODE_SETTING_KEY = "devtools_runtime_enabled"

TRUTHY = ("1", "true", "yes", "on")

# Bounds on anything the browser hands us. A ring buffer that grew without a
# ceiling would let a noisy console page turn one annotation into a megabyte.
MAX_CONSOLE_ENTRIES = 50
MAX_NETWORK_ENTRIES = 25
MAX_BREADCRUMB_ENTRIES = 40
MAX_ENTRY_CHARS = 500


def _env_allows_dev_mode() -> bool:
    return os.environ.get(DEV_MODE_ENV_FLAG, "").strip().lower() in TRUTHY


def _read_setting(key: str) -> Optional[str]:
    try:
        conn = get_db()
    except Exception:
        return None
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def env_allows_dev_mode() -> bool:
    """
    The environment gate alone, readable before the database exists.

    Needed at application construction time, where is_dev_mode cannot be used
    because it reads a settings table that has not been created yet.
    """
    return _env_allows_dev_mode()


def is_dev_mode() -> bool:
    """
    Whether the maintainer surface exists in this process.

    The environment is the outer gate. The database can only close it, never
    open it, which is what keeps a consumer install from being persuaded to
    enable developer routes through its own API.
    """
    if not _env_allows_dev_mode():
        return False
    override = _read_setting(DEV_MODE_SETTING_KEY)
    if override is None:
        return True
    return override.strip().lower() in TRUTHY


def set_runtime_dev_mode(enabled: bool) -> bool:
    """
    Toggles the surface within a running session. Refuses when the environment
    does not already permit dev mode, so this can never be an escalation path.
    Returns the resulting effective state.
    """
    if not _env_allows_dev_mode():
        return False
    conn = get_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (DEV_MODE_SETTING_KEY, "1" if enabled else "0"),
        )
        conn.commit()
    finally:
        conn.close()
    return bool(enabled)


# ---------------------------------------------------------------------------
# Screen registry
# ---------------------------------------------------------------------------

# Each entry is the id of a real tab pane in index.html. If a screen is renamed
# there and not here, `verify_screen_registry` fails, which is how this stays
# true rather than becoming documentation.
SCREEN_REGISTRY: Dict[str, Dict[str, Any]] = {
    "tab-studio": {"key": "studio", "label": "Post Studio", "owner": "DESIGNER"},
    "tab-queue": {"key": "queue", "label": "Schedule and Queue", "owner": "ENGINEERING_MANAGER"},
    "tab-crm": {"key": "crm", "label": "Inbound CRM", "owner": "ENGINEERING_MANAGER"},
    "tab-inspirations": {"key": "swipe", "label": "Viral Swipe File", "owner": "CEO"},
    "tab-analytics": {"key": "analytics", "label": "Analytics", "owner": "QA_LEAD"},
    "tab-ai-command": {"key": "ai_command", "label": "AI Command", "owner": "ENGINEERING_MANAGER"},
    "tab-docs": {"key": "docs", "label": "Playbook and Docs", "owner": "CEO"},
    "tab-settings": {"key": "settings", "label": "Settings", "owner": "RELEASE_MANAGER"},
}

UNMAPPED_PREFIX = "unmapped:"


def resolve_location(
    tab_id: Optional[str],
    section_hint: Optional[str] = None,
    ancestor_ids: Optional[List[str]] = None,
) -> Tuple[str, str]:
    """
    Turns a picked element into a stable (screen_key, section_key) pair.

    `section_hint` is the value of the nearest `data-section` ancestor, which is
    the only thing here that survives a restyle. Without one, the nearest
    ancestor id is recorded under an `unmapped:` prefix. That is deliberately
    ugly: it should read as an unlabelled region, not as a real section name.
    """
    screen = SCREEN_REGISTRY.get((tab_id or "").strip(), None)
    screen_key = screen["key"] if screen else "unknown"

    hint = (section_hint or "").strip()
    if hint:
        return screen_key, hint

    for candidate in ancestor_ids or []:
        candidate = (candidate or "").strip()
        if candidate:
            return screen_key, f"{UNMAPPED_PREFIX}{candidate}"

    return screen_key, f"{UNMAPPED_PREFIX}root"


def verify_screen_registry(index_html: str) -> List[str]:
    """
    Returns the registry entries that no longer match the markup. An empty list
    means the registry describes the application that actually exists.
    """
    missing = []
    for tab_id in SCREEN_REGISTRY:
        if f'id="{tab_id}"' not in index_html:
            missing.append(tab_id)
    return missing


def section_coverage() -> Dict[str, Any]:
    """
    How much of the interface can be addressed by a name rather than a selector.

    Counts annotations filed against labelled sections against those that landed
    on unmapped regions, per screen. A screen with a high unmapped count is a
    screen where the next restyle will orphan its history.
    """
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT screen_key, section_key, COUNT(*) AS cnt
            FROM internal_sheet_issues
            WHERE screen_key IS NOT NULL
            GROUP BY screen_key, section_key
            """
        ).fetchall()
    except sqlite3.Error:
        return {"screens": [], "labelled": 0, "unmapped": 0}
    finally:
        conn.close()

    per_screen: Dict[str, Dict[str, Any]] = {}
    total_labelled = 0
    total_unmapped = 0
    for row in rows:
        screen = row["screen_key"] or "unknown"
        bucket = per_screen.setdefault(
            screen, {"screen_key": screen, "labelled": 0, "unmapped": 0, "sections": []}
        )
        count = int(row["cnt"])
        section = row["section_key"] or ""
        if section.startswith(UNMAPPED_PREFIX):
            bucket["unmapped"] += count
            total_unmapped += count
        else:
            bucket["labelled"] += count
            total_labelled += count
        bucket["sections"].append({"section_key": section, "count": count})

    return {
        "screens": sorted(per_screen.values(), key=lambda s: -(s["labelled"] + s["unmapped"])),
        "labelled": total_labelled,
        "unmapped": total_unmapped,
    }


# ---------------------------------------------------------------------------
# Capture scrubbing
# ---------------------------------------------------------------------------

# Anything shaped like a credential. Console lines and request URLs are the two
# places a key most plausibly shows up in this application.
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAQ[A-Za-z0-9_\-]{20,}\b"),  # LinkedIn li_at shape
    re.compile(r"(?i)(api[_\-]?key|authorization|bearer|token|password)\s*[=:]\s*\S+"),
]


def scrub(text: Any) -> str:
    """Redacts credential shaped substrings and bounds the length."""
    if text is None:
        return ""
    value = str(text).replace("\u2014", " - ")
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub("[redacted]", value)
    if len(value) > MAX_ENTRY_CHARS:
        value = value[:MAX_ENTRY_CHARS] + "...[truncated]"
    return value


def _bounded(entries: Optional[List[Any]], limit: int, fields: Tuple[str, ...]) -> List[Dict[str, Any]]:
    """Keeps the most recent `limit` entries, scrubbed, with only known fields."""
    if not entries:
        return []
    clean: List[Dict[str, Any]] = []
    for entry in list(entries)[-limit:]:
        if not isinstance(entry, dict):
            clean.append({fields[0]: scrub(entry)})
            continue
        clean.append({field: scrub(entry.get(field)) for field in fields if entry.get(field) is not None})
    return clean


def normalize_capture(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Takes the browser's raw context bundle and returns the bounded, scrubbed
    version that is safe to persist and to hand to somebody in an export.
    """
    payload = payload or {}
    return {
        "console": _bounded(payload.get("console"), MAX_CONSOLE_ENTRIES, ("level", "message", "at")),
        "network": _bounded(payload.get("network"), MAX_NETWORK_ENTRIES, ("method", "url", "status", "ms", "at")),
        "breadcrumbs": _bounded(payload.get("breadcrumbs"), MAX_BREADCRUMB_ENTRIES, ("kind", "label", "at")),
        "a11y": _bounded(payload.get("a11y"), 20, ("rule", "detail")),
    }


def repro_fingerprint(screen_key: str, section_key: str, category: str, console: List[Dict[str, Any]]) -> str:
    """
    A stable hash over where the problem is and what the console said, so two
    reports of the same failure collide instead of becoming two tickets.
    """
    first_error = ""
    for entry in console:
        if (entry.get("level") or "").lower() in ("error", "warn"):
            first_error = entry.get("message", "")
            break
    basis = "|".join([screen_key or "", section_key or "", category or "", first_error[:160]])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Inspectors
# ---------------------------------------------------------------------------

def environment_snapshot() -> Dict[str, Any]:
    """
    The build and machine an annotation was filed from. Stamped onto every
    record, because "works for me" is usually a version difference.
    """
    try:
        from .migrations import SCHEMA_VERSION, get_schema_version
    except ImportError:  # pragma: no cover - direct module execution
        from migrations import SCHEMA_VERSION, get_schema_version

    db_version: Any = "unavailable"
    try:
        conn = get_db()
        try:
            db_version = get_schema_version(conn)
        finally:
            conn.close()
    except Exception:
        pass

    return {
        "app_version": APP_VERSION,
        "schema_version": db_version,
        "schema_expected": SCHEMA_VERSION,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "portable": paths.is_portable(),
    }


# Tables worth counting. Kept explicit so a new table does not silently join the
# inspector with a name nobody vetted.
_INSPECTED_TABLES = (
    "posts",
    "leads",
    "lead_interactions",
    "analytics_daily",
    "audience_demographics",
    "viral_templates",
    "media_assets",
    "generation_tasks",
    "internal_sheet_issues",
)


def state_inspector() -> Dict[str, Any]:
    """
    Row counts and background worker state. The question this answers is "is the
    screen empty because there is no data, or because the query is broken", and
    that question costs ten minutes every time it is asked without this.
    """
    conn = get_db()
    tables: List[Dict[str, Any]] = []
    try:
        present = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        for name in _INSPECTED_TABLES:
            if name not in present:
                tables.append({"table": name, "rows": None, "note": "absent"})
                continue
            count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            tables.append({"table": name, "rows": int(count)})
    finally:
        conn.close()

    # Worker state is read from the rows the workers themselves write rather
    # than from an in process counter, so this stays true for a task that was
    # left mid flight by a crash.
    workers: Dict[str, Any] = {"image_tasks": {}}
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM generation_tasks GROUP BY status"
        ).fetchall()
        workers["image_tasks"] = {row["status"]: int(row["cnt"]) for row in rows}
    except sqlite3.Error:
        workers["image_tasks"] = "unavailable"
    finally:
        conn.close()

    return {
        "tables": tables,
        "workers": workers,
        "environment": environment_snapshot(),
        "database_path": paths.get_db_path(),
    }


def migration_inspector() -> Dict[str, Any]:
    """
    Where this database sits against the ledger, and what a stranger's database
    would do if this build opened it. Read only: applying is a separate call so
    that looking is never the thing that changes state.
    """
    try:
        from .migrations import SCHEMA_VERSION, MIGRATIONS, get_schema_version, pending_migrations
    except ImportError:  # pragma: no cover - direct module execution
        from migrations import SCHEMA_VERSION, MIGRATIONS, get_schema_version, pending_migrations

    conn = get_db()
    try:
        current = get_schema_version(conn)
        pending = [
            {"version": version, "description": description}
            for version, description, _ in pending_migrations(conn)
        ]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()

    backups: List[Dict[str, Any]] = []
    backup_dir = paths.get_backups_dir()
    if os.path.isdir(backup_dir):
        for name in sorted(os.listdir(backup_dir), reverse=True)[:10]:
            full = os.path.join(backup_dir, name)
            try:
                backups.append({"name": name, "bytes": os.path.getsize(full)})
            except OSError:
                continue

    return {
        "current_version": current,
        "expected_version": SCHEMA_VERSION,
        "up_to_date": current == SCHEMA_VERSION,
        "ledger": [{"version": v, "description": d} for v, d, _ in MIGRATIONS],
        "pending": pending,
        "integrity_check": integrity,
        "backups": backups,
    }


def capability_report() -> Dict[str, Any]:
    """What the maintainer surface can currently do, and why it is visible."""
    return {
        "dev_mode": is_dev_mode(),
        "env_flag": DEV_MODE_ENV_FLAG,
        "env_permits": _env_allows_dev_mode(),
        "capabilities": [
            {"key": "element_picker", "label": "Screen concept and element picker"},
            {"key": "context_capture", "label": "Console, network and breadcrumb capture"},
            {"key": "internal_sheet", "label": "Annotation ledger and CSV export"},
            {"key": "state_inspector", "label": "Table counts and worker state"},
            {"key": "migration_inspector", "label": "Schema ledger and backups"},
            {"key": "section_coverage", "label": "Screen and section labelling coverage"},
            {"key": "sheet_portability", "label": "JSON export and import of annotations"},
        ],
        "screens": [
            {"tab_id": tab_id, **meta} for tab_id, meta in SCREEN_REGISTRY.items()
        ],
    }
