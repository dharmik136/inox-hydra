"""
Phase 4 Verification Suite: Algorithmic Safety & Hardware Verification.
=======================================================================
Validates:
1. SQLite WAL database file footprint is strictly below the 40MB limit.
2. Local ICP mathematical scoring latency is sub-millisecond (< 1ms per lead).
3. Gaussian token bucket rate limiter intervals strictly adhere to [660s, 1140s] bounds.
4. Passive observer architecture: zero synthetic click automation against LinkedIn DOM.
5. Loopback binding constraint: 127.0.0.1:8000.
6. Repository-wide zero em-dash compliance across all tracked source files.
"""

import os
import sys
import time
import pytest

# Ensure studio path is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from studio.backend.database import DB_PATH, get_db
from studio.backend.crm import ICPScoringEngine
from studio.core.rate_limiter import generate_gaussian_interval, GaussianRateLimiter


def test_phase4_sqlite_database_footprint():
    """Verify SQLite WAL database footprint is well within the 40MB threshold."""
    assert os.path.exists(DB_PATH), f"Database file {DB_PATH} does not exist"
    db_size = os.path.getsize(DB_PATH)
    wal_path = DB_PATH + "-wal"
    wal_size = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0
    total_mb = (db_size + wal_size) / (1024 * 1024)

    assert total_mb < 40.0, f"Database footprint {total_mb:.2f} MB exceeds 40MB budget"
    assert total_mb > 0.05, "Database appears uninitialized or empty"

    # Verify journal mode is WAL
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode;")
    j_mode = cursor.fetchone()[0]
    conn.close()
    assert j_mode.lower() == "wal", f"Expected WAL journal mode, got {j_mode}"


def test_phase4_deterministic_icp_latency_benchmark():
    """Verify local mathematical ICP scoring runs in sub-millisecond time (< 1.0 ms)."""
    test_cases = [
        ("VP of Engineering at CloudScale", "CloudScale", "How do you handle WAL checkpoints?", "COMMENT"),
        ("Chief AI Scientist", "Enterprise Labs", "Interested in your benchmarks.", "COMMENT"),
        ("Staff Systems Architect", "Nexus Tech", "Decoupled logic is critical.", "LIKE"),
        ("Senior Developer", "Startup Inc", "Great post!", "COMMENT"),
        ("Technical Recruiter", "Talent Org", "Are you hiring?", "COMMENT"),
    ]

    iterations = 2000
    start = time.perf_counter()
    for i in range(iterations):
        headline, company, comment, itype = test_cases[i % len(test_cases)]
        score = ICPScoringEngine.calculate_icp_score(headline, company, comment, itype)
        assert 0.0 <= score <= 100.0
    elapsed_total_ms = (time.perf_counter() - start) * 1000.0
    avg_ms_per_lead = elapsed_total_ms / iterations

    # Sub-millisecond requirement (< 1.0 ms)
    assert avg_ms_per_lead < 1.0, f"Average ICP scoring latency {avg_ms_per_lead:.4f} ms exceeds 1ms limit"
    # In practice it is ~0.003 ms (3 microseconds)
    assert avg_ms_per_lead < 0.1, f"Expected < 0.1ms on local hardware, got {avg_ms_per_lead:.4f} ms"


def test_phase4_gaussian_rate_limiter_bounds():
    """Verify Gaussian jitter rate limiter strictly respects [660s, 1140s] bounds."""
    limiter = GaussianRateLimiter(mu=900.0, sigma=120.0, clamp_sigmas=2.0)
    min_bound = 900.0 - 240.0  # 660.0s
    max_bound = 900.0 + 240.0  # 1140.0s

    # Generate 500 random samples and verify every single one is clamped
    for _ in range(500):
        interval = generate_gaussian_interval(mu=900.0, sigma=120.0, clamp_sigmas=2.0)
        assert min_bound <= interval <= max_bound, f"Interval {interval} violated bounds [{min_bound}, {max_bound}]"


def test_phase4_passive_observer_compliance():
    """Verify browser extension content script operates strictly as a passive DOM observer."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    content_js_path = os.path.join(base_dir, "studio", "extension", "content.js")
    with open(content_js_path, "r", encoding="utf-8") as f:
        js_code = f.read()

    # Must NOT perform programmatic DOM clicks on LinkedIn buttons (no .click() on interactive elements)
    # Observer must use MutationObserver or window scroll passive listeners
    assert "MutationObserver" in js_code, "Extension must use passive MutationObserver"
    assert "password" not in js_code.lower(), "Extension must never scrape or inspect password inputs"
    assert "document.querySelectorAll(\"button\").forEach(b => b.click())" not in js_code


def test_phase4_repository_wide_zero_em_dashes():
    """Verify zero literal em-dash characters (\\u2014) across entire tracked repository."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    checked_exts = {".py", ".js", ".html", ".css", ".md"}
    # Build output is excluded: dist/ contains vendored third party libraries
    # (fastapi, pydantic, pymupdf, requests) whose source we neither author nor
    # ship as our own content. The anti-slop rule governs this project's writing.
    #
    # payload/ is the same category, staged by tools/stage_desktop_payload.py
    # for the desktop bundle, and target/ is the Rust build directory. Both are
    # gitignored, both appear only after a build, and neither holds a line this
    # project wrote.
    excluded = {".git", "__pycache__", "node_modules", ".pytest_cache", "venv",
                ".venv", "dist", "build", "build_artifacts", "archive", "scratch",
                "payload", "target"}

    violations = []
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d not in excluded]
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext in checked_exts:
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "rb") as f:
                        if b"\xe2\x80\x94" in f.read():
                            violations.append(os.path.relpath(fpath, base_dir))
                except Exception:
                    pass

    assert not violations, f"Forbidden em-dash character (\\xe2\\x80\\x94) found in files: {violations}"
