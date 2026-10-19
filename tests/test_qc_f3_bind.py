"""
A repost's permalink cannot claim the creator's post.
=====================================================

BRIDGE-24  Opening the permalink of someone's plain repost of the creator's
           post shows the creator's text. The bridge offered that page's URN
           for binding with no author, the studio matched the text and bound
           the repost's activity id to the studio post, and the creator's real
           post then never bound. Now the bridge does not offer a repost, says
           whose post it read, and the studio refuses a post that names
           another author.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

import app as app_module
from database import get_db

from qc_f3_pages import Pages, page_html

client = TestClient(app_module.app)


def _armed():
    text = f"Shipping notes from week forty {uuid.uuid4().hex[:6]}: the sync engine survives a lid closing mid write."
    response = client.post("/api/v1/posts/injected", json={"content": text})
    assert response.json()["status"] == "recorded"
    return text, response.json()["post_id"]


def _urn_of(post_id):
    conn = get_db()
    try:
        return conn.execute("SELECT activity_urn FROM posts WHERE id = ?", (post_id,)).fetchone()["activity_urn"]
    finally:
        conn.close()


def test_a_post_by_another_author_does_not_bind(confirmed_creator):
    text, post_id = _armed()
    repost = f"urn:li:activity:73870000{uuid.uuid4().int % 10**11:011d}"
    answer = client.post("/api/v1/posts/bind-urn",
                         json={"activity_urn": repost, "post_text": text, "post_author": "a-follower"}).json()
    assert answer["status"] == "not_yours" and answer["bound"] is False
    assert _urn_of(post_id) is None

    real = f"urn:li:activity:73870001{uuid.uuid4().int % 10**11:011d}"
    answer = client.post("/api/v1/posts/bind-urn",
                         json={"activity_urn": real, "post_text": text, "post_author": confirmed_creator}).json()
    assert answer["status"] == "bound"
    assert _urn_of(post_id) == real


# ---------------------------------------------------------------------------
# The bridge's half
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pages():
    p = Pages()
    yield p
    p.close()


TEXT = "Shipping notes from week forty: the sync engine finally survives a laptop lid closing mid write."

OWN = page_html(f"""
<main>
 <div class="feed-shared-update-v2" data-urn="urn:li:activity:7387000000000000123">
   <div class="update-components-actor"><a class="update-components-actor__meta-link" href="https://www.linkedin.com/in/test-creator/">Test Creator</a></div>
   <div class="update-components-text">{TEXT}</div>
 </div>
</main>""")

REPOST = page_html(f"""
<main>
 <div class="feed-shared-update-v2" data-urn="urn:li:activity:7387000000000009999">
   <div class="update-components-header"><span class="update-components-header__text-view"><a href="https://www.linkedin.com/in/a-follower/">A Follower</a> reposted this</span></div>
   <div class="update-components-actor"><a class="update-components-actor__meta-link" href="https://www.linkedin.com/in/test-creator/">Test Creator</a></div>
   <div class="update-components-text">{TEXT}</div>
 </div>
</main>""")


def test_your_own_post_is_offered_with_its_author(pages):
    page = pages.open("/feed/update/urn:li:activity:7387000000000000123/", OWN)
    page.clock.run_for(3000)
    sent = pages.sent(page, "/api/v1/posts/bind-urn")
    assert sent == [{"activity_urn": "urn:li:activity:7387000000000000123", "post_text": TEXT,
                     "post_author": "test-creator"}]


def test_a_repost_is_not_offered_for_binding(pages):
    page = pages.open("/feed/update/urn:li:activity:7387000000000009999/", REPOST)
    page.clock.run_for(3000)
    assert pages.sent(page, "/api/v1/posts/bind-urn") == []
