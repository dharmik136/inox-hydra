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
