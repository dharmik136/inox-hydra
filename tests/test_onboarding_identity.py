"""
The creator's identity, and the rule that everything else hangs from.
=====================================================================

Onboarding asks the creator to open their own profile, and the studio then
asks "is this you?". From that answer the studio can tell the creator's own
pages, posts and likes apart from everybody else's, which it could not do at
all before: it had no record of who its user was.

These tests hold the rule in onboarding.py:

  Nothing is stored as the creator's until they confirm who they are, and after
  that nothing is stored as theirs unless it carries the confirmed identity.

Each failure mode here has a concrete cost. A stranger held as a candidate is a
screen asking "is this you?" about someone else. A repost stored as an own post
credits the creator with somebody else's writing. The creator's likes stored as
leads fill the CRM with people who never engaged with them.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module
import onboarding
from database import get_db

client = TestClient(app_module.app)

ME = "priya-raman-42"
# A real-shaped activity id: the high bits are milliseconds since the epoch.
URN_2024 = "urn:li:activity:" + str(int(datetime(2024, 3, 5, tzinfo=timezone.utc).timestamp() * 1000) << 22)
URN_OTHER = "urn:li:activity:" + str(int(datetime(2024, 6, 1, tzinfo=timezone.utc).timestamp() * 1000) << 22)

TABLES = ("creator_identity", "creator_positions", "creator_education", "creator_skills",
          "own_posts", "outbound_engagements", "self_import_requests", "bridge_heartbeats", "captures")


@pytest.fixture(autouse=True)
def clean():
    def wipe():
        conn = get_db()
        try:
            with conn:
                for table in TABLES:
                    conn.execute(f"DELETE FROM {table}")
                conn.execute("DELETE FROM settings WHERE key = 'creator_profile'")
        finally:
            conn.close()
    wipe()
    yield
    wipe()


def _profile(vanity=ME, evidence=("owner_edit_controls",), **extra):
    body = {
        "vanity": vanity,
        "self_evidence": list(evidence),
        "display_name": "Priya Raman",
        "headline": "VP of Engineering at Northwind Freight",
        "location": "Pune, India",
        "about": "I build logistics platforms.",
        "current_company": "Northwind Freight",
        "follower_count": 4200,
        "positions": [{"title": "VP of Engineering", "company": "Northwind Freight", "date_range": "2021 - Present"}],
        "education": [{"school": "IIT Bombay", "degree": "B.Tech", "date_range": "2008 - 2012"}],
        "skills": ["Kafka", "Go", "Kafka"],
        "contact": {"email": "priya@example.com", "phone": "+91 98 7654 3210",
                    "birthday": "March 4", "websites": ["https://priya.dev"]},
    }
    body.update(extra)
    return body


def _confirm():
    assert client.post("/api/v1/identity/observe", json=_profile()).json()["status"] == "candidate"
    assert client.post("/api/v1/identity/confirm", json={"vanity": ME}).status_code == 200


def _state():
    return client.get("/api/v1/onboarding/state").json()


# ---------------------------------------------------------------------------
# Becoming known
# ---------------------------------------------------------------------------

def test_a_stranger_is_never_offered_as_you():
    """
    A profile without any sign the viewer owns it is not even held as a
    candidate, so the screen can never ask "is this you?" about someone else.
    """
    result = client.post("/api/v1/identity/observe", json=_profile(evidence=())).json()
    assert result["status"] == "ignored"
    assert _state()["candidate"] is None


def test_an_unrecognised_evidence_label_does_not_count():
    result = client.post("/api/v1/identity/observe", json=_profile(evidence=("looks_like_me",))).json()
    assert result["status"] == "ignored"


def test_your_own_profile_becomes_a_question_not_an_answer():
    """Before confirmation the capture is a candidate. Nothing is yet yours."""
    client.post("/api/v1/identity/observe", json=_profile())
    state = _state()
    assert state["candidate"]["vanity"] == ME
    assert state["candidate"]["display_name"] == "Priya Raman"
    assert state["candidate"]["evidence"], "the screen cannot say why it thinks this is you"
    assert state["identity"] is None
    assert state["steps"]["identity"] is False


def test_confirming_a_different_profile_is_refused():
    client.post("/api/v1/identity/observe", json=_profile())
    response = client.post("/api/v1/identity/confirm", json={"vanity": "someone-else"})
    assert response.status_code == 409
    assert _state()["identity"] is None


def test_confirming_stores_the_whole_profile():
    _confirm()
    identity = _state()["identity"]
    assert identity["vanity"] == ME
    assert identity["headline"] == "VP of Engineering at Northwind Freight"
    assert identity["follower_count"] == 4200
    assert identity["positions"][0]["company"] == "Northwind Freight"
    assert identity["education"][0]["school"] == "IIT Bombay"
    assert identity["skills"] == ["Go", "Kafka"], "skills are deduplicated"
    assert identity["email"] == "priya@example.com"
    assert identity["websites"] == ["https://priya.dev"]


def test_confirming_fills_blank_studio_fields_and_keeps_typed_ones():
    """
    What the creator typed in Brand Studio wins. The capture fills blanks only,
    so confirming cannot quietly replace a headline written on purpose.
    """
    conn = get_db()
    with conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('creator_profile', ?)",
                     (json.dumps({"name": "", "headline": "Builder of boring, reliable things"}),))
    conn.close()

    _confirm()

    profile = client.get("/api/settings/profile").json()["profile"]
    assert profile["name"] == "Priya Raman"
    assert profile["headline"] == "Builder of boring, reliable things"
    assert profile["company"] == "Northwind Freight"


# ---------------------------------------------------------------------------
# After you are known
# ---------------------------------------------------------------------------

def test_another_profile_after_confirmation_is_not_stored():
    _confirm()
    result = client.post("/api/v1/identity/observe",
                         json=_profile(vanity="a-stranger", display_name="A Stranger")).json()
    assert result["status"] == "ignored"
    assert _state()["identity"]["display_name"] == "Priya Raman"


def test_a_section_missing_from_a_later_read_is_kept():
    """A profile read with About collapsed must not erase last week's About."""
    _confirm()
    later = _profile(about=None, headline="CTO at Northwind Freight")
    del later["positions"]
    client.post("/api/v1/identity/observe", json=later)

    identity = _state()["identity"]
    assert identity["headline"] == "CTO at Northwind Freight"
    assert identity["about"] == "I build logistics platforms."
    assert identity["positions"], "positions absent from the read were erased"


def test_profile_urls_and_vanities_are_the_same_person():
    assert onboarding.normalise_vanity("https://www.linkedin.com/in/Priya-Raman-42/?trk=x") == ME
    assert onboarding.normalise_vanity("priya-raman-42/") == ME
    assert onboarding.normalise_vanity("not a vanity at all") == ""


def test_forgetting_removes_everything():
    _confirm()
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [{"activity_urn": URN_2024, "actor": ME}]})
    assert client.delete("/api/v1/identity").status_code == 200
    state = _state()
    assert state["identity"] is None and state["counts"]["posts"] == 0


# ---------------------------------------------------------------------------
# Posts and activity
# ---------------------------------------------------------------------------

def test_posts_are_refused_before_you_are_known():
    response = client.post("/api/v1/self/posts/ingest",
                           json={"author": ME, "posts": [{"activity_urn": URN_2024, "actor": ME}]})
    assert response.status_code == 409


def test_a_repost_is_not_your_writing():
    """Activity pages show reposts. The actor decides whose post it is."""
    _confirm()
    result = client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": URN_2024, "actor": ME, "text": "Mine"},
        {"activity_urn": URN_OTHER, "actor": "someone-else", "text": "Theirs"},
    ]}).json()
    assert (result["written"], result["skipped"]) == (1, 1)


def test_a_post_date_comes_from_its_urn_and_unread_counts_stay_unknown():
    _confirm()
    client.post("/api/v1/self/posts/ingest",
                json={"author": ME, "posts": [{"activity_urn": URN_2024, "actor": ME, "reactions": 12}]})
    conn = get_db()
    row = dict(conn.execute("SELECT * FROM own_posts").fetchone())
    conn.close()
    assert row["published_at"].startswith("2024-03-05")
    assert row["published_at_source"] == "urn_decode"
    assert row["reactions"] == 12
    assert row["comments"] is None, "a count the page did not show was stored as a measurement"


def test_reading_a_post_again_does_not_duplicate_it_or_lose_counts():
    _confirm()
    for body in ({"reactions": 12, "comments": 3}, {"reactions": 15}):
        client.post("/api/v1/self/posts/ingest",
                    json={"author": ME, "posts": [dict(activity_urn=URN_2024, actor=ME, **body)]})
    conn = get_db()
    rows = [dict(r) for r in conn.execute("SELECT reactions, comments FROM own_posts")]
    conn.close()
    assert rows == [{"reactions": 15, "comments": 3}]


def test_your_likes_are_yours_and_never_leads():
    """
    The creator reacting to someone's post used to become that person being a
    lead. It is a fact about the creator's attention and is stored as one.
    """
    _confirm()
    conn = get_db()
    leads_before = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    conn.close()

    client.post("/api/v1/self/outbound/ingest", json={"actor": ME, "items": [
        {"target_activity_urn": URN_OTHER, "kind": "reaction", "reaction_kind": "like", "target_author": "Asha K"},
        {"target_activity_urn": URN_OTHER, "kind": "comment", "my_text": "Great point on retries."},
        {"target_activity_urn": URN_OTHER, "kind": "comment", "my_text": "great point  on retries."},
    ]})

    counts = _state()["counts"]
    assert counts["reactions"] == 1
    assert counts["comments"] == 1, "the same comment read twice was stored twice"
    conn = get_db()
    assert conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == leads_before
    conn.close()


def test_someone_elses_activity_is_refused():
    _confirm()
    response = client.post("/api/v1/self/outbound/ingest", json={"actor": "someone-else", "items": []})
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Imports only happen because you asked
# ---------------------------------------------------------------------------

def test_an_import_needs_a_confirmed_identity():
    assert client.post("/api/v1/self/imports", json={"kind": "posts"}).status_code == 409


def test_an_import_request_is_what_the_extension_waits_for():
    _confirm()
    requested = client.post("/api/v1/self/imports", json={"kind": "posts"}).json()
    assert requested["open_url"] == f"https://www.linkedin.com/in/{ME}/recent-activity/all/"

    pending = client.post("/api/v1/self/imports/pending", json={"kind": "posts"}).json()
    assert pending["request"]["id"] == requested["id"]
    assert pending["vanity"] == ME

    client.post("/api/v1/self/imports/event", json={"id": requested["id"], "event": "finished", "items_seen": 40})
    assert client.post("/api/v1/self/imports/pending", json={"kind": "posts"}).json()["request"] is None


def test_an_old_request_cannot_start_a_scroll_today():
    """A click from last week must not start scrolling the next time a page opens."""
    _confirm()
    request_id = client.post("/api/v1/self/imports", json={"kind": "comments"}).json()["id"]
    stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    conn = get_db()
    with conn:
        conn.execute("UPDATE self_import_requests SET requested_at = ? WHERE id = ?", (stale, request_id))
    conn.close()
    assert onboarding.pending_import("comments") is None


# ---------------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------------

def test_the_bridge_is_connected_only_while_it_is_heard_from():
    assert _state()["bridge"]["connected"] is False
    client.post("/api/v1/bridge/heartbeat", json={"extension_version": "2.1.0", "page_kind": "feed"})
    bridge = _state()["bridge"]
    assert bridge["connected"] is True and bridge["extension_version"] == "2.1.0"

    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    conn = get_db()
    with conn:
        conn.execute("UPDATE bridge_heartbeats SET seen_at = ?", (old,))
    conn.close()
    assert _state()["bridge"]["connected"] is False


# ---------------------------------------------------------------------------
# The LinkedIn session: kept only for the live send, and deletable
# ---------------------------------------------------------------------------

def test_the_session_is_reported_and_can_be_deleted():
    app_module.linkedin_client.save_tokens("AQEDAnotarealkey_live_shaped", "ajax:1234567890")
    session = _state()["session"]
    assert session["stored"] is True and session["saved_at"]
    assert "AQED" not in json.dumps(_state()), "the session value itself reached the screen"

    assert client.delete("/api/auth/cookies").status_code == 200
    assert _state()["session"]["stored"] is False
    assert app_module.linkedin_client.get_tokens().get("li_at") in (None, "")


def test_no_timer_harvests_the_session():
    """
    The extension copied li_at into the studio every 15 minutes. The creator
    chose to keep the session only for the live send, captured when they press
    Sync, so nothing on a schedule may call the sync.
    """
    path = os.path.join(os.path.dirname(__file__), "..", "studio", "extension", "background.js")
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    code = "\n".join(line for line in source.splitlines() if not line.strip().startswith("//"))
    assert "alarms.create" not in code, "an alarm is being created again"
    assert "onAlarm" not in code, "something still runs on an alarm"
    assert 'alarms.clear("studio_periodic_sync")' in code, (
        "the alarm an earlier version registered is no longer cleared, and alarms outlive their code"
    )


# ---------------------------------------------------------------------------
# Who counts as a lead
# ---------------------------------------------------------------------------

def _engager(**extra):
    body = {
        "full_name": "Asha Kulkarni",
        "linkedin_urn": "https://www.linkedin.com/in/asha-kulkarni-9",
        "headline": "Head of Platform at Loomwork",
        "interaction_type": "COMMENT",
        "comment_text": "How did you stage the rollout?",
        "post_urn": URN_2024,
    }
    body.update(extra)
    return client.post("/api/v1/crm/interactions/ingest", json=body).json()


def _lead_count():
    conn = get_db()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM leads WHERE profile_url LIKE '%asha-kulkarni-9%' OR name = 'Asha Kulkarni'"
        ).fetchone()[0]
    finally:
        conn.close()


@pytest.fixture
def no_asha():
    yield
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM lead_interactions WHERE lead_id IN (SELECT id FROM leads WHERE name = 'Asha Kulkarni')")
        conn.execute("DELETE FROM leads WHERE name = 'Asha Kulkarni'")
    conn.close()


def test_before_setup_no_engager_is_a_lead(no_asha):
    """
    Without a confirmed creator the studio cannot tell whose post anything is,
    so it stores nothing and says where that gets fixed.
    """
    result = _engager(post_author=ME)
    assert result["status"] == "skipped" and "Setup" in result["reason"]
    assert _lead_count() == 0


def test_a_strangers_commenter_is_not_your_lead(no_asha):
    """The failure the audit ranked third: the feed filling the CRM with other creators' audiences."""
    _confirm()
    result = _engager(post_author="another-creator", post_urn=URN_OTHER)
    assert result["status"] == "skipped"
    assert _lead_count() == 0


def test_you_are_never_your_own_lead(no_asha):
    _confirm()
    result = _engager(full_name="Priya Raman", linkedin_urn=f"https://www.linkedin.com/in/{ME}/", post_author=ME)
    assert result["status"] == "skipped" and result["reason"] == "that is you"


def test_an_engager_on_your_post_is_a_lead(no_asha):
    _confirm()
    assert _engager(post_author=ME)["status"] == "success"
    assert _lead_count() == 1


def test_a_post_you_imported_is_recognised_by_its_urn(no_asha):
    """When the card's author link was not readable, a URN already known to be yours still counts."""
    _confirm()
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [{"activity_urn": URN_2024, "actor": ME}]})
    assert _engager(post_author=None)["status"] == "success"


def test_the_batch_path_cannot_step_around_the_rule(no_asha):
    """
    /api/analytics/ingest is relayable from a LinkedIn page for analytics, and
    it also accepts leads. Without the same gate there, any script on the page
    could write a stranger as a lead through it.
    """
    _confirm()
    result = client.post("/api/analytics/ingest", json={"leads": [{
        "name": "Asha Kulkarni", "headline": "Head of Platform",
        "profile_url": "https://www.linkedin.com/in/asha-kulkarni-9", "post_author": "another-creator",
    }]}).json()
    assert result["leads_skipped"] == 1
    assert _lead_count() == 0


def test_the_sync_button_goes_through_the_worker():
    """
    The popup's Sync button is now the only way a session reaches the studio.
    It made its request with a bare fetch, which carries no studio token, so
    every press was refused and reported as "server not reachable". It must
    ask the service worker, which carries the token, and the worker must only
    accept that request from the popup, never from a LinkedIn page.
    """
    ext = os.path.join(os.path.dirname(__file__), "..", "studio", "extension")
    with open(os.path.join(ext, "popup.js"), encoding="utf-8") as handle:
        popup = handle.read()
    with open(os.path.join(ext, "background.js"), encoding="utf-8") as handle:
        background = handle.read()

    assert "/api/auth/cookies" not in popup, "the popup calls the studio directly again, without a token"
    assert 'action: "SYNC_NOW"' in popup, "the Sync button no longer asks the worker"

    handler = background[background.index('message.action === "SYNC_NOW"'):]
    handler = handler[:handler.index("return true;\n  }") + 20]
    assert "sender.tab" in handler, (
        "the worker copies the session for anyone who asks, including a content "
        "script running inside a LinkedIn page"
    )


# ---------------------------------------------------------------------------
# Your LinkedIn posts, joined to the studio records they came from
# ---------------------------------------------------------------------------

OPENING = "Most teams think their migration failed because of the database. It failed because nobody owned the rollback plan until it was needed."


@pytest.fixture
def studio_records():
    made = {"posts": [], "drafts": []}
    yield made
    conn = get_db()
    with conn:
        for pid in made["posts"]:
            conn.execute("DELETE FROM posts WHERE id = ?", (pid,))
        for did in made["drafts"]:
            conn.execute("DELETE FROM posts WHERE draft_id = ?", (did,))
            conn.execute("DELETE FROM drafts WHERE id = ?", (did,))
    conn.close()


def _studio_post(made, pid, content, status="published"):
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO posts (id, content, status) VALUES (?,?,?)", (pid, content, status))
    conn.close()
    made["posts"].append(pid)


def _import(text, urn=URN_2024):
    return client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": urn, "actor": ME, "text": text}]}).json()


def _post(pid):
    conn = get_db()
    row = conn.execute("SELECT * FROM posts WHERE id = ?", (pid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def test_a_post_marked_published_binds_without_the_composer_button(studio_records):
    """
    Binding needed a fingerprint that only the composer's inject button stored,
    so a post marked as published or sent to LinkedIn's scheduler never bound.
    """
    _confirm()
    _studio_post(studio_records, "bindprobe-marked", OPENING + " Here is what we changed.")

    # LinkedIn rewrites whitespace and punctuation; the fingerprint survives it.
    result = _import(OPENING.replace(". ", ".\n\n") + " Here is what we changed.")

    assert result["bound_to_posts"] == 1
    row = _post("bindprobe-marked")
    assert row["activity_urn"] == URN_2024
    assert row["published_at"].startswith("2024-03-05"), "the publish date is LinkedIn's, from the URN"


def test_a_draft_retyped_on_linkedin_finds_its_post(studio_records):
    """A draft that was never queued or injected still becomes the post it turned into."""
    _confirm()
    conn = get_db()
    with conn:
        draft_id = conn.execute("INSERT INTO drafts (title, raw_content) VALUES (?, ?)",
                                ("Rollback", OPENING)).lastrowid
    conn.close()
    studio_records["drafts"].append(draft_id)

    assert _import(OPENING)["bound_to_drafts"] == 1
    conn = get_db()
    row = conn.execute("SELECT activity_urn, status FROM posts WHERE draft_id = ?", (draft_id,)).fetchone()
    conn.close()
    assert row["activity_urn"] == URN_2024 and row["status"] == "published"


def test_two_candidates_bind_neither(studio_records):
    """A wrong binding credits one post's engagers to another, so an ambiguous match binds nothing."""
    _confirm()
    _studio_post(studio_records, "bindprobe-a", OPENING + " Version A.")
    _studio_post(studio_records, "bindprobe-b", OPENING + " Version B.")

    result = _import(OPENING)
    assert result["bound_to_posts"] == 0
    assert _post("bindprobe-a")["activity_urn"] is None and _post("bindprobe-b")["activity_urn"] is None


def test_an_unrelated_post_binds_nothing(studio_records):
    _confirm()
    _studio_post(studio_records, "bindprobe-other", "A completely different post about hiring your first platform engineer and what to ask them.")
    assert _import(OPENING)["bound_to_posts"] == 0
    assert _post("bindprobe-other")["activity_urn"] is None


# ---------------------------------------------------------------------------
# Sorting leads captured before the studio knew which posts were yours
# ---------------------------------------------------------------------------

@pytest.fixture
def legacy_leads():
    """Three leads as the old capture would have left them."""
    from crm import reverse_crm

    made = {}
    for key, urn in (("mine", URN_2024), ("theirs", URN_OTHER), ("nopost", None)):
        made[key] = reverse_crm.ingest_interaction(
            f"Legacy {key}", f"https://www.linkedin.com/in/legacy-{key}-probe", "Engineer",
            None, "COMMENT", f"A comment from {key}.", post_urn=urn,
        )["lead_id"]
    yield made
    conn = get_db()
    with conn:
        for lead_id in made.values():
            conn.execute("DELETE FROM lead_interactions WHERE lead_id = ?", (lead_id,))
            conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    conn.close()


def _history_imported():
    _confirm()
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [{"activity_urn": URN_2024, "actor": ME}]})
    request_id = client.post("/api/v1/self/imports", json={"kind": "posts"}).json()["id"]
    client.post("/api/v1/self/imports/event", json={"id": request_id, "event": "finished", "items_seen": 1})


def test_nothing_is_called_a_stranger_before_your_history_is_read(legacy_leads):
    """A post the studio does not recognise may just be an older post of yours."""
    _confirm()
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [{"activity_urn": URN_2024, "actor": ME}]})
    review = client.get("/api/v1/leads/review").json()
    assert review["history_complete"] is False
    assert review["counts"]["not_yours"] == 0


def test_leads_are_sorted_once_your_history_is_complete(legacy_leads):
    _history_imported()
    review = client.get("/api/v1/leads/review").json()
    flagged = {lead["id"] for lead in review["not_yours"]}
    assert legacy_leads["theirs"] in flagged
    assert legacy_leads["mine"] not in flagged, "someone who engaged with your post was offered for removal"
    assert legacy_leads["nopost"] not in flagged, "a lead with no known post was called a stranger"


def test_removal_rechecks_every_name(legacy_leads):
    """A lead that is yours is kept even if its id is on the list sent for removal."""
    _history_imported()
    result = client.post("/api/v1/leads/review/remove",
                         json={"lead_ids": [legacy_leads["theirs"], legacy_leads["mine"]]}).json()
    assert result == {"status": "success", "removed": 1, "kept": 1}
    conn = get_db()
    remaining = {r[0] for r in conn.execute("SELECT id FROM leads WHERE id IN (?, ?)",
                                             (legacy_leads["theirs"], legacy_leads["mine"]))}
    conn.close()
    assert remaining == {legacy_leads["mine"]}


def test_the_dossier_says_where_they_engaged(legacy_leads):
    _history_imported()
    mine = client.get(f"/api/v1/crm/leads/{legacy_leads['mine']}/timeline").json()["interactions"]
    theirs = client.get(f"/api/v1/crm/leads/{legacy_leads['theirs']}/timeline").json()["interactions"]
    assert mine[0]["post_origin"] == "yours"
    assert theirs[0]["post_origin"] == "not_yours"


# ---------------------------------------------------------------------------
# Capture health: a broken selector is visible rather than silent
# ---------------------------------------------------------------------------

def _health():
    return {entry["extractor"]: entry for entry in _state()["health"]}


def test_every_extractor_is_listed_even_before_it_runs():
    """An absent row is the question the creator is asking, so it is shown as never run."""
    health = _health()
    assert set(health) >= {"engagers", "profile", "activity_posts", "analytics"}
    assert all(entry["state"] == "never_run" for entry in health.values())


def test_a_run_that_could_not_read_the_page_is_drift():
    client.post("/api/v1/bridge/capture", json={"extractor": "engagers", "items_seen": 12, "items_kept": 12})
    client.post("/api/v1/bridge/capture", json={
        "extractor": "engagers", "items_seen": 9, "items_kept": 0, "drift": ["commenter_name"]})
    entry = _health()["engagers"]
    assert entry["state"] == "drifting"
    assert entry["drift"] == ["commenter_name"]
    assert entry["last_good_at"], "when it last worked is what tells the creator how long it has been broken"


def test_a_working_run_clears_drift():
    client.post("/api/v1/bridge/capture", json={"extractor": "profile", "items_seen": 1, "drift": ["name"]})
    client.post("/api/v1/bridge/capture", json={"extractor": "profile", "items_seen": 4, "items_kept": 4})
    assert _health()["profile"]["state"] == "working"


def test_an_unknown_extractor_is_refused():
    assert client.post("/api/v1/bridge/capture", json={"extractor": "anything"}).status_code == 409


def test_the_extension_reports_what_it_could_not_read():
    """The canaries are the point: each reader says when a page had content it could not parse."""
    ext = os.path.join(os.path.dirname(__file__), "..", "studio", "extension")
    with open(os.path.join(ext, "content.js"), encoding="utf-8") as handle:
        content = handle.read()
    with open(os.path.join(ext, "own_pages.js"), encoding="utf-8") as handle:
        own = handle.read()
    assert '"commenter_name"' in content and 'reportCapture("engagers"' in content
    assert 'reportCapture("analytics"' in content
    assert 'reportCapture("profile"' in own and '"post_author"' in own
