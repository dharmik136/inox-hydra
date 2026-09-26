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


# ---------------------------------------------------------------------------
# Authenticated test client
#
# The API requires a loopback Host, a permitted Origin and a valid token on
# every call. The suite has to satisfy all three the same way a real caller
# does, because the alternative is a bypass inside the application that exists
# only for tests, and a bypass that ships is a bypass an attacker can use.
#
# So instead of weakening the server, every TestClient is built pointing at the
# real loopback origin and carrying the real token. A test that wants to prove
# the boundary holds simply overrides these per request.
# ---------------------------------------------------------------------------
def _install_authenticated_test_client():
    from fastapi.testclient import TestClient
    from security import get_or_create_token, TOKEN_HEADER

    original_init = TestClient.__init__

    def patched_init(self, *args, **kwargs):
        # Host must name loopback or the rebinding check refuses the request.
        kwargs.setdefault("base_url", "http://127.0.0.1:8000")
        headers = dict(kwargs.get("headers") or {})
        headers.setdefault(TOKEN_HEADER, get_or_create_token())
        kwargs["headers"] = headers
        original_init(self, *args, **kwargs)

    if not getattr(TestClient, "_inox_auth_patched", False):
        TestClient.__init__ = patched_init
        TestClient._inox_auth_patched = True


_install_authenticated_test_client()


def pytest_unconfigure(config):
    """Cleans up the temporary session test sandbox."""
    global _SESSION_TEST_HOME
    if _SESSION_TEST_HOME and os.path.isdir(_SESSION_TEST_HOME):
        shutil.rmtree(_SESSION_TEST_HOME, ignore_errors=True)
        _SESSION_TEST_HOME = None


# ---------------------------------------------------------------------------
# What counts as this repository's own content
#
# Several hygiene scans walk the working tree. That is right for studio/ and
# wrong everywhere else, and the asymmetry is load bearing in both directions.
#
# copy_application copies studio/ from the working tree rather than from the
# index, so an untracked file there does reach a user and has to be scanned.
# That is the lesson a ten file credential leak taught this project once
# already.
#
# Nothing outside studio/ ships. The portable build copies only studio/, and
# the wheel declares only studio packages. So an unrelated scratch script left
# in tools/ was failing a check named for shipped files, while CI, which
# clones, stayed green. A suite that is red for a reason that cannot affect a
# user trains people to read red as normal, which costs more than the noise it
# saves.
#
# Shared here rather than copied into each test file, because two copies of a
# rule about what to inspect is how one of them quietly stops matching.
# ---------------------------------------------------------------------------
def _git_tracked_paths(repo_root):
    """Every path git knows about, or None when git cannot answer."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "ls-files"], cwd=repo_root,
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return None
        return {
            line.replace("/", os.sep)
            for line in result.stdout.splitlines()
            if line.strip()
        }
    except Exception:
        return None


def is_repository_content(rel_path, repo_root, _cache={}):
    """
    True for anything that ships, or that git is tracking.

    Everything under studio/ counts whether tracked or not, because the build
    copies that directory from disk. Elsewhere, tracked is the test. When git
    is unavailable the answer is True, so a checkout without git scans more
    rather than less.
    """
    if repo_root not in _cache:
        _cache[repo_root] = _git_tracked_paths(repo_root)
    tracked = _cache[repo_root]

    normalised = str(rel_path).replace("/", os.sep)
    if normalised.startswith("studio" + os.sep):
        return True
    if tracked is None:
        return True
    return normalised in tracked
