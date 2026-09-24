import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PanelRight } from "lucide-react";
import { StudioRail } from "@/components/StudioRail";
import { NavigationTray } from "@/components/NavigationTray";
import { ContextBar, type SaveState } from "@/components/ContextBar";
import { ComposerCanvas, FOLD_CHARS } from "@/components/ComposerCanvas";
import { HookFilmstrip } from "@/components/HookFilmstrip";
import { CommandPalette } from "@/components/CommandPalette";
import { Inspector } from "@/components/Inspector";
import { LeadsSurface } from "@/components/LeadsSurface";
import { SwipeSurface } from "@/components/SwipeSurface";
import { AnalyticsSurface } from "@/components/AnalyticsSurface";
import { BrandStudioSurface } from "@/components/BrandStudioSurface";
import { QueueSurface } from "@/components/QueueSurface";
import { DocsSurface } from "@/components/DocsSurface";
import { CommandSurface } from "@/components/CommandSurface";
import { PublishDialog } from "@/components/PublishDialog";
import { DevtoolsSurface } from "@/components/DevtoolsSurface";
import { STUDIO_SECTIONS, sectionById, type SectionId } from "@/lib/navigation";
import { cn } from "@/lib/utils";
import {
  createDraft,
  fetchDevtoolsStatus,
  fetchLatestDraft,
  generateHooks,
  updateDraft,
  type GeneratedHook,
} from "@/lib/api";
import { measurableLength, measurableWordCount } from "@/lib/text";

/** Average adult reading speed. Used for an estimate that is labelled as one. */
const WORDS_PER_MINUTE = 200;

/**
 * Replaces the opening paragraph, which is what applying a hook means.
 *
 * A paragraph ends at the first blank line. When the draft has no blank line
 * the whole thing is the opening, and when it is empty the hook simply becomes
 * the draft.
 */
function swapFirstParagraph(draft: string, hook: string): string {
  if (!draft.trim()) return hook;
  const breakIndex = draft.indexOf("\n\n");
  return breakIndex === -1 ? hook : hook + draft.slice(breakIndex);
}

export default function App() {
  const [active, setActive] = useState<SectionId>("composer");
  const [trayOpen, setTrayOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [draft, setDraft] = useState("");
  const [draftId, setDraftId] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [publishOpen, setPublishOpen] = useState(false);

  // Devtools is a maintainer surface. Every route behind it answers 404 in
  // a consumer build, so the rail does not offer a destination that cannot
  // work. Asked once, from the one devtools route that stays reachable.
  const [devMode, setDevMode] = useState(false);
  useEffect(() => {
    let live = true;
    fetchDevtoolsStatus()
      .then((status) => live && setDevMode(status.dev_mode))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  const sections = useMemo(
    () => STUDIO_SECTIONS.filter((section) => section.id !== "devtools" || devMode),
    [devMode],
  );

  // Incremented whenever a hook replaces the opening, so the canvas can play
  // the vertical text transition. A counter rather than a boolean, because
  // applying the same hook twice still has to animate.
  const [swapKey, setSwapKey] = useState(0);

  // Alternatives generated from a selection. While these are present the
  // filmstrip shows them instead of the vaulted library.
  const [generated, setGenerated] = useState<GeneratedHook[] | null>(null);

  /** Whether the author has put anything into the editor this session. */
  const touched = useRef(false);

  // Reopen the most recent draft from the studio's own database, which is
  // what the queue and the scheduler read. A draft held anywhere else is
  // invisible to both.
  useEffect(() => {
    let live = true;
    fetchLatestDraft()
      .then((existing) => {
        // Only adopt it if nothing has been typed in the meantime. A slow
        // response would otherwise overwrite whatever the author started while
        // it was still in flight. The check reads a ref rather than the draft
        // state, because deciding inside a setDraft updater would make that
        // updater impure and React is free to run it more than once.
        if (!live || !existing || touched.current) return;
        setDraft(existing.content);
        setDraftId(existing.id);
      })
      .catch(() => {
        // Nothing loaded. The composer opens empty rather than claiming a
        // draft it does not have, and the first save will create one.
      });
    return () => {
      live = false;
    };
  }, []);

  // Dark first, matching docs/UI_CONVENTIONS.md: an unstamped document gets
  // the dark palette, and data-theme="light" is the opt out.
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const telemetry = useMemo(() => {
    // Both counts come from the undecorated text. See lib/text.ts: a struck
    // character carries a second code point, and a bolded one is a surrogate
    // pair, so a raw .length reports roughly double for either.
    const chars = measurableLength(draft);
    const words = measurableWordCount(draft);
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
    touched.current = true;
    setDraft(next);
    setSaveState("dirty");
    setSavedAt(null);
    setSaveError(null);
  }, []);

  const onApplyHook = useCallback(
    (hook: string) => {
      touched.current = true;
      setDraft((current) => swapFirstParagraph(current, hook));
      setSaveState("dirty");
      setSavedAt(null);
      setSwapKey((key) => key + 1);
    },
    [],
  );

  const onReHook = useCallback(async (selection: string) => {
    try {
      const hooks = await generateHooks(selection);
      // An empty result is left alone rather than swapping the filmstrip to an
      // empty strip, which would read as though the library had vanished.
      if (hooks.length) setGenerated(hooks);
    } catch {
      setGenerated(null);
    }
  }, []);

  /**
   * Save writes the draft to the studio database and only then reports that it
   * did.
   *
   * This product has a run of fixes for surfaces that announced success
   * without performing the work, so the timestamp is stamped after the write
   * returns, and a rejected write says SAVE FAILED and carries the server's
   * reason. The 5,000 character limit is enforced server side and arrives as a
   * 400, which the author needs to read rather than have swallowed.
   */
  const onSave = useCallback(async () => {
    if (!draft.trim()) {
      // Refuse rather than create an empty row the queue would later show as
      // a post with no content.
      setSaveState("failed");
      setSaveError("There is nothing written to save.");
      return;
    }

    setSaveState("saving");
    setSaveError(null);
    try {
      if (draftId) {
        await updateDraft(draftId, draft);
      } else {
        setDraftId(await createDraft(draft));
      }
      const now = new Date();
      setSavedAt(
        [now.getHours(), now.getMinutes(), now.getSeconds()]
          .map((part) => String(part).padStart(2, "0"))
          .join(":"),
      );
      setSaveState("saved");
    } catch (error) {
      setSaveState("failed");
      setSaveError(error instanceof Error ? error.message : "The save was rejected.");
      setSavedAt(null);
    }
  }, [draft, draftId]);

  const section = sectionById(active);

  return (
    <div className="flex h-full w-full overflow-hidden bg-canvas">
      <StudioRail
        sections={sections}
        active={active}
        onSelect={setActive}
        trayOpen={trayOpen}
        onToggleTray={() => setTrayOpen((open) => !open)}
      />

      <div className="relative flex min-w-0 flex-1 flex-col">
        {/* The context bar is about the document being written. On a surface
            that has no document it reported "0 chars, 0% of fold" beside a
            Save button with nothing to save, which is telemetry about nothing.
            Those surfaces get a plain heading instead. */}
        {active === "composer" ? (
          <ContextBar
            kind="POST"
            draftRef="DRAFT 01"
            title={draft.trim().split("\n")[0]?.slice(0, 72) || "Untitled draft"}
            chars={telemetry.chars}
            foldLabel={telemetry.foldLabel}
            pastFold={telemetry.pastFold}
            readSeconds={telemetry.readSeconds}
            saveState={saveState}
            savedAt={savedAt}
            saveError={saveError}
            onSave={onSave}
            onPublish={async () => {
            // Publishing acts on a stored post. An unsaved draft has no id, so
            // it is written first rather than opening a dialog that can only
            // tell the author to go and save.
            if (!draftId && draft.trim()) await onSave();
            setPublishOpen(true);
          }}
          />
        ) : (
          <header className="flex h-12 shrink-0 items-center gap-3 border-b border-edge bg-ink px-4">
            <span className="studio-meta uppercase">{section.label}</span>
            <span className="truncate text-[13px] text-ink-muted">{section.blurb}</span>
          </header>
        )}

        <div className="relative flex min-h-0 flex-1">
          <div className="flex min-w-0 flex-1 flex-col">
            {active === "composer" && (
              <HookFilmstrip
                onApply={onApplyHook}
                generated={generated}
                onClearGenerated={() => setGenerated(null)}
              />
            )}

            {/* The surfaces that scroll internally manage their own overflow,
                so the shell does not add a second scrollbar around them. */}
            <main className={cn("min-h-0 flex-1", active === "leads" || active === "swipe" || active === "docs" ? "overflow-hidden" : "overflow-y-auto")}>
              {active === "composer" && (
                <ComposerCanvas
                  value={draft}
                  onChange={onChangeDraft}
                  onReHook={onReHook}
                  swapKey={swapKey}
                />
              )}
              {active === "leads" && <LeadsSurface />}
              {active === "swipe" && <SwipeSurface />}
              {active === "analytics" && <AnalyticsSurface />}
              {active === "settings" && <BrandStudioSurface />}
              {active === "queue" && <QueueSurface />}
              {active === "docs" && <DocsSurface />}
              {active === "command" && <CommandSurface />}
              {active === "devtools" && <DevtoolsSurface />}

            </main>
          </div>

          {/* The inspector inspects a draft, so it is not drawn beside the
              surfaces that are not about one. */}
          {active === "composer" && (
            <Inspector open={inspectorOpen} onClose={() => setInspectorOpen(false)} draft={draft} />
          )}

          {!inspectorOpen && active === "composer" && (
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
            sections={sections}
            open={trayOpen}
            active={active}
            onSelect={setActive}
            onClose={() => setTrayOpen(false)}
          />
        </div>
      </div>

      <PublishDialog
        open={publishOpen}
        postId={draftId}
        onClose={() => setPublishOpen(false)}
        onDone={(message) => {
          // The post left the composer. Reporting it as "saved" would be the
          // wrong claim, and reporting nothing would leave the author unsure
          // whether an irreversible action happened.
          setSaveState("published");
          setSavedAt(message);
          setSaveError(null);
        }}
      />

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
