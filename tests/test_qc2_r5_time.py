"""
One clock per screen, with a date when the day alone would mislead.
==================================================================

Cycle 2, batch R5, D-12. On a 12-hour machine Today's Queue card read "Mon
05:30 PM" for the next post and "Tuesday 17:30" for the next slot. The next
post had a weekday and no date, so a post from five weeks ago read as next
Monday. Posts wrote dates as "2026-10-17"; Activity wrote "Impressions: 4100"
and a count it never read as 0.
"""

import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from qc2_r5_live import ME, confirm_identity, server, urn_days_ago  # noqa: F401
from qc2_r5_live import studio as _studio  # noqa: F401


@pytest.fixture
def studio(server, _studio):  # noqa: F811
    """The same studio, with a page whose clock reads in 12-hour US English."""
    _studio["context"].close()
    context = server["browser"].new_context(viewport={"width": 1440, "height": 900}, service_workers="block",
                                            locale="en-US", timezone_id="UTC")
    _studio["page"] = context.new_page()
    _studio["context"] = context
    yield _studio
    context.close()


def _queue_a_post(scheduled_for):
    import database

    conn = database.get_db()
    try:
        conn.execute(
            "INSERT INTO posts (id, content, status, scheduled_for, created_at) VALUES (?, ?, 'scheduled', ?, ?)",
            (str(uuid.uuid4()), "A queued post about rotas.", scheduled_for, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def test_todays_queue_card_uses_one_clock_and_dates_the_next_post(studio):
    confirm_identity(studio["client"])
    when = (datetime.now(timezone.utc) - timedelta(days=36)).replace(hour=17, minute=30, second=0, microsecond=0)
    _queue_a_post(when.isoformat())
    page = studio["page"]
    page.goto(studio["url"] + "/#/today", wait_until="networkidle")
    card = page.locator("section", has_text="Next to go out").first
    text = card.inner_text()
    assert not re.search(r"\b(1[3-9]|2[0-3]):\d\d\b", text), f"a 24-hour time beside 12-hour ones: {text}"
    next_post = card.locator("dd").first.inner_text()
    assert str(when.day) in next_post and when.strftime("%b") in next_post, next_post
    assert "PM" in next_post, next_post


def test_posts_dates_read_as_dates_and_activity_figures_as_figures(studio):
    client = studio["client"]
    confirm_identity(client)
    urn = urn_days_ago(40, 3)
    post = {"activity_urn": urn, "actor": ME, "text": "Nobody reads your roadmap.", "reactions": 4100}
    assert client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [post]}).status_code == 200
    page = studio["page"]
    page.goto(studio["url"] + "/#/posts", wait_until="networkidle")
    body = page.inner_text("main")
    assert not re.search(r"\b20\d\d-\d\d-\d\d\b", body), body

    page.goto(studio["url"] + "/#/activity", wait_until="networkidle")
    page.wait_for_selector("text=Nobody reads your roadmap.")
    row = page.inner_text("main")
    assert "Reactions: 4,100" in row, row
    assert "Comments: not measured" in row, row
