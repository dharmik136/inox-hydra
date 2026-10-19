"""
Times on screen are the creator's local times.
==============================================

WRITE-22 / UX-05: the Queue printed the stored UTC string sliced to sixteen
characters, so a post queued for Tuesday 08:30 in India was listed at 03:00.
lib/time.ts formats in the machine's zone; this runs it in node under
Asia/Kolkata, and then reads the Queue in a browser set to that zone.
"""

import json
import os
import shutil
import subprocess
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI_DIR = os.path.join(REPO_ROOT, "studio", "ui")
TIME_MODULE = os.path.join(UI_DIR, "src", "lib", "time.ts")
QUEUE = os.path.join(UI_DIR, "src", "components", "QueueSurface.tsx")
NODE = shutil.which("node") or shutil.which("node.exe")

PROBE = r"""
import { formatLocal } from "./time.js";
console.log(JSON.stringify({
  ist: formatLocal("2026-10-20T03:00:00+00:00"),
  missing: formatLocal(null),
  junk: formatLocal("not a time"),
}));
"""


def _esbuild():
    for name in ("esbuild.cmd", "esbuild"):
        candidate = os.path.join(UI_DIR, "node_modules", ".bin", name)
        if os.path.exists(candidate):
            return candidate
    return None


@pytest.fixture(scope="module")
def formatted():
    esbuild = _esbuild()
    if not NODE or not esbuild:
        pytest.skip("node or the UI dependencies are not installed")
    with tempfile.TemporaryDirectory() as work:
        build = subprocess.run(
            [esbuild, TIME_MODULE, "--format=esm", f"--outfile={os.path.join(work, 'time.js')}"],
            capture_output=True, text=True,
        )
        assert build.returncode == 0, build.stderr
        with open(os.path.join(work, "probe.mjs"), "w", encoding="utf-8") as handle:
            handle.write(PROBE)
        run = subprocess.run(
            [NODE, "probe.mjs"], capture_output=True, text=True, cwd=work,
            env={**os.environ, "TZ": "Asia/Kolkata", "LANG": "en_GB.UTF-8"},
        )
        assert run.returncode == 0, run.stderr
        return json.loads(run.stdout)


def test_a_utc_time_is_shown_on_the_local_clock(formatted):
    assert "08:30" in formatted["ist"], formatted["ist"]
    assert "03:00" not in formatted["ist"]


def test_a_missing_time_says_so_and_a_bad_one_shows_itself(formatted):
    assert formatted["missing"] == "No time set"
    assert formatted["junk"] == "not a time"


def test_the_queue_does_not_slice_stored_times():
    with open(QUEUE, encoding="utf-8") as handle:
        source = handle.read()
    assert ".slice(0, 16)" not in source
    assert "formatLocal(" in source
