"""
The Queue lists every due post; Today lists the first ten.
==========================================================

today.py said "Due posts listed on Today; the Queue lists every one", and
both callers used the same DUE_LIMIT of 10: /api/queue/due called
today.due_posts(conn) with the default (cycle 4, track 3, batch 0, from the
sections report's defects table). A creator with eleven posts waiting saw ten
on the screen whose job is to show what is due, with nothing saying one was
held back.

The Queue now asks for every due post. Today keeps its ten, because it is a
summary, and the one implementation still serves both.
"""

import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

DUE = 12


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t3_due_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    init_db()
    now = datetime.now()
    conn = get_db()
    with conn:
        for n in range(DUE):
            stamp = (now - timedelta(minutes=DUE - n)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("INSERT INTO posts (id, content, status, scheduled_for, created_at) VALUES (?, ?, 'due', ?, ?)",
                         (f"due-{n:02d}", f"Post {n}.\n\nIts body.", stamp, stamp))
    conn.close()
    import app as app_module
    from fastapi.testclient import TestClient
    yield TestClient(app_module.app)
    shutil.rmtree(home, ignore_errors=True)


def test_the_queue_lists_every_due_post(studio):
    import today
    answer = studio.get("/api/queue/due")
    assert answer.status_code == 200, answer.text
    due = answer.json()["due"]
    assert len(due) == DUE, f"the Queue holds {len(due)} of {DUE} due posts"
    assert [post["post_id"] for post in due] == [f"due-{n:02d}" for n in range(DUE)], "oldest first"
    assert DUE > today.DUE_LIMIT, "the fixture does not exceed Today's limit, so this proves nothing"


def test_today_keeps_its_summary_of_ten(studio):
    import today
    answer = studio.get("/api/v1/today")
    assert answer.status_code == 200, answer.text
    due = answer.json()["queue"]["due"]
    assert len(due) == today.DUE_LIMIT == 10
    assert [post["post_id"] for post in due] == [f"due-{n:02d}" for n in range(10)]


def test_the_comment_in_today_tells_the_truth():
    """The sentence that was false: it now says what each caller asks for."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend"))
    with open(os.path.join(root, "today.py"), encoding="utf-8") as handle:
        source = handle.read()
    with open(os.path.join(root, "routers", "queue.py"), encoding="utf-8") as handle:
        queue = handle.read()
    assert "due_posts(conn, limit=None)" in queue, "the Queue route still takes Today's limit"
    assert "the Queue lists every one" not in source or "limit=None" in source
