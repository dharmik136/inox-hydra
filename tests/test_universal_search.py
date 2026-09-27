"""
Universal Search Guards
=======================
The command palette searched a list of its own actions and nothing else. A post
from last week, a lead whose name you half remember, the specimen with the
opening you liked: none could be found from anywhere but the surface that held
it, and an earlier post could not be found at all. The help article on drafts
had to say so in as many words: "No surface reopens an older post in the
Composer."

The palette also offered five actions that did not do what they said. "Generate
5 hooks", "Make sharper", "Add contrarian angle", "Turn into carousel" and
"Schedule at peak slot" each only switched screens.

/api/v1/search answers across posts, leads, specimens and the help, and each
result carries where it opens. These guards hold what that has to mean: every
word must match, a wildcard in a query is a character and not a wildcard, a
published post is never offered for editing, a group that fails says so, and
nothing leaves the machine.
"""

import json
import os
import subprocess
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI_SRC = os.path.join(REPO_ROOT, "studio", "ui", "src")
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

import universal_search  # noqa: E402
from database import get_db  # noqa: E402

from app import app  # noqa: E402
from tests.test_composer_text_measurement import ESBUILD, NODE  # noqa: E402

client = TestClient(app)


def _search(q, limit=6):
    response = client.get("/api/v1/search", params={"q": q, "limit": limit})
    assert response.status_code == 200, response.text
    return response.json()


def _rendered(path):
    import re
    if not os.path.exists(path):
        pytest.skip(f"{os.path.basename(path)} is not present in this checkout")
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    source = re.sub(r"\{/\*.*?\*/\}", "", source, flags=re.DOTALL)
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//[^\n]*$", "", source, flags=re.MULTILINE)


@pytest.fixture(scope="module")
def seeded():
    """
    One draft, one published post, one scheduled post, and a lead with a
    comment, each carrying a word nothing else in the sandbox contains.
    """
    draft = client.post("/api/posts", json={
        "content": "Xylophonic launch notes\n\nWhat the fold audit taught us.", "status": "draft"}).json()["id"]
    published = client.post("/api/posts", json={
        "content": "Xylophonic retrospective, already posted", "status": "published"}).json()["id"]
    scheduled = client.post("/api/posts", json={
        "content": "Xylophonic follow-up, waiting in the queue", "status": "scheduled",
        "scheduled_for": "2031-01-01T09:00:00"}).json()["id"]

    conn = get_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO leads (id, name, full_name, company, headline, status, lead_status) "
            "VALUES ('lead-us-1', 'Quillon Marsh', 'Quillon Marsh', 'Northwind Robotics', "
            "'Head of Platform', 'new', 'NEW')")
        conn.execute(
            "INSERT INTO lead_interactions (lead_id, interaction_type, comment_text) "
            "VALUES ('lead-us-1', 'COMMENT', 'The grommetwise drift section saved our week.')")
        conn.commit()
    finally:
        conn.close()
    return {"draft": draft, "published": published, "scheduled": scheduled}


# ---------------------------------------------------------------------------
# What is found, and where it opens
# ---------------------------------------------------------------------------

def test_an_empty_query_finds_nothing_and_asks_nothing():
    body = _search("   ")
    assert body["total"] == 0
    assert all(items == [] for items in body["groups"].values())


def test_posts_are_found_whatever_their_status(seeded):
    ids = {post["id"] for post in _search("xylophonic")["groups"]["posts"]}
    assert {seeded["draft"], seeded["published"], seeded["scheduled"]} <= ids, ids


def test_only_a_draft_is_offered_for_editing(seeded):
    """
    The Composer holds one post and Save writes over whichever post it holds,
    so opening a published or queued post there would make the next Save
    quietly rewrite something that has already gone out or is waiting to.
    """
    opens = {post["id"]: post["opens"] for post in _search("xylophonic")["groups"]["posts"]}
    assert opens[seeded["draft"]] == "composer"
    assert opens[seeded["published"]] == "analytics", opens
    assert opens[seeded["scheduled"]] == "queue", opens


def test_every_word_must_match(seeded):
    """ "acme cto" should find the CTO at Acme, not every CTO and everyone at Acme. """
    assert _search("xylophonic fold")["groups"]["posts"], "both words are in the draft"
    ids = {post["id"] for post in _search("xylophonic fold")["groups"]["posts"]}
    assert ids == {seeded["draft"]}, f"a post missing one of the words matched: {ids}"
    assert not _search("xylophonic zzzabsent")["groups"]["posts"]


def test_a_wildcard_in_a_query_is_a_character(seeded):
    """
    LIKE treats % and _ as wildcards. Unescaped, a search for "%" matched every
    row in the table, which is a search that returns everything and means
    nothing.
    """
    # The property is not "no results": a post that really says "80%" should be
    # found by "%". It is that every result contains the characters literally.
    # The first version of this test asserted no results and failed on exactly
    # such a post, which was the escaping working.
    conn = get_db()
    try:
        contents = {str(r["id"]): (r["content"] or "").lower() for r in conn.execute("SELECT id, content FROM posts")}
    finally:
        conn.close()
    for query in ("%", "_", "%%", "x_l", "100%"):
        for post in _search(query)["groups"]["posts"]:
            assert query in contents[post["id"]], (
                f"{query!r} matched {post['id']}, which does not contain it: a wildcard, not a character"
            )
    assert not _search("x_l")["groups"]["posts"], "an underscore matched any single character"
    total = len(contents)
    assert len(_search("%", limit=20)["groups"]["posts"]) < total, "'%' matched every post in the table"


def test_a_lead_is_found_by_what_they_said(seeded):
    """A comment someone left is often the one thing you remember about them."""
    leads = _search("grommetwise")["groups"]["leads"]
    assert [lead["id"] for lead in leads] == ["lead-us-1"], leads
    assert leads[0]["snippet"].startswith("Commented:"), leads[0]["snippet"]
    assert leads[0]["opens"] == "leads"

    by_profile = _search("quillon northwind")["groups"]["leads"]
    assert by_profile and not by_profile[0]["snippet"].startswith("Commented:")


def test_a_specimen_carries_the_id_the_swipe_file_renders():
    """
    Opening a result means finding it on the surface. The Swipe File keys its
    cards by the id /api/inspirations returns, so search must return the same.
    """
    rendered = {str(item["id"]) for item in client.get("/api/inspirations").json().get("inspirations", [])}
    if not rendered:
        pytest.skip("no specimens in this sandbox")
    found = _search("egress")["groups"]["specimens"] or _search("hook")["groups"]["specimens"]
    assert found, "no specimen matched a common word"
    for item in found:
        assert item["id"] in rendered, f"{item['id']} is not an id the Swipe File renders"


def test_help_is_ranked_the_way_docs_ranks_it():
    """
    The same ordering as the Docs search: help, then reference, then retired,
    and a retired manual is marked as one before anyone opens it.
    """
    help_hits = _search("extension", limit=20)["groups"]["help"]
    assert help_hits, "no help hits for a word the help is full of"
    retired = [hit["retired"] for hit in help_hits]
    assert retired == sorted(retired), f"a retired manual ranks above current help: {retired}"
    assert help_hits[0]["retired"] is False
    assert all(hit["anchor_text"] for hit in help_hits), "a help hit has no heading to open at"


def test_a_group_that_fails_says_so(monkeypatch):
    """
    Silence from a group reads as "no matches". A group that could not be
    searched is reported, so the palette can say which one.
    """
    def broken(*args, **kwargs):
        raise RuntimeError("leads table unavailable")

    monkeypatch.setattr(universal_search, "search_leads", broken)
    body = _search("anything")
    assert "leads" in body["failures"], body["failures"]
    assert body["groups"]["leads"] == []


def test_the_query_is_bounded():
    assert len(universal_search.terms_of("a " * 50)) == universal_search.MAX_TERMS
    assert len("".join(universal_search.terms_of("x" * 5000))) <= universal_search.MAX_QUERY_LENGTH


def test_search_reaches_nothing_off_this_machine():
    """
    Every group is SQLite or the offline documentation index. The module has
    no way to make a request, and the route does not call one that does.
    """
    path = os.path.join(REPO_ROOT, "studio", "backend", "universal_search.py")
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    for forbidden in ("requests", "httpx", "urllib", "socket", "egress"):
        assert f"import {forbidden}" not in source and f"from {forbidden}" not in source, forbidden


# ---------------------------------------------------------------------------
# The palette
# ---------------------------------------------------------------------------

PALETTE = os.path.join(UI_SRC, "components", "CommandPalette.tsx")


def test_the_palette_offers_no_action_that_does_not_do_what_it_says():
    source = _rendered(PALETTE)
    for label in ("Generate 5 hooks", "Make sharper", "Add contrarian angle",
                  "Turn into carousel", "Schedule at peak slot", "Audit for reach", "Check fold safety"):
        assert label not in source, f"{label!r} is offered again, and it only switches screens"


def test_the_palette_offers_only_the_sections_the_rail_offers():
    """It listed Devtools when the surface was off, which led to a dead end."""
    source = _rendered(PALETTE)
    assert "STUDIO_SECTIONS" not in source, "the palette reads the full list instead of the rail's"
    assert "sections.map" in source


def test_the_palette_does_not_re_rank_what_the_server_found():
    """
    cmdk's own filter scores items by their label, which would hide a post whose
    match is in its body rather than its first line.
    """
    assert "shouldFilter={false}" in _rendered(PALETTE)


def test_search_can_be_seen_as_well_as_typed():
    """Ctrl+K was mentioned nowhere on screen, so for most people search did not exist."""
    rail = _rendered(os.path.join(UI_SRC, "components", "StudioRail.tsx"))
    assert 'aria-label="Search everything (Ctrl+K)"' in rail
    app_source = _rendered(os.path.join(UI_SRC, "App.tsx"))
    assert "Search everything" in app_source


def test_unsaved_text_is_asked_about_before_a_draft_replaces_it():
    source = _rendered(os.path.join(UI_SRC, "App.tsx"))
    assert "window.confirm(" in source, "opening a draft can discard unsaved text without asking"
    assert 'result.opens !== "composer"' in source, "a non-draft post can be loaded into the editor"


def test_an_anchor_waits_for_its_heading():
    """
    Opened from search, Docs mounts from nothing and the document can arrive
    before the library. The jump used to run then, find no heading, clear
    itself, and leave the article open at the top.
    """
    source = _rendered(os.path.join(UI_SRC, "components", "DocsSurface.tsx"))
    assert "if (!document.getElementById(anchor)) return;" in source


# ---------------------------------------------------------------------------
# Highlighting, executed
# ---------------------------------------------------------------------------

PROBE = r"""
import { highlightRuns, matchesAll, termsOf } from "./search.js";
const flat = (runs) => runs.map((r) => (r.matched ? "[" + r.text + "]" : r.text)).join("");
console.log(JSON.stringify({
  basic: flat(highlightRuns("The Fold audit found the fold", ["fold"])),
  longest: flat(highlightRuns("fold audit", ["fold", "fold audit"])),
  literal: flat(highlightRuns("Learning c++ and (draft) notes", ["c++", "(draft)"])),
  markup: flat(highlightRuns("<b>bold</b> text", ["bold"])),
  none: flat(highlightRuns("nothing here", [])),
  every: [matchesAll("Go to Leads", ["go", "leads"]), matchesAll("Go to Leads", ["go", "queue"])],
  terms: termsOf("  Acme   CTO  "),
}));
"""


@pytest.fixture(scope="module")
def highlight():
    if not NODE or not ESBUILD:
        pytest.skip("Node or the UI dependencies are not installed")
    module = os.path.join(UI_SRC, "lib", "search.ts")
    with tempfile.TemporaryDirectory() as work:
        out = os.path.join(work, "search.js")
        build = subprocess.run([ESBUILD, module, "--format=esm", f"--outfile={out}"],
                               capture_output=True, text=True)
        assert build.returncode == 0, build.stderr
        probe = os.path.join(work, "probe.mjs")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write(PROBE)
        run = subprocess.run([NODE, probe], capture_output=True, text=True, cwd=work)
        assert run.returncode == 0, run.stderr
        return json.loads(run.stdout)


def test_every_occurrence_is_marked_whatever_its_case(highlight):
    assert highlight["basic"] == "The [Fold] audit found the [fold]", highlight["basic"]


def test_the_longer_term_wins_a_tie(highlight):
    assert highlight["longest"] == "[fold audit]", highlight["longest"]


def test_terms_are_matched_literally(highlight):
    """A query is text. Compiled into a pattern, "c++" throws and "(draft)" is a group."""
    assert highlight["literal"] == "Learning [c++] and [(draft)] notes", highlight["literal"]


def test_markup_in_a_result_stays_text(highlight):
    assert highlight["markup"] == "<b>[bold]</b> text", highlight["markup"]


def test_no_terms_means_no_marks(highlight):
    assert highlight["none"] == "nothing here"


def test_actions_need_every_word_too(highlight):
    assert highlight["every"] == [True, False]
    assert highlight["terms"] == ["acme", "cto"]
