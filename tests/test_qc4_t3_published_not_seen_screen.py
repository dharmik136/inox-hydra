"""
Posts shows the posts marked published here and not yet seen on LinkedIn.
=========================================================================

Review round 2, B2 (b), in the browser: under the table when posts are
imported, and under the empty state when none are, because a creator whose
only published posts went out from the studio would otherwise see nothing.
"""

from datetime import datetime, timezone

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

from qc2_r5_live import open_section, seed_creator, server, studio  # noqa: F401,E402


def _marked_published(text):
    from database import get_db
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO posts (id, content, status, published_at) VALUES ('sent-1', ?, 'published', ?)",
                     (text, datetime.now(timezone.utc).isoformat()))
    conn.close()


def test_the_group_sits_under_the_table(studio):
    seed_creator(studio["client"])
    _marked_published("Sent to LinkedIn from the studio.\n\nBody.")
    page = open_section(studio, "posts")
    group = page.locator("section[aria-labelledby=posts-not-yet-seen]")
    expect(group).to_contain_text("Published here, not yet seen on LinkedIn", timeout=10000)
    expect(group).to_contain_text("Sent to LinkedIn from the studio.")
    expect(group).to_contain_text("no figures and no people here")
    assert studio["errors"] == [], studio["errors"]


def test_the_group_sits_under_the_empty_state(studio):
    _marked_published("The only post so far, sent from the studio.\n\nBody.")
    page = open_section(studio, "posts")
    expect(page.locator("main")).to_contain_text("None of your posts have been imported yet", timeout=10000)
    group = page.locator("section[aria-labelledby=posts-not-yet-seen]")
    expect(group).to_contain_text("The only post so far, sent from the studio.")
    assert studio["errors"] == [], studio["errors"]


def test_nothing_is_drawn_when_there_are_none(studio):
    seed_creator(studio["client"])
    page = open_section(studio, "posts")
    expect(page.locator("main")).to_contain_text("What worked, and who it brought", timeout=10000)
    page.wait_for_timeout(500)
    assert page.locator("section[aria-labelledby=posts-not-yet-seen]").count() == 0
