"""
Opt-In Update Check: The Only Outbound Request This Product Makes.
==================================================================
Reuses the asymmetric CDN pattern already proven in intelligence_sync.py: a
conditional HTTP GET against a static file on GitHub Releases, with ETag
caching so an unchanged file transfers zero bytes and costs zero dollars.

Two rules govern this module, and they are not negotiable:

  1. **Off by default.** A product whose headline promise is zero cloud egress
     cannot quietly contact a server. The user is asked once, the answer is
     stored, and the answer is honoured. Disabled means no request is made, not
     that the result is hidden.

  2. **It reports, it never acts.** This module returns a version string and a
     link. It does not download, unpack, execute, or modify anything. A failed
     self-update on a machine nobody can reach is unrecoverable, so the update
     procedure stays manual: the user downloads a ZIP and swaps the folder.
     Their data is outside that folder by construction, so the swap is safe.

Strict Invariants:
- Zero em-dashes.
- Never fetch anything when the preference is disabled.
- Never execute or install anything named by the remote response.
"""

import json
import os
import sqlite3
import urllib.parse
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

try:
    from . import paths
    from ..__version__ import __version__
except ImportError:
    import paths
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from __version__ import __version__

DEFAULT_MANIFEST_URL = os.environ.get(
    "INOX_UPDATE_MANIFEST_URL",
    "https://raw.githubusercontent.com/dharmik136/inox-hydra/main/release/latest.json",
)

ALLOWED_UPDATE_SCHEMES = ("https",)

PREFERENCE_KEY = "update_check_enabled"
LAST_CHECKED_KEY = "update_last_checked"
LAST_SEEN_KEY = "update_last_seen_version"

RELEASES_PAGE = "https://github.com/dharmik136/inox-hydra/releases"
REQUEST_TIMEOUT_SECONDS = 10


def _etag_file() -> str:
    return os.path.join(paths.get_data_dir(), ".update_etag")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(paths.get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _get_setting(key: str) -> Optional[str]:
    try:
        conn = _connect()
    except Exception:
        return None
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None
    except Exception:
        return None
    finally:
        conn.close()


def _set_setting(key: str, value: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def is_enabled() -> bool:
    """Defaults to False. Absence of a stored preference means not yet asked."""
    return (_get_setting(PREFERENCE_KEY) or "").strip().lower() in ("1", "true", "yes", "on")


def has_been_asked() -> bool:
    """True once the user has made a choice either way, so we stop prompting."""
    return _get_setting(PREFERENCE_KEY) is not None


def set_enabled(enabled: bool) -> Dict[str, Any]:
    _set_setting(PREFERENCE_KEY, "true" if enabled else "false")
    return {"enabled": enabled, "asked": True}


def parse_version(value: str) -> Tuple[int, ...]:
    """
    Numeric comparison, so 2.10.0 correctly sorts above 2.9.0.

    Anything non-numeric is dropped rather than raising, because the remote
    value is untrusted input and a malformed manifest must not crash startup.
    Limits input string length and number of segments.
    """
    parts = []
    chunks = str(value)[:100].strip().split(".")[:10]
    for chunk in chunks:
        digits = "".join(c for c in chunk if c.isdigit())[:10]
        parts.append(int(digits) if digits else 0)
    return tuple(parts or [0])


def is_newer(remote: str, local: str = __version__) -> bool:
    remote_parts = parse_version(remote)
    local_parts = parse_version(local)
    length = max(len(remote_parts), len(local_parts))
    remote_parts += (0,) * (length - len(remote_parts))
    local_parts += (0,) * (length - len(local_parts))
    return remote_parts > local_parts


def check_for_update(force: bool = False, url: Optional[str] = None) -> Dict[str, Any]:
    """
    Performs the conditional GET, if and only if the user enabled it.

    `force` bypasses the ETag cache, not the preference. Nothing overrides the
    preference, which is the entire point of it existing.
    """
    if not is_enabled():
        return {
            "checked": False,
            "reason": "Update checks are disabled. Nothing was sent.",
            "enabled": False,
            "current_version": __version__,
        }

    import requests  # imported lazily so a disabled check touches no network stack

    target = (url or DEFAULT_MANIFEST_URL).strip()
    parsed = urllib.parse.urlparse(target)
    if parsed.scheme not in ALLOWED_UPDATE_SCHEMES:
        return {
            "checked": False,
            "enabled": True,
            "error": f"Disallowed URL scheme '{parsed.scheme}'. Only HTTPS is permitted.",
            "current_version": __version__,
        }

    headers = {"Accept": "application/json", "User-Agent": f"InoxHydra/{__version__}"}

    cached_etag = None
    if not force and os.path.exists(_etag_file()):
        try:
            with open(_etag_file(), encoding="utf-8") as f:
                cached_etag = f.read().strip() or None
        except OSError:
            cached_etag = None
    if cached_etag:
        headers["If-None-Match"] = cached_etag

    result: Dict[str, Any] = {
        "checked": True,
        "enabled": True,
        "current_version": __version__,
        "latest_version": None,
        "update_available": False,
        "releases_url": RELEASES_PAGE,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }

    try:
        response = requests.get(target, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
    except Exception as exc:
        result["error"] = f"Could not reach the update manifest: {exc}"
        return result

    _set_setting(LAST_CHECKED_KEY, result["checked_at"])

    if response.status_code == 304:
        result["not_modified"] = True
        result["bytes_transferred"] = 0
        last_seen = _get_setting(LAST_SEEN_KEY)
        if last_seen:
            result["latest_version"] = last_seen
            result["update_available"] = is_newer(last_seen)
        return result

    if response.status_code != 200:
        result["error"] = f"Update manifest returned HTTP {response.status_code}"
        return result

    try:
        manifest = response.json()
    except Exception as exc:
        result["error"] = f"Update manifest was not valid JSON: {exc}"
        return result

    latest = str(manifest.get("version") or "").strip()
    if not latest:
        result["error"] = "Update manifest did not declare a version"
        return result

    etag = response.headers.get("ETag")
    if etag:
        try:
            with open(_etag_file(), "w", encoding="utf-8") as f:
                f.write(etag)
        except OSError:
            pass

    _set_setting(LAST_SEEN_KEY, latest)

    result["latest_version"] = latest
    result["update_available"] = is_newer(latest)
    # Notes are remote text. They are shown to the user, never executed, and
    # never used to locate or launch anything.
    result["notes"] = str(manifest.get("notes") or "")[:1000]
    return result


def describe() -> Dict[str, Any]:
    """Status without performing any network request."""
    return {
        "current_version": __version__,
        "enabled": is_enabled(),
        "asked": has_been_asked(),
        "last_checked": _get_setting(LAST_CHECKED_KEY),
        "last_seen_version": _get_setting(LAST_SEEN_KEY),
        "manifest_url": DEFAULT_MANIFEST_URL,
        "releases_url": RELEASES_PAGE,
    }
