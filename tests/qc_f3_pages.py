"""
The bridge's page scripts, run on fixture LinkedIn pages in a real browser.
==========================================================================

A helper for the tests named test_qc_f3_*. content.js and own_pages.js read
LinkedIn's DOM, so what they send depends on layout, innerText and event
order, which a source assertion cannot see. These load the shipped scripts
into Playwright's own headless Chromium, on a page served from a fixture under
https://www.linkedin.com/..., with a fake `chrome` object that records every
message the scripts send to the worker and answers it as the test says.

Nothing leaves the machine: every request is answered from the fixture or
aborted inside the browser, and the host resolver maps every name to nothing.
The page clock is installed, so the scripts' debounces run instantly.
"""

import json
import os

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXT = os.path.join(REPO_ROOT, "studio", "extension")

# The worker, as far as a content script can tell. Messages are recorded in
# window.__sent; window.__answer(message) decides the reply, and a test can
# replace it. "unreachable" answers as the worker does when the studio is not
# running: no httpStatus at all.
FAKE_CHROME = r"""
(() => {
  const sent = [];
  const storage = Object.assign({}, window.__initialStorage || {});
  const sessionStore = Object.assign({}, window.__initialSession || {});
  const changed = [];
  window.__sent = sent;
  window.__storage = storage;
  window.__session = sessionStore;
  // One storage area, as chrome.storage has them: local, and session (which
  // the browser empties when it closes). Changes reach every listener with
  // the area's name.
  const area = (store, name) => ({
    get: (key, callback) => {
      const out = {};
      const keys = key === null || key === undefined ? Object.keys(store) : [].concat(key);
      for (const k of keys) if (k in store) out[k] = store[k];
      setTimeout(() => callback(out), 0);
    },
    set: (items, callback) => {
      const changes = {};
      for (const k of Object.keys(items)) { changes[k] = { oldValue: store[k], newValue: items[k] }; store[k] = items[k]; }
      for (const fn of changed) fn(changes, name);
      if (callback) setTimeout(callback, 0);
    },
    remove: (keys, callback) => {
      const changes = {};
      for (const k of [].concat(keys)) { changes[k] = { oldValue: store[k], newValue: undefined }; delete store[k]; }
      for (const fn of changed) fn(changes, name);
      if (callback) setTimeout(callback, 0);
    },
  });
  window.__me = window.__me === undefined ? "test-creator" : window.__me;
  window.__answers = {};
  window.__answer = (message) => {
    const path = message.path || "";
    if (Object.prototype.hasOwnProperty.call(window.__answers, path)) {
      const answer = window.__answers[path];
      if (answer === "unreachable") return { status: "error", error: "Failed to fetch" };
      if (answer && answer.httpStatus && answer.httpStatus >= 400) {
        return { status: "error", httpStatus: answer.httpStatus, data: answer.data || {} };
      }
      return { status: "success", httpStatus: 200, data: answer };
    }
    if (path === "/api/v1/identity/me") return { status: "success", httpStatus: 200, data: { status: "success", vanity: window.__me } };
    if (path === "/api/v1/self/imports/pending") return { status: "success", httpStatus: 200, data: { status: "success", request: null } };
    return { status: "success", httpStatus: 200, data: { status: "success", buckets_ingested: 1 } };
  };
  const listeners = [];
  window.__messageListeners = listeners;
  const chromeApi = {
    runtime: {
      id: "test-extension",
      lastError: undefined,
      getManifest: () => ({ version: "test" }),
      getURL: (p) => "chrome-extension://test-extension/" + p,
      sendMessage: (message, callback) => {
        sent.push(JSON.parse(JSON.stringify(message)));
        const answer = window.__answer(message);
        setTimeout(() => { if (callback) callback(answer); }, 0);
      },
      onMessage: { addListener: (fn) => listeners.push(fn) },
    },
    storage: {
      local: area(storage, "local"),
      session: area(sessionStore, "session"),
      onChanged: { addListener: (fn) => changed.push(fn) },
    },
  };
  Object.defineProperty(window, "chrome", { value: chromeApi, configurable: true, writable: true });
})();
"""


def page_html(body, title="LinkedIn", lang=None):
    lang_attr = f" lang='{lang}'" if lang else ""
    return (f"<!doctype html><html{lang_attr}><head><meta charset='utf-8'><title>{title}</title></head>"
            f"<body>{body}</body></html>")


class Pages:
    """One headless Chromium for a test module; one context per page."""

    def __init__(self):
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(
            headless=True,
            args=["--host-resolver-rules=MAP * ~NOTFOUND", "--disable-background-networking"],
        )
        self.blocked = []

    def open(self, path, html, scripts=("voyager_schema.js", "content.js"), me="test-creator",
             storage=None, before=None, session=None):
        """
        Serves `html` at https://www.linkedin.com<path>, installs the fake
        chrome and the page clock, then loads the named extension scripts in
        the order the manifest does.
        """
        context = self.browser.new_context(service_workers="block")

        def route(r):
            url = r.request.url
            if url.split("?")[0] == "https://www.linkedin.com" + path.split("?")[0]:
                return r.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
            self.blocked.append(url)
            return r.abort()

        context.route("**/*", route)
        context.add_init_script(
            f"window.__me = {json.dumps(me)}; window.__initialStorage = {json.dumps(storage or {})};"
            f" window.__initialSession = {json.dumps(session or {})};"
        )
        context.add_init_script(FAKE_CHROME)
        page = context.new_page()
        page.clock.install()
        page.goto("https://www.linkedin.com" + path, wait_until="load")
        if before:
            page.evaluate(before)
        for name in scripts:
            page.add_script_tag(path=os.path.join(EXT, name))
        return page

    def sent(self, page, path=None):
        messages = page.evaluate("() => window.__sent")
        if path is None:
            return messages
        return [m["body"] for m in messages if m.get("path") == path]

    def close(self):
        self.browser.close()
        self._pw.stop()


def toast_text(page):
    return page.evaluate(
        "() => { const t = document.getElementById('studio-bridge-inpage-toast'); return t ? t.innerText.replace(/\\s+/g, ' ').trim() : null; }"
    )
