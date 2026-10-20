"""
Quality cycle 2026-10, batch F8 [F4b-N1]: the Activity screen's Imports tab
draws each import outcome as what it was.

It coloured only the old "completed" outcome as done, so an import read to the
end ("end_of_list") showed in grey beside a partial one. This executes
importEnding from studio/ui/src/lib/importOutcome.ts, the function the tab
renders with, against every outcome studio/backend/onboarding.py records.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

from studio.backend import onboarding

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI_DIR = os.path.join(REPO_ROOT, "studio", "ui")
MODULE = os.path.join(UI_DIR, "src", "lib", "importOutcome.ts")
SURFACE = os.path.join(UI_DIR, "src", "components", "ActivitySurface.tsx")

NODE = shutil.which("node") or shutil.which("node.exe")
ESBUILD = next(
    (
        os.path.join(UI_DIR, "node_modules", ".bin", name)
        for name in ("esbuild.cmd", "esbuild")
        if os.path.exists(os.path.join(UI_DIR, "node_modules", ".bin", name))
    ),
    None,
)

# Every finished outcome the backend writes: what the extension reports, what
# an older extension sent, and what the studio closes requests with itself.
RECORDED = sorted(set(onboarding.IMPORT_OUTCOMES) | set(onboarding.OLD_EXTENSION_OUTCOMES)
                  | {"nothing_read", "superseded", "expired", "not_opened"})

PROBE = """
import { importEnding } from "./importOutcome.js";
const outcomes = JSON.parse(process.argv[2]);
const out = {};
for (const outcome of outcomes) {
  out[outcome] = importEnding({ outcome, started_at: "2026-10-20 10:00:00", finished_at: "2026-10-20 10:05:00" });
}
out.__running = importEnding({ outcome: "pending", started_at: "2026-10-20 10:00:00", finished_at: null });
out.__waiting = importEnding({ outcome: "pending", started_at: null, finished_at: null });
out.__paused = importEnding({ outcome: "paused_hidden", started_at: "2026-10-20 10:00:00", finished_at: null });
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def endings():
    if not NODE:
        pytest.skip("Node is not installed")
    if not ESBUILD:
        pytest.skip("studio/ui dependencies are not installed, cannot compile TypeScript")
    with tempfile.TemporaryDirectory() as work:
        compiled = os.path.join(work, "importOutcome.js")
        build = subprocess.run([ESBUILD, MODULE, "--format=esm", f"--outfile={compiled}"],
                               capture_output=True, text=True)
        assert build.returncode == 0, build.stderr
        probe = os.path.join(work, "probe.mjs")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write(PROBE)
        run = subprocess.run([NODE, probe, json.dumps(RECORDED)], capture_output=True, text=True, cwd=work)
        assert run.returncode == 0, run.stderr
        return json.loads(run.stdout)


def test_only_an_import_read_to_the_end_is_drawn_as_done(endings):
    assert endings["end_of_list"]["tone"] == "done"
    assert endings["end_of_list"]["label"] == "Read to the end"
    for outcome in RECORDED:
        if outcome != "end_of_list":
            assert endings[outcome]["tone"] != "done", f"{outcome} read part of the list but is drawn as done"


@pytest.mark.parametrize("outcome", ["stalled", "round_limit", "stopped", "left_page", "nothing_read",
                                     "expired", "not_opened", "old_extension", "completed", "partial"])
def test_partial_endings_are_drawn_as_partial(endings, outcome):
    assert endings[outcome]["tone"] == "partial", outcome


@pytest.mark.parametrize("outcome", ["old_extension", "completed", "partial"])
def test_an_older_extension_ending_says_the_end_is_not_known(endings, outcome):
    assert "not known" in endings[outcome]["label"], outcome


def test_labels_are_words_not_codes(endings):
    for outcome in RECORDED:
        label = endings[outcome]["label"]
        assert "_" not in label and label.lower() != outcome, f"{outcome} is shown as its code"


def test_an_unfinished_import_is_running_or_waiting(endings):
    assert endings["__running"]["tone"] == "running"
    assert endings["__waiting"]["tone"] == "running"
    assert endings["__running"]["label"] != endings["__waiting"]["label"]


def test_the_imports_tab_renders_with_import_ending():
    with open(SURFACE, encoding="utf-8") as handle:
        source = handle.read()
    assert "importEnding(" in source
    assert not re.search(r"outcome\s*===\s*\"completed\"", source), "the tab still keys its colour on 'completed'"


def test_an_import_paused_in_a_hidden_tab_says_so(endings):
    """SETUP-15 rest: the extension reports the pause; the tab does not call it running."""
    assert endings["__paused"]["tone"] == "partial"
    assert "hidden" in endings["__paused"]["label"].lower()
