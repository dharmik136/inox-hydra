/**
 * Whether the Composer holds work that has not been saved.
 *
 * There is no autosave, so anything that reloads the studio (switching
 * creator profile does) asks first. App registers the check, because it owns
 * the draft; the profile switcher reads it.
 */
let check: () => boolean = () => false;

export function setUnsavedCheck(next: () => boolean): void {
  check = next;
}

export function hasUnsavedWork(): boolean {
  return check();
}
