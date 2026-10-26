"""
No capture is lost quietly, on any path, and the creator is told.
=================================================================

Cycle 2 taught the worker to keep a capture the studio was too busy for. It
covered one ingest path of nine and leaked four ways:

  - a kept capture was never shown to anybody: the `kept` flag was dropped in
    content.js, and nothing anywhere read `keptCaptures`;
  - the queue drained only on browser start-up or after a later successful
    relay, with no `chrome.alarms` despite the permission being in the
    manifest;
  - a refusal during a drain that was not a busy studio was shifted off the
    front and dropped, so an unpaired browser threw the whole queue away;
  - `keepCapture` was not serialized against the drain, so a drain that
    started mid-keep overwrote the capture just kept.

These run the real service worker under node with a fake chrome API, the way
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

HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(process.argv[process.argv.length - 1], "utf8");

const storage = {};
const listeners = { installed: [], startup: [], changed: [], message: [], request: [], alarm: [] };
const event = (bucket) => ({ addListener: (fn) => listeners[bucket].push(fn) });
const alarmsMade = [];
const alarmsCleared = [];

const chrome = {
  runtime: {
    id: "self",
    lastError: undefined,
    onInstalled: event("installed"),
    onStartup: event("startup"),
    onMessage: event("message"),
    getManifest: () => ({ version: "9.9.9" }),
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
  alarms: {
    clear: (name) => { alarmsCleared.push(name); },
    create: (name, info) => { alarmsMade.push({ name, info }); },
    onAlarm: event("alarm"),
  },
  cookies: { get: (_q, cb) => cb({ value: "token" }), onChanged: event("changed") },
  sidePanel: { open: async () => {} },
  webRequest: { onCompleted: { addListener: (fn) => listeners.request.push(fn) } },
};

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
  if (opts && opts.method && opts.method !== "GET") sent.push({ path, body: opts.body });
  const recipes = answers[path];
  if (!recipes || recipes.length === 0) return reply({ status: 200 });
  return reply(recipes.length > 1 ? recipes.shift() : recipes[0]);
};

const context = vm.createContext({
  chrome, fetch: fakeFetch, console: { log() {}, warn() {}, error() {}, debug() {} },
  URL, setTimeout, TextEncoder,
});
vm.runInContext(source, context);

const tick = (ms) => new Promise((r) => setTimeout(r, ms || 30));
const relay = (path, body) => new Promise((resolve) => {
  const sender = { tab: { id: 1, url: "https://www.linkedin.com/feed/" }, id: "self" };
  for (const fn of listeners.message) fn({ action: "STUDIO_API", path, body: body || { full_name: "A Person" } }, sender, resolve);
});
const kept = () => storage.keptCaptures || [];
const names = () => kept().map((item) => JSON.parse(item.body).full_name || JSON.parse(item.body).marker);
const writes = (path) => sent.filter((s) => s.path === path);
const busy = { status: 503, retryAfter: 0.01, body: { detail: { code: "studio_busy" } } };

const CARRIES_DATA = [
  "/api/v1/crm/interactions/ingest",
  "/api/v1/self/posts/ingest",
  "/api/v1/self/posts/analytics",
  "/api/v1/self/outbound/ingest",
  "/api/v1/identity/observe",
  "/api/v1/posts/bind-urn",
  "/api/analytics/ingest",
  "/api/analytics/page-figures",
];
const BOOKKEEPING = [
  "/api/v1/bridge/heartbeat",
  "/api/v1/bridge/capture",
  "/api/v1/self/imports/event",
];

(async () => {
  const out = {};

  // 1. Every path that carries the creator's own data is kept when the studio
  //    is busy. This was one path of nine.
  out.keptPerPath = {};
  for (const path of CARRIES_DATA) {
    storage.keptCaptures = [];
    answers[path] = [busy];
    const answer = await relay(path, { marker: path });
    out.keptPerPath[path] = { kept: answer.kept === true, inQueue: kept().length, waiting: answer.waiting };
    delete answers[path];
  }

  // 2. Bookkeeping is about a moment that has passed, and is not kept.
  out.notKeptPerPath = {};
  for (const path of BOOKKEEPING) {
    storage.keptCaptures = [];
    answers[path] = [busy];
    const answer = await relay(path, { marker: path });
    out.notKeptPerPath[path] = { kept: answer.kept === true, inQueue: kept().length };
    delete answers[path];
  }

  // 3. A browser the studio has not been paired with yet answers 401. Asking
  //    again works as soon as the creator opens the studio, so it is kept.
  storage.keptCaptures = [];
  answers["/api/v1/crm/interactions/ingest"] = [{ status: 401, body: { detail: "no token" } }];
  out.afterUnpaired = await relay("/api/v1/crm/interactions/ingest", { full_name: "Unpaired Person" });
  out.keptAfterUnpaired = names();

  // 4. A drain that meets an unpaired studio keeps everything. It used to
  //    shift each one off the front and throw the whole queue away.
  storage.keptCaptures = [
    { path: "/api/v1/crm/interactions/ingest", body: JSON.stringify({ full_name: "First" }), at: "then" },
    { path: "/api/v1/crm/interactions/ingest", body: JSON.stringify({ full_name: "Second" }), at: "then" },
    { path: "/api/v1/crm/interactions/ingest", body: JSON.stringify({ full_name: "Third" }), at: "then" },
  ];
  sent.length = 0;
  answers["/api/v1/crm/interactions/ingest"] = [{ status: 403, body: { detail: "not paired" } }];
  for (const fn of listeners.startup) fn();
  await tick(80);
  out.keptAfterUnpairedDrain = names();

  // 5. A capture the studio has decided about is dropped, its reason is kept
  //    for the side panel, and the rest of the queue still goes.
  storage.keptCaptures = [
    { path: "/api/v1/crm/interactions/ingest", body: JSON.stringify({ full_name: "Refused" }), at: "then" },
    { path: "/api/v1/crm/interactions/ingest", body: JSON.stringify({ full_name: "Fine" }), at: "then" },
  ];
  delete storage.lastRefusal;
  sent.length = 0;
  answers["/api/v1/crm/interactions/ingest"] = [
    { status: 409, body: { outcome: "refused", reason: "import_posts_first", show: true,
                           message: "Import your posts from the studio's Setup screen first.",
                           detail: "Import your posts from the studio's Setup screen first." } },
    { status: 200 },
  ];
  for (const fn of listeners.startup) fn();
  await tick(80);
  out.afterRefusedDrain = names();
  out.deliveredAfterRefusal = writes("/api/v1/crm/interactions/ingest")
    .map((w) => JSON.parse(w.body).full_name);
  out.rememberedRefusal = storage.lastRefusal || null;

  // 6. An alarm drains the queue, so a creator who closed LinkedIn does not
  //    wait for the next browser start. It is cleared once nothing is waiting.
  alarmsMade.length = 0;
  alarmsCleared.length = 0;
  storage.keptCaptures = [];
  answers["/api/v1/crm/interactions/ingest"] = [busy];
  await relay("/api/v1/crm/interactions/ingest", { full_name: "Alarm Person" });
  out.alarmsWhileWaiting = alarmsMade.map((a) => a.name);
  out.alarmPeriod = alarmsMade.length ? alarmsMade[0].info : null;
  out.alarmListeners = listeners.alarm.length;

  sent.length = 0;
  answers["/api/v1/crm/interactions/ingest"] = [{ status: 200 }];
  for (const fn of listeners.alarm) fn({ name: "studio_drain_kept" });
  await tick(80);
  out.drainedByAlarm = writes("/api/v1/crm/interactions/ingest").map((w) => JSON.parse(w.body).full_name);
  out.keptAfterAlarm = kept().length;
  out.alarmsClearedAfter = alarmsCleared.filter((n) => n === "studio_drain_kept").length;

  // 7. How many are waiting is written where the side panel can read it, and
  //    told to the studio so a screen can show the number.
  storage.keptCaptures = [];
  sent.length = 0;
  answers["/api/v1/crm/interactions/ingest"] = [busy];
  const keptAnswer = await relay("/api/v1/crm/interactions/ingest", { full_name: "Counted Person" });
  await tick(60);
  out.waitingInStorage = storage.waitingCaptures || null;
  out.waitingToldToStudio = writes("/api/v1/bridge/heartbeat")
    .map((w) => JSON.parse(w.body))
    .filter((b) => b.waiting_captures !== undefined);
  out.keptAnswerWaiting = keptAnswer.waiting;

  // 8. A refusal comes back with its reason and its sentence, so whoever asked
  //    can show it. All of this used to collapse to an error with nothing said.
  storage.keptCaptures = [];
  answers["/api/v1/self/posts/analytics"] = [
    { status: 409, body: { outcome: "refused", reason: "import_posts_first", show: true,
                           message: "Import your posts first.", detail: "Import your posts first." } },
  ];
  out.refusalAnswer = await relay("/api/v1/self/posts/analytics", { marker: "analytics" });

  // 9. Every write declares the contract it speaks and the build that sent it.
  sent.length = 0;
  answers["/api/v1/crm/interactions/ingest"] = [{ status: 200 }];
  await relay("/api/v1/crm/interactions/ingest", { full_name: "Stamped Person" });
  out.stamped = JSON.parse(writes("/api/v1/crm/interactions/ingest")[0].body);

  // 10. A studio newer than this extension is noted once, not on every call.
  delete storage.reloadNoticeFor;
  answers["/api/v1/crm/interactions/ingest"] = [{
    status: 200,
    body: { status: "success", handshake: { contract_version: 7, reload_required: true, message: "Reload it." } },
  }];
  await relay("/api/v1/crm/interactions/ingest", { full_name: "Old Extension" });
  await tick(50);
  out.reloadNoticeFor = storage.reloadNoticeFor;
  out.handshakeHeld = storage.studioHandshake || null;

  process.stdout.write(JSON.stringify(out));
})();
"""


@pytest.fixture(scope="module")
def run():
    if not NODE:
        pytest.skip("node is not installed")
    result = subprocess.run(
        [NODE, "-e", HARNESS, os.path.join(EXT, "background.js")],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_every_path_that_carries_the_creators_data_is_kept(run):
    """
    KEEP_WHEN_BUSY was {"/api/v1/crm/interactions/ingest"}, so the creator's
    engagers survived a busy studio and their own posts, their posts' figures,
    their comments and reactions, and their profile did not.
    """
    for path, seen in run["keptPerPath"].items():
        assert seen["kept"] is True, f"{path} was not kept for a busy studio"
        assert seen["inQueue"] == 1, f"{path} was answered as kept but is not in the queue"
        assert seen["waiting"] == 1, f"{path} did not say how many are waiting"


def test_bookkeeping_about_a_passing_moment_is_still_not_kept(run):
    """A heartbeat or a capture log resent later would be a lie about when."""
    for path, seen in run["notKeptPerPath"].items():
        assert seen["kept"] is False, f"{path} was queued although it is about a moment"
        assert seen["inQueue"] == 0


def test_a_browser_the_studio_has_not_been_paired_with_keeps_the_capture(run):
    """
    401 and 403 mean the creator has not opened the studio in this browser
    yet, which ends the moment they do. The capture was dropped.
    """
    assert run["afterUnpaired"]["kept"] is True, run["afterUnpaired"]
    assert run["keptAfterUnpaired"] == ["Unpaired Person"]


def test_a_drain_that_meets_an_unpaired_studio_keeps_the_whole_queue(run):
    """
    The leak that cost the most: a non-busy refusal during a drain was shifted
    off the front and dropped, one per item, so an unpaired browser emptied the
    queue of everything the creator had captured.
    """
    assert run["keptAfterUnpairedDrain"] == ["First", "Second", "Third"], run["keptAfterUnpairedDrain"]


def test_a_decided_refusal_is_dropped_remembered_and_does_not_block_the_rest(run):
    assert run["afterRefusedDrain"] == [], run["afterRefusedDrain"]
    assert run["deliveredAfterRefusal"] == ["Refused", "Fine"], run["deliveredAfterRefusal"]
    remembered = run["rememberedRefusal"]
    assert remembered and remembered["reason"] == "import_posts_first"
    assert "Import your posts" in remembered["message"]
    assert remembered["show"] is True


def test_an_alarm_drains_the_queue_and_stops_when_it_is_empty(run):
    """
    The drain fired only on chrome.runtime.onStartup or after a later
    successful relay, so a creator who closed LinkedIn with captures waiting
    kept them until the next browser start. The alarms permission was already
    in the manifest and unused.
    """
    assert run["alarmsWhileWaiting"] == ["studio_drain_kept"], run["alarmsWhileWaiting"]
    assert run["alarmPeriod"]["periodInMinutes"] == 1
    assert run["alarmListeners"] == 1, "nothing listens for the drain alarm"
    assert run["drainedByAlarm"] == ["Alarm Person"], run["drainedByAlarm"]
    assert run["keptAfterAlarm"] == 0
    assert run["alarmsClearedAfter"] >= 1, "the alarm kept firing with nothing waiting"


def test_how_many_are_waiting_is_said_where_it_can_be_read(run):
    """
    Nothing in the product read keptCaptures, so a creator had no way to learn
    that work was waiting rather than lost.
    """
    assert run["waitingInStorage"]["waiting"] == 1
    assert run["waitingInStorage"]["oldest_at"]
    assert run["keptAnswerWaiting"] == 1
    told = run["waitingToldToStudio"]
    assert told, "the studio was never told how many captures are waiting"
    assert told[-1]["waiting_captures"] == 1
    assert told[-1]["contract_version"] == 1


def test_a_refusal_comes_back_with_its_reason_and_its_sentence(run):
    answer = run["refusalAnswer"]
    assert answer["status"] == "error" and answer["httpStatus"] == 409
    assert answer["reason"] == "import_posts_first"
    assert answer["message"] == "Import your posts first."
    assert answer["show"] is True


def test_every_write_declares_the_contract_it_speaks(run):
    """
    The handshake. The extension sent extension_version on four paths and the
    studio compared it to nothing.
    """
    assert run["stamped"]["contract_version"] == 1
    assert run["stamped"]["extension_version"] == "9.9.9"


def test_a_studio_newer_than_this_extension_is_noted_once(run):
    assert run["reloadNoticeFor"] == 7
    assert run["handshakeHeld"]["message"] == "Reload it."


# ---------------------------------------------------------------------------
# The page scripts. These need a LinkedIn DOM to run, so what is asserted here
# is that the handling exists where the defect was, in the wording the creator
# reads.
# ---------------------------------------------------------------------------

def _source(name):
    with open(os.path.join(EXT, name), encoding="utf-8") as handle:
        return handle.read()


def test_the_page_script_no_longer_collapses_a_refusal_to_null():
    """
    own_pages.js:54-57 resolved every answer that was not a success to null,
    with nothing logged, which is why "this post is not one of your recorded
    posts; import your posts first" was invisible on the one page a creator
    opens on purpose.
    """
    own = _source("own_pages.js")
    assert "function studioCall(" in own, "there is still no answer-shaped call"
    call = own[own.index("function studioCall("):own.index("function rememberRefusal(")]
    assert "unreachable: true" in call, "no answer at all is not told apart from a refusal"
    assert "reason:" in call and "message:" in call and "show:" in call
    assert "kept: true" in call, "a capture the worker kept is not told apart from a refusal"
    wrapper = own[own.index("async function studio(path, body)"):]
    wrapper = wrapper[:wrapper.index("\n  }")]
    assert "console.warn" in wrapper and "rememberRefusal" in wrapper, (
        "a refusal is still returned as null with nothing logged")


def test_the_analytics_page_says_on_the_page_what_the_studio_refused():
    own = _source("own_pages.js")
    assert 'announce(await studioCall("/api/v1/self/posts/analytics"' in own
    announce = own[own.index("function announce(answer, path)"):]
    announce = announce[:announce.index("\n  }\n")]
    # Said in the side panel, or in the import's banner while one runs
    # (cycle 4, the review's S7): never drawn into the page on its own.
    assert "notice(" in announce and "answer.message" in announce
    assert "waiting in all" in announce, "a kept capture does not say how many are waiting"


def test_the_engager_notice_shows_every_refusal_the_studio_asked_to_be_shown():
    """
    content.js counted a skip as needing setup only when the reason matched
    /Setup/, which the reason the creator meets most does not, so no toast
    fired at all.
    """
    content = _source("content.js")
    assert "/Setup/.test" not in content, "the notice still matches on the word Setup"
    assert 'a.status === "refused" && a.show && a.message' in content
    assert "are kept and will be sent again" in content
    panel = _source("content.js")
    assert '"kept"' in panel, "content.js still drops the kept flag"


def test_the_side_panel_shows_what_is_waiting_and_what_was_refused():
    panel = _source("sidepanel.js")
    assert "waitingAndRefusalPanel" in panel
    block = panel[panel.index("async function waitingAndRefusalPanel("):panel.index("async function loadSideHealth(")]
    assert "not measured yet" in block, "an unreported count is shown as a number"
    assert "capture(s) waiting" in block
    assert "last refused a capture" in block
    assert "Reload this extension" in block
