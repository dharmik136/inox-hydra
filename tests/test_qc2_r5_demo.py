"""
Demo Data Confirms a Sample Creator (D-25).
===========================================

`--demo` never confirmed an identity, so Today, Posts, Patterns and Outbound,
which are about the confirmed creator, showed only their empty states in demo
mode, and the UI audit run against a demo never saw them with data. Demo mode
now confirms a sample creator with a few posts of their own, people engaging
on them and some outbound activity, all marked as samples, and a start
without demo mode removes exactly that.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import os
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from studio.backend import app as app_module  # noqa: E402
from studio.backend import database, onboarding, paths  # noqa: E402


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.setenv("INOX_DEMO_DATA", "1")
    monkeypatch.delenv("INOX_DEMO_CREATOR", raising=False)
    database.init_db()
    database.seed_initial_data()
    return TestClient(app_module.app)


def _count(sql, *args):
    conn = sqlite3.connect(paths.get_db_path())
    try:
        return conn.execute(sql, args).fetchone()[0]
    finally:
        conn.close()


def test_demo_mode_confirms_a_sample_creator(demo):
    assert onboarding.confirmed_vanity() == database.DEMO_VANITY
    state = demo.get("/api/v1/onboarding/state").json()
    assert state["steps"]["identity"] is True


def test_today_has_a_latest_post_and_people_to_reply_to(demo):
    brief = demo.get("/api/v1/today").json()
    assert brief["identity"]["known"] is True
    assert brief["latest_post"], "Today shows no post of the demo creator"
    assert "(demo data)" in (brief["latest_post"].get("excerpt") or "")
    assert brief["reply_to"], "nobody is waiting on a reply in demo mode"
    assert all("(demo data)" in person["name"] for person in brief["reply_to"])


def test_posts_patterns_and_outbound_have_data(demo):
    posts = demo.get("/api/v1/insights/posts").json()
    assert len(posts["posts"]) == len(database.DEMO_OWN_POSTS), posts.keys()
    assert any(post["people"] for post in posts["posts"]), "no demo post lists the people who engaged"

    patterns = demo.get("/api/v1/insights/patterns").json()
    assert patterns["posts_compared"] >= 7, patterns
    assert patterns["patterns"], f"Patterns has nothing to compare in demo mode: {patterns['not_enough_posts']}"

    outbound = demo.get("/api/v1/insights/outbound").json()
    assert outbound != {} and _count("SELECT COUNT(*) FROM outbound_engagements") == len(database.DEMO_OUTBOUND)


def test_seeding_twice_writes_nothing_more(demo):
    before = (_count("SELECT COUNT(*) FROM own_posts"), _count("SELECT COUNT(*) FROM lead_interactions"))
    database.seed_initial_data()
    assert (_count("SELECT COUNT(*) FROM own_posts"), _count("SELECT COUNT(*) FROM lead_interactions")) == before


def test_a_real_creator_is_never_replaced(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.setenv("INOX_DEMO_DATA", "1")
    monkeypatch.delenv("INOX_DEMO_CREATOR", raising=False)
    database.init_db()
    onboarding.observe_profile({"vanity": "real-person", "self_evidence": ["owner_edit_controls"]})
    onboarding.confirm_identity("real-person")
    database.seed_initial_data()
    assert onboarding.confirmed_vanity() == "real-person"
    assert _count("SELECT COUNT(*) FROM own_posts") == 0


def test_the_older_demo_is_one_setting_away(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.setenv("INOX_DEMO_DATA", "1")
    monkeypatch.setenv("INOX_DEMO_CREATOR", "0")
    database.init_db()
    database.seed_initial_data()
    assert onboarding.confirmed_vanity() == ""


def test_a_start_without_demo_mode_removes_the_sample_creator(demo, monkeypatch):
    real_post = "urn:li:activity:7300000000000000001"
    conn = sqlite3.connect(paths.get_db_path())
    conn.execute("INSERT INTO own_posts (activity_urn, text, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?)",
                 (real_post, "A post of mine", "2026-10-01T00:00:00", "2026-10-01T00:00:00"))
    conn.commit()
    conn.close()

    monkeypatch.delenv("INOX_DEMO_DATA")
    database.seed_initial_data()

    assert onboarding.confirmed_vanity() == ""
    assert _count("SELECT COUNT(*) FROM own_posts WHERE text LIKE '%(demo data)%'") == 0
    assert _count("SELECT COUNT(*) FROM own_posts WHERE activity_urn = ?", real_post) == 1, "a non-demo row went"
    assert _count("SELECT COUNT(*) FROM leads WHERE name LIKE 'Sample engager%'") == 0
    assert _count("SELECT COUNT(*) FROM outbound_engagements") == 0
    notice = demo.get("/api/v1/today").json().get("demo_cleanup") or {}
    removed = {item["kind"]: item["count"] for item in notice.get("removed", [])}
    assert removed.get("posts", 0) >= len(database.DEMO_OWN_POSTS)
