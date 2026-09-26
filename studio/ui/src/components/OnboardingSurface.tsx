import { useCallback, useEffect, useState } from "react";
import { Check, ExternalLink, Loader2 } from "lucide-react";
import {
  OWN_PROFILE_URL,
  confirmIdentity,
  deleteLinkedInSession,
  fetchBrowserBridge,
  fetchOnboardingState,
  forgetIdentity,
  launchBridge,
  rejectIdentityCandidate,
  requestSelfImport,
  type BrowserBridge,
  type CreatorIdentity,
  type OnboardingState,
  type SelfImport,
  type SelfImportKind,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Setup: the studio learns who you are from your own LinkedIn.
 *
 * Four steps, each showing its real state rather than a checkbox the creator
 * ticks: the bridge is connected when the extension has been heard from, you
 * are known when you have said "that's me", and history counts are rows in
 * the database, not intentions.
 *
 * The state is polled while this screen is open, because the interesting
 * moment happens in the other window. The creator opens their profile in the
 * bridge browser, and the question "is this you?" should be waiting here when
 * they look back.
 */
const POLL_MS = 3000;

export function OnboardingSurface() {
  const [state, setState] = useState<OnboardingState | null>(null);
  const [bridge, setBridge] = useState<BrowserBridge | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setState(await fetchOnboardingState());
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), POLL_MS);
    fetchBrowserBridge().then(setBridge).catch(() => setBridge({ browsers: [], extension_path: "" }));
    return () => window.clearInterval(timer);
  }, [refresh]);

  // The browser that carries the extension, if any. "auto" lets the backend
  // pick, which it does by the same measured rule the Leads screen uses.
  const carrier = bridge?.browsers.find((b) => b.carries_extension === true)?.id ?? "auto";

  async function act(key: string, work: () => Promise<string | void>) {
    setBusy(key);
    setNote(null);
    try {
      const message = await work();
      if (message) setNote(message);
      await refresh();
    } catch (caught) {
      setNote(caught instanceof Error ? caught.message : "That did not work.");
    } finally {
      setBusy(null);
    }
  }

  const open = (url: string) => act(url, async () => (await launchBridge(carrier, url)).message);

  if (failed && !state) return <Centered>SETUP UNAVAILABLE. IS THE STUDIO RUNNING?</Centered>;
  if (!state) return <Centered>LOADING SETUP</Centered>;

  const { steps, identity, candidate } = state;

  return (
    <article className="mx-auto max-w-[72ch] px-8 py-8">
      <p className="studio-label">Setup</p>
      <h2 className="studio-title mt-2">Teach the studio who you are</h2>
      <p className="mt-2 text-[14px] leading-relaxed text-ink-secondary">
        The studio reads your own LinkedIn in a browser it opens for you: your profile, your posts, and what
        you have liked and commented on. It all stays in the database on this machine.
      </p>

      <ol className="mt-8 flex flex-col">
        <Step
          n={1}
          title="Connect the browser"
          done={state.bridge.connected}
          current={!state.bridge.connected}
          status={bridgeLine(state)}
        >
          {!state.bridge.connected && (
            <div className="flex flex-wrap items-center gap-2">
              <Primary
                pending={busy === "https://www.linkedin.com/feed/"}
                disabled={busy !== null}
                onPress={() => void open("https://www.linkedin.com/feed/")}
              >
                Open LinkedIn with the bridge
              </Primary>
              <p className="studio-meta text-[10px] text-ink-muted">
                SIGN IN THERE IF IT ASKS. THIS STEP TICKS BY ITSELF.
              </p>
            </div>
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
              onPress={() => void open(OWN_PROFILE_URL)}
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
                  onPress={() => void act("confirm", () => confirmIdentity(candidate.vanity))}
                >
                  Yes, that&rsquo;s me
                </Primary>
                <Secondary disabled={busy !== null} onPress={() => void act("reject", rejectIdentityCandidate)}>
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
              busy={busy}
              onOpen={(url) => void open(url)}
              onForget={() =>
                void act("forget", async () => {
                  await forgetIdentity();
                  return "Everything the studio held about you is deleted.";
                })
              }
            />
          )}
        </Step>

        <Step
          n={4}
          title="Your history"
          done={steps.posts && steps.activity}
          current={steps.identity}
          last
          status={
            steps.identity
              ? `${state.counts.posts} posts, ${state.counts.comments} comments, ${state.counts.reactions} reactions`
              : "Your posts, and what you have liked and commented on"
          }
        >
          {steps.identity && (
            <>
              <p className="mb-3 text-[13px] leading-relaxed text-ink-secondary">
                Each import opens one of your activity pages and scrolls it for you at a steady pace until the list
                ends. Keep that tab in view; it pauses while hidden, and the Stop button on the page ends it.
              </p>
              <div className="flex flex-col divide-y divide-edge border-y border-edge">
                {IMPORTS.map((entry) => (
                  <ImportRow
                    key={entry.kind}
                    label={entry.label}
                    count={state.counts[entry.kind]}
                    last={state.imports.find((i) => i.kind === entry.kind) ?? null}
                    pending={busy === entry.kind}
                    disabled={busy !== null}
                    onImport={() =>
                      void act(entry.kind, async () => {
                        const url = await requestSelfImport(entry.kind);
                        return (await launchBridge(carrier, url)).message;
                      })
                    }
                  />
                ))}
              </div>
            </>
          )}
        </Step>
      </ol>

      {/* The one stored thing that could act as the creator on LinkedIn.
          Captured only from the extension's Sync button, kept only for the
          live send in the publish dialog, and deletable here. */}
      <section className="border-t border-edge pt-4">
        <p className="studio-meta text-[10px] text-ink-muted">LINKEDIN SESSION</p>
        <div className="mt-1 flex items-center justify-between gap-4">
          <p className="text-[13px] text-ink-secondary">
            {state.session.stored
              ? `Stored${state.session.saved_at ? ` since ${state.session.saved_at.slice(0, 10)}` : ""}, used only to hand a post to LinkedIn's scheduler.`
              : "Not stored. Only needed to schedule posts on LinkedIn itself; the extension's Sync button captures it."}
          </p>
          {state.session.stored && (
            <Secondary
              disabled={busy !== null}
              onPress={() =>
                void act("session", async () => {
                  await deleteLinkedInSession();
                  return "The LinkedIn session is deleted.";
                })
              }
            >
              Delete
            </Secondary>
          )}
        </div>
      </section>

      {note && (
        <p role="status" className="studio-meta mt-6 leading-snug text-ink-secondary">
          {note}
        </p>
      )}
    </article>
  );
}

const IMPORTS: { kind: SelfImportKind; label: string }[] = [
  { kind: "posts", label: "Posts you wrote" },
  { kind: "comments", label: "Comments you left" },
  { kind: "reactions", label: "Posts you reacted to" },
];

function bridgeLine(state: OnboardingState): string {
  const { bridge } = state;
  if (bridge.connected) return `Connected${bridge.extension_version ? `, extension ${bridge.extension_version}` : ""}`;
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
        aria-label={done ? `Step ${n}, done` : `Step ${n}`}
      >
        {done ? <Check className="size-3.5" strokeWidth={2.5} aria-hidden="true" /> : n}
      </span>
      <div className="min-w-0 flex-1 pt-0.5">
        <p className={cn("text-[14px] font-medium", done || current ? "text-ink-primary" : "text-ink-muted")}>{title}</p>
        <p className="studio-meta mt-0.5 text-[11px] text-ink-muted">{status}</p>
        {children && <div className="mt-3">{children}</div>}
      </div>
    </li>
  );
}

function ProfileCard({
  identity,
  busy,
  onOpen,
  onForget,
}: {
  identity: CreatorIdentity;
  busy: string | null;
  onOpen: (url: string) => void;
  onForget: () => void;
}) {
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
        onClick={onForget}
        disabled={busy !== null}
        className="studio-meta self-start text-[10px] text-ink-muted transition-colors hover:text-signal-orange-text disabled:opacity-40"
      >
        NOT YOU, OR WANT IT GONE? DELETE EVERYTHING THE STUDIO HOLDS ABOUT YOU
      </button>
    </div>
  );
}

function ImportRow({
  label,
  count,
  last,
  pending,
  disabled,
  onImport,
}: {
  label: string;
  count: number;
  last: SelfImport | null;
  pending: boolean;
  disabled: boolean;
  onImport: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5">
      <div className="min-w-0">
        <p className="text-[13px] text-ink-primary">{label}</p>
        <p className="studio-meta mt-0.5 text-[10px] text-ink-muted">
          {count} STORED{last ? ` · ${importLine(last)}` : ""}
        </p>
      </div>
      <Secondary disabled={disabled} onPress={onImport}>
        {pending && <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />}
        {count > 0 ? "Import again" : "Import"}
      </Secondary>
    </div>
  );
}

function importLine(entry: SelfImport): string {
  if (!entry.finished_at) return entry.started_at ? "SCROLLING NOW" : "WAITING FOR THE PAGE TO OPEN";
  if (entry.outcome === "stopped") return `STOPPED AT ${entry.items_seen ?? 0}`;
  if (entry.outcome === "left_page") return `LEFT THE PAGE AT ${entry.items_seen ?? 0}`;
  if (entry.outcome === "superseded") return "REPLACED BY A NEWER IMPORT";
  return `LAST IMPORT READ ${entry.items_seen ?? 0}`;
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
