"""
Today answers the day's questions in one view, without scrolling.
=================================================================

ONEVIEW.md sections 1 and 3. Today was a reading column 584 pixels wide in a
1384 pixel work area: 16.1% ink, 1,874 characters, 1.36 scroll pages, and it
answered three of the six questions a creator has each day. What worked, the
thirty day totals and the posting rhythm were on other screens, and two
signals the studio already held were readable only by calling an endpoint:
how many captures the extension is holding for a studio that was busy
(T3's /api/v1/extension/captures/waiting), and whether the backup schedule
has stopped running (T4's stale flag on /api/v1/storage).

This drives the built interface at 1440x900 and asks what is on the screen.
"""

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

from qc2_r5_live import confirm_identity, open_section, seed_creator, server, studio  # noqa: F401


def test_the_day_is_three_columns_and_nothing_is_below_the_fold(studio):
    seed_creator(studio["client"], commenter="Anika Shah")
    page = open_section(studio, "today")
    expect(page.locator("h1")).to_have_text("What to do in the next hour")

    # Three columns of content at 1440, not one centred column. Measured as
    # the distinct left edges of the panels, which is what a creator sees.
    edges = page.evaluate("""() => {
      const panels = Array.from(document.querySelectorAll('main section'));
      const lefts = panels
        .filter((el) => el.getBoundingClientRect().width > 120)
        .map((el) => Math.round(el.getBoundingClientRect().left / 8) * 8);
      return [...new Set(lefts)].sort((a, b) => a - b);
    }""")
    assert len(edges) >= 3, f"Today is not in three columns: panels start at {edges}"

    # The work area is used, rather than 42% of it with 400px blank either side.
    extent = page.evaluate("""() => {
      const main = document.querySelector('main');
      const box = main.getBoundingClientRect();
      let left = Infinity, right = 0;
      for (const el of main.querySelectorAll('*')) {
        if (!el.textContent || !el.textContent.trim()) continue;
        const r = el.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0) continue;
        left = Math.min(left, r.left); right = Math.max(right, r.right);
      }
      return { used: right - left, area: box.width };
    }""")
    assert extent["used"] / extent["area"] > 0.9, (
        f"Today uses {extent['used']:.0f}px of {extent['area']:.0f}px"
    )

    # Nothing to scroll to: the screen holds the day.
    pages = page.evaluate("""() => {
      const main = document.querySelector('main');
      return main.scrollHeight / main.clientHeight;
    }""")
    assert pages <= 2.0, f"Today is {pages:.2f} screens tall"
    assert studio["errors"] == [], studio["errors"]


def test_the_six_daily_questions_are_all_on_the_screen(studio):
    seed_creator(studio["client"], commenter="Anika Shah")
    page = open_section(studio, "today")
    main = page.locator("main")
    for panel in (
        "ONE THING TO OPEN",     # is there one thing broken
        "Reply to",              # who should I reply to
        "Your latest post",      # how is my latest post doing
        "What worked",           # what worked and what did not
        "Next out",              # what goes out next
        "Last 30 days",          # the thirty day line
        "Rhythm",                # how steadily am I posting
    ):
        expect(main).to_contain_text(panel, timeout=10000)
    assert studio["errors"] == [], studio["errors"]


def test_who_to_reply_to_carries_their_own_words(studio):
    """
    T1's unified post identity and T2's results engine make the comment text
    answerable, so the row is the person, what they did, and what they said.
    """
    seed_creator(studio["client"], commenter="Anika Shah", comment="This matches what we saw last year.")
    page = open_section(studio, "today")
    reply = page.locator("section", has_text="Reply to").first
    expect(reply).to_contain_text("Anika Shah", timeout=10000)
    expect(reply).to_contain_text("This matches what we saw last year.")


def test_captures_waiting_for_the_studio_are_said_on_the_screen(studio):
    """
    T3 kept the count and answered it on request; nothing showed it, so a
    creator had no way to learn that captured work was waiting.
    """
    client = studio["client"]
    confirm_identity(client)
    held = client.post("/api/v1/bridge/heartbeat", json={
        "extension_version": "2.6.0", "page_kind": "feed", "waiting_captures": 7,
    })
    assert held.status_code == 200, held.text
    waiting = client.get("/api/v1/extension/captures/waiting").json()
    assert waiting["measured"] and waiting["waiting"] == 7, waiting
    page = open_section(studio, "today")
    expect(page.locator("main")).to_contain_text("CAPTURES WAITING FOR THE STUDIO", timeout=10000)


def test_a_stale_backup_is_said_on_the_screen(studio):
    """
    T4 made the schedule report that it has stopped producing backups. It was
    true only inside the Storage and privacy panel's own endpoint.
    """
    page = studio["page"]
    page.route("**/api/v1/storage/backups", lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body=(
            '{"enabled": true, "last": null, "next_due": null, "automatic_count": 0, '
            '"zip_count": 0, "keeps": {"daily": 7, "weekly": 4, "monthly": 6, "database_copies": 3}, '
            '"directory": "/tmp", "last_daily": null, "rotation_reach_days": 180, '
            '"age_hours": 73.4, "stale": true, "never": false, "stale_after_hours": 48.0}'
        ),
    ))
    confirm_identity(studio["client"])
    page.goto(studio["url"] + "/#/today", wait_until="networkidle")
    expect(page.locator("main")).to_contain_text("NO BACKUP FOR 73 HOURS", timeout=10000)
    expect(page.locator("main")).to_contain_text("STORAGE AND PRIVACY")


def test_a_figure_the_studio_never_captured_says_so_rather_than_zero(studio):
    """The honesty rule, on the screen a creator reads every morning."""
    seed_creator(studio["client"], commenter=None)
    page = open_section(studio, "today")
    latest = page.locator("section", has_text="Your latest post").first
    expect(latest).to_be_visible(timeout=10000)
    text = latest.inner_text()
    # The seeded posts carry reactions and comments but no impressions, so
    # impressions is the figure with nothing behind it.
    assert "Not measured" in text, text
    assert studio["errors"] == [], studio["errors"]
