"""
Quality cycle 2026-10, batch F4b: when the creator's post history counts as read.
================================================================================

SETUP-03 and BRIDGE-04. Leads review offers a lead for permanent deletion as
"engaged only with other people's posts" once the creator's post history is
complete. Two things made that verdict wrong for real leads:

  The history counted as complete after any posts import the extension called
  "completed", which it said when the list merely stopped growing (a slow
  "Show more", a button in another language), when it ran out of rounds, and
  when it had read nothing at all.

  A post known only from LinkedIn's archive is named by its share or ugcPost
  id, while engagement on it is captured under its activity id, so it was
  never recognised as the creator's post.
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module
import onboarding
import today
from database import get_db

client = TestClient(app_module.app)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OWN_PAGES = os.path.join(REPO_ROOT, "studio", "extension", "own_pages.js")

ME = "sample-erin"
TABLES = ("creator_identity", "own_posts", "self_import_requests", "outbound_engagements", "posts_probe")


def _ms(moment):
    return int(moment.timestamp() * 1000)


# One post, as the archive names it and as the page names it: the same moment,
# different low bits.
POSTED = datetime(2025, 5, 14, 9, 30, tzinfo=timezone.utc)
SHARE_URN = f"urn:li:share:{(_ms(POSTED) << 22) | 1234}"
ACTIVITY_URN = f"urn:li:activity:{(_ms(POSTED) << 22) | 987654}"
# Somebody else's post, a day later.
OTHER_URN = f"urn:li:activity:{(_ms(POSTED + timedelta(days=1)) << 22) | 55}"
# A recent post of the creator's, which the bridge did read.
RECENT_URN = f"urn:li:activity:{(_ms(datetime.now(timezone.utc) - timedelta(days=3)) << 22) | 7}"


def _wipe():
    conn = get_db()
    try:
        with conn:
            for table in ("creator_identity", "own_posts", "self_import_requests", "outbound_engagements"):
                conn.execute(f"DELETE FROM {table}")
            conn.execute("DELETE FROM lead_interactions WHERE lead_id IN "
                         "(SELECT id FROM leads WHERE linkedin_urn LIKE '%f4b-history-probe%')")
            conn.execute("DELETE FROM leads WHERE linkedin_urn LIKE '%f4b-history-probe%'")
            conn.execute("DELETE FROM settings WHERE key IN ('creator_profile', 'identity_filled_profile')")
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def clean():
    _wipe()
    yield
    _wipe()


def _confirm():
    client.post("/api/v1/identity/observe", json={"vanity": ME, "display_name": "Sample Erin",
                                                  "self_evidence": ["owner_edit_controls"]})
    assert client.post("/api/v1/identity/confirm", json={"vanity": ME}).status_code == 200


def _archive_post(urn=SHARE_URN, text="What a year of saying no to clients taught me about pricing."):
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, first_seen_at, last_seen_at) "
            "VALUES (?, ?, ?, 'archive', ?, ?)",
            (urn, text, POSTED.isoformat(), POSTED.isoformat(), POSTED.isoformat()))
    conn.close()


def _lead(name, post_urn, kind="COMMENT"):
    from crm import reverse_crm
    slug = name.lower().replace(" ", "-")
    return str(reverse_crm.ingest_interaction(
        name, f"https://www.linkedin.com/in/{slug}-f4b-history-probe/", "Engineer", None, kind,
        f"A comment from {name}." if kind == "COMMENT" else None, post_urn=post_urn)["lead_id"])


def _posts_import(items_seen, outcome):
    request_id = client.post("/api/v1/self/imports", json={"kind": "posts"}).json()["id"]
    client.post("/api/v1/self/imports/event", json={"id": request_id, "event": "started"})
    body = {"id": request_id, "event": "finished", "items_seen": items_seen}
    if outcome is not None:
        body["outcome"] = outcome
    assert client.post("/api/v1/self/imports/event", json=body).status_code == 200
    return request_id


def _review():
    return client.get("/api/v1/leads/review").json()


# ---------------------------------------------------------------------------
# A partial import is not the whole history
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("items_seen,outcome", [
    (0, "completed"),      # what the extension said after reading nothing
    (3, "completed"),      # what an older extension said for a stall or the round cap
    (3, None),             # no outcome at all
    (40, "stalled"),       # the list stopped growing with more still offered
    (900, "round_limit"),  # the import ran out of rounds
    (0, "end_of_list"),    # the list "ended" with nothing read
])
def test_an_import_that_did_not_read_to_the_end_is_not_your_history(items_seen, outcome):
    _confirm()
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [{"activity_urn": RECENT_URN, "actor": ME}]})
    stranger_on_old_post = _lead("Olga Older", OTHER_URN)
    _posts_import(items_seen, outcome)

    review = _review()
    assert review["history_complete"] is False
    assert review["counts"]["not_yours"] == 0
    assert stranger_on_old_post not in {lead["id"] for lead in review["not_yours"]}
    assert client.post("/api/v1/leads/review/remove", json={"lead_ids": [stranger_on_old_post]}).json()["removed"] == 0


def test_what_a_partial_import_read_is_recorded_as_partial():
    _confirm()
    request_id = _posts_import(0, "completed")
    entry = next(i for i in client.get("/api/v1/onboarding/state").json()["imports"] if i["id"] == request_id)
    assert entry["outcome"] != "completed"
    assert entry["items_seen"] == 0

    request_id = _posts_import(0, "end_of_list")
    entry = next(i for i in client.get("/api/v1/onboarding/state").json()["imports"] if i["id"] == request_id)
    assert entry["outcome"] == "nothing_read"


# Review of BRIDGE-04: a browser keeps running the old extension until it is
# reloaded, and the old code says "completed" for every import. Recorded as
# partial, Setup and Today sent the creator to import again, forever, while the
# studio claimed an end of list it cannot know was missed.

def test_an_import_from_an_older_extension_says_to_reload_it():
    _confirm()
    client.post("/api/v1/bridge/heartbeat", json={"extension_version": "test"})
    for _ in range(2):  # importing again with the same old extension changes nothing
        request_id = _posts_import(3, "completed")
        entry = next(i for i in _state()["imports"] if i["id"] == request_id)
        assert entry["outcome"] == "old_extension"
        state = _state()
        assert state["steps"]["history"] is False
        assert state["extension_outdated"] is True

        reason = client.get("/api/v1/today").json()["open_next"]["reason"]
        assert "reload the extension" in reason.lower()
        assert "extensions page" in reason
        assert "read to the end" not in reason, "the studio cannot know the old import missed the end"


def test_an_old_completed_row_from_before_the_upgrade_says_the_same():
    _confirm()
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO self_import_requests (kind, requested_at, started_at, finished_at, items_seen, "
                     "outcome) VALUES ('posts', ?, ?, ?, 40, 'completed')", (POSTED.isoformat(),) * 3)
    conn.close()
    assert _state()["extension_outdated"] is True


def test_reloading_and_importing_again_ends_it():
    _confirm()
    _posts_import(3, "completed")
    _posts_import(12, "end_of_list")
    state = _state()
    assert state["extension_outdated"] is False
    assert state["steps"]["history"] is True


def test_an_import_that_read_to_the_end_completes_your_history():
    _confirm()
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [{"activity_urn": RECENT_URN, "actor": ME}]})
    stranger = _lead("Sam Stranger", OTHER_URN)
    _posts_import(12, "end_of_list")
    review = _review()
    assert review["history_complete"] is True
    assert stranger in {lead["id"] for lead in review["not_yours"]}


# ---------------------------------------------------------------------------
# A post known only from the archive is yours
# ---------------------------------------------------------------------------

def test_a_lead_on_an_archive_post_is_yours_not_a_stranger():
    _confirm()
    _archive_post()
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [{"activity_urn": RECENT_URN, "actor": ME}]})
    commenter = _lead("Sample Commenter", ACTIVITY_URN)
    stranger = _lead("Sam Stranger", OTHER_URN)
    _posts_import(12, "end_of_list")

    review = _review()
    flagged = {lead["id"] for lead in review["not_yours"]}
    assert commenter not in flagged, "someone who commented on your archive post was offered for deletion"
    assert stranger in flagged
    assert review["counts"]["yours"] >= 1

    timeline = client.get(f"/api/v1/crm/leads/{commenter}/timeline").json()["interactions"]
    assert timeline[0]["post_origin"] == "yours"


def test_an_archive_post_does_not_claim_posts_made_at_other_times():
    _confirm()
    _archive_post()
    conn = get_db()
    try:
        own = onboarding._own_activity_ids(conn)
    finally:
        conn.close()
    assert onboarding._activity_id(ACTIVITY_URN) in own
    assert onboarding._activity_id(OTHER_URN) not in own
    near = f"urn:li:activity:{(_ms(POSTED + timedelta(minutes=30)) << 22) | 3}"
    assert onboarding._activity_id(near) not in own


def test_todays_reply_to_lists_commenters_on_archive_posts():
    _confirm()
    _archive_post()
    commenter = _lead("Sample Commenter", ACTIVITY_URN)
    reply_to = client.get("/api/v1/today").json()["reply_to"]
    assert commenter in {person["lead_id"] for person in reply_to}


# ---------------------------------------------------------------------------
# SETUP-13. Step 5 ticked when posts and activity rows existed, which the
# archive alone provides, while Today needs a posts import read to the end,
# so Today sent the creator to a Setup where every step was ticked.
# ---------------------------------------------------------------------------

def _state():
    return client.get("/api/v1/onboarding/state").json()


def _archive_activity():
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO outbound_engagements (target_activity_urn, kind, reaction_kind, my_text_key, "
                     "first_seen_at, last_seen_at) VALUES (?, 'reaction', 'like', '', ?, ?)",
                     (OTHER_URN, POSTED.isoformat(), POSTED.isoformat()))
    conn.close()


def test_the_archive_alone_does_not_tick_your_history():
    _archive_post()
    _archive_activity()
    steps = _state()["steps"]
    assert steps["history"] is False, "step 5 ticked before the identity was even confirmed"

    _confirm()
    client.post("/api/v1/bridge/heartbeat", json={"extension_version": "test"})
    steps = _state()["steps"]
    assert steps["posts"] is True and steps["activity"] is True
    assert steps["history"] is False

    open_next = client.get("/api/v1/today").json()["open_next"]
    assert open_next["action"] == "setup"
    assert "read to the end" in open_next["reason"]


def test_a_posts_import_read_to_the_end_ticks_step_five_and_today_agrees():
    _confirm()
    _archive_post()
    client.post("/api/v1/bridge/heartbeat", json={"extension_version": "test"})
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [{"activity_urn": RECENT_URN, "actor": ME}]})
    _posts_import(12, "end_of_list")
    assert _state()["steps"]["history"] is True
    open_next = client.get("/api/v1/today").json()["open_next"]
    assert "post history" not in open_next["reason"]


# ---------------------------------------------------------------------------
# WRITE-18. A history import bound an old LinkedIn post to a newer, unpublished
# draft that reused its opening, marking the draft published with the old date.
# ---------------------------------------------------------------------------

OPENING = ("Last spring I turned down a client worth a third of our revenue. It was the best decision our "
           "two person design studio has made in five years, and I almost did not make it at all, honestly.")
OLD_POST = OPENING + "\n\nHere is what happened next, and what it taught me about pricing."
NEW_DRAFT = OPENING + "\n\nOne year on: what that decision did to our pipeline, with the actual numbers this time."


@pytest.fixture
def studio_rows():
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


def _row(pid):
    conn = get_db()
    try:
        return dict(conn.execute("SELECT status, published_at, activity_urn FROM posts WHERE id = ?", (pid,)).fetchone())
    finally:
        conn.close()


def _ingest_old_post():
    return client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": ACTIVITY_URN, "actor": ME, "text": OLD_POST}]}).json()


def test_an_old_post_does_not_take_over_a_newer_draft(studio_rows):
    _confirm()
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO posts (id, content, status) VALUES ('f4b-new-draft', ?, 'draft')", (NEW_DRAFT,))
    conn.close()
    studio_rows["posts"].append("f4b-new-draft")

    assert _ingest_old_post()["bound_to_posts"] == 0
    row = _row("f4b-new-draft")
    assert row["status"] == "draft" and row["activity_urn"] is None and row["published_at"] is None


def test_an_old_post_does_not_bind_to_a_draft_written_after_it(studio_rows):
    _confirm()
    conn = get_db()
    with conn:
        draft_id = conn.execute("INSERT INTO drafts (title, raw_content) VALUES ('Follow-up', ?)",
                                (NEW_DRAFT,)).lastrowid
    conn.close()
    studio_rows["drafts"].append(draft_id)
    assert _ingest_old_post()["bound_to_drafts"] == 0


def test_a_post_marked_published_after_it_went_out_still_binds(studio_rows):
    """
    Review of WRITE-18: 'Mark as published' stamps the click time, and a
    creator who posts on LinkedIn first and marks it in the studio later, or
    pastes it in afterwards, must still get the two linked.
    """
    _confirm()
    created = client.post("/api/posts", json={"content": OLD_POST, "status": "draft"}).json()
    post_id = created.get("id") or created.get("post", {}).get("id")
    studio_rows["posts"].append(post_id)
    assert client.post(f"/api/posts/{post_id}/publish-now").status_code == 200

    assert _ingest_old_post()["bound_to_posts"] == 1
    assert _row(post_id)["activity_urn"] == ACTIVITY_URN


def test_a_draft_written_before_the_post_still_binds(studio_rows):
    _confirm()
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO posts (id, content, status, created_at) VALUES ('f4b-old-draft', ?, 'draft', ?)",
                     (OLD_POST, (POSTED - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")))
    conn.close()
    studio_rows["posts"].append("f4b-old-draft")
    assert _ingest_old_post()["bound_to_posts"] == 1
    assert _row("f4b-old-draft")["status"] == "published"


# ---------------------------------------------------------------------------
# The extension says how an import ended
# ---------------------------------------------------------------------------

def _function(source, name):
    start = source.index(f"function {name}(")
    if source[max(0, start - 6):start] == "async ":
        start -= 6
    depth, i = 0, source.index("{", source.index(")", start))
    while True:
        depth += {"{": 1, "}": -1}.get(source[i], 0)
        if depth == 0:
            return source[start:i + 1]
        i += 1


def _run_import(grows, button=None, loader=False, max_rounds=250, stop_at=None):
    """
    Runs runImport under node against a page whose list grows by `grows[i]`
    items in round i (0 once the list is exhausted). Returns what the
    extension told the studio when it finished.
    """
    with open(OWN_PAGES, encoding="utf-8") as handle:
        source = handle.read()
    names = ["runImport", "clickShowMore"]
    # claimedElsewhere: the import is claimed by one tab (cycle 4, track 1, phase 2).
    for helper in ("showMoreButton", "moreOffered", "claimedElsewhere"):
        if f"function {helper}(" in source:
            names.append(helper)
    functions = "\n".join(_function(source, n) for n in names)
    for const in ("LOAD_MORE_WORDS", "LOADER_SELECTOR", "IMPORT_PROGRESS_MS", "HIDDEN_RELEASE_MS"):
        line = next((l for l in source.splitlines() if l.strip().startswith(f"const {const} ")), None)
        if line:
            functions = line + "\n" + functions
    script = r"""
const sent = [];
const grows = %(grows)s;
const BUTTON = %(button)s;
const LOADER = %(loader)s;
let round = 0;
const IMPORT_KIND = { activity_posts: "posts" };
const MAX_ROUNDS = %(max_rounds)d;
const STALL_ROUNDS = 8;
let importRunning = false;
let stopRequested = false;
const sentKeys = new Set();
// What the page has offered once, for the import's running total (own_pages.js).
const offeredKeys = new Set();
const clean = (t) => (t || "").replace(/\s+/g, " ").trim();
const pause = () => Promise.resolve();
const humanPause = () => Promise.resolve();
async function whileHidden() {}
function banner() {}
function clearBanner() {}
function pageKind() { return "activity_posts"; }
function activityCards() { return []; }
async function sendActivity() {
  const added = round < grows.length ? grows[round] : 0;
  round += 1;
  if (%(stop_at)s !== null && round >= %(stop_at)s) stopRequested = true;
  return added;
}
async function studio(path, body) { sent.push({ path, body }); return { status: "success" }; }
const button = BUTTON === null ? null : {
  innerText: BUTTON.text, disabled: false, classList: { contains: () => false },
  getAttribute: () => null, click() {},
  // Below the list, inside LinkedIn's scroller: where its load control sits.
  closest: (sel) => (BUTTON.below_list && sel === ".scaffold-finite-scroll" ? {} : null),
};
const loader = { getClientRects: () => [1] };
const document = {
  body: { scrollHeight: 1000 }, documentElement: { scrollHeight: 1000 },
  querySelectorAll(selector) {
    if (selector === "button") return button ? [button] : [];
    return LOADER ? [loader] : [];
  },
};
const window = { scrollTo() {}, location: {} };
%(functions)s
runImport("activity_posts", "sample-erin", { id: 7 }).then(() => {
  process.stdout.write(JSON.stringify(sent.find((m) => m.body.event === "finished").body));
});
""" % {"grows": json.dumps(grows), "button": json.dumps(button), "loader": json.dumps(loader),
       "max_rounds": max_rounds, "stop_at": json.dumps(stop_at), "functions": functions}
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


node = pytest.mark.skipif(shutil.which("node") is None, reason="node is required to execute the extension logic")


@node
def test_a_list_that_ends_is_reported_as_the_end():
    finished = _run_import([5, 4, 3])
    assert finished == {"id": 7, "event": "finished", "items_seen": 12, "outcome": "end_of_list"}


@node
@pytest.mark.parametrize("button", [
    {"text": "Show more results", "below_list": False},
    # A creator using LinkedIn in German: recognised by where it sits, not its words.
    {"text": "Weitere Ergebnisse anzeigen", "below_list": True},
])
def test_a_list_that_stops_growing_while_more_is_offered_has_stalled(button):
    finished = _run_import([5, 4, 3], button=button)
    assert finished["outcome"] == "stalled"
    assert finished["items_seen"] == 12


@node
def test_a_list_still_loading_has_stalled():
    assert _run_import([5], loader=True)["outcome"] == "stalled"


@node
def test_running_out_of_rounds_is_not_the_end():
    finished = _run_import([1] * 20, max_rounds=10)
    assert finished["outcome"] == "round_limit"
    assert finished["items_seen"] == 10


@node
def test_stopping_is_still_reported_as_stopped():
    assert _run_import([1] * 20, stop_at=3)["outcome"] == "stopped"
