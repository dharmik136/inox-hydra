"""
A post the bridge first finds after migration 26 is still one post.
===================================================================

Found by track 3 on main (cf0ba9d, the released 2.7.0). Migration 26 gave
every publication the studio held its posts row, once. Nothing gave one to a
publication first found after it: the activity reader bound a post only when a
studio draft matched it, the archive import wrote the publication alone, and
an engager captured on the creator's own post left no record of the post at
all. post_identity.resolve found no posts row, so the engagers route answered
404 and Posts said "NOBODY CAPTURED FROM THIS POST YET." however many people
had engaged.

The rule migration 26 applied once is now post_identity.ensure_post, applied
wherever a post first becomes known, and this track's migration
(_migrate_reader_timing_and_network_reading) applies it to the publications
the defect left behind.

Every name and text here is invented.

Strict Invariants:
- Zero em-dashes.
"""

import ast
import hashlib
import io
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
sys.path.insert(0, BACKEND)

ME = "identity-probe-creator"
TEXT = "Shipping a local-first app taught me three things about what users will forgive and what they will not."
OTHER = "Nobody tells you that the hardest part of a side project is deciding what it will never do for anyone."
SHARES_HEADER = "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl,Visibility\n"


def _snow(moment: datetime, salt: int) -> int:
    """A LinkedIn-style id: the high bits are the millisecond timestamp."""
    return (int(moment.timestamp() * 1000) << 22) | (salt & ((1 << 22) - 1))


def _urn(hours_ago: float, salt: int, kind: str = "activity") -> str:
    return f"urn:li:{kind}:{_snow(datetime.now(timezone.utc) - timedelta(hours=hours_ago), salt)}"


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_t1_identity_")
    monkeypatch.setenv("INOX_HYDRA_HOME", os.path.join(home, "studio"))
    monkeypatch.setenv("HOME", os.path.join(home, "user"))
    monkeypatch.setenv("USERPROFILE", os.path.join(home, "user"))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    os.makedirs(os.path.join(home, "user", "Downloads"))
    from database import init_db
    init_db()
    yield home
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture
def client(studio):
    import app as app_module
    from fastapi.testclient import TestClient
    client = TestClient(app_module.app)
    client.post("/api/v1/identity/observe", json={"vanity": ME, "self_evidence": ["owner_edit_controls"],
                                                  "display_name": "Identity Probe"})
    client.post("/api/v1/identity/confirm", json={"vanity": ME})
    return client


def _db():
    from database import get_db
    return get_db()


def _engager(client, post_urn, who="engager-one", author=ME):
    answer = client.post("/api/v1/crm/interactions/ingest", json={
        "full_name": who.replace("-", " ").title(), "linkedin_urn": f"https://www.linkedin.com/in/{who}/",
        "headline": "Founder at Example", "interaction_type": "COMMENT", "comment_text": "Well put.",
        "post_urn": post_urn, "post_author": author})
    assert answer.status_code == 200, answer.text
    return answer.json()


def _engagers(client, identifier):
    return client.get(f"/api/v1/posts/{identifier}/engagers")


def _posts_carrying(urn):
    conn = _db()
    try:
        return [dict(r) for r in conn.execute("SELECT id, source, activity_urn FROM posts WHERE activity_urn = ?", (urn,))]
    finally:
        conn.close()


def _publication(urn):
    conn = _db()
    try:
        row = conn.execute("SELECT activity_urn, post_id, text FROM own_posts WHERE activity_urn = ?", (urn,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Each reader that can first find a post
# ---------------------------------------------------------------------------

def test_a_post_first_read_on_the_activity_page_answers_for_its_engagers(client):
    urn = _urn(30, 1)
    answer = client.post("/api/v1/self/posts/ingest", json={
        "author": ME, "posts": [{"activity_urn": urn, "actor": ME, "text": TEXT, "reactions": 4}]})
    assert answer.status_code == 200, answer.text
    # Asked before any engager is read, so nothing but the activity reader made the post.
    found = _engagers(client, urn)
    assert found.status_code == 200, "a post first read on the activity page has no posts row"
    assert _publication(urn)["post_id"] == found.json()["post_id"]
    _engager(client, urn)
    assert _engagers(client, urn).json()["count"] == 1


def test_a_post_first_seen_through_its_engagers_answers_for_them(client):
    urn = _urn(5, 2)
    assert _engager(client, urn)["outcome"] == "accepted"
    found = _engagers(client, urn)
    assert found.status_code == 200, "a post first seen through its engagers has no posts row"
    assert found.json()["count"] == 1
    assert _publication(urn) is not None, "the creator's post has no publication record"


def test_a_post_known_only_from_the_archive_answers_once_its_analytics_page_is_read(client):
    """The state the archive import left: a publication with no posts row."""
    urn = _urn(50, 3)
    conn = _db()
    with conn:
        conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, "
                     "first_seen_at, last_seen_at) VALUES (?, ?, ?, 'archive', ?, ?)",
                     (urn, TEXT, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat(),
                      datetime.now(timezone.utc).isoformat()))
    conn.close()
    answer = client.post("/api/v1/self/posts/analytics", json={"author": ME, "activity_urn": urn,
                                                               "metrics": {"impressions": 120}})
    assert answer.status_code == 200, answer.text
    found = _engagers(client, urn)
    assert found.status_code == 200, "a post whose analytics page was read has no posts row"


def test_the_analytics_page_alone_still_does_not_make_a_post_the_creators(client):
    """By design: the page is shown to its author, but the studio is told only the signed-in account."""
    urn = _urn(20, 4)
    answer = client.post("/api/v1/self/posts/analytics", json={"author": ME, "activity_urn": urn,
                                                               "metrics": {"impressions": 120}})
    assert answer.status_code == 409
    assert _publication(urn) is None and _posts_carrying(urn) == []


def test_a_post_read_twice_is_still_one_post(client):
    urn = _urn(30, 5)
    for _ in range(2):
        client.post("/api/v1/self/posts/ingest", json={
            "author": ME, "posts": [{"activity_urn": urn, "actor": ME, "text": TEXT}]})
        _engager(client, urn)
    assert len(_posts_carrying(urn)) == 1


# ---------------------------------------------------------------------------
# The archive
# ---------------------------------------------------------------------------

def _archive(rows):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Shares.csv", SHARES_HEADER + "".join(rows))
    return buffer.getvalue()


def _share_row(moment, urn, text):
    link = "https://www.linkedin.com/feed/update/" + urn.replace(":", "%3A")
    quoted = '"' + text.replace('"', '""') + '"'
    return f"{moment.strftime('%Y-%m-%d %H:%M:%S')},{link},{quoted},,,MEMBER_NETWORK\n"


def _import(client, rows):
    upload = client.post("/api/v1/archive/upload", content=_archive(rows),
                         headers={"Content-Type": "application/zip",
                                  "X-Archive-Name": "Complete_LinkedInDataExport_10-19-2026.zip"})
    assert upload.status_code == 200, upload.text
    answer = client.post("/api/v1/archive/import", json={"source": upload.json()["source"], "include": ["posts"],
                                                          "confirm_owner": True})
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_an_archive_import_gives_each_new_post_its_posts_row(client):
    moment = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=40)
    urn = f"urn:li:activity:{_snow(moment, 6)}"
    _import(client, [_share_row(moment, urn, TEXT)])
    assert _engagers(client, urn).status_code == 200, "a post the archive brought has no posts row"


def test_removing_the_archive_import_takes_the_posts_it_made(client):
    import archive_import
    moment = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=41)
    urn = f"urn:li:share:{_snow(moment, 7)}"
    _import(client, [_share_row(moment, urn, OTHER)])
    assert len(_posts_carrying(urn)) == 1
    archive_import.remove_last_import()
    assert _publication(urn) is None
    assert _posts_carrying(urn) == [], "removing the import left the post it made behind"


def test_engagers_filed_under_the_activity_id_of_an_archive_post_are_found(client):
    """
    The archive names a post by its share id and the bridge by its activity
    id. When the bridge reads the post, the archive's publication takes the
    activity id; the engagers it files under that id are the post's.
    """
    moment = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=3)
    share = f"urn:li:share:{_snow(moment, 8)}"
    activity = f"urn:li:activity:{_snow(moment + timedelta(seconds=1), 9)}"
    _import(client, [_share_row(moment, share, TEXT)])
    client.post("/api/v1/self/posts/ingest", json={
        "author": ME, "posts": [{"activity_urn": activity, "actor": ME, "text": TEXT}]})
    assert _publication(activity) is not None and _publication(share) is None, "the twin was not joined"
    _engager(client, activity)
    found = _engagers(client, activity)
    assert found.status_code == 200
    assert found.json()["count"] == 1, "the engagers filed under the post's activity id were not found"


# ---------------------------------------------------------------------------
# The bind the studio's own post depends on
# ---------------------------------------------------------------------------

def test_an_engager_read_before_the_bind_does_not_take_the_studios_post(client):
    """
    On the post's own page the engagers are often read before its text is
    offered for binding. A post made from the engagers alone must give way to
    the studio's own post when its text arrives, or the post the creator put
    into LinkedIn's composer never binds.
    """
    armed = client.post("/api/v1/posts/injected", json={"content": TEXT}).json()
    assert armed.get("status") == "recorded", armed
    urn = _urn(1, 10)
    _engager(client, urn)
    bound = client.post("/api/v1/posts/bind-urn", json={"activity_urn": urn, "post_text": TEXT,
                                                         "post_author": ME}).json()
    assert bound["status"] == "bound" and bound["post_id"] == armed["post_id"], bound
    assert [p["id"] for p in _posts_carrying(urn)] == [armed["post_id"]]
    found = _engagers(client, urn).json()
    assert found["post_id"] == armed["post_id"] and found["count"] == 1
    assert _publication(urn)["post_id"] == armed["post_id"]


def test_a_post_made_from_its_words_gives_way_to_the_post_marked_published_later(client):
    """
    WRITE-18: a creator who posts on LinkedIn first and pastes the post in and
    marks it published afterwards still gets the two linked. The import made
    a post from the words before the studio's existed; it stands in, and
    gives way.
    """
    urn = _urn(30, 11)
    client.post("/api/v1/self/posts/ingest", json={
        "author": ME, "posts": [{"activity_urn": urn, "actor": ME, "text": OTHER}]})
    made = _posts_carrying(urn)
    assert len(made) == 1 and made[0]["source"] == "linkedin"
    pasted = client.post("/api/posts", json={"content": OTHER, "status": "draft"}).json()
    assert client.post(f"/api/posts/{pasted['id']}/publish-now").status_code == 200
    answer = client.post("/api/v1/self/posts/ingest", json={
        "author": ME, "posts": [{"activity_urn": urn, "actor": ME, "text": OTHER}]}).json()
    assert answer["bound_to_posts"] == 1, answer
    assert [p["id"] for p in _posts_carrying(urn)] == [pasted["id"]], "the stand-in did not give way"
    assert _publication(urn)["post_id"] == pasted["id"]


def test_a_post_the_creator_has_touched_is_not_given_away(client):
    """Tagged in the studio, it is the creator's record, and stays the post."""
    urn = _urn(31, 16)
    client.post("/api/v1/self/posts/ingest", json={
        "author": ME, "posts": [{"activity_urn": urn, "actor": ME, "text": OTHER}]})
    made = _posts_carrying(urn)[0]["id"]
    conn = _db()
    with conn:
        conn.execute("UPDATE posts SET tags = ? WHERE id = ?", ('["launch"]', made))
    conn.close()
    pasted = client.post("/api/posts", json={"content": OTHER, "status": "draft"}).json()
    client.post(f"/api/posts/{pasted['id']}/publish-now")
    bound = client.post("/api/v1/posts/bind-urn", json={"activity_urn": urn, "post_text": OTHER,
                                                         "post_author": ME}).json()
    assert bound["status"] == "already_bound" and bound["post_id"] == made, bound


def test_an_engager_on_a_post_the_studio_carries_records_nothing_new(client):
    """The post is known and resolves already; no publication is invented for it."""
    urn = _urn(2, 17)
    conn = _db()
    with conn:
        conn.execute("INSERT INTO posts (id, content, status, activity_urn) VALUES ('post-carried', ?, 'published', ?)",
                     (TEXT, urn))
    conn.close()
    _engager(client, urn)
    assert _publication(urn) is None
    assert [p["id"] for p in _posts_carrying(urn)] == ["post-carried"]
    assert _engagers(client, urn).json()["count"] == 1


def test_forgetting_the_creator_takes_the_posts_made_from_their_publications(client):
    """They hold the creator's post text and LinkedIn id and nothing written here."""
    made_urn, studio_urn = _urn(30, 18), _urn(31, 19)
    client.post("/api/v1/self/posts/ingest", json={
        "author": ME, "posts": [{"activity_urn": made_urn, "actor": ME, "text": OTHER}]})
    written = client.post("/api/posts", json={"content": TEXT, "status": "draft"}).json()["id"]
    assert client.delete("/api/v1/identity").status_code == 200
    assert _posts_carrying(made_urn) == [], "a post made from a forgotten publication outlived it"
    conn = _db()
    try:
        assert conn.execute("SELECT 1 FROM posts WHERE id = ?", (written,)).fetchone(), "a post written here went"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Installs the defect already reached
# ---------------------------------------------------------------------------

def _publication_row(conn, urn, text, post_id=None, source="urn_decode"):
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, first_seen_at, "
                 "last_seen_at, post_id) VALUES (?, ?, ?, ?, ?, ?, ?)", (urn, text, now, source, now, now, post_id))


def test_the_upgrade_gives_every_publication_its_post_again(client):
    import migrations
    from database import get_db_path
    bind_me, plain, captionless, healthy = _urn(70, 12), _urn(60, 13), _urn(50, 14), _urn(40, 15)
    conn = _db()
    with conn:
        # A studio draft one orphan's words match: the rule binds it rather than making a second post.
        conn.execute("INSERT INTO posts (id, content, status, created_at) VALUES ('post-studio-draft', ?, 'draft', ?)",
                     (TEXT, (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()))
        conn.execute("INSERT INTO posts (id, content, status, activity_urn, source) "
                     "VALUES ('post-healthy', ?, 'published', ?, 'linkedin')", (OTHER, healthy))
        _publication_row(conn, bind_me, TEXT)
        _publication_row(conn, plain, OTHER + " Plain.")
        _publication_row(conn, captionless, None)
        _publication_row(conn, healthy, OTHER, post_id="post-healthy")
        _publication_row(conn, "urn:inox:post:post-studio-local", "Local", post_id="post-studio-local")
    conn.close()
    before = len([r for r in _db().execute("SELECT id FROM posts")])

    # A database at 2.7.0's schema, as every install that met the defect is:
    # the migrations after it run in order, this track's among them, which
    # is found by its function, never by its number.
    raw = sqlite3.connect(get_db_path())
    raw.execute("PRAGMA user_version = 27")
    report = migrations.ensure_schema(raw, take_backup=False)
    raw.close()
    ours = next(m[0] for m in migrations.MIGRATIONS if m[2] is migrations._migrate_reader_timing_and_network_reading)
    assert ours in [a["version"] for a in report["applied"]], report

    assert _publication(bind_me)["post_id"] == "post-studio-draft", "the orphan did not bind to its draft"
    for urn in (plain, captionless):
        post_id = _publication(urn)["post_id"]
        assert post_id == f"post-{hashlib.sha256(urn.encode('utf-8')).hexdigest()[:12]}"
        assert _posts_carrying(urn)[0]["source"] == "linkedin"
    assert _publication(healthy)["post_id"] == "post-healthy"
    assert _publication("urn:inox:post:post-studio-local")["post_id"] == "post-studio-local"
    for urn in (bind_me, plain, captionless, healthy):
        assert _engagers(client, urn).status_code == 200
    after = len([r for r in _db().execute("SELECT id FROM posts")])
    assert after == before + 2, "the upgrade made a post it should have bound, or skipped one"

    # Idempotent: the work still to do is what is left without a post.
    raw = sqlite3.connect(get_db_path())
    migrations._migrate_reader_timing_and_network_reading(raw.cursor())
    raw.commit()
    raw.close()
    assert len([r for r in _db().execute("SELECT id FROM posts")]) == after


# ---------------------------------------------------------------------------
# The guard: every writer of a publication or an engagement goes through the rule
# ---------------------------------------------------------------------------

SQL_WRITES = re.compile(r"INSERT(?:\s+OR\s+\w+)?\s+INTO\s+(own_posts|lead_interactions)\b", re.IGNORECASE)
ENGAGEMENT_WRITER = "ingest_interaction"
# The ways through the rule, and the step each must take itself, down to
# post_identity.ensure_post, the rule.
GATEWAYS = {
    "ensure_post": None,
    "note_own_post": "ensure_post",
    "_bind_to_studio": "ensure_post",
    "ingest_own_posts": "_bind_to_studio",
}
# The rule's own module, the one low-level engagement writer (its callers are
# held instead), and the migrations, which are a frozen record of what ran.
EXEMPT_FILES = {"post_identity.py", "migrations.py"}
EXEMPT_FUNCTIONS = {("crm.py", ENGAGEMENT_WRITER)}


def _named(node, name):
    """Whether code under this node uses the name, as a call or as a value. Comments and docstrings do not count."""
    return any((isinstance(n, ast.Name) and n.id == name) or (isinstance(n, ast.Attribute) and n.attr == name)
               for n in ast.walk(node))


def _functions_of(tree):
    """Every function, with the functions that enclose it."""
    stack = [(tree, [])]
    while stack:
        node, enclosing = stack.pop()
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield child, enclosing
                stack.append((child, enclosing + [child]))
            else:
                stack.append((child, enclosing))


def _parents(tree):
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _rule_follows(function, site, parents):
    """
    Whether, after the statement holding this write, the flow out of the
    function passes a way through the rule: a later statement of the same
    block, or of any block enclosing it, up to the function.
    """
    node = site
    while not isinstance(node, ast.stmt):
        node = parents[node]
    while node is not function:
        parent = parents[node]
        for field in ("body", "orelse", "finalbody", "handlers"):
            block = getattr(parent, field, None)
            if isinstance(block, list) and node in block:
                later = block[block.index(node) + 1:]
                if any(_named(statement, gateway) for statement in later for gateway in GATEWAYS):
                    return True
        node = parent
    return False


def _writers():
    """
    Every function that writes a publication or an engagement, with whether it
    goes through the rule: a publication insert must be followed by a way
    through it, and an engagement writer must take one anywhere in the
    function or around it, because the route makes the post known first.
    """
    found, gateways = [], {}
    for root, dirs, files in os.walk(BACKEND):
        dirs[:] = [d for d in dirs if d not in ("tests", "__pycache__")]
        for name in files:
            if not name.endswith(".py"):
                continue
            rel = os.path.relpath(os.path.join(root, name), BACKEND).replace(os.sep, "/")
            if rel in EXEMPT_FILES:
                continue
            with open(os.path.join(root, name), encoding="utf-8") as handle:
                tree = ast.parse(handle.read())
            parents = _parents(tree)
            for function, enclosing in _functions_of(tree):
                if function.name in GATEWAYS:
                    gateways[function.name] = function
                if any((rel, f.name) in EXEMPT_FUNCTIONS for f in enclosing + [function]):
                    continue
                inserts = [n for n in ast.walk(function)
                           if isinstance(n, ast.Constant) and isinstance(n.value, str) and SQL_WRITES.search(n.value)]
                engagement = _named(function, ENGAGEMENT_WRITER)
                if not inserts and not engagement:
                    continue
                scopes = [function] + enclosing
                ok = all(_rule_follows(function, site, parents) for site in inserts)
                if engagement:
                    ok = ok and any(_named(scope, gateway) for scope in scopes for gateway in GATEWAYS
                                    if gateway != function.name)
                found.append((rel, function, ok))
    return found, gateways


def test_every_writer_of_a_post_or_its_engagement_goes_through_the_one_rule():
    writers, gateways = _writers()
    names = {(rel, function.name) for rel, function, _ in writers}
    # The guard must be reading the writers it exists for.
    for expected in (("onboarding.py", "ingest_own_posts"), ("onboarding.py", "note_own_post"),
                     ("archive_import.py", "_import_posts"), ("routers/crm.py", "_write_engagement"),
                     ("database.py", "seed_demo_identity")):
        assert expected in names, f"the guard no longer finds {expected}"
    outside = [(rel, function.name) for rel, function, ok in writers if not ok]
    assert not outside, (
        f"{outside} write a publication or an engagement without going through post_identity.ensure_post, "
        "so a post first found there gets no posts row and its engagers route answers 404")
    for gateway, step in GATEWAYS.items():
        if step:
            assert gateway in gateways and _named(gateways[gateway], step), (
                f"{gateway} no longer calls {step}, so it is not a way through the rule")
