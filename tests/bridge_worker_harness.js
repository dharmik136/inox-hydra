// The extension's service worker under node, with a fake chrome API and a
// fake studio, for the cycle 4 track 1 phase 2 tests (tests/test_qc4_t1p2_*).
// Nothing here reaches the network: fetch is answered from recipes, and the
// extension's own manifest.json is answered from `diskVersion`, as an
// unpacked install's files on disk would answer it.
const fs = require("fs");
const vm = require("vm");
const nodeCrypto = require("crypto");

function boot(sourcePath, options) {
  options = options || {};
  const storage = Object.assign({}, options.storage || {});
  const session = Object.assign({}, options.session || {});
  const listeners = { installed: [], startup: [], changed: [], message: [], request: [], alarm: [], removed: [],
    cookie: [], updated: [] };
  const event = (bucket) => ({ addListener: (fn) => listeners[bucket].push(fn) });
  const badge = { text: [], background: [], textColor: [], title: [] };
  const area = (store, name) => ({
    get: (keys, cb) => {
      const wanted = keys === null || keys === undefined ? Object.keys(store) : [].concat(keys);
      const out = {};
      for (const key of wanted) if (key in store) out[key] = JSON.parse(JSON.stringify(store[key]));
      setTimeout(() => cb(out), 0);
    },
    set: (items, cb) => {
      const changes = {};
      for (const key of Object.keys(items)) {
        changes[key] = { oldValue: store[key], newValue: items[key] };
        store[key] = JSON.parse(JSON.stringify(items[key]));
      }
      for (const fn of listeners.changed) fn(changes, name);
      if (cb) setTimeout(cb, 0);
    },
    remove: (keys, cb) => {
      for (const key of [].concat(keys)) delete store[key];
      if (cb) setTimeout(cb, 0);
    },
  });
  const alarms = {};
  const executed = [];
  const registered = (options.registered || []).map((id) => ({ id }));
  const unregistered = [];
  const tabs = (options.tabs || []).map((tab) => Object.assign({}, tab));
  const diskManifest = { version: options.diskVersion || options.version || "9.9.9" };
  let reloads = 0;
  const chrome = {
    runtime: {
      id: "self", lastError: undefined,
      onInstalled: event("installed"), onStartup: event("startup"), onMessage: event("message"),
      getManifest: () => ({ version: options.version || "9.9.9" }),
      getURL: (path) => "chrome-extension://self/" + path,
      reload: () => { reloads += 1; },
    },
    storage: { local: area(storage, "local"), session: options.noSession ? undefined : area(session, "session"),
      onChanged: event("changed") },
    scripting: {
      // Scripts registered with the browser, which persist across sessions:
      // `registered` lists what an earlier version left registered.
      getRegisteredContentScripts: async (filter) => registered
        .filter((script) => !filter || !filter.ids || filter.ids.includes(script.id))
        .map((script) => Object.assign({}, script)),
      registerContentScripts: async (scripts) => { for (const script of scripts) registered.push(Object.assign({}, script)); },
      unregisterContentScripts: async (filter) => {
        const ids = filter && filter.ids ? filter.ids : registered.map((script) => script.id);
        unregistered.push(...ids);
        for (const id of ids) {
          const at = registered.findIndex((script) => script.id === id);
          if (at >= 0) registered.splice(at, 1);
        }
      },
      executeScript: async (details) => {
        executed.push(JSON.parse(JSON.stringify(details)));
        if (details.func) return [{ result: options.probe === undefined ? null : options.probe }];
        if (options.executeFails) throw new Error(options.executeFails);
        return [{ result: null }];
      },
    },
    alarms: {
      create: (name, info) => { alarms[name] = info; },
      clear: (name, cb) => { delete alarms[name]; if (cb) cb(true); },
      get: (name, cb) => cb(alarms[name]),
      onAlarm: event("alarm"),
    },
    cookies: { get: (_query, cb) => cb({ value: "token" }), onChanged: event("cookie") },
    sidePanel: { open: async () => {} },
    webRequest: { onCompleted: { addListener: (fn) => listeners.request.push(fn) } },
    action: {
      setBadgeText: (d, cb) => { badge.text.push(d); if (cb) cb(); },
      setBadgeBackgroundColor: (d, cb) => { badge.background.push(d); if (cb) cb(); },
      setBadgeTextColor: (d, cb) => { badge.textColor.push(d); if (cb) cb(); },
      setTitle: (d, cb) => { badge.title.push(d); if (cb) cb(); },
    },
    tabs: { onRemoved: event("removed"), onUpdated: event("updated"), query: async () => tabs.map((t) => Object.assign({}, t)) },
  };

  const sent = [];
  const recipes = {};
  let inFlight = 0;
  let maxInFlight = 0;
  const fakeFetch = async (url, opts) => {
    if (String(url).startsWith("chrome-extension://")) {
      // A folder deleted or moved under the running extension: the browser
      // cannot read the file, and fetch rejects as Chromium's does.
      if (options.filesGone) throw new TypeError("Failed to fetch");
      return { ok: true, status: 200, headers: { get: () => null }, json: async () => JSON.parse(JSON.stringify(diskManifest)) };
    }
    const path = String(url).replace("http://127.0.0.1:8000", "");
    const record = { path, body: opts && opts.body ? JSON.parse(opts.body) : null, headers: (opts && opts.headers) || {} };
    if (opts && opts.method && opts.method !== "GET") sent.push(record);
    inFlight += 1;
    maxInFlight = Math.max(maxInFlight, inFlight);
    try {
      if (options.studioDelayMs) await new Promise((r) => setTimeout(r, options.studioDelayMs));
      let recipe = { status: 200, body: {} };
      const found = recipes[path];
      if (typeof found === "function") recipe = found(record);
      else if (Array.isArray(found) && found.length) recipe = found.length > 1 ? found.shift() : found[0];
      if (recipe === "unreachable") throw new TypeError("Failed to fetch");
      const status = recipe.status || 200;
      return {
        ok: status >= 200 && status < 300, status,
        headers: { get: (name) => (name === "Retry-After" ? (recipe.retryAfter === undefined ? null : String(recipe.retryAfter)) : null) },
        json: async () => JSON.parse(JSON.stringify(recipe.body || {})),
      };
    } finally {
      inFlight -= 1;
    }
  };
  const context = vm.createContext({
    chrome, fetch: fakeFetch, URL, setTimeout, clearTimeout, setInterval, clearInterval, TextEncoder,
    crypto: nodeCrypto.webcrypto,
    navigator: options.navigator || { userAgentData: { brands: [{ brand: "Chromium" }, { brand: "Brave" }] } },
    console: { log() {}, warn() {}, error() {}, debug() {} },
  });
  vm.runInContext(fs.readFileSync(sourcePath, "utf8"), context);

  const tick = (ms) => new Promise((r) => setTimeout(r, ms === undefined ? 30 : ms));
  const senderFor = (tab) => {
    const t = Object.assign({ id: 1, windowId: 1, active: true, url: "https://www.linkedin.com/feed/" }, tab || {});
    return { tab: t, id: "self", url: t.url, frameId: 0, documentId: "doc-" + t.id };
  };
  const relay = (path, body, tab) => new Promise((resolve) => {
    for (const fn of listeners.message) fn({ action: "STUDIO_API", path, body }, senderFor(tab), resolve);
  });
  const fromTab = (message, tab) => new Promise((resolve) => {
    for (const fn of listeners.message) fn(message, senderFor(tab), resolve);
  });
  const fire = (bucket, ...args) => { for (const fn of listeners[bucket]) fn(...args); };
  return {
    chrome, storage, session, listeners, badge, sent, recipes, alarms, executed, tabs, diskManifest,
    registered, unregistered,
    tick, relay, fromTab, fire, senderFor,
    get reloads() { return reloads; },
    get maxInFlight() { return maxInFlight; },
  };
}

module.exports = { boot };
