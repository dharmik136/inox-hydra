"""
Post Attribution
================
The chain that answers "which of my posts produced my best leads".

Three attribution surfaces have existed in this codebase since early on and all
three were correct: crm.py joins leads to posts, the leaderboard join in app.py
ranks by attributed engagement, and /api/v1/analytics/posts/{id}/leads answers
the question directly. Every one of them returned zero for the product's entire
existence, because nothing ever recorded which post an engagement belonged to.
On the install this was built for, lead_interactions.post_id was populated on 0
of 842 rows.

The chain has three links and the middle one is the only one that reads
LinkedIn:

  1. The creator injects a draft. The studio caused that, so it records a row
     with a fingerprint of the text.
  2. The creator opens their own post. The URL carries the activity URN and the
     page carries the text; if the text matches, the URN belongs to that row.
  3. Engagers captured from that page carry the URN.

The end-to-end test below is the one that matters. Each link works in isolation
in the tests around it, and the whole point is that they did not work together.
"""

import os
import re

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONTENT_JS = os.path.join(REPO_ROOT, "studio", "extension", "content.js")

POST_TEXT = (
    "Stepping into enterprise systems feels like learning a completely new "
    "language. Six months in, here is the part nobody warned me about: the "
    "hard problem is never the database."
)
ACTIVITY_URN = "urn:li:activity:7504139397143883776"


@pytest.fixture
def client():
    import studio.backend.app as app_module
    return TestClient(app_module.app, raise_server_exceptions=False)


@pytest.fixture
def cleanup():
    """Remove whatever a test created, so the shared sandbox stays predictable."""
    created = {"posts": [], "leads": []}
    yield created

    from studio.backend.database import get_db
    conn = get_db()
    for pid in created["posts"]:
        conn.execute("DELETE FROM posts WHERE id = ?", (pid,))
    for lid in created["leads"]:
        conn.execute("DELETE FROM lead_interactions WHERE lead_id = ?", (lid,))
        conn.execute("DELETE FROM leads WHERE id = ?", (lid,))
    conn.execute("DELETE FROM posts WHERE activity_urn = ?", (ACTIVITY_URN,))
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------
# The fingerprint
# --------------------------------------------------------------------------

def test_a_post_is_recognised_after_linkedin_reformats_it():
    """
    LinkedIn rewrites whitespace and the studio's own formatter emits bold
    unicode letterforms, so a hash of the raw text would never match. The
    fingerprint compares the alphanumeric spine of the opening.
    """
    from studio.backend.post_identity import content_fingerprint, fingerprint_matches

    fp = content_fingerprint(POST_TEXT)
    assert fp is not None

    bold = "".join(
        chr(0x1D5D4 + ord(c) - ord("A")) if "A" <= c <= "Z"
        else chr(0x1D5EE + ord(c) - ord("a")) if "a" <= c <= "z"
        else c
        for c in POST_TEXT
    )

    for label, variant in [
        ("as typed", POST_TEXT),
        ("whitespace rewritten", POST_TEXT.replace(" ", "  ")),
        ("bold letterforms", bold),
        ("emoji prepended", "\U0001F680 " + POST_TEXT),
        ("hashtags appended", POST_TEXT + "\n\n#architecture #systems"),
    ]:
        assert fingerprint_matches(variant, fp), f"failed to recognise: {label}"


def test_a_different_post_is_not_recognised():
    """A wrong binding attributes one post's engagers to another, silently."""
    from studio.backend.post_identity import content_fingerprint, fingerprint_matches

    fp = content_fingerprint(POST_TEXT)
    assert not fingerprint_matches(
        "A completely different post about how we approach hiring engineers.", fp
    )
    # Shares an opening, then diverges.
    assert not fingerprint_matches(POST_TEXT[:45] + " and then something else entirely happened.", fp)


def test_text_too_short_to_identify_is_refused():
    """Two words would match half the creator's drafts."""
    from studio.backend.post_identity import content_fingerprint
    assert content_fingerprint("Shipped it") is None
    assert content_fingerprint("") is None


# --------------------------------------------------------------------------
# The routes
# --------------------------------------------------------------------------

def test_injection_records_a_post_that_can_be_found_again(client, cleanup):
    res = client.post("/api/v1/posts/injected", json={"content": POST_TEXT})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "recorded"
    cleanup["posts"].append(body["post_id"])

    from studio.backend.database import get_db
    conn = get_db()
    row = conn.execute(
        "SELECT content_fingerprint, activity_urn, published_at FROM posts WHERE id = ?",
        (body["post_id"],),
    ).fetchone()
    conn.close()

    assert row["content_fingerprint"] == body["content_fingerprint"]
    assert row["activity_urn"] is None, "the URN is not known until the post is opened"
    assert row["published_at"] is not None


def test_injecting_the_same_text_twice_does_not_create_a_competitor(client, cleanup):
    """
    A retry must not leave two unbound rows with the same fingerprint, or the
    URN would attach to whichever one the query happened to return first.
    """
    first = client.post("/api/v1/posts/injected", json={"content": POST_TEXT}).json()
    second = client.post("/api/v1/posts/injected", json={"content": POST_TEXT}).json()
    cleanup["posts"].extend([first["post_id"], second["post_id"]])

    assert first["post_id"] == second["post_id"]


def test_a_post_too_short_to_identify_is_reported_rather_than_stored(client):
    res = client.post("/api/v1/posts/injected", json={"content": "Shipped."})
    assert res.json()["status"] == "too_short"


def test_binding_attaches_the_urn_to_the_matching_post(client, cleanup):
    injected = client.post("/api/v1/posts/injected", json={"content": POST_TEXT}).json()
    cleanup["posts"].append(injected["post_id"])

    res = client.post("/api/v1/posts/bind-urn", json={
        "activity_urn": f"/feed/update/{ACTIVITY_URN}/",
        "post_text": POST_TEXT + "\n\n#systems",
    })
    body = res.json()
    assert body["status"] == "bound", body
    assert body["post_id"] == injected["post_id"]
    assert body["activity_urn"] == ACTIVITY_URN


def test_binding_refuses_when_nothing_matches(client, cleanup):
    """
    Refusing is the whole safety property. A wrong binding would attribute one
    post's engagers to another and be very hard to notice afterwards.
    """
    injected = client.post("/api/v1/posts/injected", json={"content": POST_TEXT}).json()
    cleanup["posts"].append(injected["post_id"])

    body = client.post("/api/v1/posts/bind-urn", json={
        "activity_urn": ACTIVITY_URN,
        "post_text": "Somebody else's post that I happened to open today.",
    }).json()

    assert body["status"] == "no_match"
    assert body["bound"] is False

    from studio.backend.database import get_db
    conn = get_db()
    row = conn.execute(
        "SELECT activity_urn FROM posts WHERE id = ?", (injected["post_id"],)
    ).fetchone()
    conn.close()
    assert row["activity_urn"] is None, "a non-matching post was bound anyway"


def test_a_malformed_urn_is_refused(client):
    body = client.post("/api/v1/posts/bind-urn", json={
        "activity_urn": "not-a-urn", "post_text": POST_TEXT,
    }).json()
    assert body["status"] == "invalid_urn"
    assert body["bound"] is False


# --------------------------------------------------------------------------
# End to end
# --------------------------------------------------------------------------

def test_the_whole_chain_answers_who_engaged_with_which_post(client, cleanup):
    """
    The question this product exists to answer, asked of data that travelled
    the real path: injected, bound, captured, queried.
    """
    injected = client.post("/api/v1/posts/injected", json={"content": POST_TEXT}).json()
    post_id = injected["post_id"]
    cleanup["posts"].append(post_id)

    # Before binding, the studio says so rather than returning an empty list
    # that looks like "nobody engaged".
    early = client.get(f"/api/v1/posts/{post_id}/engagers").json()
    assert early["status"] == "unbound"

    bound = client.post("/api/v1/posts/bind-urn", json={
        "activity_urn": f"/feed/update/{ACTIVITY_URN}/",
        "post_text": POST_TEXT,
    }).json()
    assert bound["bound"] is True

    # Two people engage, as the extension would report them.
    for name, headline, itype, comment in [
        ("Priya Raman", "VP of Engineering at Northwind", "COMMENT",
         "How did you handle the migration without downtime?"),
        ("Tom Alvarez", "Software Engineer at Acme", "LIKE", ""),
    ]:
        r = client.post("/api/v1/crm/interactions/ingest", json={
            "full_name": name,
            "linkedin_urn": f"https://www.linkedin.com/in/{name.lower().replace(' ', '-')}",
            "headline": headline,
            "interaction_type": itype,
            "comment_text": comment,
            "post_urn": ACTIVITY_URN,
            "capture_context": f"/feed/update/{ACTIVITY_URN}/",
        })
        assert r.status_code == 200, r.text
        cleanup["leads"].append(r.json()["interaction"]["lead_id"])

    answer = client.get(f"/api/v1/posts/{post_id}/engagers").json()

    assert answer["status"] == "success"
    assert answer["activity_urn"] == ACTIVITY_URN
    assert answer["count"] == 2, (
        f"Expected both engagers to be attributed to this post, got {answer['count']}. "
        f"This is the assertion that has never been true in this codebase."
    )

    names = [e["full_name"] for e in answer["engagers"]]
    assert "Priya Raman" in names and "Tom Alvarez" in names
    # Ordered by fit, so the person worth replying to first is first.
    assert answer["engagers"][0]["icp_score"] >= answer["engagers"][1]["icp_score"]


# --------------------------------------------------------------------------
# The extension half
# --------------------------------------------------------------------------

def _content_source():
    with open(CONTENT_JS, "r", encoding="utf-8") as f:
        return f.read()


def test_the_extension_stamps_a_post_urn_on_every_captured_engager():
    """
    The one-line omission that severed the chain: content.js built its lead
    objects with no post field at all, so the backend stored NULL even though
    its column, its route and its join were all ready.
    """
    source = _content_source()
    code = [l for l in source.splitlines() if not l.lstrip().startswith("//")]

    assert any("post_urn: postUrnFor(card)" in l for l in code), (
        "commenter capture does not record which post the comment is on"
    )
    assert any("post_urn: postUrnFor(item)" in l for l in code), (
        "reactor capture does not record which post the reaction is on"
    )
    assert any("post_urn: lead.post_urn" in l for l in code), (
        "the CRM ingest payload does not forward the post URN"
    )


def test_the_extension_reads_the_urn_from_the_url_before_any_markup():
    """
    location.pathname cannot be renamed. Depending on a CSS class first would
    make attribution as fragile as the scraping around it.
    """
    source = _content_source()
    fn = re.search(r"function postUrnFor\b[\s\S]*?\n}", source).group(0)
    url_at = fn.index("window.location.pathname")
    attr_at = fn.index("getAttribute")
    assert url_at < attr_at, (
        "postUrnFor consults DOM attributes before the URL, so the robust "
        "source is only a fallback"
    )
