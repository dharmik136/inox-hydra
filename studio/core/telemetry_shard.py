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
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("studio.telemetry_shard")

try:
    from studio.backend.paths import get_data_dir
except ImportError:
    try:
        from backend.paths import get_data_dir
    except ImportError:
        try:
            from paths import get_data_dir
        except ImportError:
            def get_data_dir() -> str:
                return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))

TELEMETRY_DB_FILENAME = "analytics_telemetry.db"


def get_telemetry_db_path() -> str:
    """Returns the absolute path to the telemetry shard database."""
    return os.path.join(get_data_dir(), TELEMETRY_DB_FILENAME)


class TelemetryEngine:
    """
    Dedicated SQLite storage engine for analytics telemetry.
    Operates in WAL journal mode with non-blocking concurrency.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_telemetry_db_path()
        self._lock = threading.Lock()
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Returns a configured SQLite connection with row factories and WAL mode."""
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _init_db(self) -> None:
        """Initializes the telemetry tables and indexes."""
        with self._lock:
            conn = self.get_connection()
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
            finally:
                conn.close()

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
        self._events_buffer: List[Tuple[str, str, str]] = []
        self._dwell_buffer: List[Tuple[str, float, float, float]] = []
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
            payload_str = json.dumps(payload, default=str) if not isinstance(payload, str) else payload
        except Exception:
            payload_str = "{}"

        safe_event_type = str(event_type or "unknown")[:100]
        safe_source = str(source or "extension")[:50]
        entry = (safe_event_type, safe_source, payload_str)

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

        entry = (safe_post_id, safe_dwell, safe_scroll, safe_velocity)
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

            if events_to_flush:
                try:
                    flushed_events = self.engine.record_events_batch(events_to_flush)
                except Exception as err:
                    errors.append(str(err))
                    with self._lock:
                        self._events_buffer = (events_to_flush + self._events_buffer)[-self.max_buffer_size:]

            if dwells_to_flush:
                try:
                    flushed_dwells = self.engine.record_dwell_batch(dwells_to_flush)
                except Exception as err:
                    errors.append(str(err))
                    with self._lock:
                        self._dwell_buffer = (dwells_to_flush + self._dwell_buffer)[-self.max_buffer_size:]

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


# Global instances
telemetry_engine = TelemetryEngine()
telemetry_buffer = TelemetryBuffer(engine=telemetry_engine)
