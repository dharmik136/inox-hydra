"""
Network reading keeps the readings it exists for on a busy page.
================================================================

BRIDGE-16  The interceptor counted every one of LinkedIn's data responses
           (messaging, notifications, the feed) against its 30 per minute cap
           before checking whether it was one the bridge reads. On a busy page
           the creator analytics response was dropped without a trace, and the
           exact figures the creator switched network reading on for never
           arrived. Responses the bridge does not read are now ignored before
           the cap, and are not copied at all.

This runs the shipped voyager_interceptor.js under node with a fake fetch.
"""

import json
import os
import shutil
import subprocess

import pytest

EXT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "extension"))

HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(process.argv[process.argv.length - 1], "utf8");
const posted = [];
const respond = (url) => Promise.resolve({
  url, status: 200,
  headers: { get: () => null },
  clone() { return { text: async () => JSON.stringify({ elements: [{ followerCount: 4200 }] }) }; },
});
const window = { fetch: (url) => respond(url), location: { origin: "https://www.linkedin.com" },
                 postMessage: (message) => posted.push(message.payload.url) };
vm.runInContext(source, vm.createContext({ window, Proxy, Reflect, Object, URL, JSON, Date, Math, Promise, parseInt }));
(async () => {
  for (let i = 0; i < 40; i++) await window.fetch("https://www.linkedin.com/voyager/api/messaging/conversations?i=" + i);
  for (let i = 0; i < 5; i++) await window.fetch("https://www.linkedin.com/voyager/api/voyagerNotificationsDashBadges?i=" + i);
  await window.fetch("https://www.linkedin.com/voyager/api/identity/dash/creatorAnalytics?q=me");
  await new Promise((r) => setTimeout(r, 50));
  process.stdout.write(JSON.stringify(posted));
})();
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required to run the interceptor")
def test_the_creator_analytics_response_survives_a_busy_page():
    result = subprocess.run([shutil.which("node"), "-e", HARNESS, os.path.join(EXT, "voyager_interceptor.js")],
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    posted = json.loads(result.stdout)
    assert "https://www.linkedin.com/voyager/api/identity/dash/creatorAnalytics" in posted
    # What the bridge does not read is not copied out of LinkedIn's page.
    assert not [url for url in posted if "messaging" in url or "Notifications" in url]


def test_the_interceptor_reads_what_the_schema_registry_reads():
    with open(os.path.join(EXT, "voyager_interceptor.js"), encoding="utf-8") as handle:
        interceptor = handle.read()
    with open(os.path.join(EXT, "voyager_schema.js"), encoding="utf-8") as handle:
        schema = handle.read()
    for endpoint in ("feed\\/updatesV2", "identity\\/dash\\/creatorAnalytics", "socialActions", "feed\\/comments"):
        assert endpoint in schema
        assert endpoint in interceptor, f"the interceptor no longer lets {endpoint} through"
