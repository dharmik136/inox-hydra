"""
A packaged copy's help holds the help, not the project's internal documents. [D-5]

prepare_package staged seven top level documents and every module manual
beside the help articles, so every ZIP, installer and wheel listed
"For maintainers" and "Retired manuals and history" in its Docs screen, and
search answered "restore my data" with the bug register. Packaged builds now
carry docs/help (every article, including the two filed for maintainers)
plus the other documents a help section lists, and a section with nothing
left to show is not listed.

A source checkout is unchanged here: it keeps every document, and hiding the
internal ones from its search is batch R5's.

Strict Invariants:
- Zero em-dashes.
"""

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

import prepare_package  # noqa: E402
from studio.backend import docs_engine  # noqa: E402


def _staged_files(root):
    found = []
    for folder, _, files in os.walk(root):
        for name in files:
            found.append(os.path.relpath(os.path.join(folder, name), root).replace(os.sep, "/"))
    return sorted(found)


def test_only_the_help_is_staged(tmp_path):
    staged = str(tmp_path / "docs")
    result = prepare_package.stage_docs(staged)
    assert result["missing"] == []

    files = _staged_files(staged)
    every_article = sorted("help/" + name for name in os.listdir(os.path.join(REPO_ROOT, "docs", "help"))
                           if name.endswith(".md"))
    internal = [path for path in files if not path.startswith("help/") and path != "strategy_playbook.md"]
    assert internal == [], f"a packaged copy would ship internal documents: {internal}"
    assert [path for path in files if path.startswith("help/")] == every_article
    assert "strategy_playbook.md" in files, "a document a help section lists was left out"


def test_the_packaged_docs_screen_lists_no_empty_or_retired_section(tmp_path):
    staged = str(tmp_path / "docs")
    prepare_package.stage_docs(staged)
    sections = docs_engine.help_sections(staged)
    kinds = {section["id"]: section["kind"] for section in sections}
    assert "retired" not in kinds, "a packaged copy lists the retired manuals"
    assert all(section["count"] > 0 for section in sections), [
        (s["id"], s["count"]) for s in sections if s["count"] == 0]
    maintainers = next(s for s in sections if s["id"] == "maintainers")
    assert all(entry["path"].startswith("help/") for entry in maintainers["documents"])


def test_every_help_section_is_still_complete_when_packaged(tmp_path):
    staged = str(tmp_path / "docs")
    prepare_package.stage_docs(staged)
    expected = {s["id"]: len(s["paths"]) for s in docs_engine.HELP_SECTIONS
                if docs_engine.section_kind(s["id"]) == "help"}
    shown = {s["id"]: s["count"] for s in docs_engine.help_sections(staged) if s["kind"] == "help"}
    assert shown == expected


def test_a_source_checkout_still_lists_every_section():
    ids = [section["id"] for section in docs_engine.help_sections()]
    assert ids[:len(docs_engine.HELP_SECTIONS)] == [s["id"] for s in docs_engine.HELP_SECTIONS]


def test_the_release_gates_refuse_internal_documents():
    sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
    import smoke_portable
    import verify_package

    assert "ships no maintainer or retired documents" in verify_package.GATE_SCRIPT
    assert "ships no maintainer or retired documents" in smoke_portable.SMOKE
