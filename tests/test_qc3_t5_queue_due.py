"""
One list of due posts, with the reason one was missed, on both screens.
=======================================================================

ONEVIEW.md section 2: "Queue state is not where posting happens", and the
Queue screen said nothing about a post having been missed or why. The Queue
read the generic posts endpoint (`/api/posts?status=due`), which carries no
missed note at all, while Today built its own list with the note attached. Two
screens, two lists of the same posts, one of them unable to say that a post
had been missed while the machine slept.

There is now one implementation, `today.due_posts`, and both screens read it:
Today inside its own brief, the Queue through `/api/queue/due`. This is the
shape `tests/test_fold_is_one_number.py` set for one definition in one place.
"""

import os
import sys
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import today as today_module  # noqa: E402
from database import get_db  # noqa: E402
from scheduler import MISSED_POST_KEY  # noqa: E402
import app as app_module  # noqa: E402

client = TestClient(app_module.app, base_url="http://127.0.0.1")

PREFIX = "post_qc3_t5_"


@pytest.fixture
def due_posts():
    """Two posts whose time has come, one of them missed. Removed afterwards."""
    now = datetime.now()
    rows = [
        (PREFIX + "ontime", "Its time has come.\n\nIts body.", now - timedelta(minutes=10), None),
        (PREFIX + "missed", "Missed while the machine slept.\n\nIts body.", now - timedelta(hours=26), 1560.0),
    ]
    conn = get_db()
    try:
        with conn:
            for post_id, content, when, late in rows:
                stamp = when.strftime("%Y-%m-%d %H:%M:%S")
                conn.execute(
                    "INSERT INTO posts (id, content, status, scheduled_for, created_at) "
                    "VALUES (?, ?, 'due', ?, ?)",
                    (post_id, content, stamp, stamp),
                )
                if late is not None:
                    conn.execute(
                        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (
                            MISSED_POST_KEY + post_id,
                            '{"scheduled_for": "%s", "noticed_at": "%s", "late_minutes": %s}'
                            % (stamp, now.isoformat(timespec="seconds"), late),
                        ),
                    )
    finally:
        conn.close()
    yield [row[0] for row in rows]
    conn = get_db()
    try:
        with conn:
            conn.execute(f"DELETE FROM posts WHERE id LIKE '{PREFIX}%'")
            conn.execute(f"DELETE FROM settings WHERE key LIKE '{MISSED_POST_KEY}{PREFIX}%'")
    finally:
        conn.close()


def _ours(items):
    return [item for item in items if item["post_id"].startswith(PREFIX)]


def test_the_queue_has_a_due_list_of_its_own(due_posts):
    answer = client.get("/api/queue/due")
    assert answer.status_code == 200, answer.text
    ours = _ours(answer.json()["due"])
    assert [item["post_id"] for item in ours] == [PREFIX + "missed", PREFIX + "ontime"], "oldest first"
    assert ours[0]["content"] == "Missed while the machine slept.\n\nIts body.", "Copy text needs the whole post"
    assert ours[1]["excerpt"].startswith("Its time has come.")


def test_the_queue_says_a_post_was_missed_and_how_late_it_was_noticed(due_posts):
    """
    The reason, in the scheduler's own terms. The Queue could not say this at
    all: /api/posts?status=due answers with no note, so a missed post read as
    an on-time one.
    """
    ours = _ours(client.get("/api/queue/due").json()["due"])
    missed = next(item for item in ours if item["post_id"] == PREFIX + "missed")
    assert missed["missed"], "the missed note did not reach the Queue"
    assert missed["missed"]["late_minutes"] == 1560.0
    assert missed["missed"]["noticed_at"]
    # Its own time, never moved: that is the whole point of the note.
    assert missed["missed"]["scheduled_for"] == missed["scheduled_for"]

    on_time = next(item for item in ours if item["post_id"] == PREFIX + "ontime")
    assert on_time["missed"] is None

    plain = client.get("/api/posts?status=due")
    assert plain.status_code == 200
    assert all("missed" not in post for post in plain.json()["posts"]), (
        "the generic posts endpoint grew a missed note; the Queue should still read /api/queue/due"
    )


def test_today_and_the_queue_answer_with_the_same_list(due_posts):
    """One implementation, two callers. The precedent is fold.py."""
    from_queue = _ours(client.get("/api/queue/due").json()["due"])
    from_today = _ours(client.get("/api/v1/today").json()["queue"]["due"])
    assert from_queue == from_today, "Today and the Queue disagree about what is due"

    conn = get_db()
    try:
        directly = _ours(today_module.due_posts(conn))
    finally:
        conn.close()
    assert directly == from_queue


def test_the_due_list_is_the_only_place_that_reads_the_due_status():
    """
    A second query for the same question is how the two screens drifted
    apart in the first place.
    """
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend"))
    with open(os.path.join(root, "today.py"), encoding="utf-8") as handle:
        today_source = handle.read()
    assert today_source.count("status = 'due'") == 1, "today.py reads the due status more than once"
    assert "def due_posts(" in today_source

    with open(os.path.join(root, "routers", "queue.py"), encoding="utf-8") as handle:
        queue_source = handle.read()
    assert "today_module.due_posts(" in queue_source, "the queue route builds its own due list"
    assert "status = 'due'" not in queue_source


def test_the_queue_screen_reads_the_new_route_and_shows_the_reason():
    """The screen, not just the route: a reason nothing prints is not a reason."""
    ui = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "ui", "src"))
    with open(os.path.join(ui, "lib", "api.ts"), encoding="utf-8") as handle:
        api = handle.read()
    assert '"/api/queue/due"' in api
    assert '"/api/posts?status=due"' not in api, "fetchDuePosts still reads the generic posts endpoint"

    with open(os.path.join(ui, "components", "QueueSurface.tsx"), encoding="utf-8") as handle:
        screen = handle.read()
    assert "MISSED, WAS DUE" in screen
    assert "closed or the machine asleep" in screen, "the Queue does not say why a post was missed"
    assert "late_minutes" in screen, "the Queue does not say how late it was noticed"
