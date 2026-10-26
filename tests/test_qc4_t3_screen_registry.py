"""
Every section can be filed against, and the registry lists no ghost.
====================================================================

Only six of the twelve sections carried a screenKey into the backend's
screen registry, so an annotation filed from Setup, Today, Activity, Posts,
Patterns, Outbound or Devtools resolved to "unknown"; and the registry still
listed the Swipe File and Command, which cycle 3 cut (cycle 4, track 3,
batch 0, from the sections report's defects table). The existing guard in
test_devtools.py holds that a declared key exists in the registry; this
holds the other two directions: every section declares one, and every
registry entry is a section that exists.
"""

import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

import devtools  # noqa: E402

NAVIGATION = os.path.join(REPO_ROOT, "studio", "ui", "src", "lib", "navigation.ts")


def _sections():
    """(id, screenKey or None) for each entry of STUDIO_SECTIONS, in rail order."""
    with open(NAVIGATION, encoding="utf-8") as handle:
        source = handle.read()
    block = source.split("export const STUDIO_SECTIONS", 1)[1].split("\n];", 1)[0]
    found = []
    for entry in re.findall(r"\{\s*id:\s*\"([a-z]+)\"([^}]*)\}", block):
        key = re.search(r'screenKey:\s*"([a-z_]+)"', entry[1])
        found.append((entry[0], key.group(1) if key else None))
    return found


def test_every_section_declares_a_screen_key():
    missing = [section for section, key in _sections() if key is None]
    assert not missing, f"an annotation filed from these sections resolves to unknown: {missing}"


def test_the_registry_lists_no_section_that_no_longer_exists():
    declared = {key for _section, key in _sections() if key}
    registered = {screen["key"] for screen in devtools.SCREEN_REGISTRY.values()}
    ghosts = sorted(registered - declared)
    assert not ghosts, f"the registry lists screens the rail does not have: {ghosts}"


def test_the_guard_reads_the_rail_it_is_about():
    sections = dict(_sections())
    assert {"composer", "queue", "leads", "analytics", "docs", "settings"} <= set(sections), sections
    assert sections["composer"] == "studio" and sections["leads"] == "crm"
