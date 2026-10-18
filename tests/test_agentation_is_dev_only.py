"""
The interface review toolbar never reaches a user.
===================================================

Agentation is a dev dependency: a toolbar that lets a person click an element
in the running studio, write what is wrong, and send the note with its
selector to the agent through agentation-mcp on localhost:4747.

That is the right tool for interface work and the wrong thing to ship. A user
build carrying it would show a stranger a review toolbar and open connections
to a port nothing on their machine listens on. These hold the line at each
place it could slip:

  - package.json      a dev dependency, pinned, never a runtime one
  - main.tsx          imported only behind constants Vite folds at build time
  - the built bundle  carries no trace of it, when a build is present
"""

import glob
import json
import os
import re

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI = os.path.join(REPO_ROOT, "studio", "ui")
BUILT = os.path.join(REPO_ROOT, "studio", "frontend_next")


def test_it_is_a_pinned_dev_dependency():
    with open(os.path.join(UI, "package.json"), encoding="utf-8") as handle:
        package = json.load(handle)
    assert "agentation" not in package.get("dependencies", {}), "the review toolbar became a runtime dependency"
    version = package.get("devDependencies", {}).get("agentation")
    assert version and re.fullmatch(r"\d+\.\d+\.\d+", version), "agentation should be pinned to an exact version"


def test_it_is_imported_only_behind_build_time_constants():
    with open(os.path.join(UI, "src", "main.tsx"), encoding="utf-8") as handle:
        main = handle.read()
    assert not re.search(r"^import[^\n]*agentation", main, re.M | re.I), (
        "a static import puts the toolbar in every bundle"
    )
    guard = re.search(
        r'if \(import\.meta\.env\.DEV \|\| import\.meta\.env\.VITE_AGENTATION === "1"\) \{\s*'
        r'void import\("\./dev/agentation"\)',
        main,
    )
    assert guard, "the toolbar is loaded without the dev-only guard"

    for path in glob.glob(os.path.join(UI, "src", "**", "*.ts*"), recursive=True):
        if os.path.normpath(path).endswith(os.path.join("dev", "agentation.tsx")):
            continue
        with open(path, encoding="utf-8") as handle:
            assert "from \"agentation\"" not in handle.read(), f"{path} imports agentation directly"


def test_the_built_bundle_has_no_trace_of_it():
    scripts = glob.glob(os.path.join(BUILT, "static", "*.js"))
    if not scripts:
        pytest.skip("studio/frontend_next is not built in this checkout")
    for path in scripts + [os.path.join(BUILT, "index.html")]:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        assert "agentation" not in text.lower() and ":4747" not in text, (
            f"{os.path.basename(path)} carries the review toolbar. "
            "Rebuild without VITE_AGENTATION before this build goes anywhere."
        )
