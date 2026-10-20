"""
Telemetry Ingress Shard & In-Memory Batch Buffer.
=================================================
Provides decoupled, high-velocity ingestion for passive Voyager telemetry,
browser extension observer events, and reader dwell metrics.

Architectural Guarantees:
1. Subsystem Sharding: Writes land in analytics_telemetry.db, completely
   isolated from the core linkedin_studio.db ACID drafting pipeline.
2. In-Memory Ring Buffer: TelemetryBuffer ingests in RAM (< 1 microsecond)
   with zero lock contention.
3. Thread-Safe Batch Commits: Periodically flushes bulk batches via executemany.
4. WAL Mode: Uses SQLite WAL mode with synchronous = NORMAL for optimal throughput.
5. Strict Zero Em-Dashes: The character is strictly prohibited.
"""

import json
import logging
import os
import re
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("studio.telemetry_shard")

from contextlib import nullcontext

try:
    from studio.backend import paths as _paths
except ImportError:
    try:
        from backend import paths as _paths
    except ImportError:
        try:
            import paths as _paths
        except ImportError:
            _paths = None


def get_data_dir() -> str:
    if _paths is not None:
        return _paths.get_data_dir()
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))


def _active_profile() -> Optional[str]:
    """
    The profile a request pinned, or None for "whichever is active when written".

    Only the pin is read: it is a context variable, so staging stays the
    sub-microsecond RAM write it is meant to be. Resolving the active profile
    from profiles.json would stat a file on every event.
    """
    return _paths._pinned_profile.get() if _paths is not None else None


def _in_profile(profile_id: Optional[str]):
    """Pins paths to one creator profile while a batch is written."""
    if _paths is None or profile_id is None:
        return nullcontext()
    return _paths.using_profile(profile_id)

TELEMETRY_DB_FILENAME = "analytics_telemetry.db"

# What one telemetry entry keeps of the payload it records [DATA-14, BE-13].
#
# Every payload was stored whole: posts' text, commenters' names, viewers'
# job titles, and request paths that, for /identity/profiles, name the member
# whose profile was viewed. One request with an extra 10 MB field added 10 MB.
# Nothing reads any of it but a count. So an entry keeps only the payload's
# shape: its numbers, how many items each list or object held, the HTTP
# method, and the request path cut before anything that identifies a person.
# Text is never kept, and neither is a key that is not a plain field name.
MAX_PAYLOAD_KEYS = 50
_FIELD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,40}$")
_PERSON_PATH_MARKERS = ("/identity/profiles", "/in/", "/company/", "/school/")
_MEMBER_ID = re.compile(r"urn(?::|%3A)li(?::|%3A)[A-Za-z_]+(?::|%3A)[^/?#]+", re.IGNORECASE)


def _path_shape(url: str) -> str:
    """A request path with no query, and nothing after the part that would name someone."""
    path = str(url).split("?", 1)[0].split("#", 1)[0]
    for marker in _PERSON_PATH_MARKERS:
        at = path.find(marker)
        if at >= 0:
            path = path[:at + len(marker)].rstrip("/")
            break
    return _MEMBER_ID.sub("urn:li:<id>", path)[:300]


def minimal_payload(payload: Any) -> Dict[str, Any]:
    """What a telemetry entry stores of `payload`. See the note above."""
    if not isinstance(payload, dict):
        return {"shape": type(payload).__name__}
    kept: Dict[str, Any] = {}
    counts: Dict[str, int] = {}
    for key, value in list(payload.items())[:MAX_PAYLOAD_KEYS]:
        if not isinstance(key, str) or not _FIELD_NAME.match(key):
            continue
        if key == "url" and isinstance(value, str):
            kept["url"] = _path_shape(value)
        elif key == "method" and isinstance(value, str):
            kept["method"] = value.upper()[:10]
        elif isinstance(value, bool):
            kept[key] = value
        elif isinstance(value, (int, float)) and value == value and abs(value) < 1e15:
            kept[key] = value
        elif isinstance(value, (list, dict)):
            counts[key] = len(value)
    if counts:
        kept["counts"] = counts
    return kept


def get_telemetry_db_path() -> str:
    """Returns the absolute path to the telemetry shard database."""
    return os.path.join(get_data_dir(), TELEMETRY_DB_FILENAME)


class TelemetryEngine:
    """
    Dedicated SQLite storage engine for analytics telemetry.
    Operates in WAL journal mode with non-blocking concurrency.
    """

    def __init__(self, db_path: Optional[str] = None):
        # Without an explicit path, the shard is the active creator profile's,
        # resolved on every use: one fixed at import time sent every profile's
        # telemetry into whichever profile was active when the studio started.
        self._fixed_path = db_path
        self._ready: set = set()
        self._lock = threading.RLock()
        self._init_db()

    @property
    def db_path(self) -> str:
        return self._fixed_path or get_telemetry_db_path()

    def get_connection(self) -> sqlite3.Connection:
        """Returns a configured SQLite connection with row factories and WAL mode."""
        path = self.db_path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        conn = sqlite3.connect(path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA secure_delete = ON")
        if path not in self._ready:
            self._ready.add(path)
            self._create_tables(conn)
        return conn

    def _init_db(self) -> None:
        """Initializes the telemetry tables and indexes for the current shard."""
        conn = self.get_connection()
        conn.close()

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        """Creates the telemetry tables and indexes."""
        with self._lock:
            try:
                cursor = conn.cursor()
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    payload TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS post_dwell_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id TEXT NOT NULL,
                    dwell_seconds REAL NOT NULL,
                    scroll_depth REAL DEFAULT 1.0,
                    reading_velocity_wpm REAL DEFAULT 220.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_events_type ON telemetry_events(event_type)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_events_created ON telemetry_events(created_at DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_dwell_metrics_post ON post_dwell_metrics(post_id)")
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def record_events_batch(self, events: List[Tuple[str, str, str]]) -> int:
        """
        Executes bulk insertion of telemetry events:
        events format: [(event_type, source, payload_json_str), ...]
        """
        if not events:
            return 0
        with self._lock:
            conn = self.get_connection()
            try:
                cursor = conn.cursor()
                cursor.executemany("""
                INSERT INTO telemetry_events (event_type, source, payload)
                VALUES (?, ?, ?)
                """, events)
                conn.commit()
                return len(events)
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
            finally:
                conn.close()

    def record_dwell_batch(self, dwells: List[Tuple[str, float, float, float]]) -> int:
        """
        Executes bulk insertion of dwell metrics:
        dwells format: [(post_id, dwell_seconds, scroll_depth, reading_velocity_wpm), ...]
        """
        if not dwells:
            return 0
        with self._lock:
            conn = self.get_connection()
            try:
                cursor = conn.cursor()
                cursor.executemany("""
                INSERT INTO post_dwell_metrics (post_id, dwell_seconds, scroll_depth, reading_velocity_wpm)
                VALUES (?, ?, ?, ?)
                """, dwells)
                conn.commit()
                return len(dwells)
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
            finally:
                conn.close()

    def get_recent_events(self, event_type: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Queries recent telemetry events with optional type filtering and bounded limit."""
        try:
            safe_limit = max(1, min(int(limit), 500))
        except (TypeError, ValueError):
            safe_limit = 50

        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            if event_type:
                cursor.execute("""
                SELECT id, event_type, source, payload, created_at
                FROM telemetry_events
                WHERE event_type = ?
                ORDER BY id DESC LIMIT ?
                """, (str(event_type)[:100], safe_limit))
            else:
                cursor.execute("""
                SELECT id, event_type, source, payload, created_at
                FROM telemetry_events
                ORDER BY id DESC LIMIT ?
                """, (safe_limit,))
            rows = cursor.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                if item.get("payload"):
                    try:
                        item["payload"] = json.loads(item["payload"])
                    except Exception:
                        pass
                results.append(item)
            return results
        finally:
            conn.close()

    def get_status(self) -> Dict[str, Any]:
        """Returns telemetry shard diagnostics, event counts, and storage metrics."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM telemetry_events")
            event_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM post_dwell_metrics")
            dwell_count = cursor.fetchone()[0]
            cursor.execute("PRAGMA journal_mode")
            journal_mode = cursor.fetchone()[0]
            db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            return {
                "status": "healthy",
                "db_path": self.db_path,
                "journal_mode": journal_mode,
                "total_events": event_count,
                "total_dwell_records": dwell_count,
                "file_size_bytes": db_size
            }
        finally:
            conn.close()

    def clear(self) -> None:
        """Clears all telemetry data (useful for test isolation)."""
        with self._lock:
            conn = self.get_connection()
            try:
                conn.execute("DELETE FROM telemetry_events")
                conn.execute("DELETE FROM post_dwell_metrics")
                conn.commit()
            finally:
                conn.close()


class TelemetryBuffer:
    """
    In-memory staging ring buffer with non-blocking ingestion.
    Collects events in RAM and flushes in batches to TelemetryEngine.
    """

    def __init__(
        self,
        engine: Optional[TelemetryEngine] = None,
        batch_size: int = 25,
        max_buffer_size: int = 1000,
        failure_cooldown_seconds: float = 5.0
    ):
        self.engine = engine or TelemetryEngine()
        self.max_buffer_size = max(10, int(max_buffer_size))
        self.batch_size = max(1, min(int(batch_size), self.max_buffer_size))
        # (profile id, entry): the profile the entry was staged in.
        self._events_buffer: List[Tuple[Optional[str], Tuple[str, str, str]]] = []
        self._dwell_buffer: List[Tuple[Optional[str], Tuple[str, float, float, float]]] = []
        self._lock = threading.Lock()
        # Serializes flushes so two overlapping failures cannot splice their
        # restored batches back in out of chronological order.
        self._flush_lock = threading.Lock()
        self._last_flush_time = time.time()
        self._last_failure_time = 0.0
        self.failure_cooldown_seconds = float(failure_cooldown_seconds)

    def ingest(self, event_type: Any, payload: Any, source: str = "extension") -> bool:
        """
        Fast non-blocking ingestion into RAM ring buffer (< 1 microsecond).
        Automatically flushes when batch_size threshold is exceeded.
        """
        try:
            payload_str = json.dumps(minimal_payload(payload))
        except Exception:
            payload_str = "{}"

        safe_event_type = str(event_type or "unknown")[:100]
        safe_source = str(source or "extension")[:50]
        entry = (_active_profile(), (safe_event_type, safe_source, payload_str))

        flush_needed = False
        with self._lock:
            if len(self._events_buffer) >= self.max_buffer_size:
                # Evict oldest event to maintain bounded RAM usage
                self._events_buffer.pop(0)
            self._events_buffer.append(entry)
            if len(self._events_buffer) >= self.batch_size:
                flush_needed = True

        if flush_needed and self._auto_flush_allowed():
            self.flush()
        return True

    def ingest_dwell(
        self,
        post_id: Any,
        dwell_seconds: Any,
        scroll_depth: Any = 1.0,
        reading_velocity_wpm: Any = 220.0
    ) -> bool:
        """Stages a dwell metric observation into RAM with defensive bounds."""
        safe_post_id = str(post_id or "")[:100]
        try:
            safe_dwell = max(0.0, min(float(dwell_seconds), 86400.0))
        except (TypeError, ValueError):
            safe_dwell = 0.0

        try:
            safe_scroll = max(0.0, min(1.0, float(scroll_depth)))
        except (TypeError, ValueError):
            safe_scroll = 1.0

        try:
            safe_velocity = max(1.0, min(2000.0, float(reading_velocity_wpm)))
        except (TypeError, ValueError):
            safe_velocity = 220.0

        entry = (_active_profile(), (safe_post_id, safe_dwell, safe_scroll, safe_velocity))
        flush_needed = False
        with self._lock:
            if len(self._dwell_buffer) >= self.max_buffer_size:
                self._dwell_buffer.pop(0)
            self._dwell_buffer.append(entry)
            if len(self._dwell_buffer) >= self.batch_size:
                flush_needed = True

        if flush_needed and self._auto_flush_allowed():
            self.flush()
        return True

    def _auto_flush_allowed(self) -> bool:
        """
        Suppresses automatic flushes for a cooldown after a failed write.
        Without this, a broken engine turns every ingest() into a blocking
        failed write, and ingestion stops being the non-blocking RAM staging
        the buffer exists to provide. Explicit flush() calls are never gated.
        """
        with self._lock:
            last_failure = self._last_failure_time
        if not last_failure:
            return True
        return (time.time() - last_failure) >= self.failure_cooldown_seconds

    def flush(self) -> Dict[str, Any]:
        """
        Flushes staged events and dwell records to SQLite using batch executemany.
        A failed write restores the staged items to the buffer (bounded, oldest
        evicted first) so a transient SQLite error does not silently lose data.
        Returns the counts of flushed records, plus an "error" key on failure.
        """
        # One flush at a time: concurrent restores would otherwise interleave
        # and leave the buffer out of chronological order, so the bounded
        # eviction in ingest() could drop a newer event than one it keeps.
        with self._flush_lock:
            with self._lock:
                events_to_flush = self._events_buffer
                dwells_to_flush = self._dwell_buffer
                self._events_buffer = []
                self._dwell_buffer = []
                self._last_flush_time = time.time()

            flushed_events = 0
            flushed_dwells = 0
            errors = []

            # Each entry carries the creator profile it was staged in, and is
            # written to that profile's shard, whichever profile is active now.
            failed_events, failed_dwells = [], []
            for profile in dict.fromkeys(p for p, _ in events_to_flush):
                batch = [e for p, e in events_to_flush if p == profile]
                try:
                    with _in_profile(profile):
                        flushed_events += self.engine.record_events_batch(batch)
                except Exception as err:
                    errors.append(str(err))
                    failed_events += [(p, e) for p, e in events_to_flush if p == profile]
            for profile in dict.fromkeys(p for p, _ in dwells_to_flush):
                batch = [d for p, d in dwells_to_flush if p == profile]
                try:
                    with _in_profile(profile):
                        flushed_dwells += self.engine.record_dwell_batch(batch)
                except Exception as err:
                    errors.append(str(err))
                    failed_dwells += [(p, d) for p, d in dwells_to_flush if p == profile]
            if failed_events or failed_dwells:
                with self._lock:
                    self._events_buffer = (failed_events + self._events_buffer)[-self.max_buffer_size:]
                    self._dwell_buffer = (failed_dwells + self._dwell_buffer)[-self.max_buffer_size:]

            with self._lock:
                self._last_failure_time = time.time() if errors else 0.0

            result: Dict[str, Any] = {
                "flushed_events": flushed_events,
                "flushed_dwells": flushed_dwells
            }
            if errors:
                logger.warning("Telemetry flush failed, staged items restored to buffer: %s", "; ".join(errors))
                result["error"] = "; ".join(errors)
            return result

    def pending_count(self) -> int:
        """Returns total items currently in-memory waiting for flush."""
        with self._lock:
            return len(self._events_buffer) + len(self._dwell_buffer)

    def forget(self) -> None:
        """
        Removes this profile's telemetry, staged and stored, when the creator
        forgets their identity [DATA-14]. It was left behind, readings of the
        creator's own pages included. Staged entries bound for this profile (an
        unpinned one is written to whichever is active) are dropped first, so a
        flush cannot write them back after the shard is cleared.
        """
        profile = _active_profile()
        with self._flush_lock:
            with self._lock:
                self._events_buffer = [(p, e) for p, e in self._events_buffer if p not in (profile, None)]
                self._dwell_buffer = [(p, d) for p, d in self._dwell_buffer if p not in (profile, None)]
            self.engine.clear()


# Global instances
telemetry_engine = TelemetryEngine()
telemetry_buffer = TelemetryBuffer(engine=telemetry_engine)
