"""
Purging Fabricated Analytics
============================
Migration 4 added a provenance column but deliberately left pre-existing rows at
NULL, because a migration runs on every database and cannot know which of its
rows were seeded. Guessing there would have been the exact mistake the column
exists to prevent.

An operation the creator asks for can do better than guess. The demo series is
deterministic, so a stored row either matches the generator on every field or it
does not. purge_seeded_analytics deletes only the ones that do.

On the install this was written for, all 90 rows matched exactly: the stored
follower count was 2330 + 90/3 = 2360, profile views 70 + 90/5 = 88, and the
newest date the generator's own base_date. That is proof, not inference.

These tests pin two properties that matter more than the deletion itself:

1. A row the creator has really captured is never deleted, even when it sits on
   a date the generator also produces.
2. The seeder and the purge share one definition of the series, so they cannot
   drift apart and start disagreeing about what is fabricated.
"""

import os
import sqlite3
import tempfile

import pytest


@pytest.fixture
def isolated_db(monkeypatch):
    """A database of its own, so a test that deletes analytics deletes only its own."""
    home = tempfile.mkdtemp(prefix="inox_purge_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.setenv("INOX_DEMO_DATA", "1")

    import importlib
    import studio.backend.paths as paths
    import studio.backend.database as database
    importlib.reload(paths)
    importlib.reload(database)

    database.init_db()
    database.seed_initial_data()
    yield database


def test_the_seeder_and_the_purge_share_one_definition(isolated_db):
    """
    Two copies of the arithmetic would drift, and a purge working from a drifted
    copy would either leave fabricated rows behind or delete real ones. This is
    the property that makes the purge safe.
    """
    report = isolated_db.identify_seeded_analytics()
    assert len(report["seeded"]) == isolated_db.DEMO_SERIES_DAYS, (
        f"Only {len(report['seeded'])} of {isolated_db.DEMO_SERIES_DAYS} freshly "
        f"seeded rows were recognised as seeded. The generator and the matcher "
        f"have drifted apart."
    )
    assert not report["modified"]
    assert not report["unknown"]


def test_a_captured_row_is_never_purged_even_on_a_generated_date(isolated_db):
    """
    The dangerous case: the creator captures real numbers for a day the demo
    series also covers. Matching on the date alone would delete their data.
    """
    generated = isolated_db.demo_analytics_rows()
    collision_date = generated[40]["date"]

    conn = isolated_db.get_db()
    conn.execute(
        "UPDATE analytics_daily SET impressions = ?, source = 'observed' WHERE date = ?",
        (91234, collision_date),
    )
    conn.commit()
    conn.close()

    report = isolated_db.purge_seeded_analytics(dry_run=False)

    assert collision_date not in report["seeded"]
    assert collision_date in report["observed"]

    conn = isolated_db.get_db()
    row = conn.execute(
        "SELECT impressions FROM analytics_daily WHERE date = ?", (collision_date,)
    ).fetchone()
    conn.close()
    assert row is not None, "a captured row was deleted by the purge"
    assert row["impressions"] == 91234


def test_a_row_edited_away_from_the_generator_survives(isolated_db):
    """
    Even without a provenance mark, a row that differs from the generator is not
    the generator's work and must be kept.
    """
    generated = isolated_db.demo_analytics_rows()
    edited_date = generated[10]["date"]

    conn = isolated_db.get_db()
    # Leave source NULL: this is the state of every row written before
    # migration 4, which is the situation the purge exists to resolve.
    conn.execute(
        "UPDATE analytics_daily SET followers = followers + 7, source = NULL WHERE date = ?",
        (edited_date,),
    )
    conn.commit()
    conn.close()

    report = isolated_db.identify_seeded_analytics()
    assert edited_date in report["modified"]
    assert edited_date not in report["seeded"]

    isolated_db.purge_seeded_analytics(dry_run=False)

    conn = isolated_db.get_db()
    row = conn.execute(
        "SELECT followers FROM analytics_daily WHERE date = ?", (edited_date,)
    ).fetchone()
    conn.close()
    assert row is not None, "a row that differs from the generator was deleted"


def test_dry_run_deletes_nothing(isolated_db):
    """The default has to be safe, because the argument order is easy to get wrong."""
    before = _count(isolated_db)
    report = isolated_db.purge_seeded_analytics()

    assert report["dry_run"] is True
    assert report["deleted"] == 0
    assert len(report["seeded"]) > 0, "nothing was identified, so this proves nothing"
    assert _count(isolated_db) == before


def test_the_purge_removes_exactly_what_it_identified(isolated_db):
    before = _count(isolated_db)
    identified = len(isolated_db.identify_seeded_analytics()["seeded"])

    report = isolated_db.purge_seeded_analytics(dry_run=False)

    assert report["deleted"] == identified
    assert _count(isolated_db) == before - identified


def test_purging_twice_is_a_no_op(isolated_db):
    isolated_db.purge_seeded_analytics(dry_run=False)
    second = isolated_db.purge_seeded_analytics(dry_run=False)
    assert second["deleted"] == 0
    assert not second["seeded"]


def _count(database):
    conn = database.get_db()
    n = conn.execute("SELECT COUNT(*) FROM analytics_daily").fetchone()[0]
    conn.close()
    return n


# --------------------------------------------------------------------------
# Demographics and posts
# --------------------------------------------------------------------------

def test_seeded_demographics_are_recognised_and_removed(isolated_db):
    """
    These 18 rows describe an audience the studio has never observed, and they
    reached the creator through the data export as well as the API. A fabricated
    audience breakdown inside a file labelled as their own data is the worst
    place for one to end up.
    """
    expected = len(isolated_db.demo_demographics_rows())

    dry = isolated_db.purge_seeded_demographics()
    assert dry["seeded"] == expected
    assert dry["deleted"] == 0, "a dry run must not delete"

    report = isolated_db.purge_seeded_demographics(dry_run=False)
    assert report["deleted"] == expected

    conn = isolated_db.get_db()
    left = conn.execute("SELECT COUNT(*) FROM audience_demographics").fetchone()[0]
    conn.close()
    assert left == 0


def test_a_demographic_row_with_a_different_percentage_is_kept(isolated_db):
    """Matching on the label alone would delete a real reading of the same slice."""
    dimension, label, percentage = isolated_db.demo_demographics_rows()[0]

    conn = isolated_db.get_db()
    conn.execute(
        "UPDATE audience_demographics SET percentage = ? WHERE dimension = ? AND label = ?",
        (percentage + 4.2, dimension, label),
    )
    conn.commit()
    conn.close()

    isolated_db.purge_seeded_demographics(dry_run=False)

    conn = isolated_db.get_db()
    row = conn.execute(
        "SELECT percentage FROM audience_demographics WHERE dimension = ? AND label = ?",
        (dimension, label),
    ).fetchone()
    conn.close()
    assert row is not None, "a row that differs from the seeder was deleted"
    assert abs(row["percentage"] - (percentage + 4.2)) < 1e-9


def test_seeded_posts_are_removed_and_authored_posts_are_not(isolated_db):
    """
    Three of the demo posts carry the same figures as the analytics spikes
    (1450/48, 303/10, 28/3), which is what marks them as one fabricated set
    rather than three coincidences.
    """
    conn = isolated_db.get_db()
    conn.execute(
        "INSERT OR REPLACE INTO posts (id, content, status, impressions) VALUES (?, ?, 'published', ?)",
        ("a-post-the-creator-wrote", "Something I actually published.", 77),
    )
    conn.commit()
    conn.close()

    report = isolated_db.purge_seeded_posts(dry_run=False)
    assert report["deleted"] > 0

    conn = isolated_db.get_db()
    mine = conn.execute(
        "SELECT impressions FROM posts WHERE id = ?", ("a-post-the-creator-wrote",)
    ).fetchone()
    seeded_left = conn.execute(
        "SELECT COUNT(*) FROM posts WHERE id IN ({})".format(
            ",".join("?" for _ in isolated_db.DEMO_POST_IDS)
        ),
        isolated_db.DEMO_POST_IDS,
    ).fetchone()[0]
    conn.close()

    assert mine is not None and mine["impressions"] == 77, "an authored post was deleted"
    assert seeded_left == 0


def test_purging_everything_reports_each_table(isolated_db):
    report = isolated_db.purge_all_seeded_data(dry_run=False)
    for table in ("analytics", "demographics", "posts"):
        assert table in report, f"{table} missing from the purge report"
    assert report["analytics"]["deleted"] > 0
    assert report["demographics"]["deleted"] > 0
    assert report["posts"]["deleted"] > 0
