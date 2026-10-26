"""
The archive age nudge: one sentence in Setup and Today when the last archive
import is older than a month (capture report, item 25).
=============================================================================

The archive is the record baseline, and importing it again adds nothing
twice, so a monthly loop is cheap to encourage. One sentence, computed once
in archive_age.py, rides on archive_state and on Today's brief, so both
screens say the same thing; a recent import, or none, says nothing.

Strict Invariants:
- Zero em-dashes.
"""

import io
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

import archive_age  # noqa: E402
import archive_import  # noqa: E402
import app as app_module  # noqa: E402
from database import get_db  # noqa: E402

client = TestClient(app_module.app)
NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def _read(path):
    with io.open(os.path.join(REPO_ROOT, path), encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture(autouse=True)
def no_imports():
    def wipe():
        conn = get_db()
        with conn:
            conn.execute("DELETE FROM archive_imports")
        conn.close()
    wipe()
    yield
    wipe()


def _imported(days_ago):
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO archive_imports (archive_name, archive_bytes, imported_at, summary) VALUES (?, ?, ?, ?)",
                     ("Complete_LinkedInDataExport_probe.zip", 1000,
                      (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(),
                      json.dumps({"posts": {"added": 3}})))
    conn.close()


# ---------------------------------------------------------------------------
# The sentence
# ---------------------------------------------------------------------------

def test_no_import_says_nothing():
    assert archive_age.sentence(None, NOW) is None
    assert archive_age.sentence("", NOW) is None
    assert archive_age.sentence("not a date", NOW) is None


def test_a_recent_import_says_nothing():
    assert archive_age.sentence((NOW - timedelta(days=10)).isoformat(), NOW) is None
    # The boundary: a month is 31 days, and the day before it is silent.
    assert archive_age.sentence((NOW - timedelta(days=30)).isoformat(), NOW) is None


def test_a_month_old_import_is_said_in_weeks():
    said = archive_age.sentence((NOW - timedelta(days=31)).isoformat(), NOW)
    assert said.startswith("Your last archive was imported 4 weeks ago.")
    assert "once a month" in said
    assert archive_age.sentence((NOW - timedelta(days=60)).isoformat(), NOW).startswith(
        "Your last archive was imported 8 weeks ago.")


def test_a_date_without_a_zone_is_read_as_utc():
    naive = (NOW - timedelta(days=45)).replace(tzinfo=None).isoformat()
    assert archive_age.sentence(naive, NOW) is not None


# ---------------------------------------------------------------------------
# Where it is said
# ---------------------------------------------------------------------------

def test_the_archive_state_carries_it_only_when_the_import_is_old():
    _imported(3)
    assert archive_import.archive_state()["age_nudge"] is None
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM archive_imports")
    conn.close()
    _imported(40)
    state = archive_import.archive_state()
    assert state["age_nudge"].startswith("Your last archive was imported 5 weeks ago.")
    assert client.get("/api/v1/archive").json()["age_nudge"] == state["age_nudge"]


def test_today_says_the_same_sentence():
    _imported(40)
    brief = client.get("/api/v1/today").json()
    assert brief["archive_age"] == archive_import.archive_state()["age_nudge"]
    assert brief["archive_age"].startswith("Your last archive was imported 5 weeks ago.")


def test_today_says_nothing_when_there_is_nothing_to_say():
    assert client.get("/api/v1/today").json()["archive_age"] is None


def test_the_two_screens_read_the_servers_sentence():
    setup = _read("studio/ui/src/components/ArchiveImport.tsx")
    assert "age_nudge" in setup
    today = _read("studio/ui/src/components/TodaySurface.tsx")
    assert "brief.archive_age" in today
    assert "weeks ago" not in setup and "weeks ago" not in today, "a screen writes the sentence itself"
