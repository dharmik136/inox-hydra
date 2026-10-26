"""
Replies: who commented on my posts that I have not answered, oldest-seen first?
==============================================================================

Cycle 4, track 4, batch 3 of the sections report, and decision 9.

Today lists five people. The full set of comments on the creator's own posts
was held in lead_interactions and shown nowhere but one person or one post at
a time. Replies lists every one in the window, grouped by post, oldest seen
first, with the commenter's own words.

Two rules carry the honesty of the section:

  - Whether a creator answered is not something the bridge reads, so the
    only "answered" is the creator's own mark (reply_marks). Today's rule
    that a lead status of Outreach Sent, Connected or Meeting Booked means
    answered is kept, because the two lists must agree.
  - A comment's time is when the studio first saw it: the bridge stamps the
    row when it reads the page (crm.py writes CURRENT_TIMESTAMP), so the
    screen says "seen by the studio", never "commented at".

Strict Invariants:
- Zero em-dashes.
- No ordering of people by score.
"""

import io
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

UI = os.path.join(REPO_ROOT, "studio", "ui", "src")

ME = "replies-creator"


def _read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def _stamp(days_ago, hours=0):
    """The form crm.py stores: CURRENT_TIMESTAMP, UTC, without a zone."""
    return (datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours)).strftime("%Y-%m-%d %H:%M:%S")


def _urn(days_ago, salt=0):
    moment = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return "urn:li:activity:" + str((int(moment.timestamp() * 1000) << 22) + salt)


POST_ONE = _urn(6, 1)
POST_TWO = _urn(3, 2)
SOMEONE_ELSES = _urn(4, 3)


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t4_replies_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    from migrations import interaction_comment_key
    init_db()
    conn = get_db()
    with conn:
        conn.execute("INSERT OR REPLACE INTO creator_identity (id, vanity, display_name, confirmed_at) "
                     "VALUES (1, ?, 'Replies Creator', '2026-10-01T00:00:00+00:00')", (ME,))
        for urn, text, days in ((POST_ONE, "The rota is a culture document.", 6),
                                (POST_TWO, "Nobody reads your roadmap.", 3)):
            published = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, first_seen_at, last_seen_at) "
                         "VALUES (?, ?, ?, ?, ?)", (urn, text, published, _stamp(days), _stamp(days)))
        people = (
            ("lead-a", "Asha Rao", None, 10.0),
            ("lead-b", "Ben Okoro", None, 95.0),
            ("lead-c", "Cora Lind", None, 50.0),
            ("lead-d", "Dev Patel", None, 40.0),
            ("lead-e", "Eli Moss", None, 30.0),
            ("lead-f", "Fay Wu", "DM_SENT", 20.0),
        )
        for lead_id, name, status, score in people:
            conn.execute("INSERT INTO leads (id, name, full_name, headline, lead_status, icp_score) VALUES (?, ?, ?, ?, ?, ?)",
                         (lead_id, name, name, f"Headline of {name}", status, score))

        def comment(lead_id, post, text, seen, kind="COMMENT"):
            conn.execute(
                "INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, comment_text, interacted_at, "
                "comment_key, first_seen_at, last_seen_at, seen_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
                (lead_id, post, kind, text if kind == "COMMENT" else None, seen,
                 interaction_comment_key(text if kind == "COMMENT" else None), seen, seen))

        # Asha has the lowest score and commented on both posts.
        comment("lead-a", POST_ONE, "This matches what we saw last year.", _stamp(3))
        comment("lead-a", POST_TWO, "Which roadmap tool did you use?", _stamp(1))
        # Ben has the highest score and was seen first of all, on post one.
        comment("lead-b", POST_ONE, "We stopped counting story points too.", _stamp(5))
        # Cora only reacted: nothing to reply to.
        comment("lead-c", POST_ONE, None, _stamp(2), kind="LIKE")
        # Dev commented twenty days ago, outside the default window.
        comment("lead-d", POST_TWO, "An old comment.", _stamp(20))
        # Eli commented on someone else's post.
        comment("lead-e", SOMEONE_ELSES, "Not on your post.", _stamp(2))
        # Fay has already been answered, by her lead status.
        comment("lead-f", POST_ONE, "Thanks for this.", _stamp(2))
    conn.close()
    yield home
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture
def client(studio):
    from fastapi.testclient import TestClient
    import app as app_module
    return TestClient(app_module.app)


def _flat(body):
    """(name, post activity urn, comment) in the order the screen draws them."""
    return [(c["name"], group["activity_urn"], c["comment_text"]) for group in body["posts"] for c in group["comments"]]


# ---------------------------------------------------------------------------
# Who is waiting, in which order
# ---------------------------------------------------------------------------

def test_every_comment_waiting_on_your_posts_is_listed_grouped_by_post_oldest_seen_first(client):
    body = client.get("/api/v1/replies").json()
    assert body["window"] == {"days": 14, "label": "last 14 days", "since": body["window"]["since"]}
    assert _flat(body) == [
        ("Ben Okoro", POST_ONE, "We stopped counting story points too."),
        ("Asha Rao", POST_ONE, "This matches what we saw last year."),
        ("Asha Rao", POST_TWO, "Which roadmap tool did you use?"),
    ]
    assert body["counts"]["waiting"] == 3
    assert body["counts"]["people"] == 2
    assert body["counts"]["posts"] == 2
    first = body["posts"][0]
    assert first["excerpt"].startswith("The rota is a culture document.")
    assert first["url"] == f"https://www.linkedin.com/feed/update/{POST_ONE}/"
    assert first["waiting"] == 2


def test_people_are_never_ordered_by_score(client):
    """Ben's 95 and Asha's 10 change nothing: the order is when the studio saw each comment."""
    from database import get_db
    conn = get_db()
    with conn:
        conn.execute("UPDATE leads SET icp_score = 99 WHERE id = 'lead-a'")
        conn.execute("UPDATE leads SET icp_score = 1 WHERE id = 'lead-b'")
    conn.close()
    names = [name for name, _post, _text in _flat(client.get("/api/v1/replies").json())]
    assert names == ["Ben Okoro", "Asha Rao", "Asha Rao"]
    source = _read(os.path.join(REPO_ROOT, "studio", "backend", "replies.py"))
    assert "icp_score" not in source, "the replies module reads the score"


def test_a_comment_read_again_keeps_the_time_it_was_first_seen(client):
    """last_seen_at moves every time the post is reopened; the order and the time shown do not."""
    from database import get_db
    conn = get_db()
    with conn:
        first_seen = conn.execute("SELECT first_seen_at FROM lead_interactions WHERE lead_id = 'lead-b'").fetchone()[0]
        conn.execute("UPDATE lead_interactions SET last_seen_at = ? WHERE lead_id = 'lead-b'", (_stamp(0),))
    conn.close()
    body = client.get("/api/v1/replies").json()
    ben = body["posts"][0]["comments"][0]
    assert ben["name"] == "Ben Okoro", "a re-read comment jumped the queue"
    assert ben["seen_at"] == first_seen


def test_the_window_is_configurable_and_bounded(client):
    body = client.get("/api/v1/replies?days=30").json()
    assert body["window"]["label"] == "last 30 days"
    assert ("Dev Patel", POST_TWO, "An old comment.") in _flat(body)
    assert client.get("/api/v1/replies?days=0").status_code == 422
    assert client.get("/api/v1/replies?days=400").status_code == 422


def test_the_first_view_pages_by_post(client):
    page_one = client.get("/api/v1/replies?limit=1").json()
    assert page_one["unit"] == "posts" and page_one["total"] == 2
    assert [g["activity_urn"] for g in page_one["posts"]] == [POST_ONE]
    assert len(page_one["posts"][0]["comments"]) == 2
    assert page_one["next_offset"] == 1
    page_two = client.get("/api/v1/replies?limit=1&offset=1").json()
    assert _flat(page_two) == [("Asha Rao", POST_TWO, "Which roadmap tool did you use?")]
    assert page_two["next_offset"] is None


def _post_id(urn):
    return urn.rsplit(":", 1)[1]


def test_a_busy_post_shows_its_longest_waiting_comments_and_opens_to_all_of_them(client):
    """
    One post with a hundred comments waiting filled the first view and hid
    every other post. The first view shows each post's first few, and the
    post opens to the rest.
    """
    from database import get_db
    from migrations import interaction_comment_key
    import replies
    conn = get_db()
    with conn:
        for n in range(5):
            lead_id = f"lead-busy-{n}"
            conn.execute("INSERT INTO leads (id, name, full_name, lead_status) VALUES (?, ?, ?, 'NEW')",
                         (lead_id, f"Busy {n}", f"Busy {n}"))
            text = f"Busy comment {n}"
            conn.execute(
                "INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, comment_text, interacted_at, "
                "comment_key, first_seen_at, last_seen_at) VALUES (?, ?, 'COMMENT', ?, ?, ?, ?, ?)",
                (lead_id, POST_TWO, text, _stamp(0, hours=10 - n), interaction_comment_key(text),
                 _stamp(0, hours=10 - n), _stamp(0, hours=10 - n)))
    conn.close()

    first = client.get("/api/v1/replies").json()
    busy = [g for g in first["posts"] if g["activity_urn"] == POST_TWO][0]
    assert busy["in_view"] == 6 and busy["waiting"] == 6
    assert len(busy["comments"]) == replies.PER_POST
    assert busy["comments"][0]["name"] == "Asha Rao", "the longest waiting comes first"

    opened = client.get(f"/api/v1/replies?post={_post_id(POST_TWO)}").json()
    assert opened["unit"] == "comments" and opened["total"] == 6
    names = [c["name"] for c in opened["posts"][0]["comments"]]
    assert names == ["Asha Rao", "Busy 0", "Busy 1", "Busy 2", "Busy 3", "Busy 4"]
    paged = client.get(f"/api/v1/replies?post={_post_id(POST_TWO)}&limit=2&offset=2").json()
    assert [c["name"] for c in paged["posts"][0]["comments"]] == ["Busy 1", "Busy 2"]
    assert paged["next_offset"] == 4
    assert client.get("/api/v1/replies?post=not-an-id").status_code == 422


# ---------------------------------------------------------------------------
# The creator's own mark
# ---------------------------------------------------------------------------

def _mark(client, comment, path="/api/v1/replies/mark"):
    return client.post(path, json={"lead_id": comment["lead_id"], "post_urn": comment["post_urn"],
                                   "comment_key": comment["comment_key"]})


def test_marking_a_comment_answered_takes_it_off_the_list_and_onto_the_answered_list(client):
    body = client.get("/api/v1/replies").json()
    ben = body["posts"][0]["comments"][0]
    answer = _mark(client, ben)
    assert answer.status_code == 200, answer.text
    assert answer.json()["marked_at"]

    body = client.get("/api/v1/replies").json()
    assert [name for name, _p, _t in _flat(body)] == ["Asha Rao", "Asha Rao"]
    assert body["counts"]["waiting"] == 2
    assert body["counts"]["answered_last_7_days"] == 1

    answered = client.get("/api/v1/replies?view=answered").json()
    assert _flat(answered) == [("Ben Okoro", POST_ONE, "We stopped counting story points too.")]
    assert answered["posts"][0]["comments"][0]["marked_at"] == answer.json()["marked_at"]


def test_a_mark_can_be_taken_back(client):
    ben = client.get("/api/v1/replies").json()["posts"][0]["comments"][0]
    _mark(client, ben)
    assert _mark(client, ben, "/api/v1/replies/unmark").status_code == 200
    assert client.get("/api/v1/replies").json()["counts"]["waiting"] == 3


def test_a_mark_for_a_comment_the_studio_does_not_hold_is_refused(client):
    answer = client.post("/api/v1/replies/mark", json={"lead_id": "lead-a", "post_urn": POST_ONE, "comment_key": "nope"})
    assert answer.status_code == 404
    from database import get_db
    conn = get_db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM reply_marks").fetchone()[0] == 0
    finally:
        conn.close()


def test_the_empty_list_names_how_many_were_answered_in_the_last_week(client):
    body = client.get("/api/v1/replies").json()
    for group in body["posts"]:
        for comment in group["comments"]:
            _mark(client, comment)
    body = client.get("/api/v1/replies").json()
    assert body["posts"] == [] and body["counts"]["waiting"] == 0
    assert body["counts"]["answered_last_7_days"] == 3
    surface = _read(os.path.join(UI, "components", "RepliesSurface.tsx"))
    assert "answered_last_7_days" in surface, "the empty state does not name the count answered"


def test_before_the_studio_knows_who_you_are_nothing_is_listed(client):
    from database import get_db
    conn = get_db()
    with conn:
        conn.execute("UPDATE creator_identity SET confirmed_at = NULL")
    conn.close()
    body = client.get("/api/v1/replies").json()
    assert body["identity_known"] is False
    assert body["posts"] == [] and body["counts"]["waiting"] == 0


# ---------------------------------------------------------------------------
# Today and Replies agree
# ---------------------------------------------------------------------------

def test_today_counts_what_replies_lists_and_leaves_off_what_was_marked(client):
    today = client.get("/api/v1/today").json()
    assert today["replies"]["waiting"] == 3
    assert today["replies"]["window_days"] == 14
    assert {p["name"] for p in today["reply_to"]} == {"Asha Rao", "Ben Okoro"}

    ben = client.get("/api/v1/replies").json()["posts"][0]["comments"][0]
    _mark(client, ben)
    today = client.get("/api/v1/today").json()
    assert today["replies"]["waiting"] == 2
    assert {p["name"] for p in today["reply_to"]} == {"Asha Rao"}, "a person whose only comment is marked answered is still listed"


def test_a_person_with_one_comment_answered_and_one_waiting_stays_on_today(client):
    body = client.get("/api/v1/replies").json()
    asha_on_post_one = [c for c in body["posts"][0]["comments"] if c["name"] == "Asha Rao"][0]
    _mark(client, asha_on_post_one)
    names = {p["name"] for p in client.get("/api/v1/today").json()["reply_to"]}
    assert "Asha Rao" in names, "her comment on the second post is still waiting"


# ---------------------------------------------------------------------------
# What the screen says
# ---------------------------------------------------------------------------

def test_the_screen_says_seen_by_the_studio_and_never_commented_at():
    surface = _read(os.path.join(UI, "components", "RepliesSurface.tsx"))
    assert re.search(r"seen by the studio", surface, re.I)
    rendered = re.sub(r"/\*.*?\*/|//[^\n]*|\{/\*.*?\*/\}", "", surface, flags=re.S)
    assert not re.search(r"commented (at|on \{|\$\{)", rendered, re.I), "a capture time is shown as when they commented"


def test_replies_has_a_help_article_filed_for_a_creator():
    import docs_engine
    shipped = [path for section in docs_engine.HELP_SECTIONS if section["id"] != "maintainers"
               for path in section["paths"]]
    assert "help/answer-the-people-waiting-on-a-reply.md" in shipped
    article = _read(os.path.join(REPO_ROOT, "docs", "help", "answer-the-people-waiting-on-a-reply.md"))
    assert "seen by the studio" in article.lower()
    assert "Answered" in article
