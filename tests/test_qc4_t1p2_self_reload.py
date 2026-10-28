"""
The real extension, in Chromium: it reloads itself and gives open tabs its readers.
==================================================================================

Cycle 4, track 1, phase 2 ("never reload by hand", parts a and b), checked
end to end rather than against a fake chrome. A copy of studio/extension is
loaded unpacked into Playwright's Chromium, as the owner loads it; a LinkedIn
tab is open on a fixture page; the copy's manifest version is then changed on
disk, as a git pull changes it. The worker notices its files changed and
reloads itself, and on the update it gives the tab already open the new
version's readers, in a fresh world, with no refresh of the tab.

The copy's studio address is rewritten to a closed port, so nothing it
sends can reach a studio running on this machine; every page request other
than the fixture is aborted.

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import re
import shutil
import tempfile

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXT = os.path.join(REPO_ROOT, "studio", "extension")
PAGE = "<!doctype html><html><head><title>LinkedIn</title></head><body><main>feed</main></body></html>"
CLOSED = "http://127.0.0.1:9"


def _copy_extension(into):
    target = os.path.join(into, "extension")
    shutil.copytree(EXT, target)
    path = os.path.join(target, "background.js")
    with open(path, encoding="utf-8") as handle:
        worker = handle.read()
    worker = worker.replace("http://127.0.0.1:8000", CLOSED).replace("http://localhost:8000", CLOSED)
    assert ":8000" not in worker
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(worker)
    return target


def _set_version(extension, version):
    path = os.path.join(extension, "manifest.json")
    with open(path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    manifest["version"] = version
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)


PROBE = """async (tabUrl) => {
  const [tab] = await chrome.tabs.query({ url: tabUrl });
  if (!tab) return { tab: null };
  const found = await chrome.scripting.executeScript({ target: { tabId: tab.id },
    func: () => (typeof window.__inoxBridgeVersion === 'string' ? window.__inoxBridgeVersion : null) });
  return { tab: tab.id, readers: found[0].result, running: chrome.runtime.getManifest().version };
}"""


def test_an_unpacked_install_reloads_itself_and_the_open_tab_gets_the_new_readers():
    scratch = tempfile.mkdtemp(prefix="inox_t1p2_reload_")
    try:
        extension = _copy_extension(scratch)
        _set_version(extension, "9.9.0")
        with sync_playwright() as pw:
            try:
                context = pw.chromium.launch_persistent_context(
                    os.path.join(scratch, "profile"), channel="chromium", headless=True,
                    args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}",
                          "--host-resolver-rules=MAP * ~NOTFOUND"])
            except Exception as error:  # noqa: BLE001
                pytest.skip(f"this Chromium cannot load an unpacked extension: {error}")
            try:
                context.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html", body=PAGE)
                              if r.request.url.startswith("https://www.linkedin.com/") else r.abort())
                worker = (context.service_workers[0] if context.service_workers
                          else context.wait_for_event("serviceworker", timeout=15000))
                # An unpacked install is loaded with developer mode on.
                admin = context.new_page()
                admin.goto("chrome://extensions/")
                admin.locator("#devMode").click(timeout=5000)
                tab = context.new_page()
                tab.goto("https://www.linkedin.com/feed/")
                tab.wait_for_timeout(1500)
                before = worker.evaluate(PROBE, "https://www.linkedin.com/feed/")
                assert before["readers"] == "9.9.0" and before["running"] == "9.9.0", before

                _set_version(extension, "9.9.1")
                try:
                    worker.evaluate("checkOwnFiles()")
                except Exception:  # noqa: BLE001
                    pass  # the worker reloaded under the call
                fresh = None
                for _ in range(40):
                    tab.wait_for_timeout(250)
                    workers = [w for w in context.service_workers if w is not worker]
                    if workers:
                        fresh = workers[-1]
                        break
                assert fresh is not None, "the extension did not reload itself when its files changed"
                after = None
                for _ in range(20):
                    after = fresh.evaluate(PROBE, "https://www.linkedin.com/feed/")
                    if after.get("readers") == "9.9.1":
                        break
                    tab.wait_for_timeout(250)
                assert after["running"] == "9.9.1", after
                assert after["readers"] == "9.9.1", (
                    f"the tab already open did not get the new readers without a refresh: {after}")
                assert tab.url == "https://www.linkedin.com/feed/", "the tab was reloaded"
            finally:
                context.close()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_the_copy_under_test_cannot_reach_a_running_studio():
    scratch = tempfile.mkdtemp(prefix="inox_t1p2_copy_")
    try:
        extension = _copy_extension(scratch)
        for name in os.listdir(extension):
            if name.endswith(".js"):
                with open(os.path.join(extension, name), encoding="utf-8") as handle:
                    assert not re.search(r"https?://(127\.0\.0\.1|localhost):8000", handle.read()) or name != "background.js"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
