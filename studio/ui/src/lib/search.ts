/**
 * Pieces of universal search that are not a network call.
 *
 * Kept out of the palette component so a test can execute them without a
 * browser, the same way lib/snippet.ts and lib/markdown.ts are tested.
 */

/**
 * An instruction to a surface to show one item.
 *
 * The nonce is what makes choosing the same result twice work. Without it the
 * second request is equal to the first, the effect watching it does not run,
 * and a lead you scrolled away from stays where you left it.
 */
export interface SearchFocus {
  id: string;
  anchor?: string | null;
  nonce: number;
}

export interface HighlightRun {
  text: string;
  matched: boolean;
}

/**
 * Splits text into runs, marking every case-insensitive occurrence of a term.
 *
 * Plain runs, never markup: the caller renders each as its own element, so a
 * post that contains angle brackets is shown as written. Terms are matched
 * literally rather than compiled into a pattern, so a search for "c++" or
 * "(draft)" highlights exactly those characters instead of throwing.
 */
export function highlightRuns(text: string, terms: string[]): HighlightRun[] {
  if (!text) return [];
  const needles = terms.map((term) => term.toLowerCase()).filter(Boolean);
  if (!needles.length) return [{ text, matched: false }];

  const lower = text.toLowerCase();
  const runs: HighlightRun[] = [];
  let cursor = 0;

  while (cursor < text.length) {
    let bestAt = -1;
    let bestLength = 0;
    for (const needle of needles) {
      const at = lower.indexOf(needle, cursor);
      if (at === -1) continue;
      // Earliest match wins; on a tie the longer term, so "fold audit" is
      // not split into "fold" and a separate "audit".
      if (bestAt === -1 || at < bestAt || (at === bestAt && needle.length > bestLength)) {
        bestAt = at;
        bestLength = needle.length;
      }
    }
    if (bestAt === -1) break;
    if (bestAt > cursor) runs.push({ text: text.slice(cursor, bestAt), matched: false });
    runs.push({ text: text.slice(bestAt, bestAt + bestLength), matched: true });
    cursor = bestAt + bestLength;
  }

  if (cursor < text.length) runs.push({ text: text.slice(cursor), matched: false });
  return runs;
}

/** Whether every term appears in the text, for filtering the local actions. */
export function matchesAll(text: string, terms: string[]): boolean {
  const lower = text.toLowerCase();
  return terms.every((term) => lower.includes(term.toLowerCase()));
}

/** The words of a query, as the server splits them, so both sides agree. */
export function termsOf(query: string): string[] {
  return query
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 8);
}
