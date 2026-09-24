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

This module also resolves bundled read-only content (frontend, docs). That is
deliberately kept separate from state below: content ships with the code and is
replaced by an update, state never is. Both live here so there is exactly one
answer to "where is X" in the codebase.

Strict Invariants:
- Zero em-dashes in any code, docstring, or comment.
- No other module may resolve writable state or bundled content by any other means.
"""

import os
import sys

APP_DIR_NAME_WINDOWS = "InoxHydra"
APP_DIR_NAME_POSIX = "inox-hydra"
DB_FILENAME = "linkedin_studio.db"

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


def is_portable() -> bool:
    """True when state lives beside the code rather than in the user profile."""
    return get_app_home() == _STUDIO_DIR


def _ensure(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def get_data_dir() -> str:
    """Database, ETag caches, and other small structured state."""
    return _ensure(os.path.join(get_app_home(), "data"))


def get_assets_dir() -> str:
    """Root of user media. Mounted at /assets by the web layer."""
    return _ensure(os.path.join(get_app_home(), "assets"))


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
    return _ensure(os.path.join(get_app_home(), "backups"))


def get_db_path() -> str:
    """Absolute path to the SQLite database."""
    return os.path.join(get_data_dir(), DB_FILENAME)


# ---------------------------------------------------------------------------
# Bundled read-only content. Ships with the code, replaced by an update.
# ---------------------------------------------------------------------------

_REPO_DOCS_DIR = os.path.abspath(os.path.join(_STUDIO_DIR, "..", "docs"))
_PACKAGED_DOCS_DIR = os.path.join(_STUDIO_DIR, "docs")


def get_frontend_dir() -> str:
    """
    Single page application served at /. Always ships inside the package.

    Two interfaces exist during the Editorial Motion OS rewrite. frontend_next
    is the React build produced by `npm run build` in studio/ui; frontend is the
    original vanilla page. The built one wins when it is actually present and
    complete, and the check is for index.html rather than for the directory,
    because an interrupted or cleaned build leaves the directory behind with
    nothing servable in it. Falling back then is the difference between the old
    interface and a blank page.
    """
    built = os.path.join(_STUDIO_DIR, "frontend_next")
    if os.path.isfile(os.path.join(built, "index.html")):
        return built
    return os.path.join(_STUDIO_DIR, "frontend")


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
    """
    if os.path.isdir(_REPO_DOCS_DIR):
        return _REPO_DOCS_DIR
    return _PACKAGED_DOCS_DIR


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
        "docs_source": "source checkout" if os.path.isdir(_REPO_DOCS_DIR) else "packaged",
    }
