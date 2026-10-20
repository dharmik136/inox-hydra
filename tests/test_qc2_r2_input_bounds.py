"""
Inputs outside what the studio stores answer 422, never a 500 or a silent write. [BE-19, BE-20]

A post with status "banana" (or a megabyte of text) was stored and then shown
on no screen. Integers SQLite cannot hold answered 500 with OverflowError, and
limit=-1 returned every row.
"""

import os
import sys

import pytest

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend"))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# The long one carries its own short name: pytest puts the whole parameter in
# the test's id and then in PYTEST_CURRENT_TEST, and Windows refuses an
# environment variable longer than 32767 characters, which errored the setup
# and the teardown of this test there.
@pytest.mark.parametrize("status", [
    "banana",
    pytest.param("x" * 100000, id="a hundred thousand letters"),
    "DRAFT",
])
def test_an_unknown_post_status_is_refused(client, status):
    res = client.post("/api/posts", json={"content": "a post with a made-up status", "status": status})
    assert res.status_code == 422, res.text
    created = client.post("/api/posts", json={"content": "a real draft", "status": "draft"})
    assert created.status_code == 200
    res = client.put(f"/api/posts/{created.json()['id']}", json={"status": status})
    assert res.status_code == 422, res.text


@pytest.mark.parametrize("status", ["draft", "scheduled", "published"])
def test_the_studios_own_statuses_are_accepted(client, status):
    body = {"content": f"a {status} post", "status": status}
    if status == "scheduled":
        body["scheduled_for"] = "2031-01-07T09:00:00+00:00"
    res = client.post("/api/posts", json=body)
    assert res.status_code in (200, 400), res.text  # 400 is the cadence rule, not the status


@pytest.mark.parametrize("url", [
    "/api/v1/analytics/posts/99999999999999999999/leads",
    "/api/v1/self/activity-stream?limit=-1",
    "/api/v1/self/activity-stream?limit=0",
])
def test_out_of_range_integers_answer_422(client, url):
    res = client.get(url)
    assert res.status_code == 422, (url, res.status_code, res.text[:200])


def test_a_huge_limit_is_capped_not_a_500(client):
    res = client.get("/api/v1/self/activity-stream?limit=99999999999999999999")
    assert res.status_code == 200, res.text[:200]
