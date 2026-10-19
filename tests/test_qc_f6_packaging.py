"""
What Ships, and What a Shipped Copy Is Told.
============================================

Every built copy is what a paying creator runs. These hold the build to
shipping the help, and installed copies to being told only about releases
that exist.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from studio.backend import updates  # noqa: E402


# ---------------------------------------------------------------------------
# PLATFORM-18: the update manifest comes from the latest release, not main
# ---------------------------------------------------------------------------

def test_the_update_check_reads_the_latest_release_not_a_branch():
    url = updates.RELEASE_MANIFEST_URL
    assert url.startswith("https://github.com/dharmik136/inox-hydra/releases/latest/download/"), url
    assert url.endswith("/latest.json")
    assert "raw.githubusercontent.com" not in url and "/main/" not in url
    if not os.environ.get("INOX_UPDATE_MANIFEST_URL"):
        assert updates.DEFAULT_MANIFEST_URL == url


def test_every_release_carries_the_manifest_the_check_reads():
    with open(os.path.join(REPO_ROOT, ".github", "workflows", "release.yml"), encoding="utf-8") as handle:
        workflow = handle.read()
    attach = workflow[workflow.index("Attach To GitHub Release"):]
    files = attach[attach.index("files:"):attach.index("generate_release_notes")]
    assert "release/latest.json" in files, "the release does not attach latest.json"
    assert re.search(r"dist/portable/\*\.zip", files)
