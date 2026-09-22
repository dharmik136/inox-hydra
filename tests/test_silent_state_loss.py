"""
State is not discarded without somebody being told.
===================================================

Four places lost something and reported success.

  docs_engine deleted the index, then swallowed every per-file failure in a
  handler that sits INSIDE the guard meant to catch them, then committed. A
  docs_index left from an older schema made every INSERT fail, so the index
  emptied, the function returned 0, and search returned nothing for good.

  updates.py wrote the ETag before recording the version it belongs to. If the
  version write failed, every later check sent the new ETag, got a 304 and
  reported the user as up to date permanently.

  internal_sheet created the G-Stack backlog task before opening its own
  connection, so a failed insert left a PENDING task pointing at no issue, and
  every retry added another.

  ingress advanced last_update_id before processing the message. Telegram
  never resends an acknowledged update, so a draft that failed to store was
  gone.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import docs_engine
import ingress
from database import get_db

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _index_rows():
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM docs_index").fetchone()[0]
    except Exception:
        return 0
    finally:
        conn.close()


def test_a_stale_index_schema_is_rebuilt_not_emptied():
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS does nothing when a table of that name
    exists, whatever its columns are. The DELETE still succeeded and every
    INSERT then failed against the wrong column count.
    """
    docs_engine.init_docs_search_index()
    healthy = _index_rows()
    assert healthy > 0, "the index did not build at all, so this proves nothing"

    conn = get_db()
    try:
        conn.execute("DROP TABLE IF EXISTS docs_index")
        conn.execute("CREATE VIRTUAL TABLE docs_index USING fts5(filename, content)")
        conn.commit()
    finally:
        conn.close()

    rebuilt = docs_engine.init_docs_search_index()

    assert rebuilt > 0, "the rebuild indexed nothing against a stale schema"
    assert _index_rows() > 0, "the index was emptied rather than rebuilt"


def test_an_index_that_cannot_be_built_leaves_the_old_one_alone(monkeypatch):
    """
    DELETE has already run by the time the inserts fail. Committing zero rows
    replaces a working index with nothing and returns 0 without raising.
    """
    docs_engine.init_docs_search_index()
    before = _index_rows()
    assert before > 0

    real_walk = docs_engine.os.walk

    def exploding_open(*args, **kwargs):
        raise OSError("simulated read failure")

    monkeypatch.setattr(docs_engine, "open", exploding_open, raising=False)

    result = docs_engine.init_docs_search_index()

    assert result == 0
    assert _index_rows() == before, (
        "a failed rebuild replaced a working index with an empty one, so every "
        "search would return nothing from now on"
    )


def test_the_update_version_is_recorded_before_the_etag():
    """
    The ETag is a promise that we already know what is at that URL. Writing it
    first means a failed version write leaves the checker permanently
    satisfied. intelligence_sync documents this ordering; updates.py had it
    backwards.
    """
    source = open(os.path.join(REPO_ROOT, "studio", "backend", "updates.py"), encoding="utf-8").read()

    version_at = source.index("_set_setting(LAST_SEEN_KEY, latest)")
    etag_at = source.index('etag = response.headers.get("ETag")')

    assert version_at < etag_at, (
        "the ETag is written before the version it implies, so a failure "
        "between them reports the user as up to date for good"
    )


def test_a_failed_issue_insert_leaves_no_orphan_backlog_task(monkeypatch):
    """
    The backlog task is the derived record. It must not outlive the issue it
    derives from.
    """
    monkeypatch.setenv("INOX_DEV_MODE", "1")

    import internal_sheet
    from gstack_governance import gstack_engine

    conn = get_db()
    try:
        before = conn.execute("SELECT COUNT(*) FROM gstack_backlog").fetchone()[0]
    finally:
        conn.close()

    # A title that fails validation, so the insert never happens.
    with pytest.raises(ValueError):
        internal_sheet.internal_sheet_manager.create_issue(
            target_selector=".probe", title="", description="d",
            promote_to_backlog=True,
        )

    conn = get_db()
    try:
        after = conn.execute("SELECT COUNT(*) FROM gstack_backlog").fetchone()[0]
    finally:
        conn.close()

    assert after == before, (
        f"{after - before} backlog tasks were created for an issue that was "
        f"never stored"
    )


def test_a_telegram_message_is_acknowledged_only_after_it_is_handled():
    """
    last_update_id becomes the next poll's offset. Advancing it before
    processing tells Telegram we have the message while we do not, and
    Telegram never resends an acknowledged update.
    """
    source = open(os.path.join(REPO_ROOT, "studio", "backend", "ingress.py"), encoding="utf-8").read()

    process_at = source.index("p = self.process_incoming_update(update)")
    advance_at = source.index("self.last_update_id = update_id", process_at)

    assert advance_at > process_at, (
        "the offset advances before the message is processed, so a failure "
        "loses the draft permanently"
    )


def test_an_unprocessable_message_does_not_block_the_queue_forever():
    """
    The other half. Moving the advance below the call, on its own, means a
    message that can never be processed is retried forever and blocks every
    message behind it.
    """
    assert ingress.MAX_UPDATE_ATTEMPTS >= 1

    source = open(os.path.join(REPO_ROOT, "studio", "backend", "ingress.py"), encoding="utf-8").read()
    assert "_failed_updates" in source, "failed updates are not tracked at all"
    assert "Giving up on Telegram update" in source, (
        "there is no path that steps over a message which can never be handled"
    )
