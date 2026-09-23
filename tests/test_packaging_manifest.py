"""
P2 Verification Suite: The Build Manifest Ships What The App Needs.
==================================================================
Fast guards on pyproject.toml. These do not build anything, so they run in
milliseconds on every commit. The full build-install-boot verification lives in
tools/verify_package.py and belongs on the release job.

Every assertion here corresponds to a defect that was actually observed:
  - auto-discovery swept studio.tests into the distributable
  - no package-data declaration, so the wheel shipped no frontend and no docs
  - apscheduler and python-multipart were imported but never declared, so a
    clean install failed at import and at the first upload respectively

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import os
import shutil
import sys
import tempfile

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 and older
    tomllib = None

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PYPROJECT = os.path.join(REPO_ROOT, "pyproject.toml")

sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
import prepare_package

pytestmark = pytest.mark.skipif(tomllib is None, reason="tomllib requires Python 3.11 or newer")


@pytest.fixture
def staging_dir():
    """
    A throwaway destination for prepare_package.stage_docs.

    tempfile rather than pytest's tmp_path, matching the rest of this suite.
    """
    path = tempfile.mkdtemp(prefix="inox_staging_")
    try:
        yield os.path.join(path, "staged")
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="module")
def manifest():
    with open(PYPROJECT, "rb") as f:
        return tomllib.load(f)


def test_pyproject_exists_and_parses(manifest):
    assert manifest["project"]["name"] == "inox-hydra"


def test_version_is_single_sourced(manifest):
    """The packaging version must come from studio/__version__.py, not a literal."""
    assert "version" in manifest["project"].get("dynamic", []), (
        "version is hardcoded in pyproject.toml, so it can drift from the application"
    )
    attr = manifest["tool"]["setuptools"]["dynamic"]["version"]["attr"]
    assert attr == "studio.__version__.__version__"

    sys.path.insert(0, REPO_ROOT)
    from studio.__version__ import __version__
    assert __version__.count(".") == 2, f"not semantic versioning: {__version__}"


def test_test_code_is_not_shipped_to_users(manifest):
    """studio.tests must never appear in a user artifact."""
    packages = manifest["tool"]["setuptools"]["packages"]
    assert "studio.tests" not in packages
    assert not any(p.endswith(".tests") or ".tests." in p for p in packages), packages


def test_every_runtime_package_is_declared(manifest):
    """Each importable subpackage the app needs must be listed explicitly."""
    packages = set(manifest["tool"]["setuptools"]["packages"])
    for required in (
        "studio",
        "studio.backend",
        "studio.backend.agno_agentos",
        "studio.backend.agno_agentos.agents",
        "studio.core",
    ):
        assert required in packages, f"{required} would be missing from the wheel"


def test_non_python_content_is_declared(manifest):
    """
    The frontend, extension and docs are data files. setuptools ships none of
    them unless told to, which is what produced a wheel that could not serve a
    single page.
    """
    patterns = manifest["tool"]["setuptools"]["package-data"]["studio"]
    joined = " ".join(patterns)
    for needed in ("frontend/", "extension/", "docs/", "extension/icons/"):
        assert needed in joined, f"package-data does not ship {needed}"
    assert "frontend/*.html" in patterns
    assert "docs/modules/*.md" in patterns


@pytest.mark.parametrize("package", [
    "fastapi",
    "uvicorn",
    "pydantic",
    "pillow",
    "pymupdf",
    "apscheduler",
    "python-multipart",
    "requests",
    "httpx",
])
def test_runtime_dependency_declared(manifest, package):
    """
    Guards the class of failure where a dependency is present in the developer
    environment as somebody else's transitive dependency, so the code works
    locally and breaks on a clean install.
    """
    declared = " ".join(manifest["project"]["dependencies"]).lower()
    assert package.lower() in declared, f"{package} is used at runtime but not declared"


def test_staged_docs_match_what_the_app_serves(staging_dir):
    """
    tools/prepare_package.py must stage every document the Docs tab lists.

    This ran the staging tool's output rather than the tool, by looking for
    studio/docs on disk and skipping when it was absent. studio/docs is
    gitignored as a build artifact, so it existed only on a machine where
    somebody had run the tool by hand, and the test skipped on every CI run
    from the day it was written. The check on what ships to a user was the one
    not being made.

    It now stages into a temporary directory and asserts on the result, so it
    runs everywhere and exercises the tool instead of its leftovers.
    """
    result = prepare_package.stage_docs(staging_dir)
    staged = result["destination"]

    assert result["missing"] == [], (
        f"prepare_package lists {result['missing']} as documents the app "
        f"serves, and they are not in docs/. The build prints a warning and "
        f"succeeds, so these would simply be absent from the shipped Docs tab."
    )

    modules_dir = os.path.join(staged, "modules")
    assert os.path.isdir(modules_dir), "staged docs are missing the modules directory"
    module_files = [f for f in os.listdir(modules_dir) if f.endswith(".md")]
    assert len(module_files) >= 6, f"expected the 6 module docs, found {module_files}"
    assert os.path.exists(os.path.join(staged, "ENTERPRISE_USAGE.md"))


def test_every_document_the_app_serves_is_staged(staging_dir):
    """
    The list in prepare_package and the files on disk have to agree in both
    directions. The assertion above catches a listed file that is missing;
    this one catches a served file that was never listed, which ships a build
    whose Docs tab is missing a page nobody noticed writing.
    """
    result = prepare_package.stage_docs(staging_dir)

    for name in prepare_package.TOP_LEVEL_DOCS:
        assert os.path.exists(os.path.join(result["destination"], name)), (
            f"{name} is listed as served and did not reach the staged tree"
        )

    source_modules = os.path.join(REPO_ROOT, "docs", "modules")
    expected = sorted(f for f in os.listdir(source_modules) if f.endswith(".md"))
    assert result["modules"] == expected, (
        f"staged modules {result['modules']} do not match docs/modules "
        f"{expected}"
    )


def test_staging_twice_leaves_the_same_tree(staging_dir):
    """
    The script says it is idempotent, and the release job may run it after a
    partial earlier run. It removes the destination first, so a document
    dropped from the list must not survive in a stale tree.
    """
    destination = staging_dir

    first = prepare_package.stage_docs(destination)
    stale = os.path.join(destination, "LEFTOVER.md")
    with open(stale, "w", encoding="utf-8") as handle:
        handle.write("from an older build")

    second = prepare_package.stage_docs(destination)

    assert not os.path.exists(stale), (
        "a file from a previous staging survived, so a document removed from "
        "the served list would still ship"
    )
    assert first["copied"] == second["copied"]
