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


class EventBus:
    """Thread-safe event broadcaster supporting Server-Sent Events."""

    def __init__(self, buffer_size: int = 100):
        self.buffer_size = buffer_size
        self._history: Deque[Dict[str, Any]] = deque(maxlen=buffer_size)
        self._subscribers: List[asyncio.Queue] = []
        self._event_counter: int = 0
        self._lock = asyncio.Lock()

    def publish_sync(self, event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous wrapper to publish events from background threads."""
        self._event_counter += 1
        payload = {
            "id": self._event_counter,
            "event": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat(),
        }
        self._history.append(payload)

        # Distribute to all active async queues
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(payload)
            except (asyncio.QueueFull, Exception):
                pass
        return payload

    async def publish(self, event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Asynchronously broadcast an event to all connected clients."""
        async with self._lock:
            return self.publish_sync(event_type, data)

    async def subscribe(self, last_event_id: Optional[int] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Subscribe to the event stream, replaying missed events if last_event_id is provided."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(queue)

        try:
            # Replay missed events from history buffer if client provides last_event_id
            if last_event_id is not None:
                for event in list(self._history):
                    if event["id"] > last_event_id:
                        yield event

            # Stream live events
            while True:
                event = await queue.get()
                yield event
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    def format_sse(self, event: Dict[str, Any]) -> str:
        """Format an event dictionary into standard SSE wire format."""
        event_id = event["id"]
        event_type = event["event"]
        json_data = json.dumps(event["data"])
        return f"id: {event_id}\nevent: {event_type}\ndata: {json_data}\n\n"

    def get_history(self) -> List[Dict[str, Any]]:
        """Return the current replay buffer."""
        return list(self._history)


# Global singleton event bus
event_bus = EventBus()
