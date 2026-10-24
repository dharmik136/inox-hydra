"""
The Queue opens on the week, and says what was missed and why.
==============================================================

ONEVIEW.md section 1: on a three year install the Queue rendered 770
characters, 8.7% ink and three controls, in a column using 57% of the width
it was given, and it answered one question ("when does the next post go
out") that nothing else on it supported. It did not say that a post had been
missed, and it had no reading of the creator's own rhythm to judge the slots
against.
"""

from datetime import datetime, timedelta

import pytest
from playwright.sync_api import expect

from qc2_r5_live import confirm_identity, open_section, seed_creator, server, studio  # noqa: F401


def _queue_a_post(client, text, when):
    created = client.post("/api/posts", json={"content": text + "\n\nIts body.", "status": "draft"})
    assert created.status_code == 200, created.text
    post_id = created.json()["id"]
    moved = client.post(
        f"/api/posts/{post_id}/reschedule",
        json={"scheduled_for": when.strftime("%Y-%m-%d %H:%M:%S")},
    )
    assert moved.status_code == 200, moved.text
    return post_id


def test_the_week_is_the_first_thing_on_the_queue(studio):
    confirm_identity(studio["client"])
    now = datetime.now()
    _queue_a_post(studio["client"], "The rota rewrite shipped.", now + timedelta(days=1, hours=2))
    page = open_section(studio, "queue")

    week = page.locator("section", has_text="This week").first
    expect(week).to_be_visible(timeout=10000)
    # Seven named days, each carrying its slots and what sits in them.
    for day in ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"):
        expect(week).to_contain_text(day)
    expect(week).to_contain_text("TODAY")
    assert week.locator("li").count() >= 7
    assert studio["errors"] == [], studio["errors"]


def test_a_post_sits_in_the_cell_whose_day_its_own_row_names(studio):
    """
    WRITE-22's family, in the new week grid. Reading the stored time as UTC
    put a post queued for Saturday 10:57 PM into the Sunday cell while the
    queued row beside it read Saturday. The grid and the row are both
    lib/time.ts now, so they cannot disagree.
    """
    confirm_identity(studio["client"])
    # Soon, because the API will not schedule into the past, and inside the
    # week the grid draws, which runs Monday to Sunday: "tomorrow" is in the
    # next week when this runs on a Sunday, and the post would then be in no
    # cell at all.
    now = datetime.now()
    when = now + timedelta(minutes=90)
    week_ends = (now + timedelta(days=7 - ((now.weekday() + 7) % 7))).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    if when >= week_ends:
        pytest.skip("the next free moment is in next week, which this week's grid does not draw")
    _queue_a_post(studio["client"], "The one queued post.", when)

    page = open_section(studio, "queue")
    week = page.locator("section", has_text="This week").first
    expect(week).to_be_visible(timeout=10000)

    agreement = page.evaluate(
        """() => {
          const cells = Array.from(document.querySelectorAll('section ul li'))
            .map((li) => li.innerText)
            .filter((t) => /QUEUED|DUE|MISSED|EMPTY|No slot/.test(t));
          const queued = cells.filter((t) => /\\d+ QUEUED/.test(t));
          const row = Array.from(document.querySelectorAll('li'))
            .map((li) => li.innerText)
            .find((t) => t.includes('The one queued post.'));
          return { queued, row };
        }"""
    )
    assert len(agreement["queued"]) == 1, agreement
    # The cell's day initial and the weekday the row prints are the same day.
    day_in_cell = agreement["queued"][0].split("\n")[0].strip()
    assert agreement["row"], "the queued post is not listed"
    weekday = agreement["row"].split(",")[0].strip().upper()
    assert weekday.startswith(day_in_cell[:3]) or day_in_cell.startswith(weekday[:3]), (
        f"the week grid says {day_in_cell} and the row says {weekday}"
    )


def test_the_queue_uses_the_width_it_is_given(studio):
    confirm_identity(studio["client"])
    page = open_section(studio, "queue")
    expect(page.locator("h1")).to_have_text("Queue")
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
    assert extent["used"] / extent["area"] > 0.8, (
        f"the Queue uses {extent['used']:.0f}px of {extent['area']:.0f}px"
    )


def test_a_missed_post_says_it_was_missed_and_how_late_it_was_noticed(studio):
    """
    The reason is the scheduler's own: nothing was running at its time. The
    post keeps the time the creator chose; only they may move it.
    """
    client = studio["client"]
    confirm_identity(client)
    # The API will not schedule into the past, correctly, so the state a
    # missed post is actually in is written as the scheduler writes it.
    import sqlite3  # noqa: F401  (the studio's own connection is used below)
    from database import get_db
    from scheduler import MISSED_POST_KEY

    when = datetime.now() - timedelta(hours=26)
    stamp = when.strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT INTO posts (id, content, status, scheduled_for, created_at) VALUES (?, ?, 'due', ?, ?)",
            ("post_t5_missed", "Missed while the machine slept.\n\nIts body.", stamp, stamp),
        )
        conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (
                MISSED_POST_KEY + "post_t5_missed",
                '{"scheduled_for": "%s", "noticed_at": "%s", "late_minutes": 1560.0}'
                % (stamp, datetime.now().isoformat(timespec="seconds")),
            ),
        )
    conn.close()

    page = open_section(studio, "queue")
    due = page.locator("section", has_text="Due, waiting for you to post it").first
    expect(due).to_contain_text("MISSED, WAS DUE", timeout=10000)
    expect(due).to_contain_text("closed or the machine asleep")
    expect(due).to_contain_text("It kept its time; nothing moved it")
    # Noticed 1,560 minutes late, said in a unit a person reads.
    expect(due).to_contain_text("26.0 hours late")
    assert studio["errors"] == [], studio["errors"]


def test_the_slots_are_judged_against_the_creators_own_rhythm(studio):
    """
    T2 measures how steadily the creator actually posts. The Queue's own
    cadence percentage said "100%" beside "Collisions 0" on an empty queue,
    which is a number about nothing.
    """
    seed_creator(studio["client"], commenter=None)
    page = open_section(studio, "queue")
    cadence = page.locator("section", has_text="Cadence").first
    expect(cadence).to_be_visible(timeout=10000)
    expect(cadence).to_contain_text("Against your own rhythm")
    expect(cadence).to_contain_text("Your usual gap")
    expect(cadence).to_contain_text("Posts read")
    expect(cadence).to_contain_text("These slots")
    # The percentage that could not be explained is no longer printed.
    assert "Cadence health" not in cadence.inner_text()
    assert studio["errors"] == [], studio["errors"]
