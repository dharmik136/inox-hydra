"""
Queue the newest draft acts only on a post that is still a draft.
=================================================================

Review round 2, S5. The Queue's one action on drafts calls the reschedule
route, which set status = 'scheduled' on whatever post it was given. The
drafts block can be 30 seconds stale, so the action could silently move a
draft queued meanwhile to another slot, or flip a post published meanwhile
back to scheduled, so that it came due again and Today asked the creator
to post it twice.

The route now writes only when the post is in the state the caller expects,
in one conditional UPDATE rather than a read and then a write, and refuses
with a sentence otherwise. The Queue expects "draft". Whatever the caller,
a published post is never put back in the queue.
"""

import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

QUEUE = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "QueueSurface.tsx")
ROUTER = os.path.join(REPO_ROOT, "studio", "backend", "routers", "posts.py")
WHEN = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0).isoformat()


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t3_s5_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    import app as app_module
    from fastapi.testclient import TestClient
    from security import TOKEN_HEADER, get_or_create_token
    yield TestClient(app_module.app, base_url="http://127.0.0.1:8000", headers={TOKEN_HEADER: get_or_create_token()})
    shutil.rmtree(home, ignore_errors=True)


def _post(post_id, status, scheduled_for=None, published_at=None):
    from database import get_db
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO posts (id, content, status, scheduled_for, published_at) VALUES (?, 'A post.', ?, ?, ?)",
                     (post_id, status, scheduled_for, published_at))
    conn.close()


def _row(post_id):
    from database import get_db
    conn = get_db()
    try:
        return dict(conn.execute("SELECT status, scheduled_for, published_at FROM posts WHERE id = ?", (post_id,)).fetchone())
    finally:
        conn.close()


def test_a_post_published_meanwhile_is_not_put_back_in_the_queue(studio):
    """The reviewer's case, through the route the Queue calls."""
    published_at = "2026-10-20T09:00:00+00:00"
    _post("was-a-draft", "published", published_at=published_at)
    answer = studio.post("/api/posts/was-a-draft/reschedule", json={"scheduled_for": WHEN, "expected_status": "draft"})
    assert answer.status_code == 409, answer.text
    assert "no longer a draft" in answer.json()["detail"]
    assert _row("was-a-draft") == {"status": "published", "scheduled_for": None, "published_at": published_at}


def test_a_published_post_is_never_requeued_whoever_asks(studio):
    _post("published-1", "published", published_at="2026-10-20T09:00:00+00:00")
    answer = studio.post("/api/posts/published-1/reschedule", json={"scheduled_for": WHEN})
    assert answer.status_code == 409, answer.text
    assert _row("published-1")["status"] == "published"


def test_a_draft_queued_meanwhile_is_not_moved(studio):
    earlier = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0).isoformat()
    _post("queued-1", "scheduled", scheduled_for=earlier)
    answer = studio.post("/api/posts/queued-1/reschedule", json={"scheduled_for": WHEN, "expected_status": "draft"})
    assert answer.status_code == 409, answer.text
    assert _row("queued-1") == {"status": "scheduled", "scheduled_for": earlier, "published_at": None}


def test_a_draft_is_queued(studio):
    _post("draft-1", "draft")
    answer = studio.post("/api/posts/draft-1/reschedule", json={"scheduled_for": WHEN, "expected_status": "draft"})
    assert answer.status_code == 200, answer.text
    assert _row("draft-1")["status"] == "scheduled"


def test_the_queue_says_what_it_expects_and_the_write_is_conditional():
    queue = open(QUEUE, encoding="utf-8").read()
    assert 'schedulePost(draft.id, slot.slot_datetime, "draft")' in queue, "the Queue does not say the post must be a draft"
    router = open(ROUTER, encoding="utf-8").read()
    route = router[router.index("def reschedule_post"):]
    route = route[:route.index("\n@router")]
    assert "AND status" in route and "rowcount" in route, "the write is not a conditional update"
