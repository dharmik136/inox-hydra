"""
Did the cards help? Counts, a contemporaneous comparison that abstains, a sentence a month, and a backtest.
===========================================================================================================

Cycle 4, track 7, batch 8 of the personalised daily ideas report. Evaluation
lives in the creator's own rows: the marks are a preference, said as counts
under the studio's sample rules; the posts that came from a card are
compared with the creator's other posts of the same 90 days at about two
days old, and the comparison says nothing under 8 a side or when its posts
cannot show less than a doubling; each month gets one of three sentences;
and a backtest the owner runs offline asks whether the section's picks were
still the right posts when the readings came in. Invented posts only.
"""

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
sys.path.insert(0, BACKEND)


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


def urn(n):
    return f"urn:li:activity:74400000000000{n:05d}"


def add_post(conn, n, published, reactions_48h=None, from_card=False, text=None):
    conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, first_seen_at, last_seen_at) "
                 "VALUES (?, ?, ?, 'activity_page', ?, ?)", (urn(n), text or f"A post about hiring loops, number {n}.",
                                                             published.isoformat(), published.isoformat(), published.isoformat()))
    if reactions_48h is not None:
        observed = published + timedelta(hours=48)
        conn.execute("INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, source, "
                     "impressions, reactions, comments, reposts) VALUES (?, ?, ?, 48.0, 'post_analytics', ?, ?, 0, 0)",
                     (urn(n), observed.isoformat(), observed.strftime("%Y-%m-%dT%H"), reactions_48h * 40, reactions_48h))
    if from_card:
        conn.execute("INSERT INTO posts (id, content, status, activity_urn, origin_card_id, origin_day) "
                     "VALUES (?, 'x', 'published', ?, 'theme:hiring', ?)", (f"post_card_{n}", urn(n), published.date().isoformat()))


# ---------------------------------------------------------------------------
# The sample rules
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("part,whole,said,rate", [
    (0, 0, "0 of 0, too few to call a rate", None),
    (3, 4, "3 of 4, too few to call a rate", None),
    (3, 10, "~3 of 10", None),
    (5, 20, "5 of 20 (25%)", 25),
])
def test_a_share_is_said_under_the_sample_rules(part, whole, said, rate):
    import record_evaluation

    answer = record_evaluation.said_share(part, whole)
    assert answer["said"] == said and answer["rate"] == rate


def test_the_funnel_is_counts_by_kind_and_label(home):
    import record_evaluation

    conn = db()
    for n in range(6):
        conn.execute("INSERT INTO daily_view (day, card_id, slot, block, kind, label, method, payload_json, provenance_json, "
                     "status, created_at) VALUES (?, ?, 3, 'you_asked', 'theme', 'typed', 'r', '{}', '{}', 'shown', ?)",
                     (f"2026-10-0{n + 1}", f"theme:{n}", "2026-10-01"))
    for n, mark in enumerate(("keep", "keep", "skip", "used")):
        conn.execute("INSERT INTO card_marks (day, card_id, mark, at) VALUES (?, ?, ?, ?)",
                     (f"2026-10-0{n + 1}", f"theme:{n}", mark, "2026-10-01"))
    conn.commit()
    funnel = record_evaluation.funnel(conn)
    conn.close()
    row = funnel["by_kind"][0]
    assert row["name"] == "Your recurring words" and row["shown"] == 6
    assert row["kept"]["said"] == "2 of 3, too few to call a rate"
    assert row["drafted"]["said"] == "~1 of 6"
    assert "preferred, not what worked" in funnel["note"]
    assert funnel["by_label"][0]["name"] == "typed"


def test_the_monday_line_is_not_a_card_in_the_funnel(home):
    """It has no Keep, Skip or Draft button, so every rate it joined only fell."""
    import record_evaluation

    conn = db()
    conn.execute("INSERT INTO daily_view (day, card_id, slot, block, kind, label, method, payload_json, provenance_json, "
                 "status, created_at) VALUES ('2026-10-26', 'monday:2026-W44', 0, 'monday', 'monday', 'measured', 'r', "
                 "'{}', '{}', 'shown', '2026-10-26')")
    conn.execute("INSERT INTO daily_view (day, card_id, slot, block, kind, label, method, payload_json, provenance_json, "
                 "status, created_at) VALUES ('2026-10-26', 'theme:a', 3, 'you_asked', 'theme', 'typed', 'r', '{}', '{}', "
                 "'shown', '2026-10-26')")
    conn.commit()
    funnel = record_evaluation.funnel(conn)
    conn.close()
    assert [row["name"] for row in funnel["by_kind"]] == ["Your recurring words"]
    assert funnel["total"]["shown"] == 1


# ---------------------------------------------------------------------------
# The comparison, contemporaneous, and its abstentions
# ---------------------------------------------------------------------------

def recent(days_ago):
    return datetime.now(timezone.utc) - timedelta(days=days_ago, hours=3)


def test_no_readings_is_said_in_words(home):
    import record_evaluation

    conn = db()
    add_post(conn, 1, recent(10), None, from_card=True)
    conn.commit()
    answer = record_evaluation.comparison(conn)
    conn.close()
    assert answer["verdict"] == "no_readings" and "was read at about two days old" in answer["sentence"]


def test_under_eight_a_side_nothing_is_said(home):
    import record_evaluation

    conn = db()
    for n in range(3):
        add_post(conn, n, recent(5 + n), 30, from_card=True)
    for n in range(3, 13):
        add_post(conn, n, recent(5 + n), 15)
    conn.commit()
    answer = record_evaluation.comparison(conn)
    conn.close()
    assert answer["verdict"] == "too_few_posts" and answer["n_with"] == 3 and answer["n_without"] == 10
    assert "8 a side are needed" in answer["sentence"] and "times" not in answer["sentence"]


def test_too_few_to_see_less_than_a_doubling_is_said_too(home):
    import record_evaluation

    conn = db()
    spread = [2, 40, 5, 60, 8, 90, 3, 70]
    for n, value in enumerate(spread):
        add_post(conn, n, recent(2 + n), value, from_card=True)
    for n, value in enumerate(spread, start=20):
        add_post(conn, n, recent(2 + n - 20), value)
    conn.commit()
    answer = record_evaluation.comparison(conn)
    conn.close()
    assert answer["too_small_to_tell"] is True
    assert "cannot show a difference smaller than about" in answer["sentence"] and "nothing is said yet" in answer["sentence"]


def test_enough_steady_posts_give_a_ratio_with_both_counts_and_the_caveat(home):
    import record_evaluation

    conn = db()
    for n in range(20):
        add_post(conn, n, recent(2 + n % 60), 30 + n % 3, from_card=True)
    for n in range(20, 50):
        add_post(conn, n, recent(2 + n % 60), 15 + n % 3)
    conn.commit()
    answer = record_evaluation.comparison(conn)
    conn.close()
    assert answer["verdict"] == "more" and answer["n_with"] == 20 and answer["n_without"] == 30
    sentence = answer["sentence"]
    assert "times your usual reactions" in sentence and "across 30 other posts" in sentence
    assert "a note, not a finding" in sentence
    assert "%" not in sentence


# ---------------------------------------------------------------------------
# A sentence a month
# ---------------------------------------------------------------------------

def test_the_three_month_templates(home):
    import record_evaluation

    conn = db()
    july = datetime(2026, 7, 3, 9, tzinfo=timezone.utc)
    august = datetime(2026, 8, 3, 9, tzinfo=timezone.utc)
    september = datetime(2026, 9, 2, 9, tzinfo=timezone.utc)
    add_post(conn, 1, july, None)
    for n in range(3):
        add_post(conn, 10 + n, august + timedelta(days=n), 20, from_card=True)
    for n in range(10):
        add_post(conn, 20 + n, august + timedelta(days=n), 10)
    for n in range(9):
        add_post(conn, 40 + n, september + timedelta(days=n), 30 + n % 2, from_card=True)
    for n in range(12):
        add_post(conn, 60 + n, september + timedelta(days=n), 15 + n % 2)
    conn.commit()
    assert record_evaluation.monthly_sentence(conn, "2026-07") == {
        "month": "2026-07", "template": "C", "sentence": "The studio has no readings for July 2026's posts yet."}
    august_said = record_evaluation.monthly_sentence(conn, "2026-08")
    assert august_said["template"] == "B" and august_said["sentence"].startswith("Fewer than 5 posts came from a card in August 2026")
    september_said = record_evaluation.monthly_sentence(conn, "2026-09")
    conn.close()
    assert september_said["template"] == "A"
    assert september_said["sentence"].startswith("In September 2026, 9 posts came from a card. At 48 hours they drew")
    assert "across 12 other posts" in september_said["sentence"] and september_said["sentence"].endswith("not a finding.")


def test_the_evaluation_route_and_its_screen(home):
    from fastapi.testclient import TestClient

    import app as app_module

    answer = TestClient(app_module.app).get("/api/v1/record/evaluation")
    assert answer.status_code == 200
    body = answer.json()
    assert set(body) >= {"funnel", "comparison", "months", "notes", "this_month"} and len(body["months"]) == 3
    panel = open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "RecordEvaluationPanel.tsx"), encoding="utf-8").read()
    assert "saveRecordNote" in panel and "It is sent nowhere" in panel
    surface = open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "RecordSurface.tsx"), encoding="utf-8").read()
    assert '"Did these help?"' in surface


# ---------------------------------------------------------------------------
# The backtest, offline, on a history that already happened
# ---------------------------------------------------------------------------

def make_history(path, monkeypatch):
    """Ten months of invented posts with readings, in a studio database at `path`."""
    import paths

    from database import init_db

    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    init_db()
    conn = sqlite3.connect(paths.get_db_path())
    start = datetime(2025, 1, 6, 9, tzinfo=timezone.utc)
    n = 0
    for month in range(10):
        for week in range(4):
            published = start + timedelta(days=30 * month + 7 * week)
            text = ("Hiring loops that respect candidates" if week % 2 else "Pricing for small studios") + f" note {n}"
            reactions = 40 if week == 0 else 10 + week
            conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, reactions, "
                         "first_seen_at, last_seen_at) VALUES (?, ?, ?, 'activity_page', ?, ?, ?)",
                         (urn(n), text, published.isoformat(), reactions, published.isoformat(), published.isoformat()))
            for age in (48, 24 * 10):
                observed = published + timedelta(hours=age)
                conn.execute("INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, "
                             "source, impressions, reactions, comments, reposts) VALUES (?, ?, ?, ?, 'post_analytics', ?, ?, 0, 0)",
                             (urn(n), observed.isoformat(), observed.strftime("%Y-%m-%dT%H"), float(age), reactions * 50,
                              reactions))
            n += 1
    conn.commit()
    conn.close()
    return paths.get_db_path()


def test_the_backtest_reports_shares_and_nothing_of_the_posts(tmp_path, monkeypatch):
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    database = make_history(str(tmp_path / "history"), monkeypatch)
    before = hashlib.sha256(open(database, "rb").read()).hexdigest()
    out = tmp_path / "report.json"
    done = subprocess.run([sys.executable, os.path.join(REPO_ROOT, "tools", "backtest_record.py"), "--db", database,
                           "--out", str(out), "--top", "3", "--tune", "2025"],
                          capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr
    report = json.loads(out.read_text())
    assert report["tool"] == "backtest_record" and report["format"] == 1 and report["top"] == 3
    assert report["database"] == os.path.basename(database)
    assert report["months"], "no month was backtested"
    for month in report["months"]:
        for key in ("stability", "foresight", "resurfacing"):
            assert month[key] is None or 0.0 <= month[key] <= 1.0, month
    assert report["split"] == {"tune": ["2025"], "test": []}
    text = out.read_text()
    assert "urn:li:" not in text and "Hiring loops" not in text and "Pricing for small" not in text
    assert hashlib.sha256(open(database, "rb").read()).hexdigest() == before, "the backtest wrote to the database"
    assert "| Month |" in done.stdout


def test_the_snapshot_holds_every_column_the_engine_reads_and_an_older_database_still_ranks(tmp_path):
    """
    The snapshot was built from a fixed list of columns, so when migration 28
    gave readings a precision the engine's newest-reading query failed on it
    and every month ranked nothing. It copies the source's columns now; on a
    database from before that migration the column is NULL, which the engine
    reads as a reading that does not say how it was read.
    """
    sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
    import backtest_record

    older = str(tmp_path / "older.db")
    conn = sqlite3.connect(older)
    conn.execute("CREATE TABLE own_posts (activity_urn TEXT PRIMARY KEY, text TEXT, published_at TEXT, "
                 "published_at_source TEXT, reactions INTEGER, comments INTEGER, reposts INTEGER, impressions INTEGER, "
                 "first_seen_at TEXT, last_seen_at TEXT)")
    conn.execute("CREATE TABLE post_metric_observations (activity_urn TEXT, observed_at TEXT, observed_hour TEXT, "
                 "age_hours REAL, source TEXT, impressions INTEGER, members_reached INTEGER, reactions INTEGER, "
                 "comments INTEGER, reposts INTEGER, saves INTEGER, sends INTEGER)")
    start = datetime(2025, 1, 6, 9, tzinfo=timezone.utc)
    for n, reactions in enumerate((30, 12, 18, 9)):
        published = start + timedelta(days=7 * n)
        conn.execute("INSERT INTO own_posts VALUES (?, 'a post', ?, 'activity_page', NULL, NULL, NULL, NULL, ?, ?)",
                     (urn(n), published.isoformat(), published.isoformat(), published.isoformat()))
        observed = published + timedelta(days=10)
        conn.execute("INSERT INTO post_metric_observations VALUES (?, ?, ?, 240.0, 'post_analytics', ?, NULL, ?, 0, 0, "
                     "NULL, NULL)", (urn(n), observed.isoformat(), observed.strftime("%Y-%m-%dT%H"), reactions * 50,
                                     reactions))
    conn.commit()
    conn.close()
    source = backtest_record.open_read_only(older)
    try:
        moment = datetime(2025, 6, 1, tzinfo=timezone.utc)
        snap = backtest_record.snapshot(source, moment.isoformat())
        columns = {row[1] for row in snap.execute("PRAGMA table_info(post_metric_observations)")}
        assert "precision" in columns
        assert snap.execute("SELECT COUNT(*) FROM post_metric_observations WHERE precision IS NULL").fetchone()[0] == 4
        assert backtest_record._ranking(snap, moment)["order"][0] == urn(0)
    finally:
        source.close()


def test_a_months_picks_use_nothing_read_after_it(tmp_path, monkeypatch):
    """The leak check: a post read only after the month cannot be one of that month's picks."""
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
    import backtest_record

    database = make_history(str(tmp_path / "history"), monkeypatch)
    conn = sqlite3.connect(database)
    late = datetime(2025, 3, 1, 9, tzinfo=timezone.utc)
    conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, reactions, first_seen_at, "
                 "last_seen_at) VALUES ('urn:li:activity:7449999999999999999', 'read late', ?, 'activity_page', 9999, ?, ?)",
                 (late.isoformat(), late.isoformat(), late.isoformat()))
    observed = datetime(2025, 9, 1, 9, tzinfo=timezone.utc)
    conn.execute("INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, source, "
                 "impressions, reactions, comments, reposts) VALUES ('urn:li:activity:7449999999999999999', ?, ?, 4400.0, "
                 "'post_analytics', 99999, 9999, 0, 0)", (observed.isoformat(), observed.strftime("%Y-%m-%dT%H")))
    conn.commit()
    conn.close()
    source = backtest_record.open_read_only(database)
    try:
        june = datetime(2025, 6, 1, tzinfo=timezone.utc)
        at_june = backtest_record.snapshot(source, june.isoformat())
        order = backtest_record._ranking(at_june, june)["order"]
        assert "urn:li:activity:7449999999999999999" not in order, "a reading from September ranked a June pick"
        october = datetime(2025, 10, 1, tzinfo=timezone.utc)
        at_october = backtest_record.snapshot(source, october.isoformat())
        assert backtest_record._ranking(at_october, october)["order"][0] == "urn:li:activity:7449999999999999999"
    finally:
        source.close()
