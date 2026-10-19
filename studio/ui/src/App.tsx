import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Activity, Moon, PanelRight, Search, Sun } from "lucide-react";
import { StudioRail } from "@/components/StudioRail";
import { NavigationTray } from "@/components/NavigationTray";
import { ContextBar, SaveReason, type SaveState } from "@/components/ContextBar";
import { ComposerCanvas, FOLD_CHARS } from "@/components/ComposerCanvas";
import { HookFilmstrip } from "@/components/HookFilmstrip";
import { CommandPalette } from "@/components/CommandPalette";
import { Inspector } from "@/components/Inspector";
import { LeadsSurface } from "@/components/LeadsSurface";
import { OnboardingSurface } from "@/components/OnboardingSurface";
import { TodaySurface } from "@/components/TodaySurface";
import { ActivitySurface } from "@/components/ActivitySurface";
import { PostsSurface } from "@/components/PostsSurface";
import { OutboundSurface } from "@/components/OutboundSurface";
import { PatternsSurface } from "@/components/PatternsSurface";
import { SwipeSurface } from "@/components/SwipeSurface";
import { AnalyticsSurface } from "@/components/AnalyticsSurface";
import { BrandStudioSurface } from "@/components/BrandStudioSurface";
import { QueueSurface } from "@/components/QueueSurface";
import { DocsSurface } from "@/components/DocsSurface";
import { CommandSurface } from "@/components/CommandSurface";
import { PublishDialog } from "@/components/PublishDialog";
import { DevtoolsSurface } from "@/components/DevtoolsSurface";
import { StudioStatusBanner } from "@/components/StudioStatusBanner";
import { STUDIO_SECTIONS, sectionById, type SectionId } from "@/lib/navigation";
import { cn } from "@/lib/utils";
import {
  createDraft,
  fetchDevtoolsStatus,
  fetchLatestDraft,
  fetchOnboardingState,
  generateHooks,
  isDraftChangedElsewhere,
  updateDraft,
  fetchDraftById,
  type GeneratedHook,
  type SearchResult,
} from "@/lib/api";
import type { SearchFocus } from "@/lib/search";
import { measurableLength, measurableWordCount, openingEnd, storedLength, swapOpening } from "@/lib/text";
import { DOCKED_INSPECTOR_QUERY, useMediaQuery } from "@/lib/viewport";
import { confirmLeaving, registerUnsavedWork } from "@/lib/unsaved";

/** Average adult reading speed. Used for an estimate that is labelled as one. */
const WORDS_PER_MINUTE = 200;

/**
 * The screen an address names: "#/leads" is Leads.
 *
 * Every screen has one, so a reload stays where it was, a help article or a
 * teammate can link to a screen, and Back moves between screens instead of
 * leaving the studio. The section is all an address holds. Devtools is never
 * linked to, because in a consumer build every route behind it answers 404.
 */
function sectionFromAddress(hash: string): SectionId | null {
  const id = hash.replace(/^#\/?/, "");
  return STUDIO_SECTIONS.some((section) => section.id === id && id !== "devtools") ? (id as SectionId) : null;
}

type Theme = "dark" | "light";

/** Where this browser remembers the theme the creator chose. */
const THEME_KEY = "inox-hydra:theme";

/** The theme chosen earlier in this browser, if any. Storage can be blocked. */
function rememberedTheme(): Theme | null {
  try {
    const value = window.localStorage.getItem(THEME_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

/** Puts a screen's address in the location bar, as a new history entry unless `replace`. */
function writeAddress(section: SectionId, replace: boolean): void {
  const address = `#/${section}`;
  if (window.location.hash === address) return;
  if (replace) window.history.replaceState(null, "", address);
  else window.history.pushState(null, "", address);
}

export default function App() {
  // Opened on an address, the studio starts on that screen and Setup's first
  // run redirect leaves it alone.
  const linked = useRef(sectionFromAddress(window.location.hash));
  const [active, setActive] = useState<SectionId>(linked.current ?? "composer");
  const activeRef = useRef(active);
  activeRef.current = active;

  /**
   * Moves to another screen, the one way every control and link does.
   *
   * Leaving a screen whose edits live only on that screen asks first (see
   * lib/unsaved.ts), and answering Cancel stays put. `confirmed` is for a
   * caller that has already asked. Returns whether the move happened.
   */
  const navigate = useCallback((next: SectionId, confirmed = false): boolean => {
    if (next === activeRef.current) return true;
    if (!confirmed && !confirmLeaving(activeRef.current)) return false;
    setActive(next);
    writeAddress(next, false);
    return true;
  }, []);

  // Back and Forward, and an address typed into the location bar. Leaving a
  // screen whose edits would be lost asks first; staying puts that screen's
  // address back, since the browser has already moved off it.
  useEffect(() => {
    if (!linked.current) writeAddress(activeRef.current, true);
    const onPop = () => {
      const target = sectionFromAddress(window.location.hash) ?? "composer";
      if (target === activeRef.current) return;
      if (!confirmLeaving(activeRef.current)) {
        writeAddress(activeRef.current, false);
        return;
      }
      setActive(target);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const [trayOpen, setTrayOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  // Docked beside the editor on a wide window; a drawer over it on a narrow
  // one, where it starts closed so the first thing on screen is the page you
  // write on.
  const dockedInspector = useMediaQuery(DOCKED_INSPECTOR_QUERY);
  const [inspectorOpen, setInspectorOpen] = useState(dockedInspector);
  useEffect(() => {
    if (!dockedInspector) setInspectorOpen(false);
  }, [dockedInspector]);
  const [draft, setDraft] = useState("");
  const [draftId, setDraftId] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");

  // Text in the Composer that is not on disk. Registered once with the
  // unsaved-work registry, which asks before the page reloads or closes and
  // which the profile switcher reads before it reloads the studio. A save
  // still on its way counts: reloading now could cut it off. No section,
  // because the draft lives here and survives moving between screens.
  const composerUnsaved = useRef(false);
  composerUnsaved.current =
    (saveState === "dirty" || saveState === "failed" || saveState === "saving") && draft.trim().length > 0;
  useEffect(
    () => registerUnsavedWork("composer", { label: "The post in the Composer", check: () => composerUnsaved.current }),
    [],
  );
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  // The text this window last loaded or saved for the draft it holds, sent
  // with every save so the server can refuse one that would replace a newer
  // save from another window. Tied to the id, so a draft swapped in by any
  // other path is never checked against the wrong text.
  const base = useRef<{ id: string; content: string } | null>(null);
  const [changedElsewhere, setChangedElsewhere] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);

  /**
   * Which item a surface should show, when search asked it to.
   *
   * One value for the whole app rather than one per surface, because only the
   * surface being shown can use it, and a focus left behind on a surface you
   * then navigate away from and back to would re-open something you had
   * already moved on from.
   */
  const [focus, setFocus] = useState<{ section: SectionId; target: SearchFocus } | null>(null);
  const focusNonce = useRef(0);

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

  // A new install opens on Setup, because nothing else in the studio can be
  // about the creator until it knows who they are. Asked once. Moving
  // elsewhere before the answer arrives wins over it, so a creator who clicks
  // straight to the composer is not pulled back.
  useEffect(() => {
    let live = true;
    fetchOnboardingState()
      .then((state) => {
        // Setup until the studio knows who you are, Today afterwards. Not
        // when the studio was opened on a screen's address, and replacing
        // the address rather than adding one, so Back does not return to a
        // Composer the creator never chose.
        if (live && !linked.current && activeRef.current === "composer") {
          const home = state.steps.identity ? "today" : "setup";
          setActive(home);
          writeAddress(home, true);
        }
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  // Whether the bridge has been heard from lately, for the mark beside
  // Activity. That mark used to pulse green on every screen whatever the
  // bridge was doing, including on Setup beside "Not seen yet". Read from the
  // state Setup shows, again each minute while the header is on screen, since
  // the server calls the bridge connected for 150 seconds after it last
  // reported. Null until known, and then nothing is claimed.
  const [bridgeConnected, setBridgeConnected] = useState<boolean | null>(null);
  const showsHeader = active !== "composer";
  useEffect(() => {
    if (!showsHeader) return;
    let live = true;
    const read = () =>
      fetchOnboardingState()
        .then((state) => live && setBridgeConnected(state.bridge.connected))
        .catch(() => live && setBridgeConnected(null));
    void read();
    const timer = window.setInterval(read, 60_000);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [showsHeader]);

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

  // The author's own opening, kept while a hook stands in for it. Text set by
  // the program is not on the textarea's undo stack, so Ctrl+Z could not
  // bring it back and one click lost a paragraph for good. Kept across
  // several hooks tried in a row, so Undo returns the author's words rather
  // than the previous hook, and offered for as long as the hook is still the
  // opening.
  const [hookUndo, setHookUndo] = useState<{ opening: string; hook: string } | null>(null);
  const canUndoHook = hookUndo !== null && draft.startsWith(hookUndo.hook);

  /** Whether the author has put anything into the editor this session. */
  const touched = useRef(false);

  // The text on screen now, for code that finishes after a render it began
  // in: a save that returns has to know whether the author kept typing.
  const latestDraft = useRef(draft);
  latestDraft.current = draft;

  // Set while a save is on its way. A ref rather than the save state, because
  // a double click lands both clicks before React renders between them, and
  // each one created its own draft.
  const saving = useRef(false);

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
        base.current = { id: existing.id, content: existing.content };
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
  // the dark palette, and data-theme="light" is the opt out. Dark is the
  // default only when nothing says otherwise, though: a choice made here is
  // remembered, and until there is one the computer's own setting decides.
  // It used to be dark on every launch, reload and profile switch.
  const prefersLight = useMediaQuery("(prefers-color-scheme: light)");
  const [chosenTheme, setChosenTheme] = useState<Theme | null>(rememberedTheme);
  const theme: Theme = chosenTheme ?? (prefersLight ? "light" : "dark");
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);
  const toggleTheme = useCallback(() => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setChosenTheme(next);
    try {
      window.localStorage.setItem(THEME_KEY, next);
    } catch {
      // Not remembered in a browser that blocks storage; it still switches.
    }
  }, [theme]);

  const telemetry = useMemo(() => {
    // Both counts come from the undecorated text. See lib/text.ts: a struck
    // character carries a second code point, and a bolded one is a surrogate
    // pair, so a raw .length reports roughly double for either.
    const chars = measurableLength(draft);
    const words = measurableWordCount(draft);
    return {
      chars,
      // A length limit counts what is stored, not what a reader sees, so the
      // strip's count against 3,000 is a different measure from the fold's.
      stored: storedLength(draft),
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
      const end = openingEnd(draft);
      const opening = end === -1 || !draft.trim() ? draft : draft.slice(0, end);
      setHookUndo({ opening: hookUndo && draft.startsWith(hookUndo.hook) ? hookUndo.opening : opening, hook });
      setDraft(swapOpening(draft, hook));
      setSaveState("dirty");
      setSavedAt(null);
      setSwapKey((key) => key + 1);
    },
    [draft, hookUndo],
  );

  // Re-Hook in flight, and what the last one said when it failed. A press
  // while one is running is ignored: each used to start another request, and
  // enough of them against a stalled provider froze the studio. A failure was
  // swallowed here too, so a revoked key looked like a button doing nothing.
  const [reHook, setReHook] = useState<{ busy: boolean; error: string | null }>({ busy: false, error: null });
  const reHookInFlight = useRef(false);
  // Without a model, Re-Hook answers with fill-in templates, which say so.
  const fillIns =
    !!generated?.length && generated.every((hook) => (hook as { source?: string }).source === "template");

  const onUndoHook = useCallback(() => {
    if (!hookUndo || !draft.startsWith(hookUndo.hook)) return;
    setDraft(hookUndo.opening + draft.slice(hookUndo.hook.length));
    setHookUndo(null);
    setSaveState("dirty");
    setSavedAt(null);
  }, [draft, hookUndo]);

  const onReHook = useCallback(async (selection: string) => {
    if (reHookInFlight.current) return;
    reHookInFlight.current = true;
    setReHook({ busy: true, error: null });
    try {
      const hooks = await generateHooks(selection);
      // An empty result is left alone rather than swapping the filmstrip to an
      // empty strip, which would read as though the library had vanished.
      if (hooks.length) setGenerated(hooks);
      setReHook({ busy: false, error: null });
    } catch (caught) {
      setGenerated(null);
      setReHook({ busy: false, error: caught instanceof Error ? caught.message : "The request did not complete." });
    } finally {
      reHookInFlight.current = false;
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
   *
   * Resolves to whether the write landed, which Publish waits on.
   */
  const onSave = useCallback(async (keepMine = false): Promise<boolean> => {
    if (saving.current) return false;
    if (!draft.trim()) {
      // Refuse rather than create an empty row the queue would later show as
      // a post with no content.
      setSaveState("failed");
      setSaveError("There is nothing written to save.");
      return false;
    }

    saving.current = true;
    setSaveState("saving");
    setSaveError(null);
    setChangedElsewhere(false);
    try {
      if (draftId) {
        const known = base.current?.id === draftId ? base.current.content : undefined;
        await updateDraft(draftId, draft, keepMine ? undefined : known);
        base.current = { id: draftId, content: draft };
      } else {
        const created = await createDraft(draft);
        base.current = { id: created, content: draft };
        setDraftId(created);
      }
      if (latestDraft.current !== draft) {
        // Typed into while the save was out: what is on screen is not what
        // was written, so it is not SAVED.
        setSaveState("dirty");
        setSavedAt(null);
        return false;
      }
      const now = new Date();
      setSavedAt(
        [now.getHours(), now.getMinutes(), now.getSeconds()]
          .map((part) => String(part).padStart(2, "0"))
          .join(":"),
      );
      setSaveState("saved");
      return true;
    } catch (error) {
      setSaveState("failed");
      setSaveError(error instanceof Error ? error.message : "The save was rejected.");
      setChangedElsewhere(isDraftChangedElsewhere(error));
      setSavedAt(null);
      return false;
    } finally {
      saving.current = false;
    }
  }, [draft, draftId]);

  /**
   * Opens what a search result names.
   *
   * Only a draft is loaded into the Composer. The server already routes a
   * published or queued post to Queue or Analytics, because Save writes over
   * whatever post the editor holds, and a draft that has since been published
   * elsewhere is treated the same way when it turns out to be gone from the
   * draft list.
   *
   * Loading a draft replaces the editor's text, and there is no autosave, so
   * unsaved work is asked about first rather than silently discarded. The
   * help article on drafts had to warn that the interface could not hold two
   * drafts; this is the one place that would otherwise lose one.
   */
  const onOpenResult = useCallback(
    async (result: SearchResult) => {
      const point = (target: SectionId, id: string, anchor: string | null = null) => {
        if (!navigate(target)) return;
        focusNonce.current += 1;
        setFocus({ section: target, target: { id, anchor, nonce: focusNonce.current } });
      };

      if (result.kind === "post") {
        if (result.opens !== "composer") {
          navigate(result.opens === "queue" ? "queue" : "analytics");
          return;
        }
        if (result.id === draftId) {
          navigate("composer");
          return;
        }
        if (!confirmLeaving(activeRef.current)) return;
        if (
          composerUnsaved.current &&
          !window.confirm(
            "The post in the Composer has unsaved changes. Open the other draft and discard them?",
          )
        ) {
          return;
        }
        const found = await fetchDraftById(result.id).catch(() => null);
        if (!found) {
          // Published or queued since the search ran, so it no longer belongs
          // in the editor.
          navigate("analytics", true);
          return;
        }
        touched.current = true;
        setDraft(found.content);
        setDraftId(found.id);
        base.current = { id: found.id, content: found.content };
        setSaveState("idle");
        setSavedAt(null);
        setSaveError(null);
        setGenerated(null);
        setHookUndo(null);
        navigate("composer", true);
        return;
      }

      if (result.kind === "lead") point("leads", result.id);
      else if (result.kind === "specimen") point("swipe", result.id);
      else if (result.kind === "help") point("docs", result.id, result.anchor_text ?? null);
    },
    [draftId, navigate],
  );

  const focusFor = (target: SectionId) => (focus && focus.section === target ? focus.target : null);

  const section = sectionById(active);

  return (
    <div className="flex h-full w-full overflow-hidden bg-canvas">
      <StudioRail
        sections={sections}
        active={active}
        onSelect={navigate}
        trayOpen={trayOpen}
        onToggleTray={() => setTrayOpen((open) => !open)}
        onSearch={() => setPaletteOpen(true)}
      />

      <div className="relative flex min-w-0 flex-1 flex-col">
        <StudioStatusBanner />
        {/* The context bar is about the document being written. On a surface
            that has no document it reported "0 chars, 0% of fold" beside a
            Save button with nothing to save, which is telemetry about nothing.
            Those surfaces get a plain heading instead. */}
        {active === "composer" ? (
          <>
          <ContextBar
            kind="POST"
            title={draft.trim().split("\n")[0]?.slice(0, 72) || "Untitled draft"}
            storedChars={telemetry.stored}
            foldLabel={telemetry.foldLabel}
            pastFold={telemetry.pastFold}
            readSeconds={telemetry.readSeconds}
            saveState={saveState}
            savedAt={savedAt}
            saveError={saveError}
            onSave={() => void onSave()}
            onPublish={async () => {
            // Publishing acts on the stored post, so the stored post has to be
            // what is on screen. This saved only a post that had never been
            // saved, so after an edit Queue it and Send to LinkedIn acted on
            // the older stored text, and the strip then replaced UNSAVED with
            // the schedule, hiding that the edit was in neither place. Any
            // unsaved edit is written first now. A save that fails leaves the
            // dialog closed, with its reason in the strip, rather than opening
            // a dialog that can only say "save first".
            if (saveState === "saving") return;
            if (!draft.trim()) {
              setSaveState("failed");
              setSaveError("There is nothing written to publish.");
              return;
            }
            if (!draftId || saveState === "dirty" || saveState === "failed") {
              if (!(await onSave())) return;
            }
            setPublishOpen(true);
          }}
          />
          {saveState === "failed" && saveError && (
            <SaveReason reason={saveError} onKeepMine={changedElsewhere ? () => void onSave(true) : undefined} />
          )}
          </>
        ) : (
          <header className="flex h-12 shrink-0 items-center gap-3 border-b border-edge bg-ink px-4">
            <span className="studio-meta uppercase">{section.label}</span>
            <span className="min-w-0 flex-1 truncate text-[13px] text-ink-muted">{section.blurb}</span>
            <button
              type="button"
              onClick={() => navigate("activity")}
              className={cn(
                "flex shrink-0 items-center gap-1.5 rounded-md border px-2.5 py-1 text-[12px] font-medium transition-colors",
                active === "activity"
                  ? "border-signal-orange bg-soft text-ink-primary"
                  : "border-edge bg-canvas text-ink-muted hover:border-edge-strong hover:text-ink-primary",
              )}
            >
              <span
                className={cn(
                  "size-1.5 rounded-full",
                  bridgeConnected ? "bg-signal-green" : "border border-edge-strong",
                )}
                aria-hidden="true"
              />
              <Activity className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
              {/* Words beside the icons from a small tablet up. On a phone
                  they pushed Search past the edge of the screen; there they
                  stay the button's name without taking its width. */}
              <span className="max-sm:sr-only">Activity</span>
              {bridgeConnected !== null && (
                <span className="sr-only">{bridgeConnected ? ", bridge connected" : ", bridge not connected"}</span>
              )}
            </button>
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
              className="grid size-7 shrink-0 place-items-center rounded-md border border-edge bg-canvas text-ink-muted transition-colors hover:border-edge-strong hover:text-ink-primary"
            >
              {theme === "dark" ? (
                <Sun className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
              ) : (
                <Moon className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
              )}
            </button>
            <button
              type="button"
              onClick={() => setPaletteOpen(true)}
              aria-keyshortcuts="Control+K Meta+K"
              className="flex shrink-0 items-center gap-2 rounded-md border border-edge bg-canvas py-1 pr-1.5 pl-2.5 text-[12px] text-ink-muted transition-colors duration-(--studio-motion-fast) hover:border-edge-strong hover:text-ink-primary"
            >
              <Search className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
              <span className="max-sm:sr-only">Search everything</span>
              <kbd className="studio-meta rounded-sm border border-edge px-1 text-[10px] text-ink-muted max-sm:hidden">Ctrl K</kbd>
            </button>
          </header>
        )}

        <div className="relative flex min-h-0 flex-1">
          <div className="flex min-w-0 flex-1 flex-col">
            {active === "composer" && (
              <HookFilmstrip
                onApply={onApplyHook}
                generated={generated}
                onClearGenerated={() => setGenerated(null)}
                canUndo={canUndoHook}
                onUndo={onUndoHook}
              />
            )}
            {active === "composer" && (reHook.busy || reHook.error || fillIns) && (
              <div
                role="status"
                className="flex shrink-0 items-baseline justify-between gap-3 border-b border-edge px-10 py-2"
              >
                {reHook.busy ? (
                  <p className="studio-meta animate-pulse text-ink-muted">WRITING HOOKS FROM YOUR SELECTION</p>
                ) : reHook.error ? (
                  <p className="text-[12px] leading-snug text-signal-orange-text">
                    Re-Hook failed. {reHook.error}
                  </p>
                ) : (
                  <p className="studio-meta text-ink-muted">
                    NO MODEL IS SET UP, SO THESE ARE FILL-IN TEMPLATES. REPLACE EACH [BRACKET] WITH YOUR OWN
                    WORDS BEFORE POSTING.
                  </p>
                )}
                {reHook.error && (
                  <button
                    type="button"
                    onClick={() => setReHook({ busy: false, error: null })}
                    className="studio-meta shrink-0 text-[10px] text-ink-muted transition-colors hover:text-ink-primary"
                  >
                    DISMISS
                  </button>
                )}
              </div>
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
              {active === "setup" && <OnboardingSurface />}
              {active === "today" && (
                <TodaySurface
                  onOpenSetup={() => navigate("setup")}
                  onOpenActivity={() => navigate("activity")}
                  onOpenLead={(leadId) => {
                    if (!navigate("leads")) return;
                    focusNonce.current += 1;
                    setFocus({ section: "leads", target: { id: leadId, anchor: null, nonce: focusNonce.current } });
                  }}
                />
              )}
              {active === "activity" && (
                <ActivitySurface
                  onOpenLead={(leadId) => {
                    if (!navigate("leads")) return;
                    focusNonce.current += 1;
                    setFocus({ section: "leads", target: { id: leadId, anchor: null, nonce: focusNonce.current } });
                  }}
                />
              )}
              {active === "leads" && <LeadsSurface focus={focusFor("leads")} />}
              {active === "posts" && (
                <PostsSurface
                  onOpenActivity={() => navigate("activity")}
                  onOpenLead={(leadId) => {
                    if (!navigate("leads")) return;
                    focusNonce.current += 1;
                    setFocus({ section: "leads", target: { id: leadId, anchor: null, nonce: focusNonce.current } });
                  }}
                />
              )}
              {active === "outbound" && <OutboundSurface />}
              {active === "patterns" && <PatternsSurface />}
              {active === "swipe" && <SwipeSurface focus={focusFor("swipe")} />}
              {active === "analytics" && <AnalyticsSurface />}
              {active === "settings" && <BrandStudioSurface />}
              {active === "queue" && <QueueSurface />}
              {active === "docs" && <DocsSurface focus={focusFor("docs")} />}
              {active === "command" && <CommandSurface draft={draft} />}
              {active === "devtools" && <DevtoolsSurface />}

            </main>
          </div>

          {/* The inspector inspects a draft, so it is not drawn beside the
              surfaces that are not about one. */}
          {active === "composer" && (
            <Inspector
              open={inspectorOpen}
              onClose={() => setInspectorOpen(false)}
              draft={draft}
              overlay={!dockedInspector}
            />
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
            onSelect={navigate}
            onClose={() => setTrayOpen(false)}
          />
        </div>
      </div>

      <PublishDialog
        open={publishOpen}
        postId={draftId}
        opening={draft.trim().split("\n")[0] ?? ""}
        onClose={() => setPublishOpen(false)}
        onDone={(message) => {
          // The post left the composer. Reporting it as "saved" would be the
          // wrong claim, and reporting nothing would leave the author unsure
          // whether an irreversible action happened.
          //
          // The message says "marked as published" rather than "published"
          // because that is what occurred: a status written to a local row.
          // Nothing in this product makes an outbound request, so a studio
          // that reported a delivery would be reporting one it cannot make.
          //
          // The post has left the draft list, so the editor lets go of it and
          // clears for the next one. It used to stay attached, and the next
          // post typed into it and saved was written over the post just
          // published or queued, with no copy kept. A queued post stays on
          // the Queue, and a published one in Analytics.
          touched.current = true;
          setDraftId(null);
          setDraft("");
          setGenerated(null);
          setSaveState("published");
          setSavedAt(message);
          setSaveError(null);
        }}
      />

      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        sections={sections}
        onOpenResult={(result) => void onOpenResult(result)}
        onNavigate={navigate}
        onToggleTheme={toggleTheme}
        onToggleInspector={() => setInspectorOpen((open) => !open)}
      />
    </div>
  );
}
