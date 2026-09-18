"""
Day 02 Test Suite (Core Mirror): Anti-Detection Rate Limiter & Concurrency Actor.
================================================================================
Mirror of tests/test_rate_limiter.py inside studio/tests package for standalone runs.
Strict Invariants:
- Zero em-dashes across all code and comments.
"""

from datetime import datetime
import math
import os
import sys
import threading
import pytest

# Add backend and core
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "core")))

from rate_limiter import (
    GaussianRateLimiter,
    SingleWriterActor,
    generate_gaussian_interval,
)


def test_core_gaussian_distribution():
    """Validates Gaussian distribution and clamping inside studio.core."""
    mu = 900.0
    sigma = 120.0
    clamp_sigmas = 2.0
    min_bound = mu - (clamp_sigmas * sigma)
    max_bound = mu + (clamp_sigmas * sigma)

    samples = [generate_gaussian_interval(mu, sigma, clamp_sigmas) for _ in range(500)]
    for s in samples:
        assert min_bound <= s <= max_bound

    mean = sum(samples) / len(samples)
    assert abs(mean - mu) < 20.0


def test_core_single_writer_actor():
    """Validates SingleWriterActor execution."""
    actor = SingleWriterActor(maxsize=50)
    future = actor.submit(lambda x, y: x * y, 6, 7)
    res = future.result(timeout=2.0)
    assert res == 42
    actor.stop()
