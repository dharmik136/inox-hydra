"""
Review of PLATFORM-04: the way back in works for every creator.
==============================================================

Analytics are kept only for the LinkedIn account confirmed in Setup, and the
bridge learns which account is signed in from the creator's own profile. The
review found two ways that recovery locked creators out:

  a. On a non-English LinkedIn, opening your own profile from a link taught
     the bridge nothing: the owner check matched English control labels only
     ("Edit intro"), not "Profil bearbeiten". The owner's own edit links are
     now evidence whatever the language, the /in/me/ address keeps working,
     and the refusal names https://www.linkedin.com/in/me/ as the sure way.
  b. Any write of the li_at cookie, even of the same value when LinkedIn
     refreshes it, made the bridge forget the account. It now forgets only
     when the cookie is removed or its value changes.
"""

import json
import os
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

import app as app_module

from qc_f3_pages import EXT, Pages, page_html

client = TestClient(app_module.app)
SCRIPTS = ("voyager_schema.js", "content.js", "own_pages.js")
REMEMBERED = "() => window.__storage.signedInVanity || null"


def profile(vanity="test-creator", name="Test Creator", controls=""):
    return page_html(f"""<main><section aria-label="Primary content"><section>
      <h2>{name}</h2><div>Gründer bei Local-First Labs</div><div>Berlin</div>
      <a href="/in/{vanity}/overlay/contact-info/">Kontaktinfo</a>{controls}
    </section></section></main>""", title=f"{name} | LinkedIn", lang="de")


GERMAN_OWNER = '<a href="/in/test-creator/edit/intro/" aria-label="Profil bearbeiten"><svg></svg></a>'


@pytest.fixture(scope="module")
def pages():
    p = Pages()
    yield p
    p.close()


def test_a_german_own_profile_opened_from_a_link_teaches_the_account(pages):
    page = pages.open("/in/test-creator/", profile(controls=GERMAN_OWNER), scripts=SCRIPTS, me=None)
    page.clock.run_for(4000)
    assert page.evaluate(REMEMBERED) == "test-creator"


def test_a_german_own_profile_with_its_private_analytics_teaches_the_account(pages):
    # Only the owner is shown their profile views and dashboard, whatever the
    # language, even where the edit control is a button with a German label.
    controls = ('<button aria-label="Profil bearbeiten"></button>'
                '<a href="https://www.linkedin.com/me/profile-views/">42 Profilbesuche</a>')
    page = pages.open("/in/test-creator/", profile(controls=controls), scripts=SCRIPTS, me=None)
    page.clock.run_for(4000)
    assert page.evaluate(REMEMBERED) == "test-creator"


def test_a_german_own_profile_reached_through_in_me_teaches_the_account(pages):
    page = pages.open("/in/me/", profile(), scripts=SCRIPTS, me=None)
    page.clock.run_for(3000)
    page.evaluate("() => history.pushState({}, '', '/in/test-creator/')")
    page.clock.run_for(5000)
    assert page.evaluate(REMEMBERED) == "test-creator"


def test_an_edit_link_to_another_profile_teaches_nothing(pages):
    # A stranger's page that happens to link to your own edit form (from the
    # navigation, say) is still the stranger's.
    page = pages.open("/in/stranger-author/", profile("stranger-author", "Stranger Author", GERMAN_OWNER),
                      scripts=SCRIPTS, me=None)
    page.clock.run_for(4000)
    assert page.evaluate(REMEMBERED) is None


def test_the_refusal_names_the_address_that_always_works(confirmed_creator):
    response = client.post("/api/analytics/ingest", json={
        "period_label": "1d", "series": [{"date": "2031-06-07", "period_label": "1d", "impressions": 5}]})
    assert response.status_code == 409
    assert "linkedin.com/in/me/" in response.json()["detail"]


WORKER = r"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(process.argv[process.argv.length - 1], "utf8");
const storage = {};
const storageListeners = [];
const cookieListeners = [];
let cookie = { name: "li_at", value: "AQEDAAAA", domain: ".www.linkedin.com" };
const event = () => ({ addListener: () => {} });
const changed = (changes) => { for (const fn of storageListeners) fn(changes, "local"); };
const chrome = {
  runtime: { id: "self", onInstalled: event(), onStartup: event(), onMessage: event(),
             getManifest: () => ({ version: "test" }), getURL: (p) => "chrome-extension://self/" + p },
  storage: { local: {
      get: (k, cb) => { const out = {}; for (const key of [].concat(k)) if (key in storage) out[key] = storage[key]; cb(out); },
      set: (items, cb) => { const c = {}; for (const key in items) { c[key] = { oldValue: storage[key], newValue: items[key] }; storage[key] = items[key]; } changed(c); if (cb) cb(); },
      remove: (k, cb) => { const c = {}; for (const key of [].concat(k)) { c[key] = { oldValue: storage[key] }; delete storage[key]; } changed(c); if (cb) cb(); } },
    onChanged: { addListener: (fn) => storageListeners.push(fn) } },
  scripting: { getRegisteredContentScripts: async () => [], registerContentScripts: async () => {}, unregisterContentScripts: async () => {} },
  alarms: { clear: () => {} },
  cookies: { get: (q, cb) => cb(q.name === "li_at" && cookie ? cookie : null),
             onChanged: { addListener: (fn) => cookieListeners.push(fn) } },
  sidePanel: { open: async () => {} },
  webRequest: { onCompleted: { addListener: () => {} } },
};
vm.runInContext(source, vm.createContext({ chrome, fetch: async () => ({}), console: { log() {}, warn() {}, error() {}, debug() {} },
  URL, setTimeout, crypto: globalThis.crypto, TextEncoder }));
const tick = () => new Promise((r) => setTimeout(r, 30));
const write = async (value) => {
  for (const fn of cookieListeners) fn({ removed: true, cause: "overwrite", cookie });
  cookie = { name: "li_at", value, domain: ".www.linkedin.com" };
  for (const fn of cookieListeners) fn({ removed: false, cause: "explicit", cookie });
  await tick();
};
(async () => {
  const out = {};
  chrome.storage.local.set({ signedInVanity: "test-creator" });   // own_pages.js learns it
  await tick();
  out.storesNoCookie = JSON.stringify(storage).includes("AQEDAAAA");
  await write("AQEDAAAA");
  out.afterSameValue = storage.signedInVanity || null;
  await write("AQEDBBBB");
  out.afterNewValue = storage.signedInVanity || null;
  chrome.storage.local.set({ signedInVanity: "test-creator" });
  await tick();
  for (const fn of cookieListeners) fn({ removed: true, cause: "explicit", cookie });
  cookie = null;
  await tick();
  out.afterSignOut = storage.signedInVanity || null;
  process.stdout.write(JSON.stringify(out));
})();
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required to run the worker")
def test_a_refreshed_sign_in_cookie_keeps_the_account_and_a_new_one_forgets_it():
    result = subprocess.run([shutil.which("node"), "-e", WORKER, os.path.join(EXT, "background.js")],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["storesNoCookie"] is False, "the sign-in cookie itself must not be stored"
    assert out["afterSameValue"] == "test-creator"
    assert out["afterNewValue"] is None
    assert out["afterSignOut"] is None
