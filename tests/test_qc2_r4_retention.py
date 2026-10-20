"""
Retention the Creator Controls, With Nothing of Theirs Lost Without Asking.
==========================================================================
DATA-06 and DATA-01. Nothing expired except three logs: readings, reactions
and telemetry grew for ever, and nothing offered to forget the people who
engaged once, years ago, and were never contacted.

Held here:
- telemetry older than 30 days is removed;
- post readings older than 30 days keep the last of each day and every
  reading in Today's comparison window, and Today's two-day comparison and
  latest reading are identical for every post afterwards;
- reactions older than 24 months fold into per-post counts, no reaction is
  lost from the count, and comments are never touched;
- on a database that already held readings or reactions, neither runs until
  the creator confirms a preview; a new install does both going forward;
- leads silent for 24 months that were never acted on are listed, never
  removed on their own; forgetting re-checks each person;
- every cleanup is previewable, logged, idempotent, absent from migrations,
  and takes a verified backup first;
- forgotten people can be removed from backups too.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import json
import os
import sqlite3
import sys
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from studio.backend import database, migrations, paths, retention, support, today  # noqa: E402

NOW = datetime.now(timezone.utc)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    database.init_db()
    for name in os.listdir(paths.get_backups_dir()):
        os.remove(os.path.join(paths.get_backups_dir(), name))
    return tmp_path


def _sql_time(moment):
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def _db():
    conn = sqlite3.connect(paths.get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _set(key, value):
    conn = _db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def _count(sql, *args):
    conn = _db()
    try:
        return conn.execute(sql, args).fetchone()[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Data builders
# ---------------------------------------------------------------------------

def _post_readings(posts=6, days_old=200):
    """Posts published up to `days_old` days ago, read hourly for 10 days, then daily twice."""
    conn = _db()
    for p in range(posts):
        urn = f"urn:li:activity:{7100000000000000000 + p}"
        published = NOW - timedelta(days=days_old - p * 30)
        conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, first_seen_at, last_seen_at) "
                     "VALUES (?, ?, ?, ?, ?)", (urn, f"post {p}", published.isoformat(),
                                                published.isoformat(), published.isoformat()))
        moments = [published + timedelta(hours=h, minutes=7) for h in range(1, 240)]
        moments += [published + timedelta(days=d, hours=h) for d in range(10, 40) for h in (3, 15)]
        for i, moment in enumerate(m for m in moments if m < NOW):
            for source in ("activity_page", "post_analytics"):
                age = round((moment - published).total_seconds() / 3600.0, 2)
                conn.execute(
                    "INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, "
                    "source, impressions, reactions, comments) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (urn, moment.isoformat(), moment.strftime("%Y-%m-%dT%H"), age, source,
                     100 + i * 3 + (1 if source == "post_analytics" else 0), 5 + i, 1 + i // 10))
    conn.commit()
    conn.close()


def _today_view():
    conn = database.get_db()
    try:
        urns = [r[0] for r in conn.execute("SELECT activity_urn FROM own_posts ORDER BY activity_urn")]
        return {urn: (today._reading_at_age(conn, urn), today._latest_reading(conn, urn),
                      bool(conn.execute("SELECT 1 FROM post_metric_observations WHERE activity_urn = ? "
                                        "AND source = 'post_analytics' LIMIT 1", (urn,)).fetchone()))
                for urn in urns}
    finally:
        conn.close()


def _lead(lead_id, name, status="NEW", notes=None, updated=None):
    conn = _db()
    conn.execute("INSERT INTO leads (id, name, full_name, lead_status, notes, created_at, updated_at) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (lead_id, name, name, status, notes, _sql_time(updated or NOW), _sql_time(updated or NOW)))
    conn.commit()
    conn.close()


def _interaction(lead_id, kind, when, post="urn:li:activity:1", text=None):
    conn = _db()
    conn.execute(
        "INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, comment_text, interacted_at, "
        "comment_key, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (lead_id, post, kind, text, _sql_time(when), migrations.interaction_comment_key(text),
         _sql_time(when), _sql_time(when)))
    conn.commit()
    conn.close()


def _telemetry(days_ago_list):
    path = os.path.join(paths.get_data_dir(), "analytics_telemetry.db")
    from studio.core.telemetry_shard import TelemetryEngine
    TelemetryEngine(path)
    conn = sqlite3.connect(path)
    for days in days_ago_list:
        conn.execute("INSERT INTO telemetry_events (event_type, source, payload, created_at) VALUES (?, ?, ?, ?)",
                     ("feed", "extension", "{}", _sql_time(NOW - timedelta(days=days))))
    conn.commit()
    conn.close()
    return path


# ---------------------------------------------------------------------------
# Migration 20: structures only, and the starting state of each rule
# ---------------------------------------------------------------------------

def test_a_new_install_folds_and_rolls_up_going_forward(home):
    assert retention.rules()["readings"] == "on"
    assert retention.rules()["fold_reactions"] == "on"
    assert retention.rules()["daily_backup"] == "on"
    assert retention.rules()["telemetry_days"] == "30"
    assert retention.rules()["lead_review"] == "ask"


def _back_to_19():
    conn = _db()
    conn.execute("DROP TABLE reaction_folds")
    conn.execute("DROP TABLE lead_retention_keeps")
    conn.execute("DROP TABLE retention_log")
    conn.execute("DROP TABLE forgotten_in_backups")
    conn.execute("DROP TRIGGER lead_returned")
    conn.execute("DELETE FROM settings WHERE key LIKE 'retention_%'")
    conn.execute("PRAGMA user_version = 19")
    conn.commit()
    conn.close()


def test_an_existing_database_asks_first_and_the_migration_removes_nothing(home):
    _post_readings(posts=2)
    _lead("lead-old", "Old Reactor")
    _interaction("lead-old", "LIKE", NOW - timedelta(days=900))
    _back_to_19()
    readings = _count("SELECT COUNT(*) FROM post_metric_observations")
    interactions = _count("SELECT COUNT(*) FROM lead_interactions")

    database.init_db()
    database.init_db()  # idempotent

    assert _count("PRAGMA user_version") == migrations.SCHEMA_VERSION
    assert retention.rules()["readings"] == "ask"
    assert retention.rules()["fold_reactions"] == "ask"
    assert _count("SELECT COUNT(*) FROM post_metric_observations") == readings
    assert _count("SELECT COUNT(*) FROM lead_interactions") == interactions
    assert any(n.startswith("linkedin_studio_premigration_") for n in os.listdir(paths.get_backups_dir()))


def test_the_forget_trigger_covers_the_keep_list(home):
    _lead("lead-k", "Kept Person", updated=NOW - timedelta(days=800))
    retention.keep_leads(["lead-k"])
    conn = _db()
    conn.execute("DELETE FROM leads WHERE id = 'lead-k'")
    conn.commit()
    conn.close()
    assert _count("SELECT COUNT(*) FROM lead_retention_keeps") == 0


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

def test_telemetry_older_than_thirty_days_is_removed(home):
    _telemetry([1, 10, 29, 31, 60, 200])
    assert retention.preview("telemetry")["rows"] == 3
    done = retention.run("telemetry")
    assert done["removed"] == 3
    shard = sqlite3.connect(os.path.join(paths.get_data_dir(), "analytics_telemetry.db"))
    assert shard.execute("SELECT COUNT(*) FROM telemetry_events").fetchone()[0] == 3
    shard.close()
    assert retention.run("telemetry")["removed"] == 0
    assert retention.recent_log()[0]["job"] == "telemetry"


def test_telemetry_keeps_what_its_rule_says(home):
    _telemetry([1, 8, 40, 100])
    retention.set_rules({"telemetry_days": "90"})
    assert retention.preview("telemetry")["rows"] == 1
    retention.set_rules({"telemetry_days": "7"})
    assert retention.preview("telemetry")["rows"] == 3


# ---------------------------------------------------------------------------
# Post readings: Today's comparison is unchanged
# ---------------------------------------------------------------------------

def test_the_reading_roll_up_leaves_todays_comparison_identical(home):
    _post_readings(posts=6)
    before = _today_view()
    rows_before = _count("SELECT COUNT(*) FROM post_metric_observations")
    latest_post_before = today._latest_post(database.get_db())

    expected = retention.preview("readings")["rows"]
    assert expected > rows_before / 3, "the roll-up found too little to roll up for this to prove anything"
    done = retention.run("readings")
    assert done["removed"] == expected

    assert _today_view() == before, "Today's comparison or latest reading changed"
    assert today._latest_post(database.get_db())["comparison"] == latest_post_before["comparison"]
    assert retention.preview("readings")["rows"] == 0
    assert retention.run("readings")["removed"] == 0, "the roll-up is not idempotent"


def test_the_roll_up_keeps_one_reading_per_day_and_every_recent_reading(home):
    _post_readings(posts=1, days_old=45)
    cut = (NOW - timedelta(days=30)).strftime("%Y-%m-%dT%H")
    recent_before = _count("SELECT COUNT(*) FROM post_metric_observations WHERE observed_hour >= ?", cut)
    retention.run("readings")
    assert _count("SELECT COUNT(*) FROM post_metric_observations WHERE observed_hour >= ?", cut) == recent_before
    per_day = _count(
        "SELECT MAX(n) FROM (SELECT COUNT(*) AS n FROM post_metric_observations WHERE observed_hour < ? "
        "AND NOT (age_hours BETWEEN 36 AND 72) GROUP BY source, substr(observed_hour, 1, 10))", cut)
    assert per_day == 1


# ---------------------------------------------------------------------------
# Reactions: folded into per-post counts, comments kept
# ---------------------------------------------------------------------------

def _engagement():
    for i in range(30):
        _lead(f"lead-{i}", f"Person {i}")
    for i in range(30):
        post = f"urn:li:activity:{i % 3}"
        _interaction(f"lead-{i}", "LIKE", NOW - timedelta(days=800 + i), post=post)
        _interaction(f"lead-{i}", "COMMENT", NOW - timedelta(days=900), post=post, text=f"Comment {i}")
        if i % 2:
            _interaction(f"lead-{i}", "LIKE", NOW - timedelta(days=10), post=f"urn:li:activity:{i}0")


def _likes_per_post():
    conn = _db()
    counts = {r[0]: r[1] for r in conn.execute(
        "SELECT post_urn, COUNT(*) FROM lead_interactions WHERE interaction_type = 'LIKE' GROUP BY post_urn")}
    for urn, folded in conn.execute("SELECT post_urn, reactions FROM reaction_folds"):
        counts[urn] = counts.get(urn, 0) + folded
    conn.close()
    return counts


def test_old_reactions_fold_into_per_post_counts_and_comments_stay(home, monkeypatch):
    _engagement()
    monkeypatch.setattr(retention, "BATCH", 7)
    before = _likes_per_post()
    comments = _count("SELECT COUNT(*) FROM lead_interactions WHERE interaction_type = 'COMMENT'")

    preview = retention.preview("reactions")
    assert preview["rows"] == 30 and preview["posts"] == 3 and preview["comments_kept"] == comments
    assert retention.run("reactions")["removed"] == 30

    assert _likes_per_post() == before, "a reaction was lost from its post's count"
    assert _count("SELECT COUNT(*) FROM lead_interactions WHERE interaction_type = 'COMMENT'") == comments
    assert _count("SELECT COUNT(*) FROM lead_interactions WHERE interaction_type = 'LIKE'") == 15
    assert retention.run("reactions")["removed"] == 0
    assert _likes_per_post() == before, "running the fold again counted reactions twice"
    assert retention.folded_reactions()["urn:li:activity:0"] == 10


# ---------------------------------------------------------------------------
# Asking first
# ---------------------------------------------------------------------------

def test_readings_and_reactions_are_switched_on_only_by_confirming(home):
    _set("retention_readings", "ask")
    with pytest.raises(retention.RetentionRefused, match="preview"):
        retention.set_rules({"readings": "on"})
    with pytest.raises(retention.RetentionRefused):
        retention.set_rules({"fold_reactions": "on"})
    retention.set_rules({"readings": "off"})
    assert retention.rules()["readings"] == "off"
    retention.run("readings")
    assert retention.rules()["readings"] == "on"


def test_the_daily_run_waits_for_the_creator_where_it_must_ask(home):
    _post_readings(posts=2)
    _engagement()
    _set("retention_readings", "ask")
    _set("retention_fold_reactions", "ask")
    readings = _count("SELECT COUNT(*) FROM post_metric_observations")
    likes = _count("SELECT COUNT(*) FROM lead_interactions WHERE interaction_type = 'LIKE'")

    report = retention.run_daily()

    assert report["backup"]["ok"]
    assert report["jobs"]["readings"] == "waiting for you"
    assert report["jobs"]["reactions"] == "waiting for you"
    assert _count("SELECT COUNT(*) FROM post_metric_observations") == readings
    assert _count("SELECT COUNT(*) FROM lead_interactions WHERE interaction_type = 'LIKE'") == likes


def test_the_daily_run_cleans_up_behind_the_backup_it_made(home):
    _post_readings(posts=2)
    _telemetry([45])
    report = retention.run_daily()
    archive = report["backup"]["archive"]
    assert os.path.basename(archive).startswith("inox_backup_daily_")
    assert report["jobs"]["readings"].startswith("removed")
    with zipfile.ZipFile(archive) as z:
        z.extract("data/linkedin_studio.db", str(home / "check"))
    held = sqlite3.connect(str(home / "check" / "data" / "linkedin_studio.db"))
    assert held.execute("SELECT COUNT(*) FROM post_metric_observations").fetchone()[0] > \
        _count("SELECT COUNT(*) FROM post_metric_observations"), "the backup does not hold what was removed"
    held.close()
    logged = [entry["job"] for entry in retention.recent_log()]
    assert "daily_backup" in logged and "readings" in logged


def test_nothing_is_removed_when_the_backup_fails(home, monkeypatch):
    _post_readings(posts=2)
    monkeypatch.setattr(support, "_integrity_of", lambda path: "malformed")
    readings = _count("SELECT COUNT(*) FROM post_metric_observations")
    report = retention.run_daily()
    assert report["backup"]["ok"] is False
    assert report["jobs"] == {}
    with pytest.raises(retention.RetentionRefused, match="backup"):
        retention.run("readings")
    assert _count("SELECT COUNT(*) FROM post_metric_observations") == readings
    assert retention.last_daily_backup()["ok"] is False


def test_a_run_the_creator_starts_takes_its_own_backup_first(home):
    _telemetry([45])
    done = retention.run("telemetry")
    assert done["backup"].startswith("inox_backup_pre_cleanup_")
    assert os.path.exists(os.path.join(paths.get_backups_dir(), done["backup"]))


def test_no_cleanup_lives_in_a_migration():
    import inspect
    source = inspect.getsource(migrations._migrate_retention)
    assert "DELETE FROM lead_interactions" not in source.split("CREATE TRIGGER")[0]
    assert "post_metric_observations WHERE" not in source
    assert "telemetry" not in source


# ---------------------------------------------------------------------------
# Silent leads: a review list
# ---------------------------------------------------------------------------

def _silent_people():
    old = NOW - timedelta(days=800)
    _lead("lead-silent", "Silent Sam", updated=old)
    _interaction("lead-silent", "LIKE", old)
    _lead("lead-recent", "Recent Rita", updated=old)
    _interaction("lead-recent", "COMMENT", NOW - timedelta(days=20), text="Still here")
    _lead("lead-contacted", "Contacted Carl", status="CONTACTED", updated=old)
    _lead("lead-noted", "Noted Nina", notes="met at a conference", updated=old)
    _lead("lead-staged", "Staged Stan", updated=old)
    conn = _db()
    conn.execute("INSERT INTO lead_stage_events (lead_id, from_status, to_status, changed_at) "
                 "VALUES ('lead-staged', 'New Lead', 'New Lead', ?)", (old.isoformat(),))
    conn.commit()
    conn.close()


def test_the_review_list_holds_only_people_never_acted_on_and_silent(home):
    _silent_people()
    listed = retention.review_list()
    assert [lead["id"] for lead in listed["leads"]] == ["lead-silent"]
    assert listed["count"] == 1


def test_nothing_on_the_review_list_is_removed_by_the_daily_run(home):
    _silent_people()
    retention.run_daily()
    assert _count("SELECT COUNT(*) FROM leads WHERE id = 'lead-silent'") == 1


def test_forgetting_re_checks_each_person_and_takes_a_backup(home):
    _silent_people()
    _interaction("lead-silent", "COMMENT", NOW - timedelta(days=1), text="Back again")
    done = retention.forget_leads(["lead-silent", "lead-contacted"])
    assert done["forgotten"] == 0 and done["kept_since"] == 2
    assert _count("SELECT COUNT(*) FROM leads") == 5


def test_forgetting_from_the_review_list(home):
    _silent_people()
    done = retention.forget_leads(["lead-silent"])
    assert done["forgotten"] == 1
    assert done["backup"].startswith("inox_backup_pre_cleanup_")
    assert _count("SELECT COUNT(*) FROM leads WHERE id = 'lead-silent'") == 0
    assert _count("SELECT COUNT(*) FROM lead_interactions WHERE lead_id = 'lead-silent'") == 0
    assert retention.scrub_pending()["people"] == 1
    assert done["backups"]["automatic_gone_by"] == \
        (NOW + timedelta(days=support.ROTATION_REACH_DAYS)).date().isoformat()


def test_keeping_takes_people_off_the_list(home):
    _silent_people()
    assert retention.keep_leads(["lead-silent"])["kept"] == 1
    assert retention.review_list()["count"] == 0
    assert retention.keep_leads(["lead-silent"])["kept"] == 0


# ---------------------------------------------------------------------------
# Remove from backups too
# ---------------------------------------------------------------------------

def test_forgotten_people_can_be_removed_from_backups_too(home):
    _silent_people()
    manual = support.create_backup("manual")
    old = datetime.now() - timedelta(days=3)
    os.utime(manual, (old.timestamp(), old.timestamp()))
    copy = migrations.backup_database("premigration")
    retention.forget_leads(["lead-silent"])
    held = [os.path.join(paths.get_backups_dir(), n) for n in os.listdir(paths.get_backups_dir())]
    # The manual backup is minutes old and checked, so the forget ran behind it
    # rather than writing another full copy.
    assert len(held) == 2

    result = retention.scrub_backups()

    assert result["failed"] == [] and result["rewritten"] == 2, result
    for path in held:
        if path.endswith(".zip"):
            with zipfile.ZipFile(path) as z:
                data = z.read("data/linkedin_studio.db")
                manifest = json.loads(z.read("backup_manifest.json"))
            assert manifest["forgotten_people_removed"][0]["people"] == 1
        else:
            with open(path, "rb") as handle:
                data = handle.read()
        assert b"Silent Sam" not in data, f"{os.path.basename(path)} still holds the forgotten person"
        assert b"Recent Rita" in data, f"{os.path.basename(path)} lost someone who was not forgotten"
    assert abs(os.path.getmtime(manual) - old.timestamp()) < 2, "the rewritten backup changed its date"
    assert support.inspect_backup(copy)["kind"] == "database"
    assert retention.scrub_pending()["people"] == 0
    assert [n for n in os.listdir(paths.get_backups_dir()) if n.startswith(".scrub-")] == []


def test_a_forget_from_anywhere_can_be_removed_from_backups_too(home):
    from studio.backend.crm import reverse_crm

    _lead("lead-dossier", "Dora Dossier")
    support.create_backup("manual")
    assert reverse_crm.purge_lead("lead-dossier")["lead_deleted"]
    assert retention.scrub_pending()["people"] == 1, "a forget from the Leads screen was not offered for backups"
    assert retention.scrub_backups()["rewritten"] == 1
    assert retention.scrub_pending()["people"] == 0


def test_someone_who_comes_back_is_not_removed_from_later_backups(home):
    from studio.backend.crm import reverse_crm

    _lead("lead-back", "Bea Back")
    reverse_crm.purge_lead("lead-back")
    _lead("lead-back", "Bea Back")
    assert retention.scrub_pending()["people"] == 0


def test_leaving_backups_to_rotation_drops_the_held_ids(home):
    _silent_people()
    retention.forget_leads(["lead-silent"])
    assert retention.leave_backups()["people"] == 0


# ---------------------------------------------------------------------------
# Compacting and sizes
# ---------------------------------------------------------------------------

def test_compacting_returns_the_free_space(home):
    _post_readings(posts=3)
    retention.run("readings")
    assert retention.sizes()["free_bytes"] > 0
    done = retention.compact()
    assert done["after_bytes"] < done["before_bytes"]
    assert retention.sizes()["free_bytes"] == 0


def test_sizes_cover_every_table_and_say_when_not_measured(home, monkeypatch):
    _post_readings(posts=1)
    measured = retention.sizes()
    assert measured["measured"] is True
    readings = next(c for c in measured["categories"] if c["key"] == "readings")
    assert readings["bytes"] > 0 and readings["rows"] > 0
    conn = database.get_db()
    pages = conn.execute("PRAGMA page_count").fetchone()[0] * conn.execute("PRAGMA page_size").fetchone()[0]
    conn.close()
    assert sum(c["bytes"] for c in measured["categories"]) == pages - measured["free_bytes"], \
        "a table's pages were not counted in any category"

    real_get_db = retention.get_db

    class NoDbstat:
        def __init__(self, conn):
            self.conn = conn

        def execute(self, sql, *args):
            if "dbstat" in sql:
                raise sqlite3.OperationalError("no such table: dbstat")
            return self.conn.execute(sql, *args)

        def close(self):
            self.conn.close()

    monkeypatch.setattr(retention, "get_db", lambda: NoDbstat(real_get_db()))
    unmeasured = retention.sizes()
    assert unmeasured["measured"] is False
    assert all(c["bytes"] is None for c in unmeasured["categories"]), "an unmeasured size was shown as a number"


def test_the_overview_has_everything_the_panel_shows(home):
    _silent_people()
    support.run_daily_backup()
    view = retention.overview()
    assert view["review"]["count"] == 1
    assert view["backups"]["last"]["verified"] is True
    assert view["backups"]["next_due"]
    assert view["defaults"]["telemetry_days"] == "30"
    assert "ask" not in view["options"]["readings"]
    assert view["backups"]["rotation_reach_days"] == support.ROTATION_REACH_DAYS


def test_the_scheduled_job_is_registered_and_skips_under_the_suite(monkeypatch):
    from studio.backend import scheduler
    assert retention.run_for_every_profile() == []
    added = {}

    class Recorder:
        running = False

        def add_job(self, func, trigger, **kwargs):
            added[kwargs["id"]] = (func, trigger, kwargs)

        def start(self):
            pass

    monkeypatch.setattr(scheduler.native_scheduler, "scheduler", Recorder())
    scheduler.native_scheduler.start()
    func, trigger, kwargs = added["daily_backup_and_retention"]
    assert trigger == "interval" and kwargs["hours"] == 1
    assert func.__name__ == "run_for_every_profile"


# ---------------------------------------------------------------------------
# Review R4: no extra full backup per run
# ---------------------------------------------------------------------------

def _zips():
    return sorted(n for n in os.listdir(paths.get_backups_dir()) if n.endswith(".zip"))


def test_runs_within_the_hour_share_one_backup(home):
    _telemetry([45, 46])
    first = retention.run("telemetry")
    _telemetry([47])
    second = retention.run("telemetry")
    assert first["backup"] == second["backup"]
    assert len(_zips()) == 1


def test_a_run_with_nothing_to_remove_takes_no_backup(home):
    _set("retention_readings", "ask")
    done = retention.run("readings")
    assert done["removed"] == 0 and done["backup"] is None
    assert _zips() == []
    assert retention.rules()["readings"] == "on"


def test_a_cleanup_backup_is_rotated_with_the_rest(home):
    earlier = datetime.now() - timedelta(hours=2)
    for minutes in (0, 10):
        made = earlier + timedelta(minutes=minutes)
        path = os.path.join(paths.get_backups_dir(), f"inox_backup_daily_{made.strftime('%Y%m%d_%H%M%S')}.zip")
        open(path, "wb").close()
    _telemetry([45])
    if datetime.now().date() != earlier.date():
        pytest.skip("the two hours before now cross midnight")
    retention.run("telemetry")
    assert len(_zips()) == 1, _zips()
