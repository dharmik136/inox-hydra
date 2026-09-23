"""
Composer Text Measurement Guard
===============================
The React composer reports a character count, and that count decides whether
the interface tells a creator their post clears the LinkedIn fold. The fold
verdict is this product's central claim.

studio/backend/formatters.py already carries a fix for the server side of this:
to_strikethrough and to_underline decorate by inserting a combining mark after
every character, those marks are real code points, and len() therefore doubled.
An 80 character hook measured 160 and mobile_safe flipped from True to False.

The browser has that same hazard and a second one of its own. JavaScript's
String.length counts UTF-16 code units, so mathematical sans-serif bold, which
lives above the basic plane, costs two units per letter. Python's len() counts
code points and never saw that, which is exactly why porting the server's fix
by eye would have missed it.

So this executes the real module rather than reading it. A test that checked
the source contained the word "measurable" would pass against a function that
returned the wrong number.
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


def _find_node():
    """Locates a Node executable, including the default Windows install path."""
    found = shutil.which("node") or shutil.which("node.exe")
    if found:
        return found
    for candidate in (
        r"C:\Program Files\nodejs\node.exe",
        r"C:\Program Files (x86)\nodejs\node.exe",
    ):
        if os.path.exists(candidate):
            return candidate
    return None


def _find_esbuild():
    """esbuild ships in the UI's own node_modules, which a clean checkout lacks."""
    for name in ("esbuild.cmd", "esbuild"):
        candidate = os.path.join(UI_DIR, "node_modules", ".bin", name)
        if os.path.exists(candidate):
            return candidate
    return None


NODE = _find_node()
ESBUILD = _find_esbuild()

# The probe runs against the compiled module and prints a JSON verdict.
#
# "abc" is built three ways: plain, in Mathematical Sans-Serif Bold (U+1D5EE is
# small a, matching to_sans_bold), and struck with U+0336 (matching
# to_strikethrough). All three read as three characters to a person.
PROBE = r"""
import { measurableLength, measurableWordCount, rawIndexAtMeasurableOffset } from "./text.js";

const plain = "abc";
const bold = String.fromCodePoint(0x1d5ee, 0x1d5ef, 0x1d5f0);
const struck = "a\u0336b\u0336c\u0336";

console.log(JSON.stringify({
  rawLengths: { plain: plain.length, bold: bold.length, struck: struck.length },
  measured: {
    plain: measurableLength(plain),
    bold: measurableLength(bold),
    struck: measurableLength(struck),
  },
  words: {
    plain: measurableWordCount("one two three"),
    struck: measurableWordCount("o\u0336n\u0336e\u0336 t\u0336w\u0336o\u0336 three"),
  },
  // Five readable characters into struck text sit ten code units in, because
  // each carries a mark. The fold ruler depends on this translation.
  rawIndexStruck: rawIndexAtMeasurableOffset("a\u0336b\u0336c\u0336d\u0336e\u0336fg", 5),
  rawIndexPlain: rawIndexAtMeasurableOffset("abcdefg", 5),
  empty: measurableLength(""),
}));
"""


@pytest.fixture(scope="module")
def measurements():
    """Compiles studio/ui/src/lib/text.ts and runs the probe against it."""
    if not NODE:
        pytest.skip("Node is not installed, cannot execute the composer text module")
    if not ESBUILD:
        pytest.skip("studio/ui dependencies are not installed, cannot compile TypeScript")
    if not os.path.exists(TEXT_MODULE):
        pytest.skip("studio/ui/src/lib/text.ts is not present in this checkout")

    with tempfile.TemporaryDirectory() as work:
        compiled = os.path.join(work, "text.js")
        build = subprocess.run(
            [ESBUILD, TEXT_MODULE, "--format=esm", f"--outfile={compiled}"],
            capture_output=True,
            text=True,
            shell=False,
        )
        assert build.returncode == 0, f"esbuild failed: {build.stderr}"

        probe = os.path.join(work, "probe.mjs")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write(PROBE)

        run = subprocess.run([NODE, probe], capture_output=True, text=True, cwd=work)
        assert run.returncode == 0, f"probe failed: {run.stderr}"
        return json.loads(run.stdout)


def test_the_hazards_are_real(measurements):
    """
    Establishes that the distortions exist before asserting they are corrected.

    If this fails, the formatters changed and the rest of this file is asserting
    against a problem that no longer occurs.
    """
    raw = measurements["rawLengths"]
    assert raw["plain"] == 3
    assert raw["bold"] == 6, "mathematical bold should cost two UTF-16 units per letter"
    assert raw["struck"] == 6, "each struck character should carry a combining mark"


def test_decoration_does_not_change_the_character_count(measurements):
    """
    The count a creator is shown is the count a reader would make.

    This is the assertion the fold verdict rests on. Bolding a hook must not
    push it past the fold, and neither must striking it through.
    """
    measured = measurements["measured"]
    assert measured["plain"] == 3
    assert measured["bold"] == 3, "bold inflated the count through surrogate pairs"
    assert measured["struck"] == 3, "strikethrough inflated the count through combining marks"


def test_decoration_does_not_change_the_word_count(measurements):
    """Reading time is derived from words, so the same distortion reaches it."""
    words = measurements["words"]
    assert words["plain"] == 3
    assert words["struck"] == 3, "combining marks split decorated words apart"


def test_the_fold_offset_translates_into_the_raw_string(measurements):
    """
    The ruler is drawn in the raw string but positioned by what a reader counts.

    Using the readable offset directly would place the mark halfway back through
    decorated text, because every decorated character occupies more than one
    index.
    """
    assert measurements["rawIndexPlain"] == 5
    assert measurements["rawIndexStruck"] == 10, "marks were not accounted for in the offset"


def test_empty_text_measures_zero(measurements):
    """An empty draft is the first state every session is in."""
    assert measurements["empty"] == 0
