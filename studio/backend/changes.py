"""
What changed, told to the windows that are listening.
=====================================================

Every screen used to learn about a capture by asking again on a timer, and
each ask re-ran the whole onboarding aggregate to hear, almost always, that
nothing had changed: Setup at 3 seconds cost about 1,700 statements a minute
while idle. The studio knows the moment it writes something, so it says so
instead, and a screen reads again only then.

Two sources feed one stream:

- The ingest paths call `publish(kind)` after their write commits: a capture
  logged, a heartbeat, the creator's posts, a post's readings, the account's
  daily figures, an engagement on one of the creator's posts, the creator's
  own engagement elsewhere, the creator's profile, an import's progress, a
  post the queue moved. A kind is a word for what changed, so a window can
  decide what to read again, never a figure.
- A watcher reads `PRAGMA data_version` on one long-lived connection about
  once a second while any window is listening. SQLite changes that value
  whenever another connection commits, in this process or in any other, so a
  write from the CLI, a second studio, or a path nobody hooked is still
  noticed, and announced as the kind "database". A change the bus was told
  about is not announced twice: the watcher only speaks when data_version
  moved and nothing was published since it last looked.

Each listener is one open GET /api/v1/events (studio/backend/routers/events.py),
one per window. The watcher runs on a thread of its own, started by the first
listener. It stops looking the moment the last listener leaves, so a studio
with no window in view runs nothing, and keeps its connection a minute longer
so a window that was hidden briefly can still be told truthfully that nothing
changed; then it closes the connection and the thread ends. Nothing starts at
import.

A restore replaces the database file, and Windows refuses to replace a file
any handle holds, so the restore puts the watcher's connection down first
(`put_down`) and lets it reopen after (`let_go`); the reopened watcher tells
the windows to read again, which is how a screen comes to show the restored
data without a reload.

Strict Invariants:
- Zero em-dashes in any code, docstring, or comment.
- Nothing here leaves the machine: the stream answers on loopback behind the
  same three checks as every other route, and publishes words, not figures.
"""

import asyncio
import logging
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from . import paths, sqlite_open
except ImportError:
    import paths
    import sqlite_open

_log = logging.getLogger("studio.changes")

# The words a change can carry. "readings" are one post's figures and
# "account" the creator's daily figures; "people" is someone engaging with one
# of the creator's posts and "outbound" the creator engaging elsewhere.
# "database" is the watcher's, something was committed that no publisher
# named, and a writer of several unrelated things says it too: either way a
# window takes it as "anything may have changed".
KINDS = ("capture", "heartbeat", "posts", "readings", "account", "people", "outbound",
         "identity", "imports", "queue", "database")

# What a change may carry beside its kind, so a window can tell whether it
# alters what that window shows: which reader ran and whether it drifted, whether
# a heartbeat said how many captures wait, which post, how someone engaged, and
# who by the studio's own id. Never a name, never text, never a figure: an
# identifier that does not match its shape is dropped, and a change without it
# is read as "this kind, anywhere".
IDENTIFIERS = {
    "extractor": re.compile(r"^[a-z_]{1,40}$"),
    "post": re.compile(r"^urn:li:activity:\d{1,25}$"),
    "interaction": re.compile(r"^(comment|reaction|repost)$"),
    "lead": re.compile(r"^[A-Za-z0-9_.:-]{1,80}$"),
}
FLAGS = ("drift", "waiting")

# The most notes one message carries; past this each kind is sent bare.
MAX_NOTES = 32

# How often the watcher looks at data_version while anyone listens. One look
# is one PRAGMA on an open connection, well under a millisecond; a second is
# the latency a creator notices for a write the bus was not told about.
WATCH_EVERY_S = 1.0

# How long the watcher keeps its connection after the last listener leaves.
# A window that comes back within it is told whether anything changed while
# it was hidden; after it the connection is closed, so an idle studio holds no
# handle on the file, and a window that comes back is told to read again.
# Longer than the fifteen seconds after which a returning screen reads again
# anyway (studio/ui/src/lib/refresh.ts), which is where the knowledge pays.
IDLE_CLOSE_S = 60.0

# The hold a restore puts on the database files, shared between both import
# names of sqlite_open; see that module.
_FILES = sys.modules.get("_inox_database_files")


def _files_free() -> bool:
    gate = _FILES or sys.modules.get("_inox_database_files")
    return gate is None or gate.free.is_set()


# ---------------------------------------------------------------------------
# The bus
# ---------------------------------------------------------------------------

# Names this process in every event id. A window that reconnects after the
# studio restarted names an id from the old process, and a sequence alone
# could match the new process's count by chance and say "nothing changed"
# when a whole restart went by.
BOOT = secrets.token_hex(4)

_lock = threading.Lock()
_sequence = 0
_subscribers: Dict[int, "Subscription"] = {}


class Subscription:
    """One listening window, woken on the loop it was opened on."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.woken = asyncio.Event()
        self.closing = False
        self._notes: List[Dict[str, Any]] = []

    def _deliver(self, note: Dict[str, Any]) -> None:
        self._notes.append(note)
        self.woken.set()

    def _close(self) -> None:
        self.closing = True
        self.woken.set()

    async def wait(self, timeout: float) -> bool:
        """True when something was delivered before the timeout, else False."""
        try:
            await asyncio.wait_for(self.woken.wait(), timeout)
        except asyncio.TimeoutError:
            return False
        self.woken.clear()
        return True

    def take(self) -> Tuple[List[str], List[Dict[str, Any]]]:
        """
        The kinds delivered since the last take, each once in a fixed order,
        and the changes themselves, each once. A burst of the same change is
        one note; past MAX_NOTES distinct ones, each kind is sent bare.
        """
        notes: List[Dict[str, Any]] = []
        seen = set()
        for note in self._notes:
            key = tuple(sorted(note.items()))
            if key not in seen:
                seen.add(key)
                notes.append(note)
        self._notes.clear()
        kinds = sorted({note["kind"] for note in notes})
        if len(notes) > MAX_NOTES:
            notes = [{"kind": kind} for kind in kinds]
        return kinds, notes


def sequence() -> int:
    """How many changes have been published since this studio started."""
    with _lock:
        return _sequence


def current_id() -> str:
    """The id of the latest change, as the stream names it: this process and its count."""
    return f"{BOOT}-{sequence()}"


def note_of(kind: str, identifiers: Dict[str, Any]) -> Dict[str, Any]:
    """The change as it is sent: the kind, and only identifiers of the right shape."""
    note: Dict[str, Any] = {"kind": kind}
    for name, value in identifiers.items():
        if name in FLAGS and isinstance(value, bool):
            note[name] = value
        elif name in IDENTIFIERS and isinstance(value, str) and IDENTIFIERS[name].match(value):
            note[name] = value
        elif value is not None:
            _log.debug("A %s change dropped its %s: not an identifier of that shape.", kind, name)
    return note


def publish(kind: str, **identifiers: Any) -> None:
    """
    Says that something of this kind changed, with what a window needs to
    decide whether it shows it (see IDENTIFIERS). Safe from any thread: the
    ingest paths run on worker threads and on the single writer, and each
    listener is woken on its own loop. A writer's identifier of the wrong
    shape is dropped rather than raised: the write has already happened.
    """
    global _sequence
    if kind not in KINDS:
        raise ValueError(f"not a kind of change: {kind!r}")
    note = note_of(kind, identifiers)
    with _lock:
        _sequence += 1
        targets = list(_subscribers.values())
    for sub in targets:
        try:
            sub.loop.call_soon_threadsafe(sub._deliver, dict(note))
        except RuntimeError:
            # The loop is closed; the stream it served is already gone.
            pass


def publish_written(**written: Any) -> None:
    """
    Publishes each kind a writer says it wrote, by its own count: for one
    whose answer counts several things, so that a write of nothing says
    nothing. `publish_written(account=3, people=0)` publishes "account".
    """
    for kind, count in written.items():
        if count:
            publish(kind)


def published(result: Dict[str, Any], kind: str, statuses: Tuple[str, ...]) -> Dict[str, Any]:
    """
    Publishes `kind` when a writer's answer has one of `statuses`, and hands
    the answer back, for a route that returns its writer's answer as it is.
    """
    if isinstance(result, dict) and result.get("status") in statuses:
        publish(kind)
    return result


def subscriber_count() -> int:
    with _lock:
        return len(_subscribers)


async def open_subscription() -> Subscription:
    """
    Registers the calling stream as a listener. The watcher takes one look at
    the database first, so a stream that names what it last saw is told
    truthfully whether anything happened while it was away.
    """
    loop = asyncio.get_running_loop()
    _hook_server_stop()
    await loop.run_in_executor(None, _watch.look)
    sub = Subscription(loop)
    with _lock:
        _subscribers[id(sub)] = sub
        _watch.ensure_ticking_locked()
    return sub


def unsubscribe(sub: Subscription) -> None:
    with _lock:
        _subscribers.pop(id(sub), None)


def close_all(loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
    """
    Ends every open stream, or every one served on `loop`, so a stopping
    server has no response in flight. A test runs several servers in one
    process, and one of them stopping must not end the others' streams.
    """
    with _lock:
        targets = [sub for sub in _subscribers.values() if loop is None or sub.loop is loop]
    for sub in targets:
        try:
            sub.loop.call_soon_threadsafe(sub._close)
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# The data_version watcher
# ---------------------------------------------------------------------------

class _Watch:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.conn: Optional[sqlite3.Connection] = None
        self.path: Optional[str] = None
        self.version: Optional[int] = None
        self.down = False
        self.thread: Optional[threading.Thread] = None
        self.seen_sequence = 0
        self.looks = 0

    def _close_locked(self) -> None:
        if self.conn is not None:
            try:
                self.conn.close()
            except sqlite3.Error:
                pass
        self.conn = None
        self.path = None

    def _read_locked(self) -> int:
        # fetchall steps the statement to its end, so no read transaction is
        # left open between looks to hold back a checkpoint or a VACUUM.
        return int(self.conn.execute("PRAGMA data_version").fetchall()[0][0])

    def _tick_locked(self) -> str:
        """One look. Returns closed, opened, reopened, changed or same."""
        if self.down or not _files_free():
            self._close_locked()
            return "closed"
        path = paths.get_db_path()
        if self.conn is None or path != self.path:
            had_one = self.version is not None
            self._close_locked()
            if not os.path.exists(path):
                return "closed"
            try:
                # Closed from the restore's thread, so not bound to this one.
                # Read only; the connection never writes, so it never holds
                # a lock a writer waits on.
                self.conn = sqlite_open.connect(path, timeout=5.0, check_same_thread=False)
                self.conn.execute("PRAGMA query_only = ON")
                self.version = self._read_locked()
            except sqlite3.Error as why:
                _log.warning("The change watcher could not open the database: %s", why)
                self._close_locked()
                return "closed"
            self.path = path
            return "reopened" if had_one else "opened"
        try:
            version = self._read_locked()
        except sqlite3.Error as why:
            _log.warning("The change watcher lost the database: %s", why)
            self._close_locked()
            return "closed"
        if version != self.version:
            self.version = version
            return "changed"
        return "same"

    def look(self) -> None:
        """
        Looks once and announces "database" when the file changed and nothing
        was published since the last look, or when the watcher reopened its
        connection (after a restore or a profile switch, anything may have
        changed). A published write moves data_version too, and is not
        announced a second time.
        """
        with self.lock:
            self.looks += 1
            outcome = self._tick_locked()
            unexplained = outcome in ("changed", "reopened") and sequence() == self.seen_sequence
            if unexplained:
                publish("database")
            self.seen_sequence = sequence()

    def ensure_ticking_locked(self) -> None:
        """Called under the bus lock, with at least one subscriber registered."""
        if self.thread is not None and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="studio-changes-watch", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        idle_since: Optional[float] = None
        while True:
            time.sleep(WATCH_EVERY_S)
            # The watch lock first, then the bus lock, the order look() takes
            # them in, so a listener arriving now cannot deadlock with this.
            with self.lock:
                with _lock:
                    listening = bool(_subscribers)
                    if listening:
                        idle_since = None
                    else:
                        idle_since = idle_since if idle_since is not None else time.monotonic()
                        if time.monotonic() - idle_since >= IDLE_CLOSE_S:
                            self.thread = None
                            self._close_locked()
                            return
            if not listening:
                continue
            try:
                self.look()
            except Exception:
                _log.warning("The change watcher's look failed.", exc_info=True)

    def put_down(self) -> None:
        with self.lock:
            self.down = True
            self._close_locked()

    def let_go(self) -> None:
        with self.lock:
            self.down = False

    def state(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "open": self.conn is not None,
                "path": self.path,
                "down": self.down,
                "ticking": self.thread is not None and self.thread.is_alive(),
                "listening": subscriber_count(),
                "looks": self.looks,
            }


_watch = _Watch()


def put_down() -> None:
    """Closes the watcher's connection and keeps it closed, for a restore's file swap."""
    _watch.put_down()


def let_go() -> None:
    """Lets the watcher open the database again, after the swap."""
    _watch.let_go()


def watch_state() -> Dict[str, Any]:
    """What the watcher is doing, for tests and diagnostics."""
    return _watch.state()


# ---------------------------------------------------------------------------
# A stopping server
# ---------------------------------------------------------------------------

_hooked = False


def _hook_server_stop() -> None:
    """
    Ends the streams when uvicorn begins its graceful shutdown.

    uvicorn waits for every in-flight response before it exits, and with no
    graceful timeout set it waits for ever, so a stream that never ended would
    hold a reload, a Ctrl+C or the desktop shell's stop until the process was
    killed. The shutdown is a method looked up on the class when it runs, so
    wrapping it here, once, reaches a server that is already running.
    """
    global _hooked
    if _hooked:
        return
    _hooked = True
    try:
        from uvicorn.server import Server
    except ImportError:  # pragma: no cover - the test client needs no server
        return
    original = Server.shutdown

    async def shutdown(self, sockets=None):
        close_all(asyncio.get_running_loop())
        await original(self, sockets=sockets)

    shutdown.__wrapped__ = original  # type: ignore[attr-defined]
    Server.shutdown = shutdown
