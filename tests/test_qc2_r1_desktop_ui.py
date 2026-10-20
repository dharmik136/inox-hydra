"""
Desktop installers carry the studio interface. [INS-02]

desktop.yml had no Node setup and no `npm ci && npm run build`, and
studio/frontend_next is gitignored, so every installer it built opened, after
the splash, on the 503 JSON message "The studio interface has not been
built". Its payload check did not look for the interface either.

Two guards now: the workflow builds the interface before staging, and the one
function both channels copy the application through refuses a tree without
it, so neither the ZIP nor an installer can be produced without the UI.

Strict Invariants:
- Zero em-dashes.
"""

import os
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

import build_portable  # noqa: E402


def _workflow():
    with open(os.path.join(REPO_ROOT, ".github", "workflows", "desktop.yml"), encoding="utf-8") as handle:
        return handle.read()


def test_the_desktop_workflow_builds_the_interface_before_staging():
    workflow = _workflow()
    assert "actions/setup-node@v4" in workflow
    build = workflow.index("Build The Studio Interface")
    stage = workflow.index("python tools/stage_desktop_payload.py")
    assert build < stage, "the payload is staged before the interface is built"
    block = workflow[build:stage]
    assert "npm ci" in block and "npm run build" in block


def test_the_payload_check_looks_for_the_interface():
    workflow = _workflow()
    check = workflow[workflow.index("Verify The Payload Layout"):]
    check = check[:check.index("- name:", 10)]
    assert "desktop/payload/app/studio/frontend_next/index.html" in check


def test_the_builder_refuses_an_application_without_its_interface(tmp_path):
    studio = tmp_path / "studio"
    studio.mkdir()
    with pytest.raises(SystemExit, match="interface"):
        build_portable.assert_interface_built(str(studio))

    (studio / "frontend_next").mkdir()
    (studio / "frontend_next" / "index.html").write_text("<html></html>", encoding="utf-8")
    build_portable.assert_interface_built(str(studio))


def test_copy_application_runs_the_interface_check():
    import inspect

    source = inspect.getsource(build_portable.copy_application)
    assert "assert_interface_built(" in source
