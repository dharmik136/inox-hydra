"""
Documentation Library Guards
============================
The offline search index has always covered every markdown file under the docs
directory, 38 of them. The product exposed 7.

So a search could match a section of DATA_ARCHITECTURE.md, rank it, build a
real snippet with the terms marked, render it, and have nowhere to send the
reader: there was no route that could open that file. Four fifths of everything
the index could find was unreachable, and the result list was not clickable,
which was at least consistent.

Three things were wrong at once, and each has guards here:

1. Only the curated seven could be opened. Every indexed file now has an id,
   and resolution is a dictionary lookup against a table built by walking the
   directory, so a request selects a row and never contributes a path segment.
2. A hit named a filename and nothing else, so it could not become a
   destination. It now carries the id of the document the section lives in.
3. The response had no title field and the client read data.title, so every
   document in the reader was headed by its own raw id: "studio-editor" instead
   of "Studio & Editor". The build was clean and the suite was green.
"""

import os
import re
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI_SRC = os.path.join(REPO_ROOT, "studio", "ui", "src")
DOCS_DIR = os.path.join(REPO_ROOT, "docs")
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

import docs_engine  # noqa: E402

from app import app  # noqa: E402

client = TestClient(app)


def _read(path):
    if not os.path.exists(path):
        pytest.skip(f"{os.path.basename(path)} is not present in this checkout")
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _rendered(path):
    """
    A component's source with comments removed.

    Shared with tests/test_prototype_sweep.py and tests/test_egress_surface.py
    for the same reason all three need it: a guard that greps a component for a
    sentence must not match the comment explaining why that sentence is there.
    The <pre> check below failed on the paragraph explaining why <pre> was
    taken out, which is the fourth time a guard in this suite has caught its
    own rationale.
    """
    source = _read(path)
    source = re.sub(r"\{/\*.*?\*/\}", "", source, flags=re.DOTALL)
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//[^\n]*$", "", source, flags=re.MULTILINE)


def _write(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _markdown_files():
    out = []
    for root, _, files in os.walk(DOCS_DIR):
        for name in files:
            if name.endswith(".md"):
                rel = os.path.relpath(os.path.join(root, name), DOCS_DIR)
                out.append(rel.replace(os.sep, "/"))
    return sorted(out)


@pytest.fixture(scope="module", autouse=True)
def real_corpus_index():
    """
    Build the index from the real docs directory before asserting against it.

    There is exactly one docs_index table for the whole session, and another
    test rebuilds it from a temporary directory holding a single file. Running
    this module alone passed; running the suite failed with "no hits to
    inspect", because by then the index described a directory that no longer
    existed. A guard whose verdict depends on which files ran before it is not
    a guard, so this one states its own precondition.
    """
    indexed = docs_engine.init_docs_search_index()
    assert indexed > 0, "the documentation index did not build, so nothing below proves anything"
    return indexed


@pytest.fixture(scope="module")
def catalogue():
    response = client.get("/api/docs")
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Every indexed file is reachable
# ---------------------------------------------------------------------------

def test_the_library_lists_every_file_the_index_covers(catalogue):
    """
    The gap this file exists for. The indexer walks docs/ for *.md; the listing
    has to cover the same set, or a search can match something the product
    cannot open.
    """
    if not os.path.isdir(DOCS_DIR):
        pytest.skip("docs/ is not present in this checkout")
    on_disk = set(_markdown_files())
    listed = {entry["path"] for entry in catalogue["library"]}
    assert on_disk == listed, (
        "the library and the search index disagree about which files exist. "
        f"indexed but unlisted: {sorted(on_disk - listed)[:6]}; "
        f"listed but absent: {sorted(listed - on_disk)[:6]}"
    )


def test_every_indexed_document_can_be_opened(catalogue):
    """
    Not "most". A file the index can match and the product cannot open is a
    search result that goes nowhere, which is what 31 of these 38 files were.
    """
    assert len(catalogue["library"]) >= 30, (
        f"the library lists {len(catalogue['library'])} documents, which is back "
        "near the seven curated modules"
    )
    unopenable = []
    for entry in catalogue["library"]:
        response = client.get(f"/api/docs/{entry['id']}")
        if response.status_code != 200 or not response.json().get("content", "").strip():
            unopenable.append((entry["id"], entry["path"], response.status_code))
    assert not unopenable, f"documents listed but not openable: {unopenable[:6]}"


def test_the_curated_seven_keep_their_own_ids(catalogue):
    """The existing contract. A link built from a curated id keeps working."""
    ids = {module["id"] for module in catalogue["modules"]}
    assert {"studio-editor", "viral-swipe-file", "analytics", "enterprise-usage"} <= ids
    for module_id in sorted(ids):
        assert client.get(f"/api/docs/{module_id}").status_code == 200, module_id


def test_a_curated_file_answers_to_both_of_its_ids():
    """
    Two vocabularies name the same file: a hand written id and a path slug. They
    have to land on one document, or a search hit and a sidebar click open
    different things that look the same.
    """
    curated = client.get("/api/docs/studio-editor")
    slug = client.get("/api/docs/modules-01_studio_and_editor")
    number = client.get("/api/docs/01")
    assert curated.status_code == slug.status_code == number.status_code == 200
    assert curated.json()["path"] == slug.json()["path"] == number.json()["path"]
    assert curated.json()["id"] == slug.json()["id"] == "studio-editor", (
        "the slug resolves to a different record than the curated id"
    )


def test_a_document_is_returned_with_its_title():
    """
    The reader read data.title from a response that never had one, so every
    document was headed by its own id. A clean build, a happy type checker, and
    the heading on screen read "studio-editor".
    """
    body = client.get("/api/docs/studio-editor").json()
    assert "title" in body, "the response carries no title, so the reader will show an id"
    assert body["title"] == "Studio & Editor", body["title"]
    assert not re.fullmatch(r"[a-z0-9_-]+", body["title"]), (
        f"the title is still id shaped: {body['title']!r}"
    )

    # A file with no curated entry falls back to its own first heading, not to
    # its slug.
    other = client.get("/api/docs/data_architecture").json()
    assert other["title"] and not re.fullmatch(r"[a-z0-9_-]+", other["title"]), other["title"]


def test_a_document_says_where_it_lives():
    """
    A relative link inside a document resolves against the document's own path,
    so the path has to come back with the content or every cross reference in
    the corpus is unresolvable.
    """
    body = client.get("/api/docs/modules-03_inbound_crm").json()
    assert body["path"] == "modules/03_INBOUND_CRM.md", body["path"]


# ---------------------------------------------------------------------------
# A hit is a destination
# ---------------------------------------------------------------------------

def test_every_search_hit_names_a_document_that_opens():
    """
    The result list was not clickable because a hit named a filename and the
    product had no route for most filenames. Both halves are fixed, so every
    hit has to resolve.
    """
    seen = 0
    for term in ("egress", "carousel", "worktree", "schema", "hook"):
        results = client.get(f"/api/docs/search?q={term}&limit=10").json()["results"]
        for hit in results:
            seen += 1
            assert hit.get("document_id"), f"a hit on {term!r} names no document: {hit['filename']}"
            opened = client.get(f"/api/docs/{hit['document_id']}")
            assert opened.status_code == 200, (
                f"a hit on {term!r} points at {hit['document_id']!r}, which answers "
                f"{opened.status_code}"
            )
            assert opened.json()["path"] == hit["filename"], (
                f"the hit's document id opens {opened.json()['path']} but the hit is in {hit['filename']}"
            )
    assert seen >= 10, f"only {seen} hits across five terms, the index may be empty"


def test_index_paths_use_one_separator_on_every_platform():
    """
    os.path.relpath returns backslashes on Windows. That string is shown to the
    reader and is now also matched against a document path to resolve a hit, so
    a platform dependent spelling means the hit resolves on one machine and not
    another.

    This asserts the property a caller can observe, not one implementation of
    it, and four places enforce it: the indexer when it stores a path, the
    search reader when it returns one, the library walk, and the endpoint that
    annotates a hit. Removing any one leaves this green, which is defence in
    depth rather than a weak check. Removing all four fails it immediately with
    a backslashed path, which is how that was established rather than assumed.
    """
    results = client.get("/api/docs/search?q=carousel&limit=10").json()["results"]
    assert results, "no hits to inspect"
    for hit in results:
        assert "\\" not in hit["filename"], f"a hit filename carries a backslash: {hit['filename']}"
    for entry in client.get("/api/docs").json()["library"]:
        assert "\\" not in entry["path"], entry["path"]


# ---------------------------------------------------------------------------
# Resolution is a lookup, not a join
# ---------------------------------------------------------------------------

def test_a_request_never_contributes_a_path_segment():
    """
    The id selects a row from a table this module built by walking the docs
    directory, so traversal is not something that has to be defended twice.
    """
    for probe in (
        "..%2F..%2Fetc%2Fpasswd",
        "___invalid_mod___",
        "....",
        "..",
        "modules-01_studio_and_editor-",
    ):
        response = client.get(f"/api/docs/{probe}")
        assert response.status_code in (400, 404), (
            f"{probe!r} answered {response.status_code}"
        )


def test_the_registry_resolves_nothing_it_did_not_walk():
    assert docs_engine.resolve_document_path("") is None
    assert docs_engine.resolve_document_path("../../etc/passwd") is None
    assert docs_engine.resolve_document_path("___invalid_mod___") is None
    found = docs_engine.resolve_document_path("modules-05_analytics")
    assert found and os.path.isfile(found), found


def test_every_document_id_is_unique():
    """Two paths collapsing onto one id makes one of them unreachable."""
    ids = [entry["id"] for entry in docs_engine.document_library()]
    assert len(ids) == len(set(ids)), "duplicate document ids"


# ---------------------------------------------------------------------------
# What the listing says about a document is read from the document
# ---------------------------------------------------------------------------

def test_an_excerpt_is_the_document_s_own_prose(catalogue):
    """
    Nothing here is generated. The excerpt is the document's own first line of
    prose, so it must not be a horizontal rule, a table row or a bare list
    marker. Five files opened with a rule and showed "---" in the sidebar.
    """
    for entry in catalogue["library"]:
        excerpt = entry["excerpt"]
        if not excerpt:
            continue
        assert not docs_engine.is_rule(excerpt), f"{entry['path']} shows a rule as its excerpt"
        assert not excerpt.startswith("|"), f"{entry['path']} shows a table row: {excerpt[:40]!r}"
        assert not re.match(r"^\[[ xX]\]", excerpt), f"{entry['path']} shows a checkbox marker"
        assert not re.match(r"^(?:[-*+]|\d{1,9}[.)])\s", excerpt), (
            f"{entry['path']} shows a raw list marker: {excerpt[:40]!r}"
        )


def test_the_rule_check_knows_a_rule_from_a_hyphen():
    """
    Written without a backreference on purpose. The first version used one, the
    heredoc that wrote the file turned it into a literal control byte, and the
    pattern silently matched nothing: grep printed the line as if it were fine
    and only cat -A showed it.
    """
    assert docs_engine.is_rule("---")
    assert docs_engine.is_rule("***")
    assert docs_engine.is_rule("___")
    assert docs_engine.is_rule("- - -")
    assert not docs_engine.is_rule("--")
    assert not docs_engine.is_rule("-")
    assert not docs_engine.is_rule("| :--- |")
    assert not docs_engine.is_rule("a paragraph")


def test_a_word_count_is_counted_not_guessed(catalogue):
    for entry in catalogue["library"]:
        source = os.path.join(DOCS_DIR, *entry["path"].split("/"))
        if not os.path.isfile(source):
            continue
        with open(source, encoding="utf-8", errors="replace") as handle:
            actual = len(handle.read().split())
        assert entry["words"] == actual, (
            f"{entry['path']} reports {entry['words']} words and holds {actual}"
        )


# ---------------------------------------------------------------------------
# The surface
# ---------------------------------------------------------------------------

def test_the_reader_renders_parsed_blocks():
    """
    The defect that started this: the reader printed the whole document as one
    <pre> element, so every table, fence, bullet and bold run arrived as literal
    markdown characters.
    """
    source = _rendered(os.path.join(UI_SRC, "components", "DocsSurface.tsx"))
    assert "DocumentView" in source, "the reader no longer draws parsed blocks"
    assert "parseMarkdown" in source, "the reader no longer parses the document"
    assert "<pre" not in source, (
        "the reader is printing preformatted text again, which is how 798 table "
        "rows reached the screen as pipes"
    )


def test_task_state_is_decided_per_item_not_per_list():
    """
    checked is recorded per item by the parser. The renderer used to switch to
    the task treatment only when every item was a task, so one plain bullet
    among them sent the whole list down the bullet path, where no box is drawn
    and every tick and every empty box silently disappeared.

    Nothing in the corpus mixes them today, which is exactly why this needs a
    guard rather than a look: the marker is parsed off either way, so the only
    symptom is content quietly missing from the screen.
    """
    source = _rendered(os.path.join(UI_SRC, "components", "DocumentView.tsx"))
    assert "items.some((item) => item.checked !== null)" in source, (
        "the task treatment is decided for the whole list again, so a mixed list "
        "loses every checkbox"
    )
    assert "items.every((item) => item.checked !== null)" not in source


def test_the_surface_reaches_the_library_and_search():
    client_source = _read(os.path.join(UI_SRC, "lib", "api.ts"))
    for route in ("/api/docs", "/api/docs/search"):
        assert route in client_source, f"{route} is unreachable from the interface"
    assert "document_id" in client_source, (
        "the client drops the id that makes a search hit a destination"
    )


def test_a_module_number_is_typed_as_the_label_it_is():
    """
    The backend sends "01" through "06" and "Master". The client declared a
    number, so the one entry that is not numeric was a lie the type checker
    could not see through.
    """
    client_source = _read(os.path.join(UI_SRC, "lib", "api.ts"))
    assert re.search(r"number:\s*string;", client_source), (
        "DocModule.number is typed as a number again, and one of them is \"Master\""
    )
    numbers = {module["number"] for module in client.get("/api/docs").json()["modules"]}
    assert any(not value.isdigit() for value in numbers), (
        f"no non numeric module label left, so this guard no longer proves anything: {numbers}"
    )


def test_an_unresolvable_link_is_not_offered_as_a_control():
    """
    The studio can open a target or it cannot. A control that does nothing when
    pressed is worse than showing the reader the path.
    """
    source = _rendered(os.path.join(UI_SRC, "components", "DocumentView.tsx"))
    assert 'target.kind === "document"' in source
    assert 'target.kind === "external"' in source
    # The missing branch is the fall through, and it must not be a button.
    tail = source[source.index('target.kind === "external"'):]
    assert "<span" in tail, "a link with no target is still rendered as a control"


def test_an_external_link_is_marked_as_leaving_the_machine():
    """
    This product's claim is that it does not reach the network on its own. A
    reader following a link is not the studio phoning home, and they are owed
    the distinction before they click.
    """
    source = _rendered(os.path.join(UI_SRC, "components", "DocumentView.tsx"))
    assert 'rel="noreferrer noopener"' in source
    assert "leaves this machine" in source, (
        "an outbound link is drawn the same as an internal one"
    )


# ---------------------------------------------------------------------------
# The index is not a snapshot of whatever the corpus was the first time anyone
# searched
# ---------------------------------------------------------------------------

def test_the_index_is_built_when_the_studio_starts():
    """
    init_docs_search_index was imported into app.py and never called there. The
    only other call site is inside search_docs_fts, guarded by "the table does
    not exist", so the index was built exactly once per database and never
    again.
    """
    app_source = _read(os.path.join(REPO_ROOT, "studio", "backend", "app.py"))
    lifespan = app_source[app_source.index("async def lifespan"):]
    lifespan = lifespan[: lifespan.index("yield")]
    assert "init_docs_search_index()" in lifespan, (
        "the documentation index is not built at startup, so it is whatever the "
        "first search left behind"
    )


def test_editing_a_document_changes_what_search_finds(monkeypatch):
    """
    paths.py promises that a source checkout takes effect immediately, "without
    a repackaging step". That was true for opening a document, which reads from
    disk, and false for finding one: search answered from an index built once
    and never refreshed.

    It matters more now that a hit is a destination. A stale index can return a
    section of a file that has since been renamed, and the reader follows it to
    a 404 rather than to a slightly old snippet.
    """
    with tempfile.TemporaryDirectory() as corpus:
        page = os.path.join(corpus, "NOTE.md")
        _write(page, "# Note\n\n## Section\n\nThe word here is zarquon.\n")

        monkeypatch.setattr(docs_engine, "DOCS_DIR", corpus)
        monkeypatch.setattr(docs_engine, "_index_signature", None)

        built = docs_engine.init_docs_search_index(docs_dir=corpus)
        assert built > 0, "the temporary corpus did not index"
        assert docs_engine.search_docs_fts("zarquon", limit=5), "the first word was not findable"

        _write(page, "# Note\n\n## Section\n\nThe word here is blorptastic now.\n")

        try:
            assert docs_engine.search_docs_fts("blorptastic", limit=5), (
                "an edited document is still invisible to search, so the index is a "
                "snapshot rather than a view"
            )
            assert not docs_engine.search_docs_fts("zarquon", limit=5), (
                "the replaced text is still findable, so the rebuild appended instead "
                "of replacing"
            )
        finally:
            # This rebuilt the one shared docs_index from a temporary
            # directory, which is exactly the contamination that made two
            # guards in this file fail only when the whole suite ran.
            # Handed back.
            monkeypatch.undo()
            docs_engine._index_signature = None
            docs_engine.init_docs_search_index()


def test_a_corpus_fingerprint_notices_a_same_size_edit():
    """
    The fingerprint reads contents, not timestamps.

    An earlier version used path, size and modification time. Windows stamps a
    write with the system clock tick, so two same length writes inside one tick
    share an mtime and the fingerprint did not move. This test passed on its
    own and failed under the load of the full suite, which is the correct
    verdict on a timestamp: it records when the filesystem noticed, not what
    the file says. Repeated here rather than run once, because the defect it
    replaced was intermittent and a single pass is what hid it.
    """
    with tempfile.TemporaryDirectory() as corpus:
        page = os.path.join(corpus, "A.md")
        for attempt in range(25):
            _write(page, "one")
            before = docs_engine.corpus_signature(corpus)
            _write(page, "two")
            after = docs_engine.corpus_signature(corpus)
            assert before != after, (
                f"on pass {attempt} a same size edit written immediately after the "
                "last one left the fingerprint unchanged"
            )


def test_a_failed_rebuild_does_not_record_a_signature_it_did_not_write(monkeypatch):
    """
    The signature is recorded after the commit and nowhere else, so a rebuild
    that rolled back leaves the previous one in place and the next search tries
    again rather than trusting an index that was never written.
    """
    with tempfile.TemporaryDirectory() as corpus:
        _write(os.path.join(corpus, "A.md"), "# A\n\nbody\n")

        monkeypatch.setattr(docs_engine, "_index_signature", "sentinel")

        def exploding_open(*args, **kwargs):
            raise OSError("simulated read failure")

        monkeypatch.setattr(docs_engine, "open", exploding_open, raising=False)
        result = docs_engine.init_docs_search_index(docs_dir=corpus)

    assert result == 0
    assert docs_engine._index_signature == "sentinel", (
        "a rebuild that indexed nothing recorded itself as current, so the next "
        "search would trust an index it never wrote"
    )
