"""
Batch R5: help and search for customers.

D-5. A creator asking Ctrl+K "restore my data" got only the engineering bug
register, and the Docs home listed 17 maintainer and 24 retired documents
beside the help. Those documents are for whoever maintains the studio, so in a
consumer run they are left out of search and of the Docs home. They still open
by id, so a help article that links to one keeps working, and with the
developer switch on (INOX_DEV_MODE) a maintainer sees them again.
"""

import os
import re
import sys

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

from app import app  # noqa: E402
import docs_engine  # noqa: E402

client = TestClient(app)

INTERNAL = {"maintainers", "retired"}


@pytest.fixture
def consumer(monkeypatch):
    monkeypatch.delenv("INOX_DEV_MODE", raising=False)


@pytest.fixture
def maintainer(monkeypatch):
    monkeypatch.setenv("INOX_DEV_MODE", "1")


def _help_ids(query):
    body = client.get("/api/v1/search", params={"q": query}).json()
    return [hit["id"] for hit in body["groups"]["help"]]


def test_universal_search_does_not_answer_with_the_bug_register(consumer):
    ids = _help_ids("restore my data")
    assert not any(doc_id.startswith("quality-") for doc_id in ids), ids


def test_docs_search_returns_only_customer_documents(consumer):
    for query in ("kafka", "restore", "architecture", "migration"):
        results = client.get("/api/docs/search", params={"q": query, "limit": 20}).json()["results"]
        kinds = {hit["kind"] for hit in results}
        assert kinds <= {"help"}, f"{query!r} returned {kinds}: {[hit['document_id'] for hit in results]}"


def test_help_hits_are_not_crowded_out_by_hidden_ones(consumer):
    """
    Dozens of maintainer sections mention "scheduler" and two help articles
    do. Dropping the hidden ones from a page afterwards left none.

    The probe was "architecture" until cycle 3 batch T7 retired
    browse-the-swipe-file.md, which was the only help article carrying that
    word (through the engineering pack's archetype names). A probe no help
    article answers measures nothing.
    """
    results = client.get("/api/docs/search", params={"q": "scheduler", "limit": 5}).json()["results"]
    assert results, "the help articles that mention the scheduler were crowded out"
    assert {hit["kind"] for hit in results} == {"help"}


def test_the_docs_listing_holds_only_help_for_a_creator(consumer):
    """R1-N2: a packaged copy's /api/docs still listed the retired manuals."""
    listing = client.get("/api/docs").json()
    assert not {section["id"] for section in listing["sections"]} & INTERNAL, listing["sections"]
    assert {docs_engine.section_kind(entry["section"]) for entry in listing["library"]} == {"help"}
    assert listing["modules"] == [] and listing["count"] == 0, listing["modules"]
    assert "help/command-line-tool-reference.md" in {entry["path"] for entry in listing["library"]}

    # A maintainer asks for the rest explicitly.
    everything = client.get("/api/docs", params={"internal": 1}).json()
    assert INTERNAL <= {section["id"] for section in everything["sections"]}
    assert everything["modules"]
    hits = client.get("/api/docs/search", params={"q": "architecture", "limit": 20, "internal": 1}).json()["results"]
    assert any(hit["kind"] != "help" for hit in hits)


def test_a_hidden_document_still_opens_by_id(consumer):
    body = client.get("/api/docs/data_architecture")
    assert body.status_code == 200, body.text
    assert body.json()["section"] == "For maintainers"


def test_a_maintainer_sees_them_again(maintainer):
    sections = client.get("/api/docs").json()["sections"]
    assert not any(section["hidden"] for section in sections)
    results = client.get("/api/docs/search", params={"q": "architecture", "limit": 20}).json()["results"]
    assert any(hit["kind"] != "help" for hit in results), "dev mode should search maintainer documents"


def test_the_helper_hides_only_internal_sections():
    for section in docs_engine.HELP_SECTIONS:
        expected = section["id"] in INTERNAL
        assert docs_engine.section_hidden(section["id"], shown=False) is expected, section["id"]
        assert docs_engine.section_hidden(section["id"], shown=True) is False


def test_the_docs_surface_leaves_hidden_sections_out():
    with open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "DocsSurface.tsx"), encoding="utf-8") as handle:
        source = handle.read()
    assert "hidden" in source and re.search(r"sections\.filter\(\(section\) => !section\.hidden\)", source), (
        "the Docs surface does not leave hidden sections out of its home and its name filter"
    )

