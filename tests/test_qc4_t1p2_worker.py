"""
The worker coordinates the tabs: one browser, one request per read, one heartbeat.
=================================================================================

Cycle 4, track 1, phase 2 (the capture report's Appendix B, days 1 to 4, and
"never reload by hand"). Runs the real service worker under node with a fake
chrome API and a fake studio (tests/bridge_worker_harness.js).

  stamp        every relayed capture names its browser (an id minted once),
               the browser's name, the tab, window and document, and the
               LinkedIn account the browser is signed in to; the account
               also rides as X-Inox-Account, which the studio routes by
  coalescing   identical captures from other tabs within ten seconds are
               answered here, without a request; a new one always goes
  batching     one read of a post is one request carrying items[], and each
               person's answer comes back in the order they were read
  cap          at most four requests to the studio at once
  held         a capture for an account no profile holds is kept, and sent
               when the studio says a profile for that account exists
  heartbeat    one per browser per minute, from the worker, carrying the
               LinkedIn pages open by kind; pages report to the worker
  reload       on install and update the readers go into the LinkedIn tabs
               already open; an unpacked install whose files changed reloads
               itself; a tab the readers could not reach is reported

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import shutil
import subprocess

import pytest

TESTS = os.path.dirname(os.path.abspath(__file__))
WORKER = os.path.abspath(os.path.join(TESTS, "..", "studio", "extension", "background.js"))
HARNESS = os.path.join(TESTS, "bridge_worker_harness.js")
NODE = shutil.which("node")


def run(script, timeout=60):
    if not NODE:
        pytest.skip("node is not installed")
    program = (f"const {{ boot }} = require({json.dumps(HARNESS)});\n"
               f"const WORKER = {json.dumps(WORKER)};\n"
               "(async () => {\n" + script + "\n})().catch((e) => { console.error(e && e.stack || e); process.exit(1); });")
    result = subprocess.run([NODE, "-e", program], capture_output=True, text=True, timeout=timeout)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


PEOPLE = """
const person = (n, extra) => Object.assign({ full_name: "Person " + n, linkedin_urn: "https://www.linkedin.com/in/person-" + n + "-example",
  headline: "Engineer", interaction_type: "COMMENT", comment_text: "Words " + n, post_urn: "urn:li:activity:7385000000000000001",
  post_author: "test-creator", capture_context: "/feed/" }, extra || {});
const accept = (record) => ({ status: 200, body: { status: "success", outcome: "accepted", items_accepted: (record.body.items || [1]).length,
  items: (record.body.items || []).map((i) => ({ idempotency_key: i.idempotency_key, status: "success", outcome: "accepted" })) } });
"""


def test_every_relayed_capture_names_its_browser_tab_and_account():
    out = run(PEOPLE + """
      const w = boot(WORKER, { storage: { signedInVanity: "test-creator" } });
      w.recipes["/api/v1/crm/interactions/ingest"] = accept;
      await w.relay("/api/v1/crm/interactions/ingest", { items: [person(1)] }, { id: 7, windowId: 2 });
      await w.relay("/api/v1/crm/interactions/ingest", { items: [person(2)] }, { id: 8, windowId: 2 });
      await w.tick(50);
      const writes = w.sent.filter((s) => s.path === "/api/v1/crm/interactions/ingest");
      process.stdout.write(JSON.stringify({ first: writes[0].body.stamp, second: writes[1].body.stamp,
        header: writes[0].headers["X-Inox-Account"], stored: w.storage.browserInstanceId }));
    """)
    stamp = out["first"]
    assert stamp["tab_id"] == 7 and stamp["window_id"] == 2 and stamp["document_id"] == "doc-7"
    assert stamp["frame_id"] == 0 and stamp["tab_active"] is True
    assert stamp["signed_in_vanity"] == "test-creator" and stamp["browser"] == "Brave"
    assert stamp["browser_instance_id"] and stamp["browser_instance_id"] == out["second"]["browser_instance_id"]
    assert out["stored"] == stamp["browser_instance_id"], "the browser's id is not kept across restarts"
    assert out["header"] == "test-creator", "the account the studio routes by is not sent"


def test_two_tabs_reading_one_post_make_one_request():
    out = run(PEOPLE + """
      const w = boot(WORKER, { storage: { signedInVanity: "test-creator" } });
      w.recipes["/api/v1/crm/interactions/ingest"] = accept;
      const read = { items: [person(1), person(2), person(3)] };
      const [a, b] = await Promise.all([
        w.relay("/api/v1/crm/interactions/ingest", JSON.parse(JSON.stringify(read)), { id: 1 }),
        w.relay("/api/v1/crm/interactions/ingest", JSON.parse(JSON.stringify(read)), { id: 2 }),
      ]);
      const later = await w.relay("/api/v1/crm/interactions/ingest", { items: [person(2), person(4)] }, { id: 3 });
      await w.tick(50);
      const writes = w.sent.filter((s) => s.path === "/api/v1/crm/interactions/ingest");
      process.stdout.write(JSON.stringify({ requests: writes.length, firstItems: writes[0].body.items.length,
        a: a.data.items.map((i) => i.outcome), b: b.data.items.map((i) => i.reason),
        laterSent: writes[1] ? writes[1].body.items.map((i) => i.full_name) : null,
        later: later.data.items.map((i) => i.reason || i.outcome) }));
    """)
    assert out["requests"] == 2, f"{out['requests']} requests for one post read in two tabs, then one new person"
    assert out["firstItems"] == 3
    assert out["a"] == ["accepted"] * 3 and out["b"] == ["already_seen"] * 3
    assert out["laterSent"] == ["Person 4"], "a person already sent was sent again, or the new one was not"
    assert out["later"] == ["already_seen", "accepted"], "the answers are not in the order the people were read"


def test_the_same_capture_after_the_window_is_sent_again():
    out = run(PEOPLE + """
      const w = boot(WORKER, { storage: { signedInVanity: "test-creator" } });
      w.recipes["/api/v1/crm/interactions/ingest"] = accept;
      await w.relay("/api/v1/crm/interactions/ingest", { items: [person(1)] }, { id: 1 });
      const held = JSON.parse(JSON.stringify(w.session.coalescedCaptures || {}));
      for (const key of Object.keys(held)) held[key] -= 11000;
      w.session.coalescedCaptures = held;
      await w.relay("/api/v1/crm/interactions/ingest", { items: [person(1)] }, { id: 2 });
      await w.tick(50);
      process.stdout.write(JSON.stringify({ requests: w.sent.filter((s) => s.path === "/api/v1/crm/interactions/ingest").length,
        keysAreHashes: Object.keys(w.session.coalescedCaptures).every((k) => /^[0-9a-f]{64}$/.test(k)) }));
    """)
    assert out["requests"] == 2
    assert out["keysAreHashes"], "the session holds a capture's words rather than its hash"


def test_no_more_than_four_requests_reach_the_studio_at_once():
    out = run("""
      const w = boot(WORKER, { storage: { signedInVanity: "test-creator" }, studioDelayMs: 40 });
      const reads = [];
      for (let n = 0; n < 10; n += 1) {
        reads.push(w.relay("/api/v1/self/posts/analytics",
          { author: "test-creator", activity_urn: "urn:li:activity:73850000000000000" + (10 + n), metrics: { impressions: n } }, { id: n + 1 }));
      }
      await Promise.all(reads);
      process.stdout.write(JSON.stringify({ sent: w.sent.filter((s) => s.path === "/api/v1/self/posts/analytics").length,
        most: w.maxInFlight }));
    """)
    assert out["sent"] == 10
    assert out["most"] <= 4, f"{out['most']} requests were in flight at once"


def test_a_capture_for_an_account_no_profile_holds_is_kept_until_one_does():
    out = run(PEOPLE + """
      const w = boot(WORKER, { storage: { signedInVanity: "second-account" } });
      const held = { status: 202, body: { status: "held", outcome: "held", reason: "no_profile_for_account", account: "second-account" } };
      w.recipes["/api/v1/crm/interactions/ingest"] = [held];
      const answer = await w.relay("/api/v1/crm/interactions/ingest", { items: [person(1)] }, { id: 1 });
      await w.tick(50);
      const keptAfter = (w.storage.keptCaptures || []).map((i) => i.heldFor);
      w.fire("alarm", { name: "studio_drain_kept" });
      await w.tick(80);
      const beforeHome = w.sent.filter((s) => s.path === "/api/v1/crm/interactions/ingest").length;
      w.recipes["/api/v1/crm/interactions/ingest"] = accept;
      w.recipes["/api/v1/bridge/heartbeat"] = [{ status: 200, body: { status: "success", profile_vanities: ["second-account"] } }];
      w.fire("alarm", { name: "inox_bridge_heartbeat" });
      await w.tick(200);
      process.stdout.write(JSON.stringify({ answer: { kept: answer.kept, held: answer.held }, keptAfter, beforeHome,
        afterHome: w.sent.filter((s) => s.path === "/api/v1/crm/interactions/ingest").length,
        left: (w.storage.keptCaptures || []).length,
        heldOnBeat: (w.sent.filter((s) => s.path === "/api/v1/bridge/heartbeat")[0] || {}).body.held }));
    """)
    assert out["answer"] == {"kept": True, "held": True}
    assert out["keptAfter"] == ["second-account"]
    assert out["beforeHome"] == 1, "a held capture was sent again before any profile held its account"
    assert out["heldOnBeat"] == {"second-account": 1}, "the heartbeat does not say what is held"
    assert out["afterHome"] == 2 and out["left"] == 0, "the held capture was not sent when its account got a profile"


def test_the_worker_beats_once_for_the_browser_with_the_pages_it_has_open():
    out = run("""
      const w = boot(WORKER, { storage: { signedInVanity: "test-creator" },
        tabs: [{ id: 1, url: "https://www.linkedin.com/feed/" }, { id: 2, url: "https://www.linkedin.com/in/test-creator/" },
               { id: 3, url: "https://www.linkedin.com/feed/", discarded: true }] });
      await w.fromTab({ action: "PAGE_STATE", page_kind: "feed", visible: true, extension_version: "9.9.9" }, { id: 1 });
      await w.fromTab({ action: "PAGE_STATE", page_kind: "in", visible: false, extension_version: "9.9.9" }, { id: 2 });
      await w.fromTab({ action: "PAGE_STATE", page_kind: "feed", visible: false, extension_version: "9.9.9" }, { id: 3 });
      w.sent.length = 0;
      w.fire("alarm", { name: "inox_bridge_heartbeat" });
      await w.tick(150);
      const first = w.sent.filter((s) => s.path === "/api/v1/bridge/heartbeat");
      w.tabs.splice(1, 1);
      w.fire("removed", 2);
      await w.tick(50);
      w.sent.length = 0;
      w.fire("alarm", { name: "inox_bridge_heartbeat" });
      await w.tick(150);
      const second = w.sent.filter((s) => s.path === "/api/v1/bridge/heartbeat");
      process.stdout.write(JSON.stringify({ beats: first.length, body: first[0].body, after: second[0].body.open_pages,
        alarm: w.alarms.inox_bridge_heartbeat || null }));
    """)
    assert out["beats"] == 1
    body = out["body"]
    assert body["open_pages"] == {"feed": 1, "in": 1}, "a discarded tab or a missing one is counted as open"
    assert body["browser_instance_id"] and body["browser"] == "Brave" and body["signed_in_vanity"] == "test-creator"
    assert body["self_reload"] is True
    assert out["after"] == {"feed": 1}
    assert out["alarm"] and out["alarm"]["periodInMinutes"] == 1, "the worker's heartbeat is not on a minute's alarm"


def test_a_page_reports_to_the_worker_and_never_to_the_studio():
    """own_pages.js sends PAGE_STATE to the worker; no tab sends the studio a heartbeat of its own."""
    with open(os.path.join(TESTS, "..", "studio", "extension", "own_pages.js"), encoding="utf-8") as handle:
        own = handle.read()
    assert '"/api/v1/bridge/heartbeat"' not in own, "a tab still sends its own heartbeat"
    assert '"PAGE_STATE"' in own


def test_an_unpacked_install_whose_files_changed_reloads_itself():
    out = run("""
      const changed = boot(WORKER, { version: "2.10.0", diskVersion: "2.10.1" });
      changed.fire("alarm", { name: "inox_own_files" });
      await changed.tick(80);
      const same = boot(WORKER, { version: "2.10.0", diskVersion: "2.10.0" });
      same.fire("alarm", { name: "inox_own_files" });
      same.fire("startup");
      await same.tick(80);
      process.stdout.write(JSON.stringify({ changed: changed.reloads, same: same.reloads,
        files: same.storage.filesVersion, alarm: same.alarms.inox_own_files || null }));
    """)
    assert out["changed"] == 1, "an unpacked install whose files changed did not reload itself"
    assert out["same"] == 0, "an install whose files did not change reloaded"
    assert out["files"] == "2.10.0"
    assert out["alarm"] and out["alarm"]["periodInMinutes"] == 5


def test_on_update_the_readers_go_into_the_linkedin_tabs_already_open():
    out = run("""
      const w = boot(WORKER, { version: "2.10.0", tabs: [
        { id: 5, url: "https://www.linkedin.com/feed/" }, { id: 6, url: "https://www.linkedin.com/feed/", discarded: true }] });
      w.fire("installed", { reason: "update" });
      await w.tick(150);
      const current = boot(WORKER, { version: "2.10.0", probe: "2.10.0", tabs: [{ id: 5, url: "https://www.linkedin.com/feed/" }] });
      current.fire("installed", { reason: "update" });
      await current.tick(150);
      process.stdout.write(JSON.stringify({ executed: w.executed, current: current.executed.filter((e) => e.files) }));
    """)
    files = [(e["target"]["tabId"], e.get("world", "ISOLATED"), tuple(e["files"])) for e in out["executed"] if e.get("files")]
    assert (5, "MAIN", ("card_urns.js",)) in files
    assert (5, "ISOLATED", ("voyager_schema.js", "content.js", "own_pages.js", "own_insights.js")) in files
    assert not [f for f in files if f[0] == 6], "the readers were sent into a discarded tab"
    assert out["current"] == [], "a tab already carrying this version was given the readers again"


def test_a_tab_the_readers_could_not_reach_is_reported_as_needing_a_reload():
    out = run("""
      const w = boot(WORKER, { version: "2.10.0", executeFails: "Cannot access contents of the page",
        tabs: [{ id: 5, url: "https://www.linkedin.com/feed/" }] });
      w.fire("installed", { reason: "update" });
      await w.tick(150);
      w.sent.length = 0;
      w.fire("alarm", { name: "inox_bridge_heartbeat" });
      await w.tick(150);
      process.stdout.write(JSON.stringify({ beat: w.sent.filter((s) => s.path === "/api/v1/bridge/heartbeat")[0].body }));
    """)
    assert out["beat"]["tabs_needing_reload"] == 1


def test_ten_tabs_reporting_one_readers_run_in_a_minute_send_one_report():
    out = run("""
      const w = boot(WORKER, { storage: { signedInVanity: "test-creator" } });
      const reports = [];
      for (let tab = 1; tab <= 10; tab += 1) {
        reports.push(w.relay("/api/v1/bridge/capture", { extractor: "engagers", page_kind: "feed", items_seen: 30 + tab,
          items_kept: 30, drift: null, duration_ms: tab }, { id: tab }));
      }
      await Promise.all(reports);
      const drifted = await w.relay("/api/v1/bridge/capture", { extractor: "engagers", page_kind: "feed", items_seen: 3,
        items_kept: 0, drift: ["commenter_name"] }, { id: 11 });
      await w.tick(50);
      process.stdout.write(JSON.stringify({ sent: w.sent.filter((s) => s.path === "/api/v1/bridge/capture").length }));
    """)
    assert out["sent"] == 2, f"{out['sent']} run reports for one reader in one minute, and a drifted one"


def test_the_heartbeat_says_what_the_extension_found_in_its_own_folder():
    """
    A portable upgrade deletes the folder the extension was loaded from: the
    extension runs on from memory, cannot update itself, and the browser will
    not load it at its next start. Its own check is the only witness, so the
    heartbeat carries it: readable or not, and when it looked.
    """
    out = run("""
      const gone = boot(WORKER, { version: "2.10.0", filesGone: true });
      gone.fire("alarm", { name: "inox_own_files" });
      await gone.tick(80);
      gone.fire("alarm", { name: "inox_bridge_heartbeat" });
      await gone.tick(150);
      const here = boot(WORKER, { version: "2.10.0", diskVersion: "2.10.0" });
      here.fire("alarm", { name: "inox_own_files" });
      await here.tick(80);
      here.fire("alarm", { name: "inox_bridge_heartbeat" });
      await here.tick(150);
      const beat = (w) => w.sent.filter((r) => r.path === "/api/v1/bridge/heartbeat").pop().body;
      process.stdout.write(JSON.stringify({ gone: beat(gone), here: beat(here), reloads: gone.reloads }));
    """)
    assert out["gone"]["files_readable"] is False and out["gone"]["files_version"] is None
    assert out["reloads"] == 0, "an extension whose folder is gone reloaded into nothing"
    assert out["here"]["files_readable"] is True and out["here"]["files_version"] == "2.10.0"
    assert out["here"]["files_checked_at"].endswith("Z")


def test_a_studio_of_another_version_has_the_worker_look_at_its_files_now():
    """
    After an in-place update the studio restarts first; the extension looks
    at its folder when the studio's answer names another version, rather
    than up to five minutes later, and reloads itself if the folder moved on.
    """
    out = run("""
      const w = boot(WORKER, { version: "2.10.0", diskVersion: "2.10.1" });
      w.recipes["/api/v1/bridge/heartbeat"] = [{ status: 200, body: { status: "success",
        handshake: { reload_required: false, studio_version: "2.10.1", contract_version: 1 } } }];
      w.fire("alarm", { name: "inox_bridge_heartbeat" });
      await w.tick(200);
      const same = boot(WORKER, { version: "2.10.1", diskVersion: "2.10.1" });
      same.recipes["/api/v1/bridge/heartbeat"] = [{ status: 200, body: { status: "success",
        handshake: { reload_required: false, studio_version: "2.10.1", contract_version: 1 } } }];
      same.fire("alarm", { name: "inox_bridge_heartbeat" });
      await same.tick(200);
      process.stdout.write(JSON.stringify({ reloads: w.reloads, same: same.reloads, checked: !!same.storage.filesCheck }));
    """)
    assert out["reloads"] >= 1, "the worker waited for its own alarm while the studio had moved on"
    assert out["same"] == 0 and out["checked"] is False, "a studio of the same version made the worker look"
