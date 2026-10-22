"""
A Fold Keeps Every Number a Screen Shows.
=========================================
DATA-06, from review R4. Folding reactions older than 24 months kept the
per-post totals in reaction_folds, which nothing read, and kept nothing per
person, so after confirming the fold the Leads review, lead timelines and
every per-post or per-person count dropped (one post went from 221 people
to 54). A fold now keeps, per post, how many reacted and how many of those
engaged with that post in no other way, and per person how many old
reactions they made and on whose posts, and retention.folded_counts() is
the one helper every reader adds. Kept here: the Leads review counts, the
lead timeline, the silent-lead review, and the helper's arithmetic against
what the rows said before the fold. Posts, Analytics and Patterns read the
same helper in batch R3's summary.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from studio.backend import database, migrations, onboarding, paths, retention  # noqa: E402

NOW = datetime.now(timezone.utc)
OLD = NOW - timedelta(days=900)
OWN = [f"urn:li:activity:{7100000000000000000 + i}" for i in range(3)]
ELSEWHERE = "urn:li:activity:7000000000000000009"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    database.init_db()
    _build()
    return tmp_path


def _t(moment):
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def _build():
    conn = sqlite3.connect(paths.get_db_path())
    for urn in OWN:
        conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, first_seen_at, last_seen_at) "
                     "VALUES (?, 'p', ?, ?, ?)", (urn, OLD.isoformat(), OLD.isoformat(), OLD.isoformat()))

    def add(lead, kind, post, when, text=None):
        conn.execute(
            "INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, comment_text, interacted_at, "
            "comment_key, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (lead, post, kind, text, _t(when), migrations.interaction_comment_key(text), _t(when), _t(when)))

    for i in range(12):
        lead = f"lead-{i}"
        conn.execute("INSERT INTO leads (id, name, full_name, lead_status, created_at, updated_at) "
                     "VALUES (?, ?, ?, 'NEW', ?, ?)", (lead, f"P{i}", f"P{i}", _t(OLD), _t(OLD)))
        add(lead, "LIKE", OWN[i % 3], OLD)                     # every one an old reaction
        if i % 3 == 0:
            add(lead, "COMMENT", OWN[i % 3], OLD, f"said {i}")  # some also commented there
        if i % 4 == 0:
            add(lead, "LIKE", OWN[(i + 1) % 3], NOW - timedelta(days=5))  # some recently, elsewhere
        if i == 11:
            add(lead, "LIKE", ELSEWHERE, OLD)                  # one also on someone else's post
        if i == 7:
            add(lead, "LIKE", OWN[2], OLD)                     # two old reactions, two posts
    # Tiers and a conversation among the people whose reactions are folded.
    conn.execute("UPDATE leads SET icp_score = 85, lead_status = 'ENGAGED' WHERE id = 'lead-2'")
    conn.execute("UPDATE leads SET icp_score = 65 WHERE id IN ('lead-5', 'lead-7')")
    conn.execute("UPDATE leads SET icp_score = 90 WHERE id = 'lead-3'")
    # These tiers are the fixture's subject, so they stand as though the
    # engine had written them: since batch T2 a score carries a mark saying it
    # needs recomputing, and inserting a lead sets it, so the mark is cleared
    # here. A reaction alone cannot reach the VIP cut through the engine,
    # which is a finding of its own and not what this file tests.
    conn.execute("UPDATE leads SET icp_stale = 0")
    conn.commit()
    conn.close()


def _rows():
    conn = sqlite3.connect(paths.get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM lead_interactions")]
    finally:
        conn.close()


def _views():
    """
    What the screens count, read as batch R3's summary and Patterns read
    them: from live rows plus the one helper. Before a fold the helper is
    empty, so this is the plain count.
    """
    folds = retention.folded_counts()
    conn = sqlite3.connect(paths.get_db_path())
    conn.row_factory = sqlite3.Row
    leads = {r["id"]: dict(r) for r in conn.execute("SELECT id, icp_score, lead_status FROM leads")}
    pairs = {(r["post_urn"], r["lead_id"]) for r in conn.execute("SELECT post_urn, lead_id FROM lead_interactions")}
    likes, per_lead = {}, {}
    for r in conn.execute("SELECT post_urn, lead_id, interaction_type FROM lead_interactions"):
        if r["interaction_type"] == "LIKE":
            likes[r["post_urn"]] = likes.get(r["post_urn"], 0) + 1
        per_lead[r["lead_id"]] = per_lead.get(r["lead_id"], 0) + 1
    topic_of = retention._topic_of_posts(conn)
    conn.close()

    posts = {}
    for urn, lead in pairs:
        p = posts.setdefault(urn, {"people": 0, "vip": 0, "qualified": 0, "icp_known": 0, "icp_sum": 0.0,
                                   "conversations": 0})
        icp, status = leads[lead]["icp_score"], leads[lead]["lead_status"]
        p["people"] += 1
        if icp is not None:
            p["icp_known"] += 1
            p["icp_sum"] += icp
            p["vip"] += icp >= 80
            p["qualified"] += icp >= 60
        p["conversations"] += (status or "") in ("ENGAGED", "CONVERTED")
    for urn, fold in folds["by_post"].items():
        p = posts.setdefault(urn, {"people": 0, "vip": 0, "qualified": 0, "icp_known": 0, "icp_sum": 0.0,
                                   "conversations": 0})
        for key in p:
            p[key] += fold[key]
        likes[urn] = likes.get(urn, 0) + fold["reactions"]
    for lead, fold in folds["by_lead"].items():
        per_lead[lead] = per_lead.get(lead, 0) + fold["reactions"]

    topics = {}
    for urn, lead in pairs:
        if urn in topic_of:
            topics.setdefault(topic_of[urn], set()).add(lead)
    for lead, fold in folds["by_lead"].items():
        for topic in fold["topics"]:
            topics.setdefault(topic, set()).add(lead)
    qualified = {lead for lead, row in leads.items()
                 if (row["icp_score"] or 0) >= 60 or (row["lead_status"] or "") in ("ENGAGED", "CONVERTED")}
    return {"posts": posts, "post_reactions": likes, "per_lead": per_lead,
            "people_engaged": len(set(per_lead)),
            "topics": {t: (len(ids), len(ids & qualified)) for t, ids in topics.items()}}


def _timeline_totals():
    from fastapi.testclient import TestClient
    from studio.backend.app import app

    client = TestClient(app)
    totals = {}
    for i in range(12):
        body = client.get(f"/api/v1/crm/leads/lead-{i}/timeline").json()
        folded = body.get("folded_reactions") or {}
        totals[f"lead-{i}"] = (len(body["interactions"]) + (folded.get("count") or 0), body["lead"]["scored"])
    return totals


def test_every_count_is_the_same_after_the_fold(home):
    before_views = _views()
    before_review = onboarding.lead_review()
    before_timelines = _timeline_totals()

    assert retention.run("reactions")["removed"] == 14

    assert _views() == before_views
    after_review = onboarding.lead_review()
    assert after_review["counts"] == before_review["counts"], "the Leads review counted people differently"
    assert after_review["not_yours"] == before_review["not_yours"]
    assert _timeline_totals() == before_timelines, "a lead timeline lost engagements"


def test_the_folded_counts_say_on_whose_posts(home):
    retention.run("reactions")
    folds = retention.folded_counts()
    assert folds["by_lead"]["lead-11"]["reactions"] == 2
    assert folds["by_lead"]["lead-11"]["yours"] == 1
    assert folds["by_lead"]["lead-11"]["not_yours"] + folds["by_lead"]["lead-11"]["unknown"] == 1
    assert sum(f["reactions"] for f in folds["by_post"].values()) == 14
    # lead-0, lead-3, lead-6 and lead-9 also commented on the post they reacted to.
    assert sum(f["people"] for f in folds["by_post"].values()) == 14 - 4
    # lead-2 (85, in conversation) and lead-5 and lead-7 (65) reacted only; lead-3 (90) also commented.
    assert sum(f["vip"] for f in folds["by_post"].values()) == 1
    assert sum(f["qualified"] for f in folds["by_post"].values()) == 4
    assert sum(f["conversations"] for f in folds["by_post"].values()) == 1
    assert folds["by_lead"]["lead-7"]["reactions"] == 2 and folds["by_lead"]["lead-7"]["topics"]


def test_the_silent_lead_review_still_counts_folded_reactions(home):
    before = {lead["id"]: lead["interactions"] for lead in retention.review_list()["leads"]}
    retention.run("reactions")
    after = {lead["id"]: lead["interactions"] for lead in retention.review_list()["leads"]}
    assert after == before


def test_forgetting_a_person_removes_their_folded_counts(home):
    retention.run("reactions")
    from studio.backend.crm import reverse_crm

    reverse_crm.purge_lead("lead-5")
    assert "lead-5" not in retention.folded_counts()["by_lead"]


def test_the_lead_review_switch_can_be_turned_back(home):
    retention.set_rules({"lead_review": "off"})
    assert retention.set_rules({"lead_review": "ask"})["lead_review"] == "ask"


def test_the_fold_confirmation_says_exactly_what_is_kept_and_lost():
    source = open(os.path.join(os.path.dirname(__file__), "..", "studio", "ui", "src", "components",
                               "StoragePrivacyWorkspace.tsx"), encoding="utf-8").read()
    assert "how many reacted is kept" not in source
    assert "Kept: how many people reacted to each post" in source
    assert "Lost: which people reacted to which post" in source
    assert "Everyone stays in your leads" in source
