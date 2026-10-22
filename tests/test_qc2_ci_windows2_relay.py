"""
A Capture the Studio Was Too Busy For Is Kept, Not Dropped (CI-WINDOWS2-N1).
=============================================================================

The studio answers 503 "the studio's database is busy" with Retry-After when
a write cannot get the database lock in time (CI-WIN2-01), and a request can
also end with no answer at all. The service worker reported either to the
content script and forgot it, so the person just captured was gone from the
post with nothing said: the backend retry made that rare, not impossible.

The worker now asks again a few times, honouring Retry-After with jitter, and
if the studio is still busy it keeps the capture in chrome.storage.local and
sends it with the next relay that gets through. These run the real service
worker under node with a fake chrome API, the way
tests/test_network_reading_is_opt_in.py does, so they test behaviour rather
than source text.

Strict Invariants:
- Zero em-dashes in any code, docstring, or comment.
"""

import json
import os
import shutil
import subprocess

import pytest

EXT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "extension"))
NODE = shutil.which("node")

CAPTURE = "/api/v1/crm/interactions/ingest"
HEARTBEAT = "/api/v1/bridge/heartbeat"

HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(process.argv[process.argv.length - 1], "utf8");

const storage = {};
const listeners = { installed: [], startup: [], changed: [], message: [], request: [] };
const event = (bucket) => ({ addListener: (fn) => listeners[bucket].push(fn) });

const chrome = {
  runtime: {
    id: "self",
    lastError: undefined,
    onInstalled: event("installed"),
    onStartup: event("startup"),
    onMessage: event("message"),
    getManifest: () => ({ version: "test" }),
    getURL: (path) => "chrome-extension://self/" + path,
  },
  storage: {
    local: {
      get: (keys, cb) => {
        const wanted = Array.isArray(keys) ? keys : [keys];
        const out = {};
        for (const key of wanted) out[key] = storage[key];
        cb(out);
      },
      set: (items, cb) => { Object.assign(storage, items); if (cb) cb(); },
      remove: (keys) => { for (const key of [].concat(keys)) delete storage[key]; },
    },
    onChanged: event("changed"),
  },
  scripting: {
    getRegisteredContentScripts: async () => [],
    registerContentScripts: async () => {},
    unregisterContentScripts: async () => {},
  },
  alarms: { clear: () => {}, create: () => {}, onAlarm: { addListener: () => {} } },
  cookies: { get: (_q, cb) => cb({ value: "token" }), onChanged: event("changed") },
  sidePanel: { open: async () => {} },
  webRequest: { onCompleted: { addListener: (fn) => listeners.request.push(fn) } },
};

// What the studio answers next, per path: a list of recipes, the last one
// repeating once the list runs out.
const answers = {};
const sent = [];

const reply = (recipe) => {
  if (recipe === "unreachable") throw new TypeError("Failed to fetch");
  const status = recipe.status || 200;
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (name) => (name === "Retry-After" ? (recipe.retryAfter === undefined ? null : String(recipe.retryAfter)) : null) },
    json: async () => recipe.body || {},
  };
};

const fakeFetch = async (url, opts) => {
  const path = url.replace("http://127.0.0.1:8000", "");
  if (opts && opts.method && opts.method !== "GET") sent.push({ path, body: opts.body, at: Date.now() });
  const recipes = answers[path];
  if (!recipes || recipes.length === 0) return reply({ status: 200 });
  return reply(recipes.length > 1 ? recipes.shift() : recipes[0]);
};

const context = vm.createContext({
  chrome, fetch: fakeFetch, console: { log() {}, warn() {}, error() {}, debug() {} },
  URL, setTimeout, TextEncoder,
});
vm.runInContext(source, context);

const tick = (ms) => new Promise((r) => setTimeout(r, ms || 20));
const relay = (path, body) => new Promise((resolve) => {
  const sender = { tab: { id: 1, url: "https://www.linkedin.com/feed/" }, id: "self" };
  for (const fn of listeners.message) fn({ action: "STUDIO_API", path, body: body || { full_name: "A Person" } }, sender, resolve);
});
const kept = () => storage.keptCaptures || [];
const writes = (path) => sent.filter((s) => s.path === path);

(async () => {
  const out = {};

  // One 503, then the studio is free: the capture arrives exactly once.
  answers[CAPTURE] = [{ status: 503, retryAfter: 0.05, body: { detail: { code: "studio_busy" } } }, { status: 200 }];
  out.afterOneBusy = await relay(CAPTURE, { full_name: "Once Person" });
  out.writesAfterOneBusy = writes(CAPTURE).length;
  out.deliveredAfterOneBusy = writes(CAPTURE).filter((w) => JSON.parse(w.body).full_name === "Once Person").length;
  out.keptAfterOneBusy = kept().length;

  // The studio stays busy: every attempt is made, then the capture is kept.
  sent.length = 0;
  answers[CAPTURE] = [{ status: 503, retryAfter: 0.05, body: { detail: { code: "studio_busy" } } }];
  const busyStart = Date.now();
  out.afterStayingBusy = await relay(CAPTURE, { full_name: "Kept Person" });
  out.busyMs = Date.now() - busyStart;
  out.attemptsWhileBusy = writes(CAPTURE).length;
  out.keptWhileBusy = kept().map((item) => ({ path: item.path, name: JSON.parse(item.body).full_name, at: item.at }));

  // A heartbeat is about this moment, so it is not kept.
  answers[HEARTBEAT] = [{ status: 503, retryAfter: 0 }];
  out.afterBusyHeartbeat = await relay(HEARTBEAT, { vanity: "me" });
  out.keptAfterHeartbeat = kept().length;

  // The next relay that gets through sends what was kept, once.
  sent.length = 0;
  answers[CAPTURE] = [{ status: 200 }];
  answers[HEARTBEAT] = [{ status: 200 }];
  out.afterTheStudioIsFree = await relay(HEARTBEAT, { vanity: "me" });
  await tick(50);
  out.keptSent = writes(CAPTURE).map((w) => JSON.parse(w.body).full_name);
  out.keptAfterSending = kept().length;

  // Nothing is sent twice: another relay sends nothing more.
  sent.length = 0;
  out.afterOneMoreRelay = await relay(HEARTBEAT, { vanity: "me" });
  await tick(50);
  out.writesOnTheSecondDrain = writes(CAPTURE).length;

  // A studio that answers nothing at all is the same as a busy one.
  sent.length = 0;
  answers[CAPTURE] = ["unreachable"];
  out.afterNoAnswer = await relay(CAPTURE, { full_name: "Silent Person" });
  out.keptAfterNoAnswer = kept().map((item) => JSON.parse(item.body).full_name);

  // The queue is bounded: a long outage cannot grow it without limit.
  storage.keptCaptures = [];
  for (let k = 0; k < 205; k += 1) {
    storage.keptCaptures.push({ path: CAPTURE, body: JSON.stringify({ full_name: "Person " + k }), at: "then" });
  }
  answers[CAPTURE] = [{ status: 503, retryAfter: 0 }];
  await relay(CAPTURE, { full_name: "Newest Person" });
  out.keptWhenFull = kept().length;
  out.newestIsKept = kept().some((item) => JSON.parse(item.body).full_name === "Newest Person");
  out.oldestIsGone = !kept().some((item) => JSON.parse(item.body).full_name === "Person 0");

  process.stdout.write(JSON.stringify(out));
})();
"""


@pytest.fixture(scope="module")
def run():
    if not NODE:
        pytest.skip("node is not installed")
    harness = HARNESS.replace("CAPTURE", json.dumps(CAPTURE)).replace("HEARTBEAT", json.dumps(HEARTBEAT))
    result = subprocess.run(
        [NODE, "-e", harness, os.path.join(EXT, "background.js")],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_a_busy_studio_then_a_free_one_delivers_exactly_one_capture(run):
    assert run["afterOneBusy"]["status"] == "success", run["afterOneBusy"]
    assert run["writesAfterOneBusy"] == 2, "the capture was not asked again, or was asked too often"
    assert run["deliveredAfterOneBusy"] == 2, "a retry sent a different payload"
    assert run["keptAfterOneBusy"] == 0, "a capture that got through was kept as well"


def test_a_studio_that_stays_busy_has_the_capture_kept_rather_than_lost(run):
    answer = run["afterStayingBusy"]
    assert answer["kept"] is True, answer
    assert answer["httpStatus"] == 503
    assert "kept" in answer["error"]
    assert run["attemptsWhileBusy"] == 3, "the number of attempts is not bounded at three"
    assert [item["name"] for item in run["keptWhileBusy"]] == ["Kept Person"]
    assert run["keptWhileBusy"][0]["path"] == "/api/v1/crm/interactions/ingest"
    # Retry-After was 50 ms and two waits were taken, with jitter.
    assert 50 <= run["busyMs"] < 4000, run["busyMs"]


def test_what_is_about_this_moment_is_not_kept(run):
    assert run["afterBusyHeartbeat"]["status"] == "error"
    assert run["afterBusyHeartbeat"].get("kept") is None
    assert run["keptAfterHeartbeat"] == 1, "a heartbeat was queued, or the kept capture was lost"


def test_the_next_relay_that_gets_through_sends_what_was_kept(run):
    assert run["afterTheStudioIsFree"]["status"] == "success"
    assert run["keptSent"] == ["Kept Person"], run["keptSent"]
    assert run["keptAfterSending"] == 0


def test_a_kept_capture_is_sent_once_and_not_again(run):
    assert run["writesOnTheSecondDrain"] == 0, "a kept capture was sent a second time"


def test_a_studio_that_answers_nothing_keeps_the_capture_too(run):
    assert run["afterNoAnswer"]["kept"] is True, run["afterNoAnswer"]
    assert run["keptAfterNoAnswer"] == ["Silent Person"]


def test_the_queue_is_bounded(run):
    assert run["keptWhenFull"] == 200, run["keptWhenFull"]
    assert run["newestIsKept"], "the capture just taken was the one dropped"
    assert run["oldestIsGone"]
