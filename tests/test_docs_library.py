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
import time

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


def _advance_mtime(path, nanoseconds=20_000_000):
    """
    Moves a file's modification time forward without sleeping.

    A real save advances it because a clock tick passes between one edit and
    the next. A test that writes twice in the same millisecond does not, and
    waiting for a tick would put a real pause into the suite for no reason.
    """
    stat = os.stat(path)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + nanoseconds))


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

    An earlier version used path, size and modification time alone. Windows
    stamps a write with the system clock tick, so two same length writes inside
    one tick share an mtime and the fingerprint did not move. That test passed
    on its own and failed under the load of the full suite, which is the
    correct verdict on a timestamp: it records when the filesystem noticed, not
    what the file says.

    The content hash is gated on a stat, because running it on every search
    took the FTS5 query from under 15ms to 104ms against a 50ms budget. So the
    guarantee is precisely this: an edit whose size or modification time
    differs is seen, and the content decides whether anything is rebuilt. The
    mtime is advanced explicitly here rather than by sleeping, which is what a
    real save does by taking longer than a clock tick.
    """
    with tempfile.TemporaryDirectory() as corpus:
        page = os.path.join(corpus, "A.md")
        for attempt in range(25):
            _write(page, "one")
            before = docs_engine.corpus_signature(corpus)
            _write(page, "two")
            _advance_mtime(page)
            after = docs_engine.corpus_signature(corpus)
            assert before != after, (
                f"on pass {attempt} a same size edit was not noticed, so a search "
                "would keep answering from the previous contents"
            )


def test_a_touch_that_changes_nothing_does_not_move_the_fingerprint():
    """
    The other half, and the reason the gate is not the answer.

    A stat alone would call a touched file a changed one and rebuild the whole
    index for nothing. The content is what decides, so the stat is only ever a
    reason to go and look.
    """
    with tempfile.TemporaryDirectory() as corpus:
        page = os.path.join(corpus, "A.md")
        _write(page, "# A\n\nunchanged body\n")
        before = docs_engine.corpus_signature(corpus)
        _advance_mtime(page)
        assert docs_engine.corpus_signature(corpus) == before, (
            "touching a file moved the fingerprint, so every touch rebuilds the index"
        )


def test_an_unchanged_corpus_is_cheap_to_check():
    """
    Hashing 450KB on every search took the FTS5 query to 104ms against a 50ms
    budget that already existed. Making search four times slower to notice an
    edit nobody made is a bad trade, and the guard that caught it is in
    tests/test_milestone3_days09_12.py.
    """
    docs_engine.corpus_signature()
    start = time.perf_counter()
    for _ in range(20):
        docs_engine.corpus_signature()
    per_call_ms = (time.perf_counter() - start) / 20 * 1000
    assert per_call_ms < 12, (
        f"checking an unchanged corpus costs {per_call_ms:.1f}ms per search, which is "
        "back in the range that broke the query budget"
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


# ---------------------------------------------------------------------------
# The help sections
# ---------------------------------------------------------------------------
# Documents were grouped by the folder they sit in, which put "Reference",
# "Prudent Handoff" and "Builder Feedback" at the top level of a help centre.
# Those are facts about the filesystem. Nobody asking what leaves this machine
# would guess to look under a directory named after a handoff process.

def test_every_document_is_filed_under_exactly_one_section(catalogue):
    """
    Completeness, and the reason the taxonomy is a written table rather than
    keyword matching on titles: a guess that is right most of the time files
    the rest somewhere wrong, and nothing says which.
    """
    filed = [doc_id for section in catalogue["sections"] for doc_id in section["document_ids"]]
    assert len(filed) == len(set(filed)), "a document appears under two sections"

    library_ids = {entry["id"] for entry in catalogue["library"]}
    assert set(filed) == library_ids, (
        "the sections and the library disagree about which documents exist. "
        f"filed but not in the library: {sorted(set(filed) - library_ids)[:5]}; "
        f"in the library but unfiled: {sorted(library_ids - set(filed))[:5]}"
    )


def test_nothing_is_left_in_the_unfiled_section(catalogue):
    """
    A new document lands in "Not yet filed" rather than quietly joining an
    existing section, and this is what turns that into a decision somebody
    makes rather than a default nobody notices.

    This, and not the completeness check above, is the guard that fails when a
    path is dropped from HELP_SECTIONS. Completeness stays green because the
    fallback catches the document and the sections still cover the library,
    which is the fallback doing its job. The difference matters when reading a
    failure: completeness means the taxonomy and the library disagree about
    what exists, this one means a file exists that nobody has filed.
    """
    unfiled = [s for s in catalogue["sections"] if s["id"] == docs_engine.UNFILED["id"]]
    if not unfiled:
        return
    names = [entry["path"] for entry in docs_engine.document_library()
             if docs_engine.section_for_path(entry["path"]) == docs_engine.UNFILED["id"]]
    raise AssertionError(
        "these documents are indexed and readable but nobody has said which part of "
        f"the help they belong to. Add them to HELP_SECTIONS in docs_engine.py: {names}"
    )


def test_the_unfiled_section_is_reachable_rather_than_a_silent_default():
    """
    The fallback exists and is its own named section. If it were an existing
    one, an unfiled document would read as a decision somebody made.
    """
    assert docs_engine.section_for_path("NOT_A_REAL_FILE.md") == docs_engine.UNFILED["id"]
    assert docs_engine.section_meta(docs_engine.UNFILED["id"])["title"] == "Not yet filed"
    known = {section["id"] for section in docs_engine.HELP_SECTIONS}
    assert docs_engine.UNFILED["id"] not in known, (
        "the fallback is one of the real sections, so an unfiled document is "
        "indistinguishable from a filed one"
    )


def test_every_section_path_exists_on_disk():
    """
    A path in the table that no longer exists is a topic with a hole in it, and
    it would otherwise show a smaller count without saying anything is wrong.
    """
    on_disk = set(_markdown_files())
    listed = [path for section in docs_engine.HELP_SECTIONS for path in section["paths"]]
    missing = [path for path in listed if path not in on_disk]
    assert not missing, f"HELP_SECTIONS names files that are not in docs/: {missing}"


def test_a_section_says_what_it_is_for(catalogue):
    """
    A card with a title and a count is a folder. The blurb is what makes it an
    answer to "is what I need in here".
    """
    for section in catalogue["sections"]:
        assert section["title"] and not section["title"].islower(), section["title"]
        assert len(section["blurb"]) > 40, f"{section['title']} has no real description"
        assert section["count"] > 0, f"{section['title']} is empty"
        assert section["words"] > 0, f"{section['title']} reports no length"


def test_the_sections_are_not_the_folders(catalogue):
    """
    The defect this replaced. If these names come back, the grouping has fallen
    back to the directory layout.
    """
    titles = {section["title"] for section in catalogue["sections"]}
    for folder_name in ("Reference", "Prudent Handoff", "Builder Feedback", "Module Manuals"):
        assert folder_name not in titles, (
            f"{folder_name!r} is a directory in docs/, not something a reader came to do"
        )


def test_a_hit_reports_its_help_section_without_losing_its_heading():
    """
    Both, and under different names.

    "section" is the heading FTS5 matched inside the document, and the anchor a
    result scrolls to is derived from it. Writing the help category into that
    same key silently broke every jump to a passage while leaving the result
    list looking exactly right.
    """
    results = client.get("/api/docs/search?q=egress&limit=6").json()["results"]
    assert results, "no hits to inspect"
    section_titles = {s["title"] for s in client.get("/api/docs").json()["sections"]}

    for hit in results:
        assert hit["help_section"] in section_titles, (
            f"a hit reports an unknown help section: {hit['help_section']!r}"
        )
        assert hit["section"] not in section_titles, (
            "the heading the hit matched has been overwritten with the help "
            f"category, so its anchor is gone: {hit['section']!r}"
        )
        assert hit["section"].strip(), "the matched heading is empty"
        assert hit["document_title"], "a hit does not name the document it is in"


def test_an_opened_document_reports_its_section():
    body = client.get("/api/docs/help-what-leaves-this-machine").json()
    assert body["section"] == "Your data and privacy", body["section"]
    # The engineering account of the same subject is maintainer reference now,
    # not user help, and says so.
    body = client.get("/api/docs/data_architecture").json()
    assert body["section"] == "For maintainers", body["section"]


# ---------------------------------------------------------------------------
# The way in
# ---------------------------------------------------------------------------

def test_the_surface_opens_on_the_help_rather_than_on_a_document():
    """
    It used to open straight onto module 01, so the first thing a reader saw
    was an answer to a question they had not asked.
    """
    source = _rendered(os.path.join(UI_SRC, "components", "DocsSurface.tsx"))
    assert 'useState<View>("home")' in source, "the surface no longer opens on the topics"
    assert "HelpHome" in source and "SectionView" in source, (
        "the help centre views are no longer drawn"
    )
    assert "setOpenId((current) => current ??" not in source, (
        "a document is being opened automatically again"
    )


def test_search_results_are_shown_at_reading_width():
    """
    Results lived in a 300px rail, where a snippet wrapped to five lines and a
    filename was the only clue about where the answer was.
    """
    surface = _rendered(os.path.join(UI_SRC, "components", "DocsSurface.tsx"))
    assert "ResultsView" in surface, "results are no longer drawn in the reading column"
    results = _rendered(os.path.join(UI_SRC, "components", "HelpCentre.tsx"))
    assert "help_section" in results, "a result does not say which part of the help it came from"
    assert "document_title" in results, "a result does not name its document"
    assert "readableSnippet" in results, (
        "the snippet is no longer parsed, so FTS5 markers and the markdown around "
        "them reach the reader as characters"
    )


def test_the_view_is_held_rather_than_derived_from_the_query():
    """
    Derived from whether a query was set, clicking a result put the document on
    screen and the still present query put the results straight back over it.
    """
    source = _rendered(os.path.join(UI_SRC, "components", "DocsSurface.tsx"))
    assert "const [view, setView] = useState<View>" in source, (
        "the reading column decides what to show from the query again"
    )


# ---------------------------------------------------------------------------
# The help articles
# ---------------------------------------------------------------------------
# Sixteen articles under docs/help, drafted from a brief by a researcher who
# walked the interface and the routes behind it, then checked claim by claim
# against the code by a reviewer told to assume every sentence was wrong. That
# pass made 127 corrections. These guards hold the shape that made them worth
# writing; the claims themselves are held by the code they describe.

HELP_DIR = os.path.join(DOCS_DIR, "help")


def _help_articles():
    if not os.path.isdir(HELP_DIR):
        pytest.skip("docs/help is not present in this checkout")
    return sorted(name for name in os.listdir(HELP_DIR) if name.endswith(".md"))


def test_every_help_article_is_filed_under_help():
    """An article written for the user must not end up among the reference."""
    help_paths = {
        path
        for section in docs_engine.HELP_SECTIONS
        if docs_engine.section_kind(section["id"]) == "help"
        for path in section["paths"]
    }
    for name in _help_articles():
        assert f"help/{name}" in help_paths, (
            f"docs/help/{name} is not filed under a help section"
        )


def test_help_articles_follow_the_house_shape():
    """
    Title first, then one plain sentence, because that sentence is what the
    library shows as the excerpt and what a search result leads with.
    """
    em_dash = chr(8212)
    for name in _help_articles():
        with open(os.path.join(HELP_DIR, name), encoding="utf-8") as handle:
            text = handle.read()
        lines = [line for line in text.splitlines() if line.strip()]
        assert lines[0].startswith("# "), f"{name} does not open with its title"
        assert not lines[1].startswith(("#", ">", "|", "-", "*", "1.")), (
            f"{name} has no summary sentence under its title"
        )
        assert em_dash not in text, f"{name} contains an em dash"
        assert not text.lstrip().startswith("---"), f"{name} has front matter the parser would print"


def test_links_between_help_articles_resolve():
    """A dead cross reference is rendered as text, which is honest and useless."""
    for name in _help_articles():
        with open(os.path.join(HELP_DIR, name), encoding="utf-8") as handle:
            text = handle.read()
        for target in re.findall(r"\]\(([^)#\s]+\.md)", text):
            resolved = os.path.normpath(os.path.join(HELP_DIR, target))
            assert os.path.isfile(resolved), f"{name} links to {target}, which does not exist"


def test_help_articles_hold_no_credential_values():
    """They describe where li_at and a key go. They never show one."""
    pattern = re.compile(r"AQED[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9]{16,}|ajax:[0-9]{8,}")
    for name in _help_articles():
        with open(os.path.join(HELP_DIR, name), encoding="utf-8") as handle:
            assert not pattern.search(handle.read()), f"{name} contains something shaped like a credential"


def test_a_retired_document_is_marked_and_an_article_is_not(catalogue):
    """
    The old module manuals are served, because they are the record, but the
    review found them contradicted by the code in places. The reader has to be
    told before it reads "356 vaulted blueprints".
    """
    assert client.get("/api/docs/enterprise-usage").json()["retired"] is True
    assert client.get("/api/docs/studio-editor").json()["retired"] is True
    assert client.get("/api/docs/help-what-leaves-this-machine").json()["retired"] is False

    kinds = {section["id"]: section["kind"] for section in catalogue["sections"]}
    assert kinds.get("retired") == "retired" and kinds.get("maintainers") == "reference", kinds


def test_contradicted_manuals_are_not_filed_as_help():
    """
    The critic's placement report found these contradicted by the code. Filing
    any of them under a help section would be the studio repeating a claim it
    knows to be false.
    """
    contradicted = {
        "ENTERPRISE_USAGE.md", "GETTING_STARTED.md", "EXTENSION_AND_SYNC.md", "AI_ENGINE.md",
        "modules/05_ANALYTICS.md", "modules/04_VIRAL_SWIPE_FILE.md",
    }
    for section in docs_engine.HELP_SECTIONS:
        if docs_engine.section_kind(section["id"]) != "help":
            continue
        clash = contradicted.intersection(section["paths"])
        assert not clash, f"{section['title']} files contradicted manuals as help: {sorted(clash)}"


def test_the_reader_warns_before_a_retired_document():
    source = _rendered(os.path.join(UI_SRC, "components", "DocsSurface.tsx"))
    assert "doc.retired &&" in source, "a retired manual opens with no notice"


def test_the_landing_view_keeps_help_apart_from_the_record():
    source = _rendered(os.path.join(UI_SRC, "components", "HelpCentre.tsx"))
    assert 'section.kind === "help"' in source, (
        "maintainer reference and retired manuals are drawn as help topics again"
    )


def test_search_leads_with_help_rather_than_the_record():
    """
    Searching "extension" once put the retired Chrome-only setup guide first,
    above the help article written because that guide is wrong. Within a kind
    the index's order stands; across kinds, help comes first.
    """
    order = {"help": 0, "reference": 1, "retired": 2}
    for term in ("extension", "egress", "queue", "backup", "analytics"):
        hits = client.get(f"/api/docs/search?q={term}&limit=20").json()["results"]
        assert hits, f"no hits for {term}"
        kinds = [hit["kind"] for hit in hits]
        assert kinds == sorted(kinds, key=order.get), (
            f"searching {term!r} interleaves kinds: {kinds}"
        )
        if "help" in kinds:
            assert kinds[0] == "help", f"searching {term!r} does not lead with help: {kinds[:5]}"


def test_the_requested_limit_still_holds():
    """The wider window is internal; a caller gets what it asked for and no more."""
    assert len(client.get("/api/docs/search?q=the&limit=5").json()["results"]) <= 5
    assert client.get("/api/docs/search?q=system&limit=500").json()["count"] <= 100


def test_name_matches_are_ordered_and_labelled_too():
    """
    Name matches are filtered on the client, so the server's ordering never
    reached them. Searching "extension" still led with the retired Chrome-only
    guide, through the list that sits above the passages.
    """
    source = _rendered(os.path.join(UI_SRC, "components", "DocsSurface.tsx"))
    assert "a.rank - b.rank" in source, "name matches are not grouped by kind"
    results = _rendered(os.path.join(UI_SRC, "components", "HelpCentre.tsx"))
    assert "sectionTitle(entry.section)" in results, "a name match does not say where it is filed"
