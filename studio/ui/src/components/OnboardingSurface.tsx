import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Check, Copy, Download, ExternalLink, Loader2 } from "lucide-react";
import {
  OWN_PROFILE_URL,
  confirmIdentity,
  copyExtensionPath,
  createBackup,
  fetchBackups,
  fetchBrowserBridge,
  fetchOnboardingState,
  forgetIdentity,
  launchBridge,
  rejectIdentityCandidate,
  requestSelfImport,
  syncAllActivity,
  type BrowserBridge,
  type CreatorIdentity,
  type OnboardingState,
  type SelfImport,
  type SelfImportKind,
} from "@/lib/api";
import { reportBridge } from "@/lib/bridgeState";
import { setupDone } from "@/lib/setup";
import { useRefresh, type StudioChangeNote } from "@/lib/refresh";
import { cn } from "@/lib/utils";
import { ArchiveImport, archiveStatus } from "./ArchiveImport";
import { RecordSetupFields } from "./RecordSetupFields";
import { AnalyticsExportImport } from "./AnalyticsExportImport";

/**
 * Setup: the studio learns who you are from your own LinkedIn.
 *
 * Five steps, each showing its real state rather than a checkbox the creator
 * ticks: the bridge is connected once the extension has been heard from, you
 * are known when you have said "that's me", and history counts are rows in
 * the database, not intentions.
 *
 * The state is read again while this screen is open, because the interesting
 * moment happens in the other window. The creator opens their profile in the
 * bridge browser, and the question "is this you?" should be waiting here when
 * they look back: the studio's change stream says when anything was written,
 * and this screen reads within about a second of it.
 */
const BACKSTOP_MS = 30_000;

/**
 * Whether a change can alter what Setup shows, by what it shows: the bridge,
 * who you are, each reader's line, your history and what deleting would
 * remove. Not the people who engage, the daily totals or the queue.
 *
 * The reader lines moved to Health in the 2.9.0 merge, which reads on a run
 * itself. The capture rule is kept as track 2 wrote it: it still answers for
 * the state Setup reads, which carries them.
 */
function setupMayChange(change: StudioChangeNote, state: SetupState | null): boolean {
  if (!state) return true;
  switch (change.kind) {
    case "heartbeat":
      // "Connected" carries no time: a heartbeat changes it only when the
      // bridge is shown as gone.
      return !state.bridge.connected;
    case "capture": {
      // A reader's line reads WORKING, LAST READ to the minute: another run
      // of a working reader in the minute its line already shows reads the
      // same. The studio says which minute the run was, so no clock is asked.
      const entry = state.health.find((line) => line.extractor === change.extractor);
      if (!entry || change.drift || entry.state !== "working" || !change.minute) return true;
      return (entry.last_run_at ?? "").slice(0, 16) !== change.minute;
    }
    case "people":
    case "account":
    case "queue":
    case "desk":
    case "ideas":
    case "replies":
    case "collection":
      return false;
    default:
      return true;
  }
}

/** What this screen reads from the onboarding state beyond the shared type. */
type SetupState = OnboardingState & {
  /** Import your history, while one is under way. Kept by the studio, so it survives a restart. */
  sync_chain?: { sequence: SelfImportKind[]; current_kind: SelfImportKind } | null;
  /** Readings of your posts' figures and archive connections: what deleting everything also removes. */
  counts: { readings?: number; connections?: number };
  /** history: your posts read to the end of the list, which is what Today needs. */
  steps: { history?: boolean };
  /** The latest posts import came from an older extension; reloading it is the fix, not importing again. */
  extension_outdated?: boolean;
  /** The bridge heard from needs no reload; an import an older extension read is simply imported again. */
  extension_current?: boolean;
};

export function OnboardingSurface({
  onOpenToday,
  onOpenHealth,
  onOpenSettings,
}: { onOpenToday?: () => void; onOpenHealth?: () => void; onOpenSettings?: () => void } = {}) {
  const [state, setState] = useState<SetupState | null>(null);
  const [bridge, setBridge] = useState<BrowserBridge | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<Note | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await fetchOnboardingState();
      setState(next);
      reportBridge(next.bridge.connected);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
    // A read that fails is said to have failed: an empty list of browsers
    // read as a computer with none, and sent a creator to install Edge over
    // an outage.
    fetchBrowserBridge().then(setBridge).catch(() => setBridge({ browsers: [], extension_path: "", unreachable: true }));
  }, [refresh]);
  // Within about a second of the studio saying something changed, and every
  // BACKSTOP_MS while the window is in view, for what no write announces,
  // such as the bridge going quiet. It was every 3 seconds: about 1,700
  // statements a minute on a screen where nothing was happening. A hidden
  // window is not polled.
  useRefresh(refresh, BACKSTOP_MS, { matters: (change) => setupMayChange(change, state) });

  // The browser that carries the extension, if any. "auto" lets the backend
  // pick, which it does by the same measured rule the Leads screen uses.
  const carrier = bridge?.browsers.find((b) => b.carries_extension === true)?.id ?? "auto";

  // `at` is the step whose button was pressed: what happened is shown there.
  async function act(key: string, work: () => Promise<string | void>, at: Note["at"]) {
    setBusy(key);
    setNote(null);
    try {
      const message = await work();
      if (message) setNote({ text: message, at, error: false });
      await refresh();
    } catch (caught) {
      setNote({ text: caught instanceof Error ? caught.message : "That did not work.", at, error: true });
    } finally {
      setBusy(null);
    }
  }

  // Step 4's block, the archive, opens LinkedIn's download page with the URL alone.
  const open = (url: string, at: Note["at"] = 4) =>
    act(url, async () => (await launchBridge(carrier, url)).message, at);

  if (failed && !state) return <Centered>SETUP UNAVAILABLE. IS THE STUDIO RUNNING?</Centered>;
  if (!state) return <Centered>LOADING SETUP</Centered>;

  const { steps, identity, candidate } = state;
  // Every step ticked. The screen used to end on step 5 with nothing to say
  // that Setup was over or where to go next.
  // The one rule for Setup being done; the studio opens here until it is.
  const finished = setupDone(state);

  return (
    <NoteContext.Provider value={note}>
    <article className="mx-auto max-w-[72ch] px-8 py-8">
      <p className="studio-label">Setup</p>
      <h1 className="studio-title mt-2">Teach the studio who you are</h1>
      <p className="mt-2 text-[14px] leading-relaxed text-ink-secondary">
        The studio reads your own LinkedIn in a browser it opens for you: your profile, your posts, and what
        you have liked and commented on. It all stays in the database on this machine.
      </p>

      <ol className="mt-8 flex flex-col">
        {/* Done once the bridge has been heard from; whether it is running
            now is the line under it. Tied to "connected", the step unticked
            whenever the LinkedIn tab sat in the background for a few minutes. */}
        <Step
          n={1}
          title="Connect the browser"
          done={steps.bridge}
          current={!steps.bridge}
          status={bridgeLine(state)}
        >
          {!state.bridge.connected && (
            <div className="flex flex-wrap items-center gap-2">
              <Primary
                pending={busy === "https://www.linkedin.com/feed/"}
                disabled={busy !== null}
                onPress={() => void open("https://www.linkedin.com/feed/", 1)}
              >
                Open LinkedIn with the bridge
              </Primary>
              {!steps.bridge && (
                <p className="studio-meta text-[10px] text-ink-muted">
                  SIGN IN THERE IF IT ASKS. THIS STEP TICKS BY ITSELF.
                </p>
              )}
            </div>
          )}
          {!state.bridge.connected && bridge && !bridge.browsers.some((b) => b.carries_extension === true) && (
            <LoadByHand bridge={bridge} />
          )}
        </Step>

        <Step
          n={2}
          title="Show it your profile"
          done={steps.identity}
          current={!steps.identity}
          status={
            steps.identity
              ? `Confirmed as linkedin.com/in/${identity?.vanity}`
              : candidate
                ? "Found a profile. Is it you?"
                : "Open your own profile and the studio will recognise it"
          }
        >
          {!steps.identity && !candidate && (
            <Primary
              pending={busy === OWN_PROFILE_URL}
              disabled={busy !== null}
              onPress={() => void open(OWN_PROFILE_URL, 2)}
            >
              Open my profile
            </Primary>
          )}
          {!steps.identity && candidate && (
            <div className="rounded-md border border-edge-strong p-4">
              <p className="text-[15px] font-medium text-ink-primary">{candidate.display_name ?? candidate.vanity}</p>
              {candidate.headline && <p className="mt-1 text-[13px] text-ink-secondary">{candidate.headline}</p>}
              <p className="studio-meta mt-2 text-[10px] text-ink-muted">
                LINKEDIN.COM/IN/{candidate.vanity.toUpperCase()}
                {candidate.location ? ` · ${candidate.location.toUpperCase()}` : ""}
              </p>
              {candidate.evidence.length > 0 && (
                <ul className="mt-3 flex flex-col gap-0.5">
                  {candidate.evidence.map((reason) => (
                    <li key={reason} className="text-[12px] text-ink-muted">
                      {reason}
                    </li>
                  ))}
                </ul>
              )}
              <div className="mt-4 flex gap-2">
                <Primary
                  pending={busy === "confirm"}
                  disabled={busy !== null}
                  opensBrowser={false}
                  onPress={() => void act("confirm", () => confirmIdentity(candidate.vanity), 2)}
                >
                  Yes, that&rsquo;s me
                </Primary>
                <Secondary disabled={busy !== null} onPress={() => void act("reject", rejectIdentityCandidate, 2)}>
                  No
                </Secondary>
              </div>
            </div>
          )}
        </Step>

        <Step
          n={3}
          title="Your profile"
          done={steps.identity && !!identity?.profile_observed_at}
          current={steps.identity}
          status={identity ? profileLine(identity) : "Fills in once you have confirmed it is you"}
        >
          {identity && (
            <ProfileCard
              identity={identity}
              counts={state.counts}
              busy={busy}
              onOpen={(url) => void open(url, 3)}
              onForget={() =>
                void act(
                  "forget",
                  async () => {
                    await forgetIdentity();
                    return "Everything the studio held about you is deleted.";
                  },
                  3,
                )
              }
            />
          )}
        </Step>

        <Step
          n={4}
          title="Your LinkedIn archive"
          done={steps.archive}
          current={!steps.archive}
          status={archiveStatus(state.archive)}
        >
          <ArchiveImport
            state={state.archive}
            opening={busy === state.archive.download_page}
            onOpenPage={(url) => void open(url)}
            onChanged={() => void refresh()}
          />
          {/* LinkedIn's analytics export, beside the archive: the exact figures the archive does not carry. */}
          <AnalyticsExportImport busyUrl={busy} onOpenPage={(url) => void open(url)} />
        </Step>

        <Step
          n={5}
          title="Your history"
          done={!!steps.history}
          current={steps.identity}
          last
          status={
            steps.identity
              ? `${counted(state.counts.posts, "post")}, ${counted(state.counts.comments, "comment")}, ${counted(state.counts.reactions, "reaction")}${
                  steps.history
                    ? ""
                    : state.extension_outdated
                      ? ". Your last posts import came from an older copy of the extension, which cannot tell whether it reached the end: reload the extension on your browser's extensions page, then press Import again beside Posts you wrote"
                      : `. ${state.counts.posts ? "Your posts are in, but the" : "The"} list of your posts has not been read to its end yet: press ${state.counts.posts ? "Import again" : "Import"} beside Posts you wrote`
                }`
              : "Your posts, and what you have liked and commented on"
          }
        >
          {steps.identity && (
            <>
              <p className="mb-3 text-[13px] leading-relaxed text-ink-secondary">
                Each import opens one of your activity pages and scrolls it for you at a steady pace until the list
                ends. Keep that tab in view; it pauses while hidden, and the Stop button on the page ends it.
              </p>
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-edge bg-soft/40 p-3">
                <div className="min-w-0 flex-1 basis-64">
                  <p className="text-[13px] font-medium text-ink-primary">All three, one after another</p>
                  <p className="text-[11px] text-ink-muted">
                    Opens your posts page, then your comments, then your reactions. The bridge scrolls each one to
                    the end and moves to the next page by itself.
                  </p>
                </div>
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() =>
                    void act(
                      "all",
                      async () => {
                        const res = await syncAllActivity();
                        return res.message;
                      },
                      5,
                    )
                  }
                  className="flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-md bg-signal-orange px-3 py-1.5 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-40"
                >
                  {busy === "all" ? (
                    <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                  ) : (
                    <Download className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                  )}
                  Import your history
                </button>
              </div>
              {state.sync_chain && (
                <p className="studio-meta mb-3 text-[10px] text-ink-muted">{chainLine(state.sync_chain)}</p>
              )}
              <div className="flex flex-col divide-y divide-edge border-y border-edge">
                {IMPORTS.map((entry) => (
                  <ImportRow
                    key={entry.kind}
                    label={entry.label}
                    count={state.counts[entry.kind]}
                    last={state.imports.find((i) => i.kind === entry.kind) ?? null}
                    reloadFirst={!state.extension_current}
                    pending={busy === entry.kind}
                    disabled={busy !== null}
                    onImport={() =>
                      void act(
                        entry.kind,
                        async () => {
                          const url = await requestSelfImport(entry.kind);
                          return (await launchBridge(carrier, url)).message;
                        },
                        5,
                      )
                    }
                  />
                ))}
              </div>
            </>
          )}
        </Step>
      </ol>

      {/* From your record (cycle 4, track 7): three optional questions, each
          with its reason and a Skip, kept as asks the section's cards match. */}
      <div className="mb-8 rounded-md border border-edge p-4">
        <RecordSetupFields />
      </div>

      {finished && onOpenToday && (
        <div
          role="status"
          className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-md border border-edge-strong p-4"
        >
          <p className="text-[13px] leading-snug text-ink-primary">
            Setup is done. Each day, start on Today: who to reply to, and how your latest post is doing.
          </p>
          <Primary opensBrowser={false} onPress={onOpenToday}>
            Go to Today
          </Primary>
        </div>
      )}

      {/* Capture health, which used to be listed here, is a section of its
          own: Health, in the rail, with each reader's runs this week and what
          it could not read. Setup is a first-run flow, and the question "is
          the bridge still reading" is asked long after the first run. */}
      <section className="mb-6 flex flex-wrap items-center justify-between gap-3 border-t border-edge pt-4">
        <p className="text-[13px] leading-snug text-ink-secondary">
          Whether each part of the capture is still working is on <strong className="font-medium text-ink-primary">Health</strong>: each
          reader&apos;s runs this week, what it read, and what it could not read.
        </p>
        {onOpenHealth && (
          <Secondary onPress={onOpenHealth}>Open Health</Secondary>
        )}
      </section>

      {/* The one stored thing that could act as the creator on LinkedIn has
          one control now, in Settings under Local security, with Save and
          Delete (sections report, batch 5): Setup showed it with Delete and
          Brand Studio with Save, each answered from its own key. */}
      <section className="flex flex-wrap items-center justify-between gap-3 border-t border-edge pt-4">
        <p className="text-[13px] leading-snug text-ink-secondary">
          {state.session.stored
            ? "A LinkedIn session is stored, used only to hand a post to LinkedIn's scheduler. "
            : "No LinkedIn session is stored. It is only needed to schedule posts on LinkedIn itself. "}
          It is kept, and deleted, in <strong className="font-medium text-ink-primary">Settings</strong>, under Local security.
        </p>
        {onOpenSettings && <Secondary onPress={onOpenSettings}>Open Settings</Secondary>}
      </section>
    </article>
    </NoteContext.Provider>
  );
}

/**
 * What happened after a click, and where it was clicked. The note used to be
 * written at the foot of the page, below Capture health and the session, a
 * screen away from "Open LinkedIn with the bridge", so an error such as "No
 * supported browser" was never seen and people clicked again or gave up.
 */
interface Note {
  text: string;
  /** The step number whose button produced it, or the session section. */
  at: number | "session";
  error: boolean;
}

const NoteContext = createContext<Note | null>(null);

function NoteView({ note }: { note: Note }) {
  const ref = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    ref.current?.scrollIntoView({ block: "nearest" });
    if (note.error) ref.current?.focus();
  }, [note]);
  return (
    <p
      ref={ref}
      tabIndex={-1}
      role={note.error ? "alert" : "status"}
      className={cn(
        "studio-meta mt-3 leading-snug outline-none",
        note.error ? "text-signal-orange-text" : "text-ink-secondary",
      )}
    >
      {note.text}
    </p>
  );
}

const IMPORTS: { kind: SelfImportKind; label: string }[] = [
  { kind: "posts", label: "Posts you wrote" },
  { kind: "comments", label: "Comments you left" },
  { kind: "reactions", label: "Posts you reacted to" },
];

/** "1 comment", "12 posts". */
function counted(count: number, noun: string): string {
  return `${count.toLocaleString()} ${noun}${count === 1 ? "" : "s"}`;
}

function bridgeLine(state: OnboardingState): string {
  const { bridge } = state;
  // Network reading was retired in 2.10.2; the studio says so once, only
  // where it had run, in its own sentence.
  const reading = state.network_reading_retired ? ` ${state.network_reading_retired}` : "";
  // More than one browser: each named, so two clients' bridges can be told
  // apart (cycle 4, track 1, phase 2).
  const others = (bridge.bridges ?? []).length > 1
    ? ` Bridges: ${(bridge.bridges ?? []).map((entry) =>
        `${entry.browser ?? "a browser"}${entry.signed_in_vanity ? ` (${entry.signed_in_vanity})` : ""} ` +
        (entry.connected ? "connected" : `last heard from ${ago(entry.seconds_ago)}`)).join("; ")}.`
    : "";
  if (bridge.connected) {
    return `Connected${bridge.extension_version ? `, extension ${bridge.extension_version}` : ""}.${reading}${others}`;
  }
  if (bridge.seconds_ago !== null) return `Last heard from ${ago(bridge.seconds_ago)}. Open a LinkedIn tab in the bridge browser.`;
  return "Not seen yet";
}

function profileLine(identity: CreatorIdentity): string {
  const parts = [
    identity.positions.length ? `${identity.positions.length} roles` : null,
    identity.education.length ? `${identity.education.length} schools` : null,
    identity.skills.length ? `${identity.skills.length} skills` : null,
    identity.contact_observed_at ? "contact info" : null,
  ].filter(Boolean);
  return parts.length ? `Read: ${parts.join(", ")}` : "Confirmed. Details arrive as the profile page renders.";
}

function ago(seconds: number): string {
  if (seconds < 90) return `${seconds}s ago`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 172800) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86400)} days ago`;
}

function Step({
  n,
  title,
  done,
  current,
  status,
  last,
  children,
}: {
  n: number;
  title: string;
  done: boolean;
  current: boolean;
  status: string;
  last?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <li className="relative flex gap-4 pb-8">
      {!last && <span className="absolute top-7 bottom-0 left-[13px] w-px bg-edge" aria-hidden="true" />}
      <span
        className={cn(
          "relative z-[1] grid size-7 shrink-0 place-items-center rounded-full border text-[12px] tabular-nums",
          done
            ? "border-signal-orange bg-signal-orange text-on-signal"
            : current
              ? "border-edge-strong bg-ink text-ink-primary"
              : "border-edge bg-ink text-ink-muted",
        )}
        role="img"
        aria-label={done ? `Step ${n}, done` : `Step ${n}`}
      >
        {done ? <Check className="size-3.5" strokeWidth={2.5} aria-hidden="true" /> : n}
      </span>
      <div className="min-w-0 flex-1 pt-0.5">
        <p className={cn("text-[14px] font-medium", done || current ? "text-ink-primary" : "text-ink-muted")}>{title}</p>
        <p className="studio-meta mt-0.5 text-[11px] text-ink-muted">{status}</p>
        {children && <div className="mt-3">{children}</div>}
        <StepNote n={n} />
      </div>
    </li>
  );
}

function StepNote({ n }: { n: number }) {
  const note = useContext(NoteContext);
  return note?.at === n ? <NoteView note={note} /> : null;
}

function ProfileCard({
  identity,
  counts,
  busy,
  onOpen,
  onForget,
}: {
  identity: CreatorIdentity;
  counts: SetupState["counts"];
  busy: string | null;
  onOpen: (url: string) => void;
  onForget: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const base = identity.profile_url ?? `https://www.linkedin.com/in/${identity.vanity}/`;
  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="text-[15px] font-medium text-ink-primary">{identity.display_name ?? identity.vanity}</p>
        {identity.headline && <p className="mt-1 text-[13px] text-ink-secondary">{identity.headline}</p>}
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 border-y border-edge py-3">
        <Field label="Location" value={identity.location} />
        <Field label="Company" value={identity.current_company} />
        <Field label="Followers" value={identity.follower_count?.toLocaleString() ?? null} />
        <Field label="Connections" value={identity.connection_count?.toLocaleString() ?? null} />
        <Field label="Email" value={identity.email} />
        <Field label="Phone" value={identity.phone} />
        <Field label="Birthday" value={identity.birthday} />
        <Field label="Websites" value={identity.websites.length ? identity.websites.join(", ") : null} />
      </dl>

      {identity.about && (
        <p className="line-clamp-4 text-[13px] leading-relaxed whitespace-pre-wrap text-ink-secondary">{identity.about}</p>
      )}

      {identity.positions.length > 0 && (
        <List label="Experience">
          {identity.positions.map((p, i) => (
            <li key={i}>
              <span className="text-ink-primary">{p.title}</span>
              {p.company && <span className="text-ink-secondary">, {p.company}</span>}
              {p.date_range && <span className="studio-meta ml-2 text-[10px] text-ink-muted">{p.date_range}</span>}
            </li>
          ))}
        </List>
      )}

      {identity.education.length > 0 && (
        <List label="Education">
          {identity.education.map((e, i) => (
            <li key={i}>
              <span className="text-ink-primary">{e.school}</span>
              {e.degree && <span className="text-ink-secondary">, {e.degree}</span>}
            </li>
          ))}
        </List>
      )}

      {identity.skills.length > 0 && (
        <div>
          <p className="studio-meta mb-1.5 text-[10px] text-ink-muted">SKILLS</p>
          <div className="flex flex-wrap gap-1">
            {identity.skills.map((skill) => (
              <span key={skill} className="rounded-full border border-edge px-2 py-0.5 text-[11px] text-ink-secondary">
                {skill}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* What the profile page alone cannot show: contact info lives in its
          own panel, and the profile lists only a few skills. Each opens the
          page that has it, and the extension reads it on arrival. */}
      <div className="flex flex-wrap gap-2">
        <Secondary disabled={busy !== null} onPress={() => onOpen(`${base}overlay/contact-info/`)}>
          <ExternalLink className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
          Read contact info
        </Secondary>
        <Secondary disabled={busy !== null} onPress={() => onOpen(`${base}details/skills/`)}>
          <ExternalLink className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
          Read all skills
        </Secondary>
        <Secondary disabled={busy !== null} onPress={() => onOpen(base)}>
          <ExternalLink className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
          Read profile again
        </Secondary>
      </div>

      <button
        type="button"
        onClick={() => setConfirming(true)}
        disabled={busy !== null || confirming}
        aria-expanded={confirming}
        className="studio-meta self-start text-[10px] text-ink-muted transition-colors hover:text-signal-orange-text disabled:opacity-40"
      >
        NOT YOU, OR WANT IT GONE? DELETE EVERYTHING THE STUDIO HOLDS ABOUT YOU
      </button>
      {confirming && (
        <ForgetPanel
          identity={identity}
          counts={counts}
          busy={busy}
          onCancel={() => setConfirming(false)}
          onConfirm={onForget}
        />
      )}
    </div>
  );
}

const plural = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString()} ${n === 1 ? one : many}`;

/**
 * The second, deliberate step before deleting everything. This used to be one
 * click on a 10 px line, with no confirmation, no list of what goes and no
 * backup; deleting a creator profile, which destroys less, asks you to type
 * its name. It says what will be deleted, whether a backup exists, offers one,
 * and waits for a typed word.
 */
function ForgetPanel({
  identity,
  counts,
  busy,
  onCancel,
  onConfirm,
}: {
  identity: CreatorIdentity;
  counts: SetupState["counts"];
  busy: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const [typed, setTyped] = useState("");
  const [backup, setBackup] = useState<string | null>(null);
  const [backingUp, setBackingUp] = useState(false);

  useEffect(() => {
    let live = true;
    fetchBackups()
      .then((listing) => {
        if (!live) return;
        // The listing is sorted by name, so the newest is found by its time.
        const latest = [...listing.backups].sort((a, b) => b.modified.localeCompare(a.modified))[0];
        setBackup(
          latest
            ? `The latest backup of the studio is from ${latest.modified.slice(0, 16).replace("T", " ")}, ${latest.name}.`
            : "There is no backup of the studio yet, so this could not be brought back.",
        );
      })
      .catch(() => live && setBackup("Whether a backup exists could not be checked."));
    return () => {
      live = false;
    };
  }, []);

  async function backUp() {
    setBackingUp(true);
    try {
      const made = await createBackup("before-forget");
      setBackup(`Backed up just now, to ${made.archive}.`);
    } catch (caught) {
      setBackup(`The backup did not work: ${caught instanceof Error ? caught.message : "unknown error"}.`);
    } finally {
      setBackingUp(false);
    }
  }

  const profileParts = [
    identity.positions.length ? plural(identity.positions.length, "role") : null,
    identity.education.length ? plural(identity.education.length, "school") : null,
    identity.skills.length ? plural(identity.skills.length, "skill") : null,
    identity.contact_observed_at ? "contact info" : null,
  ].filter(Boolean);
  const ready = typed.trim().toLowerCase() === "delete";

  return (
    <section
      aria-label="Delete everything the studio holds about you"
      className="rounded-md border border-signal-orange p-4"
    >
      <p className="text-[13px] font-medium text-ink-primary">This deletes, from this computer, and cannot be undone:</p>
      <ul className="mt-2 flex list-disc flex-col gap-0.5 pl-5 text-[13px] text-ink-secondary">
        <li>
          Your confirmed profile, linkedin.com/in/{identity.vanity}
          {profileParts.length ? `: ${profileParts.join(", ")}` : ""}
        </li>
        <li>
          {plural(counts.posts, "of your posts", "of your posts")}
          {counts.readings !== undefined ? ` and ${plural(counts.readings, "reading")} of their figures` : ""}
        </li>
        <li>
          {plural(counts.comments, "comment")} and {plural(counts.reactions, "reaction")} of yours on other posts
        </li>
        <li>
          {counts.connections !== undefined ? `${plural(counts.connections, "connection")} and ` : ""}the record of your
          archive and history imports
        </li>
        {/* From your record (cycle 4, track 7): forgetting clears these too. */}
        <li>
          What you asked From your record for, its daily cards, your marks on them and your notes, and the saved posts,
          follows, votes, articles, reposts and searches your archive brought
        </li>
        {/* Phase 3 of the Telegram bot: forgetting clears these too. */}
        <li>Everything you sent your Telegram bot (your collection), and the links it asked Today to open</li>
        <li>The name, headline and company Setup filled in your Brand byline, unless you changed them</li>
      </ul>
      <p className="mt-2 text-[12px] text-ink-muted">Your leads, drafts and the posts you wrote in the studio are kept.</p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <p role="status" className="min-w-0 break-words text-[12px] text-ink-secondary">
          {backup ?? "Looking for a backup."}
        </p>
        <Secondary disabled={backingUp || busy !== null} onPress={() => void backUp()}>
          {backingUp && <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />}
          Back up first
        </Secondary>
      </div>

      <label className="mt-3 flex flex-col gap-1 text-[12px] text-ink-secondary">
        Type delete to confirm
        <input
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          autoFocus
          className="w-48 rounded-md border border-edge bg-ink px-2 py-1 text-[13px] text-ink-primary outline-none focus-visible:border-edge-strong"
        />
      </label>
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          disabled={!ready || busy !== null}
          onClick={onConfirm}
          className="rounded-md bg-signal-orange px-3 py-1.5 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-40"
        >
          Delete everything
        </button>
        <Secondary disabled={busy !== null} onPress={onCancel}>
          Keep it
        </Secondary>
      </div>
    </section>
  );
}

/**
 * What to do when no browser here loads the bridge by itself: most Mac and
 * many Windows machines have only Chrome, which ignores --load-extension. The
 * launch message pointed at a folder this screen never showed.
 */
const names = (browsers: { name: string }[], says: string) =>
  browsers.length ? `${browsers.map((b) => b.name).join(", ")} ${says}` : "";

function LoadByHand({ bridge }: { bridge: BrowserBridge }) {
  const [copied, setCopied] = useState<string | null>(null);
  const none = bridge.browsers.length === 0;
  return (
    <div className="mt-4 rounded-md border border-edge p-3">
      <p className="text-[13px] leading-relaxed text-ink-secondary">
        {/* Not asked is not the same as none found. */}
        {bridge.unreachable
          ? "The studio could not be asked which browsers this computer has, so none is listed. Check that it is running, then come back to this step."
          : none
          ? "No Chromium browser was found on this computer. Install Microsoft Edge or Brave, which load the bridge by themselves, then click the button above."
          : `${[
              names(bridge.browsers.filter((b) => b.carries_extension === false), "cannot load the bridge by itself"),
              // Not probed is not the same as cannot.
              names(bridge.browsers.filter((b) => b.carries_extension !== false), "has not been checked for loading the bridge on this computer"),
            ]
              .filter(Boolean)
              .join(". ")}. Install Microsoft Edge or Brave and click the button above, or load it by hand.`}
      </p>
      {!none && (
        <>
          <p className="mt-2 text-[13px] leading-relaxed text-ink-secondary">
            To load it by hand, open your browser&rsquo;s extensions page, turn on developer mode, choose Load
            unpacked, and point it at this folder. Help has the steps, under Install the browser extension.
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Secondary
              onPress={() =>
                void copyExtensionPath()
                  .then(() => setCopied("COPIED TO THE CLIPBOARD"))
                  .catch(() => setCopied("COULD NOT REACH THE CLIPBOARD. COPY IT FROM BELOW."))
              }
            >
              <Copy className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
              Copy the folder path
            </Secondary>
            {copied && (
              <p role="status" className="studio-meta text-[10px] text-ink-muted">
                {copied}
              </p>
            )}
          </div>
          <p className="studio-meta mt-2 break-all text-[10px] text-ink-muted">{bridge.extension_path}</p>
        </>
      )}
    </div>
  );
}

function ImportRow({
  label,
  count,
  last,
  reloadFirst,
  pending,
  disabled,
  onImport,
}: {
  label: string;
  count: number;
  last: SelfImport | null;
  reloadFirst: boolean;
  pending: boolean;
  disabled: boolean;
  onImport: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5">
      <div className="min-w-0">
        <p className="text-[13px] text-ink-primary">{label}</p>
        <p className="studio-meta mt-0.5 text-[10px] text-ink-muted">
          {count} STORED{last ? ` · ${importLine(last, reloadFirst)}` : ""}
        </p>
      </div>
      <Secondary disabled={disabled} onPress={onImport}>
        {pending && <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />}
        {count > 0 ? "Import again" : "Import"}
      </Secondary>
    </div>
  );
}

function chainLine(chain: { sequence: SelfImportKind[]; current_kind: SelfImportKind }): string {
  const after = chain.sequence.slice(chain.sequence.indexOf(chain.current_kind) + 1);
  return `IMPORTING ONE AFTER ANOTHER: ${chain.current_kind.toUpperCase()} NOW${
    after.length ? `, THEN ${after.join(" AND ").toUpperCase()}` : ", THE LAST ONE"
  }`;
}

// Only "end_of_list" is the whole list. The others read part of it, and say so,
// because a partial history taken for a whole one is how real leads were
// offered for deletion as strangers.
function importLine(entry: SelfImport, reloadFirst: boolean): string {
  const read = entry.items_seen ?? 0;
  // The extension does not scroll a hidden tab, and says so; this read
  // SCROLLING NOW while nothing moved.
  if (!entry.finished_at && entry.outcome === "paused_hidden") {
    return `PAUSED AT ${read}: BRING THE LINKEDIN TAB TO THE FRONT TO GO ON`;
  }
  if (!entry.finished_at) return entry.started_at ? "SCROLLING NOW" : "WAITING FOR THE PAGE TO OPEN";
  if (entry.outcome === "end_of_list") return `READ TO THE END: ${read}`;
  if (entry.outcome === "stopped") return `STOPPED AT ${read}`;
  if (entry.outcome === "left_page") return `LEFT THE PAGE AT ${read}`;
  if (entry.outcome === "superseded") return "REPLACED BY A NEWER IMPORT";
  if (entry.outcome === "expired") return "EXPIRED, CLICK IMPORT AGAIN";
  if (entry.outcome === "not_opened") return "NOT STARTED, NO BROWSER WITH THE BRIDGE OPENED";
  if (entry.outcome === "nothing_read") return "NOTHING READ. OPEN THE PAGE AND IMPORT AGAIN";
  if (entry.outcome === "stalled") return `THE LIST STOPPED LOADING AT ${read}. IMPORT AGAIN`;
  if (entry.outcome === "round_limit") return `READ ${read}, THE MOST ONE IMPORT READS`;
  // An older extension said "completed" for every import, so whether it
  // reached the end is not known. It keeps running until it is reloaded, and
  // importing again before that only repeats this, so say to reload it, but
  // only while the bridge heard from still needs it: one that reloaded
  // itself since needs only Import again.
  return reloadFirst
    ? `READ ${read} WITH AN OLDER EXTENSION, END NOT KNOWN. RELOAD IT ON THE BROWSER'S EXTENSIONS PAGE, THEN IMPORT AGAIN`
    : `READ ${read} WITH AN OLDER EXTENSION, END NOT KNOWN. IMPORT AGAIN`;
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-[11px] text-ink-muted">{label}</dt>
      <dd className="studio-meta truncate text-right text-ink-secondary">{value ?? "Not read"}</dd>
    </div>
  );
}

function List({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="studio-meta mb-1.5 text-[10px] text-ink-muted">{label.toUpperCase()}</p>
      <ul className="flex flex-col gap-1 text-[13px]">{children}</ul>
    </div>
  );
}

function Primary({
  children,
  pending,
  disabled,
  opensBrowser = true,
  onPress,
}: {
  children: React.ReactNode;
  pending?: boolean;
  disabled?: boolean;
  /** Shows the external-link mark, for buttons that open the bridge browser. */
  opensBrowser?: boolean;
  onPress: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onPress}
      disabled={disabled}
      className="flex items-center gap-1.5 rounded-md bg-signal-orange px-3 py-1.5 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-40"
    >
      {pending ? (
        <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
      ) : opensBrowser ? (
        <ExternalLink className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
      ) : null}
      {children}
    </button>
  );
}

function Secondary({
  children,
  disabled,
  onPress,
}: {
  children: React.ReactNode;
  disabled?: boolean;
  onPress: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onPress}
      disabled={disabled}
      className="flex items-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
    >
      {children}
    </button>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid h-full place-items-center px-8">
      <p className="studio-meta max-w-[40ch] text-center leading-relaxed text-ink-muted">{children}</p>
    </div>
  );
}
