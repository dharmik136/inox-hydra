"""
Posts shows a post's readings as history, and the table says what it holds.
===========================================================================

Batch 6 of the sections report. The studio keeps every reading of a post
from each page it was read on, the reading nearest two days old that Today
compares at, up to twelve names of who each post brought, and whether the
age a post is called settled at was measured from the creator's own posts or
assumed. Posts drew one current value, a count of people, and "only once it
is N days old". Now a post's detail draws its readings as a series per page
("read N times"), with the caveat when older readings were thinned; the
two-day reading, or which of three reasons there is none; the table names
who each post brought; and the usual sentence says whether the settle age is
the creator's own measurement or the studio's assumption.

Strict Invariants:
- Zero em-dashes.
"""

import io
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
COMPONENTS = os.path.join(REPO_ROOT, "studio", "ui", "src", "components")


def _read(*parts):
    with io.open(os.path.join(*parts), encoding="utf-8") as handle:
        return handle.read()


def _urn(hours, salt):
    moment = datetime.now(timezone.utc) - timedelta(hours=hours)
    return "urn:li:activity:" + str((int(moment.timestamp() * 1000) << 22) + salt)


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t4b_posts_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    from fastapi.testclient import TestClient
    import app as app_module
    yield TestClient(app_module.app)
    shutil.rmtree(home, ignore_errors=True)


def _post(hours_old, salt, readings=()):
    """A post of the creator's this many hours old, with (age_hours, source, reactions) readings."""
    from database import get_db
    urn = _urn(hours_old, salt)
    published = (datetime.now(timezone.utc) - timedelta(hours=hours_old)).isoformat()
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, first_seen_at, last_seen_at) "
                     "VALUES (?, 'A post of mine.', ?, ?, ?)", (urn, published, published, published))
        for age, source, reactions in readings:
            at = datetime.fromisoformat(published) + timedelta(hours=age)
            conn.execute(
                "INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, source, "
                "impressions, reactions, comments) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (urn, at.isoformat(), at.strftime("%Y-%m-%dT%H"), age, source, reactions * 30, reactions, 2))
    conn.close()
    return urn


def _detail(client, urn):
    answer = client.get(f"/api/v1/insights/posts/{urn}")
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_the_two_day_reading_is_the_one_nearest_48_hours(studio):
    urn = _post(200, 1, readings=((3, "activity_page", 5), (40, "post_analytics", 20),
                                  (50, "post_analytics", 24), (120, "post_analytics", 30)))
    two = _detail(studio, urn)["two_day"]
    assert two["state"] == "read"
    assert two["reading"]["age_hours"] == 50 and two["reading"]["reactions"] == 24


def test_with_no_two_day_reading_the_detail_says_which_of_three_reasons(studio):
    assert _detail(studio, _post(10, 2))["two_day"]["state"] == "too_new"
    assert _detail(studio, _post(50, 3, readings=((5, "activity_page", 4),)))["two_day"]["state"] == "not_yet"
    old = _detail(studio, _post(300, 4, readings=((5, "activity_page", 4), (200, "post_analytics", 9))))
    assert old["two_day"]["state"] == "missed" and old["two_day"]["reading"] is None


def _readings_rule(value):
    from database import get_db
    conn = get_db()
    with conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('retention_readings', ?)", (value,))
    conn.close()


def test_the_detail_says_when_older_readings_are_thinned(studio):
    urn = _post(200, 5, readings=((3, "activity_page", 5),))
    _readings_rule("off")
    assert _detail(studio, urn)["readings_thinned_after_days"] is None, "the roll-up is off, so nothing is thinned"
    _readings_rule("on")
    assert _detail(studio, urn)["readings_thinned_after_days"] == 30


def test_the_detail_draws_the_series_per_page_and_the_two_day_reading():
    detail = _read(COMPONENTS, "PostDetail.tsx")
    series = detail.split("function Readings")[1].split("\n}\n")[0]
    assert "READ {series.length}" in series and '"TIMES"' in series, "the detail does not say how many times each page was read"
    assert "READ ${" not in series, "a template marker in JSX text draws a dollar sign"
    assert "readings_thinned_after_days" in detail
    assert "two_day" in detail and "AT ABOUT TWO DAYS OLD" in detail


def test_the_table_names_who_each_post_brought_and_says_how_the_settle_age_was_set():
    posts = _read(COMPONENTS, "PostsSurface.tsx")
    row = posts.split("function PostRow")[1].split("\n}\n")[0]
    assert "post.people" in row and "person.name" in row, "the table counts people and names none"
    assert "settled_after.measured" in posts, "the usual sentence does not say whether the settle age was measured"
