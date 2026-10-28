"""
Network reading is retired (2.10.2).
====================================

The owner's decision of 28 October 2026. A sanitised Resource Timing list
from the owner's own feed tab showed that LinkedIn's 2026 web app makes no
/voyager/api/ calls at all: its data now arrives through React Server
Component actions (/flagship-web/rsc-action/actions/pagination,
server-request, server-stream-request, /flagship-web/in/<vanity>) in an
internal streaming format. The interceptor that wrapped the page's fetch,
the schema registry it matched responses against and the webRequest
observer had nothing left to read and could not be re-keyed, so they are
gone, with the popup's switch, the webRequest permission, the coverage
meter and the studio's two routes.

What stays: the tables network reading wrote, forward only, which nothing
writes to any more. An extension not yet reloaded may still call the two
routes, send its heartbeat's network reading, or send the observer's
telemetry; the studio answers each plainly and keeps none of it, so the
extension does not retry in a loop. An update takes away what an earlier
version left in the browser: the registered interceptor, which persists
across sessions, and the stored switch.

The guard: no extension script patches window.fetch or XMLHttpRequest, no
MAIN-world script but the card stamper runs in LinkedIn's page and it
touches neither, the worker registers no content script, and the manifest
does not ask for webRequest.

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXT = os.path.join(REPO_ROOT, "studio", "extension")
TESTS = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.join(TESTS, "bridge_worker_harness.js")
WORKER = os.path.join(EXT, "background.js")
NODE = shutil.which("node")
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

RETIRED = "Network reading was retired in 2.10.2: LinkedIn's site no longer sends the data it read."


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as handle:
        return handle.read()


def _code(text):
    """A script without its comments, so a sentence about fetch is not a patch of it."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"(^|\s)//[^\n]*", r"\1", text)


def _scripts():
    return {name: _code(_read(EXT, name)) for name in sorted(os.listdir(EXT)) if name.endswith(".js")}


def _manifest():
    return json.loads(_read(EXT, "manifest.json"))


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------

# Each way a script can put itself between LinkedIn's page and its network.
PATCHES = {
    "assigns fetch": r"\b(?:window|globalThis|self|top|parent)\s*\.\s*fetch\s*=(?!=)",
    "assigns fetch by name": r"\b(?:window|globalThis|self)\s*\[\s*['\"]fetch['\"]\s*\]\s*=(?!=)",
    "defines fetch": r"defineProperty\s*\(\s*(?:window|globalThis|self)\s*,\s*['\"]fetch['\"]",
    "wraps fetch in a proxy": r"new\s+Proxy\s*\(\s*(?:(?:window|globalThis|self)\s*\.\s*)?\w*[Ff]etch\w*\b",
    "patches XMLHttpRequest": r"XMLHttpRequest\s*\.\s*prototype\s*\.\s*\w+\s*=(?!=)",
    "defines on XMLHttpRequest": r"defineProperty\s*\(\s*(?:(?:window|globalThis|self)\s*\.\s*)?XMLHttpRequest",
    "replaces XMLHttpRequest": r"(?:\b(?:window|globalThis|self)\s*\.\s*|(?<![\w.]))XMLHttpRequest\s*=(?!=)",
    "wraps XMLHttpRequest in a proxy": r"new\s+Proxy\s*\(\s*(?:(?:window|globalThis|self)\s*\.\s*)?XMLHttpRequest",
    "patches a response": r"\bResponse\s*\.\s*prototype\s*\.\s*\w+\s*=(?!=)",
}


def test_no_extension_script_patches_fetch_or_xmlhttprequest():
    found = [f"{name}: {what}" for name, code in _scripts().items()
             for what, pattern in PATCHES.items() if re.search(pattern, code)]
    assert not found, f"an extension script reaches into LinkedIn's network: {found}"


def test_the_only_script_in_linkedins_own_world_is_the_card_stamper_and_it_touches_no_request():
    main_world = [js for entry in _manifest().get("content_scripts", []) if entry.get("world") == "MAIN"
                  for js in entry.get("js", [])]
    assert set(main_world) <= {"card_urns.js"}, f"another script runs in LinkedIn's own world: {main_world}"
    stamper = _scripts()["card_urns.js"]
    assert not re.search(r"\bfetch\b|XMLHttpRequest|\bResponse\b", stamper), "the card stamper touches requests"


def test_the_worker_registers_no_content_script_and_injects_only_the_stamper_into_the_page():
    worker = _scripts()["background.js"]
    assert not re.search(r"\b(?:registerContentScripts|updateContentScripts)\s*\(", worker), (
        "the worker registers a content script, which is how the interceptor ran")
    for match in re.finditer(r"world\s*:\s*['\"]MAIN['\"]", worker):
        call = worker[max(0, match.start() - 240):match.end() + 40]
        files = re.findall(r"files\s*:\s*\[([^\]]*)\]", call)
        assert files and all(set(re.findall(r"['\"]([^'\"]+)['\"]", f)) == {"card_urns.js"} for f in files), (
            f"the worker puts something other than the card stamper into LinkedIn's world: {call!r}")
        assert not re.search(r"\bfunc\s*:", call), "the worker runs a function in LinkedIn's world"


def test_the_manifest_does_not_ask_for_webrequest():
    manifest = _manifest()
    asked = list(manifest.get("permissions", [])) + list(manifest.get("optional_permissions", []))
    assert not [p for p in asked if p.lower().startswith("webrequest")], f"the manifest asks for {asked}"


# ---------------------------------------------------------------------------
# What network reading was, gone from the extension
# ---------------------------------------------------------------------------

def test_the_interceptor_and_the_schema_registry_are_gone():
    for name in ("voyager_interceptor.js", "voyager_schema.js"):
        assert not os.path.exists(os.path.join(EXT, name)), f"{name} still ships"
    listed = [js for entry in _manifest().get("content_scripts", []) for js in entry.get("js", [])]
    assert not [js for js in listed if js.startswith("voyager_")], listed
    readers = re.search(r"const READER_FILES\s*=\s*\[([^\]]*)\]", _read(WORKER))
    assert readers and "voyager" not in readers.group(1), "the worker still injects the schema registry"
    packaged = _read(REPO_ROOT, "tools", "package_extension.py")
    assert "voyager_" not in packaged, "the package still lists a network reading file"


def test_no_page_script_listens_for_the_interceptor_or_counts_linkedins_calls():
    for name in ("content.js", "own_pages.js", "own_insights.js", "card_urns.js"):
        code = _scripts()[name]
        for gone in ("INOX_VOYAGER", "__inoxNetworkReading", "__inoxVoyagerCalls", "__inoxOnNetworkReading",
                     "networkReading", "/voyager/api/", "__InoxVoyagerSchema"):
            assert gone not in code, f"{name} still carries {gone}"


def test_the_popup_has_no_switch_and_the_side_panel_no_network_reading_lines():
    popup = _read(EXT, "popup.html") + _read(EXT, "popup.js")
    assert "network-reading" not in popup and "networkReading" not in popup
    assert "Read LinkedIn's network responses" not in popup
    panel = _code(_read(EXT, "sidepanel.js")) + _read(EXT, "sidepanel.html")
    for gone in ("Voyager Active", "DOM Fallback", "Network reading", "voyager_24h_captures", "voyager_active",
                 "Schema Registry", "network_reading", "voyager-ingest"):
        assert gone not in panel, f"the side panel still says {gone!r}"


def _run(script, timeout=60):
    if not NODE:
        pytest.skip("node is not installed")
    program = (f"const {{ boot }} = require({json.dumps(HARNESS)});\n"
               f"const WORKER = {json.dumps(WORKER)};\n"
               "(async () => {\n" + script + "\n})().catch((e) => { console.error(e && e.stack || e); process.exit(1); });")
    result = subprocess.run([NODE, "-e", program], capture_output=True, text=True, timeout=timeout)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_an_update_takes_away_what_an_earlier_version_left_in_the_browser():
    """
    A registered content script persists across browser sessions, so an
    extension updated from 2.10.1 with the switch on would go on wrapping
    LinkedIn's fetch with a file that no longer exists. The update removes
    the registration and the stored switch; so does a browser start.
    """
    out = _run("""
      const left = { networkReading: true, lastVoyagerCaptureAt: "2026-10-27T10:00:00.000Z", signedInVanity: "me" };
      const updated = boot(WORKER, { storage: Object.assign({}, left), registered: ["inox-network-reading"] });
      updated.fire("installed", { reason: "update" });
      await updated.tick(150);
      const started = boot(WORKER, { storage: Object.assign({}, left), registered: ["inox-network-reading"] });
      started.fire("startup");
      await started.tick(150);
      const fresh = boot(WORKER, { storage: {} });
      fresh.fire("installed", { reason: "install" });
      await fresh.tick(150);
      process.stdout.write(JSON.stringify({
        updated: { unregistered: updated.unregistered, registered: updated.registered, storage: updated.storage },
        started: { unregistered: started.unregistered, registered: started.registered, storage: started.storage },
        fresh: { unregistered: fresh.unregistered, registered: fresh.registered } }));
    """)
    for case in ("updated", "started"):
        seen = out[case]
        assert "inox-network-reading" in seen["unregistered"], f"{case}: the earlier interceptor is still registered"
        assert seen["registered"] == [], seen["registered"]
        assert "networkReading" not in seen["storage"], f"{case}: the switch is still stored"
        assert "lastVoyagerCaptureAt" not in seen["storage"], f"{case}: the last network capture is still stored"
        assert seen["storage"].get("signedInVanity") == "me", "the update took more than network reading's values"
    assert out["fresh"]["registered"] == [], "a fresh install registered a script"


def test_the_worker_relays_neither_retired_path():
    out = _run("""
      const w = boot(WORKER, { storage: { networkReading: true } });
      const a = await w.relay("/api/v1/bridge/voyager-ingest", { schema_name: "feed_updates", data: [] });
      const b = await w.relay("/api/v1/bridge/schema-drift", { schema_name: "feed_updates", schema_version: "1" });
      await w.tick(50);
      process.stdout.write(JSON.stringify({ a, b, sent: w.sent.map((r) => r.path) }));
    """)
    assert out["a"]["status"] == "error" and out["b"]["status"] == "error", out
    assert not [p for p in out["sent"] if "voyager" in p or "schema-drift" in p], out["sent"]


# ---------------------------------------------------------------------------
# The studio
# ---------------------------------------------------------------------------

@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_retire_nr_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    from database import init_db
    init_db()
    from fastapi.testclient import TestClient
    from app import app
    try:
        yield TestClient(app)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def _count(sql, *args):
    from database import get_db
    conn = get_db()
    try:
        return conn.execute(sql, args).fetchone()[0]
    finally:
        conn.close()


def _confirm(vanity="retired-creator"):
    from database import get_db
    conn = get_db()
    try:
        with conn:
            conn.execute("DELETE FROM creator_identity")
            conn.execute("INSERT INTO creator_identity (id, vanity, display_name, confirmed_at) "
                         "VALUES (1, ?, 'Retired Creator', '2026-10-01T00:00:00+00:00')", (vanity,))
            conn.execute("INSERT OR IGNORE INTO own_posts (activity_urn, text, first_seen_at, last_seen_at) "
                         "VALUES ('urn:li:activity:7385000000000000001', 'Mine.', '2026-10-01', '2026-10-01')")
    finally:
        conn.close()
    return vanity


def test_the_two_routes_answer_an_older_extension_retired_and_write_nothing(studio):
    me = _confirm()
    readings = "SELECT COUNT(*) FROM post_metric_observations"
    runs = "SELECT COUNT(*) FROM captures WHERE extractor LIKE 'voyager_%'"
    drift = "SELECT COUNT(*) FROM schema_drift_events"
    days = "SELECT COUNT(*) FROM analytics_daily WHERE followers IS NOT NULL AND source = 'observed'"
    before = [_count(q) for q in (readings, runs, drift, days)]
    ingest = studio.post("/api/v1/bridge/voyager-ingest", json={
        "schema_name": "feed_updates", "schema_version": "2026.10.1", "vanity": me, "extension_version": "2.10.1",
        "data": [{"urn": "urn:li:activity:7385000000000000001", "impressions": 900, "likes": 4, "comments": 1}]})
    followers = studio.post("/api/v1/bridge/voyager-ingest", json={
        "schema_name": "creator_analytics", "vanity": me, "data": [{"followers": 1234}]})
    drifted = studio.post("/api/v1/bridge/schema-drift", json={
        "schema_name": "feed_updates", "schema_version": "2026.10.1", "drift_fields": ["impressions"],
        "source_url": "https://www.linkedin.com/voyager/api/feed/updatesV2"})
    for answer in (ingest, followers, drifted):
        assert answer.status_code == 200, answer.text
        body = answer.json()
        assert body["status"] == "retired" and body["message"] == RETIRED, body
    assert [_count(q) for q in (readings, runs, drift, days)] == before, "a retired route still writes"


def test_the_heartbeat_takes_an_older_extensions_network_reading_and_keeps_none_of_it(studio):
    answer = studio.post("/api/v1/bridge/heartbeat", json={
        "extension_version": "2.10.1", "contract_version": 1, "page_kind": "feed",
        "network_reading": {"switch": True, "registered": True, "injected": True, "voyager_calls_seen": 4,
                            "matched": 0, "captured": 0},
        "voyager_calls": {"/voyager/api/feed/updatesV2": 4}})
    assert answer.status_code == 200, answer.text
    assert _count("SELECT COUNT(*) FROM bridge_heartbeats") == 1
    assert _count("SELECT COUNT(*) FROM bridge_heartbeats WHERE network_reading IS NOT NULL "
                  "OR voyager_calls IS NOT NULL") == 0, "the heartbeat's network reading was kept"


def test_the_observers_telemetry_from_an_older_extension_is_not_written(studio, monkeypatch):
    import routers.analytics as analytics
    taken = []
    if analytics.telemetry_buffer is not None:
        monkeypatch.setattr(analytics.telemetry_buffer, "ingest", lambda **kw: taken.append(kw))
    answer = studio.post("/api/analytics/ingest", json={
        "event_type": "feed_updates_v2", "source": "chrome_mv3_observer", "timestamp": "2026-10-28T09:00:00Z",
        "metadata": {"url": "https://www.linkedin.com/voyager/api/feed/updatesV2", "statusCode": 200}})
    assert answer.status_code == 200, answer.text
    assert answer.json()["status"] == "retired"
    assert taken == [], "the webRequest observer's event was written to the telemetry store"


def test_no_route_holds_a_retired_capture_for_an_account():
    import bridge_routing
    for path in ("/api/v1/bridge/voyager-ingest", "/api/v1/bridge/schema-drift"):
        assert path not in bridge_routing.DATA_PATHS and path not in bridge_routing.BOOKKEEPING_PATHS, (
            f"{path} would be held for an account and kept by the worker, for a route that keeps nothing")


def test_health_lists_no_network_reader_and_says_once_that_it_was_retired(studio):
    import health
    import onboarding
    assert not [e for e in onboarding.EXTRACTORS if e.startswith("voyager_")]
    assert not hasattr(onboarding, "OPT_IN_EXTRACTORS")
    payload = studio.get("/api/v1/extension/health").json()
    for gone in ("voyager_active", "voyager_24h_captures", "network_reading", "recent_drift", "schema_version"):
        assert gone not in payload, f"the health payload still carries {gone}"
    assert "network_reading" not in payload["bridge"]
    listed = health.readers()
    assert "network_reading" not in listed and not [r for r in listed["readers"] if "opt_in" in r]
    # Never used here: nothing to say.
    assert listed["network_reading_retired"] is None
    assert onboarding.onboarding_state()["network_reading_retired"] is None
    # Used here once: one sentence, in Health and in Setup.
    from database import get_db
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO captures (observed_at, extractor, page_kind, items_seen, items_kept) "
                     "VALUES ('2026-10-20T10:00:00+00:00', 'voyager_feed_updates', 'voyager_api', 3, 1)")
    conn.close()
    assert health.readers()["network_reading_retired"] == RETIRED
    assert onboarding.onboarding_state()["network_reading_retired"] == RETIRED
    assert not [r for r in health.readers()["readers"] if r["extractor"].startswith("voyager_")]
