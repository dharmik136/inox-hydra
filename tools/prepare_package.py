"""
Packaging Pre-Step: Stage Bundled Content Inside The Package.
=============================================================
The in-app Docs tab and the offline FTS5 search index read markdown from
`docs/` at the repository root, which is outside the `studio/` package and
therefore cannot be shipped in a wheel.

This script copies the documents the application actually serves into
`studio/docs/` so that setuptools can include them as package data. The
repository copy stays authoritative during development: `paths.get_docs_dir()`
prefers the repo root when it exists and only falls back to the staged copy in
an installed build.

Run before `python -m build`. Idempotent.

Strict Invariants:
- Zero em-dashes.
- Never copies prudent_handoff/ or internal planning docs into a user artifact.
"""

import os
import shutil
import subprocess
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SOURCE_DOCS = os.path.join(REPO_ROOT, "docs")
STAGED_DOCS = os.path.join(REPO_ROOT, "studio", "docs")

# Documents the running application serves. Anything not listed here is
# internal and must not ship to a user.
TOP_LEVEL_DOCS = [
    "ARCHITECTURE.md",
    "AI_ENGINE.md",
    "API_REFERENCE.md",
    "BYO_AI_ARCHITECTURE.md",
    "ENTERPRISE_USAGE.md",
    "EXTENSION_AND_SYNC.md",
    "GETTING_STARTED.md",
]
MODULE_DOCS_DIR = "modules"
HELP_DOCS_DIR = "help"


def served_help_paths() -> list:
    """
    Every document the Docs screen files under a help section.

    Read from docs_engine.HELP_SECTIONS, the table the screen itself is built
    from, so the build cannot drift from what the screen lists. The help
    articles were never staged, so every built copy showed each help section
    with 0 documents.
    """
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    from studio.backend import docs_engine

    return [path for section in docs_engine.HELP_SECTIONS
            if docs_engine.section_kind(section["id"]) == "help"
            for path in section["paths"]]


def missing_help(destination: str) -> list:
    """The help documents absent from a staged tree. Empty means it is complete."""
    return [path for path in served_help_paths()
            if not os.path.isfile(os.path.join(destination, *path.split("/")))]


def stage_docs(destination: str = STAGED_DOCS) -> dict:
    """
    Copies the served documents into `destination`, replacing what is there.

    Takes a destination so the test suite can stage into a temporary directory
    and check the result. It used to work only against studio/docs, which is
    gitignored as a build artifact, so the test guarding this could only run on
    a machine where somebody had already run the tool by hand. On CI it skipped
    every time, which meant the check on what ships to a user was the check not
    being made.

    Returns what was copied and what was listed but absent.
    """
    if not os.path.isdir(SOURCE_DOCS):
        raise FileNotFoundError(f"source docs directory not found: {SOURCE_DOCS}")

    if os.path.isdir(destination):
        shutil.rmtree(destination)
    os.makedirs(os.path.join(destination, MODULE_DOCS_DIR), exist_ok=True)

    top_level = []
    modules = []
    missing = []

    for name in TOP_LEVEL_DOCS:
        src = os.path.join(SOURCE_DOCS, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(destination, name))
            top_level.append(name)
        else:
            missing.append(name)

    src_modules = os.path.join(SOURCE_DOCS, MODULE_DOCS_DIR)
    if os.path.isdir(src_modules):
        for name in sorted(os.listdir(src_modules)):
            if name.endswith(".md"):
                shutil.copy2(os.path.join(src_modules, name),
                             os.path.join(destination, MODULE_DOCS_DIR, name))
                modules.append(name)

    # The help articles, written for the person using the studio, and any
    # other document a help section lists (strategy_playbook.md).
    help_docs = []
    src_help = os.path.join(SOURCE_DOCS, HELP_DOCS_DIR)
    if os.path.isdir(src_help):
        os.makedirs(os.path.join(destination, HELP_DOCS_DIR), exist_ok=True)
        for name in sorted(os.listdir(src_help)):
            if name.endswith(".md"):
                shutil.copy2(os.path.join(src_help, name), os.path.join(destination, HELP_DOCS_DIR, name))
                help_docs.append(f"{HELP_DOCS_DIR}/{name}")
    for path in served_help_paths():
        if path in help_docs:
            continue
        src = os.path.join(SOURCE_DOCS, *path.split("/"))
        if os.path.isfile(src):
            os.makedirs(os.path.dirname(os.path.join(destination, *path.split("/"))), exist_ok=True)
            shutil.copy2(src, os.path.join(destination, *path.split("/")))
            help_docs.append(path)
        else:
            missing.append(path)

    return {
        "destination": destination,
        "top_level": top_level,
        "modules": modules,
        "help": help_docs,
        "missing": missing,
        "copied": len(top_level) + len(modules) + len(help_docs),
    }


def main() -> int:
    try:
        result = stage_docs()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"staged {result['copied']} documents into studio/docs/")

    # A listed document that is absent stops the build.
    #
    # This printed WARNING and returned 0, so an incomplete Docs tab went
    # straight into the artifact. There is no quiet version of that failure:
    #
    #   ENTERPRISE_USAGE.md appears in app.py's DOCS_MODULES, which is a
    #   hardcoded list rather than a directory scan, so the tab renders the
    #   entry either way and the click answers 404 "Documentation file for
    #   'enterprise-usage' not found on disk."
    #
    #   The other six are indexed for offline search by docs_engine, which
    #   walks the staged tree, so a missing one simply stops being findable
    #   and nothing anywhere says so.
    #
    # Every caller already treats a non-zero return as fatal: build_portable,
    # stage_desktop_payload and verify_package each raise SystemExit on it.
    # The wiring was there and only the signal was missing.
    if result["missing"]:
        print(f"ERROR: listed as served but not found in docs/: "
              f"{', '.join(result['missing'])}")
        print("Either restore the files or remove them from TOP_LEVEL_DOCS. "
              "Shipping without them leaves the Docs tab pointing at nothing.")
        return 1

    # Checked on the staged tree itself, not on the list above: what ships is
    # what is on disk there.
    absent = missing_help(result["destination"])
    if absent:
        print(f"ERROR: {len(absent)} help document(s) did not reach the staged docs: {', '.join(absent[:5])}")
        print("A copy built from this would show those help sections empty.")
        return 1

    # Propagate the single version source before anything is packaged, so a
    # built artifact can never contain a drifted extension manifest.
    sync = os.path.join(REPO_ROOT, "tools", "sync_version.py")
    completed = subprocess.run([sys.executable, sync], cwd=REPO_ROOT)
    if completed.returncode != 0:
        print("ERROR: version propagation failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
