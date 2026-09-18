"""
P1 Verification Suite: The Application Is A Real Python Package.
================================================================
Guards the precondition for shipping anything other than a source checkout:
every backend module must import as `studio.backend.<name>` from any working
directory, with no dependence on the process happening to start inside
studio/backend.

This suite exists because the failure it catches is silent. `app.py` wraps its
imports in try/except ImportError, so a module that only works in top-level
mode does not raise. It falls through to the fallback branch and the real cause
is masked. `gstack_governance.py` shipped in exactly that state.

Each check runs in a subprocess with a deliberately unrelated working directory,
because importing in-process would be satisfied by the test runner's own sys.path.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import os
import subprocess
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

BACKEND_MODULES = [
    "paths",
    "database",
    "formatters",
    "repurposer",
    "leads",
    "linkedin_client",
    "scheduler",
    "agno_agent",
    "agno_agentos",
    "image_studio",
    "event_bus",
    "ingress",
    "crm",
    "rate_limiter",
    "intelligence_sync",
    "gstack_governance",
    "carousel_generator",
    "quote_renderer",
    "vault",
]


def _import_in_clean_subprocess(statement: str):
    """
    Runs `statement` from an unrelated cwd with only the repo root on sys.path.

    Returns the CompletedProcess so callers can assert on both status and output.
    """
    code = (
        "import sys\n"
        f"sys.path.insert(0, {REPO_ROOT!r})\n"
        f"{statement}\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=tempfile.gettempdir(),
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_package_markers_exist():
    """Without these files the tree is not importable as a package at all."""
    for rel in ("studio/__init__.py", "studio/backend/__init__.py", "studio/core/__init__.py"):
        assert os.path.exists(os.path.join(REPO_ROOT, rel)), f"missing package marker: {rel}"


def test_fastapi_app_imports_from_any_cwd():
    """The P1 gate: the ASGI application is importable by its package path."""
    result = _import_in_clean_subprocess(
        "import studio.backend.app as m\n"
        "assert m.app.routes, 'no routes registered'\n"
        "print('ROUTES', len(m.app.routes))"
    )
    assert result.returncode == 0, (
        f"studio.backend.app failed to import from a neutral cwd:\n{result.stderr}"
    )
    assert "ROUTES" in result.stdout


@pytest.mark.parametrize("module", BACKEND_MODULES)
def test_every_backend_module_imports_in_package_mode(module):
    """
    No backend module may depend on top-level import mode.

    A failure here means that module imports a sibling without a package-relative
    path, which works only when cwd is studio/backend.
    """
    result = _import_in_clean_subprocess(f"import studio.backend.{module}")
    assert result.returncode == 0, (
        f"studio.backend.{module} is not importable in package mode:\n{result.stderr}"
    )


def test_state_does_not_resolve_inside_the_package_when_installed():
    """
    Cross-check between P0 and P1.

    Once installed there is no studio/data directory, so state must resolve to
    the user profile. This asserts the two phases agree with each other.
    """
    result = _import_in_clean_subprocess(
        "import os, tempfile\n"
        "import studio.backend.paths as p\n"
        "p._LEGACY_DATA_DIR = os.path.join(tempfile.gettempdir(), 'inox-absent-marker')\n"
        "os.environ.pop('INOX_HYDRA_HOME', None)\n"
        "home = p.get_app_home()\n"
        "assert not home.startswith(p._STUDIO_DIR), 'state resolved inside the install dir: ' + home\n"
        "print('HOME_OK')"
    )
    assert result.returncode == 0, result.stderr
    assert "HOME_OK" in result.stdout
