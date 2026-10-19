"""
Universal search finds people by their real names and finds your LinkedIn posts.
================================================================================

Quality cycle 2026-10, batch F5b.

AUDIENCE-07. Leads were matched with SQLite's LOWER, which folds ASCII only,
against a query Python had lowercased, so "Émile" never found Émile Durand and
"Ölander" never found Zoë Ölander, even typed exactly. The help search threw
away every letter outside ASCII, so "Émile" became "mile" and the palette
offered unrelated planning documents. A name typed in quotes found nothing.

AUDIENCE-08. Posts were searched only in the studio's own posts table, so a
word from any post imported from LinkedIn found nothing at all.

Each test runs in a throwaway home of its own.
"""

import os
import shutil
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

from fastapi.testclient import TestClient  # noqa: E402

ME = "f5b-search"


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc_f5b_search_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    init_db()
    conn = get_db()
    with conn:
        conn.execute("INSERT OR REPLACE INTO creator_identity (id, vanity, display_name, confirmed_at) "
                     "VALUES (1, ?, 'F5b Search', '2026-09-27T00:00:00+00:00')", (ME,))
        for lead_id, name, headline in (
            ("lead-emile", "Émile Durand", "Chef pâtissier at Maison É"),
            ("lead-zoe", "Zoë Ölander", "Head of Growth at Ölander AB"),
            ("lead-asha", "Asha Rao", "Founder at Crumb Co"),
        ):
            conn.execute("INSERT INTO leads (id, name, full_name, headline, status, lead_status) "
                         "VALUES (?, ?, ?, ?, 'New Lead', 'NEW')", (lead_id, name, name, headline))
        conn.execute("INSERT INTO lead_interactions (lead_id, interaction_type, comment_text) "
                     "VALUES ('lead-emile', 'COMMENT', 'Merci pour le partage, très utile')")
    conn.close()
    import app as app_module
    yield TestClient(app_module.app)
    shutil.rmtree(home, ignore_errors=True)


def _search(client, q):
    res = client.get("/api/v1/search", params={"q": q})
    assert res.status_code == 200, res.text
    return res.json()


def _lead_names(client, q):
    return [lead["title"] for lead in _search(client, q)["groups"]["leads"]]


# ---------------------------------------------------------------------------
# AUDIENCE-07
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", ["Émile", "émile", "ÉMILE", "emile", "Emile Durand", '"Émile"'])
def test_an_accented_name_is_found_however_it_is_typed(studio, query):
    assert _lead_names(studio, query) == ["Émile Durand"], query


@pytest.mark.parametrize("query", ["Ölander", "ölander", "olander", "Zoë", "zoe ölander"])
def test_a_name_with_an_umlaut_is_found(studio, query):
    assert _lead_names(studio, query) == ["Zoë Ölander"], query


@pytest.mark.parametrize("query", ['"Asha"', "'Asha'", "“Asha”", '"Asha Rao"'])
def test_a_name_in_quotes_is_found(studio, query):
    assert _lead_names(studio, query) == ["Asha Rao"], query


def test_the_terms_handed_back_for_highlighting_keep_their_letters(studio):
    body = _search(studio, '"Émile"')
    assert body["terms"] == ["émile"], body["terms"]


def test_what_someone_said_is_found_with_its_accents(studio):
    leads = _search(studio, "tres utile")["groups"]["leads"]
    assert [lead["title"] for lead in leads] == ["Émile Durand"]
    assert "très utile" in leads[0]["snippet"], leads[0]["snippet"]


def test_help_found_for_an_accented_name_contains_that_name(studio):
    # The palette article names Émile as its own example; anything else that
    # came back would have matched "mile", what was left once the É was dropped.
    import universal_search
    hits = _search(studio, "Émile")["groups"]["help"]
    assert all("emile" in universal_search.fold(hit["snippet"]) for hit in hits), \
        "the help search dropped the É and matched 'mile'"
    assert _search(studio, "Zoë Ölander")["groups"]["help"] == []


def test_sql_shaped_input_is_only_text(studio):
    for query in ("' OR 1=1 --", "\"; DROP TABLE leads; --", "%", "_"):
        body = _search(studio, query)
        assert body["groups"]["leads"] == [], (query, body["groups"]["leads"])
    assert _lead_names(studio, "Asha") == ["Asha Rao"], "the leads table did not survive the queries above"


# ---------------------------------------------------------------------------
# AUDIENCE-08
# ---------------------------------------------------------------------------

def _urn(n):
    return f"urn:li:activity:{(1780000000000 + n * 86400000) << 22}"


def _import(client, *texts):
    items = [{"activity_urn": _urn(i), "actor": ME, "text": text, "reactions": 10} for i, text in enumerate(texts)]
    res = client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": items})
    assert res.status_code == 200, res.text
    return [item["activity_urn"] for item in items]


def test_a_post_imported_from_linkedin_is_found(studio):
    urns = _import(studio, "Why sourdough needs patience\nHere is what I learned.",
                   "Our café in Zürich: first month numbers")
    posts = _search(studio, "sourdough")["groups"]["posts"]
    assert [p["id"] for p in posts] == [urns[0]], posts
    assert posts[0]["title"] == "Why sourdough needs patience"
    assert posts[0]["opens"] == "analytics", "a published post was offered somewhere it can be edited"
    assert posts[0]["meta"].startswith("PUBLISHED ON LINKEDIN")
    assert [p["id"] for p in _search(studio, "zurich cafe")["groups"]["posts"]] == [urns[1]]


def test_a_studio_post_and_its_linkedin_post_are_one_result(studio):
    text = "Flour waste fell by a third once we weighed every batch"
    post_id = studio.post("/api/posts", json={"content": text, "status": "published"}).json()["id"]
    from database import get_db
    conn = get_db()
    with conn:
        conn.execute("UPDATE posts SET activity_urn = ? WHERE id = ?", (_urn(0), post_id))
    conn.close()
    _import(studio, text)
    posts = _search(studio, "flour waste")["groups"]["posts"]
    assert [p["id"] for p in posts] == [post_id], posts


def test_a_turkish_dotless_i_is_found_from_a_plain_i(studio):
    from database import get_db
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO leads (id, name, full_name, status, lead_status) "
                     "VALUES ('lead-isik', 'Işık Demir', 'Işık Demir', 'New Lead', 'NEW')")
    conn.close()
    for query in ("isik", "IŞIK", "Işık", "ışık"):
        assert _lead_names(studio, query) == ["Işık Demir"], query


def test_a_lone_accent_matches_nothing(studio):
    body = _search(studio, "́")
    assert body["groups"]["leads"] == [] and body["groups"]["posts"] == [], "an empty term matched everything"
