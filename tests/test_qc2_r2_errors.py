"""
Every failure answers JSON a person can read. [BE-01, BE-10]

A request with half an emoji in it (a lone UTF-16 surrogate, which is what the
extension's .slice(0, 140) left behind) or a NaN answered a bare
"500 Internal Server Error" in plain text, because FastAPI's own validation
handler crashed echoing the input back. Any other error a route did not catch
answered the same, and a busy or full database looked like the studio refusing
the creator. Now validation answers 422 without the input, a busy or full
database answers 503 with a sentence and a code, and anything else answers 500
JSON that says where the details are, never a traceback.
"""

import inspect
import json
import os
import sqlite3
import sys
import threading
import time

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

LONE_HALF = "Retention went up a lot, honestly \\ud83d"


@pytest.fixture
def client():
    # As a real server answers: an error becomes a response, never a raise.
    return TestClient(app, raise_server_exceptions=False)


def _post_raw(client, path, raw):
    return client.post(path, content=raw.encode("utf-8"), headers={"Content-Type": "application/json"})


def test_a_comment_cut_through_an_emoji_is_stored(client, confirmed_creator):
    """The lone half is dropped and the commenter becomes a lead, as with the emoji whole."""
    body = json.dumps({
        "full_name": "Asha Rao",
        "linkedin_urn": "https://www.linkedin.com/in/asha-rao-qc2",
        "headline": "Head of Growth at Example",
        "interaction_type": "COMMENTED",
        "comment_text": "PLACEHOLDER",
        "post_urn": "urn:li:activity:7300000000000000001",
        "post_author": confirmed_creator,
    }).replace("PLACEHOLDER", LONE_HALF)
    assert "\\ud83d" in body
    res = _post_raw(client, "/api/v1/crm/interactions/ingest", body)
    assert res.status_code == 200, res.text

    from database import get_db

    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT comment_text FROM lead_interactions WHERE comment_text LIKE 'Retention went up%'"
        ).fetchall()
    finally:
        conn.close()
    assert rows, "the commenter's comment was not stored"
    assert all(row[0] == "Retention went up a lot, honestly " for row in rows)


def test_a_whole_emoji_is_kept(client):
    res = client.post("/api/posts", json={"content": "Shipped it \U0001F680 today", "status": "draft"})
    assert res.status_code == 200, res.text
    post = client.get("/api/posts").json()["posts"]
    assert any(p["content"] == "Shipped it \U0001F680 today" for p in post)


@pytest.mark.parametrize("path, raw", [
    ("/api/format/bold", '{"text": NaN}'),
    ("/api/posts", '{"content": NaN}'),
    ("/api/format/bold", '{"text": "unfinished'),
])
def test_nan_and_broken_json_answer_422_json(client, path, raw):
    res = _post_raw(client, path, raw)
    assert res.status_code == 422, res.text
    assert isinstance(res.json()["detail"], list)


@pytest.mark.parametrize("path, raw", [
    ("/api/format/bold", '{"text": "a\\ud800b"}'),
    ("/api/posts", '{"content": "a\\udc00b", "status": "draft"}'),
])
def test_a_lone_half_character_is_dropped_not_a_500(client, path, raw):
    res = _post_raw(client, path, raw)
    assert res.status_code == 200, res.text


def test_an_unexpected_error_answers_500_json_without_a_traceback(client, monkeypatch):
    import today as today_module

    def broken():
        raise RuntimeError("the secret text of a private draft")

    monkeypatch.setattr(today_module, "today_brief", broken)
    res = client.get("/api/v1/today")
    assert res.status_code == 500
    assert res.headers["content-type"].startswith("application/json")
    detail = res.json()["detail"]
    assert detail["code"] == "internal_error"
    assert "log" in detail["message"]
    assert "secret text" not in res.text
    assert "Traceback" not in res.text and "RuntimeError" not in res.text


def test_a_busy_database_answers_503_with_a_code(client):
    created = client.post("/api/posts", json={"content": "first draft", "status": "draft"})
    assert created.status_code == 200, created.text
    post_id = created.json()["id"]

    import paths

    hold = sqlite3.connect(paths.get_db_path(), isolation_level=None, check_same_thread=False)
    hold.execute("BEGIN IMMEDIATE")
    hold.execute("INSERT INTO settings(key, value) VALUES ('qc2_busy_probe', '1') "
                 "ON CONFLICT(key) DO UPDATE SET value = '2'")
    try:
        started = time.monotonic()
        res = client.put(f"/api/posts/{post_id}", json={"content": "edited while busy"})
        took = time.monotonic() - started
    finally:
        hold.execute("ROLLBACK")
        hold.close()
    assert res.status_code == 503, res.text
    assert res.headers.get("retry-after")
    detail = res.json()["detail"]
    assert detail["code"] == "studio_busy"
    assert "Try again" in detail["message"] and "Nothing was saved" in detail["message"]
    assert "refused" not in detail["message"].lower()
    assert took < 15


def test_a_full_disk_answers_503_naming_the_data_folder(client, monkeypatch):
    import today as today_module
    import paths

    def full():
        raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(today_module, "today_brief", full)
    res = client.get("/api/v1/today")
    assert res.status_code == 503
    detail = res.json()["detail"]
    assert detail["code"] == "disk_full"
    assert paths.get_app_home() in detail["message"]


def test_a_damaged_database_answer_says_how_to_restore(client, monkeypatch):
    import today as today_module

    def damaged():
        raise sqlite3.DatabaseError("database disk image is malformed")

    monkeypatch.setattr(today_module, "today_brief", damaged)
    res = client.get("/api/v1/today")
    assert res.status_code == 503
    detail = res.json()["detail"]
    assert detail["code"] == "database_damaged"
    assert "restore" in detail["message"].lower()


def test_a_validation_error_raised_inside_a_route_is_422(client, monkeypatch):
    from pydantic import BaseModel, Field

    class Contract(BaseModel):
        concept: str = Field(..., min_length=3)

    import today as today_module

    monkeypatch.setattr(today_module, "today_brief", lambda: Contract(concept="AI"))
    res = client.get("/api/v1/today")
    assert res.status_code == 422, res.text
    assert "pydantic" not in res.text
    assert "AI" not in json.dumps(res.json()["detail"][0]["loc"])


# The routes that did blocking database and file work on the event loop froze
# every other request, health and the extension's captures included, while
# they waited on a lock. Plain functions run on the thread pool.
@pytest.mark.parametrize("path, method", [
    ("/api/posts/{post_id}/publish-now", "POST"),
    ("/api/queue/toggle-pause", "POST"),
    ("/api/media/upload", "POST"),
])
def test_blocking_routes_do_not_run_on_the_event_loop(path, method):
    def every_route(routes):
        for route in routes:
            included = getattr(route, "original_router", None)
            if included is not None:
                yield from every_route(included.routes)
            else:
                yield route

    for route in every_route(app.routes):
        if getattr(route, "path", None) == path and method in getattr(route, "methods", ()):
            assert not inspect.iscoroutinefunction(route.endpoint), f"{method} {path} is async def"
            return
    pytest.fail(f"{method} {path} not found")


@pytest.fixture(scope="module")
def live_studio():
    """A real server: the test client gives each request its own loop, which hides a blocked one."""
    import socket
    import uvicorn
    from security import get_or_create_token

    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    server = uvicorn.Server(uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", get_or_create_token()
    server.should_exit = True
    thread.join(timeout=5)


def _call(base, token, method, path, body=None):
    import urllib.error
    import urllib.request

    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=data, method=method, headers={
        "X-Inox-Token": token, "Content-Type": "application/json", "Origin": base})
    try:
        with urllib.request.urlopen(request, timeout=30) as answer:
            return answer.status, answer.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


@pytest.mark.parametrize("label", ["publish-now", "toggle-pause"])
def test_health_answers_while_a_write_waits_on_the_lock(live_studio, label):
    """A route waiting on the database lock does not hold up an unrelated request."""
    base, token = live_studio
    status, body = _call(base, token, "POST", "/api/posts", {"content": "mark me posted", "status": "draft"})
    assert status == 200, body
    post_id = json.loads(body)["id"]
    action = {
        "publish-now": ("POST", f"/api/posts/{post_id}/publish-now", None),
        "toggle-pause": ("POST", "/api/queue/toggle-pause", {"paused": False}),
    }[label]

    import paths

    hold = sqlite3.connect(paths.get_db_path(), isolation_level=None, check_same_thread=False)
    hold.execute("BEGIN IMMEDIATE")
    result = {}
    try:
        worker = threading.Thread(target=lambda: result.update(r=_call(base, token, *action)))
        worker.start()
        time.sleep(0.5)
        started = time.monotonic()
        health = _call(base, token, "GET", "/api/v1/health")
        health_took = time.monotonic() - started
    finally:
        hold.execute("ROLLBACK")
        hold.close()
    worker.join(timeout=20)
    assert health[0] == 200
    assert health_took < 1.0, f"health waited {health_took:.2f}s behind a locked {label}"
