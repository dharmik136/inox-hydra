"""
One count for the limit, one for the fold, the same on both sides
==================================================================
The Composer's strip stripped every Unicode mark before counting, which
removes the vowel signs of Hindi and Gujarati, while the Audit's Gate 2 and
the server's save limit count the characters as stored. A Hindi post the strip
called 2,964 characters was 4,332 to Gate 2, so the strip said it fitted under
LinkedIn's 3,000 while the Audit said it did not. The strip never showed the
limit at all.

There are two questions and so two counts, each now the same in the browser
and on the server:

- How long the post is against a length limit: every character as stored,
  decoration included, since it is stored and sent. storedLength in
  studio/ui/src/lib/text.ts, len() in Python: Gate 2 and the 5,000 save limit.
- Where the fold falls: what a reader sees, with marks removed so a struck or
  underlined letter counts once. measurableLength in text.ts,
  formatters._measurable_text in Python, and Gate 3.

This executes the real TypeScript module rather than reading it, like
tests/test_composer_text_measurement.py, and compares it with the server's own
functions on one shared set of texts.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
TEXT_MODULE = os.path.join(REPO_ROOT, "studio", "ui", "src", "lib", "text.ts")
UI_DIR = os.path.join(REPO_ROOT, "studio", "ui")

from formatters import _measurable_text, analyze_hook  # noqa: E402
from gstack_governance import gstack_engine  # noqa: E402

FIXTURES = {
    "hindi": "नमस्ते, आप कैसे हैं?",
    "gujarati": "કેમ છો? આજે સરસ દિવસ છે.",
    "family": "\U0001f468‍\U0001f469‍\U0001f467",
    "bold": "\U0001d5ee\U0001d5ef\U0001d5f0",
    "struck": "a̶b̶c̶",
    "plain": "Plain words, nothing else.",
}


def _find(*names):
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


NODE = _find("node", "node.exe")
ESBUILD = next(
    (
        os.path.join(UI_DIR, "node_modules", ".bin", name)
        for name in ("esbuild.cmd", "esbuild")
        if os.path.exists(os.path.join(UI_DIR, "node_modules", ".bin", name))
    ),
    None,
)

PROBE = """
import { measurableLength, storedLength, POST_LIMIT_CHARS } from "./text.js";
const fixtures = JSON.parse(process.argv[2]);
const out = { limit: POST_LIMIT_CHARS, stored: {}, measured: {} };
for (const [name, text] of Object.entries(fixtures)) {
  out.stored[name] = storedLength(text);
  out.measured[name] = measurableLength(text);
}
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def client_counts():
    if not NODE:
        pytest.skip("Node is not installed, cannot execute the composer text module")
    if not ESBUILD:
        pytest.skip("studio/ui dependencies are not installed, cannot compile TypeScript")
    with tempfile.TemporaryDirectory() as work:
        compiled = os.path.join(work, "text.js")
        build = subprocess.run([ESBUILD, TEXT_MODULE, "--format=esm", f"--outfile={compiled}"],
                               capture_output=True, text=True, encoding="utf-8")
        assert build.returncode == 0, f"esbuild failed: {build.stderr}"
        probe = os.path.join(work, "probe.mjs")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write(PROBE)
        run = subprocess.run([NODE, probe, json.dumps(FIXTURES)], capture_output=True, text=True, encoding="utf-8", cwd=work)
        assert run.returncode == 0, f"probe failed: {run.stderr}"
        return json.loads(run.stdout)


def test_the_strip_and_gate_2_count_the_limit_the_same_way(client_counts):
    """The number shown against 3,000 is the number Gate 2 blocks on."""
    assert client_counts["limit"] == 3000
    for name, text in FIXTURES.items():
        gate_2 = gstack_engine.audit_content_or_feature(text)["gates"]["gate_2_eng_manager"]["char_count"]
        assert client_counts["stored"][name] == gate_2 == len(text), name


def test_a_hindi_post_over_the_limit_is_over_it_in_the_strip_too(client_counts):
    """The finding's own case: Devanagari vowel signs are characters the limit counts."""
    hindi = FIXTURES["hindi"]
    assert client_counts["stored"]["hindi"] == len(hindi)
    assert client_counts["stored"]["hindi"] > client_counts["measured"]["hindi"], (
        "the fixture no longer contains the marks the strip used to drop"
    )


def test_the_fold_is_measured_the_same_way_in_the_editor_and_on_the_server(client_counts):
    """Struck, bold, Indic and emoji text: the editor's fold and the server's agree."""
    for name, text in FIXTURES.items():
        assert client_counts["measured"][name] == len(_measurable_text(text)), name
        assert client_counts["measured"][name] == analyze_hook(text)["char_count"], name
        first_line = gstack_engine.audit_content_or_feature(text)["gates"]["gate_3_designer"]["first_line_chars"]
        assert client_counts["measured"][name] == first_line, name


def test_decoration_still_counts_once_for_the_fold(client_counts):
    assert client_counts["measured"]["struck"] == 3
    assert client_counts["measured"]["bold"] == 3
    assert client_counts["stored"]["struck"] == 6, "a struck letter is two stored characters"
