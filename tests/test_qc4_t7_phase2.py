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


# ---------------------------------------------------------------------------
# 3. Topic diversity across the day's slots
# ---------------------------------------------------------------------------
#
# Four recurring topics, each with posts, an ask and a comment: every drawn
# slot has a card on a topic no earlier card of the day shows, so the four
# local cards are four topics, whatever the seed. Without the rule the draws
# are independent and repeat (falsified by switching it off: see the record).

FOUR_TOPICS = [
    ("Hiring loops that respect candidates take longer to design than to run.", "2025-01-06T09:00:00+00:00"),
    ("Three things I learned hiring our first five engineers without help.", "2025-02-03T09:00:00+00:00"),
    ("We changed our hiring rubric and the offers got better, not slower.", "2025-03-03T09:00:00+00:00"),
    ("Pricing is a design decision. Most teams treat it as a spreadsheet.", "2025-05-05T09:00:00+00:00"),
    ("Pricing pages lie less when the founder writes them herself.", "2025-06-02T09:00:00+00:00"),
    ("Raising our pricing lost two customers and kept the good ones.", "2025-07-07T09:00:00+00:00"),
    ("Onboarding is the product for the first week, whatever the roadmap says.", "2025-09-01T09:00:00+00:00"),
    ("Our onboarding checklist got shorter every time a customer finished it.", "2025-09-29T09:00:00+00:00"),
    ("Writing every morning before the inbox opens changed my week.", "2025-10-06T09:00:00+00:00"),
    ("Writing short paragraphs is a kindness to the reader on a phone.", "2025-11-03T09:00:00+00:00"),
]


def add_ask(conn, text):
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("INSERT INTO asks (text, source, status, created_at, updated_at) VALUES (?, 'ask_box', 'open', ?, ?)",
                 (text, now, now))
    conn.commit()


def add_reading(conn, n, reactions, days_ago=40):
    observed = datetime.now(timezone.utc) - timedelta(days=1)
    published = (datetime.now(timezone.utc) - timedelta(days=days_ago + n)).isoformat()
    conn.execute("UPDATE own_posts SET published_at = ? WHERE activity_urn = ?", (published, urn(n)))
    conn.execute(
        "INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, source, "
        "impressions, reactions, comments, reposts) VALUES (?, ?, ?, ?, 'post_analytics', ?, ?, 2, 0)",
        (urn(n), observed.isoformat(), observed.strftime("%Y-%m-%dT%H"), (days_ago + n - 1) * 24.0, reactions * 40,
         reactions))
    conn.commit()


def four_topic_history(conn):
    add_posts(conn, FOUR_TOPICS)
    # The best post is about hiring; three others make the median.
    for n, reactions in ((0, 90), (3, 20), (6, 15), (8, 10)):
        add_reading(conn, n, reactions)
    for text in ("hiring rubrics for a small team", "pricing pages that say the price",
                 "onboarding emails nobody reads", "writing habits that survive a busy week"):
        add_ask(conn, text)
    for days_ago, text in enumerate(("Our hiring rubric did the same for us.", "Pricing in public is braver than it looks.",
                                     "Onboarding is where we lost most of them too.",
                                     "Writing first thing is the only way it happens for me."), start=2):
        add_comment(conn, text, days_ago=days_ago)


def topics_of_batch(batch):
    return [c["payload"].get("topic") for c in batch["cards"] if 1 <= c["slot"] <= 4 and c["status"] == "shown"]


def test_the_days_cards_are_four_topics_when_four_are_there(conn):
    import record_cards

    four_topic_history(conn)
    for seed in SEEDS:
        batch = record_cards.compute_local(conn, DAY, seed)
        topics = topics_of_batch(batch)
        assert len(topics) == 4 and all(topics), (seed, [(c["slot"], c["kind"], c["payload"].get("topic"))
                                                           for c in batch["cards"]])
        assert len({t.casefold() for t in topics}) == 4, (seed, topics)


def test_a_slot_with_only_a_repeated_topic_still_fills(conn):
    import record_cards

    add_posts(conn, FOUR_TOPICS[:3] + FOUR_TOPICS[3:4] + FOUR_TOPICS[4:5])
    add_ask(conn, "hiring rubrics for a small team")
    add_comment(conn, "Our hiring rubric did the same for us.")
    for seed in range(10):
        batch = record_cards.compute_local(conn, DAY, seed)
        assert slot(batch, 3)["status"] == "shown" and slot(batch, 3)["kind"] == "ask"
        assert slot(batch, 4)["status"] == "shown" and slot(batch, 4)["kind"] == "comment"


def test_the_library_card_takes_a_topic_the_day_has_not_shown(conn):
    import library_bundle

    add_posts(conn, FOUR_TOPICS)
    now = datetime.now(timezone.utc).isoformat()
    for entry_id, title, tags in (("form-hiring", "The hiring note", '["hiring"]'),
                                  ("form-pricing", "The pricing note", '["pricing"]')):
        conn.execute("INSERT INTO library_entries (entry_id, kind, title, text, tags_json, author, bundle_version, "
                     "signed_at, key_id, fetched_at) VALUES (?, 'form', ?, 'Write about [it].', ?, 'Inox Hydra', "
                     "'2026.10.1', '2026-10-26', 'inox-library-2026-10', ?)", (entry_id, title, tags, now))
    conn.commit()
    hiring = next(label for key, label in __import__("evidence_briefing").derive_topic_vocabulary(
        [t for t, _ in FOUR_TOPICS]) if key == "hiring")
    for seed in SEEDS:
        card = library_bundle.match_card(conn, DAY, seed, avoid={hiring})
        assert card is not None and card["provenance"]["source_rows"] == [{"table": "library_entries", "id": "form-pricing"}]


# ---------------------------------------------------------------------------
# 5. The weekly summary: counts the marks support, on the Monday card
# ---------------------------------------------------------------------------

def add_view(conn, day, card_id, kind="opener", status="shown"):
    conn.execute("INSERT INTO daily_view (day, card_id, slot, block, kind, label, method, payload_json, provenance_json, "
                 "status, created_at) VALUES (?, ?, 2, 'working_for_you', ?, 'typed', 'r', '{}', '{}', ?, ?)",
                 (day, card_id, kind, status, day))


def add_mark(conn, day, card_id, mark):
    conn.execute("INSERT INTO card_marks (day, card_id, mark, at) VALUES (?, ?, ?, ?)", (day, card_id, mark, day + "T10:00:00+00:00"))


def test_the_monday_card_counts_last_weeks_cards_and_marks(conn):
    import record_cards

    for n in range(6):
        add_view(conn, f"2026-10-{19 + n:02d}", f"c{n}")
    add_view(conn, "2026-10-19", "monday:2026-W43", kind="monday")       # the Monday line is no card
    add_view(conn, "2026-10-20", "x", status="abstained")                # an abstention is no card shown
    add_view(conn, "2026-10-12", "older")                                # the week before is not last week
    add_view(conn, "2026-10-26", "today")                                # nor is today
    for card_id, mark, day in (("c0", "keep", "2026-10-19"), ("c1", "keep", "2026-10-20"), ("c2", "skip", "2026-10-21"),
                               ("c3", "used", "2026-10-22"), ("c3", "posted", "2026-10-22"),
                               ("older", "keep", "2026-10-12"), ("today", "keep", "2026-10-26")):
        add_mark(conn, day, card_id, mark)
    conn.commit()
    card = record_cards.monday_card(conn, MONDAY)
    week = card["payload"]["record_week"]
    assert {k: week[k] for k in ("shown", "kept", "skipped", "hidden", "drafted", "posted")} == {
        "shown": 6, "kept": 2, "skipped": 1, "hidden": 0, "drafted": 1, "posted": 1}
    assert week["sentence"] == ("From your record last week: 6 cards shown; 2 kept, 1 skipped, none hidden; "
                                "1 drafted from, 1 posted.")
    # Counts, each with the table it was counted from, and nothing compared with anything.
    names = {f["name"]: f for f in card["provenance"]["figures"]}
    assert names["record_cards_shown"]["table"] == "daily_view" and names["record_cards_kept"]["table"] == "card_marks"
    assert "%" not in week["sentence"] and "than" not in week["sentence"]


def test_a_week_without_cards_is_said_not_counted(conn):
    import record_cards

    card = record_cards.monday_card(conn, MONDAY)
    week = card["payload"]["record_week"]
    assert week["shown"] == 0
    assert week["sentence"] == "From your record last week: no cards were shown, so there is no week of them to count."


def test_the_monday_strip_says_the_summary():
    surface = io.open(os.path.join(UI, "components", "RecordSurface.tsx"), encoding="utf-8").read()
    assert "record_week" in surface


# ---------------------------------------------------------------------------
# 4. The daily job on Health
# ---------------------------------------------------------------------------

def run_row(conn, day, carried_from=None, cost=None, dropped=0, status="not_run", note="built from your record"):
    conn.execute("INSERT INTO daily_run (day, input_signature, started_at, finished_at, local_ok, carried_from, seed, "
                 "model_status, estimated_cost_usd, price_date, dropped_cards, note) VALUES (?, 's', ?, ?, 1, ?, 1, ?, ?, "
                 "'2026-10-26', ?, ?)", (day, day + "T06:00:00+00:00", day + "T06:00:01+00:00", carried_from, status,
                                         cost, dropped, note))
    conn.commit()


def test_the_health_read_says_when_the_job_ran_and_whether_it_carried_forward(conn):
    import record_daily
    import record_health

    today = record_daily.local_today().isoformat()
    first = record_health.health()
    assert first["job"]["today_built"] is False and first["job"]["sentence"].startswith("Not built yet")
    run_row(conn, today, carried_from="2026-10-27", dropped=1)
    answer = record_health.health()
    assert answer["job"]["today_built"] is True and answer["job"]["carried_from"] == "2026-10-27"
    assert "carried forward from" in answer["job"]["sentence"] and "1 card failed a check" in answer["job"]["sentence"]


def test_the_health_read_sets_the_spend_against_the_ceiling(conn):
    import record_daily
    import record_health

    today = record_daily.local_today().isoformat()
    assert record_health.health()["model"]["sentence"].startswith("No AI provider is connected")
    for key, value in (("ai_provider", "openai"), ("ai_model", "gpt-5-mini"), ("ai_api_key", "not-a-real-key-for-a-test")):
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    run_row(conn, today, cost=0.0021, status="ran")
    model = record_health.health()["model"]
    assert model["spent_today_usd"] == pytest.approx(0.0021) and model["ceiling_usd"] == pytest.approx(0.10)
    assert model["sentence"].startswith("$0.0021 of the $0.10 daily ceiling spent today")


def test_the_library_signature_state_is_said(conn, monkeypatch):
    import library_bundle
    import record_health

    assert record_health.health()["library"]["state"] == "none"
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("INSERT INTO library_entries (entry_id, kind, title, text, tags_json, author, bundle_version, signed_at, "
                 "key_id, fetched_at) VALUES ('form-a', 'form', 'A form', 'Write it.', '[]', 'Inox Hydra', '2026.10.1', "
                 "'2026-10-26', ?, ?)", (sorted(library_bundle.PUBLIC_KEYS)[0], now))
    conn.commit()
    held = record_health.health()["library"]
    assert held["state"] == "verified" and "a key this studio ships" in held["sentence"]
    monkeypatch.setattr(library_bundle, "PUBLIC_KEYS", {"another-key": "AAAA"})
    gone = record_health.health()["library"]
    assert gone["state"] == "key_not_held" and "would be refused" in gone["sentence"]


def test_health_draws_the_daily_job_block():
    surface = io.open(os.path.join(UI, "components", "HealthSurface.tsx"), encoding="utf-8").read()
    assert "fetchRecordHealth" in surface and 'title="From your record, the daily cards"' in surface
    api = io.open(os.path.join(UI, "lib", "api.ts"), encoding="utf-8").read()
    assert '"/api/v1/record/health"' in api


# ---------------------------------------------------------------------------
# 2. The Today block
# ---------------------------------------------------------------------------

@pytest.fixture
def client(conn):
    from fastapi.testclient import TestClient

    import app as app_module
    return TestClient(app_module.app)


def test_today_has_lines_only_once_todays_batch_exists(conn, client):
    import record_daily

    add_posts(conn)
    add_comment(conn, "We did the same with our onboarding checklist and it took a quarter.")
    today = record_daily.local_today()
    empty = client.get("/api/v1/record/lines").json()
    assert empty == {"day": today.isoformat(), "built": False, "lines": [], "not_yet": 0}
    # Yesterday's batch is not today's: Today draws nothing until today's is built.
    record_daily.run_today(today - timedelta(days=1))
    assert client.get("/api/v1/record/lines").json()["built"] is False
    record_daily.run_today(today)
    answer = client.get("/api/v1/record/lines").json()
    assert answer["built"] is True and answer["lines"]
    shown = {c["card_id"] for c in client.get("/api/v1/record").json()["cards"]
             if c["status"] == "shown" and c["slot"] >= 1}
    assert {line["card_id"] for line in answer["lines"]} == shown
    for line in answer["lines"]:
        assert line["block_label"] and line["title"] and line["slot"] >= 1
    assert [line["slot"] for line in answer["lines"]] == sorted(line["slot"] for line in answer["lines"])


def test_reading_the_lines_builds_nothing(conn, client):
    before = conn.execute("SELECT COUNT(*) FROM daily_run").fetchone()[0]
    for _ in range(3):
        assert client.get("/api/v1/record/lines").status_code == 200
    assert conn.execute("SELECT COUNT(*) FROM daily_run").fetchone()[0] == before == 0
    assert conn.execute("SELECT COUNT(*) FROM daily_view").fetchone()[0] == 0


def test_today_draws_one_block_that_links_into_the_section():
    today = io.open(os.path.join(UI, "components", "TodaySurface.tsx"), encoding="utf-8").read()
    assert today.count("<RecordTodayBlock />") == 1 and 'from "./RecordTodayBlock"' in today
    block = io.open(os.path.join(UI, "components", "RecordTodayBlock.tsx"), encoding="utf-8").read()
    assert 'href="#/record"' in block and "fetchRecordLines" in block
    assert "!lines.built" in block, "the block is drawn before today's batch exists"
    assert '["ideas"]' in block, "the block does not read again when the day's cards are built"


def test_the_dates_slot_takes_turns_so_a_daily_poster_still_sees_openers_and_articles(conn):
    """
    It was the post of the date whenever there was one, so a creator who has
    posted most days for years never saw an opener or an article there. The
    post of the date now comes up twice as often as each of the other two.
    """
    import record_cards

    add_posts(conn, POSTS + [("Pricing a retainer is pricing your attention, not your hours.", "2024-10-28T09:00:00+00:00")])
    add_record(conn, "article", url="https://www.linkedin.com/pulse/hiring-without-a-recruiter-example/",
               title="Hiring without a recruiter, a year on", when="2025-11-10T08:00:00+00:00")
    kinds = [slot(record_cards.compute_local(conn, DAY, seed), 2)["kind"] for seed in SEEDS]
    counts = {kind: kinds.count(kind) for kind in set(kinds)}
    assert set(counts) == {"on_this_day", "opener", "article"}, counts
    assert counts["on_this_day"] > counts["opener"] and counts["on_this_day"] > counts["article"], counts
