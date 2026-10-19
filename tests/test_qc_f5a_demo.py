"""
Demo data leaves when demo mode does.
=====================================

Starting once with INOX_DEMO_DATA=1 (a demo, a screenshot session, the e2e or
ui_audit --demo run) wrote four invented people, sixteen of the original
author's drafts, sample posts with invented figures, 90 days of analytics and
an audience breakdown. Restarting without the flag kept all of it, and the
people carried no sign that they were invented, so they read as real leads.
purge_all_seeded_data existed, but nothing called it and it did not cover the
people or the drafts.

Now every start without the flag removes what the seeder can be shown to have
written, and nothing else: a lead captured, a draft written or a seeded draft
the creator rewrote during a demo stays.
"""

import os
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))


@pytest.fixture
def demo_home(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_demo_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.setenv("INOX_DEMO_DATA", "1")
    import database

    database.init_db()
    database.seed_initial_data()
    yield database


def _count(database, sql, args=()):
    conn = database.get_db()
    try:
        return conn.execute(sql, args).fetchone()[0]
    finally:
        conn.close()


def _restart_without_the_flag(monkeypatch, database):
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    database.init_db()
    database.seed_initial_data()


def _demo_lead_ids(database):
    return tuple(lead[0] for lead in database.DEMO_LEADS)


def test_the_premise_demo_mode_writes_all_of_it(demo_home):
    ids = _demo_lead_ids(demo_home)
    marks = ",".join("?" * len(ids))
    assert _count(demo_home, f"SELECT COUNT(*) FROM leads WHERE id IN ({marks})", ids) == 4
    assert _count(demo_home, "SELECT COUNT(*) FROM drafts") >= 16
    assert _count(demo_home, "SELECT COUNT(*) FROM analytics_daily WHERE source = 'seed'") == 90


def test_turning_demo_mode_off_removes_every_invented_row(demo_home, monkeypatch):
    _restart_without_the_flag(monkeypatch, demo_home)
    ids = _demo_lead_ids(demo_home)
    marks = ",".join("?" * len(ids))
    post_marks = ",".join("?" * len(demo_home.DEMO_POST_IDS))
    left = {
        "sample leads": _count(demo_home, f"SELECT COUNT(*) FROM leads WHERE id IN ({marks})", ids),
        "their enrichment": _count(demo_home, f"SELECT COUNT(*) FROM lead_enrichments WHERE lead_id IN ({marks})", ids),
        "the author's drafts": _count(demo_home, "SELECT COUNT(*) FROM drafts"),
        "their post rows": _count(demo_home, "SELECT COUNT(*) FROM posts WHERE id LIKE 'post-day%'"),
        "sample posts": _count(demo_home, f"SELECT COUNT(*) FROM posts WHERE id IN ({post_marks})", demo_home.DEMO_POST_IDS),
        "seeded analytics": _count(demo_home, "SELECT COUNT(*) FROM analytics_daily WHERE source = 'seed'"),
        "seeded audience": _count(demo_home, "SELECT COUNT(*) FROM audience_demographics WHERE source = 'seed'"),
    }
    assert not any(left.values()), f"demo data outlived demo mode: {left}"


def test_what_the_creator_made_during_a_demo_stays(demo_home, monkeypatch):
    from crm import reverse_crm

    real = reverse_crm.ingest_interaction(
        full_name="Real Person", linkedin_urn="https://www.linkedin.com/in/real-person-demo",
        headline="Baker", interaction_type="COMMENT", comment_text="Lovely post.",
    )["lead_id"]
    own_draft = demo_home.create_draft("Words I wrote myself.", title="My own post")
    conn = demo_home.get_db()
    try:
        rewritten = conn.execute("SELECT id FROM drafts ORDER BY id LIMIT 1").fetchone()[0]
        conn.execute("UPDATE drafts SET raw_content = raw_content || ' My edit.' WHERE id = ?", (rewritten,))
        conn.commit()
    finally:
        conn.close()

    _restart_without_the_flag(monkeypatch, demo_home)

    assert _count(demo_home, "SELECT COUNT(*) FROM leads WHERE id = ?", (real,)) == 1
    assert _count(demo_home, "SELECT COUNT(*) FROM drafts WHERE id = ?", (rewritten,)) == 1, (
        "a seeded draft the creator rewrote is theirs now and must not be purged"
    )
    assert _count(demo_home, "SELECT COUNT(*) FROM drafts WHERE id = ?", (own_draft,)) == 1


def test_the_sample_people_say_they_are_samples(demo_home):
    conn = demo_home.get_db()
    try:
        notes = [r[0] for r in conn.execute(
            f"SELECT notes FROM leads WHERE id IN ({','.join('?' * 4)})", _demo_lead_ids(demo_home))]
    finally:
        conn.close()
    assert notes and all("sample" in (n or "").lower() for n in notes), notes


def test_the_sample_people_agree_with_the_funnel(demo_home):
    """status and lead_status were written apart, so a booked meeting read as 0% conversion."""
    from leads import LEAD_STATUS_TO_PIPELINE

    conn = demo_home.get_db()
    try:
        rows = conn.execute(
            f"SELECT status, lead_status FROM leads WHERE id IN ({','.join('?' * 4)})", _demo_lead_ids(demo_home)
        ).fetchall()
    finally:
        conn.close()
    assert all(LEAD_STATUS_TO_PIPELINE[r["status"]] == r["lead_status"] for r in rows), [tuple(r) for r in rows]
