"""
The extension manifest, against what the stores check.
======================================================
Chrome Web Store and Microsoft Edge Add-ons both review the manifest before a
human ever looks at the listing. Each permission must be used by the code that
ships, because the reviewer asks what every one is for and an unused entry is
answered with a rejection and a resubmission.

`activeTab` was declared and never called. Nothing executes a script on the
tab the user clicked: the side panel talks to the content script by message,
and reading `tab.url` works from the LinkedIn host permission. So it was a
permission the owner would have had to justify and could not.

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import re
import struct

EXT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "studio", "extension"
)

# Permissions whose use the grep below cannot see, with the reason. An entry
# here is a claim a reviewer may ask about, so it names where it is used.
# Empty since 2.10.0: alarms, the one entry, is now called as
# chrome.alarms.create (the heartbeat, the drain and the check of the
# extension's own files) as well as chrome.alarms.clear, so the grep sees it.
PERMISSIONS_WITHOUT_A_CHROME_CALL = {}


def _manifest():
    with open(os.path.join(EXT_DIR, "manifest.json"), encoding="utf-8") as handle:
        return json.load(handle)


def _extension_sources():
    sources = {}
    for root, _dirs, files in os.walk(EXT_DIR):
        for name in files:
            if not name.endswith((".js", ".html")):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8") as handle:
                sources[os.path.relpath(path, EXT_DIR)] = handle.read()
    return sources


def test_every_declared_permission_is_used_by_the_shipped_code():
    """A reviewer asks what each permission is for; an unused one has no answer."""
    manifest = _manifest()
    sources = _extension_sources()

    unused = []
    for permission in manifest["permissions"]:
        if permission in PERMISSIONS_WITHOUT_A_CHROME_CALL:
            continue
        pattern = re.compile(r"\bchrome\.%s\." % re.escape(permission))
        if not any(pattern.search(text) for text in sources.values()):
            unused.append(permission)

    assert unused == [], (
        "These permissions are declared but never called, so the stores have "
        "nothing to approve: %s" % unused
    )


def test_active_tab_is_not_declared():
    """Nothing in the extension uses it, and the side panel works without it."""
    manifest = _manifest()
    assert "activeTab" not in manifest["permissions"]
    sources = _extension_sources()
    assert not any("activeTab" in text for text in sources.values())


def test_manifest_fields_fit_the_store_forms():
    """Name, description and version as the upload validators want them."""
    manifest = _manifest()

    assert manifest["manifest_version"] == 3

    # Chrome Web Store truncates a longer name in the listing.
    assert 0 < len(manifest["name"]) <= 75, len(manifest["name"])

    # The manifest description is the fallback summary. Chrome refuses a
    # longer one at upload.
    description = manifest["description"]
    assert description.strip()
    assert len(description) <= 132, len(description)

    # One to four dot separated integers, each below 65536, no leading zeros.
    parts = manifest["version"].split(".")
    assert 1 <= len(parts) <= 4, manifest["version"]
    for part in parts:
        assert part.isdigit() and 0 <= int(part) < 65536, manifest["version"]
        assert part == "0" or not part.startswith("0"), manifest["version"]


def test_the_three_listed_icons_exist_at_their_stated_size():
    """A missing or wrongly sized icon fails the upload, not the review."""
    manifest = _manifest()
    for size in ("16", "48", "128"):
        relative = manifest["icons"][size]
        path = os.path.join(EXT_DIR, relative)
        assert os.path.isfile(path), relative
        with open(path, "rb") as handle:
            header = handle.read(24)
        assert header[:8] == b"\x89PNG\r\n\x1a\n", relative
        width, height = struct.unpack(">II", header[16:24])
        assert (width, height) == (int(size), int(size)), (relative, width, height)


def test_no_remote_code_and_no_off_host_permission():
    """Both stores refuse code fetched at runtime, and ask why each host is needed."""
    manifest = _manifest()

    assert set(manifest["host_permissions"]) == {
        "https://*.linkedin.com/*",
        "http://127.0.0.1:8000/*",
        "http://localhost:8000/*",
    }, manifest["host_permissions"]

    # Nothing is loaded from a network origin, and nothing is compiled from
    # text at runtime.
    for relative, text in _extension_sources().items():
        if relative.endswith(".html"):
            assert not re.search(r"<script[^>]+src=[\"']https?:", text), relative
            assert not re.search(r"<link[^>]+href=[\"']https?:", text), relative
        assert "new Function(" not in text, relative
        assert not re.search(r"(^|[^.\w])eval\s*\(", text), relative

    # No remote origin is granted a channel into the extension either.
    assert "externally_connectable" not in manifest
