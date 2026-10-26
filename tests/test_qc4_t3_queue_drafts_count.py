"""
The Queue counts the drafts waiting and offers one action.
==========================================================

The Queue listed eight drafts under "Drafts waiting" while the Composer's
Drafts panel lists them all, so two screens listed the same drafts and the
Queue did a second screen's job in its second view (cycle 4, decision 6:
"the count, with one action"). The Queue now says how many drafts are
waiting, names the newest, and offers to queue that one in the next slot;
the drafts themselves stay in the Composer.

The count comes from the posts route, which now says how many rows a
status holds beside the page it returns, so the screen reads one draft
rather than eight (every draft was 259 KB on a three year install).
"""

import os
import re
import shutil
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

SURFACE = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "QueueSurface.tsx")
API = os.path.join(REPO_ROOT, "studio", "ui", "src", "lib", "api.ts")


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t3_drafts_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    init_db()
    conn = get_db()
    with conn:
        for n in range(12):
            conn.execute("INSERT INTO posts (id, content, status, created_at) VALUES (?, ?, 'draft', ?)",
                         (f"draft-{n:02d}", f"Draft number {n}.\n\nIts body.", f"2026-10-{n + 1:02d} 09:00:00"))
        conn.execute("INSERT INTO posts (id, content, status, created_at) VALUES ('pub-1', 'Out.', 'published', '2026-10-20 09:00:00')")
    conn.close()
    import app as app_module
    from fastapi.testclient import TestClient
    yield TestClient(app_module.app)
    shutil.rmtree(home, ignore_errors=True)


def test_the_posts_route_says_how_many_a_status_holds(studio):
    answer = studio.get("/api/posts?status=draft&limit=1")
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["total"] == 12, body
    assert [post["id"] for post in body["posts"]] == ["draft-11"], "the newest draft is not the one returned"
    assert studio.get("/api/posts?status=published").json()["total"] == 1
    assert studio.get("/api/posts").json()["total"] == 13


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def test_the_queue_reads_one_draft_and_the_count():
    api = _read(API)
    assert "fetchRecentDrafts" not in api, "the Queue still has a way to read a list of drafts"
    reader = api.split("export async function fetchDraftsWaiting", 1)[1].split("\n}", 1)[0]
    assert '"/api/posts?status=draft&limit=1"' in reader, "the Queue does not read one draft"
    assert "data.total" in reader, "the Queue does not read the count the route answers with"
    surface = _read(SURFACE)
    assert "fetchDraftsWaiting().catch(() => null)" in surface, "a failed read could still draw as no drafts"
    assert "DRAFTS_SHOWN" not in surface, "the Queue still bounds a list of drafts it no longer draws"


def test_the_queue_shows_a_count_and_one_action():
    surface = _read(SURFACE)
    section = surface[surface.index('aria-labelledby="queue-drafts"'):]
    section = section[:section.index("</section>")]
    assert "Queue the newest" in section, "the one action is missing"
    assert "Edit text" not in section, "the drafts block still carries a second action"
    assert not re.search(r"drafts\.map\(", section), "the drafts block still draws a list"
    assert "waiting" in section
