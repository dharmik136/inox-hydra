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

import fnmatch
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
    """
    Each importable subpackage under studio/ must be listed explicitly.

    Found on disk rather than named here: a hand-kept list let
    studio.backend.routers ship out of the wheel, and the installed app failed
    at its first import while every test passed.
    """
    packages = set(manifest["tool"]["setuptools"]["packages"])
    on_disk = set()
    for root, dirs, files in os.walk(os.path.join(REPO_ROOT, "studio")):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__", "tests")]
        if "__init__.py" in files:
            on_disk.add(os.path.relpath(root, REPO_ROOT).replace(os.sep, "."))
    assert "studio.backend" in on_disk
    missing = sorted(on_disk - packages)
    assert not missing, f"{missing} would be missing from the wheel"


def test_non_python_content_is_declared(manifest):
    """
    The frontend, extension and docs are data files. setuptools ships none of
    them unless told to, which is what produced a wheel that could not serve a
    single page.
    """
    patterns = manifest["tool"]["setuptools"]["package-data"]["studio"]
    joined = " ".join(patterns)
    for needed in ("frontend_next/", "extension/", "docs/", "extension/icons/"):
        assert needed in joined, f"package-data does not ship {needed}"
    assert "frontend_next/*.html" in patterns
    assert "docs/modules/*.md" in patterns


def _unmatched_files(patterns, rel_root):
    """
    Every file under rel_root that no package-data pattern would ship.

    Walks the real directory rather than reasoning about the pattern list,
    because the question that matters is not whether the list mentions a
    directory but whether each file in it is actually covered.
    """
    root = os.path.join(REPO_ROOT, "studio", rel_root)
    missed = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            full = os.path.join(dirpath, filename)
            relative = os.path.relpath(full, os.path.join(REPO_ROOT, "studio")).replace(os.sep, "/")
            if not any(fnmatch.fnmatch(relative, pattern) for pattern in patterns):
                missed.append(relative)
    return sorted(missed)


def test_the_built_react_interface_is_covered_by_a_pattern(manifest):
    """
    studio/frontend_next is the interface. A wheel that omits it serves
    nothing at all now; while the vanilla page still existed it silently fell
    back to that instead, which is what kept the omission invisible for as
    long as it was.

    The declaration has to cover the files that exist, not the file types
    somebody remembered: the vanilla page was declared as *.html, *.css and
    *.js, and its manifest and icons matched none of those.

    Skipped rather than failed when the interface has not been built, because
    a checkout without node is a legitimate state. What this cannot skip past
    is a build that exists and is not declared.
    """
    built = os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")
    if not os.path.exists(built):
        pytest.skip("studio/frontend_next is not built in this checkout")

    patterns = manifest["tool"]["setuptools"]["package-data"]["studio"]
    missed = _unmatched_files(patterns, "frontend_next")
    assert not missed, f"the built interface exists but these files would not ship: {missed}"


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
    tools/prepare_package.py must stage every document a help section lists.

    This ran the staging tool's output rather than the tool, by looking for
    studio/docs on disk and skipping when it was absent. studio/docs is
    gitignored as a build artifact, so it existed only on a machine where
    somebody had run the tool by hand, and the test skipped on every CI run
    from the day it was written. It now stages into a temporary directory and
    asserts on the result, so it runs everywhere and exercises the tool.

    What is staged changed in cycle 2 (D-5): a packaged copy carries the help
    and none of the maintainer, quality or retired documents, so the module
    manuals and ENTERPRISE_USAGE.md must now be absent.
    """
    result = prepare_package.stage_docs(staging_dir)
    staged = result["destination"]

    assert result["missing"] == [], (
        f"a help section lists {result['missing']}, and they are not in docs/"
    )
    assert prepare_package.missing_help(staged) == []
    assert not os.path.exists(os.path.join(staged, "modules")), "the retired module manuals were staged"
    assert not os.path.exists(os.path.join(staged, "ENTERPRISE_USAGE.md"))


def test_every_document_the_app_serves_is_staged(staging_dir):
    """
    Both directions: every article in docs/help reaches the staged tree, and
    nothing that is not help does.
    """
    result = prepare_package.stage_docs(staging_dir)

    source_help = sorted("help/" + f for f in os.listdir(os.path.join(REPO_ROOT, "docs", "help"))
                         if f.endswith(".md"))
    assert [path for path in result["help"] if path.startswith("help/")] == source_help
    others = [path for path in result["help"] if not path.startswith("help/")]
    assert others == [path for path in prepare_package.served_help_paths() if not path.startswith("help/")]


def test_a_missing_document_fails_the_build(monkeypatch, staging_dir):
    """
    It printed WARNING and returned 0, so an incomplete Docs tab went into the
    artifact. Every caller already aborts on a non-zero return; only the
    signal was missing.
    """
    monkeypatch.setattr(
        prepare_package, "stage_docs",
        lambda *a, **k: {"destination": staging_dir, "help": [],
                         "missing": ["help/back-up-restore-and-export.md"], "copied": 3},
    )
    # Version propagation is a separate concern and must not decide this.
    monkeypatch.setattr(
        prepare_package.subprocess, "run",
        lambda *a, **k: type("R", (), {"returncode": 0})(),
    )

    assert prepare_package.main() == 1, (
        "a document the app serves was absent and the build reported success"
    )


def test_a_complete_tree_still_succeeds(monkeypatch, staging_dir):
    """Guard against the new check failing a healthy build."""
    # A real tree, staged into the temporary folder: the build now also checks
    # that every help article is on disk there (UX-12).
    real_stage = prepare_package.stage_docs
    monkeypatch.setattr(prepare_package, "stage_docs", lambda *a, **k: real_stage(staging_dir))
    monkeypatch.setattr(
        prepare_package.subprocess, "run",
        lambda *a, **k: type("R", (), {"returncode": 0})(),
    )

    assert prepare_package.main() == 0


def test_a_document_that_disappears_is_reported_as_missing(monkeypatch, staging_dir):
    """
    The real staging path, not a stubbed return. A path a help section lists
    with no file behind it has to come back in `missing` rather than being
    skipped over silently.
    """
    real = prepare_package.served_help_paths
    monkeypatch.setattr(
        prepare_package, "served_help_paths",
        lambda: real() + ["A_DOCUMENT_THAT_DOES_NOT_EXIST.md"],
    )

    result = prepare_package.stage_docs(staging_dir)

    assert result["missing"] == ["A_DOCUMENT_THAT_DOES_NOT_EXIST.md"]


def test_every_document_the_docs_tab_lists_is_staged(staging_dir):
    """
    A packaged copy's Docs screen is built from the staged tree. Every
    document a listed section names must be on disk there, so no row renders
    and answers 404 on click, and no section is listed empty.
    """
    sys.path.insert(0, REPO_ROOT)
    from studio.backend import docs_engine

    result = prepare_package.stage_docs(staging_dir)
    staged = result["destination"]

    for section in docs_engine.help_sections(staged):
        assert section["count"] > 0, f"{section['title']} is listed with nothing in it"
        for entry in section["documents"]:
            assert os.path.isfile(os.path.join(staged, *entry["path"].split("/"))), entry["path"]


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
