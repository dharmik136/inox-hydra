"""
The ingest contract: one shape for a capture, one set of answers.
=================================================================

Nine routes took the creator's data from the extension, each with its own
field names, its own idea of what identifies a post, and its own idea of what
to answer. A capture carrying the studio's own post key was answered 422 and
lost. A capture the studio declined was answered 200 "skipped" and shown to
nobody. The refusal a real creator meets most, "import your posts first", was
collapsed to null by the extension with nothing logged.

This module is the one place that says what a capture looks like and what the
studio answers. Every ingest route uses it. It is the `fold.py` shape: one
definition, one implementation, every caller through it.

The shape of a capture
----------------------

A capture names a post, names a person or names nobody, and says which client
sent it. Field names, and the only field names:

    post_urn            str   "urn:li:activity:N", "urn:li:share:N" or
                              "urn:li:ugcPost:N". What LinkedIn calls the post.
                              All three namespaces are accepted everywhere;
                              post_identity.ACTIVITY_URN_PATTERN is the one
                              pattern that reads them.
    post_key            str   The studio's own `posts.id`, which is TEXT
                              ("post-<hex12>"). Optional, and only the studio
                              can have told the extension one.
    profile_url         str   The engager's LinkedIn profile URL. A person
    linkedin_urn        str   with neither cannot be told apart from anyone
                              else of the same name, so neither is a default.
    author              str   The creator's confirmed vanity, on the routes
                              that carry the creator's own pages.
    extension_version   str   From the manifest, for the creator to read.
    contract_version    int   Which version of this contract the client
                              speaks. Absent means older than version 1.

`post_id` is still read as a deprecated alias of `post_key`, as TEXT, so an
extension that has not been reloaded keeps working. It used to be declared
`Optional[int]` for a TEXT key, which is why a correct value was a 422. It is
no longer written to `lead_interactions.post_id`: that column is an INTEGER
foreign key into `drafts(id)` and can never match a `posts.id`, which is why
it is populated on 0 of 500,061 rows.

The three answers
-----------------

Every ingest route answers exactly one of three outcomes, and says which in
`outcome`:

    accepted      Something was stored. HTTP 200.
                  {"status": "success", "outcome": "accepted", ...counts}

    nothing_new   Understood, nothing stored, nothing wrong, and nothing for
                  the creator to do. HTTP 200. The engagers of somebody
                  else's post are this: the rule worked.
                  {"status": "skipped", "outcome": "nothing_new",
                   "reason": "<code>", "message": "<a sentence>"}

    refused       Understood, nothing stored, and the creator has something
                  to do about it, or something is broken. HTTP 409.
                  {"status": "refused", "outcome": "refused",
                   "reason": "<code>", "message": "<a sentence>",
                   "detail": "<the same sentence>", "show": true}

`detail` repeats the message as a plain string so that every reader written
against the old 409 answers keeps working. `show` tells the extension to put
the message on the page; a `nothing_new` is counted and not announced,
because the feed is full of other people's posts and a toast for each one is
noise the creator learns to ignore.

Why not 409 for every refusal. An extension that has not been reloaded counts
an answer it cannot place as undecided and offers the same engager again
thirty seconds later, so turning "this post is not yours" into an error would
put a browser on a stranger's post into a slow retry loop. The outcome is
carried in the body, where a reloaded extension reads it, and the HTTP code
keeps meaning what it meant.

The handshake
-------------

The studio and the extension are shipped together and updated apart: a
creator who pulls a new studio keeps the extension Chrome loaded at startup
until they press Reload. Before this, neither side knew: the extension sent
`extension_version` on four paths and the studio compared it to nothing.

Now every client says `contract_version`, the studio answers `handshake()` on
the heartbeat and on `GET /api/v1/extension/health`, and a client older than
this contract is told once, in a sentence a creator can act on, instead of
failing quietly on a field name that moved.

What is counted
---------------

`note_refusal`, `note_client` and `note_waiting` keep what the studio knows
about this extension since the studio started: how many captures each refusal
reason has turned away, which client is talking, and how many captures the
extension is holding for a studio that was busy. It is in memory on purpose.
Every one of these is a fact about the conversation now in progress, not
history worth a table and a migration, and a studio that has just started has
not been told yet. When it has not been told, the count is None and the
screen says so, rather than showing a zero that means "not measured".
"""

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

try:
    from . import post_identity
    from .rate_limiter import write_actor
except (ImportError, ValueError):
    import post_identity
    from rate_limiter import write_actor

logger = logging.getLogger("studio.ingest")

# Version 1 is the contract written above. Raise it when a field name or an
# outcome changes, never for a new optional field: the handshake tells the
# creator to reload the extension, and that is a thing worth not crying wolf
# about.
CONTRACT_VERSION = 1

ACCEPTED = "accepted"
NOTHING_NEW = "nothing_new"
REFUSED = "refused"

# What to tell the creator when their extension is older than this contract.
# One sentence, naming the one action.
RELOAD_MESSAGE = (
    "The Inox Hydra extension in this browser is older than the studio. "
    "Open chrome://extensions and press Reload on Inox Hydra Bridge."
)

# What to do when the extension's folder is not the studio's: a reload reads
# the same folder again, so it is loaded again from the studio's.
LOAD_AGAIN = (
    "If the studio opened this browser, close it and open it again from Setup; if you loaded the "
    "extension by hand, remove it on chrome://extensions and load it again from the studio's extension folder."
)

# The reasons the engagement gate turns a capture away, as the one place they
# are written. onboarding.engagement_gate returns one of these, and
# classify() below decides which outcome each one is, so the reason a creator
# reads and the outcome the extension acts on cannot drift apart.
GATE_SETUP_FIRST = ("Confirm your profile in the studio's Setup screen, so the studio "
                    "can tell your posts from other people's.")
GATE_IMPORT_FIRST = ("Import your posts from the studio's Setup screen first. The studio has "
                     "no record of any post of yours, so it cannot tell whose post this is.")
GATE_THAT_IS_YOU = "That is you, not someone who engaged with your post."
GATE_NOT_YOUR_POST = "This post is not one of yours, so the people on it were not saved."

# A reason code per reason, and whether the creator can do something about it.
# A refusal is shown on the page; a nothing_new is counted and kept quiet.
_GATE_REASONS = {
    GATE_SETUP_FIRST: ("setup_needed", REFUSED),
    GATE_IMPORT_FIRST: ("import_posts_first", REFUSED),
    GATE_THAT_IS_YOU: ("that_is_you", NOTHING_NEW),
    GATE_NOT_YOUR_POST: ("not_your_post", NOTHING_NEW),
}


class RefusedIngest(Exception):
    """
    A capture the studio refuses and the creator can act on.

    Carries the reason code beside the sentence, so the route answers 409 with
    both and the extension can count the code while showing the sentence.
    """

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


def classify(gate_reason: Optional[str]) -> Optional[tuple]:
    """
    What the engagement gate's answer means: (reason code, outcome), or None
    when the gate allowed the capture.

    An unrecognised reason is treated as a refusal the creator should see.
    Being told something unexpected is better than being told nothing, which
    is the defect this module exists for.
    """
    if not gate_reason:
        return None
    known = _GATE_REASONS.get(gate_reason)
    if known:
        return known
    logger.warning("A capture was refused for a reason not in the contract: %s", gate_reason)
    return ("refused", REFUSED)


# The sentences the onboarding writes already refuse with, translated into
# the reason codes the extension counts and acts on. The sentence stays the
# thing a creator reads; the code is what a screen can tally. Anything not
# listed is "refused", which is still shown, because being told something
# unexpected beats being told nothing.
_REFUSAL_CODES = (
    ("import your posts first", "import_posts_first"),
    ("confirm your profile", "setup_needed"),
    ("has not confirmed who they are", "setup_needed"),
    ("do not belong to the confirmed creator", "not_your_data"),
    ("unknown extractor", "unknown_extractor"),
    ("not an activity urn", "bad_post_urn"),
)


def reason_code(message: Any) -> str:
    """The reason code for a refusal the studio words as a sentence."""
    said = str(message or "").lower()
    for fragment, code in _REFUSAL_CODES:
        if fragment in said:
            return code
    return "refused"


def accepted(**counts: Any) -> Dict[str, Any]:
    """The answer when something was stored."""
    answer = {"status": "success", "outcome": ACCEPTED, "contract_version": CONTRACT_VERSION}
    answer.update(counts)
    return answer


def nothing_new(reason: str, message: str, **counts: Any) -> Dict[str, Any]:
    """
    The answer when the capture was understood, nothing was stored, and there
    is nothing for the creator to do.

    `status` stays "skipped" so that an extension which has not been reloaded
    still counts the person as decided rather than offering them again.
    """
    answer = {"status": "skipped", "outcome": NOTHING_NEW, "reason": reason,
              "message": message, "show": False, "contract_version": CONTRACT_VERSION}
    answer.update(counts)
    note_refusal(reason)
    return answer


def refuse(reason: str, message: str) -> None:
    """Raises the refusal the route turns into a 409. Never returns."""
    note_refusal(reason)
    raise RefusedIngest(reason, message)


def refusal_body(reason: str, message: str) -> Dict[str, Any]:
    """
    The body of a 409. `detail` repeats the sentence as a plain string,
    because that is where every reader written before this contract looks.
    """
    return {"status": "refused", "outcome": REFUSED, "reason": reason, "message": message,
            "detail": message, "show": True, "contract_version": CONTRACT_VERSION}


# ---------------------------------------------------------------------------
# Reading a capture
# ---------------------------------------------------------------------------

def post_urn_of(payload: Any) -> Optional[str]:
    """
    The post URN a capture names, in any of LinkedIn's three namespaces, or
    None. One pattern, post_identity's, reads all of them: an activity, a
    share and a ugcPost card are all a post the creator wrote, and refusing
    two of the three left a post permanently un-analysable.
    """
    if not isinstance(payload, dict):
        return None
    found = post_identity.ACTIVITY_URN_PATTERN.search(str(payload.get("post_urn") or ""))
    return found.group(0) if found else None


def post_key_of(payload: Any) -> Optional[str]:
    """
    The studio's own post key a capture names, or None. `post_id` is read as a
    deprecated alias, as TEXT: `posts.id` has always been TEXT, and declaring
    the field an integer is what made a correct value a 422.
    """
    if not isinstance(payload, dict):
        return None
    for field in ("post_key", "post_id"):
        value = payload.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()[:80]
        if isinstance(value, int):
            return str(value)
    return None


def person_key_of(payload: Any) -> Optional[str]:
    """
    What identifies the person a capture is about, or None. A profile URL is
    the only thing that tells two people of the same name apart, so there is
    no fallback to a name.
    """
    if not isinstance(payload, dict):
        return None
    for field in ("profile_url", "linkedin_urn"):
        value = payload.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


# ---------------------------------------------------------------------------
# What the studio knows about the extension it is talking to
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_client: Dict[str, Any] = {}
_refusals: Dict[str, int] = {}
_waiting: Dict[str, Any] = {}


def note_client(extension_version: Any = None, contract_version: Any = None) -> None:
    """
    Remembers which client is talking, so the handshake can answer when there
    is no client on the line, as on `GET /api/v1/extension/health`.

    A client that says nothing at all teaches nothing, and what is remembered
    is left alone. A client that names itself teaches both facts, including
    that it declared no contract version: remembering the last good number
    across a reload would tell a creator everything is fine while the browser
    runs an extension that cannot speak to this studio.
    """
    speaks = contract_version if isinstance(contract_version, int) else None
    if extension_version is None and speaks is None:
        return
    with _lock:
        if extension_version:
            _client["extension_version"] = str(extension_version)[:40]
        _client["contract_version"] = speaks
        _client["last_seen_at"] = datetime.now(timezone.utc).isoformat()


def note_refusal(reason: str) -> None:
    """Counts one refusal, so the studio can say how many and why."""
    with _lock:
        _refusals[reason] = _refusals.get(reason, 0) + 1


def note_waiting(count: Any, oldest_at: Any = None) -> None:
    """
    Records how many captures the extension is holding for a studio that was
    busy. Only the extension knows this, so only the extension can say.
    """
    if not isinstance(count, int) or count < 0:
        return
    with _lock:
        _waiting["waiting"] = count
        _waiting["oldest_at"] = str(oldest_at)[:40] if oldest_at else None
        _waiting["reported_at"] = datetime.now(timezone.utc).isoformat()


def _version(text: Any) -> tuple:
    parts = []
    for chunk in str(text or "").split("."):
        digits = "".join(c for c in chunk if c.isdigit())[:10]
        parts.append(int(digits) if digits else 0)
    return tuple(parts + [0] * (4 - len(parts)))[:4]


# When this studio started. An extension that read its own folder after this
# and found its own older version there is loaded from a folder that is not
# this studio's: an in-place update would have shown it the new version.
STARTED_AT = datetime.now(timezone.utc)


def _moment(text: Any) -> Optional[datetime]:
    try:
        moment = datetime.fromisoformat(str(text).replace("Z", "+00:00")) if text else None
    except ValueError:
        return None
    return moment if moment is not None and moment.tzinfo is not None else None


def _studio_version() -> Optional[str]:
    try:
        from ..__version__ import __version__
    except (ImportError, ValueError):
        try:
            import os
            import sys
            sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
            from __version__ import __version__
        except ImportError:
            return None
    return __version__


def _newest_fresh_bridge() -> Optional[Dict[str, Any]]:
    """What the newest bridge heard from inside the freshness window said of itself, or None."""
    try:
        from . import onboarding
    except (ImportError, ValueError):
        import onboarding
    for bridge in onboarding.bridges():
        if bridge.get("connected") and (bridge.get("extension_version") or bridge.get("contract_version") is not None):
            return bridge
    return None


def handshake(extension_version: Any = None, contract_version: Any = None, self_reload: Any = None,
              files_version: Any = None, tabs_needing_reload: Any = None,
              studio_version: Optional[str] = None, files_readable: Any = None,
              files_checked_at: Any = None) -> Dict[str, Any]:
    """
    What the studio is, what it needs, and whether this client truly needs
    reloading. Answered on the heartbeat and on extension health.

    Judged on what the extension said: on the line, what it just sent;
    otherwise the newest heartbeat inside the bridge's freshness window, which
    carries its contract and whether it reloads itself. With neither, it is
    not known, and nothing is said: after every restart the studio used to
    judge a remembered nothing as stale and tell the creator to reload.

    A reload is required when the extension speaks an older contract and is
    not about to reload itself, or runs an older version than the studio and
    cannot reload itself (2.10.0 on reloads itself when its files change).
    An extension whose files are newer than it is updating itself. Tabs the
    worker could not give the new readers are their own sentence: those tabs
    need reloading, not the extension.

    Two cases a reload of itself cannot mend are said too, as loading it
    again: its folder is gone (an upgrade that extracts a new folder and
    deletes the old one), and it is older than the studio while its folder,
    read after the studio started, still holds its own version, so the
    folder is not the one the studio was updated in.
    """
    note_client(extension_version, contract_version)
    studio_version = studio_version or _studio_version()
    on_the_line = extension_version is not None or contract_version is not None
    if on_the_line:
        said: Optional[Dict[str, Any]] = {
            "extension_version": str(extension_version)[:40] if extension_version else None,
            "contract_version": contract_version if isinstance(contract_version, int) else None,
            "self_reload": self_reload is True,
            "files_version": str(files_version)[:40] if files_version else None,
            "tabs_needing_reload": tabs_needing_reload if isinstance(tabs_needing_reload, int) else None,
            "files_readable": files_readable if isinstance(files_readable, bool) else None,
            "files_checked_at": files_checked_at,
        }
    else:
        said = _newest_fresh_bridge()
        if said is not None:
            # A heartbeat from 2.10.0 on says whether it reloads itself; one
            # that does not say is from before, and cannot.
            said = dict(said, self_reload=said.get("self_reload") is True)
        with _lock:
            seen = dict(_client)
        # A capture spoke after the newest heartbeat: what it said is newer.
        # It does not say whether the extension reloads itself, so only its
        # contract is judged.
        if seen.get("last_seen_at") and (said is None or seen["last_seen_at"] > (said.get("last_seen_at") or "")):
            said = {"extension_version": seen.get("extension_version"), "contract_version": seen.get("contract_version"),
                    "self_reload": None, "files_version": None, "last_seen_at": seen.get("last_seen_at"),
                    "tabs_needing_reload": (said or {}).get("tabs_needing_reload"),
                    "files_readable": None, "files_checked_at": None}
    base = {"contract_version": CONTRACT_VERSION, "studio_version": studio_version}
    if not said:
        with _lock:
            seen = dict(_client)
        return dict(base, extension_contract_version=None, extension_version=seen.get("extension_version"),
                    last_seen_at=seen.get("last_seen_at"), reload_required=None, updating=False, message=None,
                    tabs_needing_reload=None, tabs_message=None, known=False)
    judged = _judged(said, studio_version)
    with _lock:
        last_seen = _client.get("last_seen_at")
    return dict(base, **judged, last_seen_at=said.get("last_seen_at") or last_seen, known=True)


def heard_current() -> bool:
    """
    True when the newest bridge heard from inside the freshness window needs
    no reload: Setup's advice to reload after an import from an older
    extension stands only while that is not so. Judged on the heartbeat
    alone, never on what an earlier capture left in memory.
    """
    said = _newest_fresh_bridge()
    if said is None:
        return False
    said = dict(said, self_reload=said.get("self_reload") is True)
    return _judged(said, _studio_version())["reload_required"] is False


def _judged(said: Dict[str, Any], studio_version: Optional[str]) -> Dict[str, Any]:
    """Whether what the extension said of itself needs a reload, and the sentences that say so."""
    running = said.get("extension_version")
    speaks = said.get("contract_version")
    reloads_itself = said.get("self_reload") is True
    on_disk = said.get("files_version")
    updating = reloads_itself and bool(on_disk) and bool(running) and on_disk != running
    stale_contract = speaks is None or speaks < CONTRACT_VERSION
    older = bool(running) and bool(studio_version) and _version(running) < _version(studio_version)
    cannot_reload_itself = said.get("self_reload") is False
    folder_gone = reloads_itself and said.get("files_readable") is False
    checked = _moment(said.get("files_checked_at"))
    folder_not_ours = (reloads_itself and older and not folder_gone and bool(on_disk) and on_disk == running
                       and checked is not None and checked >= STARTED_AT)
    required = not updating and (stale_contract or (older and cannot_reload_itself) or folder_gone
                                 or folder_not_ours)
    if not required:
        message = None
    elif folder_gone:
        message = (f"The folder this browser loaded Inox Hydra Bridge{' ' + running if running else ''} from is "
                   "no longer there, so it cannot update itself and the browser will not load it when it next "
                   "starts. " + LOAD_AGAIN)
    elif folder_not_ours:
        message = (f"This browser loads Inox Hydra Bridge {running} from a folder that is not this studio's, "
                   f"which runs {studio_version}, so it cannot update itself. " + LOAD_AGAIN)
    elif older and cannot_reload_itself and running:
        message = (f"This browser runs Inox Hydra Bridge {running}, older than the studio's {studio_version}, and "
                   "that version cannot reload itself. Open chrome://extensions and press Reload on Inox Hydra "
                   "Bridge once; from this version on it reloads itself when its files change.")
    else:
        message = RELOAD_MESSAGE
    tabs = said.get("tabs_needing_reload") or 0
    tabs_message = None
    if tabs:
        tabs_message = (f"{tabs} LinkedIn tab{'s' if tabs != 1 else ''} still carr{'y' if tabs != 1 else 'ies'} "
                        "an older copy of the bridge's readers, which the update could not replace: reload "
                        f"{'them' if tabs != 1 else 'it'}.")
    return dict(extension_contract_version=speaks, extension_version=running, reload_required=required,
                updating=updating, message=message, tabs_needing_reload=tabs, tabs_message=tabs_message)


def refusal_counts() -> Dict[str, Any]:
    """
    How many captures each reason has turned away since the studio started,
    and the total. Empty is empty: it does not mean no refusal ever happened,
    which is why `since` is answered beside it.
    """
    with _lock:
        counts = dict(_refusals)
    return {"refusals": counts, "total": sum(counts.values()), "since": "this studio started"}


def waiting_captures() -> Dict[str, Any]:
    """
    How many captures the extension is holding, as it last said. `measured`
    is false when it has not said anything yet, and then `waiting` is null
    rather than zero: the studio does not know, and a zero would be a claim.
    """
    with _lock:
        known = dict(_waiting)
    if "waiting" not in known:
        return {"waiting": None, "measured": False, "oldest_at": None, "reported_at": None,
                "message": "The extension has not reported since the studio started."}
    return {"waiting": known["waiting"], "measured": True, "oldest_at": known.get("oldest_at"),
            "reported_at": known.get("reported_at"),
            "message": None if known["waiting"] == 0 else
                       f"{known['waiting']} captures are waiting for the studio."}


def forget() -> None:
    """Drops what is remembered about the extension. For tests and for forget."""
    with _lock:
        _client.clear()
        _refusals.clear()
        _waiting.clear()


# ---------------------------------------------------------------------------
# What the studio has just taken: a replay is answered before the writer
# ---------------------------------------------------------------------------
#
# Ten tabs open on one post each sent every person on it, and a reloaded tab
# or a second browser sends them again: one fact, ten turns of the single
# writer, and seen_count 10. The routes keep the key of each capture they
# accepted, by the studio's own grain (grain_key), and answer the same key
# within the horizon nothing_new / already_seen without the writer. The
# tables' own unique keys stay the durable backstop: a key that has left the
# set is written as a later sighting, as it always was.
RECENT_LIMIT = 10_000
RECENT_HORIZON_SECONDS = 600.0
ALREADY_SEEN = "already_seen"


class RecentKeys:
    """A bounded set of keys with the moment each was taken, oldest first."""

    def __init__(self, limit: int = RECENT_LIMIT):
        self._limit = limit
        self._keys: "OrderedDict[str, float]" = OrderedDict()
        self._lock = threading.Lock()

    def _drop_expired(self, now: float) -> None:
        while self._keys:
            key, taken = next(iter(self._keys.items()))
            if now - taken < RECENT_HORIZON_SECONDS:
                break
            self._keys.popitem(last=False)

    def seen(self, key: Optional[str]) -> bool:
        if not key:
            return False
        now = time.monotonic()
        with self._lock:
            self._drop_expired(now)
            taken = self._keys.get(key)
            return taken is not None and now - taken < RECENT_HORIZON_SECONDS

    def remember(self, key: Optional[str]) -> None:
        if not key:
            return
        now = time.monotonic()
        with self._lock:
            self._keys[key] = now
            self._keys.move_to_end(key)
            while len(self._keys) > self._limit:
                self._keys.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._keys.clear()


RECENT = RecentKeys()


def grain_key(*parts: Any) -> str:
    """One capture's key: its grain's parts, joined and hashed, so no part is kept as written."""
    joined = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def already_seen(**counts: Any) -> Dict[str, Any]:
    """The answer to a replay of a capture the studio has just taken. Not a refusal, so not counted as one."""
    answer = {"status": "skipped", "outcome": NOTHING_NEW, "reason": ALREADY_SEEN,
              "message": "This was taken a moment ago.", "show": False, "contract_version": CONTRACT_VERSION}
    answer.update(counts)
    return answer


# ---------------------------------------------------------------------------
# One writer for a burst of captures
# ---------------------------------------------------------------------------

def through_the_writer(what: str, write: Callable, *args: Any, timeout: float = 60.0, **kwargs: Any) -> Any:
    """
    Runs one database write on the single-writer thread and waits for it.

    SQLite's busy handler polls, so thirty writers that arrive together each
    wait for the whole queue rather than for their turn: thirty captures of
    one post's engagers measured 6,047 ms of wall time against 1,318 ms for
    the same thirty done one at a time, with a mean latency 131x worse. Taking
    the turn in a queue instead of racing for the lock costs one hand-off per
    capture and removes the contention entirely.

    `write` must still open its own connection and own transaction, because
    database.write_with_retry stays the outer guard: a second studio window or
    the CLI holds the lock from another process, which an in-process queue
    cannot serialize.
    """
    try:
        return write_actor.execute_sync(write, *args, timeout=timeout, **kwargs)
    except RuntimeError as unavailable:
        # The actor is shut down or its queue is full. The write is still the
        # creator's, so it runs here rather than being lost.
        logger.warning("%s ran outside the single writer: %s", what, unavailable)
        return write(*args, **kwargs)
