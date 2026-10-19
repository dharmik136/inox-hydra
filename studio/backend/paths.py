"""
Application Path Resolver: Separation of Code from User State.
==============================================================
Single source of truth for every writable location the application uses.

The application directory is disposable. An update replaces it wholesale.
Anything a user would grieve losing (drafts, leads, analytics, generated media,
session vault) must therefore resolve through this module and live outside it.

Resolution order, highest priority first:
  1. INOX_HYDRA_HOME environment variable. Explicit override, used by tests
     and by anyone who wants their state on a different drive.
  2. A `studio/data` directory already present beside the code. This means a
     source checkout or a portable unzip, so state stays local to the tree.
  3. The platform user data directory. This is the installed-mode path:
       Windows  %LOCALAPPDATA%\\InoxHydra
       macOS    ~/Library/Application Support/InoxHydra
       Linux    $XDG_DATA_HOME/inox-hydra or ~/.local/share/inox-hydra

Creator profiles. Each creator profile is its own folder with its own
database, media, backups and exports, so one client's data cannot appear in
another's screens, backups or exports. The first profile, "default", is the
application home itself, so an install from before profiles existed keeps its
data exactly where it was. Every other profile lives in profiles/<id>/, and
profiles/profiles.json records which exist and which is active. The vault key,
logs and browser profiles belong to the machine and stay at the application
home.

This module also resolves bundled read-only content (frontend, docs). That is
deliberately kept separate from state below: content ships with the code and is
replaced by an update, state never is. Both live here so there is exactly one
answer to "where is X" in the codebase.

Strict Invariants:
- Zero em-dashes in any code, docstring, or comment.
- No other module may resolve writable state or bundled content by any other means.
"""

import json
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, List, Optional

APP_DIR_NAME_WINDOWS = "InoxHydra"
APP_DIR_NAME_POSIX = "inox-hydra"
DB_FILENAME = "linkedin_studio.db"

DEFAULT_PROFILE_ID = "default"
PROFILES_DIRNAME = "profiles"
PROFILES_FILENAME = "profiles.json"
_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")

# The profile a request, or a loop over profiles, is pinned to. Unset means
# whatever profiles.json names as active.
#
# One variable for the whole process, even when this module is imported twice
# under different names (the package imports it as studio.backend.paths, the
# tests and some tools as plain `paths`). Two variables would let a pin set
# through one name go unseen through the other.
_pinned_profile: ContextVar[Optional[str]] = getattr(sys, "_inox_pinned_profile", None) or ContextVar(
    "inox_pinned_profile", default=None
)
sys._inox_pinned_profile = _pinned_profile
_registry_cache: Dict[str, Any] = {"path": None, "mtime": None, "value": None}

# studio/backend/paths.py -> studio/
_STUDIO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_LEGACY_DATA_DIR = os.path.join(_STUDIO_DIR, "data")


def _platform_user_data_dir() -> str:
    """Returns the conventional per-user writable data directory for this OS."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        return os.path.join(base, APP_DIR_NAME_WINDOWS)
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", APP_DIR_NAME_WINDOWS)
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, APP_DIR_NAME_POSIX)


def get_app_home() -> str:
    """
    Resolves the root directory holding all user state.

    Read fresh on every call rather than cached at import time, so that tests
    and the CLI can redirect state by setting INOX_HYDRA_HOME.
    """
    override = os.environ.get("INOX_HYDRA_HOME")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    if os.path.isdir(_LEGACY_DATA_DIR):
        return _STUDIO_DIR
    return _platform_user_data_dir()


def get_browser_profile_dir(browser_id: str, exe_path: str = "") -> str:
    """
    The dedicated browser profile the bridge browser runs in.

    A separate profile is what makes the one-click launch work: Edge or Brave
    already running with the creator's normal profile receives a relaunch as a
    request to open a tab, and drops --load-extension, so the bridge never
    attaches. A different --user-data-dir is a different browser instance and
    always honours the flag.

    It never lives under studio/, even in a portable or source install where
    every other kind of state does. This profile holds the creator's LinkedIn
    cookies, and the build copies studio/ from the working tree, so a profile
    there would ship a logged-in LinkedIn session inside the next build.
    INOX_HYDRA_HOME still redirects it, for tests.
    """
    safe_id = "".join(ch for ch in (browser_id or "browser") if ch.isalnum() or ch in "-_") or "browser"
    override = os.environ.get("INOX_HYDRA_HOME")
    if override:
        return _ensure(os.path.join(os.path.abspath(os.path.expanduser(override)), "browser-profiles", safe_id))

    if sys.platform.startswith("linux"):
        # On Linux, snap-confined browsers (such as Brave or Chromium installed via snap)
        # run under AppArmor profiles that strictly prohibit reading or writing to hidden
        # dot-directories in $HOME (such as ~/.local/share/...).
        # If the browser binary is in /snap/ or ~/snap/<safe_id> exists, store the profile
        # in the snap's persistent common directory (~/snap/<safe_id>/common/inox-hydra-profile)
        # where AppArmor grants full rwklx permissions.
        snap_home = os.path.join(os.path.expanduser("~"), "snap", safe_id)
        exe_snap_name = os.path.basename(exe_path) if exe_path else ""
        alt_snap_home = os.path.join(os.path.expanduser("~"), "snap", exe_snap_name) if exe_snap_name else ""
        if os.path.isdir(snap_home):
            return _ensure(os.path.join(snap_home, "common", "inox-hydra-profile"))
        if alt_snap_home and os.path.isdir(alt_snap_home):
            return _ensure(os.path.join(alt_snap_home, "common", "inox-hydra-profile"))
        if exe_path and "/snap/" in exe_path:
            target_snap = snap_home if snap_home else alt_snap_home
            return _ensure(os.path.join(target_snap, "common", "inox-hydra-profile"))

    root = _platform_user_data_dir()
    return _ensure(os.path.join(root, "browser-profiles", safe_id))


# ---------------------------------------------------------------------------
# Creator profiles
# ---------------------------------------------------------------------------

def is_valid_profile_id(profile_id: Any) -> bool:
    return isinstance(profile_id, str) and bool(_PROFILE_ID.match(profile_id))


# Names Windows reserves for devices: a folder cannot be called any of them.
# Refused for new profiles on every platform, so a profile made on Linux can
# still move to Windows. Existing ones are left readable, never hidden.
_WINDOWS_DEVICE_NAMES = frozenset(
    {"con", "prn", "aux", "nul"} | {f"com{n}" for n in range(10)} | {f"lpt{n}" for n in range(10)}
)


def is_reserved_profile_id(profile_id: Any) -> bool:
    return isinstance(profile_id, str) and profile_id.lower() in _WINDOWS_DEVICE_NAMES


def get_profiles_root() -> str:
    """Where every profile other than the default one keeps its folder."""
    return os.path.join(get_app_home(), PROFILES_DIRNAME)


def get_profiles_file() -> str:
    return os.path.join(get_profiles_root(), PROFILES_FILENAME)


def _empty_registry() -> Dict[str, Any]:
    return {"active": DEFAULT_PROFILE_ID, "profiles": []}


def read_profiles() -> Dict[str, Any]:
    """
    The profile registry: {"active": id, "profiles": [{id, name, ...}]}.

    Absent until a second profile is created, and an absent or unreadable file
    means one profile, the default. Re-read only when the file changes, because
    every database connection asks which profile is active.
    """
    path = get_profiles_file()
    try:
        mtime = os.stat(path).st_mtime_ns
    except OSError:
        return _empty_registry()
    cache = _registry_cache
    if cache["path"] == path and cache["mtime"] == mtime and cache["value"] is not None:
        return json.loads(json.dumps(cache["value"]))
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError):
        return _empty_registry()
    if not isinstance(value, dict) or not isinstance(value.get("profiles"), list):
        return _empty_registry()
    value["profiles"] = [p for p in value["profiles"] if isinstance(p, dict) and is_valid_profile_id(p.get("id"))]
    if not is_valid_profile_id(value.get("active")):
        value["active"] = DEFAULT_PROFILE_ID
    cache.update(path=path, mtime=mtime, value=value)
    return json.loads(json.dumps(value))


def write_profiles(registry: Dict[str, Any]) -> None:
    """Replaces the registry atomically, so a crash never leaves half a file."""
    root = _ensure(get_profiles_root())
    fd, tmp = tempfile.mkstemp(prefix=".profiles-", suffix=".json", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(registry, handle, indent=2, ensure_ascii=False)
        os.replace(tmp, get_profiles_file())
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    _registry_cache.update(path=None, mtime=None, value=None)


def registered_profile_ids() -> List[str]:
    """Every profile on this machine, the default first, whatever the licence covers."""
    ids = [DEFAULT_PROFILE_ID]
    for entry in read_profiles()["profiles"]:
        if entry["id"] not in ids:
            ids.append(entry["id"])
    return ids


def _licensed_profile_count() -> int:
    try:
        from . import licensing
    except ImportError:
        import licensing
    try:
        return max(1, int(licensing.profile_limit()))
    except Exception:
        # A licence that cannot be read is the free tier. See licensing.py.
        return 1


def profile_ids() -> List[str]:
    """
    Every profile the licence lets the studio open, the default first.

    The profiles beyond the licence's count, in the order they were made, stay
    on disk and in the registry: they can be backed up, exported and deleted,
    but they are not opened, made active, or worked by the scheduler. The
    limit used to be asked only when a profile was created, so an Agency
    licence that ended kept all five profiles working.
    """
    ids = registered_profile_ids()
    if len(ids) == 1:
        return ids
    return ids[:_licensed_profile_count()]


def locked_profile_ids() -> List[str]:
    """The profiles beyond what the licence covers."""
    usable = profile_ids()
    return [pid for pid in registered_profile_ids() if pid not in usable]


def get_active_profile_id() -> str:
    pinned = _pinned_profile.get()
    if pinned:
        return pinned
    active = read_profiles()["active"]
    return active if active in profile_ids() else DEFAULT_PROFILE_ID


def get_profile_home(profile_id: Optional[str] = None) -> str:
    """The folder holding one profile's database, media, backups and exports."""
    pid = profile_id or get_active_profile_id()
    if pid == DEFAULT_PROFILE_ID:
        return get_app_home()
    if not is_valid_profile_id(pid):
        raise ValueError(f"not a profile id: {pid!r}")
    return os.path.join(get_profiles_root(), pid)


@contextmanager
def using_profile(profile_id: str) -> Iterator[str]:
    """Pins every path resolved inside the block to one profile."""
    if profile_id != DEFAULT_PROFILE_ID and not is_valid_profile_id(profile_id):
        raise ValueError(f"not a profile id: {profile_id!r}")
    token = _pinned_profile.set(profile_id)
    try:
        yield profile_id
    finally:
        _pinned_profile.reset(token)


def is_portable() -> bool:
    """True when state lives beside the code rather than in the user profile."""
    return get_app_home() == _STUDIO_DIR


def _ensure(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


class ProfileGone(RuntimeError):
    """The creator profile this work is pinned to has been deleted."""


def _profile_dir(name: str) -> str:
    """
    One of the active profile's folders, created if missing, unless the profile is gone.

    Work pinned to a profile (an image generation, an import, a telemetry
    batch) can outlive the profile being deleted. Resolving its paths used to
    create the folders again, so the deleted client's folder came back with
    whatever that work wrote, outside every backup, and the id could never be
    used again.
    """
    pid = get_active_profile_id()
    if pid != DEFAULT_PROFILE_ID and pid not in registered_profile_ids():
        raise ProfileGone(f"Creator profile '{pid}' was deleted, so nothing more is written for it.")
    return _ensure(os.path.join(get_profile_home(pid), name))


def get_data_dir() -> str:
    """Database, ETag caches, and other small structured state. Per profile."""
    return _profile_dir("data")


def get_assets_dir() -> str:
    """Root of user media. Mounted at /assets by the web layer. Per profile."""
    return _profile_dir("assets")


def get_uploads_dir() -> str:
    """Files the user dropped in: images, PDF carousels, videos."""
    return _ensure(os.path.join(get_assets_dir(), "uploads"))


def get_generated_dir() -> str:
    """AI Image Studio output."""
    return _ensure(os.path.join(get_assets_dir(), "generated"))


def get_vault_dir() -> str:
    """Encrypted session credential material."""
    return _ensure(os.path.join(get_app_home(), "vault"))


def get_logs_dir() -> str:
    """Rotating application logs, collected by the diagnostics bundle."""
    return _ensure(os.path.join(get_app_home(), "logs"))


def get_backups_dir() -> str:
    """
    Timestamped database copies taken before any schema migration.

    This is the user's undo button. It is the only recovery path available when
    an upgrade goes wrong on a machine nobody can reach.
    """
    return _profile_dir("backups")


def get_exports_dir() -> str:
    """Where an export lands when the caller names no destination. Per profile."""
    return _profile_dir("exports")


def get_db_path() -> str:
    """Absolute path to the active profile's SQLite database."""
    return os.path.join(get_data_dir(), DB_FILENAME)


# ---------------------------------------------------------------------------
# Bundled read-only content. Ships with the code, replaced by an update.
# ---------------------------------------------------------------------------

_REPO_DOCS_DIR = os.path.abspath(os.path.join(_STUDIO_DIR, "..", "docs"))
_PACKAGED_DOCS_DIR = os.path.join(_STUDIO_DIR, "docs")


def get_frontend_dir() -> str:
    """
    Single page application served at /. Always ships inside the package.

    This is the built React interface in studio/frontend_next, produced by
    `npm run build` in studio/ui. It used to fall back to a second, vanilla
    page when the build was absent. That page is gone, and the fallback with
    it: a missing build is now a missing interface rather than a silent
    downgrade to a different one, which is what kept the packaging defect
    invisible for as long as it was.
    """
    return os.path.join(_STUDIO_DIR, "frontend_next")


def get_extension_dir() -> str:
    """Unpacked Chrome MV3 source, shipped for the one time store install."""
    return os.path.join(_STUDIO_DIR, "extension")


def get_docs_dir() -> str:
    """
    Markdown consumed by the in-app Docs tab and the offline search index.

    A source checkout is authoritative when present, so editing docs/ during
    development takes effect immediately without a repackaging step. An
    installed build has no repo-root docs/, so it falls through to the copy
    staged inside the package by tools/prepare_package.py.

    The repo-root folder counts only when it holds the help articles. Beside an
    installed package, ../docs is site-packages/docs, which any other package
    may have created, and taking it would show that package's files and none
    of the help.
    """
    if _is_our_docs(_REPO_DOCS_DIR):
        return _REPO_DOCS_DIR
    return _PACKAGED_DOCS_DIR


def _is_our_docs(folder: str) -> bool:
    return os.path.isdir(os.path.join(folder, "help"))


def get_modules_docs_dir() -> str:
    """Per-module documentation (01_STUDIO_AND_EDITOR.md through 06_AI_COMMAND.md)."""
    return os.path.join(get_docs_dir(), "modules")


def describe() -> dict:
    """
    Structured snapshot of resolved locations.

    Consumed by the diagnostics bundle so a user can tell us where their state
    actually landed without us needing access to their machine.
    """
    home = get_app_home()
    source = "INOX_HYDRA_HOME" if os.environ.get("INOX_HYDRA_HOME") else (
        "portable (studio/data present)" if is_portable() else "platform user data dir"
    )
    db = get_db_path()
    return {
        "app_home": home,
        "resolved_by": source,
        "active_profile": get_active_profile_id(),
        "profile_home": get_profile_home(),
        "portable": is_portable(),
        "data_dir": get_data_dir(),
        "assets_dir": get_assets_dir(),
        "uploads_dir": get_uploads_dir(),
        "generated_dir": get_generated_dir(),
        "vault_dir": get_vault_dir(),
        "logs_dir": get_logs_dir(),
        "db_path": db,
        "db_exists": os.path.exists(db),
        "db_size_bytes": os.path.getsize(db) if os.path.exists(db) else 0,
        "frontend_dir": get_frontend_dir(),
        "docs_dir": get_docs_dir(),
        "docs_source": "source checkout" if _is_our_docs(_REPO_DOCS_DIR) else "packaged",
    }
