"""
A network reader that cannot read LinkedIn's response says so.
==============================================================

The sections report's capture row 5, cycle 4, track 1. The network-reading
write recorded every run with no drift, so Setup could never say a network
reader had stopped reading: a creator analytics response that no longer
carried the follower count, or a feed response whose shape had changed, read
as READ NOTHING, or left no run at all, beside a DOM reader that names what
it cannot read.

A network run now reports drift the way the DOM readers do: a field the
reader cannot do without, missing from every entry of a response that plainly
matched its endpoint, or a response with no list of entries at all. A missing
optional figure is not drift for the reader (most of a feed is other members'
posts, which carry no view count); it still goes to the schema drift log.
The studio keeps the run's drift on its row, so the reader reads DRIFTING.

Every name and figure here is invented.

Strict Invariants:
- Zero em-dashes.
"""

import os
import shutil
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

INGEST = "/api/v1/bridge/voyager-ingest"
DRIFT_LOG = "/api/v1/bridge/schema-drift"


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_t1_voyager_drift_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    from database import init_db
    init_db()
    yield
    shutil.rmtree(home, ignore_errors=True)


def _health(extractor):
    import onboarding
    return {entry["extractor"]: entry for entry in onboarding.capture_health()}[extractor]


# ---------------------------------------------------------------------------
# The studio keeps the run's drift
# ---------------------------------------------------------------------------

def test_a_network_run_that_names_drift_reads_drifting(studio):
    import onboarding
    onboarding.record_voyager_ingest({"schema_name": "feed_updates", "data": [{"text": "a post"}], "drift": ["urn"],
                                      "extension_version": "test"})
    entry = _health("voyager_feed_updates")
    assert entry["state"] == "drifting", "a network reader that cannot read its response is not drifting"
    assert entry["drift"] == ["urn"]


def test_a_creator_analytics_response_without_followers_reads_drifting(studio):
    import onboarding
    onboarding.record_voyager_ingest({"schema_name": "creator_analytics", "data": [], "drift": ["followers"],
                                      "vanity": None, "extension_version": "test"})
    entry = _health("voyager_creator_analytics")
    assert entry["state"] == "drifting" and entry["drift"] == ["followers"]
    assert entry["last_good_at"] is None


def test_a_clean_network_run_still_reads_working(studio):
    import onboarding
    onboarding.record_voyager_ingest({"schema_name": "feed_updates", "data": [{"urn": "urn:li:activity:7123456789012345678"}],
                                      "drift": [], "extension_version": "test"})
    entry = _health("voyager_feed_updates")
    assert entry["state"] == "working" and entry["drift"] == []


# ---------------------------------------------------------------------------
# The page names it
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pages():
    pytest.importorskip("playwright.sync_api")
    from qc_f3_pages import Pages
    p = Pages()
    yield p
    p.close()


def _respond(pages, url, body, status=200):
    from qc_f3_pages import page_html
    page = pages.open("/feed/", page_html("<main></main>"), storage={"networkReading": True})
    page.clock.run_for(100)
    page.evaluate("(m) => window.postMessage(m, window.location.origin)", {
        "type": "INOX_VOYAGER_CAPTURE", "source": "inox-voyager-interceptor",
        "payload": {"url": url, "method": "GET", "status": status, "timestamp": "2026-10-26T10:00:00.000Z",
                    "captureId": "capture_1", "body": body}})
    page.wait_for_timeout(100)
    return page


FEED = "https://www.linkedin.com/voyager/api/feed/updatesV2"
ANALYTICS = "https://www.linkedin.com/voyager/api/identity/dash/creatorAnalytics"


def test_a_feed_response_whose_entries_carry_no_post_id_is_a_drifted_run(pages):
    body = {"elements": [{"commentary": {"text": {"text": "first"}}}, {"commentary": {"text": {"text": "second"}}}]}
    page = _respond(pages, FEED, body)
    sent = pages.sent(page, INGEST)
    assert sent, "a response the reader could not read left no run at all"
    assert sent[-1]["drift"] == ["urn"]


def test_a_response_with_no_list_of_entries_has_changed_shape(pages):
    page = _respond(pages, ANALYTICS, {"data": {"followerCount": 4200}})
    sent = pages.sent(page, INGEST)
    assert sent and sent[-1]["drift"] == ["elements"], sent


def test_a_missing_optional_figure_is_not_drift_for_the_reader(pages):
    body = {"elements": [{"entityUrn": "urn:li:activity:7123456789012345678"}]}
    page = _respond(pages, FEED, body)
    sent = pages.sent(page, INGEST)
    assert sent and sent[-1]["drift"] == []
    assert pages.sent(page, DRIFT_LOG), "the missing optional figures no longer reach the drift log"


def test_an_error_response_is_not_judged_for_shape(pages):
    page = _respond(pages, ANALYTICS, {"status": 401}, status=401)
    assert all(not body.get("drift") for body in pages.sent(page, INGEST))


def test_the_drift_the_page_names_is_the_drift_the_studio_keeps(pages, studio):
    import onboarding
    body = {"elements": [{"impressionAggregate": 120}]}
    page = _respond(pages, ANALYTICS, body)
    sent = pages.sent(page, INGEST)
    assert sent and sent[-1]["drift"] == ["followers"]
    try:
        onboarding.record_voyager_ingest(dict(sent[-1]))
    except onboarding.RefusedCapture:
        pass  # no confirmed creator here; the run is still recorded
    entry = _health("voyager_creator_analytics")
    assert entry["drift"] == ["followers"]
