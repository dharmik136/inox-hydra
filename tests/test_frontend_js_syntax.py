"""
Frontend JavaScript Syntax Guard
================================
A syntax error anywhere in app.js stops the browser parsing the whole file,
which takes the entire studio UI down while every Python test stays green.
That happened once: a duplicated catch block shipped in the queue and cadence
work and no suite noticed, because the existing frontend tests only read the
files as text to check for forbidden characters.

This suite parses the shipped JavaScript with Node. It skips, rather than
fails, when Node is not installed, so a Python only environment can still run
the suite.
"""

import os
import shutil
import subprocess

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

JS_FILES = [
    os.path.join("studio", "frontend", "app.js"),
    os.path.join("studio", "extension", "background.js"),
    os.path.join("studio", "extension", "content.js"),
    os.path.join("studio", "extension", "popup.js"),
]


def _find_node():
    """Locates a Node executable, including the default Windows install path."""
    found = shutil.which("node") or shutil.which("node.exe")
    if found:
        return found
    for candidate in (
        r"C:\Program Files\nodejs\node.exe",
        r"C:\Program Files (x86)\nodejs\node.exe",
    ):
        if os.path.exists(candidate):
            return candidate
    return None


NODE = _find_node()


@pytest.mark.parametrize("rel_path", JS_FILES)
def test_shipped_javascript_parses(rel_path):
    """Verifies every shipped JavaScript file parses, so the UI cannot ship dead on arrival."""
    if not NODE:
        pytest.skip("Node is not installed, cannot parse check JavaScript")

    full_path = os.path.join(REPO_ROOT, rel_path)
    if not os.path.exists(full_path):
        pytest.skip(f"{rel_path} is not present in this checkout")

    result = subprocess.run(
        [NODE, "--check", full_path],
        capture_output=True,
        text=True,
        timeout=60
    )
    assert result.returncode == 0, (
        f"{rel_path} does not parse as JavaScript. The browser would abort the "
        f"entire file and the studio UI would not load.\n{result.stderr.strip()}"
    )


def test_load_queue_has_exactly_one_error_handler():
    """Pins the specific regression: loadQueue once shipped with a duplicated, orphaned catch block."""
    with open(os.path.join(REPO_ROOT, "studio", "frontend", "app.js"), "r", encoding="utf-8") as f:
        content = f.read()

    occurrences = content.count('console.error("Failed to load queue:", e);')
    assert occurrences == 1, (
        f"Expected exactly 1 loadQueue error handler, found {occurrences}. "
        f"A duplicated handler means an orphaned catch block and a file that does not parse."
    )
