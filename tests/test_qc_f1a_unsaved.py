"""
Unsaved work: one registry every screen can join
================================================
The unsaved check held one function, so only the Composer could ever be
asked about, and nothing asked at all when the page reloaded or closed.
studio/ui/src/lib/unsaved.ts is now a registry: any screen registers what it
would lose, and the page guard, App's navigation and the profile switch read
it. This executes the compiled module in node with a stand-in window, so the
contract a second screen (Brand Studio) relies on is pinned. The browser half
is in tests/test_qc_f1a_composer.py.
"""

import json
import os
import shutil
import subprocess
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODULE = os.path.join(REPO_ROOT, "studio", "ui", "src", "lib", "unsaved.ts")
UI_DIR = os.path.join(REPO_ROOT, "studio", "ui")

NODE = shutil.which("node") or shutil.which("node.exe")
ESBUILD = next(
    (
        os.path.join(UI_DIR, "node_modules", ".bin", name)
        for name in ("esbuild.cmd", "esbuild")
        if os.path.exists(os.path.join(UI_DIR, "node_modules", ".bin", name))
    ),
    None,
)

PROBE = """
const listeners = {};
const asked = [];
let answer = true;
globalThis.window = {
  addEventListener: (name, fn) => { (listeners[name] ||= []).push(fn); },
  confirm: (message) => { asked.push(message); return answer; },
};
const m = await import("./unsaved.js");
const out = {};
let composer = false, brand = false;
const offComposer = m.registerUnsavedWork("composer", { label: "The post in the Composer", check: () => composer });
const offBrand = m.registerUnsavedWork("brand", { label: "Your Brand Studio edits", section: "settings", check: () => brand });

const unload = () => { const e = { prevented: false, returnValue: undefined, preventDefault() { this.prevented = true; } };
                       for (const fn of listeners.beforeunload || []) fn(e); return e.prevented; };
out.listeners = (listeners.beforeunload || []).length;
out.cleanUnload = unload();
out.cleanLeave = m.confirmLeaving("settings");
composer = true;
out.composerOnly = { any: m.hasUnsavedWork(), labels: m.unsavedWorkLabels(), leavingComposer: m.unsavedWorkLeaving("composer"),
                     leavingSettings: m.unsavedWorkLeaving("settings"), unload: unload() };
brand = true;
answer = false;
out.both = { labels: m.unsavedWorkLabels(), leavingSettings: m.unsavedWorkLeaving("settings"),
             go: m.confirmLeaving("settings"), asked: asked.slice() };
offBrand();
out.afterUnregister = { labels: m.unsavedWorkLabels(), go: m.confirmLeaving("settings") };
offComposer();
out.none = { any: m.hasUnsavedWork(), unload: unload() };

// A reload the author already agreed to, such as a confirmed profile switch.
let reloaded = false;
globalThis.window.location = { reload: () => { reloaded = true; } };
m.registerUnsavedWork("composer", { label: "The post in the Composer", check: () => true });
out.agreedReload = { before: unload(), reloaded: (m.reloadStudio(), reloaded), after: unload() };
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def results():
    if not NODE:
        pytest.skip("Node is not installed, cannot execute the unsaved-work module")
    if not ESBUILD:
        pytest.skip("studio/ui dependencies are not installed, cannot compile TypeScript")
    with tempfile.TemporaryDirectory() as work:
        compiled = os.path.join(work, "unsaved.js")
        build = subprocess.run([ESBUILD, MODULE, "--format=esm", f"--outfile={compiled}"],
                               capture_output=True, text=True, encoding="utf-8")
        assert build.returncode == 0, f"esbuild failed: {build.stderr}"
        probe = os.path.join(work, "probe.mjs")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write(PROBE)
        run = subprocess.run([NODE, probe], capture_output=True, text=True, encoding="utf-8", cwd=work)
        assert run.returncode == 0, f"probe failed: {run.stderr}"
        return json.loads(run.stdout)


def test_the_page_asks_before_unloading_only_while_something_is_unsaved(results):
    assert results["listeners"] == 1, "registering two screens added two page guards"
    assert results["cleanUnload"] is False
    assert results["composerOnly"]["unload"] is True
    assert results["none"]["unload"] is False


def test_composer_text_survives_moving_between_screens_so_leaving_does_not_ask(results):
    only = results["composerOnly"]
    assert only["any"] is True
    assert only["labels"] == ["The post in the Composer"]
    assert only["leavingComposer"] == [], "the Composer's draft lives in App and is not lost by navigating"
    assert only["leavingSettings"] == []


def test_a_second_screen_registers_and_is_asked_about_by_name(results):
    both = results["both"]
    assert both["labels"] == ["The post in the Composer", "Your Brand Studio edits"]
    assert both["leavingSettings"] == ["Your Brand Studio edits"]
    assert both["go"] is False, "answering Cancel did not keep the author on the screen"
    assert both["asked"] and "Your Brand Studio edits has unsaved changes" in both["asked"][0]
    assert results["cleanLeave"] is True


def test_a_reload_already_agreed_to_is_not_asked_about_twice(results):
    """Confirming a profile switch, then being asked again by the page, could leave the two out of step."""
    assert results["agreedReload"] == {"before": True, "reloaded": True, "after": False}


def test_unregistering_removes_the_screen(results):
    assert results["afterUnregister"] == {"labels": ["The post in the Composer"], "go": True}
    assert results["none"]["any"] is False
