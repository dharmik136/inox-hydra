"""
The bridge learns the signed-in member's URN, and sends it with the session.
===========================================================================

BE-09: Send to LinkedIn named a placeholder author because nothing ever
learnt the creator's member URN. LinkedIn renders each page with the data
behind it in hidden <code> blocks (normalised Voyager responses, HTML-escaped
in the markup): the profile shown carries its "publicIdentifier" (the vanity)
beside its "entityUrn", urn:li:fsd_profile:<id>, and the signed-in member's own
entry from /voyager/api/me carries the same id as "dashEntityUrn".

own_pages.js already reads the creator's own profile to note which account is
signed in (signedInVanity). It now reads the URN from those blocks there too,
matched on the vanity, and background.js sends both with the session when the
creator presses Sync. These run the shipped scripts on fixture pages and a
fake worker; nothing is fetched.
"""

import html
import json
import os
import shutil
import subprocess

import pytest

from qc_f3_pages import Pages, page_html

EXT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "extension"))

OWN = "urn:li:fsd_profile:ACoAABcDeFgHiJkLmN0pQ"
STRANGER = "urn:li:fsd_profile:ACoAAStrangerId00001"


def _code(payload):
    return f'<code style="display: none" id="bpr-guid-{abs(hash(json.dumps(payload))) % 99999}">{html.escape(json.dumps(payload))}</code>'


# The /voyager/api/me datalet LinkedIn puts on every page, and the profile's
# own response. The page also carries someone else (a "People also viewed").
ME_BLOCK = {"data": {"plainId": 123456789, "*miniProfile": "urn:li:fs_miniProfile:ACoAABcDeFgHiJkLmN0pQ"},
            "included": [{"$type": "com.linkedin.voyager.identity.shared.MiniProfile",
                          "entityUrn": "urn:li:fs_miniProfile:ACoAABcDeFgHiJkLmN0pQ",
                          "dashEntityUrn": OWN, "publicIdentifier": "test-creator"}]}
PROFILE_BLOCK = {"data": {"*elements": [OWN]},
                 "included": [{"$type": "com.linkedin.voyager.dash.identity.profile.Profile", "entityUrn": STRANGER,
                               "publicIdentifier": "stranger-author", "firstName": "Stranger"},
                              {"$type": "com.linkedin.voyager.dash.identity.profile.Profile", "entityUrn": OWN,
                               "publicIdentifier": "test-creator", "firstName": "Test"}]}

PROFILE = """
<main><section aria-label="Primary content"><section>
  <h2>Test Creator</h2><div>Founder at Local-First Labs</div><div>Berlin</div>
  <a href="/in/test-creator/overlay/contact-info/">Contact info</a>
  <button aria-label="Edit intro">Edit</button>
</section></section></main>
"""


@pytest.fixture(scope="module")
def pages():
    p = Pages()
    yield p
    p.close()


def _open_profile(pages, body, vanity="test-creator", storage=None):
    page = pages.open(f"/in/{vanity}/", page_html(body, title="Test Creator | LinkedIn"),
                      scripts=("voyager_schema.js", "content.js", "own_pages.js"), storage=storage)
    page.clock.run_for(4000)
    return page


def test_your_own_profile_teaches_the_bridge_your_member_urn(pages):
    page = _open_profile(pages, PROFILE + _code(PROFILE_BLOCK))
    member = page.evaluate("() => window.__storage.signedInMemberUrn")
    assert member == {"vanity": "test-creator", "urn": OWN}, member


def test_the_me_block_alone_is_enough(pages):
    page = _open_profile(pages, PROFILE + _code(ME_BLOCK))
    assert page.evaluate("() => window.__storage.signedInMemberUrn") == {"vanity": "test-creator", "urn": OWN}


def test_a_page_without_the_data_teaches_no_urn_and_keeps_the_vanity(pages):
    page = _open_profile(pages, PROFILE)
    assert page.evaluate("() => window.__storage.signedInVanity") == "test-creator"
    assert page.evaluate("() => window.__storage.signedInMemberUrn || null") is None


def test_a_strangers_profile_teaches_no_urn(pages):
    stranger = PROFILE.replace("Test Creator", "Stranger Author").replace("test-creator", "stranger-author") \
        .replace('<button aria-label="Edit intro">Edit</button>', "<button>Connect</button><button>Message</button>")
    page = _open_profile(pages, stranger + _code(PROFILE_BLOCK), vanity="stranger-author",
                         storage={"signedInVanity": "test-creator"})
    assert page.evaluate("() => window.__storage.signedInMemberUrn || null") is None


WORKER = r"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(process.argv[process.argv.length - 1], "utf8");
const storage = JSON.parse(process.env.R6_STORAGE);
const listeners = [];
const event = () => ({ addListener: () => {} });
const sent = [];
const chrome = {
  runtime: { id: "self", onInstalled: event(), onStartup: event(), onMessage: { addListener: (fn) => listeners.push(fn) },
             getManifest: () => ({ version: "test" }), getURL: (p) => "chrome-extension://self/" + p },
  storage: { local: { get: (k, cb) => { const out = {}; for (const key of [].concat(k)) if (key in storage) out[key] = storage[key]; cb(out); },
                      set: (items, cb) => { Object.assign(storage, items); if (cb) cb(); },
                      remove: (k, cb) => { for (const key of [].concat(k)) delete storage[key]; if (cb) cb(); } },
             onChanged: event() },
  scripting: { getRegisteredContentScripts: async () => [], registerContentScripts: async () => {}, unregisterContentScripts: async () => {} },
  alarms: { clear: () => {}, create: () => {}, onAlarm: { addListener: () => {} } },
  cookies: { get: (q, cb) => cb({ value: q.name === "li_at" ? "AQEDAlive" : "ajax:1" }), onChanged: { addListener: () => {} } },
  sidePanel: { open: async () => {} },
  webRequest: { onCompleted: { addListener: () => {} } },
};
const fakeFetch = async (url, opts) => {
  sent.push({ url: String(url), body: opts && opts.body ? JSON.parse(opts.body) : null });
  return { ok: true, status: 200, json: async () => ({ status: "success", token: "t" }), text: async () => "" };
};
vm.runInContext(source, vm.createContext({ chrome, fetch: fakeFetch, console: { log() {}, warn() {}, error() {}, debug() {} },
  URL, setTimeout, clearTimeout, TextEncoder, crypto: require("crypto").webcrypto }));
const sender = { id: "self" };
const reply = new Promise((resolve) => {
  for (const fn of listeners) fn({ action: process.env.R6_ACTION }, sender, resolve);
});
Promise.race([reply, new Promise((r) => setTimeout(() => r("no reply"), 3000))]).then((answer) => {
  const cookies = sent.filter((s) => s.url.includes("/api/auth/cookies"));
  process.stdout.write(JSON.stringify({ answer, cookies: cookies.map((c) => c.body) }));
});
"""


def _run_worker(storage):
    node = shutil.which("node")
    env = dict(os.environ, R6_STORAGE=json.dumps(storage), R6_ACTION="SYNC_NOW")
    result = subprocess.run([node, "-e", WORKER, os.path.join(EXT, "background.js")], capture_output=True,
                            text=True, encoding="utf-8", timeout=30, env=env)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required to run the worker")
def test_sync_sends_the_account_and_its_urn_with_the_session():
    out = _run_worker({"signedInVanity": "test-creator", "signedInMemberUrn": {"vanity": "test-creator", "urn": OWN}})
    assert out["cookies"], out
    body = out["cookies"][-1]
    assert body["vanity"] == "test-creator"
    assert body["member_urn"] == OWN


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required to run the worker")
def test_a_urn_learnt_for_another_account_is_not_sent():
    out = _run_worker({"signedInVanity": "test-creator", "signedInMemberUrn": {"vanity": "someone-else", "urn": STRANGER}})
    body = out["cookies"][-1]
    assert body["vanity"] == "test-creator"
    assert body["member_urn"] is None
    assert "Open your own LinkedIn profile" in json.dumps(out["answer"])
