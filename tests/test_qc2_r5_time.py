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


def test_today_names_the_post_just_marked_published(studio):
    """D-9: Today showed a months-old post as your latest right after Mark as published."""
    from qc2_r5_live import seed_creator

    client = studio["client"]
    seed_creator(client, commenter=None)
    created = client.post("/api/posts", json={"content": "Shipping the rota rewrite today.", "status": "draft"})
    post_id = created.json()["id"]
    assert client.post(f"/api/posts/{post_id}/publish-now").status_code == 200
    page = studio["page"]
    page.goto(studio["url"] + "/#/today", wait_until="networkidle")
    section = page.locator("section", has_text="Your latest post").first.inner_text()
    assert "You marked “Shipping the rota rewrite today.” as published" in section, section
    assert "once the bridge sees it on LinkedIn" in section, section


def test_today_does_not_say_nothing_captured_beside_posts_it_holds(studio):
    """D-10: "captured" counted the capture's runs, which a creator cannot see."""
    client = studio["client"]
    confirm_identity(client)
    post = {"activity_urn": urn_days_ago(9, 1), "actor": ME, "text": "Nobody reads your roadmap.", "reactions": 12}
    assert client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [post]}).status_code == 200
    brief = client.get("/api/v1/today").json()
    assert brief["freshness"]["posts_held"] == 1, brief["freshness"]
    page = studio["page"]
    page.goto(studio["url"] + "/#/today", wait_until="networkidle")
    line = page.locator("article > p.studio-meta").first.inner_text()
    assert "NOTHING CAPTURED YET" not in line, line
    if not brief["freshness"]["last_capture_at"]:
        assert "1 POST OF YOURS HELD" in line, line
