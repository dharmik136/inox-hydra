"""
Brand and Settings, split from Brand Studio.
============================================

Batch 5 of the sections report. Brand Studio opened on a Name, Headline and
Company form with five more tabs behind it, the one outright one-view
failure; it answered "who am I in the studio" from settings.creator_profile
while Setup confirmed creator_identity; and "is a LinkedIn session stored"
was answered from two keys, with Delete only on Setup and Save only on Brand
Studio. Now:

- Brand opens on the profile as LinkedIn last showed it, each part with the
  date it was read, and the follower and connection counts on the days they
  were read; the identity and watermark editors are one level down, and the
  identity editor shows both identities side by side.
- Settings opens on an overview (last backup, next cleanup, egress totals,
  licence tier and end, update check, autostart), with Grounding, Local
  security, Storage and privacy and Licence one level down.
- The kept list can be read and a keep taken back; each backup says whether
  it was verified and at which schema; one session control answers from one
  route with Save and Delete, and Setup points to it.

Strict Invariants:
- Zero em-dashes.
"""

import io
import os
import shutil
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
UI = os.path.join(REPO_ROOT, "studio", "ui", "src")


def _read(*parts):
    with io.open(os.path.join(*parts), encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture
def client(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t4b_brand_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    from fastapi.testclient import TestClient
    import app as app_module
    yield TestClient(app_module.app)
    shutil.rmtree(home, ignore_errors=True)


def _profile_read(conn):
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO creator_identity (id, vanity, display_name, headline, about, location, "
            "follower_count, connection_count, profile_observed_at, confirmed_at) VALUES (1, 'brand-creator', "
            "'Asha Rao', 'Head of Operations', 'I run dispatch.', 'Pune', 1200, 480, "
            "'2026-10-20T09:00:00+00:00', '2026-10-01T09:00:00+00:00')")
        conn.execute("INSERT INTO creator_positions (ordinal, title, company, date_range, location, description, "
                     "observed_at) VALUES (0, 'Head of Operations', 'Sample Freight', '2023 - Present', 'Pune', "
                     "'Dispatch and routing.', '2026-10-18T09:00:00+00:00')")
        conn.execute("INSERT INTO creator_education (ordinal, school, degree, date_range, observed_at) VALUES "
                     "(0, 'Sample University', 'BEng', '2010 - 2014', '2026-10-18T09:00:00+00:00')")
        conn.execute("INSERT INTO creator_skills (skill, observed_at) VALUES ('Logistics', '2026-10-19T09:00:00+00:00')")
        conn.execute("INSERT INTO analytics_daily (date, followers, connections, source) VALUES "
                     "('2026-10-10', 1150, 470, 'observed'), ('2026-10-20', 1200, 480, 'observed'), "
                     "('2026-10-15', 9999, 9999, 'seed')")


def test_brand_shows_the_profile_as_last_read_with_each_parts_date(client):
    from database import get_db
    conn = get_db()
    _profile_read(conn)
    conn.close()
    body = client.get("/api/v1/brand/profile").json()
    assert body["profile"]["headline"] == "Head of Operations" and body["profile"]["read_at"] == "2026-10-20T09:00:00+00:00"
    [position] = body["positions"]
    assert position["description"] == "Dispatch and routing." and position["read_at"] == "2026-10-18T09:00:00+00:00"
    assert body["education"][0]["date_range"] == "2010 - 2014"
    assert body["skills"] == [{"skill": "Logistics", "read_at": "2026-10-19T09:00:00+00:00"}]
    assert [p["date"] for p in body["audience"]] == ["2026-10-10", "2026-10-20"], "a seeded day is not a read one"


def test_settings_opens_on_its_overview(client):
    body = client.get("/api/v1/settings/overview").json()
    for part in ("backup", "cleanup", "egress", "licence", "updates", "autostart"):
        assert part in body, f"the overview has no {part}"
    assert body["egress"]["since"] == "the studio started"
    assert {job["job"] for job in body["cleanup"]["jobs"]} == {"telemetry", "readings", "reactions"}
    assert "tier_label" in body["licence"] and "supported" in body["autostart"]


def test_the_kept_list_can_be_read_and_a_keep_taken_back(client):
    from database import get_db
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO leads (id, name, full_name) VALUES ('kept-1', 'Ben Okoro', 'Ben Okoro')")
    conn.close()
    assert client.post("/api/v1/storage/review/keep", json={"lead_ids": ["kept-1"]}).status_code == 200
    [kept] = client.get("/api/v1/storage/kept").json()["kept"]
    assert kept["lead_id"] == "kept-1" and kept["name"] == "Ben Okoro" and kept["kept_at"]
    assert client.delete("/api/v1/storage/kept/kept-1").json()["removed"] == 1
    assert client.get("/api/v1/storage/kept").json()["kept"] == []


def test_each_backup_says_whether_it_was_verified_and_at_which_schema(client):
    made = client.post("/api/v1/support/backup", json={"label": "test"})
    assert made.status_code == 200, made.text
    [backup] = client.get("/api/v1/support/backups").json()["backups"]
    assert "verified" in backup and "schema_version" in backup
    assert backup["verified"] is True and isinstance(backup["schema_version"], int)


def test_one_route_answers_whether_a_session_is_stored_since_when_and_whose(client):
    body = client.get("/api/auth/status").json()
    assert body["client_session"] is False and body["stored"] is False
    assert body["saved_at"] is None and body["account"] is None
    from database import get_db
    conn = get_db()
    with conn:
        # What Setup used to call stored: an li_at on disk, usable or not.
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('li_at', 'sample-not-a-real-session')")
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_token_update', '2026-10-20T09:00:00')")
    conn.close()
    body = client.get("/api/auth/status").json()
    assert body["stored"] is True and body["client_session"] is False, "a stored but unusable session is still stored"
    assert body["saved_at"] == "2026-10-20T09:00:00"


def test_the_rail_points_brand_and_settings_at_their_own_screens():
    app = _read(UI, "App.tsx")
    assert "<BrandSurface" in app and "<SettingsSurface" in app and "<BrandStudioSurface" not in app
    navigation = _read(UI, "lib", "navigation.ts")
    assert "in Brand Studio" not in navigation, "a rail entry still says it opens Brand Studio"


def test_setup_points_to_the_one_session_control():
    setup = _read(UI, "components", "OnboardingSurface.tsx")
    assert "deleteLinkedInSession" not in setup, "Setup still has its own session control"
    surface = _read(UI, "components", "BrandStudioSurface.tsx")
    session = surface.split("function SessionConnection")[1]
    assert "deleteLinkedInSession" in session and "saveSessionCookies" in session, "the one control lacks Save or Delete"
