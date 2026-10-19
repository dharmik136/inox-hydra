import type { SectionId } from "@/lib/navigation";

/**
 * Whether the studio holds work that has not been saved.
 *
 * There is no autosave, so anything that reloads the studio (switching
 * creator profile does) asks first. App registers the Composer's check,
 * because it owns the draft; other screens register their own with
 * registerUnsavedWork; the profile switcher reads them all.
 *
 * registerUnsavedWork and unsavedWorkLabels match the registry batch F1a
 * builds in this file (QC 2026-10), which also guards reload, close and
 * navigation; on merge, F1a's version of this file replaces this one.
 */
let check: () => boolean = () => false;

export function setUnsavedCheck(next: () => boolean): void {
  check = next;
}

export interface UnsavedWork {
  /** What would be lost, as it begins a sentence: "Your Brand Studio edits". */
  label: string;
  /** The screen whose edits are lost by leaving it. Omit when they survive. */
  section?: SectionId;
  /** True while there is work that would be lost. Called often; keep it cheap. */
  check: () => boolean;
}

const registered = new Map<string, UnsavedWork>();

/** Registers a screen's unsaved work under `id`. Returns the unregister function. */
export function registerUnsavedWork(id: string, work: UnsavedWork): () => void {
  registered.set(id, work);
  return () => {
    if (registered.get(id) === work) registered.delete(id);
  };
}

/** What would be lost by reloading, for a question that names it. */
export function unsavedWorkLabels(): string[] {
  const labels = check() ? ["The post in the Composer"] : [];
  for (const work of registered.values()) if (work.check()) labels.push(work.label);
  return labels;
}

export function hasUnsavedWork(): boolean {
  return unsavedWorkLabels().length > 0;
}
