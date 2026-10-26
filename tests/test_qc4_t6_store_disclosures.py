"""
Item 30: the store listing's disclosures, held to the manifest.
===============================================================

release/STORE_DISCLOSURES.md is what the coordinator pastes into the store
dashboards. A permission the manifest declares with no justification here
is the gap a reviewer finds first, so every permission and host permission
in studio/extension/manifest.json must have its row, and the Limited Use
policy's prominent disclosure must be there.

Strict Invariants:
- Zero em-dashes.
"""

import io
import json
import os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DISCLOSURES = os.path.join(REPO_ROOT, "release", "STORE_DISCLOSURES.md")
MANIFEST = os.path.join(REPO_ROOT, "studio", "extension", "manifest.json")


def _read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def _declared():
    manifest = json.loads(_read(MANIFEST))
    return (list(manifest.get("permissions", [])) + list(manifest.get("optional_permissions", [])),
            list(manifest.get("host_permissions", [])) + list(manifest.get("optional_host_permissions", [])))


def _unjustified(text, permissions, hosts):
    rows = [line for line in text.splitlines() if line.startswith("| ")]
    missing = [p for p in permissions if not any(line.startswith(f"| `{p}` |") for line in rows)]
    missing += [h for h in hosts if not any(f"`{h}`" in line for line in rows)]
    return missing


def test_every_declared_permission_has_its_justification():
    permissions, hosts = _declared()
    assert permissions and hosts
    assert _unjustified(_read(DISCLOSURES), permissions, hosts) == []


def test_the_guard_can_fail():
    """Falsified: a permission the manifest gains without a row here is caught."""
    permissions, hosts = _declared()
    assert _unjustified(_read(DISCLOSURES), permissions + ["notifications"], hosts) == ["notifications"]


def test_the_limited_use_disclosure_is_prominent_and_true():
    text = " ".join(_read(DISCLOSURES).split())
    assert "Limited Use" in text
    assert "The prominent disclosure, for the top of the listing description" in text
    assert "127.0.0.1:8000" in text and "no server of ours" in text
    assert "Remote code" in text and "> No." in text
    for certification in ("I do not sell or transfer user data to third parties",
                          "I do not use or transfer user data for purposes that are unrelated",
                          "I do not use or transfer user data to determine creditworthiness"):
        assert certification in text


def test_the_cookies_and_tabs_rows_say_every_use():
    """
    Review note N-18: the cookies row said li_at is read only on Sync, while
    the popup reads it each time it opens and the worker watches it to keep
    its digest; it is sent only on Sync. tabs is used from the side panel too.
    """
    rows = {line.split("|")[1].strip(): line for line in _read(DISCLOSURES).splitlines() if line.startswith("| `")}
    cookies = " ".join(rows["`cookies`"].split())
    assert "Only when you press Sync LinkedIn Session, it reads your li_at and JSESSIONID" not in cookies
    assert "watches it change" in cookies and "to show in the popup whether you are signed in" in cookies
    assert "Only when you press Sync LinkedIn Session does it" in cookies
    assert "side panel" in rows["`tabs`"]
