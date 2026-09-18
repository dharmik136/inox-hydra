"""
LinkedIn Studio Backend - Rate Limiter & Concurrency Proxy.
===========================================================
Exports GaussianRateLimiter, SingleWriterActor, and globals from studio.core.
Prefers a normal package import; falls back to explicit file loading only in
legacy top-level import mode, where the module name collides.

Strict Invariants:
- Zero em-dashes across all code and docstrings.
- 100% loopback and local operation.
"""

import os
import importlib.util

try:
    # Package mode. This is the path taken by the installed application and by
    # anything importing studio.backend.*, so production never touches the
    # file-path loader below.
    from ..core.rate_limiter import (
        GaussianRateLimiter,
        SingleWriterActor,
        generate_gaussian_interval,
        rate_limiter,
        write_actor,
    )
except ImportError:
    # Legacy top-level mode, used by the existing test suites which place both
    # studio/backend and studio/core on sys.path. Both directories contain a
    # module literally named rate_limiter, so a plain import would resolve to
    # whichever directory happens to come first. Load by explicit file path to
    # make the resolution deterministic instead of order dependent.
    _core_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "core", "rate_limiter.py"))
    _spec = importlib.util.spec_from_file_location("studio_core_rate_limiter", _core_file)
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)

    GaussianRateLimiter = _mod.GaussianRateLimiter
    SingleWriterActor = _mod.SingleWriterActor
    generate_gaussian_interval = _mod.generate_gaussian_interval
    rate_limiter = _mod.rate_limiter
    write_actor = _mod.write_actor

__all__ = [
    "GaussianRateLimiter",
    "SingleWriterActor",
    "generate_gaussian_interval",
    "rate_limiter",
    "write_actor",
]
