"""
The worker tells its own pages the instant a capture lands.
===========================================================

Cycle 4, track 1, items 8 and 9 (the worker side), and the worker half of
item 2. Every relayed write passes through the worker, which already wrote
the waiting count and the last refusal to the extension's storage. It now
writes one more key after each relay, lastCapture, and keeps a per-tab count
on the action badge, orange while captures are waiting; a drift the readers
report is noted once per page kind per browser session for the panel header
and the badge colour. The capture confirmation moves here from LinkedIn's
page (decision D3). The worker heartbeat carries the network-reading switch
and whether the reader is registered.

These run the real service worker under node with a fake chrome API, the way
tests/test_qc3_t3_capture_queue.py does.
"""

import json
import os
import shutil
import subprocess

import pytest

EXT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "extension"))
NODE = shutil.which("node")

HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(process.argv[process.argv.length - 1], "utf8");

const storage = {};
const session = {};
const listeners = { installed: [], startup: [], changed: [], message: [], request: [], alarm: [], removed: [] };
const event = (bucket) => ({ addListener: (fn) => listeners[bucket].push(fn) });
const badge = { text: [], background: [], textColor: [], title: [] };

const area = (store) => ({
  get: (keys, cb) => {
    const wanted = keys === null ? Object.keys(store) : (Array.isArray(keys) ? keys : [keys]);
    const out = {};
    for (const key of wanted) if (key in store) out[key] = store[key];
    cb(out);
  },
  set: (items, cb) => { Object.assign(store, items); if (cb) cb(); },
  remove: (keys, cb) => { for (const key of [].concat(keys)) delete store[key]; if (cb) cb(); },
});

const chrome = {
  runtime: {
    id: "self", lastError: undefined,
    onInstalled: event("installed"), onStartup: event("startup"), onMessage: event("message"),
    getManifest: () => ({ version: "9.9.9" }),
    getURL: (path) => "chrome-extension://self/" + path,
  },
  storage: { local: area(storage), session: area(session), onChanged: event("changed") },
  scripting: {
    getRegisteredContentScripts: async () => (storage.networkReading ? [{ id: "inox-network-reading" }] : []),
    registerContentScripts: async () => {}, unregisterContentScripts: async () => {},
  },
  alarms: { clear: () => {}, create: () => {}, onAlarm: event("alarm") },
  cookies: { get: (_q, cb) => cb({ value: "token" }), onChanged: event("changed") },
  sidePanel: { open: async () => {} },
  webRequest: { onCompleted: { addListener: (fn) => listeners.request.push(fn) } },
  action: {
    setBadgeText: (d, cb) => { badge.text.push(d); if (cb) cb(); },
    setBadgeBackgroundColor: (d, cb) => { badge.background.push(d); if (cb) cb(); },
    setBadgeTextColor: (d, cb) => { badge.textColor.push(d); if (cb) cb(); },
    setTitle: (d, cb) => { badge.title.push(d); if (cb) cb(); },
  },
  tabs: { onRemoved: event("removed"), query: async () => [] },
};

const answers = {};
const sent = [];
const reply = (recipe) => {
  if (recipe === "unreachable") throw new TypeError("Failed to fetch");
  const status = recipe.status || 200;
  return { ok: status >= 200 && status < 300, status,
           headers: { get: (name) => (name === "Retry-After" ? (recipe.retryAfter === undefined ? null : String(recipe.retryAfter)) : null) },
           json: async () => recipe.body || {} };
};
const fakeFetch = async (url, opts) => {
  const path = url.replace("http://127.0.0.1:8000", "");
  if (opts && opts.method && opts.method !== "GET") sent.push({ path, body: opts.body });
  const recipes = answers[path];
  if (!recipes || recipes.length === 0) return reply({ status: 200 });
  return reply(recipes.length > 1 ? recipes.shift() : recipes[0]);
};
const context = vm.createContext({
  chrome, fetch: fakeFetch, console: { log() {}, warn() {}, error() {}, debug() {} }, URL, setTimeout, TextEncoder,
});
vm.runInContext(source, context);

const tick = (ms) => new Promise((r) => setTimeout(r, ms || 30));
const relay = (path, body, tabId) => new Promise((resolve) => {
  const sender = { tab: { id: tabId === undefined ? 1 : tabId, url: "https://www.linkedin.com/feed/" }, id: "self" };
  for (const fn of listeners.message) fn({ action: "STUDIO_API", path, body: body || { full_name: "A Person" } }, sender, resolve);
});
const fromPanel = (message) => new Promise((resolve) => {
  const sender = { id: "self", url: "chrome-extension://self/sidepanel.html" };
  for (const fn of listeners.message) fn(message, sender, resolve);
});
const writes = (path) => sent.filter((s) => s.path === path).map((w) => JSON.parse(w.body));
const busy = { status: 503, retryAfter: 0.01, body: { detail: { code: "studio_busy" } } };

(async () => {
  const out = {};

  // 1. A capture the studio took is written to storage as the last capture,
  //    and the tab's badge counts it.
  answers["/api/v1/crm/interactions/ingest"] = [{ status: 200, body: { status: "success", outcome: "accepted", interaction: { id: 5 } } }];
  await relay("/api/v1/crm/interactions/ingest", { full_name: "First Person" }, 7);
  await tick(40);
  out.lastCapture = storage.lastCapture || null;
  out.badgeAfterOne = badge.text.filter((d) => d.tabId === 7).map((d) => d.text);
  await relay("/api/v1/crm/interactions/ingest", { full_name: "Second Person" }, 7);
  answers["/api/v1/self/posts/ingest"] = [{ status: 200, body: { status: "success", written: 2, skipped: 0 } }];
  await relay("/api/v1/self/posts/ingest", { author: "me", posts: [] }, 9);
  await tick(40);
  out.badgeAfterThree = badge.text.filter((d) => d.tabId === 7).map((d) => d.text);
  out.badgeOtherTab = badge.text.filter((d) => d.tabId === 9).map((d) => d.text);
  out.countsInStorage = storage.badgeCounts || null;
  out.greenAfterCaptures = badge.background.length ? badge.background[badge.background.length - 1] : null;

  // 1b. A 200 that stored nothing (an engager on someone else's post) is a
  //     relay, and is not a capture: the badge does not count it.
  answers["/api/v1/crm/interactions/ingest"] = [{ status: 200, body: { status: "skipped", outcome: "nothing_new", reason: "not_your_post" } }];
  await relay("/api/v1/crm/interactions/ingest", { full_name: "Stranger Engager" }, 7);
  await tick(40);
  out.nothingNew = storage.lastCapture || null;
  out.countAfterNothingNew = (storage.badgeCounts || {})[7];
  answers["/api/v1/self/posts/ingest"] = [{ status: 200, body: { status: "success", written: 0, skipped: 3 } }];
  await relay("/api/v1/self/posts/ingest", { author: "me", posts: [] }, 9);
  await tick(40);
  out.countOtherTabAfterNothing = (storage.badgeCounts || {})[9];
  delete answers["/api/v1/self/posts/ingest"];
  answers["/api/v1/crm/interactions/ingest"] = [{ status: 200, body: { status: "success", outcome: "accepted", interaction: { id: 6 } } }];

  // 2. Bookkeeping is not a capture: a heartbeat or a capture log row does
  //    not move the badge or the last capture.
  const before = (storage.badgeCounts || {})[7];
  await relay("/api/v1/bridge/heartbeat", { extension_version: "9.9.9" }, 7);
  await relay("/api/v1/bridge/capture", { extractor: "engagers", items_seen: 1, items_kept: 1 }, 7);
  await tick(40);
  out.countAfterBookkeeping = (storage.badgeCounts || {})[7];
  out.countBeforeBookkeeping = before;
  out.lastCaptureAfterBookkeeping = storage.lastCapture ? storage.lastCapture.path : null;
  out.lastCaptureAfterBookkeepingStored = storage.lastCapture ? storage.lastCapture.stored : null;

  // 3. Waiting captures turn the badge orange, and it stays while any wait.
  answers["/api/v1/crm/interactions/ingest"] = [busy];
  await relay("/api/v1/crm/interactions/ingest", { full_name: "Kept Person" }, 7);
  await tick(60);
  out.keptCapture = storage.lastCapture || null;
  out.orangeWhileWaiting = badge.background[badge.background.length - 1];
  out.titleWhileWaiting = badge.title.length ? badge.title[badge.title.length - 1].title : null;
  const globalTexts = badge.text.filter((d) => d.tabId === undefined);
  out.globalTextWhileWaiting = globalTexts.length ? globalTexts[globalTexts.length - 1].text : null;

  // 4. A drift the readers report is noted once per page kind per session.
  delete session.lastDrift;
  answers["/api/v1/bridge/capture"] = [{ status: 200 }];
  await relay("/api/v1/bridge/capture", { extractor: "engagers", page_kind: "feed", items_seen: 3, items_kept: 0, drift: ["commenter_name"] }, 7);
  await tick(40);
  out.driftNoted = session.lastDrift || null;
  out.driftNotInLocal = storage.lastDrift === undefined;
  const firstDriftAt = session.lastDrift && session.lastDrift.at;
  await tick(5);
  await relay("/api/v1/bridge/capture", { extractor: "engagers", page_kind: "feed", items_seen: 3, items_kept: 0, drift: ["commenter_name", "headline"] }, 7);
  await tick(40);
  out.driftNotedTwice = session.lastDrift && session.lastDrift.fields;
  out.driftSameMoment = session.lastDrift && session.lastDrift.at === firstDriftAt;
  await relay("/api/v1/bridge/capture", { extractor: "profile", page_kind: "profile", items_seen: 1, items_kept: 0, drift: ["name"] }, 7);
  await tick(40);
  out.driftOtherKind = session.lastDrift && session.lastDrift.page_kind;
  out.driftSession = Object.keys(session).filter((k) => k.startsWith("driftNoticed"));
  // A clean run of another reader leaves the notice; a clean run of the
  // reader it is about, on the same kind of page, takes it down.
  await relay("/api/v1/bridge/capture", { extractor: "engagers", page_kind: "feed", items_seen: 4, items_kept: 4, drift: null }, 7);
  await tick(40);
  out.driftAfterOtherClean = session.lastDrift ? session.lastDrift.page_kind : null;
  await relay("/api/v1/bridge/capture", { extractor: "profile", page_kind: "profile", items_seen: 2, items_kept: 2, drift: null }, 7);
  await tick(40);
  out.driftAfterClean = session.lastDrift === undefined ? null : session.lastDrift;

  // 5. Opening the panel clears the badge count.
  await fromPanel({ action: "PANEL_OPENED" });
  await tick(40);
  out.badgeAfterPanel = badge.text.filter((d) => d.tabId !== undefined).slice(-2).map((d) => d.text);
  out.countsAfterPanel = storage.badgeCounts || null;

  // 6. The worker heartbeat carries the switch and the registration.
  sent.length = 0;
  storage.networkReading = true;
  storage.keptCaptures = [];
  for (const fn of listeners.alarm) fn({ name: "studio_drain_kept" });
  await tick(80);
  const beats = writes("/api/v1/bridge/heartbeat").filter((b) => b.page_kind === "service_worker");
  out.workerBeat = beats.length ? beats[beats.length - 1] : null;

  // 7. The badge is put back from storage when the browser starts.
  badge.text.length = 0;
  storage.badgeCounts = { 4: 2 };
  for (const fn of listeners.startup) fn();
  await tick(60);
  out.badgeOnStartup = badge.text.filter((d) => d.tabId === 4).map((d) => d.text);

  process.stdout.write(JSON.stringify(out));
})();
"""


@pytest.fixture(scope="module")
def run():
    if not NODE:
        pytest.skip("node is not installed")
    result = subprocess.run([NODE, "-e", HARNESS, os.path.join(EXT, "background.js")],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_the_last_capture_is_written_where_the_panel_can_read_it(run):
    last = run["lastCapture"]
    assert last, "no lastCapture in storage after a relayed capture"
    assert last["path"] == "/api/v1/crm/interactions/ingest"
    assert last["ok"] is True and last["kept"] is False and last["stored"] is True
    assert last["tabId"] == 7
    assert isinstance(last["at"], str) and last["at"]
    assert last["outcome"] == "accepted"


def test_the_badge_counts_this_tabs_captures(run):
    assert run["badgeAfterOne"][-1] == "1"
    assert run["badgeAfterThree"][-1] == "2"
    assert run["badgeOtherTab"][-1] == "1"
    assert run["countsInStorage"] == {"7": 2, "9": 1}


def test_an_answer_that_stored_nothing_is_not_counted(run):
    """
    The engagers of someone else's post are answered 200 nothing_new: the
    rule worked and nothing was stored. Counting them would put a number on
    the badge that no row in the studio stands behind.
    """
    nothing = run["nothingNew"]
    assert nothing["ok"] is True and nothing["stored"] is False
    assert nothing["outcome"] == "nothing_new"
    assert run["countAfterNothingNew"] == run["countsInStorage"]["7"], "a capture that stored nothing was counted"
    assert run["countOtherTabAfterNothing"] == run["countsInStorage"]["9"], "written: 0 was counted as a capture"


def test_bookkeeping_is_not_a_capture(run):
    assert run["countAfterBookkeeping"] == run["countBeforeBookkeeping"]
    assert run["lastCaptureAfterBookkeeping"] == "/api/v1/self/posts/ingest"
    # Still the written: 0 relay before the bookkeeping, which did not overwrite it.
    assert run["lastCaptureAfterBookkeepingStored"] is False


def test_a_kept_capture_is_said_and_turns_the_badge_orange(run):
    kept = run["keptCapture"]
    assert kept["kept"] is True and kept["ok"] is False
    # The studio's orange, as chrome.action takes it: a colour array, not a
    # CSS variable, because the toolbar is not the studio's document.
    assert run["orangeWhileWaiting"]["color"] == [233, 85, 44, 255]
    assert run["greenAfterCaptures"]["color"] == [22, 138, 97, 255]
    assert "waiting" in (run["titleWhileWaiting"] or "")
    # A tab with no count of its own shows how many wait, so the orange is seen.
    assert run["globalTextWhileWaiting"] == "1"


def test_drift_is_noted_once_per_page_kind_per_session(run):
    noted = run["driftNoted"]
    assert noted and noted["extractor"] == "engagers" and noted["page_kind"] == "feed"
    assert run["driftNotInLocal"] is True, "the notice outlives the browser session in local storage"
    assert noted["fields"] == ["commenter_name"]
    assert run["driftSameMoment"] is True, "the second drift on the same page kind replaced the first"
    assert run["driftNotedTwice"] == ["commenter_name"]
    assert run["driftOtherKind"] == "profile", "a drift on another page kind was not noted"
    assert sorted(run["driftSession"]) == ["driftNoticed:feed", "driftNoticed:profile"]


def test_a_clean_run_of_the_same_reader_takes_the_notice_down(run):
    assert run["driftAfterOtherClean"] == "profile", "a clean run of another reader took the notice down"
    assert run["driftAfterClean"] is None, "the reader works again and the notice still says it cannot read"


def test_opening_the_panel_clears_the_badge(run):
    assert run["countsAfterPanel"] == {}
    # null is Chrome's documented reset of one tab's text to the badge's own.
    assert run["badgeAfterPanel"] == [None, None]


def test_the_worker_heartbeat_carries_the_switch_and_the_registration(run):
    beat = run["workerBeat"]
    assert beat, "the worker sent no heartbeat"
    reading = beat["network_reading"]
    assert reading["switch"] is True and reading["registered"] is True
    assert reading["injected"] is None and reading["voyager_calls_seen"] is None, "the worker invented a page's figures"


def test_the_badge_is_put_back_on_startup(run):
    assert run["badgeOnStartup"] == ["2"]
