"""
P3 Verification Suite: One Version, No Machine-Specific Paths.
==============================================================
Two classes of defect that only hurt after shipping, and never show up in a
functional test:

  1. Version drift. The application said 2.5.0, the Chrome extension manifest
     said 2.0.0, and GETTING_STARTED.md said v2.5. A user reporting a bug could
     not tell us which version they were running, and neither could we.

  2. Machine-specific absolute paths. README.md, GETTING_STARTED.md and
     ENTERPRISE_USAGE.md shipped 20 links of the form
     `file:///c:/Users/<developer>/Downloads/Linkedin%20strategy/...`, which are
     dead on every machine except one, and leak the developer's username into a
     distributed product. create_desktop_shortcut.vbs hardcoded the same path
     and so produced a broken shortcut for every user.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import json
import os
import re

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Surfaces that reach a user. Internal planning material is excluded: the
# handoff docs legitimately reference the upstream author's machine, and
# scratch/ is gitignored throwaway work.
# "tests" is excluded because test code is not a shipped surface (see
# test_packaging_manifest.py, which asserts it never reaches a user artifact),
# and because this very file has to name the offending pattern in order to
# search for it.
EXCLUDED_DIRS = {".git", "archive", "build_artifacts", "scratch", "node_modules",
                 "__pycache__", ".pytest_cache", ".playwright-mcp", "dist", "build",
                 "tests"}
EXCLUDED_RELPATHS = {
    os.path.join("docs", "prudent_handoff"),
    os.path.join("docs", "PACKAGING_AND_MAINTENANCE_MASTER_PLAN.md"),
    os.path.join("studio", "docs"),  # generated copy of docs/, checked at its source
}
SHIPPED_SUFFIXES = (".md", ".py", ".js", ".html", ".vbs", ".bat", ".json", ".css")

# Any Windows user profile path, not just the current developer's.
ABSOLUTE_USER_PATH = re.compile(r"[a-zA-Z]:[\\/]+Users[\\/]+[A-Za-z0-9_.-]+", re.IGNORECASE)
ENCODED_WORKSPACE = re.compile(r"Linkedin%20strategy", re.IGNORECASE)


def _shipped_files():
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        rel_dir = os.path.relpath(dirpath, REPO_ROOT)
        if any(rel_dir == ex or rel_dir.startswith(ex + os.sep) for ex in EXCLUDED_RELPATHS):
            continue
        for name in filenames:
            if not name.endswith(SHIPPED_SUFFIXES):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), REPO_ROOT)
            if rel in EXCLUDED_RELPATHS:
                continue
            yield rel


def test_no_absolute_user_paths_in_shipped_files():
    """A distributed artifact must not contain anyone's home directory."""
    offenders = []
    for rel in _shipped_files():
        try:
            text = open(os.path.join(REPO_ROOT, rel), encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        for pattern, label in ((ABSOLUTE_USER_PATH, "absolute user path"),
                               (ENCODED_WORKSPACE, "url-encoded workspace path")):
            for match in pattern.finditer(text):
                line = text[:match.start()].count("\n") + 1
                offenders.append(f"{rel}:{line} {label}: {match.group(0)}")
    assert not offenders, "machine-specific paths would ship to users:\n" + "\n".join(offenders)


def test_desktop_shortcut_resolves_its_own_location():
    """The shortcut installer must work from whatever folder the user unzipped into."""
    text = open(os.path.join(REPO_ROOT, "create_desktop_shortcut.vbs"), encoding="utf-8").read()
    assert "WScript.ScriptFullName" in text, "shortcut script does not resolve its own directory"
    assert not ABSOLUTE_USER_PATH.search(text)


def _source_version():
    text = open(os.path.join(REPO_ROOT, "studio", "__version__.py"), encoding="utf-8").read()
    return re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE).group(1)


def test_extension_manifest_matches_the_source_version():
    """
    Guards against the state this suite was written for: the manifest claiming a
    different version than the application. Run tools/sync_version.py to fix.
    """
    manifest_path = os.path.join(REPO_ROOT, "studio", "extension", "manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["version"] == _source_version(), (
        f"manifest.json says {manifest['version']}, studio/__version__.py says {_source_version()}. "
        "Run: python tools/sync_version.py"
    )


def test_extension_version_is_valid_for_chrome():
    """Chrome rejects anything that is not one to four integers, each 0 to 65535."""
    version = _source_version()
    assert re.match(r"^\d{1,5}(\.\d{1,5}){0,3}$", version), f"Chrome would reject {version!r}"
    assert all(int(p) <= 65535 for p in version.split("."))


def test_extension_does_not_hardcode_its_version():
    """The service worker must report the manifest's version, not a literal."""
    text = open(os.path.join(REPO_ROOT, "studio", "extension", "background.js"), encoding="utf-8").read()
    assert "chrome.runtime.getManifest().version" in text
    assert not re.search(r"Studio Bridge v\d+\.\d+", text), "a version literal is still baked in"


@pytest.mark.parametrize("doc", [
    "README.md",
    os.path.join("docs", "GETTING_STARTED.md"),
    os.path.join("docs", "ENTERPRISE_USAGE.md"),
])
def test_relative_markdown_links_resolve(doc):
    """
    The absolute links were rewritten to relative ones. Prove they point at
    files that actually exist, otherwise we traded dead links for dead links.
    """
    path = os.path.join(REPO_ROOT, doc)
    text = open(path, encoding="utf-8").read()
    doc_dir = os.path.dirname(path)

    broken = []
    for match in re.finditer(r"\]\(([^)]+)\)", text):
        target = match.group(1).split("#")[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        resolved = os.path.normpath(os.path.join(doc_dir, target))
        if not os.path.exists(resolved):
            line = text[:match.start()].count("\n") + 1
            broken.append(f"{doc}:{line} -> {target}")
    assert not broken, "markdown links point at files that do not exist:\n" + "\n".join(broken)
