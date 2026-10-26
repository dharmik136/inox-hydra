"""
Network reading keeps the creator's own posts, and nothing about anyone else.
=============================================================================

With network reading on, the feed ingest stored a reading for every post in
the creator's LinkedIn feed response: other members' post identities and
their engagement figures, in the creator's database, against "own data only".
The three schemas that carry other members (profiles, reactions on posts,
comments) were relayed to the studio as well, and dropped there.

Now the feed ingest keeps a reading only for a post that resolves to one of
the creator's own; every other entry is dropped before anything is written
and counted as a number. The other three schemas never leave the page, and
the studio refuses them. Drift events keep a path cleaned of anything that
names a member or a post. Migration 28 removes what the old behaviour stored.

Every name and text here is invented.

Strict Invariants:
- Zero em-dashes.
"""

import json
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


def _feed(client, data):
    return client.post("/api/v1/bridge/voyager-ingest", json={
        "schema_name": "feed_updates", "schema_version": "2026.10.1", "confidence": 1.0, "data": data,
        "extension_version": "test"})


# ---------------------------------------------------------------------------
# The feed: the creator's own posts only
# ---------------------------------------------------------------------------

def test_a_feed_response_keeps_only_the_creators_own_posts(client):
    mine, theirs, also_theirs = _urn(20, 1), _urn(21, 2), _urn(22, 3)
    _own_post(client, mine)
    answer = _feed(client, [
        {"urn": mine, "likes": 5, "comments": 2, "impressions": 900},
        {"urn": theirs, "likes": 40, "comments": 9, "impressions": 12000},
        {"urn": also_theirs, "likes": 7, "comments": 1, "impressions": 800},
        {"urn": None, "likes": 3},
    ])
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["items_seen"] == 4 and body["items_kept"] == 1 and body["items_dropped"] == 3, body
    assert _rows("SELECT activity_urn FROM post_metric_observations WHERE source = 'voyager_network'") == [(mine,)]
    for urn in (theirs, also_theirs):
        assert _rows("SELECT 1 FROM post_metric_observations WHERE activity_urn = ?", urn) == [], urn
        assert _rows("SELECT 1 FROM post_engagement WHERE post_urn = ?", urn) == [], "a stranger's post has a summary"
        assert _rows("SELECT 1 FROM own_posts WHERE activity_urn = ?", urn) == []
        assert _rows("SELECT 1 FROM posts WHERE activity_urn = ?", urn) == []
    assert _rows("SELECT impressions FROM own_posts WHERE activity_urn = ?", mine) == [(900,)]
    # The run says how many entries it dropped, and nothing else about them.
    run = _rows("SELECT items_seen, items_kept, items_dropped FROM captures "
                "WHERE extractor = 'voyager_feed_updates' ORDER BY id DESC LIMIT 1")
    assert run == [(4, 1, 3)], run
    dump = json.dumps(_rows("SELECT * FROM captures"))
    assert theirs not in dump and also_theirs not in dump


def test_a_feed_of_other_members_writes_nothing_about_them(client):
    theirs = [_urn(30 + i, 10 + i) for i in range(3)]
    answer = _feed(client, [{"urn": u, "likes": 4, "impressions": 100} for u in theirs])
    assert answer.status_code == 200, answer.text
    assert answer.json()["items_kept"] == 0 and answer.json()["items_dropped"] == 3
    assert _rows("SELECT COUNT(*) FROM post_metric_observations") == [(0,)]
    assert _rows("SELECT COUNT(*) FROM post_engagement") == [(0,)]


def test_a_post_the_studio_carries_counts_as_the_creators(client):
    """A studio post bound to its LinkedIn id is the creator's, with or without a publication record."""
    carried = _urn(3, 20)
    conn = _db()
    with conn:
        conn.execute("INSERT INTO posts (id, content, status, activity_urn) VALUES ('post-carried', ?, 'published', ?)",
                     (TEXT, carried))
    conn.close()
    assert _feed(client, [{"urn": carried, "likes": 2, "impressions": 50}]).json()["items_kept"] == 1


# ---------------------------------------------------------------------------
# The schemas that carry other members
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("schema, data", [
    ("identity_profiles", [{"vanity": "someone-else", "firstName": "Some", "lastName": "One",
                            "headline": "Founder at Example"}]),
    ("social_actions", [{"actorUrn": "urn:li:fsd_profile:ACoAAAexample", "actorName": "Some One",
                         "reactionType": "LIKE"}]),
    ("feed_comments", [{"commenterName": "Some One", "text": "Well put.", "commenterProfileUrl": "someone-else"}]),
])
def test_the_schemas_that_carry_other_members_are_not_kept(client, schema, data):
    before = {table: _rows(f"SELECT COUNT(*) FROM {table}")[0][0]
              for table in ("leads", "lead_interactions", "post_metric_observations", "captures")}
    answer = client.post("/api/v1/bridge/voyager-ingest", json={"schema_name": schema, "schema_version": "x",
                                                                 "confidence": 1.0, "data": data})
    assert answer.status_code == 409, answer.text
    after = {table: _rows(f"SELECT COUNT(*) FROM {table}")[0][0] for table in before}
    assert after == before, f"{schema} wrote {after} from {before}"


def test_drift_is_kept_with_a_path_that_names_nobody(client):
    answer = client.post("/api/v1/bridge/schema-drift", json={
        "schema_name": "feed_updates", "schema_version": "2026.10.1", "drift_fields": ["elements[*].entityUrn"],
        "confidence": 0.0, "success": False,
        "source_url": "https://www.linkedin.com/voyager/api/feed/updates/urn:li:activity:7385000000000000001/plainwordvanity",
        "response_top_keys": ["data", "included"]})
    assert answer.status_code == 200, answer.text
    assert _rows("SELECT source_url FROM schema_drift_events") == [("/voyager/api/feed/updates/_id_/_id_",)]
    refused = client.post("/api/v1/bridge/schema-drift", json={
        "schema_name": "identity_profiles", "schema_version": "x", "drift_fields": ["vanity"],
        "source_url": "https://www.linkedin.com/voyager/api/identity/profiles/plainwordvanity/profileView"})
    assert refused.status_code == 409
    assert len(_rows("SELECT 1 FROM schema_drift_events")) == 1


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
