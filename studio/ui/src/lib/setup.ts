import type { OnboardingState } from "@/lib/api";

/**
 * Whether Setup is done: the bridge has been heard from, you confirmed which
 * profile is yours and it has been read, the archive step is done, and your
 * posts were read to the end of the list.
 *
 * The one rule for it. Setup says "Setup is done" by it, and the studio opens
 * on Setup until it is true (sections report, decision 5); before this they
 * disagreed, and the studio opened on Today as soon as you confirmed your
 * profile while Setup still listed three steps to do.
 */
export function setupDone(state: OnboardingState): boolean {
  const { steps } = state;
  return (
    steps.bridge &&
    steps.identity &&
    !!state.identity?.profile_observed_at &&
    steps.archive &&
    !!steps.history
  );
}
