"""
Demo mode seeds a creator's queue and drafts, not the original author's campaign.
=================================================================================

Demo mode used to seed the Launch Kit: sixteen drafts, days 02 to 17 of the
original author's first-person campaign about scraping, anti-bot detection
and building this product, each with a scheduled post row and no time, so the
demo's Queue listed sixteen posts that could never go out and the Composer's
drafts were somebody else's words. Its two dated scheduled posts were in
September, so a demo opened later showed a queue of missed posts, one of them
the author's own.

Now demo mode seeds what a creator's own queue holds: drafts and a few posts
queued at the creator's next open slots, in the sample creator's voice and
labelled demo data. The cleanup still removes everything an earlier version
seeded, Launch Kit included, and still keeps anything the creator changed.

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

AUTHOR_MARKERS = ("Dharmik", "dharmik136", "dharmik-shingala", "Enterprise Labs", "Project Prudent")
CAMPAIGN_WORDS = ("scrap", "anti-bot", "Voyager", "G-Stack", "microservices")


@pytest.fixture
def demo(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t4b_demo_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.setenv("INOX_DEMO_DATA", "1")
    import database
    database.init_db()
    database.seed_initial_data()
    yield database
    shutil.rmtree(home, ignore_errors=True)


def _rows(database, sql, args=()):
    conn = database.get_db()
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def _restart_without_the_flag(monkeypatch, database):
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    database.init_db()
    database.seed_initial_data()


def test_demo_mode_seeds_no_launch_kit_and_none_of_the_authors_posts(demo):
    assert _rows(demo, "SELECT COUNT(*) AS n FROM drafts")[0]["n"] == 0, "the Launch Kit drafts are still seeded"
    assert _rows(demo, "SELECT COUNT(*) AS n FROM posts WHERE id LIKE 'post-day%'")[0]["n"] == 0
    for post in _rows(demo, "SELECT id, content FROM posts"):
        text = post["content"] or ""
        for marker in AUTHOR_MARKERS + CAMPAIGN_WORDS:
            assert marker.lower() not in text.lower(), f"{post['id']} carries {marker!r}"


def test_the_demo_queue_and_drafts_look_like_a_creators_own(demo):
    drafts = _rows(demo, "SELECT id, content FROM posts WHERE status = 'draft'")
    assert len(drafts) >= 3, "the demo's Composer and Queue have no drafts"
    queued = _rows(demo, "SELECT id, content, scheduled_for FROM posts WHERE status = 'scheduled'")
    assert len(queued) >= 2, "the demo's queue is empty"
    slots = {(r["day_of_week"], r["time_slot"])
             for r in _rows(demo, "SELECT day_of_week, time_slot FROM queue_slots WHERE is_active = 1")}
    now = datetime.now(timezone.utc)
    for post in queued:
        assert post["scheduled_for"], f"{post['id']} is queued with no time"
        when = datetime.fromisoformat(post["scheduled_for"].replace("Z", "+00:00"))
        assert when > now, f"{post['id']} is queued in the past, so the demo opens on a missed post"
        local = when.astimezone()
        assert (local.weekday(), local.strftime("%H:%M")) in slots, f"{post['id']} is not at one of the creator's slots"
    for post in drafts + queued:
        assert "(demo data)" in post["content"], f"{post['id']} does not say it is demo data"


def test_the_cleanup_still_removes_what_an_earlier_version_seeded(demo, monkeypatch):
    # What 2.9.0 seeded: the sixteen Launch Kit drafts and their post rows, and
    # the two September posts.
    conn = demo.get_db()
    try:
        for seeder in demo._DEMO_DRAFT_SEEDERS:
            seeder(conn)
        for row in demo.demo_post_rows():
            conn.execute("INSERT OR REPLACE INTO posts (id, content, media_urls, status, scheduled_for, published_at, "
                         "impressions, reactions, comments, shares, tags) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", row)
        conn.commit()
    finally:
        conn.close()
    assert _rows(demo, "SELECT COUNT(*) AS n FROM drafts")[0]["n"] >= 16

    _restart_without_the_flag(monkeypatch, demo)
    assert _rows(demo, "SELECT COUNT(*) AS n FROM drafts")[0]["n"] == 0
    assert _rows(demo, "SELECT COUNT(*) AS n FROM posts WHERE id LIKE 'post-day%'")[0]["n"] == 0
    left = _rows(demo, "SELECT id FROM posts")
    assert left == [], f"demo posts outlived demo mode: {[r['id'] for r in left]}"


def test_a_demo_post_the_creator_changed_is_theirs(demo, monkeypatch):
    conn = demo.get_db()
    try:
        draft = conn.execute("SELECT id FROM posts WHERE status = 'draft' ORDER BY id LIMIT 1").fetchone()["id"]
        queued = conn.execute("SELECT id FROM posts WHERE status = 'scheduled' ORDER BY id LIMIT 1").fetchone()["id"]
        conn.execute("UPDATE posts SET content = content || ' My own words.' WHERE id = ?", (draft,))
        conn.execute("UPDATE posts SET scheduled_for = '2030-01-01T09:00:00.000Z' WHERE id = ?", (queued,))
        conn.commit()
    finally:
        conn.close()
    _restart_without_the_flag(monkeypatch, demo)
    kept = {r["id"] for r in _rows(demo, "SELECT id FROM posts")}
    assert kept == {draft, queued}, f"the cleanup took a post the creator changed, or left a demo post: {kept}"


def test_seeding_twice_seeds_once(demo):
    before = _rows(demo, "SELECT id FROM posts ORDER BY id")
    demo.init_db()
    demo.seed_initial_data()
    assert _rows(demo, "SELECT id FROM posts ORDER BY id") == before
