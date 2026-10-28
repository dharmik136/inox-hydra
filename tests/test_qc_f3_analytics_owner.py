"""
Analytics name the LinkedIn account they came from.
===================================================

PLATFORM-04 / BRIDGE-23  Follower counts from LinkedIn's network responses,
    and the analytics page's figures, were filed under whichever creator
    profile was open in the studio, whoever was signed in to LinkedIn. An
    agency user signed in as themselves with client B's profile open wrote
    their own follower count into B's analytics, as measured fact, and a
    profile that had confirmed no identity at all took them too.

Now the bridge sends the signed-in account with every analytics reading, and
the studio refuses a reading that names another account, or none, or arrives
before the profile has confirmed who it is. The bridge learns the signed-in
account only from LinkedIn itself (the creator's own profile, shown with its
owner's controls or reached through /in/me/) and forgets it when the
browser's LinkedIn sign-in changes.

The follower counts from network reading went with it in 2.10.2, when
network reading was retired; a network reading an older extension still
sends now keeps nothing for any account (tests/test_network_reading_retired.py).
"""

import json
import os
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

import app as app_module
from database import get_db

from qc_f3_pages import Pages, page_html

client = TestClient(app_module.app)
DAY = "2031-05-06"
EXT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "extension"))


@pytest.fixture(autouse=True)
def isolated_rows():
    conn = get_db()
    with conn:
        saved = [dict(r) for r in conn.execute("SELECT * FROM analytics_daily")]
        conn.execute("DELETE FROM analytics_daily")
    conn.close()
    yield
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM analytics_daily")
        for row in saved:
            columns = ", ".join(row)
            conn.execute(f"INSERT INTO analytics_daily ({columns}) VALUES ({', '.join('?' for _ in row)})",
                         tuple(row.values()))
    conn.close()


@pytest.fixture
def no_identity():
    conn = get_db()
    with conn:
        saved = [dict(r) for r in conn.execute("SELECT * FROM creator_identity")]
        conn.execute("DELETE FROM creator_identity")
    conn.close()
    yield
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM creator_identity")
        for row in saved:
            columns = ", ".join(row)
            conn.execute(f"INSERT INTO creator_identity ({columns}) VALUES ({', '.join('?' for _ in row)})",
                         tuple(row.values()))
    conn.close()


def _rows():
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute("SELECT date, followers, impressions FROM analytics_daily")]
    finally:
        conn.close()


def _page_reading(author):
    body = {"period_label": "1d", "precision": "exact",
            "series": [{"date": DAY, "period_label": "1d", "precision": "exact", "impressions": 512, "followers": 3105}]}
    if author is not None:
        body["author"] = author
    return client.post("/api/analytics/ingest", json=body)


def test_page_analytics_from_another_account_are_refused(confirmed_creator):
    response = _page_reading("someone-else")
    assert response.status_code == 409
    assert "someone-else" in response.json()["detail"]
    assert _rows() == []


def test_page_analytics_that_name_no_account_are_refused(confirmed_creator):
    response = _page_reading(None)
    assert response.status_code == 409
    assert "profile" in response.json()["detail"]
    assert _rows() == []


def test_page_analytics_before_any_identity_is_confirmed_are_refused(no_identity):
    response = _page_reading("studio-test-creator")
    assert response.status_code == 409
    assert "Setup" in response.json()["detail"]
    assert _rows() == []


def test_page_analytics_from_the_confirmed_account_are_kept(confirmed_creator):
    response = _page_reading(confirmed_creator.upper())
    assert response.status_code == 200, response.text
    assert response.json()["buckets_ingested"] == 1
    assert _rows() == [{"date": DAY, "followers": 3105, "impressions": 512}]


def test_a_network_follower_count_is_kept_for_no_account_since_it_was_retired(confirmed_creator):
    """Even from the confirmed account: network reading was retired in 2.10.2."""
    response = client.post("/api/v1/bridge/voyager-ingest", json={
        "schema_name": "creator_analytics", "data": [{"followers": 98765}], "vanity": confirmed_creator})
    assert response.status_code == 200 and response.json()["status"] == "retired", response.text
    assert _rows() == []


# ---------------------------------------------------------------------------
# The bridge's half
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pages():
    p = Pages()
    yield p
    p.close()


ANALYTICS = page_html(
    "<main><button class='artdeco-dropdown__trigger'>Past 24 hours</button>"
    "<div data-test-metric-card><span data-test-metric-value>412</span> <span>Impressions</span></div></main>",
    title="Analytics | LinkedIn", lang="en")


def test_the_analytics_page_names_the_signed_in_account(pages):
    page = pages.open("/analytics/creator/content/", ANALYTICS, storage={"signedInVanity": "test-creator"})
    page.clock.run_for(5000)
    sent = pages.sent(page, "/api/analytics/ingest")
    assert sent and sent[-1]["author"] == "test-creator"


PROFILE = """
<main><section aria-label="Primary content"><section>
  <h2>Test Creator</h2><div>Founder at Local-First Labs</div><div>Berlin</div>
  <a href="/in/test-creator/overlay/contact-info/">Contact info</a>
  <button aria-label="Edit intro">Edit</button>
</section></section></main>
"""


def test_your_own_profile_teaches_the_bridge_which_account_is_signed_in(pages):
    page = pages.open("/in/test-creator/", page_html(PROFILE, title="Test Creator | LinkedIn"),
                      scripts=("content.js", "own_pages.js"))
    page.clock.run_for(4000)
    assert page.evaluate("() => window.__storage.signedInVanity") == "test-creator"


def test_a_strangers_profile_teaches_it_nothing(pages):
    stranger = PROFILE.replace("Test Creator", "Stranger Author").replace("test-creator", "stranger-author") \
        .replace('<button aria-label="Edit intro">Edit</button>', "<button>Connect</button><button>Message</button>")
    page = pages.open("/in/stranger-author/", page_html(stranger, title="Stranger Author | LinkedIn"),
                      scripts=("content.js", "own_pages.js"),
                      storage={"signedInVanity": "test-creator"})
    page.clock.run_for(4000)
    assert page.evaluate("() => window.__storage.signedInVanity") == "test-creator"


WORKER = r"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(process.argv[process.argv.length - 1], "utf8");
const storage = { signedInVanity: "test-creator", networkReading: false };
const cookieListeners = [];
const event = () => ({ addListener: () => {} });
const chrome = {
  runtime: { id: "self", onInstalled: event(), onStartup: event(), onMessage: event(),
             getManifest: () => ({ version: "test" }), getURL: (p) => "chrome-extension://self/" + p },
  storage: { local: { get: (k, cb) => cb({ [k]: storage[k] }), remove: (k, cb) => { for (const key of [].concat(k)) delete storage[key]; if (cb) cb(); } },
             onChanged: event() },
  scripting: { getRegisteredContentScripts: async () => [], registerContentScripts: async () => {}, unregisterContentScripts: async () => {} },
  alarms: { clear: () => {}, create: () => {}, onAlarm: { addListener: () => {} } },
  cookies: { get: (_q, cb) => cb(null), onChanged: { addListener: (fn) => cookieListeners.push(fn) } },
  sidePanel: { open: async () => {} },
  webRequest: { onCompleted: { addListener: () => {} } },
};
vm.runInContext(source, vm.createContext({ chrome, fetch: async () => ({}), console: { log() {}, warn() {}, error() {}, debug() {} }, URL, setTimeout }));
const out = {};
for (const fn of cookieListeners) fn({ removed: false, cause: "explicit", cookie: { name: "bcookie", domain: ".linkedin.com" } });
out.afterOtherCookie = storage.signedInVanity || null;
for (const fn of cookieListeners) fn({ removed: true, cause: "explicit", cookie: { name: "li_at", domain: ".www.linkedin.com" } });
out.afterSignOut = storage.signedInVanity || null;
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required to run the worker")
def test_the_signed_in_account_is_forgotten_when_the_linkedin_sign_in_changes():
    result = subprocess.run([shutil.which("node"), "-e", WORKER, os.path.join(EXT, "background.js")],
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["afterOtherCookie"] == "test-creator"
    assert out["afterSignOut"] is None
