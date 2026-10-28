"""
One bridge per browser: its heartbeat, its capture rows and its import claim.
============================================================================

Cycle 4, track 1, phase 2 (the capture report's Appendix B, days 5 to 7 and
10, the studio's half). Every LinkedIn tab sent its own heartbeat and its own
capture rows, so ten tabs in one browser wrote ten rows a minute and the
studio could not tell one browser from two. The worker now stamps every
capture with a per-browser instance id, and the studio keeps one heartbeat
row per browser per minute and one capture row per browser, reader and
minute, by upsert. Setup names each bridge by its browser and its signed-in
account.

The history import is claimed by one tab, by browser instance and tab: two
visible tabs on one activity page both used to scroll it. A claim is held
while its tab reports, given back when the tab leaves, and taken over by
another tab when it has gone quiet.

Every name here is invented.

Strict Invariants:
- Zero em-dashes.
"""

import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

BRAVE = {"browser_instance_id": "b1a2c3d4-0000-4000-8000-000000000001", "browser": "Brave",
         "signed_in_vanity": "test-creator", "tab_id": 11, "window_id": 3, "document_id": "doc-a"}
EDGE = {"browser_instance_id": "e5f6a7b8-0000-4000-8000-000000000002", "browser": "Microsoft Edge",
        "signed_in_vanity": "second-account", "tab_id": 21, "window_id": 4, "document_id": "doc-b"}


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_t1p2_rows_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    from database import init_db
    init_db()
    yield
    shutil.rmtree(home, ignore_errors=True)


def _rows(sql, *params):
    from database import get_db
    conn = get_db()
    try:
        return [tuple(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def _columns(table):
    return {row[1] for row in _rows(f"PRAGMA table_info({table})")}


# ---------------------------------------------------------------------------
# The migration
# ---------------------------------------------------------------------------

def test_the_migration_is_named_for_what_it_records(studio):
    import migrations
    entries = [m for m in migrations.MIGRATIONS if m[2] is migrations._migrate_bridge_coordination]
    assert len(entries) == 1, "the phase's migration is not registered"
    words = entries[0][1].lower()
    assert "per browser" in words and "claimed" in words, words


def test_the_migration_adds_the_browser_and_claim_columns(studio):
    for column in ("browser_instance_id", "minute", "browser", "signed_in_vanity", "contract_version",
                   "open_pages", "held", "tabs_needing_reload", "self_reload", "files_version"):
        assert column in _columns("bridge_heartbeats"), column
    for column in ("browser_instance_id", "minute"):
        assert column in _columns("captures"), column
    for column in ("claimed_by", "claimed_at"):
        assert column in _columns("self_import_requests"), column


# ---------------------------------------------------------------------------
# One heartbeat row per browser per minute
# ---------------------------------------------------------------------------

def _beat(stamp, **fields):
    import onboarding
    return onboarding.record_heartbeat(
        extension_version="2.10.0", page_kind="service_worker",
        browser_instance_id=stamp["browser_instance_id"], browser=stamp["browser"],
        signed_in_vanity=stamp["signed_in_vanity"], contract_version=1, **fields)


def test_a_browser_beating_twice_in_a_minute_is_one_row(studio):
    _beat(BRAVE, open_pages={"feed": 2})
    _beat(BRAVE, open_pages={"feed": 3})
    rows = _rows("SELECT open_pages FROM bridge_heartbeats WHERE browser_instance_id = ?",
                 BRAVE["browser_instance_id"])
    assert len(rows) == 1, f"{len(rows)} rows for one browser in one minute"
    assert '"feed": 3' in rows[0][0], "the newer beat did not replace the older one"


def test_two_browsers_are_two_rows_and_two_bridges(studio):
    import onboarding
    _beat(BRAVE, open_pages={"feed": 1})
    _beat(EDGE, open_pages={}, held={"second-account": 4})
    assert len(_rows("SELECT 1 FROM bridge_heartbeats")) == 2
    bridges = {b["browser"]: b for b in onboarding.bridge_status()["bridges"]}
    assert set(bridges) == {"Brave", "Microsoft Edge"}
    assert bridges["Brave"]["signed_in_vanity"] == "test-creator" and bridges["Brave"]["connected"] is True
    assert bridges["Brave"]["open_pages"] == {"feed": 1}
    assert bridges["Microsoft Edge"]["held"] == {"second-account": 4}


def test_an_extension_from_before_the_stamp_still_beats_as_it_did(studio):
    import onboarding
    onboarding.record_heartbeat("2.9.0", "feed")
    onboarding.record_heartbeat("2.9.0", "feed")
    assert len(_rows("SELECT 1 FROM bridge_heartbeats WHERE browser_instance_id IS NULL")) == 2
    status = onboarding.bridge_status()
    assert status["connected"] is True and status["extension_version"] == "2.9.0"
    assert [b["browser"] for b in status["bridges"]] == [None]


# ---------------------------------------------------------------------------
# One capture row per browser, reader and minute
# ---------------------------------------------------------------------------

def _capture(stamp, **fields):
    import onboarding
    payload = {"extractor": "engagers", "page_kind": "feed", "items_seen": 3, "items_kept": 3, "stamp": stamp}
    payload.update(fields)
    return onboarding.record_capture(payload)


def test_ten_tabs_reporting_one_reader_in_a_minute_are_one_row(studio):
    for tab in range(10):
        _capture(dict(BRAVE, tab_id=100 + tab), items_seen=3 + tab)
    rows = _rows("SELECT items_seen FROM captures WHERE extractor = 'engagers'")
    assert len(rows) == 1, f"{len(rows)} capture rows for one browser, reader and minute"
    assert rows[0][0] == 12, "the newest report did not replace the row"
    assert _rows("SELECT runs FROM capture_days WHERE extractor = 'engagers'") == [(1,)]


def test_two_browsers_reporting_one_reader_are_two_rows(studio):
    _capture(BRAVE)
    _capture(EDGE)
    assert len(_rows("SELECT 1 FROM captures WHERE extractor = 'engagers'")) == 2


def test_a_report_with_no_stamp_is_a_row_as_before(studio):
    import onboarding
    onboarding.record_capture({"extractor": "engagers", "items_seen": 1, "items_kept": 1})
    onboarding.record_capture({"extractor": "engagers", "items_seen": 1, "items_kept": 1})
    assert len(_rows("SELECT 1 FROM captures WHERE extractor = 'engagers'")) == 2


# ---------------------------------------------------------------------------
# The history import, claimed by one tab
# ---------------------------------------------------------------------------

def _confirmed_request(kind="posts"):
    import onboarding
    from database import get_db
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO creator_identity (id, vanity, confirmed_at) VALUES (1, 'test-creator', ?) "
                     "ON CONFLICT(id) DO UPDATE SET vanity = excluded.vanity, confirmed_at = excluded.confirmed_at",
                     (datetime.now(timezone.utc).isoformat(),))
    conn.close()
    return onboarding.request_import(kind)["id"]


def test_one_tab_holds_the_import_and_a_second_is_told_it_is_claimed(studio):
    import onboarding
    request = _confirmed_request()
    first = onboarding.pending_import("posts", claimant="b1:11")
    assert first and first["id"] == request
    assert onboarding.pending_import("posts", claimant="b1:12") is None, "a second tab was handed the same import"
    assert onboarding.pending_import("posts", claimant="b1:11")["id"] == request, "the holder lost its own claim"
    answer = onboarding.update_import(request, "started", claimant="b1:12")
    assert answer["status"] == "claimed_elsewhere"


def test_a_released_claim_is_free_for_the_next_tab(studio):
    import onboarding
    request = _confirmed_request()
    onboarding.pending_import("posts", claimant="b1:11")
    onboarding.update_import(request, "released", claimant="b1:11")
    assert onboarding.pending_import("posts", claimant="b2:21")["id"] == request


def test_a_claim_that_has_gone_quiet_is_taken_over(studio):
    import onboarding
    from database import get_db
    request = _confirmed_request()
    onboarding.pending_import("posts", claimant="b1:11")
    stale = (datetime.now(timezone.utc) - onboarding.IMPORT_CLAIM_TTL - timedelta(seconds=5)).isoformat()
    conn = get_db()
    with conn:
        conn.execute("UPDATE self_import_requests SET claimed_at = ? WHERE id = ?", (stale, request))
    conn.close()
    assert onboarding.pending_import("posts", claimant="b2:21")["id"] == request
    assert onboarding.update_import(request, "progress", items_seen=9, claimant="b1:11")["status"] == "claimed_elsewhere"


def test_progress_from_the_holder_keeps_its_claim_fresh(studio):
    import onboarding
    request = _confirmed_request()
    onboarding.pending_import("posts", claimant="b1:11")
    before = _rows("SELECT claimed_at FROM self_import_requests WHERE id = ?", request)[0][0]
    answer = onboarding.update_import(request, "progress", items_seen=40, claimant="b1:11")
    assert answer["status"] == "success"
    after = _rows("SELECT claimed_at, items_seen FROM self_import_requests WHERE id = ?", request)[0]
    assert after[0] >= before and after[1] == 40


def test_an_extension_that_names_no_tab_is_handed_the_import_as_before(studio):
    import onboarding
    request = _confirmed_request()
    assert onboarding.pending_import("posts")["id"] == request
    assert onboarding.pending_import("posts")["id"] == request
