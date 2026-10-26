"""
The daily batch is computed once, carried forward when nothing changed, and only read by the screen.
====================================================================================================

Cycle 4, track 7, batch 5 of the personalised daily ideas report. The
studio has no clock outside its own process, so the batch is built the first
time the studio runs each day, by an hourly check beside the backup's, under
the maintenance turn. The screen's read is a SELECT. When nothing the batch
is built from has changed, yesterday's cards are carried forward unchanged
and the day says "nothing new since", as a sentence; only the date's own
card moves. The job never calls a model: the model stage runs on the
creator's first open of the section (decision 7).
"""

import io
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
sys.path.insert(0, BACKEND)

MONDAY = date(2026, 10, 26)
TUESDAY = date(2026, 10, 27)
WEDNESDAY = date(2026, 10, 28)

POSTS = [
    "Hiring is a product problem, not a recruiting problem. Here is what changed for us.",
    "Three things I learned hiring our first five engineers without a recruiter.",
    "Pricing is a design decision. Most teams treat it as a spreadsheet.",
    "We changed our hiring loop and the offers got better, not slower.",
    "Pricing pages lie less when the founder writes them herself.",
    "A short note on writing every morning before the inbox opens, kept for a year.",
]


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path / "studio"))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    import results
    from database import init_db

    results.forget_cache()
    init_db()
    return tmp_path


def db():
    import paths

    conn = sqlite3.connect(paths.get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def add_posts(texts=POSTS, start=0):
    conn = db()
    for n, text in enumerate(texts, start=start):
        published = f"2025-0{1 + n % 9}-1{n % 9}T09:00:00+00:00"
        conn.execute(
            "INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, first_seen_at, last_seen_at) "
            "VALUES (?, ?, ?, 'archive', ?, ?)", (f"urn:li:activity:7410000000000{n:06d}", text, published, published, published))
    conn.commit()
    conn.close()


def add_comment(text, when):
    conn = db()
    conn.execute(
        "INSERT INTO outbound_engagements (target_activity_urn, target_author, target_excerpt, kind, my_text, my_text_key, "
        "first_seen_at, last_seen_at) VALUES (?, NULL, NULL, 'comment', ?, ?, ?, ?)",
        (f"urn:li:activity:7390000000{abs(hash(text)) % 10**9:09d}", text, text[:12], when, when))
    conn.commit()
    conn.close()


def runs():
    conn = db()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM daily_run ORDER BY day")]
    finally:
        conn.close()


def view(day):
    conn = db()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM daily_view WHERE day = ? ORDER BY slot, card_id",
                                              (day.isoformat(),))]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Once a day, and only read by the screen
# ---------------------------------------------------------------------------

def test_the_batch_is_built_once_and_the_second_run_changes_nothing(home):
    import record_daily

    add_posts()
    first = record_daily.run_today(TUESDAY)
    assert first["status"] == "built"
    rows = view(TUESDAY)
    assert rows, "nothing was stored"
    again = record_daily.run_today(TUESDAY)
    assert again["status"] == "already"
    assert view(TUESDAY) == rows, "a second run of the day changed the batch"
    assert len(runs()) == 1


def test_the_screen_read_computes_nothing(home, monkeypatch):
    import record_cards
    import record_daily

    add_posts()

    def refuse(*_args, **_kwargs):
        raise AssertionError("the screen's read computed a batch")

    monkeypatch.setattr(record_cards, "compute_local", refuse)
    monkeypatch.setattr(record_daily, "run_today", refuse)
    answer = record_daily.read_today(TUESDAY)
    assert answer["batch_day"] is None and answer["cards"] == []
    assert answer["computed"].startswith("nothing computed yet")
    assert runs() == [], "reading the section wrote a run"


def test_yesterdays_batch_is_shown_with_the_line_that_says_so(home):
    import record_daily

    add_posts()
    record_daily.run_today(MONDAY)
    answer = record_daily.read_today(TUESDAY)
    assert answer["batch_day"] == MONDAY.isoformat()
    assert answer["computed"].startswith("computed yesterday at ")
    assert answer["computed"].endswith("today's run has not happened yet")
    assert answer["cards"], "yesterday's cards are not shown"


# ---------------------------------------------------------------------------
# Carried forward when nothing changed
# ---------------------------------------------------------------------------

def test_nothing_new_since_yesterday_is_a_sentence_not_a_reshuffle(home):
    import record_daily

    add_posts()
    add_comment("We did the same with our hiring loop.", "2026-10-20T10:00:00+00:00")
    record_daily.run_today(MONDAY)
    tuesday = record_daily.run_today(TUESDAY)
    assert tuesday["status"] == "carried"
    assert tuesday["run"]["carried_from"] == MONDAY.isoformat()
    assert tuesday["run"]["note"] == f"nothing new since {MONDAY.isoformat()}"

    def steady(rows):
        return {(r["slot"], r["card_id"], r["payload_json"]) for r in rows
                if r["kind"] not in ("on_this_day", "opener", "monday")}

    assert steady(view(TUESDAY)) == steady(view(MONDAY)), "unchanged inputs reshuffled the cards"
    assert not any(r["kind"] == "monday" for r in view(TUESDAY)), "Monday's card was carried into Tuesday"
    answer = record_daily.read_today(TUESDAY)
    assert answer["nothing_new"].startswith(f"Nothing new since {MONDAY.isoformat()}")


def test_a_new_post_rebuilds_the_batch(home):
    import record_daily

    add_posts()
    record_daily.run_today(MONDAY)
    add_posts(["A new post about hiring managers who write their own job ads."], start=40)
    assert record_daily.run_today(TUESDAY)["status"] == "built"


def test_a_mark_takes_effect_on_the_next_batch(home):
    import record_daily

    add_posts()
    record_daily.run_today(MONDAY)
    card = next(r for r in view(MONDAY) if r["status"] == "shown")
    conn = db()
    conn.execute("INSERT INTO card_marks (day, card_id, mark, at) VALUES (?, ?, 'hide', ?)",
                 (MONDAY.isoformat(), card["card_id"], "2026-10-26T12:00:00+00:00"))
    conn.commit()
    conn.close()
    assert record_daily.run_today(TUESDAY)["status"] == "built", "a mark did not change what the batch is built from"
    assert card["card_id"] not in {r["card_id"] for r in view(TUESDAY) if r["status"] == "shown"}


# ---------------------------------------------------------------------------
# Suggest new: once a day, recorded, nothing lost
# ---------------------------------------------------------------------------

def test_a_reroll_is_allowed_once_and_keeps_what_was_shown(home):
    import record_daily

    add_posts()
    for n in range(5):
        add_comment(f"A comment of mine on hiring, the {n} of them.", f"2026-10-2{n}T10:00:00+00:00")
    assert record_daily.run_today(TUESDAY, reroll=True)["status"] == "refused", "a re-roll before the batch"
    record_daily.run_today(TUESDAY)
    before = {r["card_id"] for r in view(TUESDAY) if r["status"] == "shown"}
    rolled = record_daily.run_today(TUESDAY, reroll=True)
    assert rolled["status"] == "built" and rolled["run"]["rerolled_at"]
    rows = view(TUESDAY)
    replaced = {r["card_id"] for r in rows if r["status"] == "replaced"}
    assert before - {r["card_id"] for r in rows if r["status"] == "shown"} <= replaced, "a card shown before was lost"
    refused = record_daily.run_today(TUESDAY, reroll=True)
    assert refused["status"] == "refused" and "once" in refused["message"]


# ---------------------------------------------------------------------------
# Asks from the phone, and what is kept
# ---------------------------------------------------------------------------

def test_an_idea_from_telegram_becomes_one_ask(home):
    import record_daily

    conn = db()
    conn.execute("INSERT INTO posts (id, content, status, tags, created_at) VALUES "
                 "('post-draft-77', 'pricing for a two person studio', 'draft', '[\"idea\", \"mobile-ingress\"]', "
                 "'2026-10-25 08:00:00')")
    conn.execute("INSERT INTO posts (id, content, status, tags, created_at) VALUES "
                 "('post-draft-78', 'not an idea, a draft', 'draft', '[\"mobile-ingress\"]', '2026-10-25 08:00:00')")
    conn.commit()
    conn.close()
    record_daily.run_today(MONDAY)
    record_daily.run_today(TUESDAY)
    conn = db()
    asks = [dict(r) for r in conn.execute("SELECT text, source, origin_ref FROM asks")]
    conn.close()
    assert asks == [{"text": "pricing for a two person studio", "source": "telegram", "origin_ref": "post-draft-77"}]


def test_old_batches_go_except_the_ones_a_mark_or_a_draft_refers_to(home):
    import record_daily

    conn = db()
    for day in ("2025-01-01", "2025-01-02", "2025-01-03"):
        conn.execute("INSERT INTO daily_run (day, started_at, local_ok) VALUES (?, ?, 1)", (day, day))
        conn.execute("INSERT INTO daily_view (day, card_id, slot, block, kind, label, method, payload_json, "
                     "provenance_json, created_at) VALUES (?, 'theme:x', 3, 'you_asked', 'theme', 'typed', 'r', '{}', '{}', ?)",
                     (day, day))
    conn.execute("INSERT INTO card_marks (day, card_id, mark, at) VALUES ('2025-01-02', 'theme:x', 'keep', '2025-01-02')")
    conn.execute("INSERT INTO posts (id, content, status, origin_card_id, origin_day) VALUES "
                 "('p-from-card', 'x', 'draft', 'theme:x', '2025-01-03')")
    conn.commit()
    conn.close()
    preview = record_daily.preview_prune(TUESDAY)
    assert preview["days"] == 1 and preview["keep"] == "365"
    record_daily.run_today(TUESDAY)
    kept = {r["day"] for r in runs()}
    assert "2025-01-01" not in kept
    assert {"2025-01-02", "2025-01-03"} <= kept, "a batch a mark or a draft refers to was removed"


# ---------------------------------------------------------------------------
# The job: scheduled beside the backup, polite to it, and never a model
# ---------------------------------------------------------------------------

def test_a_busy_maintenance_turn_is_tried_again_next_hour(home):
    """A backup holding the turn on another thread: the lock is re-entrant within one."""
    import threading

    import record_daily
    import support

    add_posts()
    holding, release = threading.Event(), threading.Event()

    def backup():
        with support.maintenance_turn():
            holding.set()
            release.wait(10)

    worker = threading.Thread(target=backup)
    worker.start()
    try:
        assert holding.wait(10)
        answer = record_daily.run_scheduled()
    finally:
        release.set()
        worker.join(10)
    assert answer["status"] == "skipped" and answer["message"].endswith("tried again next hour")
    assert runs() == []


def test_the_suite_switch_keeps_the_scheduled_job_off(home, monkeypatch):
    import record_daily

    add_posts()
    monkeypatch.setenv("INOX_SCHEDULED_MAINTENANCE", "off")
    assert record_daily.run_for_every_profile() == []
    monkeypatch.delenv("INOX_SCHEDULED_MAINTENANCE")
    reports = record_daily.run_for_every_profile()
    assert reports and reports[0]["status"] in ("built", "carried", "already")


def test_the_scheduler_checks_hourly_however_late(home):
    from scheduler import MISFIRE_GRACE, NativeScheduler

    native = NativeScheduler()
    native.start()
    try:
        job = native.scheduler.get_job("record_daily_batch")
        assert job is not None, "the daily batch is not scheduled"
        assert job.trigger.interval == timedelta(hours=1)
        assert job.misfire_grace_time == MISFIRE_GRACE and job.coalesce is True and job.max_instances == 1
        assert not [j for j in native.scheduler.get_jobs() if "model" in j.id], "a model call is scheduled"
    finally:
        native.shutdown()


def test_the_job_never_calls_a_model(home, monkeypatch):
    from agno_agentos import model_gateway
    import record_daily

    def refuse(*_args, **_kwargs):
        raise AssertionError("the daily job called a model")

    monkeypatch.setattr(model_gateway, "execute_llm_completion", refuse)
    if hasattr(model_gateway, "execute_structured_completion"):
        monkeypatch.setattr(model_gateway, "execute_structured_completion", refuse)
    conn = db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('ai_provider', 'openai')")
    conn.commit()
    conn.close()
    add_posts()
    assert record_daily.run_today(TUESDAY)["status"] == "built"
    slot5 = [r for r in view(TUESDAY) if r["slot"] == 5]
    assert slot5 and slot5[0]["kind"] == "model_pending", "the open slot does not say the model comes on open"
    import re

    source = io.open(os.path.join(BACKEND, "record_daily.py"), encoding="utf-8").read()
    assert not re.search(r"^\s*(from\s+\S*\s+)?import\s+[^\n]*(model_gateway|record_model)", source, re.M), \
        "the daily job imports the model stage"
    assert re.search(r"^\s*(from\s+\S*\s+)?import\s+[^\n]*(model_gateway|record_model)",
                     "    from . import record_model\n", re.M), "the import check is vacuous"


def test_a_search_from_the_archive_becomes_an_ask_only_when_it_is_about_the_creators_topics(home):
    """
    Searches are imported only behind their own tick (decision 6), and a
    search is often a person's name. One that shares a recurring topic word
    of the creator's becomes an ask, once; the rest stay in archive_records.
    """
    import record_daily

    add_posts()
    conn = db()
    for n, query in enumerate(("hiring without a recruiter", "Jordan Example", "pricing pages for studios")):
        conn.execute("INSERT INTO archive_records (kind, detail, happened_at, dedupe_key, source_file, imported_at) "
                     "VALUES ('search_query', ?, '2026-10-20T18:00:00+00:00', ?, 'SearchQueries.csv', '2026-10-25')",
                     (query, f"k{n}"))
    conn.commit()
    conn.close()
    record_daily.run_today(MONDAY)
    record_daily.run_today(TUESDAY)
    conn = db()
    asks = sorted(r[0] for r in conn.execute("SELECT text FROM asks WHERE source = 'archive_search'"))
    note = conn.execute("SELECT local_note FROM daily_run WHERE day = ?", (MONDAY.isoformat(),)).fetchone()[0]
    conn.close()
    assert asks == ["hiring without a recruiter", "pricing pages for studios"]
    assert note == "2 searches from your archive became asks"
