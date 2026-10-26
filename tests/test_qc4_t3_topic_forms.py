"""
A topic is a form, compared by the contrast engine.
===================================================

Patterns drew a "Topic to Qualified Lead Attribution" table: qualified
people per topic, a share qualified, ordered by qualified leads. A lead's
tier is a keyword guess about a job title, the reactions summed a snapshot
column, and on one creator the gap between topics was 0.26 percentage points
against 27 within one topic, so the table ranked noise. Cycle 4's decision 7
retires the qualified framing and keeps topic "as a form through the
engine": the settled posts that mention a topic's word against those that do
not, by median reactions, with the engine's abstention, its "none" and its
period guard. The funnel goes to Audience as counts (track 4).
"""

import datetime as dt
import os
import shutil
import statistics
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

SURFACE = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "PatternsSurface.tsx")
API = os.path.join(REPO_ROOT, "studio", "ui", "src", "lib", "api.ts")

SETTLED = dt.datetime(2026, 8, 1, 9, tzinfo=dt.timezone.utc)


def _urn(when, salt):
    return f"urn:li:activity:{(int(when.timestamp() * 1000) << 22) + salt}"


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t3_topics_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    init_db()
    posts = []
    for n in range(10):
        posts.append((f"Croissant notes {n}.\n\nThe crumb.", 100 + n, SETTLED + dt.timedelta(days=n), n))
        posts.append((f"Sourdough notes {n}.\n\nThe crumb.", 20 + n, SETTLED + dt.timedelta(days=n, hours=1), 100 + n))
    for n in range(3):
        posts.append((f"Baguette notes {n}.\n\nThe crumb.", 50, SETTLED + dt.timedelta(days=n, hours=2), 200 + n))
    # Three hours old: too young to judge, so on neither side of any form.
    young = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3)
    posts.append(("Croissant notes, this morning.\n\nThe crumb.", 900, young, 300))
    conn = get_db()
    with conn:
        for text, reactions, when, salt in posts:
            conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, reactions, first_seen_at, last_seen_at) "
                         "VALUES (?, ?, ?, ?, '2026-10-01', '2026-10-01')", (_urn(when, salt), text, when.isoformat(), reactions))
    conn.close()
    import app as app_module
    from fastapi.testclient import TestClient
    yield TestClient(app_module.app)
    shutil.rmtree(home, ignore_errors=True)


def _topics(client):
    answer = client.get("/api/v1/insights/contrasts")
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert "contrasts" in body, "the seven forms left the payload"
    return {topic["key"]: topic for topic in body["topics"]}


def test_a_topic_is_compared_like_a_form(studio):
    topics = _topics(studio)
    croissant = topics["topic:croissant"]
    assert croissant["label"] == 'Mentions "Croissant"'
    assert croissant["status"] == "conclusive"
    assert (croissant["n_with"], croissant["n_without"]) == (10, 13), "the young post was counted, or a side is wrong"
    with_it = [100 + n for n in range(10)]
    without = [20 + n for n in range(10)] + [50, 50, 50]
    assert croissant["median_with"] == statistics.median(with_it)
    assert croissant["median_without"] == statistics.median(without)
    assert croissant["ratio"] == round(statistics.median(with_it) / statistics.median(without), 2)
    assert croissant["difference"]["verdict"] == "more"
    assert topics["topic:sourdough"]["difference"]["verdict"] == "fewer"


def test_a_topic_below_the_engines_minimum_is_an_abstention(studio):
    import results
    baguette = _topics(studio)["topic:baguette"]
    assert baguette["status"] == "not_enough_data"
    assert (baguette["n_with"], baguette["min_required"]) == (3, results.MIN_PER_SIDE)
    assert "ratio" not in baguette and "median_with" not in baguette, "an abstention carried a figure"


def test_topic_forms_go_through_the_engines_evaluator(studio, monkeypatch):
    import evidence_briefing
    seen = []
    real = evidence_briefing.evaluate_feature

    def spy(posts, key, label, has):
        seen.append(key)
        return real(posts, key, label, has)

    monkeypatch.setattr(evidence_briefing, "evaluate_feature", spy)
    topics = evidence_briefing.topic_forms()
    assert seen and seen == [topic["key"] for topic in topics], "a topic was compared outside the engine"


def test_the_screen_retires_the_qualified_framing():
    with open(SURFACE, encoding="utf-8") as handle:
        surface = handle.read()
    code = "\n".join(line for line in surface.splitlines() if not line.strip().startswith(("//", "*", "{/*")))
    for retired in ("fetchTopicAttribution", "Topic to Qualified Lead Attribution", "Which topics bring qualified pipeline",
                    "Share qualified", "qualified_leads"):
        assert retired not in code, f"Patterns still carries {retired!r}"
    assert "contrasts?.topics" in surface, "Patterns does not draw the topics from the engine's records"
    with open(API, encoding="utf-8") as handle:
        assert "fetchTopicAttribution" not in handle.read(), "the interface still has a reader for the retired table"
