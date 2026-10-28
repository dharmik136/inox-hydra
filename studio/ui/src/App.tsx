import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Activity, Moon, PanelRight, Search, Sun } from "lucide-react";
import { StudioRail } from "@/components/StudioRail";
import { NavigationTray } from "@/components/NavigationTray";
import { ContextBar, SaveReason, type BarAction, type SaveState } from "@/components/ContextBar";
import { ComposerCanvas, FOLD_CHARS } from "@/components/ComposerCanvas";
import { HookFilmstrip } from "@/components/HookFilmstrip";
import { CommandPalette } from "@/components/CommandPalette";
import { Inspector } from "@/components/Inspector";
import { LeadsSurface } from "@/components/LeadsSurface";
import { OnboardingSurface } from "@/components/OnboardingSurface";
import { TodaySurface } from "@/components/TodaySurface";
import { RecordSurface } from "@/components/RecordSurface";
import { ActivitySurface } from "@/components/ActivitySurface";
import { HealthSurface } from "@/components/HealthSurface";
import { RepliesSurface } from "@/components/RepliesSurface";
import { AudienceSurface } from "@/components/AudienceSurface";
import { PostsSurface } from "@/components/PostsSurface";
import { OutboundSurface } from "@/components/OutboundSurface";
import { PatternsSurface } from "@/components/PatternsSurface";
import { AnalyticsSurface } from "@/components/AnalyticsSurface";
import { BrandSurface, SettingsSurface } from "@/components/BrandStudioSurface";
import { QueueSurface } from "@/components/QueueSurface";
import { DocsSurface } from "@/components/DocsSurface";
import { PublishDialog } from "@/components/PublishDialog";
import { DraftsPanel, draftTitle } from "@/components/DraftsPanel";
import { DevtoolsSurface } from "@/components/DevtoolsSurface";
import { StudioStatusBanner } from "@/components/StudioStatusBanner";
import { STUDIO_SECTIONS, sectionById, type SectionId } from "@/lib/navigation";
import { setupDone } from "@/lib/setup";
import { cn } from "@/lib/utils";
import {
  createDraft,
  fetchDevtoolsStatus,
  fetchLatestDraft,
  fetchOnboardingState,
  generateHooks,
  isDraftChangedElsewhere,
  isPostedTextLocked,
  fetchPostById,
  POSTED_STATUSES,
  updateDraft,
  fetchDraftById,
  type DraftSummary,
  type GeneratedHook,
  type SearchResult,
} from "@/lib/api";
import type { SearchFocus } from "@/lib/search";
import { measurableLength, measurableWordCount, openingEnd, storedLength, swapOpening } from "@/lib/text";
import { DOCKED_INSPECTOR_QUERY, useMediaQuery } from "@/lib/viewport";
import { onBridgeReport, reportBridge } from "@/lib/bridgeState";
import { onStudioChange, useRefresh, useStudioStream } from "@/lib/refresh";
import { confirmLeaving, registerUnsavedWork } from "@/lib/unsaved";

/** Average adult reading speed. Used for an estimate that is labelled as one. */
const WORDS_PER_MINUTE = 200;

/**
 * How long after a write nothing named the header waits for a screen to
 * report the bridge before reading it itself: Today, Setup and Activity read
 * on the same news, and one answer on screen is better than two.
 */
const BRIDGE_REPORT_GRACE_MS = 1_500;

/**
 * The least time between two reads of the bridge the stream causes the header
 * to make, with the last one always made. The whole onboarding state is read
 * for one mark, so fifteen seconds, the age at which a returning screen reads
 * again, keeps it to four a minute however busy the studio is.
 */
const HEADER_GAP_MS = 15_000;

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

/** A queued, published or sent post, named the way the Composer's buttons name it. */
function postedWord(status: string): string {
  return status === "published" || status === "sent" ? status : "queued";
}

/** Why new text over such a post was not saved, and the two ways on. */
function postedRefusal(status: string): string {
  const word = postedWord(status);
  return `This post is already ${word}, so its text was not changed. Choose Correct the ${word} post to change its text on purpose, or Save as a new draft to keep this text as a separate post.`;
}

/** The time a save landed, as the SAVED mark shows it. */
function clockTime(): string {
  const now = new Date();
  return [now.getHours(), now.getMinutes(), now.getSeconds()]
    .map((part) => String(part).padStart(2, "0"))
    .join(":");
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
  // Opened without an address, the first screen is Setup or Today, and which
  // one is not known until the studio says whether it knows who you are.
  // The Composer was drawn in the meantime, for one frame, with its draft,
  // templates and profile fetched, and then replaced. Until the answer, or a
  // move the creator makes first, the shell is drawn without a screen.
  const [choosingHome, setChoosingHome] = useState(!linked.current);

  /**
   * Moves to another screen, the one way every control and link does.
   *
   * Leaving a screen whose edits live only on that screen asks first (see
   * lib/unsaved.ts), and answering Cancel stays put. `confirmed` is for a
   * caller that has already asked. Returns whether the move happened.
   */
  const navigate = useCallback((next: SectionId, confirmed = false): boolean => {
    setChoosingHome(false);
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
      setChoosingHome(false);
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
  const draftIdRef = useRef(draftId);
  draftIdRef.current = draftId;
  const [saveState, setSaveState] = useState<SaveState>("idle");

  // The drafts list, and a counter that tells an open list to read again
  // after a save, a publish or a delete changed what it shows.
  const [draftsOpen, setDraftsOpen] = useState(false);
  const [draftsKey, setDraftsKey] = useState(0);

  // The draft the Composer let go of when its text was cleared or replaced
  // all at once. Clearing the editor and saving used to write the next post
  // over that draft without a word; now the next save makes a new draft, the
  // earlier one is kept, and the line under the bar says so, with a way back
  // to writing over it on purpose.
  const [detachedFrom, setDetachedFrom] = useState<{ id: string; title: string } | null>(null);

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

  // The post the Composer holds when it is no longer a draft (queued,
  // published or sent), and whether the author has agreed to change its
  // text. The server keeps such a post's text unless a save says it means
  // to, so a stale window cannot write the next post over it; Correct the
  // queued post and Save as a new draft are the deliberate ways through.
  // Tied to the id, like base, so a draft swapped in elsewhere is never
  // treated as one.
  const [posted, setPosted] = useState<{ id: string; status: string; agreed: boolean } | null>(null);
  const [postedRefused, setPostedRefused] = useState(false);
  const holdsPosted = posted !== null && posted.id === draftId;

  /**
   * After a refused save, whether the post is one whose text is kept.
   *
   * The server says so with the posted_text_locked code. A refusal carrying
   * some other code is something else; one carrying none comes from a client
   * that cannot read the code, and the post's own status answers instead.
   */
  const noticePosted = useCallback(async (id: string, error: unknown) => {
    const code = (error as { code?: unknown } | null)?.code;
    if (!isPostedTextLocked(error) && typeof code === "string") return;
    const row = await fetchPostById(id).catch(() => null);
    if (!row || !POSTED_STATUSES.has(row.status)) return;
    setPosted((current) => ({ id, status: row.status, agreed: current?.id === id ? current.agreed : false }));
    setPostedRefused(true);
    setSaveError(postedRefusal(row.status));
  }, []);
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

  // A new install opens on Setup, and so does a studio whose Setup is not
  // done. Asked once. Moving elsewhere before the answer arrives wins over
  // it, so a creator who clicks straight to the composer is not pulled back.
  // Whether the bridge has been heard from lately, for the mark beside
  // Activity. That mark used to pulse green on every screen whatever the
  // bridge was doing, including on Setup beside "Not seen yet". It shows what
  // the last screen to read the bridge's state was told (Today, Setup and
  // Activity report it), so it cannot disagree with the screen under it, and
  // reads that state itself only when nothing has for a minute, since the
  // server calls the bridge connected for 150 seconds after it last
  // reported. Null until known, and then nothing is claimed.
  const [bridgeConnected, setBridgeConnected] = useState<boolean | null>(null);
  const bridgeReadAt = useRef(0);
  // One change stream for this window, whichever screen is open: the
  // screens listen to it through useRefresh rather than each polling.
  useStudioStream();
  useEffect(
    () =>
      onBridgeReport((connected) => {
        bridgeReadAt.current = Date.now();
        setBridgeConnected(connected);
      }),
    [],
  );

  useEffect(() => {
    let live = true;
    fetchOnboardingState()
      .then((state) => {
        // The same answer gives the header its first reading of the bridge,
        // which it used to ask for a second time a moment later.
        reportBridge(state.bridge.connected);
        // Setup until Setup is done, Today afterwards (sections report,
        // decision 5), by the one rule Setup itself uses. Not when the
        // studio was opened on a screen's address, and replacing the address
        // rather than adding one, so Back does not return to a Composer the
        // creator never chose.
        if (live && !linked.current && activeRef.current === "composer") {
          const home = setupDone(state) ? "today" : "setup";
          setActive(home);
          writeAddress(home, true);
        }
      })
      .catch(() => undefined)
      .finally(() => live && setChoosingHome(false));
    return () => {
      live = false;
    };
  }, []);

  const showsHeader = active !== "composer";
  const showsHeaderRef = useRef(showsHeader);
  showsHeaderRef.current = showsHeader;
  const readBridge = useCallback(() => {
    if (!showsHeaderRef.current || Date.now() - bridgeReadAt.current < 50_000) return;
    bridgeReadAt.current = Date.now();
    return fetchOnboardingState()
      .then((state) => reportBridge(state.bridge.connected))
      .catch(() => setBridgeConnected(null));
  }, []);
  useEffect(() => {
    if (showsHeader) void readBridge();
  }, [showsHeader, readBridge]);
  useRefresh(readBridge, 60_000);
  // The mark follows the stream. A heartbeat is the bridge heard from now,
  // which is what connected means (the studio counts it connected for 150
  // seconds after one), so the mark says so without a read. A write nothing
  // named may be the bridge too, as a heartbeat a second studio recorded or
  // a restore, so after one the header reads the state itself unless a
  // screen reported it first, at most once per HEADER_GAP_MS and always once
  // after the last. The minute above stays: nothing is written when the
  // bridge goes quiet, so only time can say it has.
  const headerReadAt = useRef(0);
  useEffect(() => {
    let waiting: number | undefined;
    const stop = onStudioChange((changes) => {
      if (changes.some((change) => change.kind === "heartbeat")) {
        bridgeReadAt.current = Date.now();
        setBridgeConnected(true);
      }
      if (!changes.some((change) => change.kind === "database") || waiting !== undefined) return;
      const heardAt = Date.now();
      const wait = Math.max(BRIDGE_REPORT_GRACE_MS, headerReadAt.current + HEADER_GAP_MS - heardAt);
      waiting = window.setTimeout(() => {
        waiting = undefined;
        if (!showsHeaderRef.current || bridgeReadAt.current >= heardAt) return;
        headerReadAt.current = Date.now();
        bridgeReadAt.current = Date.now();
        fetchOnboardingState()
          .then((state) => reportBridge(state.bridge.connected))
          .catch(() => setBridgeConnected(null));
      }, wait);
    });
    return () => {
      stop();
      if (waiting !== undefined) window.clearTimeout(waiting);
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

  // The author's own opening, kept while a hook stands in for it. Text set by
  // the program is not on the textarea's undo stack, so Ctrl+Z could not
  // bring it back and one click lost a paragraph for good. Kept across
  // several hooks tried in a row, so Undo returns the author's words rather
  // than the previous hook, and offered for as long as the hook is still the
  // opening.
  const [hookUndo, setHookUndo] = useState<{ opening: string; hook: string } | null>(null);
  const canUndoHook = hookUndo !== null && draft.startsWith(hookUndo.hook);

  const detachedRef = useRef(detachedFrom);
  detachedRef.current = detachedFrom;

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

  // Settles when the save now on its way has finished, so a Publish click
  // that lands while one is out can wait for it instead of being dropped.
  const savingDone = useRef<Promise<void>>(Promise.resolve());

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

  const onChangeDraft = useCallback((next: string, cleared = false) => {
    touched.current = true;
    const held = draftIdRef.current;
    if (cleared && held) {
      // A different post is being started over this one. It is kept as it
      // was saved, and the next save creates a new draft.
      setDetachedFrom({ id: held, title: draftTitle(base.current?.id === held ? base.current.content : "") });
      setDraftId(null);
    } else if (!held && detachedRef.current && base.current?.id === detachedRef.current.id && next === base.current.content) {
      // Undo brought the earlier draft's text back: this is that draft again.
      setDraftId(detachedRef.current.id);
      setDetachedFrom(null);
      setDraft(next);
      setSaveState("idle");
      setSavedAt(null);
      setSaveError(null);
      return;
    }
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
  const onSave = useCallback(async (keepMine = false, correctPosted = false): Promise<boolean> => {
    if (saving.current) return false;
    if (!draft.trim()) {
      // Refuse rather than create an empty row the queue would later show as
      // a post with no content.
      setSaveState("failed");
      setSaveError("There is nothing written to save.");
      return false;
    }

    saving.current = true;
    let settled = () => {};
    savingDone.current = new Promise<void>((resolve) => {
      settled = resolve;
    });
    setSaveState("saving");
    setSaveError(null);
    setChangedElsewhere(false);
    setPostedRefused(false);
    try {
      if (draftId) {
        const known = base.current?.id === draftId ? base.current.content : undefined;
        await updateDraft(draftId, draft, keepMine ? undefined : known, correctPosted);
        base.current = { id: draftId, content: draft };
      } else {
        const created = await createDraft(draft);
        base.current = { id: created, content: draft };
        setDraftId(created);
        setDetachedFrom(null);
      }
      setDraftsKey((key) => key + 1);
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
      if (draftId && !isDraftChangedElsewhere(error)) void noticePosted(draftId, error);
      return false;
    } finally {
      saving.current = false;
      settled();
    }
  }, [draft, draftId, noticePosted]);

  /**
   * Saves over the text of the queued, published or sent post the Composer
   * holds, asking first the first time. A post that has already gone to
   * LinkedIn changes only here, which the question says.
   */
  const onCorrectPosted = useCallback(() => {
    if (!posted || posted.id !== draftId) return;
    if (!posted.agreed) {
      const word = postedWord(posted.status);
      const gone =
        posted.status === "queued" || posted.status === "scheduled" || posted.status === "due"
          ? " The queue will use the new text."
          : " It has already gone to LinkedIn, and LinkedIn's copy will not change: correct it there as well.";
      if (!window.confirm(`Change the text of this ${word} post to what is in the Composer?${gone}`)) return;
      setPosted({ ...posted, agreed: true });
    }
    void onSave(false, true);
  }, [posted, draftId, onSave]);

  /** Keeps the queued, published or sent post as it is and saves this text as a new draft. */
  const onSaveAsNew = useCallback(async () => {
    if (saving.current || !draft.trim()) return;
    saving.current = true;
    setSaveState("saving");
    setSaveError(null);
    setChangedElsewhere(false);
    setPostedRefused(false);
    try {
      const created = await createDraft(draft);
      base.current = { id: created, content: draft };
      setDraftId(created);
      setPosted(null);
      setDetachedFrom(null);
      setDraftsKey((key) => key + 1);
      const current = latestDraft.current === draft;
      setSaveState(current ? "saved" : "dirty");
      setSavedAt(current ? clockTime() : null);
    } catch (error) {
      setSaveState("failed");
      setSaveError(error instanceof Error ? error.message : "The save was rejected.");
      setSavedAt(null);
    } finally {
      saving.current = false;
    }
  }, [draft]);

  /**
   * Puts a stored post into the Composer, or an empty page for a new post,
   * with every per-post state reset. The callers ask about unsaved work
   * first.
   */
  const adopt = useCallback((post: { id: string; content: string; status?: string } | null) => {
    touched.current = true;
    setDraft(post?.content ?? "");
    setDraftId(post?.id ?? null);
    base.current = post ? { id: post.id, content: post.content } : null;
    setPosted(post?.status && POSTED_STATUSES.has(post.status) ? { id: post.id, status: post.status, agreed: false } : null);
    setPostedRefused(false);
    setChangedElsewhere(false);
    setSaveState("idle");
    setSavedAt(null);
    setSaveError(null);
    setGenerated(null);
    setHookUndo(null);
    setDetachedFrom(null);
  }, []);

  /** Whether unsaved text in the Composer may be discarded, asking when there is some. */
  const mayDiscard = useCallback(
    (doing: string) =>
      !composerUnsaved.current ||
      window.confirm(`The post in the Composer has unsaved changes. ${doing} and discard them?`),
    [],
  );

  /** Opens a draft from the drafts list. Resolves false when the author chose to stay. */
  const onOpenDraft = useCallback(
    async (chosen: DraftSummary): Promise<boolean> => {
      if (chosen.id === draftId) return true;
      if (!mayDiscard("Open the other draft")) return false;
      // Read fresh: the list may be older than another window's save.
      const found = await fetchDraftById(chosen.id).catch(() => null);
      adopt(found ? { ...found, status: "draft" } : { id: chosen.id, content: chosen.content, status: "draft" });
      return true;
    },
    [draftId, mayDiscard, adopt],
  );

  /**
   * An empty page for the next post. The post open now stays as it was
   * saved, in the drafts list; unsaved changes to it are asked about.
   */
  const onNewPost = useCallback((): boolean => {
    if (!draftId && !draft.trim()) return true;
    if (!mayDiscard("Start a new post")) return false;
    adopt(null);
    return true;
  }, [draftId, draft, mayDiscard, adopt]);

  /**
   * From your record's "Draft from this": the server has made a draft that
   * records the card it came from; open it in the Composer. Unsaved text in
   * the Composer is asked about first, as opening any other draft is.
   */
  const onDraftFromCard = useCallback(
    (made: { id: string; content: string }) => {
      if (!mayDiscard("Open the draft made from this card")) return;
      adopt({ id: made.id, content: made.content, status: "draft" });
      setDraftsKey((key) => key + 1);
      navigate("composer", true);
    },
    [mayDiscard, adopt, navigate],
  );

  /**
   * Opens a queued post from the Queue in the Composer, to correct its text.
   *
   * After Publish the Composer lets go of the post, so this is the way back
   * to a queued post's words. Unsaved work in the Composer is asked about
   * first, as when opening a draft from search.
   */
  const onEditText = useCallback(
    async (postId: string) => {
      if (postId === draftId) {
        navigate("composer");
        return;
      }
      if (!confirmLeaving(activeRef.current)) return;
      if (
        composerUnsaved.current &&
        !window.confirm("The post in the Composer has unsaved changes. Open the queued post and discard them?")
      ) {
        return;
      }
      const found = await fetchPostById(postId).catch(() => null);
      if (!found) return;
      adopt(found);
      navigate("composer", true);
    },
    [draftId, navigate, adopt],
  );

  const saveActions: BarAction[] = [];
  if (saveState === "failed" && changedElsewhere) {
    saveActions.push({
      label: "Keep this version",
      onClick: () => void onSave(true, holdsPosted && posted?.agreed === true),
    });
  }
  if (saveState === "failed" && postedRefused && holdsPosted && posted) {
    saveActions.push({ label: `Correct the ${postedWord(posted.status)} post`, onClick: onCorrectPosted });
  }
  if ((saveState === "failed" && postedRefused) || holdsPosted) {
    saveActions.push({ label: "Save as a new draft", onClick: () => void onSaveAsNew() });
  }

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
          navigate(result.opens === "queue" ? "queue" : "posts");
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
          navigate("posts", true);
          return;
        }
        adopt({ ...found, status: "draft" });
        navigate("composer", true);
        return;
      }

      if (result.kind === "lead") point("leads", result.id);
      // A hook form opens the Composer, whose rail is the one place a
      // form is applied. It used to open the Swipe File, which drew the
      // same rows and could do nothing with them.
      else if (result.kind === "specimen") navigate("composer");
      else if (result.kind === "help") point("docs", result.id, result.anchor_text ?? null);
    },
    [draftId, navigate, adopt],
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
        bridgeConnected={bridgeConnected}
      />

      <div className="relative flex min-w-0 flex-1 flex-col">
        <StudioStatusBanner />
        {choosingHome ? (
          <main className="min-h-0 flex-1" aria-busy="true" />
        ) : (
        <>
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
            onSave={() => (holdsPosted ? onCorrectPosted() : void onSave())}
            onPublish={async () => {
            // Publishing acts on the stored post, so the stored post has to be
            // what is on screen. This saved only a post that had never been
            // saved, so after an edit Queue it and Send to LinkedIn acted on
            // the older stored text, and the strip then replaced UNSAVED with
            // the schedule, hiding that the edit was in neither place. Any
            // unsaved edit is written first now. A save that fails leaves the
            // dialog closed, with its reason in the strip, rather than opening
            // a dialog that can only say "save first".
            if (!draft.trim()) {
              setSaveState("failed");
              setSaveError("There is nothing written to publish.");
              return;
            }
            // A click that landed while a save was still on its way used to do
            // nothing at all: no dialog, no word about why, and on a slow
            // machine that is most of a second after every Save. It waits for
            // that save now. What is stored is then what is on screen only if
            // that save wrote this text, so the refs say whether to write
            // again rather than this render's save state, which is a step
            // behind by the time the wait is over.
            await savingDone.current;
            if (!base.current || base.current.content !== latestDraft.current) {
              if (!(await onSave())) return;
            }
            setPublishOpen(true);
          }}
            onDrafts={() => setDraftsOpen(true)}
            onNewPost={() => void onNewPost()}
            onCopy={async () => {
              if (!draft) return false;
              try {
                await navigator.clipboard.writeText(draft);
                return true;
              } catch {
                return false;
              }
            }}
          />
          {saveState === "failed" && saveError ? (
            <SaveReason reason={saveError} actions={saveActions} />
          ) : detachedFrom && !draftId ? (
            <SaveReason
              tone="note"
              reason={`This is a new post. Your draft "${detachedFrom.title}" is kept as it was saved, in Drafts. Save keeps this one as a separate draft.`}
              actions={[
                {
                  label: "Write over that draft instead",
                  onClick: () => {
                    setDraftId(detachedFrom.id);
                    setDetachedFrom(null);
                  },
                },
              ]}
            />
          ) : (
            holdsPosted &&
            posted && (
              <SaveReason
                tone="note"
                reason={`You are editing the text of a post that is already ${postedWord(posted.status)}. Save changes that post, after asking first; Save as a new draft keeps this text as a separate post.`}
                actions={saveActions}
              />
            )
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
            <main className={cn("min-h-0 flex-1", active === "leads" || active === "docs" ? "overflow-hidden" : "overflow-y-auto")}>
              {active === "composer" && (
                <ComposerCanvas
                  value={draft}
                  onChange={onChangeDraft}
                  onReHook={onReHook}
                  swapKey={swapKey}
                  onSave={() => (holdsPosted ? onCorrectPosted() : void onSave())}
                />
              )}
              {active === "setup" && (
                <OnboardingSurface
                  onOpenToday={() => navigate("today")}
                  onOpenHealth={() => navigate("health")}
                  onOpenSettings={() => navigate("settings")}
                />
              )}
              {active === "today" && (
                <TodaySurface
                  onOpenSetup={() => navigate("setup")}
                  onOpenReplies={() => navigate("replies")}
                  onOpenActivity={() => navigate("activity")}
                  onOpenQueue={() => navigate("queue")}
                  onOpenComposer={() => navigate("composer")}
                  onOpenLead={(leadId) => {
                    if (!navigate("leads")) return;
                    focusNonce.current += 1;
                    setFocus({ section: "leads", target: { id: leadId, anchor: null, nonce: focusNonce.current } });
                  }}
                />
              )}
              {active === "record" && (
                <RecordSurface
                  onOpenDraft={onDraftFromCard}
                  onOpenHelp={(documentId, section) => {
                    if (!navigate("docs")) return;
                    focusNonce.current += 1;
                    setFocus({ section: "docs", target: { id: documentId, anchor: section, nonce: focusNonce.current } });
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
              {active === "health" && <HealthSurface onOpenSetup={() => navigate("setup")} />}
              {active === "replies" && (
                <RepliesSurface
                  onOpenSetup={() => navigate("setup")}
                  onOpenLead={(leadId, fromPost) => {
                    if (!navigate("leads")) return;
                    focusNonce.current += 1;
                    setFocus({
                      section: "leads",
                      target: { id: leadId, anchor: null, post: fromPost ?? null, nonce: focusNonce.current },
                    });
                  }}
                />
              )}
              {active === "leads" && <LeadsSurface focus={focusFor("leads")} />}
              {active === "audience" && (
                <AudienceSurface
                  onOpenSetup={() => navigate("setup")}
                  onOpenLead={(leadId) => {
                    if (!navigate("leads")) return;
                    focusNonce.current += 1;
                    setFocus({ section: "leads", target: { id: leadId, anchor: null, nonce: focusNonce.current } });
                  }}
                />
              )}
              {active === "posts" && (
                <PostsSurface
                  onOpenActivity={() => navigate("activity")}
                  onOpenSetup={() => navigate("setup")}
                  onOpenLead={(leadId, fromPost) => {
                    if (!navigate("leads")) return;
                    focusNonce.current += 1;
                    setFocus({
                      section: "leads",
                      target: { id: leadId, anchor: null, post: fromPost ?? null, nonce: focusNonce.current },
                    });
                  }}
                />
              )}
              {active === "outbound" && (
                <OutboundSurface
                  onOpenSetup={() => navigate("setup")}
                  onOpenLead={(leadId) => {
                    if (!navigate("leads")) return;
                    focusNonce.current += 1;
                    setFocus({ section: "leads", target: { id: leadId, anchor: null, nonce: focusNonce.current } });
                  }}
                />
              )}
              {active === "patterns" && <PatternsSurface onOpenSetup={() => navigate("setup")} />}
              {active === "analytics" && <AnalyticsSurface />}
              {/* Brand, about you, and Settings, about this machine: Brand
                  Studio split in two (sections report, batch 5). */}
              {active === "brand" && <BrandSurface onOpenSetup={() => navigate("setup")} />}
              {active === "settings" && <SettingsSurface />}
              {active === "queue" && <QueueSurface onEditText={(postId) => void onEditText(postId)} />}
              {active === "docs" && <DocsSurface focus={focusFor("docs")} />}
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
        </>
        )}
      </div>

      <DraftsPanel
        open={draftsOpen}
        onClose={() => setDraftsOpen(false)}
        currentId={draftId}
        refreshKey={draftsKey}
        onOpen={(chosen) => onOpenDraft(chosen)}
        onNewPost={onNewPost}
        onDeletedCurrent={() => adopt(null)}
      />

      <PublishDialog
        open={publishOpen}
        postId={draftId}
        opening={draft.trim().split("\n")[0] ?? ""}
        content={draft}
        onClose={() => setPublishOpen(false)}
        onDone={(message) => {
          // The post left the composer. Reporting it as "saved" would be the
          // wrong claim, and reporting nothing would leave the author unsure
          // whether an irreversible action happened.
          //
          // The message says "marked as posted" rather than "published"
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
          setDetachedFrom(null);
          setDraftsKey((key) => key + 1);
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
