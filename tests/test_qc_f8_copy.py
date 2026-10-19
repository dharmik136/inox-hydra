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


# ---------------------------------------------------------------------------
# UX-21 rest: Activity shows only what it measured, under one name
# ---------------------------------------------------------------------------

def test_activity_claims_no_live_feed_and_names_no_fixed_address():
    """
    It read "Live updates on" while the studio was down, and told the user to
    check 127.0.0.1:8000, which is wrong whenever the studio runs elsewhere.
    """
    rendered = _rendered("ActivitySurface.tsx")
    assert "Live updates" not in rendered
    assert not re.search(r"127\.0\.0\.1|localhost|:8000", rendered), "Activity names a fixed address"


def test_activity_says_when_it_last_heard_and_when_the_studio_stops_answering():
    rendered = _rendered("ActivitySurface.tsx")
    assert "Updated " in rendered, "Activity does not say when what it shows was read"
    assert "not answering" in rendered, "Activity keeps showing old data as current when the studio stops"


def test_the_header_button_calls_the_screen_activity():
    with open(os.path.join(REPO_ROOT, "studio", "ui", "src", "App.tsx"), encoding="utf-8") as handle:
        source = handle.read()
    source = re.sub(r"\{/\*.*?\*/\}", "", source, flags=re.DOTALL)
    source = re.sub(r"^\s*//[^\n]*$", "", source, flags=re.MULTILINE)
    assert ">Live Activity<" not in source, "the header calls the Activity screen 'Live Activity'"
    assert re.search(r'<span className="max-sm:sr-only">Activity</span>', source)


# ---------------------------------------------------------------------------
# F6-N1: the command-line reference describes the reset the studio now does
# ---------------------------------------------------------------------------

def test_cli_reference_describes_the_narrow_reset():
    """
    It said reset empties the settings table, Brand Studio profile, grounding
    sources and queue pause included. support.reset_configuration clears only
    the AI provider settings and the stored LinkedIn session.
    """
    import sys

    sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
    from support import RESET_SETTING_KEYS

    article = _read(os.path.join(HELP, "command-line-tool-reference.md"))
    for stale in ("every row of the settings table", "Clears the settings table", "It clears more"):
        assert stale not in article, f"the article still says {stale!r}"
    for kept in ("Brand Studio profile", "queue"):
        assert kept in article
    assert "AI provider" in article and "LinkedIn session" in article
    assert "ai_api_key" in RESET_SETTING_KEYS and "li_at" in RESET_SETTING_KEYS
