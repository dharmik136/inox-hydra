"""
Lightweight In-Memory Event Bus & Server-Sent Events (SSE) Hub.
==============================================================
Provides zero-latency live streaming from background workers (Telegram daemon,
scheduler, passive observer) to the active browser Studio UI.
Includes an event replay buffer with Last-Event-ID for disconnect resilience.
Strict Anti-Slop Rule: Zero em-dashes.
"""

from collections import deque
from datetime import datetime
from typing import Any, AsyncGenerator, Deque, Dict, List, Optional
import asyncio
import json
import logging
import re
import threading

logger = logging.getLogger("studio.event_bus")

MAX_SUBSCRIBERS = 200
MAX_EVENT_TYPE_LENGTH = 100
DEFAULT_BUFFER_SIZE = 100
MAX_BUFFER_SIZE = 1000


class EventBus:
    """Thread-safe event broadcaster supporting Server-Sent Events."""

    def __init__(self, buffer_size: int = DEFAULT_BUFFER_SIZE):
        self.buffer_size = max(10, min(int(buffer_size), MAX_BUFFER_SIZE))
        self._history: Deque[Dict[str, Any]] = deque(maxlen=self.buffer_size)
        self._subscribers: List[asyncio.Queue] = []
        self._dropped_counts: Dict[int, int] = {}
        self._event_counter: int = 0
        self._lock = asyncio.Lock()
        # Event ids are handed out from background threads as well as the
        # loop, so the counter needs a real lock rather than the GIL.
        self._counter_lock = threading.Lock()
        # The loop that owns the subscriber queues. Captured on subscribe so
        # that a publish from a worker thread can hand work back to it.
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def subscriber_count(self) -> int:
        """Returns the number of active async subscribers."""
        return len(self._subscribers)

    def _deliver(self, queue: "asyncio.Queue", payload: Dict[str, Any]) -> None:
        """Offers one payload to one subscriber queue, accounting for a stalled reader."""
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            qid = id(queue)
            self._dropped_counts[qid] = self._dropped_counts.get(qid, 0) + 1
            if self._dropped_counts[qid] > 20:
                self._retire(queue)
        except Exception:
            self._retire(queue)

    def _retire(self, queue: "asyncio.Queue") -> None:
        """Drops a subscriber that can no longer receive."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)
        self._dropped_counts.pop(id(queue), None)

    def publish_sync(self, event_type: str, data: Any) -> Dict[str, Any]:
        """Synchronous wrapper to publish events from background threads."""
        with self._counter_lock:
            self._event_counter += 1
            event_id = self._event_counter
        safe_type = re.sub(r"[\r\n]+", "", str(event_type or "unknown")).strip()[:MAX_EVENT_TYPE_LENGTH]
        if not safe_type:
            safe_type = "generic_event"

        safe_data = data if isinstance(data, dict) else {"payload": data}

        payload = {
            "id": event_id,
            "event": safe_type,
            "data": safe_data,
            "timestamp": datetime.now().isoformat(),
        }
        self._history.append(payload)

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        owner_loop = self._loop
        # asyncio.Queue is not thread safe. Calling put_nowait from a worker
        # thread resolves the waiting getter's future but never wakes the
        # selector, so an idle loop, which is exactly what an SSE stream is
        # between events, sits in select and the event is never delivered.
        # The scheduler publishes post_published and schedule_recovery from
        # its own thread, so those notifications have to be handed back to
        # the owning loop rather than pushed across the thread boundary.
        if owner_loop is not None and owner_loop is not running_loop:
            for queue in list(self._subscribers):
                try:
                    owner_loop.call_soon_threadsafe(self._deliver, queue, payload)
                except RuntimeError:
                    # The loop is closed, so every queue it owns is dead.
                    self._retire(queue)
            return payload

        for queue in list(self._subscribers):
            self._deliver(queue, payload)

        return payload

    async def publish(self, event_type: str, data: Any) -> Dict[str, Any]:
        """Asynchronously broadcast an event to all connected clients."""
        async with self._lock:
            return self.publish_sync(event_type, data)

    async def subscribe(self, last_event_id: Optional[Any] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Subscribe to the event stream, replaying missed events if last_event_id is provided."""
        # Evict oldest queue if exceeding max subscribers to prevent unbounded memory growth
        while len(self._subscribers) >= MAX_SUBSCRIBERS:
            oldest = self._subscribers.pop(0)
            self._dropped_counts.pop(id(oldest), None)

        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(queue)

        parsed_last_id: Optional[int] = None
        if last_event_id is not None:
            try:
                parsed_last_id = int(last_event_id)
            except (ValueError, TypeError):
                parsed_last_id = None

        try:
            # Replay missed events from history buffer if client provides valid last_event_id
            if parsed_last_id is not None:
                for event in list(self._history):
                    if isinstance(event, dict) and event.get("id", 0) > parsed_last_id:
                        yield event

            # Stream live events
            while True:
                event = await queue.get()
                yield event
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)
            self._dropped_counts.pop(id(queue), None)

    def format_sse(self, event: Any) -> str:
        """Format an event dictionary into standard SSE wire format with security sanitization."""
        if not isinstance(event, dict):
            return ""
        event_id = event.get("id", 0)
        event_type = re.sub(r"[\r\n]+", "", str(event.get("event", "message")))[:MAX_EVENT_TYPE_LENGTH]
        data = event.get("data", {})
        try:
            json_data = json.dumps(data, default=str)
        except Exception:
            json_data = json.dumps({"error": "unserializable_payload"})
        return f"id: {event_id}\nevent: {event_type}\ndata: {json_data}\n\n"

    def get_history(self) -> List[Dict[str, Any]]:
        """Return the current replay buffer."""
        return list(self._history)


# Global singleton event bus
event_bus = EventBus()
