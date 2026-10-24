"""
The Composer opens on the place you type.
=========================================

Review send-back on T5-COMPOSER-FEED. The What worked panel was added above
the editor and opened by default, so on a three year install the textarea's
top landed at y=834 at 1440x900, leaving 66 pixels of it on screen, and at
1280x800 none of it was on screen at all. At the branch point the same
editor's top was y=252. The feeding is right and stays; what it cannot do is
push the writing off the screen it was added to.

This drives the built interface with the creator's own posts seeded, so the
panel has its full three strongest and two weakest to show, and with a draft
restored into the editor, which is what a real install does.
"""

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

from qc2_r5_live import seed_creator, server, studio  # noqa: F401

# A draft about the length the three year install restores, so the
# auto-growing textarea is as tall here as it is there.
LONG_DRAFT = ("The rota rewrite shipped this morning and three things broke.\n\n"
              + ("A paragraph of the post, long enough to grow the editor. " * 12)
              + "\n\n"
              + ("Another paragraph, so the column runs past a screen. " * 12))

# What a writer needs to see of the editor to start typing in it.
ROOM_TO_TYPE = 200


def _ready(studio, width=1440, height=900):
    """A creator with posts of their own, a draft to restore, and the Composer open."""
    client = studio["client"]
    seed_creator(client, commenter=None)
    created = client.post("/api/posts", json={"content": LONG_DRAFT, "status": "draft"})
    assert created.status_code == 200, created.text
    page = studio["page"]
    page.set_viewport_size({"width": width, "height": height})
    page.goto(studio["url"] + "/#/composer", wait_until="networkidle")
    expect(page.locator('[aria-label="Post body"]')).to_be_visible(timeout=10000)
    page.wait_for_timeout(900)
    return page


def _editor_top(page):
    return page.evaluate("() => document.querySelector('main textarea').getBoundingClientRect().top")


def test_what_worked_is_folded_when_the_composer_opens(studio):
    """
    Named, offered and one press away, but not in front of the caret. This
    is the rule the editor's position depends on, so it is asserted on its
    own rather than inferred from a measurement.
    """
    page = _ready(studio)
    panel = page.locator("section[aria-labelledby=composer-what-worked]")
    expect(panel).to_be_visible(timeout=10000)
    expect(panel).to_contain_text("What worked, from your own posts")
    expect(panel.get_by_role("button", name="SHOW")).to_be_visible()
    assert "Use this opening" not in panel.inner_text(), (
        "the panel opens over the editor by default"
    )


@pytest.mark.parametrize("width,height", [(1440, 900), (1280, 800)])
def test_the_editor_is_on_screen_when_the_composer_opens(studio, width, height):
    page = _ready(studio, width, height)
    top = _editor_top(page)
    assert height - top >= ROOM_TO_TYPE, (
        f"at {width}x{height} the editor starts at y={top:.0f}, with "
        f"{max(0, height - top):.0f} pixels of it on screen"
    )


def test_opening_the_panel_still_leaves_the_editor_on_screen(studio):
    """
    A writer who asks for it gets it, and still has somewhere to type: the
    panel is bounded rather than as tall as the evidence it holds.
    """
    page = _ready(studio)
    panel = page.locator("section[aria-labelledby=composer-what-worked]")
    before = _editor_top(page)
    panel.get_by_role("button", name="SHOW").click()
    page.wait_for_timeout(500)
    expect(panel).to_contain_text("not a suggestion from a model")
    after = _editor_top(page)
    assert after > before, "the panel did not open"
    assert 900 - after >= ROOM_TO_TYPE, f"opening the panel put the editor at y={after:.0f}"
    assert studio["errors"] == [], studio["errors"]


def test_the_offer_survives_the_fold(studio):
    """Folded by default must not mean the feeding is gone."""
    page = _ready(studio)
    panel = page.locator("section[aria-labelledby=composer-what-worked]")
    panel.get_by_role("button", name="SHOW").click()
    page.wait_for_timeout(500)
    use = panel.get_by_role("button", name="Use this opening").first
    expect(use).to_be_visible(timeout=10000)
    offered = panel.locator("li").first.locator("p").first.inner_text()
    use.click()
    page.wait_for_timeout(400)
    assert page.locator('[aria-label="Post body"]').input_value().startswith(offered), (
        "the opening did not reach the editor"
    )
