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


def main() -> int:
    if not os.path.isdir(SOURCE_DOCS):
        print(f"ERROR: source docs directory not found: {SOURCE_DOCS}")
        return 1

    if os.path.isdir(STAGED_DOCS):
        shutil.rmtree(STAGED_DOCS)
    os.makedirs(os.path.join(STAGED_DOCS, MODULE_DOCS_DIR), exist_ok=True)

    copied = 0
    missing = []
    for name in TOP_LEVEL_DOCS:
        src = os.path.join(SOURCE_DOCS, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(STAGED_DOCS, name))
            copied += 1
        else:
            missing.append(name)

    src_modules = os.path.join(SOURCE_DOCS, MODULE_DOCS_DIR)
    if os.path.isdir(src_modules):
        for name in sorted(os.listdir(src_modules)):
            if name.endswith(".md"):
                shutil.copy2(os.path.join(src_modules, name),
                             os.path.join(STAGED_DOCS, MODULE_DOCS_DIR, name))
                copied += 1

    print(f"staged {copied} documents into studio/docs/")
    if missing:
        print(f"WARNING: listed but not found: {', '.join(missing)}")

    # Propagate the single version source before anything is packaged, so a
    # built artifact can never contain a drifted extension manifest.
    sync = os.path.join(REPO_ROOT, "tools", "sync_version.py")
    result = subprocess.run([sys.executable, sync], cwd=REPO_ROOT)
    if result.returncode != 0:
        print("ERROR: version propagation failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
