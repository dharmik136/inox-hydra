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
RESULTS_SURFACE = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "HelpCentre.tsx")

PROBE = r"""
import { splitSnippet, readableSnippet, readableInline, readablePlain } from "./snippet.js";

// A run of spans, flattened for comparison. "code" is reported so a test can
// assert that a fragment never produces one.
const flat = (spans) => spans.map((s) => {
  if (s.kind === "text") return s.text;
  if (s.kind === "code") return "CODE{" + s.text + "}";
  if (s.kind === "strong") return "B{" + flat(s.spans) + "}";
  if (s.kind === "em") return "I{" + flat(s.spans) + "}";
  if (s.kind === "link") return "A{" + flat(s.spans) + "}";
  return "";
}).join("");

const readable = (snippet) => readableSnippet(snippet).map((r) => ({
  text: flat(r.spans), matched: r.matched,
}));

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

  // ---- the fragment cases, all taken from real results ------------------
  // FTS5 returns a window onto the INDEXED SOURCE, so a snippet arrives as
  // markdown. These were visible on screen the moment results were drawn at
  // reading width instead of squeezed into a 300px rail.
  heading: readable("## 4. Security Model & Zero-<mark>Egress</mark> Guarantee"),
  bullet: readable("* **Provider Key**: `ollama` * **<mark>Egress</mark>**: none"),
  rule: readable("Offline <mark>mode</mark> ---"),
  tableRow: readable("| Dimension | <mark>Rule</mark> & Penalty |"),
  halfLink: readable("...Swipe File](#module-04-viral-swipe-file) Reverse-engineered <mark>hooks</mark>"),
  // The window cut after an opening bold marker, so its partner is outside.
  danglingBold: readable("`http://localhost:11434/v1` * **<mark>Egress</mark>"),
  // Two backticks that were never partners in the source. Pairing them set a
  // whole sentence in monospace.
  spuriousCode: readable("py`: Generates a multi-page PDF ready for <mark>LinkedIn</mark> Document`"),
  boxArt: readable("Toggle -----------------------------+------------- <mark>theme</mark>"),
  // Balanced emphasis still means something and is kept.
  realBold: readable("**Consequence**: any update that replaces the <mark>folder</mark>"),

  // Excerpts are windows too: the document's own opening line, cut at 220.
  excerptPlain: flat(readableInline("The **Studio & Editor** is the core creation environment.")),
  excerptCut: flat(readableInline("Uses `taplio_vault_archive_backup.json` and **half a bold")),
  excerptLink: flat(readableInline("See [the manual](modules/01_STUDIO_AND_EDITOR.md) for detail.")),

  // And a heading shown as a plain string needs the same, for a title
  // attribute or an uppercased breadcrumb.
  plainTitle: readablePlain("4.1 Global Sidebar (`#global-sidebar`)"),
  plainBold: readablePlain("**Real.** Encrypted at rest"),
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
            [
                ESBUILD,
                SNIPPET_MODULE,
                "--bundle",
                "--format=esm",
                f"--alias:@={os.path.join(REPO_ROOT, 'studio', 'ui', 'src')}",
                f"--outfile={compiled}",
            ],
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
    # Named explicitly rather than taken as "everything in the dict". The probe
    # grew fragment cases that return a string or a different run shape, and a
    # test that iterates whatever happens to be there breaks on the next one
    # added, which is a test about the probe rather than about the parser.
    #
    # "unbalanced" is excluded deliberately and has its own test: an opener with
    # no closer is a document that contains those characters.
    balanced = {name: runs[name] for name in
                ("typical", "unmarked", "empty", "foreign", "hollow", "adjacent")}
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

    Results moved out of the rail and into the reading column, so the component
    that renders a snippet is the help centre. readableSnippet is splitSnippet
    with the rest of the markdown handled too, which is what the wider column
    made visible: the window FTS5 returns is a view onto the source, so it
    arrives full of headings, bullets and half a link.
    """
    if not os.path.exists(RESULTS_SURFACE):
        pytest.skip("HelpCentre.tsx is not present in this checkout")
    with open(RESULTS_SURFACE, encoding="utf-8") as handle:
        source = handle.read()

    assert "readableSnippet(" in source, "the help centre no longer parses the snippet"
    assert "dangerouslySetInnerHTML" not in source, (
        "document content was handed to the HTML parser, which renders whatever "
        "a playbook file happens to contain"
    )
    assert "{hit.snippet}" not in source, (
        "the raw snippet is being rendered again, which is the original defect"
    )


# ---------------------------------------------------------------------------
# A snippet is a window onto markdown, not a sentence
# ---------------------------------------------------------------------------
# splitSnippet solved one half: the FTS5 markers stopped reaching the reader as
# characters. The other half only became visible when results moved out of the
# 300px rail and into the reading column, where a snippet is three legible
# lines. What arrived was "## 4. Security Model", "* **Provider Key**:
# `ollama`", a trailing "---", and half a link whose label was outside the
# window. Exactly the defect the document reader had, one layer down.

FRAGMENT_SYNTAX = [
    ("**", "bold markers"),
    ("`", "a backtick"),
    ("](", "half a link"),
    ("---", "a horizontal rule"),
    ("|", "a table pipe"),
]


def _joined(runs):
    return "".join(run["text"] for run in runs)


def test_no_block_syntax_survives_into_a_snippet(runs):
    """
    A snippet is a preview of a passage, not the passage: there is no heading
    to draw, no list to indent and no rule to place.
    """
    for case in ("heading", "bullet", "rule", "tableRow", "halfLink", "boxArt"):
        text = _joined(runs[case])
        for token, why in FRAGMENT_SYNTAX:
            assert token not in text, f"{case} still shows {why}: {text!r}"
        assert "#" not in text, f"{case} still shows a heading marker: {text!r}"


def test_the_match_is_still_marked_after_cleaning(runs):
    """
    Cleaning happens before the markers are split, so the marks travel with the
    text they surround. Losing the highlight would trade one defect for another.
    """
    for case in ("heading", "bullet", "rule", "tableRow", "halfLink", "danglingBold", "boxArt", "realBold"):
        marked = [run["text"] for run in runs[case] if run["matched"]]
        assert marked, f"{case} lost its highlight"
        assert all(text.strip() for text in marked), f"{case} marked an empty run"


def test_balanced_emphasis_is_kept(runs):
    """The cleaning is of what the window broke, not of the document's own markup."""
    assert "B{Consequence}" in _joined(runs["realBold"]), runs["realBold"]
    assert "B{Studio & Editor}" in runs["excerptPlain"], runs["excerptPlain"]


def test_an_unpairable_emphasis_marker_is_dropped(runs):
    """
    A window that opens inside a bolded phrase leaves a marker whose partner is
    outside it. An unpaired delimiter marks nothing, so printing it is showing
    the reader punctuation that means nothing.

    Two layers enforce this: the odd count check before parsing, and the sweep
    of leftover delimiters out of text spans afterwards. Removing either alone
    leaves this green, which is defence in depth rather than a weak check.
    Removing both fails it with "**Egress" on screen, which is how that was
    established rather than assumed.
    """
    text = _joined(runs["danglingBold"])
    assert "**" not in text, f"a dangling bold marker reached the reader: {text!r}"
    assert "Egress" in text, "the word the marker was attached to was dropped with it"
    assert "**" not in runs["excerptCut"], runs["excerptCut"]


def test_a_fragment_never_claims_that_prose_is_code(runs):
    """
    The subtle one, and the reason backticks are dropped from a fragment
    outright rather than balanced.

    Two backticks that were never partners in the source sit next to each other
    once the window has cut, and the parser pairs them. A mis-paired emphasis
    puts the wrong words in bold; a mis-paired code span claims that run IS
    code, and a whole sentence in monospace is the interface asserting
    something untrue about the content.
    """
    for case in ("spuriousCode", "bullet", "danglingBold"):
        text = _joined(runs[case])
        assert "CODE{" not in text, f"{case} produced a code span from a windowed fragment: {text!r}"
        assert "`" not in text, f"{case} leaked a backtick: {text!r}"
    assert "CODE{" not in runs["excerptCut"], runs["excerptCut"]
    # The words survive; only the claim about what they are is dropped.
    assert "LinkedIn" in _joined(runs["spuriousCode"])
    assert "taplio_vault_archive_backup.json" in runs["excerptCut"]


def test_a_link_in_an_excerpt_reads_as_its_label(runs):
    """A preview is not a place to navigate from, so the target is not shown."""
    assert "A{the manual}" in runs["excerptLink"], runs["excerptLink"]
    assert "modules/01" not in runs["excerptLink"], runs["excerptLink"]


def test_a_title_shown_as_a_plain_string_is_cleaned_too(runs):
    """
    Headings are markdown as well, and they reach places a run of spans cannot
    go: a title attribute, an accessible name, an uppercased breadcrumb.
    """
    assert runs["plainTitle"] == "4.1 Global Sidebar (#global-sidebar)", runs["plainTitle"]
    assert runs["plainBold"] == "Real. Encrypted at rest", runs["plainBold"]
