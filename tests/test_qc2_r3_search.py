"""
Search answers from an index, and the index follows the data.
============================================================

Cycle 2, batch R3 (DATA-03).

Universal search ran a substring test through a Python function on every row
of leads joined to every interaction: 2 s for any query on three years of one
creator's data, including a query that matched nothing. It now reads FTS5
tables (unicode61, accents removed) that migration 22 builds and triggers keep
in step with posts, LinkedIn posts, leads and comments. The owner chose prefix
matching: "pric" finds pricing, and "pricing" no longer finds "repricing".
"""

import os
import shutil
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

import qc2_r3_data  # noqa: E402


@pytest.fixture
def home(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_qc2_r3_search_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    init_db()
    conn = get_db()
    data = qc2_r3_data.build(conn)
    conn.close()
    yield data
    shutil.rmtree(path, ignore_errors=True)


def _db():
    from database import get_db
    return get_db()


def _titles(found):
    return [item["title"] for item in found]


def test_search_reads_the_index_and_calls_no_python_per_row(home, monkeypatch):
    import universal_search
    conn = _db()
    seen = []
    conn.set_trace_callback(seen.append)
    try:
        universal_search.search_leads(["pricing"], conn=conn)
        universal_search.search_posts(["pricing"], conn=conn)
    finally:
        conn.set_trace_callback(None)
    try:
        assert seen and not any("inox_fold" in s for s in seen), "a Python function still runs on every row"
        assert any("search_leads MATCH" in s for s in seen) and any("search_posts MATCH" in s for s in seen)
        for statement in seen:
            if "MATCH" in statement and "search_docs d JOIN leads" in statement:
                plan = " | ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + statement))
                assert "SCAN lead_interactions" not in plan and "SCAN i" not in plan, plan
    finally:
        conn.close()


def test_words_are_matched_from_their_start(home):
    import universal_search
    conn = _db()
    try:
        with conn:
            conn.execute("INSERT INTO posts (id, content, status) VALUES ('p-re', 'Repricing our plans', 'draft')")
            conn.execute("INSERT INTO posts (id, content, status) VALUES ('p-pr', 'Pricing that works', 'draft')")
        ids = lambda q: {p["id"] for p in universal_search.search_posts(universal_search.terms_of(q), 20, conn)}
        assert "p-pr" in ids("pric") and "p-pr" in ids("PRICING")
        assert "p-re" not in ids("pricing"), "prefix search, the owner's choice: not inside a word"
        assert "p-re" in ids("repric")
    finally:
        conn.close()


def test_letters_are_folded_both_ways(home):
    import universal_search
    conn = _db()
    try:
        with conn:
            for lead_id, name in (("l-ss", "Hanna Weißbrot"), ("l-oe", "Søren Ølgaard"), ("l-ae", "Ångström Ñandú")):
                conn.execute("INSERT INTO leads (id, name, full_name, status, lead_status) "
                             "VALUES (?, ?, ?, 'New Lead', 'NEW')", (lead_id, name, name))
        for query, name in (("weissbrot", "Hanna Weißbrot"), ("WEIßBROT", "Hanna Weißbrot"), ("angstrom nandu", "Ångström Ñandú"),
                            ("Ølgaard", "Søren Ølgaard")):
            assert _titles(universal_search.search_leads(universal_search.terms_of(query), 6, conn)) == [name], query
    finally:
        conn.close()


VOCABULARY = ["pricing", "pric", "great", "post", "question", "sourdough", "olander", "cafe", "naive", "strasse",
              "asha", "ravi", "zoe", "isik", "head", "growth", "ops", "crumb", "acme", "meetup", "studio", "twin",
              "second", "line", "draft", "how", "thanks", "price", "lee", "mei", "tom", "ana", "emile"]


def _snapshot(conn):
    """For every word, which posts, LinkedIn posts and leads the index finds, by their own keys."""
    import universal_search
    out = {}
    for word in VOCABULARY:
        match = universal_search._match_word(word)
        out[("text", word)] = sorted(tuple(r) for r in conn.execute(
            "SELECT d.kind, d.ref FROM search_posts f JOIN search_docs d ON d.docid = f.rowid "
            "WHERE search_posts MATCH ?", (match,)))
        out[("lead", word)] = sorted(tuple(r) for r in conn.execute(
            "SELECT d.ref FROM search_leads f JOIN search_docs d ON d.docid = f.rowid "
            "WHERE search_leads MATCH ?", (match,)))
        out[("said", word)] = sorted(tuple(r) for r in conn.execute(
            "SELECT d.ref, f.rowid & 4294967295 FROM search_comments f JOIN search_docs d ON d.docid = f.rowid >> 32 "
            "WHERE search_comments MATCH ?", (match,)))
    return out


def _rebuilt(conn):
    import universal_search
    with conn:
        universal_search.build_search_index(conn)
    return _snapshot(conn)


@pytest.mark.parametrize("changes", [
    ["UPDATE posts SET content = 'Sourdough pricing, rewritten' WHERE id = 'post-0'",
     "UPDATE posts SET tags = '[\"strasse\"]' WHERE id = 'post-3'",
     "DELETE FROM posts WHERE id = 'post-6'",
     "INSERT INTO posts (id, content, status) VALUES ('post-new', 'A new draft about growth', 'draft')",
     "UPDATE posts SET id = 'post-renamed' WHERE id = 'post-9'"],
    ["UPDATE own_posts SET text = 'Olander café notes' WHERE rowid % 4 = 0",
     "DELETE FROM own_posts WHERE rowid % 5 = 0",
     "UPDATE own_posts SET last_seen_at = '2030-01-01' WHERE rowid % 3 = 0"],
    ["UPDATE leads SET full_name = 'Mei Pricing', name = 'Mei Pricing' WHERE rowid % 6 = 0",
     "UPDATE leads SET headline = 'Head of Sourdough', company = NULL WHERE rowid % 7 = 0",
     "UPDATE leads SET notes = 'met at the meetup' WHERE rowid % 8 = 0",
     "UPDATE leads SET updated_at = '2031-01-01' WHERE rowid % 2 = 0",
     "INSERT INTO leads (id, name, full_name, status, lead_status) VALUES ('lead-late', 'Late Lead', 'Late Lead', 'New Lead', 'NEW')"],
    ["DELETE FROM leads WHERE rowid % 3 = 0",
     "DELETE FROM lead_interactions WHERE id % 4 = 0",
     "UPDATE OR IGNORE lead_interactions SET comment_text = 'thanks for the sourdough' WHERE id % 5 = 0",
     "UPDATE OR IGNORE lead_interactions SET comment_text = NULL WHERE id % 7 = 0",
     "UPDATE OR IGNORE lead_interactions SET lead_id = 'lead-0002' WHERE id % 9 = 0",
     "INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, comment_text) "
     "VALUES ('lead-0003', NULL, 'COMMENT', 'a question about pricing')"],
    # An interaction recorded before its lead existed, then the lead.
    ["INSERT INTO lead_interactions (lead_id, interaction_type, comment_text) VALUES ('lead-early', 'COMMENT', 'early pricing question')",
     "INSERT INTO leads (id, name, full_name, status, lead_status) VALUES ('lead-early', 'Early Bird', 'Early Bird', 'New Lead', 'NEW')",
     "DELETE FROM lead_interactions WHERE lead_id = 'lead-early'"],
    ["DELETE FROM lead_interactions", "DELETE FROM leads", "DELETE FROM posts", "DELETE FROM own_posts"],
])
def test_the_index_follows_every_change(home, changes):
    """The triggers' index equals one built from scratch over the rows as they now are."""
    conn = _db()
    # Direct SQL, as an import or a repair might write it, rows out of order included.
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        with conn:
            for change in changes:
                conn.execute(change)
        maintained = _snapshot(conn)
        assert maintained == _rebuilt(conn)
        assert any(maintained.values()) or "DELETE FROM leads" in changes
    finally:
        conn.close()


def test_the_index_follows_the_studios_own_writers(home):
    import crm
    import universal_search
    from fastapi.testclient import TestClient
    import app as app_module
    client = TestClient(app_module.app)
    crm.reverse_crm.ingest_interaction(full_name="Quill Marsh", linkedin_urn="https://www.linkedin.com/in/quill",
                                       headline="Head of Sourdough", interaction_type="COMMENT",
                                       comment_text="Grommetwise pricing question", post_urn=home["own"][0])
    post = client.post("/api/posts", json={"content": "Xylophonic launch notes", "status": "draft"}).json()["id"]
    conn = _db()
    try:
        assert _titles(universal_search.search_leads(["grommetwise"], 6, conn)) == ["Quill Marsh"]
        assert [p["id"] for p in universal_search.search_posts(["xylophonic"], 6, conn)] == [post]
        maintained = _snapshot(conn)
        assert maintained == _rebuilt(conn)
    finally:
        conn.close()


def test_a_forgotten_person_cannot_be_found_by_what_they_said(home):
    """Forget removes the person's comments from the index too, whichever trigger runs first."""
    import crm
    import universal_search
    crm.reverse_crm.ingest_interaction(full_name="Vela Quorn", linkedin_urn="https://www.linkedin.com/in/vela",
                                       headline="CTO", interaction_type="COMMENT",
                                       comment_text="Zanzibarite onboarding question", post_urn=home["own"][1])
    conn = _db()
    try:
        lead_id = conn.execute("SELECT id FROM leads WHERE full_name = 'Vela Quorn'").fetchone()[0]
        assert _titles(universal_search.search_leads(["zanzibarite"], 6, conn)) == ["Vela Quorn"]
    finally:
        conn.close()
    crm.reverse_crm.purge_lead(lead_id)
    conn = _db()
    try:
        assert universal_search.search_leads(["zanzibarite"], 6, conn) == []
        assert universal_search.search_leads(["vela"], 6, conn) == []
        count = conn.execute("SELECT COUNT(*) FROM search_comments WHERE search_comments MATCH 'zanzibarite'").fetchone()[0]
        assert count == 0
    finally:
        conn.close()


def test_migration_22_indexes_an_existing_history(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_qc2_r3_mig22_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    try:
        import migrations
        import universal_search
        from database import init_db, get_db
        init_db()
        conn = get_db()
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger' "
                                    "AND name LIKE 'search_%'").fetchall():
            conn.execute(f"DROP TRIGGER {name}")
        for statement in ("search_docs", "search_posts", "search_leads", "search_comments"):
            conn.execute(f"DROP TABLE {statement}")
        conn.execute("PRAGMA user_version = 21")
        conn.commit()
        qc2_r3_data.build(conn)
        migrations.ensure_schema(conn, take_backup=False)
        assert _titles(universal_search.search_leads(["asha", "rao"], 3, conn)) == ["Asha Rao"] * 3
        snapshot = _snapshot(conn)
        assert snapshot == _rebuilt(conn), "running the build again changes nothing"
        conn.close()
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_the_leads_list_filter_uses_the_index(home):
    import universal_search
    sql, params = universal_search.lead_filter(universal_search.terms_of("head grow"))
    conn = _db()
    try:
        rows = conn.execute(f"SELECT l.headline FROM leads l WHERE {sql}", params).fetchall()
        assert rows and all("head of growth" in (r[0] or "").lower() for r in rows)
    finally:
        conn.close()
    assert universal_search.lead_filter(universal_search.terms_of("%")) is None


def test_help_folds_accents_the_way_search_does(home):
    import docs_engine
    conn = _db()
    try:
        docs_engine.init_docs_search_index(conn)
        definition = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'docs_index'").fetchone()[0]
        assert docs_engine.DOCS_TOKENIZER in definition
    finally:
        conn.close()
