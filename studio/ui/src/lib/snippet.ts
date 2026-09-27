import { parseInline, spanText, type Span } from "@/lib/markdown";

/**
 * Splitting a search snippet into plain runs and matched runs.
 *
 * FTS5 returns each hit with the matched terms wrapped in <mark> tags, and the
 * first version of the docs surface rendered that string as text on the
 * grounds that it is database content. That reasoning is right and the result
 * was wrong: the reader saw the literal characters "<mark>Hook</mark>" instead
 * of a highlight, on every hit of every search.
 *
 * The fix is not dangerouslySetInnerHTML. A playbook file is allowed to
 * contain markup, and handing it to the parser would render whatever it
 * contains. Instead the one marker pair the index emits is parsed out here and
 * the caller renders each run as its own element, so the match is highlighted
 * and nothing else in the string is ever interpreted.
 */

export interface SnippetRun {
  text: string;
  /** True when the index marked this run as a hit on the search term. */
  matched: boolean;
}

const OPEN = "<mark>";
const CLOSE = "</mark>";

export function splitSnippet(snippet: string): SnippetRun[] {
  if (!snippet) return [];

  const runs: SnippetRun[] = [];
  let cursor = 0;

  while (cursor < snippet.length) {
    const open = snippet.indexOf(OPEN, cursor);
    if (open === -1) break;

    // An opener with no closer is not a highlight, it is a document that
    // happens to contain the characters. Stop parsing and keep the remainder
    // verbatim rather than swallowing the rest of the snippet.
    const close = snippet.indexOf(CLOSE, open + OPEN.length);
    if (close === -1) break;

    if (open > cursor) {
      runs.push({ text: snippet.slice(cursor, open), matched: false });
    }
    runs.push({ text: snippet.slice(open + OPEN.length, close), matched: true });
    cursor = close + CLOSE.length;
  }

  if (cursor < snippet.length) {
    runs.push({ text: snippet.slice(cursor), matched: false });
  }

  // An empty marker pair contributes nothing to read and would otherwise
  // render an empty highlight box.
  return runs.filter((run) => run.text.length > 0);
}


/**
 * A snippet as prose, with the match still marked.
 *
 * splitSnippet above solves one half: the FTS5 markers become runs instead of
 * characters on screen. The other half only became visible once results were
 * drawn at reading width, where a snippet is three lines rather than a wrapped
 * fragment in a 300px rail. FTS5 returns a window onto the INDEXED SOURCE, so
 * what came back was markdown: "## 4. Security Model", "* **Provider Key**:
 * `ollama`", a trailing "---". Exactly the defect the document reader had,
 * one layer down, and for the same reason: a markdown fragment shown as if it
 * were prose.
 *
 * Block markers are dropped rather than rendered, because a snippet is a
 * preview of a passage and not the passage: there is no heading to draw, no
 * list to indent, no rule to place. Inline markup is parsed instead of
 * stripped, so a bolded term stays bold and a code span stays monospaced,
 * which is the part that carries meaning in a technical document.
 *
 * Cleaning happens before the markers are split, so the marks travel with the
 * text they surround. A bold run that straddles a marker boundary is not
 * recognised in either half and degrades to showing its asterisks, which is a
 * fragment of one result rather than a wrong reading.
 */

/**
 * Delimiters a window cannot be trusted to have cut cleanly.
 *
 * A fragment is a fixed width view onto markdown, so it routinely opens or
 * closes inside a pair, and the hit markers cut it again. Two delimiters that
 * were never partners in the source then sit next to each other and the parser
 * dutifully pairs them.
 *
 * Two rules, and the difference between them is what a wrong answer asserts.
 *
 * Emphasis is dropped only when its count is odd, which is proof the window
 * cut through a pair. An even count is usually right, and when it is not, the
 * cost is the wrong words in bold: a misplaced emphasis, not a false statement
 * about what the text is.
 *
 * Backticks are dropped always. A mis-paired code span does not merely style
 * the wrong run, it claims that run IS code, and a whole sentence set in
 * monospace is the interface asserting something about the content that is not
 * true. One result read "Generates a 1080 by 1080 multi-page PDF ready for
 * LinkedIn" in a code box. Measured against the corpus the cost is small and
 * the benefit is categorical: inline code here is a median of 15 characters,
 * so what a preview loses is the monospace on a short identifier that still
 * reads correctly as text, and the document itself renders it properly.
 */
function withoutUnpairableDelimiters(text: string): string {
  let out = text.split("`").join("");
  const bold = out.split("**").length - 1;
  if (bold % 2 === 1) out = out.split("**").join("");
  return out;
}

/** Leading and embedded block syntax that has no meaning inside a fragment. */
function withoutBlockMarkers(snippet: string): string {
  return snippet
    // ATX headings, wherever the window happens to have started.
    .replace(/(^|\s)#{1,6}\s+/g, "$1")
    // Bullet and ordered markers.
    .replace(/(^|\s)[-*+]\s+/g, "$1")
    .replace(/(^|\s)\d{1,3}[.)]\s+/g, "$1")
    // Blockquote markers and horizontal rules.
    .replace(/(^|\s)>\s+/g, "$1")
    .replace(/(^|\s)(?:-{3,}|\*{3,}|_{3,})(?=\s|$)/g, "$1")
    // Table pipes, which a window over a table row is otherwise full of,
    // and the rules and box drawing that a window over a fenced diagram is.
    .replace(/\s*\|\s*/g, " ")
    .replace(/[-=+_~]{3,}/g, " ")
    // Half a link. The window cuts between the label and the target often
    // enough that "](#module-04-viral-swipe-file)" arrived in a result as
    // literal characters; the label it belonged to was outside the window.
    .replace(/\]\([^)\s]*\)/g, "")
    .replace(/\[(?![^\]]*\])/g, "")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

export interface SnippetSpanRun {
  /** Inline spans, so bold and code survive into the preview. */
  spans: Span[];
  /** True when the index marked this run as a hit on the search term. */
  matched: boolean;
}

/**
 * Removes delimiters the parser did not consume.
 *
 * A snippet is a fixed width window onto the source, so it routinely opens or
 * closes inside a bolded phrase or a code span, and the hit markers split the
 * text again. Patching one delimiter at a time was whack a mole: the first
 * pass fixed a dangling "**" and left dangling backticks and a stray rule in
 * five searches out of five.
 *
 * The general rule is simpler and comes from the parser itself. parseInline
 * consumes every BALANCED pair, so anything still sitting in a text span is by
 * definition unbalanced inside this window, which means it marks nothing and
 * is just a character the reader has to look past. A "*" or a backtick inside
 * a pair that did close is held in a code or emphasis span and is never
 * touched here.
 *
 * The trade is deliberate and local: a genuine loose asterisk in prose
 * disappears from the PREVIEW. It is still there in the document, which is
 * where someone reads it.
 */
function withoutLooseDelimiters(spans: Span[]): Span[] {
  const clean = (text: string): string =>
    text
      .replace(/\*\*|__/g, "")
      .replace(/`/g, "")
      .replace(/[-=+_~]{3,}/g, " ")
      .replace(/[ \t]{2,}/g, " ");

  return spans
    .map((span) => (span.kind === "text" ? { ...span, text: clean(span.text) } : span))
    .filter((span) => span.kind !== "text" || span.text.length > 0);
}

/**
 * Any markdown fragment, as prose.
 *
 * A snippet is not the only window onto the source. A library excerpt is the
 * document's own opening line cut at 220 characters, and it is shown on the
 * landing cards, in a topic listing and beside a name match, so it arrives
 * with the same half of a bold run or half of a link that a snippet does.
 * One helper for both, rather than the same fix written twice and drifting.
 */
export function readableInline(markdown: string): Span[] {
  if (!markdown) return [];
  return withoutLooseDelimiters(parseInline(withoutUnpairableDelimiters(markdown)));
}

/**
 * The same fragment as a plain string.
 *
 * For the places a run of spans cannot go: an accessible name, a title
 * attribute, a breadcrumb that is uppercased. A heading like
 * "4.1 Global Sidebar (`#global-sidebar`)" is markdown too, and it was
 * reaching those with its backticks intact.
 */
export function readablePlain(markdown: string): string {
  return spanText(readableInline(markdown)).replace(/\s{2,}/g, " ").trim();
}

export function readableSnippet(snippet: string): SnippetSpanRun[] {
  if (!snippet) return [];
  return splitSnippet(withoutBlockMarkers(snippet))
    .map((run) => ({
      spans: withoutLooseDelimiters(parseInline(withoutUnpairableDelimiters(run.text))),
      matched: run.matched,
    }))
    .filter((run) => run.spans.length > 0);
}
