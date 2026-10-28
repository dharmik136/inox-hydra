"""
From your record, phase 2 (release 2.10.0): the enhancer made better.
=====================================================================

Five items, each from track 7's own "not done" list:

  1  cards from what the archive brought that no card used: the companies and
     people the creator follows, the polls they voted in and their own
     articles, each as the creator's own activity, matched to their recurring
     topics, with the rows it came from and its "because" sentence
  2  a Today block: the day's cards, one line each, linking into the section,
     drawn only when today's batch exists and never computed on Today's load
  3  topic diversity across the day's slots, as a rule in the daily job
  4  a Health block for the daily job: when it last ran, whether it carried
     forward, the model stage's spend against the ceiling, and the library's
     signature state
  5  the weekly summary: counts the marks support, said on the Monday card,
     abstaining in words when there are none

The data here is invented: no real person, post or figure.
"""

import io
import json
import os
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
UI = os.path.join(REPO_ROOT, "studio", "ui", "src")
sys.path.insert(0, BACKEND)

# No post was published on this date in an earlier year, so slot 2 is drawn.
DAY = date(2026, 10, 28)          # a Wednesday
MONDAY = date(2026, 10, 26)
SEEDS = range(60)

POSTS = [
    ("Hiring loops that respect candidates take longer to design than to run.", "2025-01-06T09:00:00+00:00"),
    ("Three things I learned hiring our first five engineers without help.", "2025-02-03T09:00:00+00:00"),
    ("We changed our hiring rubric and the offers got better, not slower.", "2025-03-03T09:00:00+00:00"),
    ("Hiring for judgement beats hiring for a checklist of tools.", "2025-04-07T09:00:00+00:00"),
    ("Pricing is a design decision. Most teams treat it as a spreadsheet.", "2025-05-05T09:00:00+00:00"),
    ("Pricing pages lie less when the founder writes them herself.", "2025-06-02T09:00:00+00:00"),
    ("Raising our pricing lost two customers and kept the good ones.", "2025-07-07T09:00:00+00:00"),
    ("Annual pricing with a monthly exit made renewals boring, in a good way.", "2025-08-04T09:00:00+00:00"),
    ("Onboarding is the product for the first week, whatever the roadmap says.", "2025-09-01T09:00:00+00:00"),
    ("Our onboarding checklist got shorter every time a customer finished it.", "2025-09-29T09:00:00+00:00"),
]


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path / "studio"))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    import results
    from database import get_db, init_db

    results.forget_cache()
    init_db()
    connection = get_db()
    yield connection
    connection.close()


def urn(n):
    return f"urn:li:activity:74100000000000{n:05d}"


def add_posts(conn, posts=POSTS):
    for n, (text, published) in enumerate(posts):
        conn.execute(
            "INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, first_seen_at, last_seen_at) "
            "VALUES (?, ?, ?, 'archive', ?, ?)", (urn(n), text, published, published, published))
    conn.commit()


def add_record(conn, kind, url=None, title=None, name=None, detail=None, when="2026-03-04T10:00:00+00:00"):
    cursor = conn.execute(
        "INSERT INTO archive_records (kind, url, title, name, detail, happened_at, dedupe_key, source_file, imported_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (kind, url, title, name, detail, when, f"{kind}-{url}-{title}-{name}-{detail}", f"{kind}.csv",
         "2026-10-20T08:00:00+00:00"))
    conn.commit()
    return cursor.lastrowid


def add_comment(conn, my_text, days_ago=5):
    when = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    conn.execute(
        "INSERT INTO outbound_engagements (target_activity_urn, target_author, target_excerpt, kind, reaction_kind, "
        "my_text, my_text_key, first_seen_at, last_seen_at) VALUES (?, 'Another Person', 'Their words.', 'comment', "
        "NULL, ?, ?, ?, ?)", (f"urn:li:activity:73900000000000{days_ago:05d}", my_text, my_text[:20], when, when))
    conn.commit()


def slot(batch, number):
    return next((c for c in batch["cards"] if c["slot"] == number), None)


# ---------------------------------------------------------------------------
# 1. Cards from follows, votes and articles
# ---------------------------------------------------------------------------

def test_an_article_of_yours_on_a_recurring_topic_can_be_working_for_you(conn):
    import record_cards

    add_posts(conn)
    hiring = add_record(conn, "article", url="https://www.linkedin.com/pulse/hiring-without-a-recruiter-example/",
                        title="Hiring without a recruiter, a year on", when="2025-11-10T08:00:00+00:00")
    add_record(conn, "article", url="https://www.linkedin.com/pulse/a-note-on-gardening-example/",
               title="A note on gardening", when="2025-12-01T08:00:00+00:00")
    seen = {}
    for seed in SEEDS:
        card = slot(record_cards.compute_local(conn, DAY, seed), 2)
        seen.setdefault(card["kind"], []).append(card)
    assert "article" in seen and "opener" in seen, sorted(seen)
    for card in seen["article"]:
        assert card["label"] == "typed" and card["block"] == "working_for_you"
        assert card["provenance"]["source_rows"] == [{"table": "archive_records", "id": hiring}]
        payload = card["payload"]
        assert payload["excerpt"] == "Hiring without a recruiter, a year on"
        assert payload["url"].startswith("https://www.linkedin.com/pulse/hiring")
        assert payload["because"].startswith("Because you published this article on 10 November 2025")
        assert payload["topic"].casefold() == "hiring" and payload["topic"] in payload["because"]
    # An article that goes under none of the creator's topics is never drawn.
    assert not any("gardening" in json.dumps(c) for cards in seen.values() for c in cards)


def test_a_poll_you_voted_in_and_an_account_you_follow_can_be_you_engaged_with(conn):
    import record_cards

    add_posts(conn)
    add_comment(conn, "We did the same with our onboarding checklist and it took a quarter.")
    vote = add_record(conn, "vote", url="https://www.linkedin.com/feed/update/urn:li:activity:7360000000000000009/",
                      detail="Pricing by the value it brings", when="2026-09-02T12:00:00+00:00")
    add_record(conn, "vote", url="https://www.linkedin.com/feed/update/urn:li:activity:7360000000000000010/",
               detail="Cats, obviously")
    company = add_record(conn, "company_follow", name="Hiring Guild", when="2025-01-15T10:00:00+00:00")
    add_record(conn, "member_follow", name="Jordan Example", detail="Active")
    seen = {}
    for seed in SEEDS:
        card = slot(record_cards.compute_local(conn, DAY, seed), 4)
        seen.setdefault(card["kind"], []).append(card)
    assert {"comment", "vote", "follow"} <= set(seen), sorted(seen)
    for card in seen["vote"]:
        assert card["provenance"]["source_rows"] == [{"table": "archive_records", "id": vote}]
        assert card["label"] == "typed" and card["block"] == "you_engaged_with"
        text = json.dumps(card)
        # The option was written by whoever made the poll: the card says the topic, never the words.
        assert "Pricing by the value" not in text and "value it brings" not in text
        assert card["payload"]["because"].startswith("Because you voted in this poll on 2 September 2026")
        assert card["payload"]["url"].endswith("7360000000000000009/")
    for card in seen["follow"]:
        assert card["provenance"]["source_rows"] == [{"table": "archive_records", "id": company}]
        assert "Hiring Guild" in card["payload"]["title"]
        assert card["payload"]["because"].startswith("Because you follow Hiring Guild, since 15 January 2025")
    everything = json.dumps(seen)
    assert "Cats, obviously" not in everything and "Jordan Example" not in everything


def test_without_a_comment_the_other_activity_still_fills_the_slot(conn):
    import record_cards

    add_posts(conn)
    add_record(conn, "vote", url="https://www.linkedin.com/feed/update/urn:li:activity:7360000000000000011/",
               detail="Onboarding first")
    kinds = {slot(record_cards.compute_local(conn, DAY, seed), 4)["kind"] for seed in SEEDS}
    assert kinds == {"vote"}, kinds
