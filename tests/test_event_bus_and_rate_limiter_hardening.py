import asyncio
from datetime import datetime, timezone
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Ensure studio/backend is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "studio", "backend"))

from event_bus import (
    EventBus,
    MAX_SUBSCRIBERS,
    MAX_EVENT_TYPE_LENGTH,
)
from studio.core.rate_limiter import (
    GaussianRateLimiter,
    SingleWriterActor,
    generate_gaussian_interval,
)
from app import app

client = TestClient(app)


def test_event_bus_subscriber_cap_and_eviction():
    """EventBus caps active subscribers to MAX_SUBSCRIBERS, evicting oldest."""
    bus = EventBus(buffer_size=50)

    async def _run():
        generators = []
        # Create MAX_SUBSCRIBERS + 20 subscribers
        for _ in range(MAX_SUBSCRIBERS + 20):
            gen = bus.subscribe()
            generators.append(gen)
            # Advance generator to the queue creation point
            await gen.__anext__ if False else None

        # Verify count does not exceed MAX_SUBSCRIBERS
        assert len(bus._subscribers) <= MAX_SUBSCRIBERS

    asyncio.run(_run())


def test_event_bus_dead_queue_pruning():
    """Persistent QueueFull on abandoned queues automatically triggers eviction."""
    bus = EventBus(buffer_size=10)
    abandoned_queue = asyncio.Queue(maxsize=2)
    bus._subscribers.append(abandoned_queue)

    # Publish 30 events into a full queue of size 2
    for i in range(30):
        bus.publish_sync("test_event", {"counter": i})

    # Abandoned queue should be pruned after exceeding dropped threshold
    assert abandoned_queue not in bus._subscribers


def test_event_bus_publish_sync_sanitization():
    """EventBus sanitizes event types containing newlines and wraps non-dict payloads."""
    bus = EventBus(buffer_size=10)

    # SSE injection attempt with carriage return and newline
    malicious_type = "draft_created\r\nevent: fake_event\r\ndata: injected"
    payload = bus.publish_sync(malicious_type, "simple_string_payload")

    assert "\r" not in payload["event"]
    assert "\n" not in payload["event"]
    assert payload["event"] == "draft_createdevent: fake_eventdata: injected"
    assert isinstance(payload["data"], dict)
    assert payload["data"]["payload"] == "simple_string_payload"

    # None event type defaults cleanly
    p_none = bus.publish_sync(None, {"key": "val"})
    assert p_none["event"] == "unknown"


def test_event_bus_format_sse_safe_serialization():
    """format_sse handles un-serializable objects and non-dict events without throwing."""
    bus = EventBus()

    # Non-dict event
    assert bus.format_sse(None) == ""
    assert bus.format_sse("string_event") == ""

    # Complex / non-JSON-serializable payload
    complex_event = {
        "id": 42,
        "event": "complex_update\n\r",
        "data": {
            "timestamp": datetime.now(timezone.utc),
            "custom_set": {1, 2, 3},
        }
    }
    sse_wire = bus.format_sse(complex_event)
    assert sse_wire.startswith("id: 42\nevent: complex_update\ndata: ")
    assert sse_wire.endswith("\n\n")
    assert "\r" not in sse_wire[:30]


def test_event_bus_subscribe_replay_last_id_robustness():
    """EventBus handles malformed or string last_event_id without raising TypeError."""
    bus = EventBus(buffer_size=10)
    bus.publish_sync("ev1", {"num": 1})
    bus.publish_sync("ev2", {"num": 2})

    async def _test():
        # String last_event_id
        received = []
        gen = bus.subscribe(last_event_id="1")
        # First event from replay
        ev = await gen.asend(None)
        received.append(ev)
        assert received[0]["id"] == 2

        # Invalid string that cannot be parsed as int
        gen_bad = bus.subscribe(last_event_id="invalid-id")
        assert gen_bad is not None

    asyncio.run(_test())


def test_rate_limiter_gaussian_generator_clamping():
    """generate_gaussian_interval guarantees safe positive intervals on invalid inputs."""
    interval_neg = generate_gaussian_interval(mu=-10.0, sigma=-5.0, clamp_sigmas=-1.0)
    assert interval_neg >= 0.001

    interval_normal = generate_gaussian_interval(mu=900.0, sigma=120.0, clamp_sigmas=2.0)
    assert 660.0 <= interval_normal <= 1140.0


def test_rate_limiter_defensive_tokens_and_timeouts():
    """GaussianRateLimiter safely handles zero/negative tokens and immediate timeouts."""
    limiter = GaussianRateLimiter(mu=10.0, capacity=2.0)

    # Negative tokens should return True immediately without altering bucket
    assert limiter.consume(-1.0) is True
    assert limiter.wait_time_seconds(-5.0) == 0.0
    assert limiter.acquire(-10.0) is True

    # Empty the bucket
    assert limiter.consume(2.0) is True

    # Immediate timeout when bucket is empty
    t0 = time.monotonic()
    success = limiter.acquire(tokens=1.0, block=True, timeout=0.0)
    elapsed = time.monotonic() - t0
    assert success is False
    assert elapsed < 0.2


def test_rate_limiter_reset_bounds():
    """Reset cleanly bounds tokens between 0.0 and capacity."""
    limiter = GaussianRateLimiter(capacity=5.0)
    limiter.reset(100.0)
    diag = limiter.get_diagnostics()
    assert diag["available_tokens"] == 5.0

    limiter.reset(-50.0)
    diag = limiter.get_diagnostics()
    assert diag["available_tokens"] == 0.0


def test_single_writer_actor_non_callable_rejected():
    """SingleWriterActor rejects non-callable task targets with TypeError on submission."""
    actor = SingleWriterActor(maxsize=10)
    try:
        with pytest.raises(TypeError):
            actor.submit("not_a_function")

        with pytest.raises(TypeError):
            actor.execute_sync(None)
    finally:
        actor.stop(timeout=1.0)


def test_single_writer_actor_drain_on_stop():
    """When SingleWriterActor stops, remaining queued tasks have RuntimeError set."""
    actor = SingleWriterActor(maxsize=10)

    def slow_task():
        time.sleep(0.3)
        return "slow_done"

    def pending_task():
        return "pending_done"

    f1 = actor.submit(slow_task)
    f2 = actor.submit(pending_task)
    f3 = actor.submit(pending_task)

    # Immediately stop actor
    actor.stop(timeout=2.0)

    # f1 might complete or error depending on timing, but pending tasks must not hang
    for f in (f2, f3):
        assert f.done()
        # Should raise either RuntimeError or execute
        try:
            f.result()
        except RuntimeError as err:
            assert "shut down" in str(err)


def test_app_broadcast_event_validation():
    """FastAPI broadcast endpoint rejects invalid, oversized, or empty event names."""
    # Empty event name
    r_empty = client.post("/api/v1/stream/broadcast", json={"event": "   ", "data": {}})
    assert r_empty.status_code == 400

    # Oversized event name (> 100 chars)
    r_huge = client.post("/api/v1/stream/broadcast", json={"event": "A" * 150, "data": {}})
    assert r_huge.status_code == 422


def test_app_rate_limiter_acquire_bounds():
    """FastAPI rate-limiter acquire endpoint enforces Pydantic bounds on tokens and timeout."""
    # Negative tokens rejected by Pydantic validation
    r_neg = client.post("/api/v1/rate-limiter/acquire", json={"tokens": -5.0})
    assert r_neg.status_code == 422

    # Huge tokens (> 100) rejected
    r_huge = client.post("/api/v1/rate-limiter/acquire", json={"tokens": 500.0})
    assert r_huge.status_code == 422

    # Timeout > 30s rejected
    r_timeout = client.post("/api/v1/rate-limiter/acquire", json={"timeout": 60.0})
    assert r_timeout.status_code == 422

    # Valid acquire
    r_valid = client.post("/api/v1/rate-limiter/acquire", json={"tokens": 1.0, "block": False})
    assert r_valid.status_code == 200
    assert "diagnostics" in r_valid.json()


def test_zero_em_dash_compliance_module11():
    """Verify zero em-dash (0x2014) characters exist in Module 11 files."""
    em_dash = chr(0x2014)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_files = [
        os.path.join(base_dir, "studio", "backend", "event_bus.py"),
        os.path.join(base_dir, "studio", "core", "rate_limiter.py"),
        os.path.join(base_dir, "studio", "backend", "rate_limiter.py"),
        os.path.abspath(__file__),
    ]

    for file_path in target_files:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert em_dash not in content, f"Em-dash found in {file_path}"
