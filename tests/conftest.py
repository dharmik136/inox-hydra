"""
Global Test Session Sandbox: Guaranteed State Isolation for Tests.
=================================================================
Prevents any test in this suite from mutating the user's live database or assets.

When tests run, application state is redirected to a temporary INOX_HYDRA_HOME.
At session start, the sandboxed database is initialized and seeded with baseline
test fixtures so tests run against clean, predictable data.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import os
import shutil
import sys
import tempfile
import pytest

# Ensure studio/backend and studio are importable
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_BACKEND_DIR = os.path.join(_REPO_ROOT, "studio", "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Track the sandboxed home created for the pytest session
_SESSION_TEST_HOME = None

# Configure INOX_HYDRA_HOME immediately upon module import (before test files are collected/imported)
# if the environment does not already specify an override.
if "INOX_HYDRA_HOME" not in os.environ:
    _SESSION_TEST_HOME = tempfile.mkdtemp(prefix="inox_pytest_sandbox_")
    os.environ["INOX_HYDRA_HOME"] = _SESSION_TEST_HOME

# Fabricated analytics and demographics are opt-in and OFF by default, so a real
# install never shows a creator numbers it invented. The suite needs predictable
# fixtures to assert against, so the sandbox opts in explicitly. Any test that
# cares about the un-seeded state must clear this and re-seed for itself.
os.environ.setdefault("INOX_DEMO_DATA", "1")


def pytest_configure(config):
    """Initializes and seeds the sandboxed database before test execution."""
    if _SESSION_TEST_HOME and os.environ.get("INOX_HYDRA_HOME") == _SESSION_TEST_HOME:
        try:
            from database import init_db, seed_initial_data
            init_db()
            seed_initial_data()
        except Exception as e:
            sys.stderr.write(f"Notice: Sandbox database bootstrap encountered: {e}\n")


def pytest_unconfigure(config):
    """Cleans up the temporary session test sandbox."""
    global _SESSION_TEST_HOME
    if _SESSION_TEST_HOME and os.path.isdir(_SESSION_TEST_HOME):
        shutil.rmtree(_SESSION_TEST_HOME, ignore_errors=True)
        _SESSION_TEST_HOME = None
