"""
Patterns, topics and outbound count people, and say only what they can support.
==============================================================================

Quality cycle 2026-10, batch F5b.

AUDIENCE-12. Topic attribution added one per interaction, so a founder who
commented and reacted was two qualified leads, three people made "6 qualified
leads" from one post, and "Conversion Rate" (leads divided by posts) read
600%. The copilot's top examples were ordered by that count, and Outbound's
ON YOUR POSTS counted interactions rather than posts.

Each test runs in a throwaway home of its own.
"""

import datetime as dt
import os
import shutil
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc_f5b_patterns_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    import app as app_module
    yield TestClient(app_module.app)
    shutil.rmtree(home, ignore_errors=True)


def _db():
    from database import get_db
    return get_db()


def _urn(when, salt=0):
    return f"urn:li:activity:{(int(when.timestamp() * 1000) << 22) + salt}"


def _post(text, reactions, when=None, salt=0, comments=None):
    """One of the creator's LinkedIn posts, settled (older than a week) unless `when` says otherwise."""
    when = when or dt.datetime(2026, 8, 1, 9, tzinfo=dt.timezone.utc) + dt.timedelta(days=salt)
    urn = _urn(when, salt)
    conn = _db()
    with conn:
        conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, reactions, comments, "
                     "first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, '2026-10-01', '2026-10-01')",
                     (urn, text, when.isoformat(), reactions, comments))
    conn.close()
    return urn


def _engaged(lead_id, name, urn, *kinds, score=80.0):
    conn = _db()
    with conn:
        conn.execute("INSERT OR IGNORE INTO leads (id, name, full_name, icp_score) VALUES (?, ?, ?, ?)",
                     (lead_id, name, name, score))
        for kind in kinds:
            conn.execute("INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, comment_text) "
                         "VALUES (?, ?, ?, ?)", (lead_id, urn, kind, "A real question?" if kind == "COMMENT" else None))
    conn.close()


def _get(client, path):
    res = client.get(path)
    assert res.status_code == 200, res.text
    return res.json()


# ---------------------------------------------------------------------------
# AUDIENCE-12
# ---------------------------------------------------------------------------

def test_a_person_who_commented_and_reacted_is_one_qualified_person(studio):
    urn = _post("Why we moved our database to Postgres", 50)
    for k in range(3):
        _engaged(f"lead-founder-{k}", f"Founder {k}", urn, "COMMENT", "LIKE")
    topics = _get(studio, "/api/v1/insights/attribution")["topics"]
    topic = next(t for t in topics if t["posts_count"] == 1)
    assert topic["qualified_leads"] == 3, "each interaction was counted as a qualified lead"
    assert topic["people_engaged"] == 3


def test_one_person_on_two_posts_of_a_topic_is_counted_once_for_it(studio):
    first = _post("Sourdough starter notes", 40, salt=1)
    second = _post("Sourdough proofing times", 45, salt=2)
    _engaged("lead-asha", "Asha Rao", first, "COMMENT")
    _engaged("lead-asha", "Asha Rao", second, "LIKE")
    topics = _get(studio, "/api/v1/insights/attribution")["topics"]
    assert sum(t["qualified_leads"] for t in topics) == 1, topics


def test_no_rate_exceeds_its_definition(studio):
    urn = _post("Why we moved our database to Postgres", 50)
    for k in range(3):
        _engaged(f"lead-founder-{k}", f"Founder {k}", urn, "COMMENT", "LIKE")
    _engaged("lead-student", "A Student", urn, "LIKE", score=10.0)
    for t in _get(studio, "/api/v1/insights/attribution")["topics"]:
        rate = t["lead_conversion_rate"]
        assert rate is None or 0 <= rate <= 1, t
    topic = next(t for t in _get(studio, "/api/v1/insights/attribution")["topics"] if t["people_engaged"])
    assert topic["lead_conversion_rate"] == 0.75, "three of the four people captured are qualified"


def test_a_topic_nobody_was_captured_on_has_no_rate(studio):
    _post("A post nobody has been captured on", 10)
    topic = _get(studio, "/api/v1/insights/attribution")["topics"][0]
    assert topic["people_engaged"] == 0 and topic["lead_conversion_rate"] is None


def test_the_copilot_examples_are_the_best_received_posts(studio):
    quiet = _post("Why we moved our database to Postgres", 50, salt=1)
    for k in range(3):
        _engaged(f"lead-founder-{k}", f"Founder {k}", quiet, "COMMENT", "LIKE")
    for i in range(3):
        _post(f"Weekly notes {i}", 300 + i, salt=10 + i)
    brief = _get(studio, "/api/v1/insights/evidence")
    assert [p["reactions"] for p in brief["top_exemplars"]] == [302, 301, 300], brief["top_exemplars"]
    assert "6 qualified" not in brief["brief_section"]
    by_urn = {p["activity_urn"]: p for p in brief["top_exemplars"] + brief["bottom_exemplars"]}
    assert by_urn[quiet]["qualified_leads"] == 3


def test_on_your_posts_counts_posts_not_interactions(studio):
    urn = _post("Why we moved our database to Postgres", 50)
    _engaged("lead-founder-0", "Founder 0", urn, "COMMENT", "LIKE")
    conn = _db()
    with conn:
        conn.execute("INSERT INTO outbound_engagements (target_activity_urn, target_author, kind, my_text_key, "
                     "first_seen_at, last_seen_at) VALUES ('urn:li:activity:7370000000000000001', 'Founder 0', "
                     "'reaction', '', '2026-10-01', '2026-10-01')")
    conn.close()
    authors = _get(studio, "/api/v1/insights/outbound")["authors"]
    assert authors[0]["name"] == "Founder 0"
    assert authors[0]["engaged_back"] == 1, "one comment and one like on one post were counted as two posts"


# ---------------------------------------------------------------------------
# AUDIENCE-13: a comparison flagged as mixed up with when you posted is never
# called conclusive, on screen or to the copilot
# ---------------------------------------------------------------------------

def _hashtags_then_plain():
    """Nine hashtag posts from 2024 at about 300 reactions, ten plain ones from 2026 at about 100."""
    for i in range(9):
        _post(f"Weekly notes {i}\nSome thoughts #leadership #growthmindset", 300 + i,
              when=dt.datetime(2024, 3, 1 + i * 3, 9, tzinfo=dt.timezone.utc), salt=i)
    for i in range(10):
        _post(f"Field notes {i}\nSome thoughts without tags", 100 + i,
              when=dt.datetime(2026, 8, 1 + i * 3, 9, tzinfo=dt.timezone.utc), salt=100 + i)


def test_patterns_and_contrasts_agree_about_a_period_split(studio):
    _hashtags_then_plain()
    pattern = next(p for p in _get(studio, "/api/v1/insights/patterns")["patterns"] if p["key"] == "hashtags")
    assert pattern["different_period"] is True
    contrast = next(c for c in _get(studio, "/api/v1/insights/contrasts")["contrasts"] if c["key"] == "hashtags")
    assert contrast["status"] != "conclusive", "the same split was mixed up with time above and conclusive below"
    assert contrast["status"] == "different_period"
    assert (contrast["typical_year_with"], contrast["typical_year_without"]) == (2024, 2026)
    assert contrast["planted_or_significant"] is False


def test_the_copilot_is_not_told_a_period_split_is_a_finding(studio):
    _hashtags_then_plain()
    brief = _get(studio, "/api/v1/insights/evidence")
    assert "hashtags" not in brief["brief_section"].lower(), brief["brief_section"]
    assert all(c["key"] != "hashtags" for c in brief["contrast_findings"])


def test_a_split_within_one_period_is_still_compared(studio):
    for i in range(9):
        _post(f"Weekly notes {i}\nSome thoughts #leadership", 300 + i,
              when=dt.datetime(2026, 3, 1 + i * 3, 9, tzinfo=dt.timezone.utc), salt=i)
    for i in range(10):
        _post(f"Field notes {i}\nSome thoughts without tags", 100 + i,
              when=dt.datetime(2026, 3, 2 + i * 3, 9, tzinfo=dt.timezone.utc), salt=100 + i)
    contrast = next(c for c in _get(studio, "/api/v1/insights/contrasts")["contrasts"] if c["key"] == "hashtags")
    assert contrast["status"] == "conclusive" and contrast["planted_or_significant"] is True


# ---------------------------------------------------------------------------
# AUDIENCE-27: topics come from the creator's own posts, not from the
# original author's software vocabulary
# ---------------------------------------------------------------------------

BAKERY = [
    "Why sourdough needs patience\nHere is what I learned.",
    "5 lessons from our bakery launch #smallbusiness",
    "Are you pricing your croissants right?\nA thread.",
    "Excited to share our new shop opening!",
    "Short one today.",
    "How we cut flour waste by 30 percent",
    "\U0001f950 Croissant Friday recap",
    "What nobody tells you about early mornings",
    "Our café in Zürich: first month numbers",
    "Hiring: pastry chef in Ahmedabad",
    "On saying no to wholesale",
    "Why I write every morning",
]
OLD_VOCABULARY = {"Product & Strategy", "Architecture & Systems", "AI & Machine Learning", "Leadership & Hiring",
                  "Practitioner Insights", "General Practitioner"}


def test_a_bakery_is_not_sorted_into_software_topics(studio):
    for i, text in enumerate(BAKERY):
        _post(text, 40 + i * 7, salt=i)
    body = _get(studio, "/api/v1/insights/attribution")
    names = {t["topic"] for t in body["topics"]}
    assert not names & OLD_VOCABULARY, names
    assert {"Croissant", "Morning"} <= names, names
    by_name = {t["topic"]: t["posts_count"] for t in body["topics"]}
    assert by_name["Croissant"] == 2 and by_name["Morning"] == 2
    assert "own posts" in body["grouping"], "the screen cannot say how the topics were made"


def test_a_hashtag_the_creator_uses_is_a_topic(studio):
    for i in range(4):
        _post(f"Notes from week {i} #sourdough", 10 + i, salt=i)
    for i in range(4):
        _post(f"Shop floor diary {i}", 10 + i, salt=10 + i)
    names = {t["topic"]: t["posts_count"] for t in _get(studio, "/api/v1/insights/attribution")["topics"]}
    assert names.get("Sourdough") == 4, names


def test_the_obsidian_topics_follow_the_same_grouping():
    from evidence_briefing import classify_post_topic, derive_topic_vocabulary
    vocabulary = derive_topic_vocabulary(BAKERY)
    assert classify_post_topic("Croissant Friday, part two", vocabulary) == "Croissant"
    assert classify_post_topic("Something else entirely", vocabulary) == "Other posts"
    assert classify_post_topic(None, vocabulary) == "Other posts"


# ---------------------------------------------------------------------------
# SETUP-23: posts from the archive have no figures, and the screens say that,
# not that the posts are too young
# ---------------------------------------------------------------------------

def _archive_posts(n):
    conn = _db()
    with conn:
        for i in range(n):
            when = dt.datetime(2021, 2, 4, 9, tzinfo=dt.timezone.utc) + dt.timedelta(days=i)
            conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, "
                         "first_seen_at, last_seen_at) VALUES (?, ?, ?, 'archive', '2026-10-01', '2026-10-01')",
                         (_urn(when, i), f"Synthetic sample post {i}", when.isoformat()))
    conn.close()


def test_patterns_count_the_posts_left_out_for_having_no_figures(studio):
    _archive_posts(30)
    patterns = _get(studio, "/api/v1/insights/patterns")
    assert patterns["posts_compared"] == 0
    assert patterns["settled_without_reactions"] == 30, "the screen can only blame the posts' age"
    assert patterns["settled_without_reactions_from_archive"] == 30


def test_posts_count_the_settled_posts_with_no_figures(studio):
    _archive_posts(30)
    _post("A post the bridge read", 40)
    overview = _get(studio, "/api/v1/insights/posts")
    assert overview["usual"]["reactions"]["median"] is None
    assert overview["settled_without_figures"] == 30
    assert overview["settled_without_figures_from_archive"] == 30
