"""
Quality cycle 2026-10, batch F8: integration loose ends in what the interface
and the help say, held to what the product does.

These read the components' rendered text (comments removed), because the
claims are copy: a sentence on screen that a buyer relies on.
"""

import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
COMPONENTS = os.path.join(REPO_ROOT, "studio", "ui", "src", "components")
HELP = os.path.join(REPO_ROOT, "docs", "help")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _rendered(name):
    source = _read(os.path.join(COMPONENTS, name))
    source = re.sub(r"\{/\*.*?\*/\}", "", source, flags=re.DOTALL)
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//[^\n]*$", "", source, flags=re.MULTILINE)


# ---------------------------------------------------------------------------
# F7-N2: the rail's shield does not claim everything stays on this machine
# ---------------------------------------------------------------------------

def test_rail_shield_makes_no_all_local_claim():
    """
    The always-visible shield said "All processing is local to this machine",
    while Send to LinkedIn, a connected AI provider and Generate send data out.
    """
    rendered = _rendered("StudioRail.tsx")
    assert "All processing is local" not in rendered
    assert not re.search(r"never\s+leaves?", rendered, flags=re.IGNORECASE)


def test_rail_shield_points_to_what_leaves():
    rendered = _rendered("StudioRail.tsx")
    match = re.search(r'<div[^>]*title="([^"]+)"[^>]*>\s*<ShieldCheck', rendered)
    assert match, "the shield lost its tooltip"
    tooltip = match.group(1)
    assert "Local security" in tooltip, "the tooltip does not say where to see what leaves"
    for action in ("Send to LinkedIn", "AI provider"):
        assert action in tooltip, f"the tooltip does not name {action} as something that sends"


def test_help_no_longer_says_the_rail_tooltip_is_out_of_date():
    article = _read(os.path.join(HELP, "what-leaves-this-machine.md"))
    assert "All processing is local to this machine" not in article
