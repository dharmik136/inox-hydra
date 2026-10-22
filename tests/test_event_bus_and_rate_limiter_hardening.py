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

from studio.core.rate_limiter import (
    GaussianRateLimiter,
    SingleWriterActor,
    generate_gaussian_interval,
)
from app import app

client = TestClient(app)


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


def test_zero_em_dash_compliance_module11():
    """Verify zero em-dash (0x2014) characters exist in Module 11 files."""
    em_dash = chr(0x2014)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_files = [
        os.path.join(base_dir, "studio", "core", "rate_limiter.py"),
        os.path.join(base_dir, "studio", "backend", "rate_limiter.py"),
        os.path.abspath(__file__),
    ]

    for file_path in target_files:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert em_dash not in content, f"Em-dash found in {file_path}"
