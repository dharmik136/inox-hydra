"""
Docs Search Highlighting Guard
==============================
The playbook search is served by SQLite FTS5, which returns each hit with the
matched terms wrapped in <mark> tags. The first version of the docs surface
rendered that snippet as a React text child, on the correct reasoning that a
playbook file is database content and must never reach the HTML parser.

The reasoning was right and the result was wrong. Every hit of every search
printed the literal characters "<mark>Hook</mark>" at the reader, because a
text child is escaped rather than interpreted. The build was clean, the type
checker was happy, the suite was green, and the feature was visibly broken on
screen.

studio/ui/src/lib/snippet.ts resolves it by parsing the one marker pair the
index emits into runs, which the component renders as separate elements. That
keeps the escape guarantee (nothing else in the string is ever interpreted)
while producing the highlight the search was for.

This executes the real module rather than reading it, for the same reason
test_composer_text_measurement.py does: a test that checked the source
mentioned "mark" would pass against a parser that dropped every hit.
"""

import json
import os
import subprocess
import tempfile

import pytest

from tests.test_composer_text_measurement import ESBUILD, NODE, REPO_ROOT

SNIPPET_MODULE = os.path.join(REPO_ROOT, "studio", "ui", "src", "lib", "snippet.ts")
DOCS_SURFACE = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "DocsSurface.tsx")

PROBE = r"""
import { splitSnippet } from "./snippet.js";

console.log(JSON.stringify({
  // What FTS5 actually returns for a hit on "hook".
  typical: splitSnippet("...<mark>Hook</mark> rail Replace the 260px <mark>hook</mark>-card"),
  // A snippet with no match markers is one unmatched run.
  unmarked: splitSnippet("nothing is highlighted here"),
  empty: splitSnippet(""),
  // An opener with no closer is a document that contains the characters, not
  // a highlight. The remainder must survive rather than be swallowed.
  unbalanced: splitSnippet("before <mark> after with no closer"),
  // Markup that is not the marker pair stays inert text.
  foreign: splitSnippet("a <script>alert(1)</script> b"),
  // An empty pair contributes nothing to read.
  hollow: splitSnippet("a<mark></mark>b"),
  adjacent: splitSnippet("<mark>one</mark><mark>two</mark>"),
}));
"""


@pytest.fixture(scope="module")
def runs():
    """Compiles studio/ui/src/lib/snippet.ts and runs the probe against it."""
    if not NODE:
        pytest.skip("Node is not installed, cannot execute the snippet module")
    if not ESBUILD:
        pytest.skip("studio/ui dependencies are not installed, cannot compile TypeScript")
    if not os.path.exists(SNIPPET_MODULE):
        pytest.skip("studio/ui/src/lib/snippet.ts is not present in this checkout")

    with tempfile.TemporaryDirectory() as work:
        compiled = os.path.join(work, "snippet.js")
        build = subprocess.run(
            [ESBUILD, SNIPPET_MODULE, "--format=esm", f"--outfile={compiled}"],
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


def _text(entries):
    return "".join(entry["text"] for entry in entries)


def test_the_markers_never_reach_the_reader(runs):
    """
    The defect this file exists for: the tags were shown as characters.

    Scoped to the snippets the index actually emits, which always close what
    they open. "unbalanced" is excluded deliberately and has its own test: an
    opener with no closer is a document that contains those characters, and
    stripping it there would edit the playbook rather than highlight it.
    """
    balanced = {name: entries for name, entries in runs.items() if name != "unbalanced"}
    for case, entries in balanced.items():
        joined = _text(entries)
        assert "<mark>" not in joined, f"{case} leaked an opening marker to the reader"
        assert "</mark>" not in joined, f"{case} leaked a closing marker to the reader"


def test_the_matched_terms_are_marked(runs):
    """Highlighting the hit is the entire point of the snippet."""
    matched = [entry["text"] for entry in runs["typical"] if entry["matched"]]
    assert matched == ["Hook", "hook"], f"expected both hits to be marked, got {matched}"


def test_the_surrounding_text_is_kept_in_order(runs):
    """
    A parser that highlights correctly and reorders the prose is still broken.

    The snippet reads as a sentence, so the runs have to concatenate back into
    it with only the markers removed.
    """
    assert _text(runs["typical"]) == "...Hook rail Replace the 260px hook-card"


def test_a_snippet_with_no_match_is_a_single_plain_run(runs):
    """Not every hit carries a marker, and those must still render."""
    assert runs["unmarked"] == [{"text": "nothing is highlighted here", "matched": False}]


def test_an_unbalanced_marker_keeps_the_rest_of_the_snippet(runs):
    """
    A playbook file may contain the characters without meaning a highlight.

    The failure to avoid is a parser that finds an opener, hunts for a closer,
    finds none, and silently drops everything after it. The reader would see a
    result truncated at an arbitrary point with nothing to indicate why.
    """
    assert _text(runs["unbalanced"]) == "before <mark> after with no closer"
    assert not any(entry["matched"] for entry in runs["unbalanced"])


def test_foreign_markup_stays_inert_text(runs):
    """
    The reason the original rendered as text, preserved.

    The parser recognises exactly one tag pair. Everything else is content,
    including content that would be markup if anything interpreted it, and it
    comes back as text in a run so the component escapes it.
    """
    assert _text(runs["foreign"]) == "a <script>alert(1)</script> b"
    assert not any(entry["matched"] for entry in runs["foreign"])


def test_degenerate_pairs_produce_nothing_to_render(runs):
    """An empty highlight would draw a coloured box around no characters."""
    assert runs["hollow"] == [
        {"text": "a", "matched": False},
        {"text": "b", "matched": False},
    ]
    assert [entry["text"] for entry in runs["adjacent"]] == ["one", "two"]
    assert all(entry["matched"] for entry in runs["adjacent"])


def test_the_surface_renders_runs_rather_than_raw_html():
    """
    Guards the other half: the component must use the parser, and must not
    reach for dangerouslySetInnerHTML as a shortcut back to the same bug.
    """
    if not os.path.exists(DOCS_SURFACE):
        pytest.skip("DocsSurface.tsx is not present in this checkout")
    with open(DOCS_SURFACE, encoding="utf-8") as handle:
        source = handle.read()

    assert "splitSnippet(" in source, "the docs surface no longer parses the snippet"
    assert "dangerouslySetInnerHTML" not in source, (
        "document content was handed to the HTML parser, which renders whatever "
        "a playbook file happens to contain"
    )
    assert "{hit.snippet}" not in source, (
        "the raw snippet is being rendered again, which is the original defect"
    )
