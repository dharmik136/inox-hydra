"""
Stage 1 of From your record: the daily cards from the creator's own rows.
=========================================================================

Cycle 4, track 7, batch 3 of the personalised daily ideas report. The local
stage needs no key, sends nothing, and on day 0 with an archive imported
already shows the creator's recurring words, an on-this-day post, a post
they commented on in their own words and what they asked; "what worked"
abstains in words until results.py's minimums are met, and when they are it
is results.best's answer and nobody else's.

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
sys.path.insert(0, BACKEND)

DAY = date(2026, 10, 26)          # a Monday
TUESDAY = date(2026, 10, 27)

POSTS = [
    ("Hiring is a product problem, not a recruiting problem. Here is what changed for us.", "2024-10-26T09:00:00+00:00"),
    ("Three things I learned hiring our first five engineers without a recruiter.", "2025-03-02T09:00:00+00:00"),
    ("Pricing is a design decision. Most teams treat it as a spreadsheet.", "2025-04-11T09:00:00+00:00"),
    ("We changed our hiring loop and the offers got better, not slower.", "2025-06-20T09:00:00+00:00"),
    ("Pricing pages lie less when the founder writes them herself.", "2025-08-01T09:00:00+00:00"),
    ("A short note on writing every morning before the inbox opens.", "2025-09-12T09:00:00+00:00"),
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
    return f"urn:li:activity:74000000000000{n:05d}"


def add_posts(conn, posts=POSTS, source="archive"):
    for n, (text, published) in enumerate(posts):
        conn.execute(
            "INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, first_seen_at, last_seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?)", (urn(n), text, published, source, published, published))
    conn.commit()


def add_reading(conn, n, reactions, days_ago=30, source="post_analytics"):
    published = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    observed = datetime.now(timezone.utc) - timedelta(days=1)
    conn.execute("UPDATE own_posts SET published_at = ? WHERE activity_urn = ?", (published, urn(n)))
    conn.execute(
        "INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, source, "
        "impressions, reactions, comments, reposts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (urn(n), observed.isoformat(), observed.strftime("%Y-%m-%dT%H"), (days_ago - 1) * 24.0, source,
         reactions * 40, reactions, 2, 0))
    conn.commit()


def add_comment(conn, my_text, days_ago=5, author="Another Person", excerpt="Their own post, in their own words.",
                when=None):
    when = when or (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    cursor = conn.execute(
        "INSERT INTO outbound_engagements (target_activity_urn, target_author, target_excerpt, kind, reaction_kind, "
        "my_text, my_text_key, first_seen_at, last_seen_at) VALUES (?, ?, ?, 'comment', NULL, ?, ?, ?, ?)",
        (f"urn:li:activity:73900000000000{days_ago:05d}", author, excerpt, my_text, my_text[:20], when, when))
    conn.commit()
    return cursor.lastrowid


def add_ask(conn, text, source="ask_box"):
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute("INSERT INTO asks (text, source, status, created_at, updated_at) VALUES (?, ?, 'open', ?, ?)",
                          (text, source, now, now))
    conn.commit()
    return cursor.lastrowid


def cards_of(batch):
    return {card["slot"]: card for card in batch["cards"]}


# ---------------------------------------------------------------------------
# Day 0: an archive, no readings, no key
# ---------------------------------------------------------------------------

def test_day_zero_with_an_archive_fills_the_section_and_abstains_on_what_worked(conn):
    import record_cards

    add_posts(conn)
    add_comment(conn, "We did the same with our hiring loop and it took a quarter to settle.")
    batch = record_cards.compute_local(conn, DAY, record_cards.seed_for(DAY))
    slots = cards_of(batch)

    worked = slots[1]
    assert worked["label"] == "abstained" and worked["status"] == "abstained"
    assert worked["payload"]["sentence"].startswith("No readings yet")
    assert "Import your history" in worked["payload"]["sentence"]

    # 26 October 2024: the first post was written on this day two years ago.
    assert slots[2]["kind"] == "on_this_day" and slots[2]["label"] == "measured"
    assert "2 years ago today" in slots[2]["payload"]["because"]
    assert slots[2]["payload"]["figure_sentence"] == "figures not measured"

    assert slots[3]["kind"] == "theme" and slots[3]["label"] == "typed"
    assert "recurring words" in slots[3]["payload"]["because"]

    engaged = slots[4]
    assert engaged["kind"] == "comment" and engaged["payload"]["excerpt"].startswith("We did the same")

    # Four of five slots filled, the abstention said in a sentence, nothing padded.
    assert batch["filled_slots"] == [2, 3, 4]
    assert all(card["label"] in record_cards.LABELS for card in batch["cards"])


def test_the_other_persons_post_is_never_on_a_card(conn):
    import record_cards

    add_posts(conn)
    add_comment(conn, "Agreed, and the second half matters more.", author="Jordan Example",
                excerpt="An unmistakable sentence from somebody else's post.")
    batch = record_cards.compute_local(conn, DAY, record_cards.seed_for(DAY))
    text = json.dumps(batch)
    assert "Jordan Example" not in text, "another person's name reached a card"
    assert "unmistakable sentence" not in text, "another person's post text reached a card"
    source = io.open(os.path.join(BACKEND, "record_cards.py"), encoding="utf-8").read()
    # Inside a SQL string: the module's docstring names the columns to say they are never read.
    assert not re.search(r"SELECT[^\"']*\btarget_(author|excerpt)\b", source), "the module reads other people's text"
    assert re.search(r"SELECT[^\"']*\btarget_(author|excerpt)\b", "x = 'SELECT target_author FROM t'"), "vacuous guard"


# ---------------------------------------------------------------------------
# What worked: results.ranking and nothing else
# ---------------------------------------------------------------------------

def test_what_worked_abstains_in_words_below_the_engine_minimum(conn):
    import record_cards
    import results

    add_posts(conn)
    add_reading(conn, 0, 30)
    add_reading(conn, 1, 12)
    # A third read but not settled: two days old.
    add_reading(conn, 2, 99, days_ago=2)
    card = record_cards.what_worked(conn, record_cards._posts(conn))
    assert card["label"] == "abstained"
    sentence = card["payload"]["sentence"]
    assert sentence.startswith(f"Not enough settled posts yet: 2 of {results.MIN_FOR_MEDIAN}")
    assert "3 of your posts have figures" in sentence


def test_what_worked_is_results_best_with_every_figure_from_its_row(conn):
    import record_cards
    import results

    add_posts(conn)
    for n, reactions in enumerate((30, 12, 18, 9)):
        add_reading(conn, n, reactions, days_ago=40 + n)
    card = record_cards.what_worked(conn, record_cards._posts(conn))
    assert card["label"] == "measured"
    best = results.best(conn, limit=1)["best"][0]
    assert card["provenance"]["source_rows"] == [{"table": "own_posts", "id": best}]
    assert best == urn(0)
    figures = {f["name"]: f for f in card["provenance"]["figures"]}
    assert figures["reactions"]["value"] == 30
    assert figures["reactions"]["table"] == "post_metric_observations" and figures["reactions"]["id"] == best
    assert figures["reactions"]["observed_at"], "a figure without the time it was read"
    # 30 against the median of 30, 12, 18, 9, which is 15.
    assert "2.0 times your usual reactions: 30 against your median 15 across 4 settled posts" in card["payload"]["figure_sentence"]
    assert card["payload"]["because"].endswith("rule: Working for you")


def test_no_second_ranking_of_posts_lives_in_the_section():
    """
    The guard: the section's modules rank posts only by calling results. A
    sort by reactions, impressions or a ratio, or an ORDER BY on a figure,
    would be a second definition of "worked". Falsified by planting one.
    """
    pattern = re.compile(r"ORDER BY\s+(?:\w+\.)?(reactions|impressions|comments)\b|"
                         r"sorted\([^)]*\b(reactions|impressions|against_usual)\b", re.I)
    for name in sorted(os.listdir(BACKEND)):
        if name.startswith("record_") and name.endswith(".py"):
            source = io.open(os.path.join(BACKEND, name), encoding="utf-8").read()
            assert not pattern.search(source), f"{name} ranks posts by its own rule"
    planted = "rows = conn.execute('SELECT * FROM own_posts ORDER BY reactions DESC')"
    assert pattern.search(planted), "the guard would not notice a second ranking"
    source = io.open(os.path.join(BACKEND, "record_cards.py"), encoding="utf-8").read()
    assert "results.best(" in source and "results.ranking(" in source


# ---------------------------------------------------------------------------
# Zero egress
# ---------------------------------------------------------------------------

def test_the_local_stage_sends_nothing(conn):
    import egress
    import record_cards

    add_posts(conn)
    add_comment(conn, "A thought of mine on hiring.")
    egress.reset_for_tests()
    record_cards.compute_local(conn, DAY, record_cards.seed_for(DAY))
    assert egress.describe()["total_performed"] == 0
    assert egress.describe()["total_refused"] == 0
    source = io.open(os.path.join(BACKEND, "record_cards.py"), encoding="utf-8").read()
    for client in ("import urllib", "import requests", "import httpx", "import socket", "model_gateway"):
        assert client not in source, f"the local stage imports {client}"


# ---------------------------------------------------------------------------
# You asked: matched to the creator's own posts by the words they share
# ---------------------------------------------------------------------------

def test_an_ask_is_matched_to_the_posts_that_share_its_words(conn):
    import record_cards

    add_posts(conn)
    ask_id = add_ask(conn, "hiring without a recruiter")
    card = cards_of(record_cards.compute_local(conn, DAY, record_cards.seed_for(DAY)))[3]
    assert card["kind"] == "ask" and card["label"] == "typed"
    matched = [m["activity_urn"] for m in card["payload"]["matches"]]
    assert urn(1) == matched[0], "the post sharing both words is not first"
    assert set(matched) <= {urn(0), urn(1), urn(3)}, matched
    assert {"table": "asks", "id": ask_id} in card["provenance"]["source_rows"]
    assert "hiring without a recruiter" in card["payload"]["because"]
    assert card["payload"]["because"].endswith("rule: You asked")


def test_stopwords_alone_match_nothing(conn):
    import record_cards

    add_posts(conn)
    assert record_cards.matches_in_own_posts(conn, "the and a without") == []


# ---------------------------------------------------------------------------
# Draws: reproducible, held back after a showing, never a hidden item
# ---------------------------------------------------------------------------

def test_the_same_seed_draws_the_same_batch(conn):
    import record_cards

    add_posts(conn)
    for n in range(4):
        add_comment(conn, f"A comment of mine about hiring, the {n} time.", days_ago=3 + n)
    first = record_cards.compute_local(conn, TUESDAY, 1234)
    again = record_cards.compute_local(conn, TUESDAY, 1234)
    assert [c["card_id"] for c in first["cards"]] == [c["card_id"] for c in again["cards"]]


def test_an_item_shown_yesterday_is_held_back_today(conn):
    import record_cards

    add_posts(conn)
    only = add_comment(conn, "My only comment, about pricing pages.")
    yesterday = TUESDAY - timedelta(days=1)
    batch = record_cards.compute_local(conn, yesterday, 7)
    record_cards.store_batch(conn, yesterday, batch)
    conn.commit()
    assert cards_of(batch)[4]["card_id"] == f"eng:{only}"
    today = cards_of(record_cards.compute_local(conn, TUESDAY, 7))[4]
    assert today["card_id"] != f"eng:{only}", "a card shown yesterday came straight back"
    assert today["label"] == "abstained", "with nothing else to show, the slot says so rather than repeating"
    assert today["payload"]["sentence"].startswith("Every post you engaged with was shown"), today["payload"]


def test_a_hidden_item_is_never_drawn(conn):
    import record_cards

    add_posts(conn)
    hidden = add_comment(conn, "A comment I would rather not see again.")
    conn.execute("INSERT INTO card_marks (day, card_id, mark, at) VALUES (?, ?, 'hide', ?)",
                 ("2026-10-20", f"eng:{hidden}", "2026-10-20T08:00:00+00:00"))
    conn.commit()
    for seed in range(20):
        card = cards_of(record_cards.compute_local(conn, TUESDAY, seed))[4]
        assert card["card_id"] != f"eng:{hidden}"


# ---------------------------------------------------------------------------
# The Monday card: counts only, no comparison
# ---------------------------------------------------------------------------

def test_the_monday_card_counts_and_compares_nothing(conn):
    import record_cards

    add_posts(conn)
    add_comment(conn, "A comment this week.", when=f"{DAY - timedelta(days=2)}T12:00:00+00:00")
    add_comment(conn, "A comment the week before.", when=f"{DAY - timedelta(days=9)}T12:00:00+00:00")
    monday = record_cards.monday_card(conn, DAY)
    assert monday is not None and monday["label"] == "measured"
    counts = monday["payload"]["counts"]
    assert counts["comments_given"] == 1
    assert "1 comment given" in monday["payload"]["figure_sentence"]
    # No Replies table on this branch: the count is not measured, never 0.
    assert counts["replies_answered"] is None
    assert "replies answered not measured" in monday["payload"]["figure_sentence"]
    words = monday["payload"]["figure_sentence"].lower()
    for comparing in (" than ", " up ", " down ", "%", " vs", "last week", "more", "fewer"):
        assert comparing not in f" {words} ", f"the Monday card compares: {comparing!r}"
    assert record_cards.monday_card(conn, TUESDAY) is None


# ---------------------------------------------------------------------------
# Verification: a card whose cited row is gone is dropped, not shown
# ---------------------------------------------------------------------------

def test_a_card_citing_a_missing_row_is_dropped(conn):
    import record_cards

    add_posts(conn)
    card = record_cards._card("worked:urn:li:activity:1", 1, "working_for_you", "what_worked", "measured", "rule",
                              {"title": "x"}, [{"table": "own_posts", "id": "urn:li:activity:999999999999"}])
    checked = record_cards.verify(conn, card)
    assert checked["status"] == "dropped"
    assert checked["provenance"]["verification"]["ids_exist"] is False
    assert "not found" in checked["provenance"]["verification"]["dropped_reason"]
    # A table no card may cite is refused the same way.
    card = record_cards._card("x", 1, "working_for_you", "x", "measured", "rule", {}, [{"table": "leads", "id": "1"}])
    assert record_cards.verify(conn, card)["status"] == "dropped"


def test_every_stored_card_names_its_label_and_rule(conn):
    import record_cards

    add_posts(conn)
    add_ask(conn, "pricing for small studios")
    batch = record_cards.compute_local(conn, DAY, 3)
    record_cards.store_batch(conn, DAY, batch)
    conn.commit()
    stored = record_cards.read_batch(conn, DAY)
    assert stored, "nothing was stored"
    for card in stored:
        assert card["label"] in record_cards.LABELS
        assert card["method"], card
        assert card["provenance"]["verification"]["ids_exist"] is True
        if card["status"] == "shown":
            assert card["payload"]["because"].startswith("Because"), card["payload"]


# ---------------------------------------------------------------------------
# A mark on a card the record chooses: Hide and Skip set it aside
# ---------------------------------------------------------------------------
#
# What worked and On this day are chosen by the record, not drawn, so a
# draw's weights never touched them: Hide on the best post said "It is not
# shown again" and the same post came back the next morning. A hide now
# passes it over for good and a skip for two weeks, for the next post in
# results.ranking's own order, and the card says one was passed over.

def _mark(conn, card_id, mark, at):
    conn.execute("INSERT INTO card_marks (day, card_id, mark, at) VALUES (?, ?, ?, ?)",
                 (at.date().isoformat(), card_id, mark, at.isoformat()))
    conn.commit()


def test_a_hidden_best_post_gives_way_to_the_next_in_the_same_ranking(conn):
    import record_cards
    import results

    add_posts(conn)
    for n, reactions in enumerate((30, 12, 18, 9)):
        add_reading(conn, n, reactions, days_ago=40 + n)
    order = results.ranking(conn)["order"]
    assert order[:2] == [urn(0), urn(2)], order

    _mark(conn, f"worked:{urn(0)}", "hide", datetime(2026, 10, 20, 9, tzinfo=timezone.utc))
    card = record_cards.what_worked(conn, record_cards._posts(conn), record_cards._history(conn, DAY), DAY)
    assert card["provenance"]["source_rows"] == [{"table": "own_posts", "id": urn(2)}], (
        "a hidden best post came back")
    assert "with 1 post above it set aside" in card["payload"]["because"]
    # Its figures are still its own row's, read by the one ranking.
    assert {f["name"]: f["value"] for f in card["provenance"]["figures"]}["reactions"] == 18

    # Without the marks, the same call names the best post: the order is not changed, only stepped through.
    plain = record_cards.what_worked(conn, record_cards._posts(conn))
    assert plain["provenance"]["source_rows"] == [{"table": "own_posts", "id": urn(0)}]


def test_a_skip_sets_the_best_post_aside_for_two_weeks_only(conn):
    import record_cards

    add_posts(conn)
    for n, reactions in enumerate((30, 12, 18, 9)):
        add_reading(conn, n, reactions, days_ago=40 + n)
    skipped_on = datetime(2026, 10, 20, 9, tzinfo=timezone.utc)
    _mark(conn, f"worked:{urn(0)}", "skip", skipped_on)
    within = skipped_on.date() + timedelta(days=record_cards.SKIP_HOLD_DAYS - 1)
    after = skipped_on.date() + timedelta(days=record_cards.SKIP_HOLD_DAYS)
    held = record_cards.what_worked(conn, record_cards._posts(conn), record_cards._history(conn, within), within)
    back = record_cards.what_worked(conn, record_cards._posts(conn), record_cards._history(conn, after), after)
    assert held["provenance"]["source_rows"][0]["id"] == urn(2)
    assert back["provenance"]["source_rows"][0]["id"] == urn(0)


def test_every_ranked_post_hidden_is_said_not_padded(conn):
    import record_cards
    import results

    add_posts(conn)
    for n, reactions in enumerate((30, 12, 18, 9)):
        add_reading(conn, n, reactions, days_ago=40 + n)
    for ranked in results.ranking(conn)["order"]:
        _mark(conn, f"worked:{ranked}", "hide", datetime(2026, 10, 20, 9, tzinfo=timezone.utc))
    card = record_cards.what_worked(conn, record_cards._posts(conn), record_cards._history(conn, DAY), DAY)
    assert card["label"] == "abstained"
    assert card["payload"]["sentence"].startswith("You hid or skipped every post the ranking holds.")


def test_a_hidden_post_of_this_day_gives_way_to_an_opener(conn):
    import record_cards

    add_posts(conn)
    first = record_cards.compute_local(conn, DAY, record_cards.seed_for(DAY))
    assert cards_of(first)[2]["kind"] == "on_this_day"
    _mark(conn, cards_of(first)[2]["card_id"], "hide", datetime(2026, 10, 25, 9, tzinfo=timezone.utc))
    again = record_cards.compute_local(conn, DAY, record_cards.seed_for(DAY))
    assert cards_of(again)[2]["kind"] == "opener", cards_of(again)[2]


def test_each_mark_says_only_what_it_does_to_that_kind_of_card():
    import record_cards
    import record_store

    drawn = record_store.mark_said("keep", "opener")
    chosen = record_store.mark_said("keep", "what_worked")
    once = record_store.mark_said("keep", "idea")
    assert "comes back more often" in drawn
    assert "comes back more often" not in chosen and "comes back more often" not in once
    assert "next one in line" in record_store.mark_said("hide", "on_this_day")
    assert "never shown twice" in record_store.mark_said("skip", "idea")
    # Every kind a card can have is one of the three, so no mark falls through to the wrong sentence.
    kinds = set(record_cards.DRAWN_KINDS) | set(record_cards.CHOSEN_KINDS) | {"idea", "monday"}
    assert set(record_cards.DRAWN_KINDS).isdisjoint(record_cards.CHOSEN_KINDS)
    source = io.open(os.path.join(BACKEND, "record_cards.py"), encoding="utf-8").read()
    built = set(re.findall(r'_card\([^,]+, \d, "\w+", "(\w+)"', source))
    built |= {"library", "idea"}  # library_bundle.match_card and record_model.verify_ideas
    assert built and built <= kinds, built - kinds
