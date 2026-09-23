import { useCallback, useEffect, useMemo, useState } from "react";
import { PanelRight } from "lucide-react";
import { StudioRail } from "@/components/StudioRail";
import { NavigationTray } from "@/components/NavigationTray";
import { ContextBar, type SaveState } from "@/components/ContextBar";
import { ComposerCanvas, FOLD_CHARS } from "@/components/ComposerCanvas";
import { CommandPalette } from "@/components/CommandPalette";
import { Inspector } from "@/components/Inspector";
import { sectionById, type SectionId } from "@/lib/navigation";

/** Where the working draft lives until this is wired to the backend drafts API. */
const DRAFT_KEY = "inox.studio.draft";

/** Average adult reading speed. Used for an estimate that is labelled as one. */
const WORDS_PER_MINUTE = 200;

export default function App() {
  const [active, setActive] = useState<SectionId>("composer");
  const [trayOpen, setTrayOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [draft, setDraft] = useState(() => window.localStorage.getItem(DRAFT_KEY) ?? "");
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [savedAt, setSavedAt] = useState<string | null>(null);

  // Dark first, matching docs/UI_CONVENTIONS.md: an unstamped document gets
  // the dark palette, and data-theme="light" is the opt out.
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const telemetry = useMemo(() => {
    const chars = draft.length;
    const words = draft.trim() ? draft.trim().split(/\s+/).length : 0;
    return {
      chars,
      // Two different readings, because one number cannot serve both cases.
      // Under the fold the useful quantity is how much budget is left, so a
      // percentage. Past it, the percentage is meaningless (a 352 character
      // post is not "100% of fold", it is 172 characters beyond it) and what
      // the author needs is the overshoot.
      pastFold: chars > FOLD_CHARS,
      foldLabel:
        chars > FOLD_CHARS
          ? `${chars - FOLD_CHARS} past fold`
          : `${Math.round((chars / FOLD_CHARS) * 100)}% of fold`,
      readSeconds: Math.round((words / WORDS_PER_MINUTE) * 60),
    };
  }, [draft]);

  const onChangeDraft = useCallback((next: string) => {
    setDraft(next);
    setSaveState("dirty");
    setSavedAt(null);
  }, []);

  /**
   * Save writes the draft and only then reports that it did.
   *
   * This product has a run of fixes for surfaces that announced success
   * without performing the work, so the timestamp is stamped from the result
   * of the write and a failed write leaves the mark unchanged rather than
   * showing SAVED.
   */
  const onSave = useCallback(() => {
    setSaveState("saving");
    try {
      window.localStorage.setItem(DRAFT_KEY, draft);
      const now = new Date();
      setSavedAt(
        [now.getHours(), now.getMinutes(), now.getSeconds()]
          .map((part) => String(part).padStart(2, "0"))
          .join(":"),
      );
      setSaveState("saved");
    } catch {
      // Quota exceeded, or storage disabled. Report the truth: the edits are
      // still only in memory, so the mark goes back to UNSAVED rather than to
      // a reassuring UNCHANGED.
      setSaveState("dirty");
      setSavedAt(null);
    }
  }, [draft]);

  const section = sectionById(active);

  return (
    <div className="flex h-full w-full overflow-hidden bg-canvas">
      <StudioRail
        active={active}
        onSelect={setActive}
        trayOpen={trayOpen}
        onToggleTray={() => setTrayOpen((open) => !open)}
      />

      <div className="relative flex min-w-0 flex-1 flex-col">
        <ContextBar
          kind={active === "composer" ? "POST" : section.label.toUpperCase()}
          draftRef="DRAFT 01"
          title={draft.trim().split("\n")[0]?.slice(0, 72) || "Untitled draft"}
          chars={telemetry.chars}
          foldLabel={telemetry.foldLabel}
          pastFold={telemetry.pastFold}
          readSeconds={telemetry.readSeconds}
          saveState={saveState}
          savedAt={savedAt}
          onSave={onSave}
          onPublish={() => setInspectorOpen(true)}
        />

        <div className="relative flex min-h-0 flex-1">
          <main className="min-w-0 flex-1 overflow-y-auto">
            {active === "composer" ? (
              <ComposerCanvas value={draft} onChange={onChangeDraft} />
            ) : (
              <SurfacePlaceholder label={section.label} blurb={section.blurb} />
            )}
          </main>

          <Inspector open={inspectorOpen} onClose={() => setInspectorOpen(false)} draft={draft} />

          {!inspectorOpen && (
            <button
              type="button"
              onClick={() => setInspectorOpen(true)}
              aria-label="Open inspector"
              className="absolute top-3 right-3 grid size-8 place-items-center rounded-md border border-edge bg-raised text-ink-muted transition-colors hover:text-ink-primary"
            >
              <PanelRight className="size-4" strokeWidth={1.75} aria-hidden="true" />
            </button>
          )}

          <NavigationTray
            open={trayOpen}
            active={active}
            onSelect={setActive}
            onClose={() => setTrayOpen(false)}
          />
        </div>
      </div>

      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        onNavigate={setActive}
        onToggleTheme={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
        onToggleInspector={() => setInspectorOpen((open) => !open)}
      />
    </div>
  );
}

/**
 * Stands in for a surface that has not been built yet, and says so. Blueprint
 * build order puts CRM, swipe file and analytics in phase 4, so these are
 * genuinely empty rather than pending data.
 */
function SurfacePlaceholder({ label, blurb }: { label: string; blurb: string }) {
  return (
    <div className="mx-auto flex h-full max-w-[68ch] flex-col justify-center px-10 py-12">
      <p className="studio-label">Not built yet</p>
      <h2 className="studio-title mt-2">{label}</h2>
      <p className="mt-3 max-w-prose text-sm leading-relaxed text-ink-secondary">{blurb}.</p>
      <p className="studio-meta mt-6">
        PRESS <span className="text-ink-primary">CTRL K</span> FOR THE COMMAND PALETTE
      </p>
    </div>
  );
}
