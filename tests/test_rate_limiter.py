"""
Day 02 Test Suite: Anti-Detection Rate Limiter, Gaussian Jitter & Concurrency Actor.
====================================================================================
Validates Project Prudent PRD-002 and Day 02 specifications:
1. Gaussian jitter statistical distribution (Delta t = mu + sigma * N(0, 1)).
2. Strict clamping bounds [mu - 2*sigma, mu + 2*sigma] = [660.0s, 1140.0s].
3. Token bucket consumption and replenishment.
4. Single-Writer Actor Queue serialized writes under concurrent load.
5. Ingestion and fold safety of Day 02 launch kit post.
"""

from datetime import datetime
import math
import os
import sys
import threading
import pytest
from fastapi.testclient import TestClient

# Ensure studio/backend and studio/core are importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "core")))

from app import app
from database import get_db, seed_day02_draft
from rate_limiter import (
    GaussianRateLimiter,
    SingleWriterActor,
    generate_gaussian_interval,
    rate_limiter,
    write_actor,
)
from linkedin_client import linkedin_client

client = TestClient(app)


# -------------------------------------------------------------
# 1. Statistical Verification: Gaussian Jitter & Clamping Bounds
# -------------------------------------------------------------
def test_gaussian_interval_clamping_and_distribution():
    """
    Validates that 1,000 samples follow a normal distribution with:
    - 100% adherence to clamping bounds [660.0, 1140.0].
    - Mean convergence to 900.0 within +/- 15.0 seconds.
    - Standard deviation convergence to 120.0 within +/- 25.0 seconds.
    - High entropy (distinct intervals proving non-deterministic jitter).
    """
    mu = 900.0
    sigma = 120.0
    clamp_sigmas = 2.0
    min_bound = mu - (clamp_sigmas * sigma)  # 660.0
    max_bound = mu + (clamp_sigmas * sigma)  # 1140.0

    sample_size = 1000
    samples = [generate_gaussian_interval(mu=mu, sigma=sigma, clamp_sigmas=clamp_sigmas) for _ in range(sample_size)]

    # 1. Strict Clamping Verification
    for s in samples:
        assert min_bound <= s <= max_bound, f"Sample {s} breached clamping window [{min_bound}, {max_bound}]"

    # 2. Sample Mean Convergence
    sample_mean = sum(samples) / sample_size
    assert abs(sample_mean - mu) < 15.0, f"Sample mean {sample_mean} deviated too far from mu {mu}"

    # 3. Sample Standard Deviation
    variance = sum((x - sample_mean) ** 2 for x in samples) / (sample_size - 1)
    sample_std = math.sqrt(variance)
    assert abs(sample_std - sigma) < 25.0, f"Sample std {sample_std} deviated too far from sigma {sigma}"

    # 4. Non-Deterministic Behavioral Entropy
    unique_count = len(set(samples))
    assert unique_count > 50, f"Expected high entropy interval spacing, but found only {unique_count} unique values"


# -------------------------------------------------------------
# 2. Token Bucket Mechanics: Burst Capacity & Replenishment
# -------------------------------------------------------------
def test_token_bucket_consumption_and_refill():
    """Validates token bucket consumption, depletion, wait calculation, and reset."""
    limiter = GaussianRateLimiter(mu=900.0, sigma=120.0, capacity=2.0, initial_tokens=2.0)

    # First consumption succeeds
    assert limiter.consume(1.0) is True
    # Second consumption succeeds (burst capacity 2.0)
    assert limiter.consume(1.0) is True
    # Third consumption rejected (depleted)
    assert limiter.consume(1.0) is False

    # Wait time must be a positive Gaussian-jittered interval within clamping bounds
    wait_time = limiter.wait_time_seconds(1.0)
    assert 660.0 <= wait_time <= 1140.0

    # Reset restores tokens to full capacity
    limiter.reset()
    assert limiter.consume(1.0) is True


# -------------------------------------------------------------
# 3. Concurrency: Single-Writer Actor Queue
# -------------------------------------------------------------
def test_single_writer_actor_concurrent_load():
    """
    Submits 25 concurrent write operations to SingleWriterActor.
    Validates sequential processing without SQLite lock contention.
    """
    actor = SingleWriterActor(maxsize=100)
    results = []
    lock = threading.Lock()

    def write_task(task_id: int) -> int:
        conn = get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (f"test_key_{task_id}", f"value_{task_id}")
                )
        finally:
            conn.close()
        with lock:
            results.append(task_id)
        return task_id

    futures = [actor.submit(write_task, i) for i in range(25)]

    # Await all futures
    for f in futures:
        res = f.result(timeout=5.0)
        assert isinstance(res, int)

    assert len(results) == 25
    actor.stop()


# -------------------------------------------------------------
# 4. Anti-Bot Rate Limiting & Health API Endpoints
# -------------------------------------------------------------
def test_rate_limiter_api_endpoints():
    """Tests /api/v1/rate-limiter/status and /api/v1/rate-limiter/acquire endpoints."""
    # Status endpoint
    res_status = client.get("/api/v1/rate-limiter/status")
    assert res_status.status_code == 200
    diag = res_status.json()["diagnostics"]
    assert diag["mean_interval_seconds"] == 900.0
    assert diag["std_deviation_seconds"] == 120.0
    assert diag["clamping_bounds"] == [660.0, 1140.0]

    # Acquire endpoint (non-blocking)
    res_acq = client.post("/api/v1/rate-limiter/acquire", json={"tokens": 1.0, "block": False})
    assert res_acq.status_code == 200
    data = res_acq.json()
    assert "acquired" in data
    assert "wait_time_seconds" in data

    # Metrics endpoint
    res_metrics = client.get("/api/v1/rate-limiter/single-writer/metrics")
    assert res_metrics.status_code == 200
    m = res_metrics.json()["metrics"]
    assert "queue_depth" in m
    assert "tasks_processed" in m


def test_linkedin_client_gaussian_rate_limit():
    """Tests that linkedin_client respects Gaussian rate limiter when enforce_rate_limit=True."""
    # Deplete rate limiter
    rate_limiter.consume(rate_limiter.capacity + 1.0)

    # Calling sync_live_profile_and_stats with enforce_rate_limit=True should be throttled
    res = linkedin_client.sync_live_profile_and_stats(mock=False, enforce_rate_limit=True)
    if not linkedin_client.is_authenticated():
        assert res["status"] in ("skipped", "rate_limited")
    else:
        assert res["status"] == "rate_limited"
        assert res["wait_time_seconds"] >= 660.0

    # Reset limiter for subsequent tests
    rate_limiter.reset()


# -------------------------------------------------------------
# 5. Day 02 Launch Kit Post Ingestion & Invariant Audit
# -------------------------------------------------------------
def test_day02_draft_and_post_seeded():
    """Validates that Day 02 launch draft exists in drafts and posts with 0 em-dashes and safe mobile fold."""
    # Ensure seeded
    seed_day02_draft()

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM drafts WHERE title LIKE '%The Fallacy of Heavy Web Scraping%'")
    draft = c.fetchone()
    assert draft is not None, "Day 02 launch draft missing from drafts table!"

    # Invariant checks:
    assert draft["status"] == "DRAFT"
    assert draft["is_pre_fold_safe"] == 1
    assert draft["lines_above_fold"] == 3
    assert draft["char_count"] > 1000

    # Strict Zero Em-Dashes
    assert "\u2014" not in draft["raw_content"], "BANNED: Em-dash found in Day 02 draft content!"
    assert "\u2014" not in draft["title"], "BANNED: Em-dash found in Day 02 draft title!"

    # Verify post in posts table
    post_id = f"post-day02-{draft['id']}"
    c.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
    post = c.fetchone()
    assert post is not None, "Day 02 post missing from posts table!"
    assert "\u2014" not in post["content"], "BANNED: Em-dash found in Day 02 post content!"

    conn.close()
