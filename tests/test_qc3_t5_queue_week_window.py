"""
The Queue draws the days a post can actually go out in, and shows the drafts.
============================================================================

Review send-back on T5-QUEUE, both parts.

The week grid was the calendar Monday to Sunday week containing today, so on
any day but Monday some of its cells were already past and a post queued for
next Tuesday appeared in no cell at all, while the cell headed TUE read
EMPTY two inches above the list that named that post's Tuesday. The cells
carried no date, so the two Tuesdays could not be told apart. The batch's own
week test skipped rather than failed when the moment it queued fell outside
the drawn week.

And the screen told a creator holding 150 drafts to go to the Composer to
queue one, while the left half of it was blank.

Everything here goes through the product's own routes: nothing is written
into the database by hand, which is what made the batch's own 25.6% figure
unreproducible.
"""

from datetime import datetime, timedelta

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

from qc2_r5_live import confirm_identity, open_section, server, studio  # noqa: F401


def _draft(client, text):
    created = client.post("/api/posts", json={"content": text + "\n\nIts body.", "status": "draft"})
    assert created.status_code == 200, created.text
    return created.json()["id"]


def _queue_at(client, post_id, when):
    moved = client.post(
        f"/api/posts/{post_id}/reschedule",
        json={"scheduled_for": when.strftime("%Y-%m-%d %H:%M:%S")},
    )
    assert moved.status_code == 200, moved.text


def _cells(page):
    """Each day cell of the week at a glance, as its text."""
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('section ul li'))
             .map((li) => li.innerText)
             .filter((t) => /QUEUED|DUE|MISSED|EMPTY|No slot/.test(t))"""
    )


def test_every_post_queued_in_the_next_week_is_in_a_cell(studio):
    """
    Six posts queued for the next six days, through the route the product
    uses. Every one of them is in the grid, whatever day of the week it is.
    """
    client = studio["client"]
    confirm_identity(client)
    now = datetime.now()
    for day in range(1, 7):
        _queue_at(client, _draft(client, f"Queued for day {day}."), now + timedelta(days=day, hours=1))

    page = open_section(studio, "queue")
    expect(page.locator("section", has_text="Next seven days").first).to_be_visible(timeout=10000)
    cells = _cells(page)
    assert len(cells) == 7, cells
    queued = sum(int(text.split(" QUEUED")[0].split("\n")[-1]) for text in cells if "QUEUED" in text)
    assert queued == 6, f"six posts were queued and {queued} are in the week: {cells}"


def test_each_day_in_the_grid_carries_its_date(studio):
    """
    Without a date, the creator cannot tell the grid's Monday from the
    Monday their post is queued for.
    """
    confirm_identity(studio["client"])
    page = open_section(studio, "queue")
    week = page.locator("section", has_text="Next seven days").first
    expect(week).to_be_visible(timeout=10000)
    today = datetime.now()
    expect(week).to_contain_text(str(today.day), timeout=5000)
    # Every cell, not just today's.
    dated = page.evaluate(
        """() => Array.from(document.querySelectorAll('section ul li'))
             .map((li) => li.innerText)
             .filter((t) => /QUEUED|DUE|MISSED|EMPTY|No slot/.test(t))
             .filter((t) => /\\b\\d{1,2}\\b/.test(t.split('\\n')[0]))"""
    )
    assert len(dated) == 7, f"only {len(dated)} of 7 cells carry a date"


def test_the_drafts_waiting_to_be_queued_are_on_the_queue(studio):
    """
    The screen said 'Queue a draft from the Composer' to a creator holding
    150 of them, with half the screen blank.
    """
    client = studio["client"]
    confirm_identity(client)
    for index in range(3):
        _draft(client, f"A draft waiting to be queued, number {index}.")

    page = open_section(studio, "queue")
    drafts = page.locator("section[aria-labelledby=queue-drafts]")
    expect(drafts).to_be_visible(timeout=10000)
    expect(drafts).to_contain_text("A draft waiting to be queued, number 2.")
    assert studio["errors"] == [], studio["errors"]


def test_a_draft_can_be_put_in_the_next_slot_from_the_queue(studio):
    """
    The way to act on what the screen now shows, on the screen that shows
    it, through the same route the Publish dialog uses.
    """
    client = studio["client"]
    confirm_identity(client)
    post_id = _draft(client, "The one draft to queue from here.")

    page = open_section(studio, "queue")
    drafts = page.locator("section[aria-labelledby=queue-drafts]")
    expect(drafts).to_be_visible(timeout=10000)
    row = drafts.locator("li", has_text="The one draft to queue from here.")
    row.get_by_role("button", name="Queue it").click()

    queued = page.locator("section[aria-labelledby=queue-scheduled]")
    expect(queued).to_contain_text("The one draft to queue from here.", timeout=10000)
    status = client.get("/api/posts?status=scheduled").json()["posts"]
    assert any(post["id"] == post_id for post in status), status
    assert studio["errors"] == [], studio["errors"]
