// Ten tabs on one post (tests/test_qc4_t1p2_ten_tabs.py): runs background.js
// under node against a real studio on a loopback port, replays one tab's read
// from N tabs at once, and reports the requests the worker made to the studio.
const fs = require("fs");
const vm = require("vm");
const nodeCrypto = require("crypto");

const [, , workerPath, port, token, messagesPath, tabCount] = process.argv;
const messages = JSON.parse(fs.readFileSync(messagesPath, "utf8"));
const storage = { signedInVanity: "test-creator" };
const session = {};
const listeners = { installed: [], startup: [], changed: [], message: [], request: [], alarm: [], removed: [], cookie: [], updated: [] };
const event = (bucket) => ({ addListener: (fn) => listeners[bucket].push(fn) });
const area = (store) => ({
  get: (keys, cb) => { const out = {}; for (const k of (keys === null || keys === undefined ? Object.keys(store) : [].concat(keys))) if (k in store) out[k] = JSON.parse(JSON.stringify(store[k])); setTimeout(() => cb(out), 0); },
  set: (items, cb) => { for (const k of Object.keys(items)) store[k] = JSON.parse(JSON.stringify(items[k])); if (cb) setTimeout(cb, 0); },
  remove: (keys, cb) => { for (const k of [].concat(keys)) delete store[k]; if (cb) setTimeout(cb, 0); },
});
const chrome = {
  runtime: { id: "self", lastError: undefined, onInstalled: event("installed"), onStartup: event("startup"), onMessage: event("message"),
    getManifest: () => ({ version: "measure" }), getURL: (p) => "chrome-extension://self/" + p, reload: () => {} },
  storage: { local: area(storage), session: area(session), onChanged: event("changed") },
  scripting: { getRegisteredContentScripts: async () => [], registerContentScripts: async () => {}, unregisterContentScripts: async () => {},
    executeScript: async () => [{ result: null }] },
  alarms: { create: () => {}, clear: (n, cb) => { if (cb) cb(true); }, get: (n, cb) => cb({ name: n }), onAlarm: event("alarm") },
  cookies: { get: (_q, cb) => cb({ value: token }), onChanged: event("cookie") },
  sidePanel: { open: async () => {} },
  webRequest: { onCompleted: { addListener: () => {} } },
  action: { setBadgeText: (d, cb) => cb && cb(), setBadgeBackgroundColor: (d, cb) => cb && cb(), setBadgeTextColor: (d, cb) => cb && cb(), setTitle: (d, cb) => cb && cb() },
  tabs: { onRemoved: event("removed"), onUpdated: event("updated"), query: async () => [] },
};
const requests = [];
const realFetch = async (url, opts) => {
  url = String(url);
  if (url.startsWith("chrome-extension://")) return { ok: true, status: 200, headers: { get: () => null }, json: async () => ({ version: "measure" }) };
  const target = url.replace("http://127.0.0.1:8000", "http://127.0.0.1:" + port).replace("http://localhost:8000", "http://127.0.0.1:" + port);
  const path = target.replace("http://127.0.0.1:" + port, "");
  const started = Date.now();
  const response = await fetch(target, opts);
  requests.push({ path, method: (opts && opts.method) || "GET", status: response.status, ms: Date.now() - started });
  return response;
};
const context = vm.createContext({ chrome, fetch: realFetch, URL, setTimeout, clearTimeout, setInterval, clearInterval, TextEncoder,
  crypto: nodeCrypto.webcrypto, navigator: { userAgentData: { brands: [{ brand: "Chromium" }] } },
  console: { log() {}, warn() {}, error() {}, debug() {} } });
vm.runInContext(fs.readFileSync(workerPath, "utf8"), context);

const relay = (message, tabId) => new Promise((resolve) => {
  const sender = { tab: { id: tabId, windowId: 1, active: tabId === 1, url: "https://www.linkedin.com/feed/" }, id: "self",
    url: "https://www.linkedin.com/feed/", frameId: 0, documentId: "doc-" + tabId };
  for (const fn of listeners.message) fn(message, sender, resolve);
});

(async () => {
  const started = Date.now();
  const tabs = [];
  for (let tab = 1; tab <= Number(tabCount); tab += 1) {
    tabs.push(Promise.all(messages.map((m) => relay(m, tab))));
  }
  await Promise.all(tabs);
  await new Promise((r) => setTimeout(r, 300));
  const wall = Date.now() - started;
  const byPath = {};
  for (const r of requests) byPath[r.path] = (byPath[r.path] || 0) + 1;
  process.stdout.write(JSON.stringify({ wall_ms: wall, requests: requests.filter((r) => r.method !== "GET").length,
    by_path: byPath, studio_ms: requests.reduce((s, r) => s + r.ms, 0) }));
  process.exit(0);
})();
