"""
Network reading keeps the creator's own posts, and nothing about anyone else.
=============================================================================

With network reading on, the feed ingest stored a reading for every post in
the creator's LinkedIn feed response: other members' post identities and
their engagement figures, in the creator's database, against "own data only".
The three schemas that carry other members (profiles, reactions on posts,
comments) were relayed to the studio as well, and dropped there.

The feed ingest then kept a reading only for a post that resolved to one of
the creator's own, and this track's migration
(_migrate_reader_timing_and_network_reading) removes what the old behaviour
stored. Network reading was retired in 2.10.2 (tests/
test_network_reading_retired.py): the ingest is gone and its route keeps
nothing, so what is left to hold here is the migration, which every install
from before cycle 4 still runs.

Every name and text here is invented.

Strict Invariants:
- Zero em-dashes.
"""

import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

ME = "privacy-probe-creator"
TEXT = "What three years of shipping a local-first app taught me about the users who stay."


def _urn(hours_ago: float, salt: int) -> str:
    moment = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return "urn:li:activity:" + str((int(moment.timestamp() * 1000) << 22) | salt)


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_t1_voyager_privacy_")
    monkeypatch.setenv("INOX_HYDRA_HOME", os.path.join(home, "studio"))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    yield home
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture
def client(studio):
    import app as app_module
    from fastapi.testclient import TestClient
    client = TestClient(app_module.app)
    client.post("/api/v1/identity/observe", json={"vanity": ME, "self_evidence": ["owner_edit_controls"],
                                                  "display_name": "Privacy Probe"})
    client.post("/api/v1/identity/confirm", json={"vanity": ME})
    return client


def _db():
    from database import get_db
    return get_db()


def _rows(sql, *params):
    conn = _db()
    try:
        return [tuple(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def _own_post(client, urn):
    answer = client.post("/api/v1/self/posts/ingest", json={
        "author": ME, "posts": [{"activity_urn": urn, "actor": ME, "text": TEXT}]})
    assert answer.status_code == 200, answer.text


# ---------------------------------------------------------------------------
# Installs the old behaviour reached
# ---------------------------------------------------------------------------

def test_the_upgrade_removes_what_network_reading_kept_about_other_members(client):
    import migrations
    from database import get_db_path
    mine, theirs = _urn(40, 30), _urn(41, 31)
    _own_post(client, mine)
    now = datetime.now(timezone.utc)
    conn = _db()
    with conn:
        for urn, source, hour in ((mine, "voyager_network", "a"), (mine, "activity_page", "b"),
                                  (theirs, "voyager_network", "c")):
            conn.execute("INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, "
                         "source, impressions) VALUES (?, ?, ?, 10, ?, 100)", (urn, now.isoformat(), hour, source))
        for name, url in (("identity_profiles", "https://www.linkedin.com/voyager/api/identity/profiles/plainwordvanity/"),
                          ("feed_updates", "https://www.linkedin.com/voyager/api/feed/updates/" + theirs),
                          ("social_actions", "https://www.linkedin.com/voyager/api/socialActions/" + theirs)):
            conn.execute("INSERT INTO schema_drift_events (observed_at, schema_name, schema_version, drift_fields, "
                         "confidence, success, source_url) VALUES (?, ?, 'x', NULL, 0, 0, ?)",
                         (now.isoformat(), name, url))
    conn.close()
    assert _rows("SELECT 1 FROM post_engagement WHERE post_urn = ?", theirs), "the old state is not built"

    # A database at 2.7.0's schema, as every install that met the defect is:
    # the migrations after it run in order, this track's among them, which
    # is found by its function, never by its number.
    raw = sqlite3.connect(get_db_path())
    raw.execute("PRAGMA user_version = 27")
    report = migrations.ensure_schema(raw, take_backup=False)
    raw.close()
    ours = next(m[0] for m in migrations.MIGRATIONS if m[2] is migrations._migrate_reader_timing_and_network_reading)
    assert ours in [a["version"] for a in report["applied"]], report

    assert _rows("SELECT 1 FROM post_metric_observations WHERE activity_urn = ?", theirs) == []
    assert sorted(_rows("SELECT source FROM post_metric_observations WHERE activity_urn = ?", mine)) == [
        ("activity_page",), ("voyager_network",)], "the creator's own readings went too"
    assert _rows("SELECT 1 FROM post_engagement WHERE post_urn = ?", theirs) == []
    assert _rows("SELECT schema_name, source_url FROM schema_drift_events") == [
        ("feed_updates", "/voyager/api/feed/updates/_id_")]
