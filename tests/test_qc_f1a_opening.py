"""
Applying a hook replaces the opening paragraph, and only that
=============================================================
A paragraph ended at the first "\\n\\n". A blank line that holds a space, a
no-break space or the U+2800 spacer LinkedIn writers use so the gap survives
posting is still a blank line to a reader, but not to that test, so the whole
post counted as its opening and a hook replaced all of it.

This executes swapOpening and openingEnd from studio/ui/src/lib/text.ts, the
functions the Composer applies hooks with, rather than reading their source.
tests/test_qc_f1a_composer.py drives the same case in the browser, with Undo.
"""

import json
import os
import shutil
import subprocess
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEXT_MODULE = os.path.join(REPO_ROOT, "studio", "ui", "src", "lib", "text.ts")
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

SPACERS = {
    "empty": "",
    "space": " ",
    "tab": "\t",
    "nbsp": " ",
    "braille_blank": "⠀",
    "zero_width": "​",
    "mixed": " ⠀ ",
}

PROBE = """
import { swapOpening, openingEnd } from "./text.js";
const spacers = JSON.parse(process.argv[2]);
const out = {};
for (const [name, spacer] of Object.entries(spacers)) {
  const draft = `My opening line.\\n${spacer}\\nThe body.\\n${spacer}\\nThe close.`;
  out[name] = { swapped: swapOpening(draft, "HOOK"), end: openingEnd(draft) };
}
out.noBreak = swapOpening("One paragraph only", "HOOK");
out.emptyDraft = swapOpening("", "HOOK");
out.wrappedLine = swapOpening("Line one\\nline two of the opening\\n\\nBody", "HOOK");
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def results():
    if not NODE:
        pytest.skip("Node is not installed, cannot execute the composer text module")
    if not ESBUILD:
        pytest.skip("studio/ui dependencies are not installed, cannot compile TypeScript")
    with tempfile.TemporaryDirectory() as work:
        compiled = os.path.join(work, "text.js")
        build = subprocess.run([ESBUILD, TEXT_MODULE, "--format=esm", f"--outfile={compiled}"],
                               capture_output=True, text=True)
        assert build.returncode == 0, f"esbuild failed: {build.stderr}"
        probe = os.path.join(work, "probe.mjs")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write(PROBE)
        run = subprocess.run([NODE, probe, json.dumps(SPACERS)], capture_output=True, text=True, cwd=work)
        assert run.returncode == 0, f"probe failed: {run.stderr}"
        return json.loads(run.stdout)


@pytest.mark.parametrize("name", sorted(SPACERS))
def test_a_blank_line_that_holds_only_spacing_ends_the_opening(results, name):
    spacer = SPACERS[name]
    assert results[name]["swapped"] == f"HOOK\n{spacer}\nThe body.\n{spacer}\nThe close.", name
    assert results[name]["end"] == len("My opening line."), name


def test_the_edges_are_unchanged(results):
    assert results["noBreak"] == "HOOK", "a draft with no blank line is all opening"
    assert results["emptyDraft"] == "HOOK", "an empty draft becomes the hook"
    assert results["wrappedLine"] == "HOOK\n\nBody", "a single line break is inside the opening"
