"""
Media Dimensions Guard
======================
The media library printed an asset's dimensions straight from the row, and the
media table stores that column as a JSON string. So every generated image
reported its size to the author as:

    gen_9073811e79.jpg    124 KB . {"width": 1080, "height": 1080}

The value was right and the presentation was a serialisation leak, the same
shape as the docs snippet printing its own markup. Nothing failed: the field is
typed string in api.ts, so TypeScript was satisfied, and no test looked at what
the row rendered.

studio/ui/src/lib/media.ts reads the pair out and formats it. It is tolerant on
purpose. Uploads do not all write the same shape, an unmeasured asset stores
null, and the wrong answer to an unreadable field is to print it again.

Executed rather than read, for the reason test_composer_text_measurement.py
gives: a test asserting the source mentions JSON.parse would pass against a
formatter that returned the wrong string.
"""

import json
import os
import subprocess
import tempfile

import pytest

from tests.test_composer_text_measurement import ESBUILD, NODE, REPO_ROOT

MEDIA_MODULE = os.path.join(REPO_ROOT, "studio", "ui", "src", "lib", "media.ts")
MEDIA_PANEL = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "MediaPanel.tsx")

PROBE = r"""
import { formatDimensions } from "./media.js";

console.log(JSON.stringify({
  // Exactly what the table holds for a generated image.
  stored: formatDimensions('{"width": 1080, "height": 1080}'),
  nonSquare: formatDimensions('{"width": 1920, "height": 1080}'),
  // Absent or unmeasured.
  nullish: formatDimensions(null),
  empty: formatDimensions(""),
  blank: formatDimensions("   "),
  // Shapes an upload path might have written instead.
  plain: formatDimensions("1920x1080"),
  spaced: formatDimensions("800 x 600"),
  unicode: formatDimensions("640×480"),
  // Unreadable. The wrong answer is the raw field.
  broken: formatDimensions("{not json"),
  partial: formatDimensions('{"width": 1080}'),
  zero: formatDimensions('{"width": 0, "height": 0}'),
  words: formatDimensions("very large"),
}));
"""


@pytest.fixture(scope="module")
def formatted():
    """Compiles studio/ui/src/lib/media.ts and runs the probe against it."""
    if not NODE:
        pytest.skip("Node is not installed, cannot execute the media module")
    if not ESBUILD:
        pytest.skip("studio/ui dependencies are not installed, cannot compile TypeScript")
    if not os.path.exists(MEDIA_MODULE):
        pytest.skip("studio/ui/src/lib/media.ts is not present in this checkout")

    with tempfile.TemporaryDirectory() as work:
        compiled = os.path.join(work, "media.js")
        build = subprocess.run(
            [ESBUILD, MEDIA_MODULE, "--format=esm", f"--outfile={compiled}"],
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


def test_the_stored_shape_reads_as_a_size(formatted):
    """The defect this file exists for, on the exact value the table holds."""
    assert formatted["stored"] == "1080 x 1080"
    assert formatted["nonSquare"] == "1920 x 1080"


def test_no_json_punctuation_ever_reaches_the_row(formatted):
    """
    Whatever the formatter is handed, the author never sees the field.

    This is the invariant rather than any single case: a brace or a quote in
    the output means the row is printing storage at a reader again.
    """
    for case, value in formatted.items():
        if value is None:
            continue
        for ch in ('{', '}', '"', ':'):
            assert ch not in value, f"{case} leaked {ch!r} into the row: {value!r}"


def test_an_unmeasured_asset_shows_nothing(formatted):
    """
    A null column is not an error and not a zero. The row simply omits the
    dimensions, which is what the panel's conditional is for.
    """
    assert formatted["nullish"] is None
    assert formatted["empty"] is None
    assert formatted["blank"] is None


def test_readable_shapes_are_normalised(formatted):
    """Uploads do not all write the stored shape, and those still have to read."""
    assert formatted["plain"] == "1920 x 1080"
    assert formatted["spaced"] == "800 x 600"
    assert formatted["unicode"] == "640 x 480"


def test_unreadable_values_are_dropped_rather_than_printed(formatted):
    """
    The failure to avoid is a formatter that gives up and returns its input,
    which puts the defect back for exactly the assets that confused it.
    """
    assert formatted["broken"] is None, "malformed JSON was handed back to the reader"
    assert formatted["partial"] is None, "a height-less object produced a size anyway"
    assert formatted["zero"] is None, "a zero dimension is not a measurement"
    assert formatted["words"] is None


def test_the_panel_formats_rather_than_prints():
    """Guards the other half: the row has to call the formatter."""
    if not os.path.exists(MEDIA_PANEL):
        pytest.skip("MediaPanel.tsx is not present in this checkout")
    with open(MEDIA_PANEL, encoding="utf-8") as handle:
        source = handle.read()

    assert "formatDimensions(" in source, "the panel no longer formats the field"
    assert "{asset.dimensions}" not in source, (
        "the raw dimensions field is being rendered again, which is the original "
        "defect"
    )
