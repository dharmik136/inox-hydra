/**
 * Measuring text the way a reader sees it.
 *
 * This is the client side of studio/backend/formatters.py::_measurable_text,
 * and it has to correct for two separate distortions, only one of which the
 * Python side has.
 *
 * 1. Combining marks. to_strikethrough and to_underline decorate by inserting
 *    U+0336 or U+0332 after every character. Those are real code points, so a
 *    struck 80 character hook measures as 160. That flipped the backend's fold
 *    verdict from safe to unsafe until it was fixed, and the fold verdict is
 *    this product's central claim.
 *
 * 2. Surrogate pairs, which is a JavaScript-only hazard. Mathematical sans
 *    serif bold lives above the basic plane, so each bolded letter is two
 *    UTF-16 code units and String.length doubles. The Python comment says math
 *    bold "measures correctly without help", and in Python it does, because
 *    len() counts code points there. Porting the mark stripping alone would
 *    have left bold reporting twice its length here.
 *
 * Every character count in the interface goes through these. A raw .length on
 * draft text is a bug waiting for someone to press the bold button.
 */

/** Strips decoration marks, leaving what a reader actually perceives. */
export function measurableText(text: string): string {
  if (!text) return "";
  // \p{M} is the Unicode Mark category, and the backend strips by the same
  // category. It used to test unicodedata.combining, which kept the vowel
  // signs of Hindi and Gujarati, so the two sides put the fold of one post in
  // different places. tests/test_qc_f1a_counts.py holds them together.
  return Array.from(text)
    .filter((ch) => !/\p{M}/u.test(ch))
    .join("");
}

/** How long the text reads, in characters a person would count. */
export function measurableLength(text: string): number {
  // Array.from iterates code points, so a surrogate pair counts once.
  return Array.from(measurableText(text)).length;
}

/** Words, counted on the undecorated text for the same reason. */
export function measurableWordCount(text: string): number {
  const stripped = measurableText(text).trim();
  return stripped ? stripped.split(/\s+/).length : 0;
}

/** LinkedIn's limit on the length of a post, as the Audit's Gate 2 checks it. */
export const POST_LIMIT_CHARS = 3000;

/**
 * How long the post is against a length limit: every character as stored.
 *
 * Not measurableLength. A limit counts what is saved and sent, and a struck
 * letter is stored as two characters even though a reader sees one. Stripping
 * marks also dropped the vowel signs of Hindi and Gujarati, so a Hindi post
 * the Composer's strip called 2,964 characters was 4,332 to Gate 2, which blocked it at
 * 3,000. Code points, the same as len() on the server, which is what Gate 2
 * and the 5,000 character save limit count. Which count LinkedIn itself
 * applies is not something this product has measured.
 */
export function storedLength(text: string): number {
  return Array.from(text).length;
}

/**
 * The index into the RAW string at which the measurable count reaches `target`.
 *
 * The fold ruler needs this. It has to place a mark at the 180th character a
 * reader sees, but it has to place it inside the raw string the textarea holds,
 * and the two indices diverge the moment any decoration is applied. Returns the
 * full raw length when the text never reaches the target.
 */
export function rawIndexAtMeasurableOffset(text: string, target: number): number {
  let measured = 0;
  let rawIndex = 0;

  for (const ch of text) {
    const isMark = /\p{M}/u.test(ch);

    // Stop only on the next base character, never on a mark. Returning as soon
    // as the count is reached would land between the target character and its
    // own decoration, and a DOM Range that ends inside a grapheme cluster is
    // asking the browser where half a letter is. Consuming the trailing marks
    // keeps the cluster whole.
    if (measured >= target && !isMark) return rawIndex;

    if (!isMark) measured += 1;
    rawIndex += ch.length; // ch is a full code point, so this advances by 1 or 2.
  }

  return rawIndex;
}

/**
 * A line a reader sees as blank: nothing on it but spacing.
 *
 * Not only "\n\n". Text pasted from LinkedIn or another editor keeps blank
 * lines holding a space or a no-break space, and LinkedIn writers put U+2800
 * on them so the gap survives posting. [^\S\n] is any whitespace except the
 * line break; the rest are characters that take no room but are not
 * whitespace to a regular expression.
 */
const BLANK_LINE = /\n(?:[^\S\n]|[\u2800\u200b\u200c\u200d\u2060\ufeff])*\n/;

/** Where the opening paragraph ends: the index of its blank line, or -1. */
export function openingEnd(text: string): number {
  const match = BLANK_LINE.exec(text);
  return match ? match.index : -1;
}

/**
 * Replaces the opening paragraph, which is what applying a hook means.
 *
 * A paragraph ends at the first blank line. When the draft has no blank line
 * the whole thing is the opening, and when it is empty the hook simply becomes
 * the draft. Testing only for "\n\n" took a blank line that held a space for
 * part of a paragraph, and a hook then replaced the whole post.
 */
export function swapOpening(draft: string, hook: string): string {
  if (!draft.trim()) return hook;
  const end = openingEnd(draft);
  return end === -1 ? hook : hook + draft.slice(end);
}
