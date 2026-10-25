"""
Reopening one draft reads one draft.
=====================================

Carried out of cycle 3's integration list as T6-N1's remaining half. T5 put a
`limit=1` on the boot-time read, which closed the part that landed in every
section's first paint. What was left: reopening a draft by id read *every*
draft and searched the list in the browser, because the interface had no way
to ask for one post. The client said so in its own comment, "there is no
single-post route, and the draft list is small", which stopped being true once
a creator had three years of drafts: 259 KB and 1,044 rows to put one post in
an editor.

GET /api/posts/{id} answers the one row, in the same shape as the list.
"""

import os
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    import database
    database.init_db()
    import app as app_module
    import security
    from fastapi.testclient import TestClient
    return TestClient(app_module.app, headers={
        "host": "127.0.0.1:8000",
        security.TOKEN_HEADER: security.get_or_create_token(),
    })


def _draft(client, text):
    made = client.post("/api/posts", json={"content": text, "status": "draft"})
    assert made.status_code == 200, made.text
    return made.json()["id"]


def test_one_post_by_id_answers_that_post(client):
    wanted = _draft(client, "The post the creator means to reopen.\n\nIts body.")
    _draft(client, "Another draft entirely.")

    answer = client.get(f"/api/posts/{wanted}")
    assert answer.status_code == 200, answer.text
    post = answer.json()["post"]
    assert post["id"] == wanted
    assert post["content"].startswith("The post the creator means to reopen.")
    # The same shape as the list, so one caller can read either.
    assert isinstance(post["media_urls"], list) and isinstance(post["tags"], list)
    assert post["status"] == "draft"


def test_an_id_that_is_not_there_is_a_404_not_an_empty_post(client):
    answer = client.get("/api/posts/no-such-post-id")
    assert answer.status_code == 404, answer.text
    assert "no such post" in answer.json()["detail"].lower()


def test_reopening_one_draft_no_longer_reads_them_all(client):
    """
    The saving, measured rather than asserted: one draft against the list the
    interface used to read to find it.
    """
    ids = [_draft(client, f"Draft number {n}.\n\n" + ("A paragraph of the post. " * 40))
           for n in range(60)]

    whole_list = client.get("/api/posts?status=draft")
    assert whole_list.status_code == 200
    assert len(whole_list.json()["posts"]) == 60

    one = client.get(f"/api/posts/{ids[30]}")
    assert one.status_code == 200

    list_bytes = len(whole_list.content)
    one_bytes = len(one.content)
    assert one_bytes * 20 < list_bytes, (
        f"one draft is {one_bytes} bytes and the whole list is {list_bytes}; "
        "asking for one post is meant to cost a fraction of reading all of them"
    )


def test_the_route_does_not_shadow_the_list(client):
    """
    `/api/posts/{post_id}` sits beside `/api/posts`. A path parameter that
    swallowed the collection would break every screen.
    """
    _draft(client, "A draft.")
    listed = client.get("/api/posts?status=draft")
    assert listed.status_code == 200
    assert len(listed.json()["posts"]) == 1
