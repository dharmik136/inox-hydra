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
  // \p{M} is the Unicode Mark category. The backend tests unicodedata.combining
  // instead, which is very slightly narrower, but both cover the two marks the
  // formatters actually emit and \p{M} is the closest thing JavaScript exposes.
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
