"""
A topic's reactions are the engine's one reading of each post.
==============================================================

get_topic_attribution_map summed own_posts.reactions, the snapshot column the
activity page overwrites, while every other screen reads a post's figures
through results.figures, the newest reading the studio holds (cycle 4, track
3, batch 0, from the sections report's defects table: "against the
single-reading rule"). So a topic's total could disagree with the Posts
screen's figures for the same posts in the same minute.
"""

import os
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

READ = "urn:li:activity:7380000000000000101"
SNAPSHOT_ONLY = "urn:li:activity:7380000000000000102"


@pytest.fixture
def home(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_qc4_t3_topics_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    init_db()
    conn = get_db()
    with conn:
        for urn, snapshot in ((READ, 5), (SNAPSHOT_ONLY, 7)):
            conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, reactions, first_seen_at, last_seen_at) "
                         "VALUES (?, 'Croissant notes.\n\nThe detail.', '2026-08-01T09:00:00+00:00', ?, '2026-10-01', '2026-10-01')",
                         (urn, snapshot))
        # A newer reading of the first post, from its activity page: the
        # figure every other screen shows for it.
        conn.execute("INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, source, "
                     "impressions, reactions, comments, reposts) VALUES (?, '2026-10-20T10:00:00+00:00', '2026-10-20T10', "
                     "1920, 'activity_page', 900, 50, 4, 1)", (READ,))
    conn.close()
    yield path
    shutil.rmtree(path, ignore_errors=True)


def test_a_topics_reactions_are_the_engines_figures(home):
    import results
    from database import get_db
    from evidence_briefing import get_topic_attribution_map
    conn = get_db()
    try:
        figures = results.figures(conn)
    finally:
        conn.close()
    assert figures[READ]["reactions"] == 50 and figures[READ]["source"] == "activity_page"
    assert figures[SNAPSHOT_ONLY]["reactions"] == 7 and figures[SNAPSHOT_ONLY]["source"] == results.SNAPSHOT
    answer = get_topic_attribution_map()
    assert answer["status"] == "success"
    total = sum(topic["total_reactions"] for topic in answer["topics"])
    assert total == 57, f"the topics summed {total}: the snapshot (5 + 7) rather than the one reading (50 + 7)"
