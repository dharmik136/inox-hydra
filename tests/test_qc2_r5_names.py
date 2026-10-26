"""
One name for one thing, and Setup's own words about where it ends.
=================================================================

Cycle 2, batch R5, D-17 and D-20. The import of your LinkedIn history was
"Import all three" on Setup, "Sync Activity via Bridge" on Today and "Sync All
Activity" on Activity, while Setup's sentence said "run Posts you wrote" and
Posts said 'Run "Posts you wrote"'. Today and Setup gave it a tick, which
reads as done on a button that starts work. Activity said "Bridge running" or
"Bridge idle" where the header and Today say connected. Setup counted "1
comments", and had no word for being finished.
"""

import os
import re

from qc2_r5_live import ME, open_section, seed_creator, server, studio, urn_days_ago  # noqa: F401

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI = os.path.join(REPO_ROOT, "studio", "ui", "src", "components")
OLD_NAMES = ("Import all three", "Sync Activity via Bridge", "Sync All Activity", "run Posts you wrote",
             'Run "Posts you wrote"', "Bridge running", "Bridge idle")


def _source(name):
    with open(os.path.join(UI, name), encoding="utf-8") as handle:
        return handle.read()


def test_no_screen_uses_the_old_names_on_screen():
    for name in ("TodaySurface.tsx", "ActivitySurface.tsx", "OnboardingSurface.tsx", "PostsSurface.tsx"):
        # Comments may name the old labels to say why they went; the screen may not.
        code = re.sub(r"/\*.*?\*/|//[^\n]*", "", _source(name), flags=re.S)
        for old in OLD_NAMES:
            assert old not in code, f"{name} still says {old!r}"


def test_the_history_import_has_one_name_on_every_screen(studio):
    seed_creator(studio["client"])
    for section in ("today", "activity", "setup"):
        page = open_section(studio, section)
        button = page.get_by_role("button", name="Import your history", exact=True)
        button.first.wait_for()
        assert button.count() == 1, section
        # A download mark, not a tick.
        assert button.first.locator("svg.lucide-download").count() == 1, section


def test_activity_names_the_bridge_as_the_header_does(studio):
    page = open_section(studio, "activity")
    page.wait_for_selector("text=What the bridge has read")
    text = page.inner_text("main").lower()
    assert "bridge not connected" in text, text
    assert "run a sync" not in text, text


def test_setup_counts_one_comment_as_one_comment(studio):
    client = studio["client"]
    seed_creator(client, commenter=None)
    item = {"kind": "comment", "target_activity_urn": urn_days_ago(3, 77), "target_author": "Tom Becker",
            "my_text": "Nice write-up."}
    stored = client.post("/api/v1/self/outbound/ingest", json={"actor": ME, "items": [item]})
    assert stored.status_code == 200 and stored.json().get("written", 1) == 1, stored.text
    page = open_section(studio, "setup")
    page.wait_for_selector("text=Your history")
    text = page.inner_text("main")
    assert "5 posts, 1 comment, 0 reactions" in text, text
    assert "1 comments" not in text


def test_setup_says_when_it_is_done():
    code = _source("OnboardingSurface.tsx")
    assert "Setup is done." in code and "Go to Today" in code
    with open(os.path.join(REPO_ROOT, "studio", "ui", "src", "App.tsx"), encoding="utf-8") as handle:
        app = handle.read()
    # The element Setup is drawn by, whatever else it is handed (cycle 4 added
    # the way to Health): it must be given the way to Today.
    element = app.split("<OnboardingSurface", 1)[1].split("/>", 1)[0]
    assert 'onOpenToday={() => navigate("today")}' in element, element
