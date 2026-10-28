"""
The network interceptor runs only when the creator switches it on.
==================================================================

voyager_interceptor.js wraps window.fetch inside LinkedIn's own page. It was a
static MAIN-world content script, injected again on every tab update and on
request from content.js, with no setting anywhere to turn it off. It is the
part of the bridge most visible to LinkedIn, and the page readers and the
data archive cover what it adds.

Now it is registered only while `networkReading` is true in the extension's
storage, which only the popup's switch sets, and the two capture paths it
feeds are refused while it is off. These run the real service worker under
node with a fake chrome API, so they test behaviour rather than source text.
"""

import json
import re
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
const listeners = { installed: [], startup: [], changed: [], message: [], request: [] };
const registered = [];
const calls = { register: [], unregister: [], fetch: [] };
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
    local: { get: (key, cb) => cb({ [key]: storage[key] }) },
    onChanged: event("changed"),
  },
  scripting: {
    getRegisteredContentScripts: async ({ ids }) => registered.filter((s) => ids.includes(s.id)),
    registerContentScripts: async (scripts) => { calls.register.push(scripts); registered.push(...scripts); },
    unregisterContentScripts: async ({ ids }) => {
      calls.unregister.push(ids);
      for (const id of ids) { const i = registered.findIndex((s) => s.id === id); if (i >= 0) registered.splice(i, 1); }
    },
  },
  alarms: { clear: () => {}, create: () => {}, onAlarm: { addListener: () => {} } },
  cookies: { get: (_q, cb) => cb({ value: "token" }) },
  sidePanel: { open: async () => {} },
  webRequest: { onCompleted: { addListener: (fn) => listeners.request.push(fn) } },
};
const fakeFetch = async (url, opts) => {
  calls.fetch.push(url);
  return { ok: true, status: 200, json: async () => ({}) };
};
const context = vm.createContext({ chrome, fetch: fakeFetch, console: { log() {}, warn() {}, error() {} }, URL, setTimeout });
vm.runInContext(source, context);

const tick = () => new Promise((r) => setTimeout(r, 20));
const relay = (path) => new Promise((resolve) => {
  const sender = { tab: { id: 1, url: "https://www.linkedin.com/feed/" }, id: "self" };
  for (const fn of listeners.message) fn({ action: "STUDIO_API", path, body: { a: 1 } }, sender, resolve);
});
const setting = async (value) => {
  const old = storage.networkReading;
  storage.networkReading = value;
  for (const fn of listeners.changed) fn({ networkReading: { oldValue: old, newValue: value } }, "local");
  await tick();
};

(async () => {
  const out = {};
  for (const fn of listeners.installed) await fn({ reason: "install" });
  await tick();
  out.registeredAfterInstall = registered.map((s) => s.id);

  for (const fn of listeners.request) fn({ url: "https://www.linkedin.com/voyager/api/feed/updatesV2?q=x", statusCode: 200, method: "GET" });
  await tick();
  out.requestNotesWhileOff = calls.fetch.filter((u) => u.endsWith("/api/analytics/ingest")).length;
  out.offIngest = await relay("/api/v1/bridge/voyager-ingest");
  out.offDrift = await relay("/api/v1/bridge/schema-drift");
  // The worker's own heartbeat is not a capture (cycle 4, track 1, phase 2).
  out.fetchesWhileOff = calls.fetch.filter((u) => !u.endsWith("/api/v1/bridge/heartbeat")).length;

  await setting(true);
  out.registerCalls = calls.register;
  out.onIngest = await relay("/api/v1/bridge/voyager-ingest");
  out.fetchesWhileOn = calls.fetch.filter((u) => u.endsWith("/api/v1/bridge/voyager-ingest")).length;
  for (const fn of listeners.request) fn({ url: "https://www.linkedin.com/voyager/api/feed/updatesV2?q=x", statusCode: 200, method: "GET" });
  await tick();
  out.requestNotesWhileOn = calls.fetch.filter((u) => u.endsWith("/api/analytics/ingest")).length;

  await setting(false);
  out.unregisterCalls = calls.unregister;
  out.registeredAfterOff = registered.map((s) => s.id);
  process.stdout.write(JSON.stringify(out));
})();
"""


@pytest.fixture(scope="module")
def run():
    if not NODE:
        pytest.skip("node is not installed")
    result = subprocess.run(
        [NODE, "-e", HARNESS, os.path.join(EXT, "background.js")],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_the_manifest_no_longer_injects_it():
    with open(os.path.join(EXT, "manifest.json"), encoding="utf-8") as handle:
        manifest = json.load(handle)
    for entry in manifest.get("content_scripts", []):
        assert "voyager_interceptor.js" not in entry.get("js", []), "the interceptor is a static content script again"
        if entry.get("world") == "MAIN":
            assert entry["js"] == ["card_urns.js"], "something else runs in LinkedIn's page unconditionally"


def test_feed_cards_get_their_post_id_whether_or_not_network_reading_is_on():
    """
    Feed cards carry their post id only in React's properties, which only a
    page-world script can read. That used to live in the interceptor, so the
    default (off) left feed engagers without a post.
    """
    with open(os.path.join(EXT, "card_urns.js"), encoding="utf-8") as handle:
        stamper = handle.read()
    assert "data-urn" in stamper and "__reactProps" in stamper
    code = stamper.split("*/", 1)[1]
    for forbidden in ("fetch", "XMLHttpRequest", "chrome."):
        assert forbidden not in code, f"card_urns.js uses {forbidden}; it must only read the page"
    # Its one message is its own count and timing, to the isolated world on
    # this page (the review's S7: it used to mark LinkedIn's root element).
    assert code.count("postMessage(") == 1, "card_urns.js posts something besides its run"
    assert "INOX_CARD_URNS_REPORT" in code and "window.location.origin" in code
    with open(os.path.join(EXT, "voyager_interceptor.js"), encoding="utf-8") as handle:
        assert "stampCardUrns" not in handle.read()


def test_nothing_else_injects_it():
    for name in ("background.js", "content.js", "own_pages.js", "sidepanel.js", "popup.js"):
        with open(os.path.join(EXT, name), encoding="utf-8") as handle:
            source = handle.read()
        assert "INJECT_INTERCEPTOR" not in source, f"{name} still asks for the interceptor to be injected"
        # The worker gives the LinkedIn tabs already open the readers on an
        # update (cycle 4, track 1, phase 2), and never the interceptor.
        injected = re.findall(r"executeScript\([^)]*?files:\s*(\[[^\]]*\]|[A-Z_]+)", source, re.DOTALL)
        named = {name for files in injected for name in re.findall(r'"([\w.]+\.js)"', files)}
        for constant in [files for files in injected if not files.startswith("[")]:
            declared = re.search(r"const " + constant + r" = (\[[^\]]*\])", source)
            assert declared, f"{name} injects {constant}, which it does not declare"
            named |= set(re.findall(r'"([\w.]+\.js)"', declared.group(1)))
        assert "voyager_interceptor.js" not in named, f"{name} injects the interceptor directly"


def test_off_by_default(run):
    assert run["registeredAfterInstall"] == [], "a fresh install runs the interceptor"


def test_its_captures_are_refused_while_off(run):
    for key in ("offIngest", "offDrift"):
        assert run[key]["status"] == "error" and "off" in run[key]["error"]
    assert run["fetchesWhileOff"] == 0, "a capture reached the studio while network reading was off"


def test_switching_it_on_registers_it_in_the_page_world(run):
    [[script]] = run["registerCalls"]
    assert script["js"] == ["voyager_interceptor.js"]
    assert script["world"] == "MAIN" and script["runAt"] == "document_start"
    assert script["matches"] == ["https://*.linkedin.com/*"]
    assert run["onIngest"]["status"] == "success" and run["fetchesWhileOn"] == 1


def test_switching_it_off_removes_it(run):
    assert run["unregisterCalls"] and run["registeredAfterOff"] == []


def test_the_page_cannot_feed_it_while_off():
    """Any script on a LinkedIn page can post a message claiming to be the interceptor."""
    with open(os.path.join(EXT, "content.js"), encoding="utf-8") as handle:
        content = handle.read()
    listener = content[content.index('event.data.source !== "inox-voyager-interceptor"'):][:200]
    assert "if (!networkReadingOn) return;" in listener


def test_the_switch_says_what_it_does():
    with open(os.path.join(EXT, "popup.js"), encoding="utf-8") as handle:
        popup = handle.read()
    note = popup.split("NETWORK_READING_NOTE_OFF =", 1)[1].split(";", 1)[0]
    for claim in ("Off.", "wrapping", "fetch", "automation", "never sends a request"):
        assert claim in note, f"the disclosure no longer says '{claim}'"


def test_watching_linkedins_requests_follows_the_same_switch(run):
    assert run["requestNotesWhileOff"] == 0, "LinkedIn's requests were noted while network reading was off"
    assert run["requestNotesWhileOn"] == 1
