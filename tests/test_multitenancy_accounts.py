"""
One Database per Creator Profile.
=================================

Profiles used to be rows in one shared database, with an account_id column
nothing filtered by: switching profile changed the avatar and nothing else.
The owner chose real isolation, one database per creator (planning/7 Roadmap/
Decisions Needed.md, decision 3). These hold it to that:

- the first profile is the application home itself, so existing data stays put;
- every other profile is its own folder, with its own database, media,
  backups and exports, and the API reads and writes only the active one;
- a second profile needs an Agency licence;
- deleting a profile needs its name repeated, and removes its folder;
- the background scheduler visits every profile's queue, not only the active one;
- profiles recorded in the old table are adopted.
"""

import base64
import os
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import ed25519  # noqa: E402
import licensing  # noqa: E402
import paths  # noqa: E402
from app import app  # noqa: E402
from database import get_db, init_db  # noqa: E402

TEST_SECRET = bytes(range(32))


def _licence(tier="agency", profiles=5, expires_at="2099-01-01"):
    payload = {
        "v": 1, "id": "test", "email": "buyer@example.com", "name": "", "tier": tier, "kind": "annual",
        "profiles": profiles, "issued_at": "2026-10-19", "expires_at": expires_at, "updates_until": expires_at,
    }
    return licensing.encode(payload, lambda message: ed25519.sign(TEST_SECRET, message))


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    monkeypatch.setattr(licensing, "PUBLIC_KEYS", [base64.b64encode(ed25519.public_key(TEST_SECRET)).decode()])
    init_db()
    return tmp_path


@pytest.fixture
def client(home):
    return TestClient(app)


@pytest.fixture
def agency(client):
    assert client.post("/api/v1/licence", json={"key": _licence()}).status_code == 200
    return client


def _add_post(content):
    conn = get_db()
    conn.execute("INSERT INTO posts (id, content, status) VALUES (?, ?, 'draft')", (content, content))
    conn.commit()
    conn.close()


def _post_ids(client):
    data = client.get("/api/posts").json()
    rows = data.get("posts", data) if isinstance(data, dict) else data
    return {row["id"] for row in rows}


def test_a_fresh_install_has_one_profile_in_the_application_home(client, home):
    data = client.get("/api/v1/accounts").json()
    assert [a["id"] for a in data["accounts"]] == ["default"]
    assert data["active_account_id"] == "default"
    assert data["profile_limit"] == 1
    assert paths.get_db_path() == os.path.join(str(home), "data", paths.DB_FILENAME)
    assert not os.path.exists(paths.get_profiles_file()), "a single-profile install wrote a registry"


def test_a_second_profile_needs_the_agency_licence(client):
    res = client.post("/api/v1/accounts", json={"name": "Client A", "id": "client-a"})
    assert res.status_code == 402
    assert "Agency" in res.json()["detail"]


def test_a_creator_licence_is_still_one_profile(client):
    assert client.post("/api/v1/licence", json={"key": _licence(tier="creator", profiles=1)}).status_code == 200
    assert client.post("/api/v1/accounts", json={"name": "Client A", "id": "client-a"}).status_code == 402


def test_an_expired_agency_licence_does_not_add_profiles(client):
    from datetime import date

    # Installed while it was still current; it has ended since.
    assert licensing.install(_licence(expires_at="2020-01-01"), today=date(2019, 12, 1))["status"] == "success"
    state = client.get("/api/v1/licence").json()
    assert state["status"] == "expired" and state["tier"] == "free"
    assert client.post("/api/v1/accounts", json={"name": "Client A", "id": "client-a"}).status_code == 402


def test_a_new_profile_is_its_own_folder_and_database(agency, home):
    res = agency.post("/api/v1/accounts", json={"name": "Ada Lovelace", "id": "ada"})
    assert res.status_code == 200, res.text
    account = res.json()["account"]
    assert account["avatar_initials"] == "AL" and account["is_default"] is False
    db = os.path.join(str(home), "profiles", "ada", "data", paths.DB_FILENAME)
    assert os.path.isfile(db), "the profile has no database of its own"
    version = sqlite3.connect(db).execute("PRAGMA user_version").fetchone()[0]
    assert version >= 17, "the new profile's database was not brought to the current schema"


def test_the_api_reads_and_writes_only_the_active_profile(agency):
    _add_post("default-post")
    agency.post("/api/v1/accounts", json={"name": "Client A", "id": "client-a"})
    assert agency.post("/api/v1/accounts/switch", json={"account_id": "client-a"}).status_code == 200

    assert "default-post" not in _post_ids(agency), "a client sees the default profile's posts"
    created = agency.post("/api/posts", json={"content": "Client A's own post", "status": "draft"})
    assert created.status_code in (200, 201), created.text

    agency.post("/api/v1/accounts/switch", json={"account_id": "default"})
    ids = _post_ids(agency)
    assert "default-post" in ids
    assert not any("Client A" in str(i) for i in ids)
    listing = {a["id"]: a for a in agency.get("/api/v1/accounts").json()["accounts"]}
    assert listing["client-a"]["posts_count"] == 1 and listing["default"]["posts_count"] == 1


def test_media_is_served_from_the_active_profile(agency):
    with open(os.path.join(paths.get_uploads_dir(), "mine.txt"), "w") as handle:
        handle.write("default media")
    assert agency.get("/assets/uploads/mine.txt").status_code == 200
    agency.post("/api/v1/accounts", json={"name": "Client A", "id": "client-a"})
    agency.post("/api/v1/accounts/switch", json={"account_id": "client-a"})
    assert agency.get("/assets/uploads/mine.txt").status_code == 404, "a client can open the default profile's media"


def test_backups_and_exports_belong_to_the_profile(agency, home):
    import migrations

    agency.post("/api/v1/accounts", json={"name": "Client A", "id": "client-a"})
    with paths.using_profile("client-a"):
        backup = migrations.backup_database("test")
        exports = paths.get_exports_dir()
    profile_home = os.path.join(str(home), "profiles", "client-a")
    assert backup and backup.startswith(profile_home)
    assert exports.startswith(profile_home)


def test_deleting_a_profile_needs_its_name_and_removes_its_folder(agency, home):
    assert agency.delete("/api/v1/accounts/default").status_code == 400
    agency.post("/api/v1/accounts", json={"name": "Temporary Client", "id": "temp-client"})
    agency.post("/api/v1/accounts/switch", json={"account_id": "temp-client"})
    folder = os.path.join(str(home), "profiles", "temp-client")
    assert os.path.isdir(folder)

    refused = agency.request("DELETE", "/api/v1/accounts/temp-client", json={"confirm": "temp"})
    assert refused.status_code == 400 and "Temporary Client" in refused.json()["detail"]
    assert os.path.isdir(folder)

    gone = agency.request("DELETE", "/api/v1/accounts/temp-client", json={"confirm": "Temporary Client"})
    assert gone.status_code == 200 and gone.json()["active_account_id"] == "default"
    assert not os.path.exists(folder)
    assert "temp-client" not in [a["id"] for a in agency.get("/api/v1/accounts").json()["accounts"]]


def test_the_scheduler_visits_every_profile(agency):
    from scheduler import native_scheduler

    agency.post("/api/v1/accounts", json={"name": "Client A", "id": "client-a"})
    with paths.using_profile("client-a"):
        conn = get_db()
        conn.execute(
            "INSERT INTO posts (id, content, status, scheduled_for) VALUES "
            "('due-in-a', 'Due now', 'scheduled', '2020-01-01T09:00:00+00:00')"
        )
        conn.commit()
        conn.close()
    actions = native_scheduler.check_every_profile()
    assert any(a.get("profile_id") == "client-a" for a in actions), "a due post in an inactive profile was never seen"


def test_profiles_from_the_old_table_are_adopted(home, client):
    conn = get_db()
    conn.execute(
        "INSERT INTO creator_accounts (id, name, vanity, headline, avatar_initials, is_default) "
        "VALUES ('old-client', 'Old Client', 'old', 'Founder', 'OC', 0)"
    )
    conn.commit()
    conn.close()
    ids = [a["id"] for a in client.get("/api/v1/accounts").json()["accounts"]]
    assert ids == ["default", "old-client"]


def test_a_tampered_licence_is_refused(client):
    key = _licence()
    head, body, signature = key.split(".")
    forged = ".".join([head, body[:-2] + ("AA" if body[-2:] != "AA" else "BB"), signature])
    res = client.post("/api/v1/licence", json={"key": forged})
    assert res.status_code == 400
    assert client.get("/api/v1/licence").json()["status"] == "none"


def test_strict_zero_em_dashes_in_multitenancy():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    for rel in ("studio/backend/accounts.py", "studio/backend/licensing.py", "studio/backend/ed25519.py",
                "studio/ui/src/components/AccountSwitcher.tsx", "tests/test_multitenancy_accounts.py"):
        with open(os.path.join(base_dir, rel), "r", encoding="utf-8") as handle:
            assert chr(8212) not in handle.read(), f"Forbidden em-dash found in {rel}"


# ---------------------------------------------------------------------------
# Found in review: state that followed the profile active at start-up
# ---------------------------------------------------------------------------

def test_telemetry_is_written_to_the_profile_it_came_from(agency, home):
    from studio.core.telemetry_shard import TelemetryBuffer, TelemetryEngine

    agency.post("/api/v1/accounts", json={"name": "Client A", "id": "client-a"})
    buffer = TelemetryBuffer(engine=TelemetryEngine(), batch_size=100)
    with paths.using_profile("client-a"):
        buffer.ingest("feed", {"n": 1})
    buffer.ingest("feed", {"n": 2})  # staged in the default profile
    assert buffer.flush()["flushed_events"] == 2

    def events(profile_home):
        db = os.path.join(profile_home, "data", "analytics_telemetry.db")
        return sqlite3.connect(db).execute("SELECT payload FROM telemetry_events").fetchall()

    assert events(os.path.join(str(home), "profiles", "client-a")) == [('{"n": 1}',)]
    assert events(str(home)) == [('{"n": 2}',)]


def test_each_profile_has_its_own_template_cache_tag(agency, home):
    from intelligence_sync import IntelligenceSyncEngine

    agency.post("/api/v1/accounts", json={"name": "Client A", "id": "client-a"})
    engine = IntelligenceSyncEngine()
    default_tag = engine.etag_file
    with paths.using_profile("client-a"):
        assert engine.etag_file != default_tag
        assert engine.etag_file.startswith(os.path.join(str(home), "profiles", "client-a"))


def test_the_scheduler_leaves_a_profile_from_a_newer_build_alone(agency, home):
    from scheduler import NativeScheduler

    agency.post("/api/v1/accounts", json={"name": "Client A", "id": "client-a"})
    db = os.path.join(str(home), "profiles", "client-a", "data", paths.DB_FILENAME)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO posts (id, content, status, scheduled_for) VALUES "
                 "('due', 'Due', 'scheduled', '2020-01-01T09:00:00+00:00')")
    conn.execute("PRAGMA user_version = 99")
    conn.commit()
    conn.close()
    NativeScheduler().check_every_profile()
    status = sqlite3.connect(db).execute("SELECT status FROM posts WHERE id = 'due'").fetchone()[0]
    assert status == "scheduled", "the scheduler wrote to a database a newer build owns"


def test_a_backup_is_not_restored_into_another_profile_by_accident(agency, home):
    import support

    _add_post("only-in-default")
    archive = support.create_backup("test")
    agency.post("/api/v1/accounts", json={"name": "Client A", "id": "client-a"})
    agency.post("/api/v1/accounts/switch", json={"account_id": "client-a"})
    with paths.using_profile("client-a"):
        with pytest.raises(ValueError, match="creator profile 'default'"):
            support.restore_backup(archive, take_safety_backup=False)
    with paths.using_profile("default"):
        assert support.restore_backup(archive, take_safety_backup=False)["restored_from"]


def test_old_profile_ids_with_underscores_are_adopted(home, client):
    conn = get_db()
    conn.execute("INSERT INTO creator_accounts (id, name, is_default) VALUES ('acme_labs-1a2b3c', 'Acme Labs', 0)")
    conn.commit()
    conn.close()
    names = {a["name"]: a["id"] for a in client.get("/api/v1/accounts").json()["accounts"]}
    assert names["Acme Labs"] == "acme-labs-1a2b3c"


def test_deleting_the_open_profile_opens_the_default_one(agency, home):
    import migrations

    agency.post("/api/v1/accounts", json={"name": "Client A", "id": "client-a"})
    agency.post("/api/v1/accounts/switch", json={"account_id": "client-a"})
    conn = sqlite3.connect(os.path.join(str(home), "data", paths.DB_FILENAME))
    conn.execute(f"PRAGMA user_version = {migrations.SCHEMA_VERSION - 1}")
    conn.commit()
    conn.close()
    gone = agency.request("DELETE", "/api/v1/accounts/client-a", json={"confirm": "Client A"})
    assert gone.status_code == 200
    version = sqlite3.connect(os.path.join(str(home), "data", paths.DB_FILENAME)).execute(
        "PRAGMA user_version").fetchone()[0]
    assert version == migrations.SCHEMA_VERSION
