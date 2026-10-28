"""
Setup and Health say "reload required" only when it truly is.
============================================================

Cycle 4, track 1, phase 2 ("never reload by hand", part c). The handshake
judged the extension on what the studio remembered in memory, so after every
studio restart, until the extension next spoke, Health said the extension
was older than the studio and must be reloaded: a remembered nothing read as
"stale". An extension that reloads itself when its files change (2.10.0 on)
needs no hand at all, and one whose files are newer than it is about to.

The studio now judges on what the extension said: on the line, what it just
sent; otherwise the newest heartbeat inside the bridge's freshness window,
which carries its contract and whether it reloads itself. With neither, it
says nothing. A reload is required when the extension speaks an older
contract and is not about to reload itself, or runs an older version than
the studio and cannot reload itself. Tabs the worker could not give the new
readers are named on their own: they need a reload of the tab, not of the
extension.

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


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_t1p2_reload_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    from database import init_db
    init_db()
    import ingest_contract
    ingest_contract.forget()
    yield
    ingest_contract.forget()
    shutil.rmtree(home, ignore_errors=True)


def _beat(**fields):
    import onboarding
    values = dict(extension_version="2.10.0", page_kind="service_worker",
                  browser_instance_id="b1a2c3d4-0000-4000-8000-000000000001", browser="Brave",
                  contract_version=1, self_reload=True, files_version="2.10.0")
    values.update(fields)
    onboarding.record_heartbeat(**values)


def _health_contract():
    import ingest_contract
    return ingest_contract.handshake(studio_version="2.10.0")


def test_a_studio_that_has_heard_nothing_since_it_started_says_nothing(studio):
    contract = _health_contract()
    assert contract["reload_required"] is None, "a remembered nothing was reported as a stale extension"
    assert contract["message"] is None


def test_an_extension_that_reloads_itself_is_never_told_to_reload_for_its_version(studio):
    _beat(extension_version="2.10.0", files_version="2.10.1")
    contract = _health_contract()
    assert contract["reload_required"] is False and contract["updating"] is True


def test_an_old_extension_that_cannot_reload_itself_is_told_once_by_its_versions(studio):
    _beat(extension_version="2.7.0", self_reload=None, files_version=None)
    contract = _health_contract()
    assert contract["reload_required"] is True
    assert "2.7.0" in contract["message"] and "2.10.0" in contract["message"]


def test_an_older_contract_on_old_files_is_a_reload_even_for_one_that_reloads_itself(studio):
    _beat(contract_version=0, files_version="2.10.0")
    assert _health_contract()["reload_required"] is True


def test_a_heartbeat_from_before_the_freshness_window_is_not_evidence(studio):
    from database import get_db
    _beat(extension_version="2.7.0", self_reload=None, files_version=None)
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    conn = get_db()
    with conn:
        conn.execute("UPDATE bridge_heartbeats SET seen_at = ?", (old,))
    conn.close()
    assert _health_contract()["reload_required"] is None


def test_tabs_the_new_readers_could_not_reach_are_named_on_their_own(studio):
    _beat(tabs_needing_reload=2)
    contract = _health_contract()
    assert contract["reload_required"] is False
    assert contract["tabs_needing_reload"] == 2 and "2 LinkedIn tabs" in contract["tabs_message"]


def test_the_heartbeat_is_judged_on_what_the_extension_just_said(studio):
    import ingest_contract
    answer = ingest_contract.handshake("2.10.0", 1, self_reload=True, files_version="2.10.0", studio_version="2.10.0")
    assert answer["reload_required"] is False
    answer = ingest_contract.handshake("2.9.0", 1, studio_version="2.10.0")
    assert answer["reload_required"] is True
