/**
 * Which templates the hook rail shows, when the opt-in engineering pack is
 * also in the library.
 *
 * MAKING.md M-1: `get_templates` orders by `velocity_score DESC`, and every
 * engineering pack form carries a score while a starter form carries none,
 * which SQLite sorts last in that order. So a rail asking for its usual 12
 * used to come back 12 of 12 pack forms: the pack did not add to the rail,
 * it evicted the creator's own neutral forms from it entirely.
 *
 * The fix here is purely client side: the caller fetches the whole library
 * (nothing here re-sorts the server's ranking within a source), and this
 * picks the rail from it so that the pack can only ever add to what a
 * creator starts with, never replace half or more of it.
 */

/** The one shape this module needs from a template; `HookTemplate` satisfies it. */
export interface RailCandidate {
  velocity_score: number | null;
}

export interface RailPick<T> {
  item: T;
  /** True when this slot came from the opt-in pack rather than a starter form. */
  fromPack: boolean;
}

/** The rail never grows or shrinks because of the pack: it is always this many specimens. */
export const RAIL_SIZE = 12;

/**
 * Picks `railSize` specimens, keeping at least half of them starter forms
 * whenever the pack is present, rather than letting a higher score alone
 * decide. A starter form carries no `velocity_score` (null); a pack form
 * does. Within each source, the server's own order is kept.
 */
export function selectRailTemplates<T extends RailCandidate>(templates: T[], railSize: number = RAIL_SIZE): RailPick<T>[] {
  const starters = templates.filter((t) => t.velocity_score === null);
  const pack = templates.filter((t) => t.velocity_score !== null);

  const minStarters = Math.min(starters.length, Math.ceil(railSize / 2));
  const packBudget = Math.max(0, railSize - minStarters);
  const chosenPack = pack.slice(0, packBudget);
  // Slots the pack did not fill (because it is absent, small, or capped at
  // half) go to more starters, so a library with no pack still fills the
  // rail with its usual 12 neutral forms.
  const remaining = railSize - minStarters - chosenPack.length;
  const chosenStarters = starters.slice(0, minStarters + Math.max(0, remaining));

  // Interleaved by source, starter first, so the pack reads as an addition
  // threaded through the rail rather than a block at one end of it.
  const picked: RailPick<T>[] = [];
  let si = 0;
  let pi = 0;
  while (si < chosenStarters.length || pi < chosenPack.length) {
    if (si < chosenStarters.length) picked.push({ item: chosenStarters[si++], fromPack: false });
    if (pi < chosenPack.length) picked.push({ item: chosenPack[pi++], fromPack: true });
  }
  return picked.slice(0, railSize);
}
