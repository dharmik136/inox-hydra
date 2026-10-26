"""
The rail: seventeen sections in five groups, with labels at desktop width.
=========================================================================

Cycle 4, track 4, and sections decisions 1, 5, 15 and 16. The rail was twelve
icons in a 56 pixel column, the pattern measured as ignored, with Setup first
because a new install starts there. It is now:

  Now      Today, Replies, From your record
  Make     Composer, Queue, Outbound
  Learn    Posts, Leads, Audience, Patterns, Analytics, Brand
  Bridge   Activity, Health
  Studio   Setup, Docs, Settings

The five group names are headers and never controls (decision 15). The rail
shows its labels from 1200 pixels wide and collapses to icons with a label
on hover below that (decision 16). Setup stays at the foot, so its place
never moves, and the studio opens on it until Setup is done (decision 5). A
chip at the foot says whether the bridge has been heard from and opens
Health. navigation.ts is the one definition: the tray, the palette, the
screen audit and the help's rail table follow it.

Strict Invariants:
- Zero em-dashes.
"""

import io
import os
import re

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI = os.path.join(REPO_ROOT, "studio", "ui", "src")
HELP = os.path.join(REPO_ROOT, "docs", "help")

GROUPS = [
    ("now", "Now", [("today", "Today"), ("replies", "Replies"), ("record", "From your record")]),
    ("make", "Make", [("composer", "Composer"), ("queue", "Queue"), ("outbound", "Outbound")]),
    ("learn", "Learn", [("posts", "Posts"), ("leads", "Leads"), ("audience", "Audience"), ("patterns", "Patterns"),
                        ("analytics", "Analytics"), ("brand", "Brand")]),
    ("bridge", "Bridge", [("activity", "Activity"), ("health", "Health")]),
    ("studio", "Studio", [("setup", "Setup"), ("docs", "Docs"), ("settings", "Settings")]),
]


def _read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def _code(path):
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", _read(path), flags=re.S)


def _sections():
    """(id, group, label) for each entry of STUDIO_SECTIONS, in order."""
    navigation = _code(os.path.join(UI, "lib", "navigation.ts"))
    body = navigation.split("export const STUDIO_SECTIONS", 1)[1].split("];", 1)[0]
    found = []
    for entry in re.findall(r"\{[^{}]*\bid: \"[a-z]+\"[^{}]*\}", body):
        section = re.search(r'\bid: "([a-z]+)"', entry).group(1)
        group = re.search(r'\bgroup: "([a-z]+)"', entry)
        label = re.search(r'\blabel: "([^"]+)"', entry).group(1)
        found.append((section, group.group(1) if group else None, label))
    return found


def _groups():
    navigation = _code(os.path.join(UI, "lib", "navigation.ts"))
    body = navigation.split("export const STUDIO_GROUPS", 1)[1].split("];", 1)[0]
    return re.findall(r'\{\s*id: "([a-z]+)",\s*label: "([^"]+)"\s*\}', body)


# ---------------------------------------------------------------------------
# The one definition
# ---------------------------------------------------------------------------

def test_the_rail_is_seventeen_sections_in_five_groups_in_the_reports_order():
    """The report's sixteen, and From your record (track 7) third in Now."""
    sections = [s for s in _sections() if s[0] != "devtools"]
    expected = [(section, group, label) for group, _name, entries in GROUPS for section, label in entries]
    assert sections == expected, f"the rail reads {sections}"
    assert len(sections) == 17
    assert _groups() == [(group, name) for group, name, _entries in GROUPS]


def test_devtools_stays_behind_dev_mode_and_outside_the_rail_groups():
    devtools = [s for s in _sections() if s[0] == "devtools"]
    assert devtools == [("devtools", None, "Devtools")], "devtools joined a group"
    app = _code(os.path.join(UI, "App.tsx"))
    assert 'section.id !== "devtools" || devMode' in app, "devtools is offered without dev mode"


def test_group_headers_are_headers_and_never_controls():
    """Decision 15: five headers, never clickable levels."""
    for name in ("StudioRail.tsx", "NavigationTray.tsx"):
        source = _code(os.path.join(UI, "components", name))
        headers = re.findall(r"<(\w+)[^<>]*data-rail-group[^<>]*>", source, flags=re.S)
        assert headers, f"{name} draws no group header"
        for tag in headers:
            assert tag not in ("button", "a"), f"{name} draws a group header as a {tag}"
        for opening in re.findall(r"<\w+[^<>]*data-rail-group[^<>]*>", source, flags=re.S):
            assert "onClick" not in opening and "href" not in opening and "tabIndex" not in opening, (
                f"a group header in {name} can be activated: {opening[:120]}")


def test_the_rail_opens_with_labels_from_1200_pixels():
    rail = _read(os.path.join(UI, "components", "StudioRail.tsx"))
    viewport = _read(os.path.join(UI, "lib", "viewport.ts"))
    assert 'RAIL_EXPANDED_QUERY = "(min-width: 1200px)"' in viewport
    assert "RAIL_EXPANDED_QUERY" in rail


def test_the_palette_and_the_audit_follow_the_rail():
    palette = _read(os.path.join(UI, "components", "CommandPalette.tsx"))
    assert "sections.map" in palette and "STUDIO_SECTIONS" not in palette
    audit = _read(os.path.join(REPO_ROOT, "tools", "ui_audit.py"))
    block = audit.split("SECTIONS = {", 1)[1].split("}", 1)[0]
    walked = re.findall(r'"([a-z]+)": "([^"]+)"', block)
    assert walked == [(section, label) for _g, _n, entries in GROUPS for section, label in entries], walked


def test_the_help_tabulates_the_rail_as_it_is():
    """The first-run article's rail table: every label, under its group, in order."""
    article = _read(os.path.join(HELP, "open-the-studio-for-the-first-time.md"))
    table = article.split("| Rail label | Group |", 1)[1].split("\n\n", 1)[0]
    rows = re.findall(r"^\| ([A-Z][A-Za-z ]+?) \| (Now|Make|Learn|Bridge|Studio) \|", table, flags=re.M)
    expected = [(label, name) for _g, name, entries in GROUPS for _s, label in entries]
    assert rows == expected, rows


def test_no_help_article_sends_a_creator_to_a_rail_entry_that_is_gone():
    """Brand Studio is no longer a rail label: Brand and Settings open it until the two are split."""
    offences = []
    for name in sorted(os.listdir(HELP)):
        if not name.endswith(".md"):
            continue
        for sentence in re.split(r"(?<=[.!?])\s+|\n", _read(os.path.join(HELP, name))):
            if re.search(r"\*\*Brand Studio\*\* (in|from|on) the rail", sentence) or "Press **Brand Studio**" in sentence:
                offences.append(f"{name}: {sentence.strip()[:90]}")
    assert not offences, "help sends a creator to a rail entry that is gone: " + "; ".join(offences)


def test_setup_done_is_one_definition():
    """The studio opens on Setup until Setup says it is done, and both read the same rule."""
    app = _code(os.path.join(UI, "App.tsx"))
    setup = _code(os.path.join(UI, "components", "OnboardingSurface.tsx"))
    assert "setupDone(" in app and "setupDone(" in setup
    assert "steps.identity ?" not in app, "the landing still decides by the identity step alone"


# ---------------------------------------------------------------------------
# In a browser
# ---------------------------------------------------------------------------

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

from qc2_r5_live import confirm_identity, seed_creator, server, studio  # noqa: E402,F401

LABELS = [label for _g, _n, entries in GROUPS for _s, label in entries]


def _rail(page):
    return page.locator("nav[aria-label='Studio sections']")


def test_at_desktop_width_the_rail_reads_as_five_groups_with_labels(studio):
    page = studio["page"]
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(studio["url"] + "/#/today", wait_until="networkidle")
    rail = _rail(page)
    tops = []
    for label in LABELS:
        button = rail.get_by_role("button", name=label, exact=True)
        expect(button).to_be_visible()
        expect(button).to_contain_text(label)
        tops.append(button.bounding_box()["y"])
    assert tops == sorted(tops), "the rail is not in the report's order"
    for _g, name, _e in GROUPS:
        header = rail.locator("[data-rail-group]", has_text=name)
        expect(header).to_be_visible()
        assert rail.get_by_role("button", name=name, exact=True).count() == 0, f"{name} is a control"
    # Setup sits in the foot, below the rest of the rail, and the chip opens Health.
    setup = rail.get_by_role("button", name="Setup", exact=True).bounding_box()
    assert setup["y"] > 900 / 2, "Setup is not at the foot of the rail"
    assert studio["errors"] == [], studio["errors"]


def test_below_1200_pixels_the_rail_is_icons_with_a_label_on_hover(studio):
    page = studio["page"]
    page.set_viewport_size({"width": 1100, "height": 800})
    page.goto(studio["url"] + "/#/today", wait_until="networkidle")
    rail = _rail(page)
    box = rail.bounding_box()
    assert box["width"] <= 64, f"the rail is {box['width']} pixels wide below 1200"
    button = rail.get_by_role("button", name="Audience", exact=True)
    expect(button).not_to_contain_text("Audience")
    button.hover()
    expect(page.locator("[data-rail-hover-label]", has_text="Audience")).to_be_visible()


def test_the_bridge_chip_says_what_was_heard_and_opens_health(studio):
    confirm_identity(studio["client"])
    page = studio["page"]
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(studio["url"] + "/#/today", wait_until="networkidle")
    chip = _rail(page).get_by_role("button", name=re.compile(r"^Bridge (connected|not connected)\. Open Health$"))
    expect(chip).to_be_visible(timeout=10000)
    chip.click()
    expect(page.locator("h1")).to_have_text("Is the bridge reading?")


def _finish_setup(client, archive=True):
    """The required steps: the bridge heard, you confirmed, your posts read to the end; the archive only if asked."""
    from database import get_db
    seed_creator(client)
    conn = get_db()
    with conn:
        if archive:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('archive_no_posts_at', '2026-10-01T00:00:00+00:00')")
        conn.execute("INSERT INTO self_import_requests (kind, requested_at, started_at, finished_at, items_seen, outcome) "
                     "VALUES ('posts', '2026-10-01T00:00:00+00:00', '2026-10-01T00:00:00+00:00', "
                     "'2026-10-01T00:05:00+00:00', 5, 'end_of_list')")
    conn.close()


def test_a_creator_whose_setup_is_not_done_lands_on_setup(studio):
    """Decision 5: the studio lands on Setup until Setup is done, not only until it knows who you are."""
    confirm_identity(studio["client"])
    page = studio["page"]
    page.goto(studio["url"] + "/", wait_until="networkidle")
    page.wait_for_selector("h1")
    assert page.url.endswith("#/setup"), page.url


def test_a_creator_whose_setup_is_done_lands_on_today(studio):
    _finish_setup(studio["client"])
    page = studio["page"]
    page.goto(studio["url"] + "/", wait_until="networkidle")
    expect(page.locator("h1")).to_have_text("What to do in the next hour", timeout=10000)
    assert page.url.endswith("#/today"), page.url


def test_skipping_the_archive_does_not_send_a_creator_back_to_setup(studio):
    """Importing LinkedIn's archive is offered in Setup, not required to land on Today."""
    _finish_setup(studio["client"], archive=False)
    page = studio["page"]
    page.goto(studio["url"] + "/", wait_until="networkidle")
    expect(page.locator("h1")).to_have_text("What to do in the next hour", timeout=10000)
