import type { SectionId } from "@/lib/navigation";

/**
 * Work that has not been saved, wherever in the studio it is held.
 *
 * There is no autosave. Each screen holding edits that are not on disk
 * registers a check here, and three things read the checks:
 *
 * - The page. While any check reports unsaved work, reloading, closing the
 *   tab, or pressing Back past the studio's first screen asks first. Before
 *   this, all three discarded the Composer's text without a word.
 * - App's navigation. Leaving a screen whose edits live only on that screen
 *   (its `section`) asks first, from the rail, the tray, the palette and the
 *   browser's Back. The Composer registers no section: its draft lives in
 *   App and survives moving between screens.
 * - Anything that reloads the studio, such as switching profile, through
 *   hasUnsavedWork and unsavedWorkLabels. Having asked, it reloads with
 *   reloadStudio, so the page guard does not ask a second time.
 *
 * A screen registers when it mounts and unregisters when it unmounts:
 *
 *   useEffect(() => registerUnsavedWork("brand-studio", {
 *     label: "Your Brand Studio edits",
 *     section: "settings",
 *     check: () => dirtyRef.current,
 *   }), []);
 */
export interface UnsavedWork {
  /** What would be lost, as it begins a sentence: "The post in the Composer". */
  label: string;
  /** The screen whose edits are lost by leaving it. Omit when they survive. */
  section?: SectionId;
  /** True while there is work that would be lost. Called often; keep it cheap. */
  check: () => boolean;
}

const registered = new Map<string, UnsavedWork>();

// Set by reloadStudio, for a reload the author has already agreed to.
let agreed = false;

function onBeforeUnload(event: BeforeUnloadEvent): void {
  if (agreed || !hasUnsavedWork()) return;
  // Either is enough for a current browser to ask; older Chromium needed
  // returnValue set as well.
  event.preventDefault();
  event.returnValue = "";
}

let listening = false;

/** Registers a screen's unsaved work under `id`. Returns the unregister function. */
export function registerUnsavedWork(id: string, work: UnsavedWork): () => void {
  registered.set(id, work);
  if (!listening && typeof window !== "undefined") {
    window.addEventListener("beforeunload", onBeforeUnload);
    listening = true;
  }
  return () => {
    if (registered.get(id) === work) registered.delete(id);
  };
}

function dirty(): UnsavedWork[] {
  return Array.from(registered.values()).filter((work) => work.check());
}

/** Whether anything anywhere would be lost by reloading the studio. */
export function hasUnsavedWork(): boolean {
  return dirty().length > 0;
}

/** What would be lost by reloading, for a question that names it. */
export function unsavedWorkLabels(): string[] {
  return dirty().map((work) => work.label);
}

/** What would be lost by leaving `section` for another screen. */
export function unsavedWorkLeaving(section: SectionId): string[] {
  return dirty()
    .filter((work) => work.section === section)
    .map((work) => work.label);
}

/**
 * Asks before leaving a screen whose edits would be lost, and says whether
 * to go ahead. True at once when nothing would be lost.
 */
export function confirmLeaving(section: SectionId): boolean {
  const lost = unsavedWorkLeaving(section);
  if (lost.length === 0) return true;
  return window.confirm(`${lost.join(" and ")} ${lost.length === 1 ? "has" : "have"} unsaved changes. Leave and discard them?`);
}

/**
 * Reloads the studio once the author has agreed to lose what is unsaved, for
 * example by confirming a profile switch. Without it the page guard asked
 * again, and answering that second question with Stay left the page showing
 * one profile while the server had already switched to another.
 */
export function reloadStudio(): void {
  agreed = true;
  window.location.reload();
}
