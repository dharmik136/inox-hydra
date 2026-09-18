"""
Version Propagation: One Source, Every Surface.
===============================================
`studio/__version__.py` is the only place a product version is authored. This
script pushes it into every other surface that has to state one, and can also
verify they agree without writing anything.

Surfaces:
  - studio/extension/manifest.json  ("version" field read by Chrome)
  - release/latest.json             (served to opt-in update checks)

The FastAPI application and the packaging metadata already import the source
module directly, so they cannot drift and are not handled here.

Usage:
    python tools/sync_version.py            propagate
    python tools/sync_version.py --check    verify only, non-zero exit on drift

The --check mode is what belongs in CI. A release built from a tree where the
extension claims one version and the application claims another is a support
problem that surfaces only after a user has already installed it.

Strict Invariants:
- Zero em-dashes.
- Chrome requires one to four dot separated integers, each 0 to 65535. A
  version that would be rejected at install time must fail here instead.
"""

import json
import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VERSION_FILE = os.path.join(REPO_ROOT, "studio", "__version__.py")
MANIFEST = os.path.join(REPO_ROOT, "studio", "extension", "manifest.json")
RELEASE_MANIFEST = os.path.join(REPO_ROOT, "release", "latest.json")

CHROME_VERSION_RE = re.compile(r"^\d{1,5}(\.\d{1,5}){0,3}$")


def read_source_version() -> str:
    """Parses the version without importing, so this runs with no dependencies."""
    with open(VERSION_FILE, encoding="utf-8") as f:
        text = f.read()
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not match:
        raise SystemExit(f"could not find __version__ in {VERSION_FILE}")
    return match.group(1)


def validate_for_chrome(version: str) -> None:
    if not CHROME_VERSION_RE.match(version):
        raise SystemExit(
            f"version {version!r} is not a valid Chrome extension version. "
            "Chrome requires one to four dot separated integers, each 0 to 65535."
        )
    for part in version.split("."):
        if int(part) > 65535:
            raise SystemExit(f"version segment {part} exceeds the Chrome maximum of 65535")


def sync_manifest(version: str, check_only: bool) -> bool:
    """Returns True when the manifest already agreed or was updated successfully."""
    with open(MANIFEST, encoding="utf-8") as f:
        raw = f.read()
    data = json.loads(raw)
    current = data.get("version")

    if current == version:
        print(f"  manifest.json     {current} (in sync)")
        return True

    if check_only:
        print(f"  manifest.json     {current} DRIFT, source says {version}")
        return False

    # Rewrite only the version line so the file's formatting and key order are
    # preserved. Chrome reads this file directly during an unpacked load.
    updated, count = re.subn(
        r'("version"\s*:\s*)"[^"]*"',
        lambda m: m.group(1) + '"' + version + '"',
        raw,
        count=1,
    )
    if count != 1:
        raise SystemExit("could not locate the version field in manifest.json")
    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        f.write(updated)
    print(f"  manifest.json     {current} -> {version}")
    return True


def sync_release_manifest(version: str, check_only: bool) -> bool:
    """
    Keeps the update manifest in step.

    This file is what an opt-in update check reads. If it lags behind a
    published release, every user is told they are up to date when they are not,
    and there is no other channel through which to correct that.
    """
    if not os.path.exists(RELEASE_MANIFEST):
        print("  release/latest.json MISSING")
        return False

    with open(RELEASE_MANIFEST, encoding="utf-8") as f:
        raw = f.read()
    try:
        current = json.loads(raw).get("version")
    except json.JSONDecodeError as exc:
        # This file is fetched by every opt-in client. Malformed JSON here breaks
        # update checks for everyone, so fail with a readable message rather than
        # a traceback, and never attempt to rewrite a file we cannot parse.
        print(f"  latest.json       INVALID JSON at line {exc.lineno} column {exc.colno}: {exc.msg}")
        return False

    if current == version:
        print(f"  latest.json       {current} (in sync)")
        return True
    if check_only:
        print(f"  latest.json       {current} DRIFT, source says {version}")
        return False

    updated, count = re.subn(
        r'("version"\s*:\s*)"[^"]*"',
        lambda m: m.group(1) + '"' + version + '"',
        raw,
        count=1,
    )
    if count != 1:
        raise SystemExit("could not locate the version field in release/latest.json")
    with open(RELEASE_MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        f.write(updated)
    print(f"  latest.json       {current} -> {version}")
    return True


def main() -> int:
    check_only = "--check" in sys.argv
    version = read_source_version()
    validate_for_chrome(version)

    print(f"source of truth: studio/__version__.py = {version}")
    ok = sync_manifest(version, check_only)
    ok = sync_release_manifest(version, check_only) and ok

    if check_only and not ok:
        print()
        print("Version drift detected. Run: python tools/sync_version.py")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
