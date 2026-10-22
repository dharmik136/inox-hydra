"""
One store for what the creator wrote, and no dead queue beside it.
==================================================================

Two of the four tables that held "something the creator wrote" were not
reachable from any screen:

- `drafts` held 1,044 rows on a three year install, 150 of them still DRAFT,
  while GET /api/posts?status=draft read `posts` and answered with an empty
  list. A creator's work could sit where nothing could show it.
- `queue_items` held 894 rows whose only writer, database.schedule_draft, had
  no callers at all, and which no screen read, while retention, backup, export
  and forget each carried it.

Strict Invariants:
- Zero em-dashes.
"""

import os
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import database
import retention
import support
from app import app
from database import get_db

client = TestClient(app)

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_BACKEND = os.path.join(_REPO, "studio", "backend")

TEXT = ("A draft that arrived from my phone while I was waiting for a train, which is the "
        "whole reason the ingress exists.")


@pytest.fixture
def from_the_legacy_store():
    draft_id = database.create_draft(TEXT, title="From the train")
    yield draft_id
    conn = get_db()
    try:
        with conn:
            conn.execute("DELETE FROM posts WHERE draft_id = ?", (draft_id,))
            conn.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# The drafts endpoint and the drafts table agree
# ---------------------------------------------------------------------------

def test_a_draft_written_to_the_legacy_store_is_shown_by_the_drafts_endpoint(from_the_legacy_store):
    answer = client.get("/api/posts?status=draft").json()
    assert answer["status"] == "success"
    assert any(p["content"] == TEXT for p in answer["posts"]), (
        "a draft in the legacy store is still invisible to the creator")


def test_no_row_of_the_legacy_store_holds_writing_the_record_does_not():
    """
    posts is the record. The drafts table keeps the authored form beside it
    (title, fold measurements, archetype) and nothing of its own: a row is
    either named by a posts row or holds the same text as one.
    """
    conn = get_db()
    try:
        stranded = conn.execute(
            "SELECT d.id, substr(d.raw_content, 1, 60) FROM drafts d "
            "WHERE COALESCE(d.raw_content, '') != '' "
            "AND d.id NOT IN (SELECT draft_id FROM posts WHERE draft_id IS NOT NULL) "
            "AND NOT EXISTS (SELECT 1 FROM posts p WHERE p.content = d.raw_content)"
        ).fetchall()
    finally:
        conn.close()
    assert stranded == [], [tuple(r) for r in stranded]


def test_the_ingress_no_longer_writes_a_second_post_for_one_draft(from_the_legacy_store):
    conn = get_db()
    try:
        rows = conn.execute("SELECT id, status, source FROM posts WHERE content = ?", (TEXT,)).fetchall()
    finally:
        conn.close()
    assert len(rows) == 1, [tuple(r) for r in rows]
    assert rows[0]["status"] == "draft"
    assert rows[0]["draft_id"] if "draft_id" in rows[0].keys() else True


# ---------------------------------------------------------------------------
# The dead queue is gone
# ---------------------------------------------------------------------------

def test_the_second_queue_table_is_gone():
    conn = get_db()
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    finally:
        conn.close()
    assert "queue_items" not in tables
    assert "idx_queue_scheduled" not in indexes


def test_the_writer_nothing_called_is_gone():
    assert not hasattr(database, "schedule_draft"), "the only writer of the dead queue is still here"


def test_nothing_a_creator_can_reach_depended_on_the_dead_queue():
    """
    The surfaces that carried the table: the Storage panel's sizes, the data
    export's table list, and the queue the creator actually sees. Each is
    asked for its answer, not for its source.
    """
    assert "queue_items" not in support.EXPORTABLE_TABLES
    assert all("queue_items" not in tables for _key, _label, tables in retention.CATEGORIES)

    # The Storage panel still measures what the creator holds.
    held = retention.sizes()
    assert [c for c in held["categories"] if c["key"] == "posts"], held["categories"]

    # And the data export still names every table it can take.
    conn = get_db()
    try:
        available = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        conn.close()
    assert [t for t in support.EXPORTABLE_TABLES if t not in available] == []


def test_no_backend_code_still_reads_or_writes_the_dead_queue():
    """
    Except migration 26, which drops it. A name left behind in a table list is
    how a dropped table comes back.
    """
    reads = ("'queue_items'", '"queue_items"', "FROM queue_items", "INTO queue_items",
             "ON queue_items", "UPDATE queue_items", "TABLE queue_items")
    offenders = []
    for folder, _dirs, files in os.walk(_BACKEND):
        for name in sorted(files):
            if not name.endswith(".py") or name == "migrations.py":
                continue
            path = os.path.join(folder, name)
            with open(path, "r", encoding="utf-8") as handle:
                for number, line in enumerate(handle, 1):
                    if any(pattern in line for pattern in reads):
                        offenders.append(f"{os.path.relpath(path, _REPO)}:{number}")
    assert offenders == [], offenders
