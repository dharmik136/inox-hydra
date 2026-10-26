"""
Creator Profiles: One Database per Creator.
===========================================

Each creator profile is its own folder with its own database, media, backups
and exports (see paths.py). Switching profile switches which folder every
connection opens, so one client's posts, leads and drafts cannot appear in
another's screens, backups or exports, and no query has to remember a filter.

The first profile, "default", is the application home itself, so an install
from before profiles existed keeps its data where it was. The others are
listed in profiles/profiles.json with their display details. More than one
profile is the agency tier, so creating a second one asks the licence.

Profiles used to be rows in a creator_accounts table inside the one shared
database, with an account_id column that nothing filtered by: switching
profile changed the avatar and nothing else. Those rows are adopted into the
registry the first time it is read, and each gets a database of its own.

Invariants:
- Zero literal em-dashes across all code, docstrings, and comments.
- The default profile cannot be deleted.
- Deleting a profile deletes its folder, and only when the caller repeats the
  profile's name. Nothing else ever removes a profile's data.
"""

import os
import re
import shutil
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from . import paths
    from .database import get_db, init_db, seed_initial_data
    from .migrations import SchemaTooNewError, SchemaTooOldError
    from . import licensing
except ImportError:
    import paths
    from database import get_db, init_db, seed_initial_data
    from migrations import SchemaTooNewError, SchemaTooOldError
    import licensing


MAX_ACCOUNT_NAME_LENGTH = 120
MAX_HEADLINE_LENGTH = 300
MAX_VANITY_LENGTH = 100

# Creating, switching and deleting read the registry, act, and write it back.
# Two at once could both pass the licence's limit, or one could drop the
# other's entry, so they take turns.
_REGISTRY_LOCK = threading.RLock()


def _compute_initials(name: str) -> str:
    """Computes a clean 2-character initials string from a person's or brand's name."""
    clean = re.sub(r"[^\w\s]", "", (name or "").strip())
    parts = clean.split()
    if not parts:
        return "CR"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

def _adopt_legacy_accounts() -> None:
    """
    Moves profiles recorded in the old creator_accounts table into the registry.

    Runs once, when there is no registry yet. Their data never was separated,
    so it all stays with the default profile; each adopted profile starts with
    an empty database of its own the first time it is opened.
    """
    if os.path.exists(paths.get_profiles_file()):
        return
    with paths.using_profile(paths.DEFAULT_PROFILE_ID):
        db_path = paths.get_db_path()
        if not os.path.exists(db_path):
            return
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    "SELECT id, name, vanity, headline, avatar_initials, is_default, created_at "
                    "FROM creator_accounts ORDER BY created_at"
                ).fetchall()
            finally:
                conn.close()
        except sqlite3.Error:
            return
    entries = []
    taken = {paths.DEFAULT_PROFILE_ID}
    for row in rows:
        raw = (row["id"] or "").strip().lower()
        if row["is_default"] or raw == paths.DEFAULT_PROFILE_ID:
            continue
        # The old code made ids with \w, so underscores and accented letters
        # are possible. Their data never was separate, so the id can change.
        pid = re.sub(r"[^a-z0-9-]+", "-", raw).strip("-")[:48] or f"acc-{uuid.uuid4().hex[:8]}"
        while pid in taken or not paths.is_valid_profile_id(pid) or paths.is_reserved_profile_id(pid):
            pid = f"acc-{uuid.uuid4().hex[:8]}"
        taken.add(pid)
        entries.append({
            "id": pid,
            "name": row["name"] or pid,
            "vanity": row["vanity"] or "",
            "headline": row["headline"] or "",
            "avatar_initials": row["avatar_initials"] or _compute_initials(row["name"] or pid),
            "created_at": row["created_at"] or _now(),
        })
    if entries:
        paths.write_profiles({"active": paths.DEFAULT_PROFILE_ID, "profiles": entries})


def _registry() -> Dict[str, Any]:
    _adopt_legacy_accounts()
    return paths.read_profiles()


def _default_details() -> Dict[str, str]:
    """
    How the default profile is named: what the creator set, then the profile
    they confirmed in Setup, then a plain label. Never an invented person.
    """
    entry = next((p for p in _registry()["profiles"] if p["id"] == paths.DEFAULT_PROFILE_ID), None)
    if entry and entry.get("name"):
        return {"name": entry["name"], "vanity": entry.get("vanity", ""), "headline": entry.get("headline", "")}
    with paths.using_profile(paths.DEFAULT_PROFILE_ID):
        db_path = paths.get_db_path()
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row
                try:
                    row = conn.execute(
                        "SELECT display_name, vanity, headline FROM creator_identity "
                        "WHERE id = 1 AND confirmed_at IS NOT NULL"
                    ).fetchone()
                finally:
                    conn.close()
                if row and row["display_name"]:
                    return {"name": row["display_name"], "vanity": row["vanity"] or "", "headline": row["headline"] or ""}
            except sqlite3.Error:
                pass
    return {"name": "My studio", "vanity": "", "headline": ""}


def _counts(profile_id: str) -> Dict[str, int]:
    """Posts, drafts and leads in one profile's own database, read only."""
    with paths.using_profile(profile_id):
        db_path = os.path.join(paths.get_profile_home(), "data", paths.DB_FILENAME)
    counts = {"posts_count": 0, "drafts_count": 0, "leads_count": 0}
    if not os.path.exists(db_path):
        return counts
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            # A Composer draft is a post with status 'draft'. The legacy drafts
            # table is not what the Composer writes, so counting it said a
            # profile with drafts had none, and counted each draft as a post.
            for query, key in (("SELECT COUNT(*) FROM posts WHERE status IS NOT 'draft'", "posts_count"),
                               ("SELECT COUNT(*) FROM posts WHERE status = 'draft'", "drafts_count"),
                               ("SELECT COUNT(*) FROM leads", "leads_count")):
                try:
                    counts[key] = conn.execute(query).fetchone()[0]
                except sqlite3.Error:
                    pass
        finally:
            conn.close()
    except sqlite3.Error:
        pass
    return counts


def _locked_message(entry: Dict[str, Any]) -> str:
    """
    Why a profile beyond the licence stays closed, naming the licence and how to renew.

    Nothing is deleted or hidden when a licence ends, so the message says what
    can still be done with the profile as well as what cannot.
    """
    state = licensing.current()
    licence = state.get("licence") or {}
    limit = state["profile_limit"]
    if state["status"] == "expired":
        label = licensing.TIERS.get(licence.get("tier"), {}).get("label", "")
        why = f"Your {label} licence ended on {licence.get('expires_at')}"
    elif state["status"] == "none":
        why = "There is no licence on this machine"
    elif state["status"] == "invalid":
        why = "The licence on this machine could not be read"
    else:
        why = f"Your {state['tier_label']} licence covers {limit} creator profile{'s' if limit != 1 else ''}"
    return (
        f"{why}, so {entry['name']} stays closed. To open it again, renew the Agency licence and paste "
        f"the new key in Brand Studio, Licence. Nothing in it was deleted: you can still back it up or "
        f"export it from the command line (backup --profile {entry['id']}, export --profile {entry['id']}), "
        f"or delete it."
    )


def _describe(entry: Dict[str, Any], active_id: str, locked: Optional[List[str]] = None) -> Dict[str, Any]:
    is_default = entry["id"] == paths.DEFAULT_PROFILE_ID
    is_locked = entry["id"] in (locked if locked is not None else paths.locked_profile_ids())
    return {
        "id": entry["id"],
        "name": entry["name"],
        "vanity": entry.get("vanity") or "",
        "headline": entry.get("headline") or "",
        "avatar_initials": entry.get("avatar_initials") or _compute_initials(entry["name"]),
        "is_default": is_default,
        "is_active": entry["id"] == active_id,
        "created_at": entry.get("created_at"),
        # Beyond what the licence covers: kept, listed, not opened.
        "locked": is_locked,
        "locked_reason": _locked_message(entry) if is_locked else "",
        **_counts(entry["id"]),
    }


def _entries() -> List[Dict[str, Any]]:
    registry = _registry()
    default = _default_details()
    entries = [{"id": paths.DEFAULT_PROFILE_ID, **default, "created_at": None}]
    entries += [p for p in registry["profiles"] if p["id"] != paths.DEFAULT_PROFILE_ID]
    return entries


def _open_profile(profile_id: str) -> None:
    """Creates or upgrades a profile's database, as a fresh install would."""
    with paths.using_profile(profile_id):
        init_db()
        seed_initial_data()


# ---------------------------------------------------------------------------
# Public API, used by the /api/v1/accounts routes
# ---------------------------------------------------------------------------

def get_active_account_id(conn=None) -> str:
    """The active profile. conn is accepted for older callers and ignored."""
    return paths.get_active_profile_id()


def is_first_profile(profile_id: Optional[str] = None) -> bool:
    """
    Whether a profile is the first one: the default profile, which is the
    studio as it was before profiles existed. The others are the Agency
    tier's, and licensing.FIRST_PROFILE_ONLY names what they cannot do.
    """
    return (profile_id or paths.get_active_profile_id()) == paths.DEFAULT_PROFILE_ID


def profile_refusal(feature: str) -> Optional[str]:
    """
    The sentence that refuses a first-profile-only feature in the active
    profile, or None when the feature may go ahead here. The sentence is the
    one the screen shows, so a refusal is never a bare error.
    """
    if licensing.first_profile_only(feature) and not is_first_profile():
        return licensing.FIRST_PROFILE_ONLY_REASON
    return None


def list_accounts(conn=None) -> Dict[str, Any]:
    """Every profile with its own counts, the active one, and the licence's allowance."""
    active_id = paths.get_active_profile_id()
    locked = paths.locked_profile_ids()
    accounts = [_describe(entry, active_id, locked) for entry in _entries()]
    return {
        "status": "success",
        "accounts": accounts,
        "active_account_id": active_id,
        "profile_limit": licensing.profile_limit(),
    }


def get_account(account_id: str, conn=None) -> Optional[Dict[str, Any]]:
    entry = next((e for e in _entries() if e["id"] == account_id), None)
    return _describe(entry, paths.get_active_profile_id()) if entry else None


def create_account(data: Dict[str, Any], conn=None) -> Dict[str, Any]:
    with _REGISTRY_LOCK:
        return _create_account(data, conn)


def _create_account(data: Dict[str, Any], conn=None) -> Dict[str, Any]:
    """
    Creates a creator profile with an empty database of its own.

    A second profile is the agency tier, so the licence is asked first.
    """
    name = (data.get("name") or "").strip()[:MAX_ACCOUNT_NAME_LENGTH]
    if not name:
        return {"status": "error", "message": "Account name is required"}

    existing = _entries()
    limit = licensing.profile_limit()
    if len(existing) >= limit:
        return {
            "status": "error",
            "code": "licence",
            "message": (
                f"Your licence covers {limit} creator profile{'s' if limit != 1 else ''}."
                + ("" if limit > 1 else " Separate profiles for several creators are part of the Agency licence.")
            ),
        }

    headline = (data.get("headline") or "").strip()[:MAX_HEADLINE_LENGTH]
    vanity = (data.get("vanity") or "").strip()[:MAX_VANITY_LENGTH]

    suggested_id = (data.get("id") or "").strip().lower()
    if suggested_id:
        acc_id = re.sub(r"[^a-z0-9-]", "", suggested_id.replace("_", "-"))[:48]
    else:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24]
        acc_id = f"{slug}-{uuid.uuid4().hex[:6]}" if slug else f"acc-{uuid.uuid4().hex[:8]}"
    if not paths.is_valid_profile_id(acc_id) or acc_id == paths.DEFAULT_PROFILE_ID:
        return {"status": "error", "message": f"'{acc_id}' cannot be used as a profile ID"}
    if paths.is_reserved_profile_id(acc_id):
        return {"status": "error", "message": (
            f"'{acc_id}' cannot be used as a profile ID: Windows reserves it for a device, so it "
            f"cannot be a folder name there. Add a letter or two, for example '{acc_id}-1'.")}
    if any(e["id"] == acc_id for e in existing):
        return {"status": "error", "message": f"Account ID '{acc_id}' already exists"}

    entry = {
        "id": acc_id,
        "name": name,
        "vanity": vanity,
        "headline": headline,
        "avatar_initials": _compute_initials(name),
        "created_at": _now(),
    }
    home = os.path.join(paths.get_profiles_root(), acc_id)
    if os.path.exists(home):
        return {"status": "error", "message": f"A folder for '{acc_id}' already exists at {home}"}

    # Registered first: paths refuses to create folders for a profile that is
    # not in the registry, which is what keeps a deleted one from coming back.
    registry = _registry()
    registry["profiles"].append(entry)
    paths.write_profiles(registry)
    try:
        _open_profile(acc_id)
    except Exception:
        registry = _registry()
        registry["profiles"] = [p for p in registry["profiles"] if p["id"] != acc_id]
        paths.write_profiles(registry)
        shutil.rmtree(home, ignore_errors=True)
        raise
    return {"status": "success", "account": _describe(entry, paths.get_active_profile_id())}


def switch_account(account_id: str, conn=None) -> Dict[str, Any]:
    with _REGISTRY_LOCK:
        return _switch_account(account_id, conn)


def _switch_account(account_id: str, conn=None) -> Dict[str, Any]:
    """Makes a profile active from the next request on, upgrading its database first."""
    entry = next((e for e in _entries() if e["id"] == account_id), None)
    if not entry:
        return {"status": "error", "message": f"Account '{account_id}' does not exist"}
    if account_id in paths.locked_profile_ids():
        return {"status": "error", "code": "licence", "message": _locked_message(entry)}

    try:
        _open_profile(account_id)
    except (SchemaTooNewError, SchemaTooOldError) as refused:
        # A database a newer (or far older) build wrote. This answered a bare
        # 500, and the reason, which names the backups folder, reached only
        # the server console.
        return {"status": "error", "code": "schema", "message": f"{entry['name']} cannot be opened. {refused}"}
    registry = _registry()
    registry["active"] = account_id
    paths.write_profiles(registry)
    return {
        "status": "success",
        "active_account_id": account_id,
        "account": _describe(entry, account_id),
    }


def delete_account(account_id: str, conn=None, confirm: Optional[str] = None) -> Dict[str, Any]:
    with _REGISTRY_LOCK:
        return _delete_account(account_id, conn, confirm)


def _delete_account(account_id: str, conn=None, confirm: Optional[str] = None) -> Dict[str, Any]:
    """
    Deletes a profile and every file it holds: database, media, backups, exports.

    Refuses the default profile, and refuses unless `confirm` repeats the
    profile's name or ID. If it was active, the default profile becomes active.
    """
    if account_id == paths.DEFAULT_PROFILE_ID:
        return {"status": "error", "message": "Cannot delete the default system profile"}

    entry = next((e for e in _entries() if e["id"] == account_id), None)
    if not entry:
        return {"status": "error", "message": f"Account '{account_id}' not found"}
    if (confirm or "").strip() not in (entry["name"], entry["id"]):
        return {
            "status": "error",
            "code": "confirm",
            "message": f"Type the profile's name, {entry['name']}, to delete it and all of its data.",
        }

    registry = _registry()
    registry["profiles"] = [p for p in registry["profiles"] if p["id"] != account_id]
    if registry.get("active") == account_id:
        registry["active"] = paths.DEFAULT_PROFILE_ID
        _open_profile(paths.DEFAULT_PROFILE_ID)
    paths.write_profiles(registry)

    root = os.path.realpath(paths.get_profiles_root())
    home = os.path.realpath(os.path.join(root, account_id))
    if os.path.commonpath([root, home]) == root and home != root and os.path.isdir(home):
        shutil.rmtree(home)

    return {
        "status": "success",
        "message": f"Profile '{entry['name']}' and all of its data were deleted",
        "active_account_id": registry["active"],
    }
