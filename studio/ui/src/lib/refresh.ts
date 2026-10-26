import { useEffect, useRef, useState } from "react";
import { onStudioBack, shownProfileId } from "@/lib/api";

/** Data older than this is read again when the window comes back into view. */
const STALE_ON_RETURN_MS = 15_000;

/**
 * The least time between two reads a screen makes because the studio said
 * something changed. A burst of captures is one read, and one more for what
 * arrived during it, never one read per capture.
 */
const CHANGE_GAP_MS = 1_000;

/**
 * How long before the window came back a read may have started and still be
 * the read it made on coming back. Both happen in one visibilitychange, so
 * this is slack, not a wait.
 */
const RETURN_SLACK_MS = 250;

/** The change stream (studio/backend/routers/events.py). */
const EVENTS_PATH = "/api/v1/events";

/**
 * What the studio says changed, in its own words (studio/backend/changes.py).
 * "readings" are one post's figures and "account" the creator's daily
 * figures; "people" is someone engaging with a post of the creator's and
 * "outbound" the creator engaging elsewhere; "desk" is a post the phone asked
 * the desk to read, "ideas" the daily section's cards. "database" is a write nothing
 * announced (the command line, a second studio, a path that does not say what
 * it wrote): every listener takes it as "anything may have changed".
 */
export type StudioChange =
  | "capture"
  | "heartbeat"
  | "posts"
  | "readings"
  | "account"
  | "people"
  | "outbound"
  | "identity"
  | "imports"
  | "queue"
  | "desk"
  | "ideas"
  | "database";

/** Every kind, for a screen whose one read shows whatever the bridge writes. */
export const ANY_CHANGE: readonly StudioChange[] = [
  "capture",
  "heartbeat",
  "posts",
  "readings",
  "account",
  "people",
  "outbound",
  "identity",
  "imports",
  "queue",
  "desk",
  "ideas",
  "database",
];

/**
 * One change the stream reported, with the small identifiers a screen decides
 * by. Never a name or text; a change missing one means "this kind, anywhere".
 */
export interface StudioChangeNote {
  kind: StudioChange;
  /** capture: which reader ran. */
  extractor?: string;
  /** capture: whether it could not read fields it should have. */
  drift?: boolean;
  /** capture: the minute it ran, in UTC, as Setup prints it. */
  minute?: string;
  /** heartbeat: whether the extension said how many captures it holds. */
  waiting?: boolean;
  /** readings, people: the post, when the write was about one. */
  post?: string;
  /** people: how they engaged: comment, reaction or repost. */
  interaction?: string;
  /** people: who, by the studio's own id. */
  lead?: string;
}

/**
 * What a screen listens for. `matters` says whether a change can alter what
 * the screen shows; a "database" change is never asked, because nothing names
 * it, so it always can. `gapMs` is the least time between two reads the
 * stream causes, and the last change is always read once it has passed.
 */
export interface Listen {
  matters: (change: StudioChangeNote) => boolean;
  gapMs?: number;
}

/**
 * Called with the changes the stream reported. `returnedAt` is set when the
 * stream caught the window up on what changed while it was hidden: the moment
 * the window came back, so a screen that read then already has the news. It
 * is null for a change as it happened, and for a reconnect the browser made
 * by itself.
 */
type ChangeListener = (changes: readonly StudioChangeNote[], returnedAt: number | null) => void;

/** What the stream says when it cannot say what changed. */
const ANYTHING: readonly StudioChangeNote[] = [{ kind: "database" }];

const changeListeners = new Set<ChangeListener>();

/** Calls the listener with each change the stream reports. Returns the unsubscribe. */
export function onStudioChange(listener: ChangeListener): () => void {
  changeListeners.add(listener);
  return () => {
    changeListeners.delete(listener);
  };
}

function announce(changes: readonly StudioChangeNote[], returnedAt: number | null): void {
  for (const listener of changeListeners) listener(changes, returnedAt);
}

function isChange(kind: unknown): kind is StudioChange {
  return typeof kind === "string" && (ANY_CHANGE as readonly string[]).includes(kind);
}

function parsed(data: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(data);
    return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

// The window's one stream and what it last heard. Module state rather than a
// component's, because a window has one stream however many screens listen,
// and the browser allows only six connections to the studio at once.
let source: EventSource | null = null;
let lastId: string | null = null;
let heardHello = false;
let returnedAt: number | null = null;

function openStream(): void {
  if (typeof EventSource === "undefined" || document.visibilityState !== "visible") return;
  if (source && source.readyState !== EventSource.CLOSED) return;
  // The id names what this window last heard, so the studio can say whether
  // anything changed while the stream was closed.
  const stream = new EventSource(lastId ? `${EVENTS_PATH}?since=${encodeURIComponent(lastId)}` : EVENTS_PATH);
  stream.addEventListener("hello", (event) => {
    const message = event as MessageEvent<string>;
    if (message.lastEventId) lastId = message.lastEventId;
    const hello = parsed(message.data);
    const first = !heardHello;
    heardHello = true;
    // EventSource cannot name the profile this window shows, so the stream
    // names the one it serves. Reading again on a different one is how the
    // window learns it is stale, from the answer, as every read does.
    const shown = shownProfileId();
    const otherProfile = shown !== null && typeof hello?.profile === "string" && hello.profile !== shown;
    // The screens' own first reads are their news on opening. After that, a
    // hello that says something changed is news this window missed.
    if (otherProfile || (!first && hello?.changed === true)) announce(ANYTHING, returnedAt);
    returnedAt = null;
  });
  stream.addEventListener("change", (event) => {
    const message = event as MessageEvent<string>;
    if (message.lastEventId) lastId = message.lastEventId;
    const body = parsed(message.data);
    const listed = Array.isArray(body?.changes) ? body.changes : [];
    const changes = listed.filter(
      (change): change is StudioChangeNote =>
        typeof change === "object" && change !== null && isChange((change as { kind?: unknown }).kind),
    );
    // An older studio sent the kinds alone.
    const kinds = Array.isArray(body?.kinds) ? body.kinds.filter(isChange) : [];
    if (changes.length) announce(changes, null);
    else if (kinds.length) announce(kinds.map((kind) => ({ kind })), null);
  });
  stream.addEventListener("error", () => {
    // A dropped connection, as when the studio restarts, is reconnected by
    // the browser itself. A refusal closes the stream for good; coming back
    // into view, or the studio answering again, opens it again.
    returnedAt = null;
    if (stream.readyState === EventSource.CLOSED && source === stream) source = null;
  });
  source = stream;
}

function closeStream(): void {
  source?.close();
  source = null;
}

/**
 * The window's change stream: open while the window is in view, closed while
 * it is hidden, so a hidden window still costs the studio nothing. On coming
 * back it opens again naming the last id it heard, and the studio says
 * whether anything changed meanwhile. The shell (App.tsx) calls this once;
 * screens listen through useRefresh's `on`.
 */
export function useStudioStream(): void {
  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        returnedAt = Date.now();
        openStream();
      } else {
        closeStream();
      }
    };
    const stopBack = onStudioBack(openStream);
    document.addEventListener("visibilitychange", onVisibility);
    openStream();
    return () => {
      stopBack();
      document.removeEventListener("visibilitychange", onVisibility);
      closeStream();
    };
  }, []);
}

/**
 * Keeps an open screen's data current, without polling a window nobody sees.
 *
 * Queue, Leads and Posts read once when opened, so a post that came due, or
 * a person the bridge captured from the other window, appeared only after
 * moving away and back; and a screen that failed while the studio was down
 * stayed failed after it returned. This reads `load` again:
 *
 * - when the studio answers again after an outage;
 * - when the window comes back into view and the data is older than
 *   STALE_ON_RETURN_MS, which is the cheap answer to "left open overnight";
 * - when the studio's change stream reports a change that can alter what the
 *   screen shows: one of the kinds in `on`, or one its rule says yes to,
 *   while a write nothing named always can. Within about a second of the
 *   write, and at most once per gap (a second unless the rule says) while
 *   changes keep coming, with the last one always read;
 * - every `everyMs` while the window is in view, for the few screens whose
 *   point is to show change as it happens. With `on`, this is only the
 *   backstop for what no write announces, such as the bridge going quiet.
 *   A hidden window is not polled.
 *
 * The screen's own first read stays the screen's; this only reads again.
 * `load` may change between renders; the latest one is used.
 */
export function useRefresh(load: () => unknown, everyMs?: number, on?: readonly StudioChange[] | Listen): void {
  const latest = useRef(load);
  latest.current = load;
  const lastRead = useRef(Date.now());
  // The rule is read when a change arrives, so a screen may pass a fresh one
  // each render that looks at what the screen shows now.
  const rule = useRef<Listen | null>(null);
  rule.current = !on
    ? null
    : isKinds(on)
      ? { matters: (change: StudioChangeNote) => on.includes(change.kind) }
      : on;
  const listening = Boolean(on);
  const gapMs = (on && !isKinds(on) ? on.gapMs : undefined) ?? CHANGE_GAP_MS;

  useEffect(() => {
    // A read that fails leaves the screen as its own loader decides; it is
    // never an unhandled rejection in the console.
    const read = () => {
      lastRead.current = Date.now();
      const pending = latest.current();
      if (pending instanceof Promise) pending.catch(() => undefined);
    };
    const onReturn = () => {
      if (document.visibilityState === "visible" && Date.now() - lastRead.current >= STALE_ON_RETURN_MS) read();
    };
    const stopBack = onStudioBack(read);
    window.addEventListener("focus", onReturn);
    document.addEventListener("visibilitychange", onReturn);
    const timer = everyMs
      ? window.setInterval(() => {
          if (document.visibilityState === "visible") read();
        }, everyMs)
      : undefined;
    // A read the stream asked for, when a change can alter what the screen
    // shows: now, or once gapMs has passed since the last read. A read
    // already waiting covers whatever comes next, so the last change is
    // always read and a burst is never one read each.
    let waiting: number | undefined;
    const stopChange = listening
      ? onStudioChange((changed, returnedAt) => {
          const matters = rule.current?.matters;
          if (!matters) return;
          // A write nothing named may be anything, so every listener reads it.
          if (!changed.some((change) => change.kind === "database" || matters(change))) return;
          if (returnedAt !== null && lastRead.current >= returnedAt - RETURN_SLACK_MS) return;
          if (waiting !== undefined) return;
          const wait = lastRead.current + gapMs - Date.now();
          if (wait <= 0) {
            read();
            return;
          }
          waiting = window.setTimeout(() => {
            waiting = undefined;
            read();
          }, wait);
        })
      : undefined;
    return () => {
      stopBack();
      window.removeEventListener("focus", onReturn);
      document.removeEventListener("visibilitychange", onReturn);
      if (timer !== undefined) window.clearInterval(timer);
      stopChange?.();
      if (waiting !== undefined) window.clearTimeout(waiting);
    };
  }, [everyMs, listening, gapMs]);
}

function isKinds(on: readonly StudioChange[] | Listen): on is readonly StudioChange[] {
  return Array.isArray(on);
}

/**
 * A count that goes up each time the studio answers again after an outage.
 *
 * For a screen that reads its data in an effect: listed among the effect's
 * dependencies, it runs that read again when the studio is back.
 */
export function useStudioBack(): number {
  const [returns, setReturns] = useState(0);
  useEffect(() => onStudioBack(() => setReturns((count) => count + 1)), []);
  return returns;
}
