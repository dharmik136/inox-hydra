"""
Which creator profile a capture belongs to.
===========================================

Cycle 4, track 1, phase 2 (the capture report's Appendix B, days 8 and 9).

Every capture went to whichever creator profile the studio had active. With
an Agency licence and two browsers signed in to two clients' LinkedIn
accounts, one client's posts, readings and engagers landed in the other's
profile, or were refused there and lost. The worker now names the LinkedIn
account each capture was read in, in the X-Inox-Account header: the account
the browser is signed in to, which the extension learns from the creator's
own profile page. This module answers which profile has confirmed that
account, and app.pin_creator_profile pins the request to it.

A capture for an account no profile holds is held, not written: the worker
keeps it and sends it when a profile for that account is confirmed, and
Health shows it meanwhile. A run of a reader for such an account, an
import question or a drift event is answered nothing_new: it is about a
moment, not the creator's data. A profile still being set up (the active
one, with no confirmed account) takes what its browser reads, as before, so
a new client can be onboarded. A capture that names no account goes to the
active profile, as every capture did.

Strict Invariants:
- Zero em-dashes.
- The vanity is the browser's signed-in account, the creator's own; nothing
  about another member is read here.
"""

import hashlib
import os
import sqlite3
import threading
import time
from typing import Dict, List, Optional, Tuple

try:
    from . import paths
except ImportError:
    import paths

ACCOUNT_HEADER = "X-Inox-Account"

# The creator's data: held for an account no profile holds, so the worker
# keeps it until one does. The same paths the worker keeps for a busy studio.
DATA_PATHS = frozenset({
    "/api/v1/crm/interactions/ingest",
    "/api/v1/self/posts/ingest",
    "/api/v1/self/posts/analytics",
    "/api/v1/self/outbound/ingest",
    "/api/v1/identity/observe",
    "/api/v1/posts/bind-urn",
    "/api/v1/bridge/voyager-ingest",
    "/api/analytics/ingest",
    "/api/analytics/page-figures",
})

# About a moment or a question: routed to the account's profile when there is
# one, and otherwise answered nothing_new without a write anywhere.
BOOKKEEPING_PATHS = frozenset({
    "/api/v1/bridge/capture",
    "/api/v1/bridge/schema-drift",
    "/api/v1/identity/me",
    "/api/v1/self/imports/pending",
    "/api/v1/self/imports/event",
})

# The map of confirmed accounts is read from each profile's own database, a
# few milliseconds a profile, and kept this long; confirming or forgetting an
# account, and a change to the profile registry, clear it at once.
CACHE_SECONDS = 15.0

_lock = threading.Lock()
_cache: Dict[str, object] = {"at": 0.0, "registry": None, "map": None}


def _registry_stamp() -> Optional[int]:
    try:
        return os.stat(paths.get_profiles_file()).st_mtime_ns
    except OSError:
        return None


def _confirmed_vanity(profile_id: str) -> Optional[str]:
    """A profile's confirmed LinkedIn account, read only, or None."""
    home = paths.get_profile_home(profile_id)
    db_path = os.path.join(home, "data", paths.DB_FILENAME)
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2)
        try:
            row = conn.execute("SELECT vanity, confirmed_at FROM creator_identity WHERE id = 1").fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    if row and row[0] and row[1]:
        return str(row[0]).strip().lower()
    return None


def account_map() -> Dict[str, str]:
    """{confirmed vanity: profile id} for every profile the licence opens."""
    now = time.monotonic()
    stamp = _registry_stamp()
    with _lock:
        if _cache["map"] is not None and _cache["registry"] == stamp and now - float(_cache["at"]) < CACHE_SECONDS:
            return dict(_cache["map"])  # type: ignore[arg-type]
    found: Dict[str, str] = {}
    for profile_id in paths.profile_ids():
        vanity = _confirmed_vanity(profile_id)
        if vanity and vanity not in found:
            found[vanity] = profile_id
    with _lock:
        _cache.update(at=now, registry=stamp, map=found)
    return dict(found)


def forget() -> None:
    """Clears the map, after an account is confirmed or forgotten, and for tests."""
    with _lock:
        _cache.update(at=0.0, registry=None, map=None)


def profile_for(vanity: Optional[str]) -> Optional[str]:
    if not vanity:
        return None
    return account_map().get(str(vanity).strip().lower())


def account_digest(vanity: str) -> str:
    """The one-way digest of an account, as the worker computes it for what it holds."""
    return hashlib.sha256(str(vanity).strip().lower().encode("utf-8")).hexdigest()


def profile_account_digests() -> List[str]:
    """
    Every account a profile here has confirmed, as digests, for the worker to
    send what it held for one. Digests, not names: with several creator
    profiles the browser would otherwise keep every client's account name,
    when it needs only to recognise the one it holds captures for.
    """
    return sorted(account_digest(vanity) for vanity in account_map())


def decide(path: str, vanity: Optional[str]) -> Tuple[str, Optional[str]]:
    """
    What to do with a bridge request that names an account:
      ("pin", profile)  route it to that profile
      ("held", None)    the creator's data for an account no profile holds
      ("skip", None)    a moment or a question for such an account
      ("pass", None)    as before: the active profile
    """
    if path not in DATA_PATHS and path not in BOOKKEEPING_PATHS:
        return "pass", None
    vanity = (vanity or "").strip().lower()
    if not vanity:
        return "pass", None
    profile = profile_for(vanity)
    if profile:
        return "pin", profile
    # A profile still being set up takes what its browser reads.
    if _confirmed_vanity(paths.get_active_profile_id()) is None:
        return "pass", None
    return ("held", None) if path in DATA_PATHS else ("skip", None)


def held_message(vanity: str) -> str:
    return (f"No creator profile here has confirmed the LinkedIn account linkedin.com/in/{vanity}, so this "
            "capture is kept in the browser until one does.")
