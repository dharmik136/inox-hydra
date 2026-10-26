import type { OnboardingState } from "@/lib/api";

/**
 * Whether Setup's required steps are done: the bridge has been heard from,
 * you confirmed which profile is yours and it has been read, and your posts
 * were read to the end of the list.
 *
 * Importing LinkedIn's archive is offered in Setup and is not required: a
 * creator who skips it is not sent back to Setup on every start.
 *
 * The one rule for it. Setup says "Setup is done" by it, and the studio opens
 * on Setup until it is true (sections report, decision 5); before this they
 * disagreed, and the studio opened on Today as soon as you confirmed your
 * profile while Setup still listed steps to do.
 */
export function setupDone(state: OnboardingState): boolean {
  const { steps } = state;
  return steps.bridge && steps.identity && !!state.identity?.profile_observed_at && !!steps.history;
}
