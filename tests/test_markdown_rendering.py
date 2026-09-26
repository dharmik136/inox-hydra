"""
Playbook Formatting Guards
==========================
The docs reader rendered every document as one <pre> element. Across the 38
files the studio indexes that meant 798 table rows, 182 fence lines, 1,266
bullets, 1,226 bold runs and 280 third level headings arrived as literal
markdown characters. The six row penalty table in module 01 is the content of
the algorithmic audit section rather than an aside, and it was unreadable.

studio/ui/src/lib/markdown.ts turns a document into typed blocks instead.

This executes the real module against the real corpus, for the reason
tests/test_docs_search_highlighting.py does the same: a test that read the
source and found the word "table" would pass against a parser that produced
none. Every count below is measured from docs/ at run time, so the corpus
cannot drift out from under the assertions, and a construct that stops being
recognised takes a number down with it.

Three dialect rules are pinned here because each one is a decision that a
plausible "improvement" would undo:

- Underscore never emphasises. These files are full of snake_case, and
  CommonMark's intraword rules would eat identifiers out of a technical
  document.
- A table needs its delimiter row. Several files draw ASCII interface mocks out
  of pipes, and the delimiter is the only thing that tells a sketch from a
  table.
- Inline math needs a backslash inside it. There is no typesetter here, and
  without that rule a price becomes an equation.
"""

import json
import os
import subprocess
import tempfile

import pytest

from tests.test_composer_text_measurement import ESBUILD, NODE, REPO_ROOT

MARKDOWN_MODULE = os.path.join(REPO_ROOT, "studio", "ui", "src", "lib", "markdown.ts")
DOCS_DIR = os.path.join(REPO_ROOT, "docs")

# The probe walks the corpus itself and reports both the block census and what
# it could not account for. blockAll reads every field the parser retains, not
# only the reading text: a fence language lives in block.language, an ordered
# marker in list.start, a checkbox in item.checked, a link target in span.href,
# an alert kind in callout.tone. The first version of this probe read none of
# those and reported 40 files as lossy when nothing was lost at all.
PROBE = r"""
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { parseMarkdown, parseInline, parseBlocks, splitRow, spanText, slugify } from "./markdown.js";

const DOCS = process.argv[2];

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (name.endsWith(".md")) out.push(p);
  }
  return out;
}

function spanAll(spans) {
  return spans.map((s) => {
    if (s.kind === "text" || s.kind === "code" || s.kind === "math") return s.text;
    if (s.kind === "link") return spanAll(s.spans) + " " + s.href;
    if (s.kind === "strong" || s.kind === "em") return spanAll(s.spans);
    // A break span IS the tag it replaced, so it is credited with the token,
    // exactly as a fence language, a checkbox and an alert kind are above. The
    // check stays meaningful either way: a break the parser dropped produces no
    // span, so the token goes missing and this reports it.
    if (s.kind === "break") return "br";
    return " ";
  }).join(" ");
}

function blockAll(b) {
  switch (b.kind) {
    case "heading": return b.text;
    case "paragraph": return spanAll(b.spans);
    case "code": return (b.language || "") + "\n" + b.code;
    case "formula": return b.source;
    case "rule": return "";
    case "callout": return (b.tone || "") + "\n" + b.blocks.map(blockAll).join("\n");
    case "list":
      return b.items.map((it, n) =>
        (b.ordered ? String(b.start + n) : "") + " " +
        (it.checked === null ? "" : it.checked ? "x" : " ") + " " +
        it.blocks.map(blockAll).join("\n")).join("\n");
    case "table":
      return [b.head, ...b.rows].map((row) => row.map(spanAll).join(" ")).join("\n");
    default: return "";
  }
}

const words = (s) => s.toLowerCase().match(/[a-z0-9]+/g) || [];

const census = {};
const lossy = [];
const leaks = [];
let maxTableCols = 0, maxTableRows = 0, deepestList = 0, taskItems = 0;
const tones = {};

for (const path of walk(DOCS)) {
  const rel = relative(DOCS, path).split("\\").join("/");
  const source = readFileSync(path, "utf8");
  const doc = parseMarkdown(source);

  const visit = (blocks, depth) => {
    for (const b of blocks) {
      census[b.kind] = (census[b.kind] || 0) + 1;
      if (b.kind === "table") {
        maxTableCols = Math.max(maxTableCols, b.head.length);
        maxTableRows = Math.max(maxTableRows, b.rows.length);
      }
      if (b.kind === "callout") {
        if (b.tone) tones[b.tone] = (tones[b.tone] || 0) + 1;
        visit(b.blocks, depth);
      }
      if (b.kind === "list") {
        deepestList = Math.max(deepestList, depth + 1);
        for (const it of b.items) {
          if (it.checked !== null) taskItems += 1;
          visit(it.blocks, depth + 1);
        }
      }
    }
  };
  visit(doc.blocks, 0);

  // Completeness: every word in the file survives into some field.
  const after = new Map();
  for (const w of words(doc.blocks.map(blockAll).join("\n"))) after.set(w, (after.get(w) || 0) + 1);
  const seen = new Map();
  const missing = [];
  for (const w of words(source)) {
    seen.set(w, (seen.get(w) || 0) + 1);
    if ((after.get(w) || 0) < seen.get(w)) missing.push(w);
  }
  if (missing.length) lossy.push({ file: rel, count: missing.length, sample: missing.slice(0, 6) });

  // Leaked syntax, checked only inside TEXT spans. A code span holding two
  // asterisks is content: one file tells the reader that LinkedIn ignores
  // **text**, and rendering that as bold would destroy the sentence.
  const scanSpans = (spans) => {
    for (const s of spans) {
      if (s.kind === "text") {
        if (s.text.includes("**")) leaks.push({ file: rel, why: "bold", sample: s.text.slice(0, 60) });
        if (s.text.includes("```")) leaks.push({ file: rel, why: "fence", sample: s.text.slice(0, 60) });
        if (/<br\s*\/?>/i.test(s.text)) leaks.push({ file: rel, why: "break-tag", sample: s.text.slice(0, 60) });
        if (/\]\([^)\s]+\)/.test(s.text)) leaks.push({ file: rel, why: "link", sample: s.text.slice(0, 60) });
      } else if (s.kind === "strong" || s.kind === "em" || s.kind === "link") {
        scanSpans(s.spans);
      }
    }
  };
  const scan = (blocks) => {
    for (const b of blocks) {
      if (b.kind === "paragraph") {
        scanSpans(b.spans);
        const t = spanText(b.spans);
        if (/^\s*\|.*\|\s*$/m.test(t)) leaks.push({ file: rel, why: "table-row", sample: t.slice(0, 60) });
        if (/^#{1,6}\s/.test(t)) leaks.push({ file: rel, why: "heading", sample: t.slice(0, 60) });
      }
      if (b.kind === "heading") scanSpans(b.spans);
      if (b.kind === "callout") scan(b.blocks);
      if (b.kind === "list") for (const it of b.items) scan(it.blocks);
      if (b.kind === "table") for (const row of [b.head, ...b.rows]) for (const c of row) scanSpans(c);
    }
  };
  scan(doc.blocks);
}

// ---- targeted cases, written here so they read beside the corpus census ----
const asciiMock = [
  "| TOP BAR: [View Title]  |  Chars: 0/3,000  |",
  "| [Active Prospects: 4]  |  Warm Engagers    |",
];
const realTable = ["| Dimension | Penalty |", "| :--- | ---: |", "| Hook | -20 |"];

const cases = {
  asciiMockIsNotATable: parseBlocks(asciiMock).map((b) => b.kind),
  realTableIsATable: parseBlocks(realTable).map((b) => b.kind),
  realTableAlign: parseBlocks(realTable)[0].align,
  pipeInsideCode: splitRow("| a | `x | y` | b |"),
  escapedPipe: splitRow("| a \\| b | c |"),
  snakeCase: spanText(parseInline("set word_count from li_at and taplio_vault_archive_backup.json")),
  underscoreNeverEmphasises: parseInline("a _b_ c").map((s) => s.kind),
  asteriskDoesEmphasise: parseInline("a *b* c").map((s) => s.kind),
  arithmeticIsNotEmphasis: spanText(parseInline("2 * 3 * 4")),
  priceIsNotMath: parseInline("costs $5 and $10").map((s) => s.kind),
  latexIsMath: parseInline("Score $\\ge$ 90%").map((s) => s.kind),
  boldHoldingCode: (() => {
    const s = parseInline("**Character Counter (`Chars: X / 3,000`)**:");
    return { outer: s.map((x) => x.kind), inner: s[0].kind === "strong" ? s[0].spans.map((x) => x.kind) : [] };
  })(),
  hashInsideFenceIsNotAHeading: parseBlocks(["```bash", "# install the thing", "npm i", "```"])
    .map((b) => b.kind),
  fenceKeepsItsBody: parseBlocks(["```bash", "# install", "```"])[0].code,
  nestedByRelativeIndent: (() => {
    const blocks = parseBlocks([
      "1. **Counter**:",
      "   * measures length",
      "   * warns near the limit",
      "2. **Other**:",
      "  * two spaces this time",
    ]);
    const first = blocks[0];
    return {
      kind: first.kind,
      items: first.items.length,
      firstItemBlocks: first.items[0].blocks.map((b) => b.kind),
      nestedItems: first.items[0].blocks[1] ? first.items[0].blocks[1].items.length : 0,
    };
  })(),
  taskState: parseBlocks(["- [x] done", "- [ ] not done", "- plain item"])[0].items.map((i) => i.checked),
  declaredTone: parseBlocks(["> [!IMPORTANT]", "> mind this"])[0].tone,
  plainQuoteHasNoTone: parseBlocks(["> Status note. This used to say something else."])[0].tone,
  unknownAlertIsNotATone: parseBlocks(["> [!SHOUTING]", "> hello"])[0].tone,
  slugCollisions: parseMarkdown("## Overview\n\na\n\n## Overview\n\nb\n\n## Overview\n\nc")
    .outline.map((o) => o.slug),
  placeholdersSurvive: spanText(parseInline("run it as `studio --version <version>` for <filename>")),
  scriptTagIsInertText: parseInline("a <script>alert(1)</script> b").map((s) => s.kind),
  outlineSkipsTheTitle: parseMarkdown("# Title\n\n## One\n\n### Two\n\n#### Four").outline.map((o) => o.level),
  ruleIsNotABullet: parseBlocks(["---"]).map((b) => b.kind),
  slugOfAnIndexedSection: slugify("4. 1080\u00d71080 Multi-Slide PDF Carousel Builder"),
  slugOfAnEnDashSection: [slugify("7. Algorithmic Safety Audit Engine (0\u2013100%)"),
                          slugify("7. Algorithmic Safety Audit Engine (0-100%)")],
};

console.log(JSON.stringify({ census, lossy, leaks, tones, maxTableCols, maxTableRows, deepestList, taskItems, cases }));
"""


@pytest.fixture(scope="module")
def parsed():
    """Compiles lib/markdown.ts and runs it over every markdown file in docs/."""
    if not NODE:
        pytest.skip("Node is not installed, cannot execute the markdown module")
    if not ESBUILD:
        pytest.skip("studio/ui dependencies are not installed, cannot compile TypeScript")
    if not os.path.exists(MARKDOWN_MODULE):
        pytest.skip("studio/ui/src/lib/markdown.ts is not present in this checkout")
    if not os.path.isdir(DOCS_DIR):
        pytest.skip("docs/ is not present in this checkout")

    with tempfile.TemporaryDirectory() as work:
        compiled = os.path.join(work, "markdown.js")
        build = subprocess.run(
            [ESBUILD, MARKDOWN_MODULE, "--format=esm", f"--outfile={compiled}"],
            capture_output=True, text=True, shell=False,
        )
        assert build.returncode == 0, f"esbuild failed: {build.stderr}"

        probe = os.path.join(work, "probe.mjs")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write(PROBE)

        run = subprocess.run([NODE, probe, DOCS_DIR], capture_output=True, text=True, cwd=work)
        assert run.returncode == 0, f"probe failed: {run.stderr}"
        return json.loads(run.stdout)


# ---------------------------------------------------------------------------
# The corpus is actually parsed
# ---------------------------------------------------------------------------

def test_every_construct_in_the_corpus_becomes_a_block(parsed):
    """
    The defect this file exists for, measured rather than described.

    Each floor is well under what docs/ currently holds, so ordinary editing
    does not trip it, and a parser that stopped recognising one of these
    constructs could not reach it. Before this module existed every one of
    these counts was zero and the whole document was one <pre>.
    """
    census = parsed["census"]
    floors = {
        "heading": 400, "paragraph": 1200, "list": 300,
        "code": 60, "table": 50, "rule": 150, "callout": 15, "formula": 4,
    }
    for kind, floor in floors.items():
        assert census.get(kind, 0) >= floor, (
            f"only {census.get(kind, 0)} {kind} blocks across the corpus, expected at least {floor}. "
            "Either a construct stopped being recognised or the documents changed shape."
        )


def test_no_document_loses_a_word(parsed):
    """
    Completeness. Structure may disappear; content may not.

    Checked against every field the parser retains rather than only the reading
    text, so a fence language, an ordered marker, a checkbox, a link target and
    an alert kind all count as kept.
    """
    assert parsed["lossy"] == [], (
        "these documents lost content in the parse: "
        + json.dumps(parsed["lossy"][:4], indent=2)
    )


def test_no_markdown_syntax_reaches_the_reader_as_text(parsed):
    """
    The visible half of the same defect.

    Scoped to text spans. A code span holding two asterisks is content: one file
    tells the reader that LinkedIn ignores bold markers, and rendering that as
    bold would delete the point of the sentence.
    """
    assert parsed["leaks"] == [], (
        "unparsed markdown left in prose: " + json.dumps(parsed["leaks"][:6], indent=2)
    )


def test_the_real_tables_are_parsed_at_their_real_size(parsed):
    """A table collapsed to one column is parsed, and still broken."""
    assert parsed["maxTableCols"] >= 3, f"widest table has {parsed['maxTableCols']} columns"
    assert parsed["maxTableRows"] >= 6, f"longest table has {parsed['maxTableRows']} rows"


def test_lists_nest(parsed):
    """
    Indentation in these files is 2, 3 and 5 spaces for the same depth, so
    nesting is relative. A parser that assumed a step would flatten most of it.
    """
    assert parsed["deepestList"] >= 2, "no nested list was found in a corpus with 649 nested bullets"


def test_task_state_is_captured(parsed):
    assert parsed["taskItems"] >= 30, f"only {parsed['taskItems']} task items found, expected 32"


def test_only_a_declared_alert_becomes_a_tone(parsed):
    """
    A tone is a severity. It comes from the document's own [!KIND] marker and
    nowhere else, because classifying a quote by keyword would have the studio
    assigning a severity nobody wrote.
    """
    assert parsed["tones"].get("important", 0) >= 2, (
        f"the corpus declares two [!IMPORTANT] alerts, parsed {parsed['tones']}"
    )
    census = parsed["census"]
    assert sum(parsed["tones"].values()) < census["callout"], (
        "every blockquote came back with a tone, so something is classifying them"
    )


# ---------------------------------------------------------------------------
# The dialect decisions, each pinned against the change that would undo it
# ---------------------------------------------------------------------------

def test_an_ascii_sketch_is_not_a_table(parsed):
    """
    Several files draw an interface mock out of pipes. The delimiter row is the
    only thing that tells one from a table, and reading a sketch as a table
    shreds it into cells.
    """
    case = parsed["cases"]
    assert "table" not in case["asciiMockIsNotATable"], (
        f"a pipe sketch with no delimiter row was read as a table: {case['asciiMockIsNotATable']}"
    )
    assert case["realTableIsATable"] == ["table"], case["realTableIsATable"]
    assert case["realTableAlign"] == ["left", "right"], (
        f"the delimiter row's alignment was not read: {case['realTableAlign']}"
    )


def test_a_pipe_inside_a_code_span_does_not_split_a_cell(parsed):
    """
    Splitting there shifts every later cell one column left, which is silent
    corruption rather than a visible break.
    """
    assert parsed["cases"]["pipeInsideCode"] == ["a", "`x | y`", "b"], parsed["cases"]["pipeInsideCode"]
    assert parsed["cases"]["escapedPipe"] == ["a | b", "c"], parsed["cases"]["escapedPipe"]


def test_underscore_never_emphasises(parsed):
    """
    This corpus is snake_case throughout. Emphasis on the underscore would eat
    identifiers out of a technical document, which is worse than missing an
    italic nobody wrote.
    """
    case = parsed["cases"]
    assert case["snakeCase"] == "set word_count from li_at and taplio_vault_archive_backup.json", (
        f"an identifier was mangled by emphasis: {case['snakeCase']!r}"
    )
    assert "em" not in case["underscoreNeverEmphasises"], case["underscoreNeverEmphasises"]
    assert "em" in case["asteriskDoesEmphasise"], case["asteriskDoesEmphasise"]
    assert case["arithmeticIsNotEmphasis"] == "2 * 3 * 4", case["arithmeticIsNotEmphasis"]


def test_math_needs_a_latex_command(parsed):
    """
    There is no typesetter here, so math is carried through as source. Without
    this rule a price or a shell variable becomes an equation.
    """
    case = parsed["cases"]
    assert "math" not in case["priceIsNotMath"], f"a dollar amount became math: {case['priceIsNotMath']}"
    assert "math" in case["latexIsMath"], f"a LaTeX command was not read as math: {case['latexIsMath']}"


def test_emphasis_can_hold_a_code_span(parsed):
    """
    Bold in these documents routinely wraps a code span. Flat text inside
    strong would print the backticks, which is what the first draft did.
    """
    case = parsed["cases"]["boldHoldingCode"]
    assert case["outer"][0] == "strong", case["outer"]
    assert "code" in case["inner"], f"the code span inside bold was flattened: {case['inner']}"


def test_a_fence_is_parsed_before_anything_inside_it(parsed):
    """
    A bash block's comment is not a heading and its pipes are not a table. This
    is the single largest source of wrong markdown rendering.
    """
    case = parsed["cases"]
    assert case["hashInsideFenceIsNotAHeading"] == ["code"], case["hashInsideFenceIsNotAHeading"]
    assert "# install" in case["fenceKeepsItsBody"], case["fenceKeepsItsBody"]


def test_nesting_follows_relative_indentation(parsed):
    case = parsed["cases"]["nestedByRelativeIndent"]
    assert case["kind"] == "list"
    assert case["items"] == 2, f"an ordered list of two items parsed as {case['items']}"
    assert case["firstItemBlocks"] == ["paragraph", "list"], case["firstItemBlocks"]
    assert case["nestedItems"] == 2, f"the nested list holds {case['nestedItems']} items"


def test_a_plain_item_beside_task_items_keeps_its_own_state(parsed):
    """
    checked is per item, not per list.

    The renderer used to switch to the task treatment only when every item was
    a task, so one plain bullet among them sent the whole list down the bullet
    path where no box is drawn and every tick silently vanished. Nothing in the
    corpus mixes them, which is precisely why it would not have been noticed.
    """
    assert parsed["cases"]["taskState"] == [True, False, None], parsed["cases"]["taskState"]


def test_only_the_five_declared_alert_kinds_are_tones(parsed):
    case = parsed["cases"]
    assert case["declaredTone"] == "important", case["declaredTone"]
    assert case["plainQuoteHasNoTone"] is None, case["plainQuoteHasNoTone"]
    assert case["unknownAlertIsNotATone"] is None, (
        f"an invented alert kind became a tone: {case['unknownAlertIsNotATone']}"
    )


def test_repeated_headings_get_distinct_anchors(parsed):
    """
    Several files repeat a heading. A contents rail whose entries all scroll to
    the first match reads as broken navigation.
    """
    slugs = parsed["cases"]["slugCollisions"]
    assert len(slugs) == len(set(slugs)), f"duplicate anchors: {slugs}"


def test_the_outline_starts_below_the_title(parsed):
    """
    The level one heading is the document's name and is rendered as such, so it
    is not also an entry in its own contents list.
    """
    assert parsed["cases"]["outlineSkipsTheTitle"] == [2, 3], parsed["cases"]["outlineSkipsTheTitle"]


def test_a_search_hit_and_a_heading_agree_on_the_anchor(parsed):
    """
    Clicking a result lands on the passage because the section title the FTS
    index stores and the heading the parser slugs reduce to the same anchor.
    The index sanitises an en dash to a hyphen before storing it, so the two
    spellings have to converge, which they do because neither is alphanumeric.
    """
    case = parsed["cases"]
    assert case["slugOfAnIndexedSection"] == "4-1080-1080-multi-slide-pdf-carousel-builder", (
        case["slugOfAnIndexedSection"]
    )
    raw, sanitised = case["slugOfAnEnDashSection"]
    assert raw == sanitised, (
        f"the index's sanitised heading and the parser's raw one slug differently: {raw} vs {sanitised}"
    )


# ---------------------------------------------------------------------------
# Nothing in a document is ever interpreted as markup
# ---------------------------------------------------------------------------

def test_angle_bracket_placeholders_survive(parsed):
    """
    Several files put placeholders in prose. A renderer that went through
    innerHTML would delete them, because the parser would treat them as tags.
    """
    text = parsed["cases"]["placeholdersSurvive"]
    assert "<version>" in text and "<filename>" in text, f"a placeholder was swallowed: {text!r}"


def test_markup_in_a_document_stays_text(parsed):
    """
    A playbook file is allowed to contain markup. The parser emits spans, not
    HTML, so the only markup on screen is the markup the renderer wrote.
    """
    kinds = parsed["cases"]["scriptTagIsInertText"]
    assert set(kinds) <= {"text"}, f"a tag in the document became something other than text: {kinds}"


def test_the_parser_emits_no_html(parsed):
    """
    Held at the source, because this is the property the whole design rests on.
    A helper that started returning a string for a caller to inject would move
    every document in the library into the HTML parser.
    """
    with open(MARKDOWN_MODULE, encoding="utf-8") as handle:
        source = handle.read()
    for forbidden in ("innerHTML", "dangerouslySetInnerHTML", "outerHTML", "insertAdjacentHTML"):
        assert forbidden not in source, f"{forbidden} appears in the markdown parser"


def test_the_renderer_never_injects_html():
    """The same property on the drawing side."""
    view = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "DocumentView.tsx")
    if not os.path.exists(view):
        pytest.skip("DocumentView.tsx is not present in this checkout")
    with open(view, encoding="utf-8") as handle:
        source = handle.read()
    assert "dangerouslySetInnerHTML" not in source, (
        "the document renderer hands playbook content to the HTML parser"
    )
