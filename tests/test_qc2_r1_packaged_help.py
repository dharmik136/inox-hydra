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


# A document ships because a help section lists it, which is what
# prepare_package.stage_docs stages from. Naming the exceptions here instead
# (strategy_playbook.md, then PRIVACY_POLICY.md) put half the rule in this
# file and half in tools/verify_package.py, and the two drifted the moment a
# document was added: the test was taught and the verifier was not, so the
# clean-install check failed on a document the help was meant to carry.
def _outside_help():
    return [path for path in prepare_package.served_help_paths()
            if not path.startswith("help/")]


def test_only_the_help_is_staged(tmp_path):
    staged = str(tmp_path / "docs")
    result = prepare_package.stage_docs(staged)
    assert result["missing"] == []

    files = _staged_files(staged)
    every_article = sorted("help/" + name for name in os.listdir(os.path.join(REPO_ROOT, "docs", "help"))
                           if name.endswith(".md"))
    internal = [path for path in files if not path.startswith("help/")
                and path not in _outside_help()]
    assert internal == [], f"a packaged copy would ship internal documents: {internal}"
    assert [path for path in files if path.startswith("help/")] == every_article
    outside = _outside_help()
    assert outside, "no help section lists a document outside docs/help any more"
    for expected in outside:
        assert expected in files, f"a document a help section lists was left out: {expected}"


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

def test_a_packaged_copy_ships_only_documents_a_help_section_lists(tmp_path):
    """
    The rule tools/verify_package.py applies to the built distributable, run
    here against the staged docs so the suite catches it on every platform
    rather than only in the clean-install job at the end of CI.

    That job is where PRIVACY_POLICY.md failed: it kept its own list of
    filenames ("help/ and strategy_playbook.md"), this module kept another,
    and teaching one did not teach the other. Both now ask the same question,
    which is the one that was always meant: is this document filed under a
    help section?
    """
    staged = str(tmp_path / "docs")
    prepare_package.stage_docs(staged)

    library = docs_engine.document_library(staged)
    sections = docs_engine.help_sections(staged)
    filed = {doc["id"] for section in sections for doc in section["documents"]}

    unfiled = sorted(entry["path"] for entry in library if entry["id"] not in filed)
    assert not unfiled, (
        "a packaged copy would ship documents no help section lists, which is "
        f"what the clean-install check refuses: {unfiled}"
    )

    # No assertion that every listed section is of kind "help": a packaged
    # copy does list "For maintainers", carrying the help articles filed
    # under it, which test_the_packaged_docs_screen_lists_no_empty_or_retired_section
    # above already pins. What must not ship is a document no section lists.

    # And the policy in particular, because it is the document that exposed
    # the split rule and the one a store reviewer may open from the help.
    assert "PRIVACY_POLICY.md" in {entry["path"] for entry in library}

