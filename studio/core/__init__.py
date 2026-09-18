"""
LinkedIn Strategy Studio Core Package.
======================================
Houses architectural primitives, mathematical governors, and concurrency actors.
Strict Invariants:
- Zero em-dashes across all code and comments.
- 100% local execution (no cloud egress).
"""

from .rate_limiter import GaussianRateLimiter, SingleWriterActor, generate_gaussian_interval

__all__ = [
    "GaussianRateLimiter",
    "SingleWriterActor",
    "generate_gaussian_interval",
]
