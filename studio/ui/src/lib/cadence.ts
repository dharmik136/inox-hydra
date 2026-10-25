/**
 * A gap in days, printed one way everywhere.
 *
 * The backend measures a creator's rhythm once, in insights.cadence: the
 * median gap between their posts, how long since the last one, and their
 * longest gap, each rounded to one decimal. Three screens then printed those
 * same numbers three different ways.
 *
 *   Today      0.9 DAYS          toFixed(1)
 *   Queue      0.9 days          toFixed(1)
 *   Patterns   1 days            Math.round, and "1 days" reads as a typo
 *
 * A creator who looked at Today and then at Patterns saw two answers to one
 * question about their own posting, and neither screen said it had rounded.
 * Patterns was worse than inconsistent: it printed
 * `Math.round(days_since_last ?? 0)`, so a rhythm that had never been
 * measured appeared as "0 days", which is a figure the studio does not have.
 *
 * Every screen that prints a gap in days goes through here, and
 * tests/test_one_gap_format.py holds that.
 */

/**
 * What a screen says when the studio has not measured a gap.
 *
 * One wording, because the three screens had three: "NOT MEASURED",
 * "Not measured" and "Unknown". A screen that wants it in capitals
 * upper-cases what it prints, as Today's meta row does.
 */
export const NOT_MEASURED = "Not measured";

/**
 * A gap as "0.9 days", or null when there is no measurement to print.
 *
 * One decimal, always, including a whole number ("1.0 days"): the figure the
 * backend measured is kept to the precision it measured it at, and a creator
 * comparing two screens sees the same digits on both. Null rather than a
 * fallback string, so a caller that wants the number inside a sentence has to
 * decide what the sentence is when there is no number, instead of printing
 * "Not measured between posts".
 */
export function formatDays(value: number | null | undefined): string | null {
  if (value === null || value === undefined || Number.isNaN(value)) return null;
  return `${value.toFixed(1)} days`;
}

/**
 * A gap as "0.9 days", or the not-measured wording.
 *
 * For the common case: a figure standing on its own in a cell or a stat.
 */
export function gapOrNotMeasured(value: number | null | undefined): string {
  return formatDays(value) ?? NOT_MEASURED;
}
