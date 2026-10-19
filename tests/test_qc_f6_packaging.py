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
    step = attach[:attach.index("body:")]
    assert re.search(r"fail_on_unmatched_files:\s*true", step), "a release without latest.json would still publish"


# ---------------------------------------------------------------------------
# UX-12: every built copy ships the help, and the build fails without it
# ---------------------------------------------------------------------------

sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))


def _help_paths():
    from studio.backend import docs_engine

    return [path for section in docs_engine.HELP_SECTIONS if docs_engine.section_kind(section["id"]) == "help"
            for path in section["paths"]]


def test_the_staged_docs_hold_every_help_article(tmp_path):
    import prepare_package

    staged = str(tmp_path / "staged")
    result = prepare_package.stage_docs(staged)
    assert result["missing"] == []
    missing = [path for path in _help_paths() if not os.path.isfile(os.path.join(staged, path))]
    assert missing == [], f"a built copy would ship without {len(missing)} help articles: {missing[:5]}"

    from studio.backend import docs_engine

    for section in docs_engine.help_sections(staged):
        if section["kind"] == "help":
            expected = len(next(s for s in docs_engine.HELP_SECTIONS if s["id"] == section["id"])["paths"])
            assert section["count"] == expected, f"{section['title']} shows {section['count']} of {expected}"
    assert not os.path.exists(os.path.join(staged, "prudent_handoff")), "internal docs were staged"


def test_a_missing_help_article_fails_the_build(tmp_path, monkeypatch):
    import prepare_package

    real = prepare_package.stage_docs
    staged = str(tmp_path / "staged")

    def stage_without_one(destination=None):
        # Always the temporary folder: never the repository's studio/docs.
        result = real(staged)
        os.remove(os.path.join(staged, "help", "back-up-restore-and-export.md"))
        return result

    monkeypatch.setattr(prepare_package, "stage_docs", stage_without_one)
    monkeypatch.setattr(prepare_package.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0})())
    assert prepare_package.main() == 1


def test_the_wheel_declares_the_help_as_package_data():
    import tomllib

    with open(os.path.join(REPO_ROOT, "pyproject.toml"), "rb") as handle:
        data = tomllib.load(handle)["tool"]["setuptools"]["package-data"]["studio"]
    assert "docs/help/*.md" in data


def test_the_release_gate_checks_every_help_section():
    import verify_package

    assert "help sections" in verify_package.GATE_SCRIPT
    assert "HELP_SECTIONS" in verify_package.GATE_SCRIPT


def test_the_portable_build_refuses_a_copy_without_help(tmp_path):
    import pytest
    import build_portable

    studio = tmp_path / "app" / "studio"
    (studio / "docs" / "help").mkdir(parents=True)
    with pytest.raises(SystemExit, match="help"):
        build_portable.assert_help_shipped(str(studio))


def test_docs_beside_an_installed_package_that_are_not_ours_are_ignored(tmp_path, monkeypatch):
    from studio.backend import paths

    stray = tmp_path / "site-packages" / "docs"
    stray.mkdir(parents=True)
    (stray / "index.md").write_text("someone else's docs")
    packaged = tmp_path / "site-packages" / "studio" / "docs"
    (packaged / "help").mkdir(parents=True)
    monkeypatch.setattr(paths, "_REPO_DOCS_DIR", str(stray))
    monkeypatch.setattr(paths, "_PACKAGED_DOCS_DIR", str(packaged))
    assert paths.get_docs_dir() == str(packaged)
    assert paths.describe()["docs_source"] == "packaged"
