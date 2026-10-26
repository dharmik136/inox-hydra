/**
 * The engine's cut for a ratio, printed one way everywhere.
 *
 * results.difference (studio/backend/results.py) calls a ratio "more" at
 * NOTABLE_HIGH and above and "fewer" at NOTABLE_LOW and below; between them
 * it answers "none", a difference the creator's own posts cannot separate.
 * Four screens coloured a ratio green from 1.2, so a 1.22x line read as a
 * gain beside an engine that had just said it was nothing.
 *
 * The numbers live here once, and tests/test_ratio_cut_is_one_number.py
 * reads this file and results.py because nothing else joins them, the way
 * the fold and the gap in days are held.
 */
export const NOTABLE_HIGH = 1.25;
export const NOTABLE_LOW = 0.8;

/** What the engine would say about a ratio: "more", "fewer" or "none". */
export function verdictOf(ratio: number | null | undefined): "more" | "fewer" | "none" | null {
  if (ratio === null || ratio === undefined || Number.isNaN(ratio)) return null;
  if (ratio >= NOTABLE_HIGH) return "more";
  if (ratio <= NOTABLE_LOW) return "fewer";
  return "none";
}

/**
 * The text colour a ratio is drawn in: green for "more", orange for "fewer",
 * and the quiet colour the caller names for "none" or no ratio at all.
 */
export function ratioTone(ratio: number | null | undefined, quiet = "text-ink-muted"): string {
  const verdict = verdictOf(ratio);
  if (verdict === "more") return "text-signal-green-text";
  if (verdict === "fewer") return "text-signal-orange-text";
  return quiet;
}
