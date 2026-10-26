import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, CheckCheck, Copy, Download, ExternalLink, Loader2, PenLine } from "lucide-react";
import {
  dismissDemoCleanupNotice,
  fetchAnalyticsKpis,
  fetchCadenceInsights,
  fetchEvidenceBrief,
  fetchSmartSlots,
  fetchBackupSchedule,
  fetchToday,
  fetchWaitingCaptures,
  launchBridge,
  moveToNextSlot,
  publishNow,
  syncAllActivity,
  type AnalyticsKpis,
  type CadenceInsights,
  type EvidenceExemplar,
  type MetricComparison,
  type QueueSlot,
  type RetrievalEvidenceBrief,
  type ScheduledPost,
  type TodayBrief,
  type TodayDuePost,
  type TodayLatestPost,
  type TodayPerson,
  type WaitingCaptures,
} from "@/lib/api";
import { NOT_MEASURED, formatDays, gapOrNotMeasured } from "@/lib/cadence";
import { reportBridge } from "@/lib/bridgeState";
import { useRefresh } from "@/lib/refresh";
import { ratioTone } from "@/lib/results";
import { formatLocal, formatSlotTime } from "@/lib/time";
import { cn } from "@/lib/utils";

/**
 * Today: what to do in the next hour, as one command centre.
 *
 * The first screen once the studio knows who you are, and the only one a
 * creator opens every morning. It used to be a reading column 584 pixels wide
 * in a 1384 pixel work area, holding 1,874 characters at 16.1% ink, which
 * answered three of the six questions a creator has each day and sent them to
 * another screen for the rest (research: ONEVIEW.md sections 1 and 3).
 *
 * It is now three columns in the order the day is worked, with nothing below
 * the fold at 1440x900:
 *
 *   the people    one thing to fix, then who to reply to in their own words
 *   the work      your latest post against your own history, then what
 *                 worked and what did not, from the one results engine
 *   what goes out due and missed posts, next out, the week's shape, and the
 *                 way to the next post
 *
 * Under the grid, the last thirty days; under that, your rhythm. Every panel
 * reads its own endpoint and says so in its own corner when that read did not
 * come back, so one slow or broken answer never blanks the screen.
 *
 * Nothing here is ranked by the ICP score: who engaged with you twice this
 * week is a fact, a keyword guess about a job title is not. A comparison with
 * "your usual" appears only when it is fair, and the server's own sentence
 * saying why it is not appears when it is not. A figure the studio never
 * captured reads "Not measured", never 0.
 */

/** One read: what came back, or why nothing did. Never both. */
interface Read<T> {
  data: T | null;
  failed: boolean;
  /** True until the first answer, success or failure, has arrived. */
  loading: boolean;
}

const PENDING: Read<never> = { data: null, failed: false, loading: true };

/**
 * One panel's own read, kept apart from every other panel's.
 *
 * `load` is held in a ref so a caller may pass a fresh arrow each render
 * without the read running again. The read runs once on mount and again
 * under useRefresh with no interval: when the studio answers after an
 * outage, and when the window comes back after being away. The panels'
 * failure sentence promises that, and it was true only of Today's own read:
 * the six side panels were read once per mount, so one that failed stayed
 * failed until the creator left the screen.
 */
function useRead<T>(load: () => Promise<T>, onData?: (value: T) => void): [Read<T>, () => void] {
  const [state, setState] = useState<Read<T>>(PENDING);
  const latest = useRef({ load, onData });
  latest.current = { load, onData };
  const again = useCallback(() => {
    latest.current
      .load()
      .then((value) => {
        setState({ data: value, failed: false, loading: false });
        latest.current.onData?.(value);
      })
      .catch(() => setState({ data: null, failed: true, loading: false }));
  }, []);
  useEffect(again, [again]);
  useRefresh(again);
  return [state, again];
}

export function TodaySurface({
  onOpenLead,
  onOpenSetup,
  onOpenActivity,
  onOpenQueue,
  onOpenComposer,
}: {
  onOpenLead: (leadId: string) => void;
  onOpenSetup: () => void;
  onOpenActivity?: () => void;
  onOpenQueue?: () => void;
  onOpenComposer?: () => void;
}) {
  const [brief, setBrief] = useState<TodayBrief | null>(null);
  const [failed, setFailed] = useState(false);
  const [opening, setOpening] = useState<string | null>(null);
  // What happened after a click, shown in the panel that was clicked rather
  // than at the foot of the page, out of sight.
  const [note, setNote] = useState<{ text: string; at: "top" | "latest" | "due"; error: boolean } | null>(null);

  const load = useCallback(() => {
    fetchToday()
      .then((result) => {
        setBrief(result);
        reportBridge(result.freshness.bridge.connected);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, []);

  useEffect(load, [load]);
  // Captures arrive while this screen is open, from the other window. Read
  // again every 30 seconds while the window is in view (a hidden one is not
  // polled), on coming back to it, and when the studio is back after an outage.
  useRefresh(load, 30000);

  // The panels beside Today's own read. Each is its own endpoint, and none of
  // them is polled: evidence, cadence, the thirty day totals, the week's
  // slots and the two held signals all move on the scale of days, so
  // re-reading them every half minute would be work nobody asked for. Each
  // is read again when the studio is back after an outage and when the
  // window comes back (useRead), which is what their failure sentence says.
  const [evidence] = useRead(useCallback(() => fetchEvidenceBrief(), []));
  const [cadence] = useRead(useCallback(() => fetchCadenceInsights(), []));
  const [kpis] = useRead(useCallback(() => fetchAnalyticsKpis("30d"), []));
  const [slots] = useRead(useCallback(() => fetchSmartSlots(), []));
  const [waiting] = useRead(useCallback(() => fetchWaitingCaptures(), []));
  const [backups] = useRead(useCallback(() => fetchBackupSchedule(), []));

  async function open(url: string, at: "top" | "latest" = "top") {
    setOpening(url);
    setNote(null);
    try {
      setNote({ text: (await launchBridge("auto", url)).message, at, error: false });
    } catch (caught) {
      setNote({ text: caught instanceof Error ? caught.message : "The browser could not be opened.", at, error: true });
    } finally {
      setOpening(null);
    }
  }

  async function syncAll() {
    setOpening("sync-all");
    setNote(null);
    try {
      const res = await syncAllActivity();
      setNote({ text: res.message, at: "top", error: false });
      load();
    } catch (caught) {
      setNote({ text: caught instanceof Error ? caught.message : "The import could not be started.", at: "top", error: true });
    } finally {
      setOpening(null);
    }
  }

  // A due post is copied and posted by hand; the studio records it as
  // published only when the creator says it is, as the Queue does.
  async function copyDue(content: string) {
    setNote(null);
    try {
      await navigator.clipboard.writeText(content);
      setNote({ text: "Copied. Paste it into LinkedIn, post it, then press I posted it.", at: "due", error: false });
    } catch {
      setNote({ text: "This browser did not allow copying. Open the Queue to select the text.", at: "due", error: true });
    }
  }

  async function markPosted(postId: string) {
    setOpening(postId);
    setNote(null);
    try {
      await publishNow(postId);
      // Said at the top: with nothing left due, the due box goes.
      setNote({ text: "Marked as published.", at: due.length > 1 ? "due" : "top", error: false });
      load();
    } catch (caught) {
      setNote({
        text: caught instanceof Error ? caught.message : "The studio refused to mark it as published.",
        at: "due",
        error: true,
      });
    } finally {
      setOpening(null);
    }
  }

  // A post missed while the studio was closed or asleep: Post now copies its
  // text and records it as posted by the creator, the same as Publish's Copy
  // and mark posted. Nothing is recorded when the copy did not happen.
  async function postNow(post: TodayDuePost) {
    setOpening(post.post_id);
    setNote(null);
    try {
      try {
        await navigator.clipboard.writeText(post.content);
      } catch {
        setNote({
          text: "This browser did not allow copying, so nothing was recorded. Open the Queue to copy the text.",
          at: "due",
          error: true,
        });
        return;
      }
      await publishNow(post.post_id);
      setNote({
        text: "Copied and recorded as posted by you. Paste it into LinkedIn and post it there.",
        at: due.length > 1 ? "due" : "top",
        error: false,
      });
      load();
    } catch (caught) {
      setNote({
        text: `Copied, but not recorded: ${caught instanceof Error ? caught.message : "the studio refused."}`,
        at: "due",
        error: true,
      });
    } finally {
      setOpening(null);
    }
  }

  async function moveOn(postId: string) {
    setOpening(postId);
    setNote(null);
    try {
      const moved = await moveToNextSlot(postId);
      setNote({
        text: `Moved to ${formatLocal(moved.scheduled_for)}. It is queued again.`,
        at: due.length > 1 ? "due" : "top",
        error: false,
      });
      load();
    } catch (caught) {
      setNote({ text: caught instanceof Error ? caught.message : "The studio refused to move it.", at: "due", error: true });
    } finally {
      setOpening(null);
    }
  }

  if (failed && !brief) return <Centered>TODAY IS UNAVAILABLE. IS THE STUDIO RUNNING?</Centered>;
  if (!brief) return <Centered>LOADING TODAY</Centered>;
  // Absent from a studio older than this screen; nothing is due then.
  const due: TodayDuePost[] = brief.queue.due ?? [];
  const missedCount = due.filter((post) => post.missed).length;

  return (
    <div className="flex h-full min-h-0 w-full flex-col gap-2 p-3 lg:overflow-hidden">
      {/* One strip. The only h1 on the screen, who the studio thinks you are,
          and the state that is not about any one panel. */}
      <div className="flex shrink-0 flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
          <p className="studio-label">Today</p>
          <h1 className="text-[15px] leading-tight font-semibold tracking-tight text-ink-primary">
            What to do in the next hour
          </h1>
          {brief.identity.name && (
            <span className="min-w-0 truncate text-[12px] text-ink-secondary">{brief.identity.name}</span>
          )}
        </div>
        <p className="studio-meta text-[10px] leading-snug text-ink-muted">
          {freshnessLine(brief, waiting.data)}
        </p>
      </div>

      {brief.demo_cleanup && <DemoCleanupNotice notice={brief.demo_cleanup} onDismissed={load} />}

      {/* The backup schedule has stopped producing backups. Read from the
          Storage and privacy panel's own endpoint, which is the only place
          this was said, and only to someone who went looking for it. */}
      {backups.data?.stale && (
        <p role="status" className="studio-meta shrink-0 rounded-md border border-signal-orange px-3 py-1.5 leading-snug text-signal-orange-text">
          NO BACKUP FOR {Math.round(backups.data.age_hours ?? 0)} HOURS. THE DAILY BACKUP IS ON BUT HAS
          NOT RUN; THE NEWEST COPY YOU COULD RESTORE FROM IS THAT OLD. SEE STORAGE AND PRIVACY IN BRAND STUDIO.
        </p>
      )}

      {/* First, because it has a time on it. A queued post is not posted by
          the studio: at its time it waits here and on the Queue. */}
      {due.length > 0 && (
        <section className="shrink-0 rounded-md border border-signal-orange px-3 py-2">
          <p className="studio-meta text-[10px] text-signal-orange-text">
            {missedCount > 0
              ? missedCount === 1
                ? "A POST WAS MISSED"
                : `${missedCount} POSTS WERE MISSED`
              : due.length === 1
                ? "A POST IS DUE"
                : `${due.length} POSTS ARE DUE`}
          </p>
          <p className="mt-1 text-[13px] leading-snug text-ink-primary">
            {missedCount > 0 &&
              "A post was missed while the studio was closed or asleep. It kept its time; nothing moved it. Post now copies the text and records it as posted by you. Move to next slot queues it again. "}
            {due.length > missedCount &&
              "Its time has come. Copy the text, post it on LinkedIn yourself, then press I posted it."}
          </p>
          <ul className="mt-2 flex max-h-[9rem] flex-col divide-y divide-edge overflow-y-auto border-y border-edge">
            {due.map((post) => (
              <li key={post.post_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-1.5">
                <span className="studio-meta shrink-0 text-[10px] text-signal-orange-text">
                  {post.missed
                    ? `MISSED, WAS DUE ${formatLocal(post.scheduled_for).toUpperCase()}`
                    : `DUE ${formatLocal(post.scheduled_for).toUpperCase()}`}
                </span>
                <span className="min-w-0 flex-1 truncate text-[13px] text-ink-secondary">{post.excerpt}</span>
                {post.missed ? (
                  <span className="flex shrink-0 items-center gap-2">
                    <button
                      type="button"
                      disabled={opening !== null}
                      onClick={() => void moveOn(post.post_id)}
                      className="rounded-md border border-edge px-2.5 py-0.5 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
                    >
                      Move to next slot
                    </button>
                    <button
                      type="button"
                      disabled={opening !== null}
                      onClick={() => void postNow(post)}
                      className="flex items-center gap-1.5 rounded-md bg-signal-orange px-2.5 py-0.5 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-40"
                    >
                      {opening === post.post_id ? (
                        <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                      ) : (
                        <Copy className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                      )}
                      Post now
                    </button>
                  </span>
                ) : (
                  <span className="flex shrink-0 items-center gap-2">
                    <button
                      type="button"
                      onClick={() => void copyDue(post.content)}
                      className="flex items-center gap-1.5 rounded-md border border-edge px-2.5 py-0.5 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary"
                    >
                      <Copy className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                      Copy text
                    </button>
                    <button
                      type="button"
                      disabled={opening !== null}
                      onClick={() => void markPosted(post.post_id)}
                      className="flex items-center gap-1.5 rounded-md bg-signal-orange px-2.5 py-0.5 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-40"
                    >
                      {opening === post.post_id ? (
                        <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                      ) : (
                        <CheckCheck className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                      )}
                      I posted it
                    </button>
                  </span>
                )}
              </li>
            ))}
          </ul>
          {onOpenQueue && (
            <button
              type="button"
              onClick={onOpenQueue}
              className="mt-2 text-[12px] text-ink-secondary underline underline-offset-2 hover:text-ink-primary"
            >
              Not posting it? Move it back to drafts from the Queue
            </button>
          )}
          {note?.at === "due" && <Note text={note.text} error={note.error} />}
        </section>
      )}

      {/* Three columns at 1440 and 1280, two at 1024, one below that, always
          in the order the day is worked. */}
      <div className="grid gap-2 max-lg:shrink-0 lg:min-h-0 lg:flex-1 lg:grid-cols-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)_minmax(0,0.95fr)]">
        <div className="flex min-h-0 min-w-0 flex-col gap-2 max-lg:min-h-[22rem]">
          <section className="shrink-0 rounded-md border border-edge-strong px-3 py-2">
            <p className="studio-meta text-[10px] text-ink-muted">ONE THING TO OPEN</p>
            <p className="mt-1 text-[13px] leading-snug text-ink-primary">{brief.open_next.reason}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {brief.open_next.action === "open" && brief.open_next.url ? (
                <button
                  type="button"
                  disabled={opening !== null}
                  onClick={() => void open(brief.open_next.url as string)}
                  className="flex items-center gap-1.5 rounded-md bg-signal-orange px-2.5 py-1 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-40"
                >
                  {opening === brief.open_next.url ? (
                    <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                  ) : (
                    <ExternalLink className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                  )}
                  Open it in the bridge browser
                </button>
              ) : (
                <button
                  type="button"
                  onClick={onOpenSetup}
                  className="rounded-md bg-signal-orange px-2.5 py-1 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110"
                >
                  Go to Setup
                </button>
              )}
              <button
                type="button"
                disabled={opening !== null}
                onClick={() => void syncAll()}
                className="flex items-center gap-1.5 rounded-md border border-edge bg-soft px-2.5 py-1 text-[12px] font-medium text-ink-primary transition-[filter] hover:brightness-110 disabled:opacity-40"
              >
                {opening === "sync-all" ? (
                  <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                ) : (
                  <Download className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                )}
                {/* One name for the one action, as on Setup and Activity. It
                    was "Sync Activity via Bridge" here, "Import all three" on
                    Setup and "Sync All Activity" on Activity, with a tick that
                    read as done on a button that starts work. */}
                Import your history
              </button>
              {onOpenActivity && (
                <button
                  type="button"
                  onClick={onOpenActivity}
                  className="flex items-center gap-1.5 rounded-md border border-edge bg-soft px-2.5 py-1 text-[12px] font-medium text-ink-primary transition-[filter] hover:brightness-110"
                >
                  <Activity className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                  Open Activity
                </button>
              )}
            </div>
            {note?.at === "top" && <Note text={note.text} error={note.error} />}
          </section>

          <Panel
            title="Reply to"
            note={brief.identity.known ? `${brief.reply_to.length}` : undefined}
            grow
          >
            {!brief.identity.known ? (
              <Empty>Once you confirm your profile, people who engaged with your posts appear here.</Empty>
            ) : brief.reply_to.length === 0 ? (
              <Empty>Nobody from the last two weeks is waiting on a reply.</Empty>
            ) : (
              <ul className="flex flex-col divide-y divide-edge">
                {brief.reply_to.map((person) => (
                  <Person key={person.lead_id} person={person} onOpen={() => onOpenLead(person.lead_id)} />
                ))}
              </ul>
            )}
          </Panel>
        </div>

        <div className="flex min-h-0 min-w-0 flex-col gap-2 max-lg:min-h-[26rem]">
          <Panel
            title="Your latest post"
            note={
              brief.latest_post
                ? brief.latest_post.age_hours < 48
                  ? `${Math.round(brief.latest_post.age_hours)}H OLD`
                  : `${Math.round(brief.latest_post.age_hours / 24)}D OLD`
                : undefined
            }
          >
            {brief.marked_published && (
              <p className="mb-2 text-[13px] leading-snug text-ink-secondary">
                You marked {brief.marked_published.excerpt ? `“${brief.marked_published.excerpt}”` : "a post"} as
                published {formatLocal(brief.marked_published.published_at)}. It appears here, with its figures,
                once the bridge sees it on LinkedIn.
                {brief.latest_post ? " Until then, this is the latest one it has read:" : ""}
              </p>
            )}
            {brief.latest_post ? (
              <LatestPost post={brief.latest_post} opening={opening} onOpen={(url) => void open(url, "latest")} />
            ) : (
              <Empty>
                {brief.identity.known
                  ? "No post of yours has been imported yet. Import your posts in Setup."
                  : "Your posts appear here once the studio knows who you are."}
              </Empty>
            )}
            {note?.at === "latest" && <Note text={note.text} error={note.error} />}
          </Panel>

          <WhatWorked read={evidence} grow />
        </div>

        <div className="flex min-h-0 min-w-0 flex-col gap-2 max-xl:lg:col-span-2 max-lg:min-h-[18rem]">
          <NextOut
            brief={brief}
            slots={slots}
            cadence={cadence}
            onOpenQueue={onOpenQueue}
            onOpenComposer={onOpenComposer}
            grow
          />
        </div>
      </div>

      {/* Context rather than a decision, so one strip under the three columns
          instead of a column's worth of the eye. */}
      <ThirtyDays read={kpis} />
      <Rhythm read={cadence} />
    </div>
  );
}

/* -------------------------------------------------------------------------
 * The furniture. None of it carries a colour of its own: every one is a
 * token utility, so both themes come free.
 * ---------------------------------------------------------------------- */

/** A titled region. `note` sits at its right, for a count or a state. */
function Panel({
  title,
  note,
  children,
  grow,
  readable,
}: {
  title: string;
  note?: React.ReactNode;
  children: React.ReactNode;
  /** Takes the leftover height of its column, so a dense view has no gutter at the foot. */
  grow?: boolean;
  /**
   * For a panel whose body is prose rather than controls. Its own scrolling
   * area is then reachable by Tab and named, because a region that scrolls
   * and holds nothing focusable cannot be read by keyboard at all
   * (axe: scrollable-region-focusable).
   */
  readable?: boolean;
}) {
  return (
    <section className={cn("flex min-h-0 min-w-0 flex-col rounded-md border border-edge", grow && "lg:flex-1")}>
      <div className="flex shrink-0 items-baseline justify-between gap-3 border-b border-edge px-3 py-1.5">
        <p className="studio-label">{title}</p>
        {note ? <span className="studio-meta shrink-0 text-[10px] text-ink-muted">{note}</span> : null}
      </div>
      <div
        className="min-h-0 flex-1 overflow-y-auto px-3 py-2"
        tabIndex={readable ? 0 : undefined}
        role={readable ? "group" : undefined}
        aria-label={readable ? title : undefined}
      >
        {children}
      </div>
    </section>
  );
}

/**
 * One figure.
 *
 * A value the studio never captured prints "Not measured" in the muted step,
 * at the size of a label rather than the size of a number, so it cannot be
 * read as a zero at a glance.
 */
/** The ~ that marks a rounded figure, with the word a screen reader hears instead. */
function About() {
  return (
    <>
      <span aria-hidden="true">~</span>
      <span className="sr-only">about </span>
    </>
  );
}

function Figure({
  label,
  value,
  note,
  approximate = false,
  noteApproximate = false,
}: {
  label: string;
  value: string;
  note?: string | null;
  /** The figure was built from one LinkedIn rounded, such as 1.2K. */
  approximate?: boolean;
  /** The change under it was. */
  noteApproximate?: boolean;
}) {
  const unknown = value === NOT_MEASURED;
  return (
    <div className="min-w-0">
      <p className="studio-label truncate">{label}</p>
      <p
        className={cn(
          "truncate tabular-nums",
          unknown ? "studio-meta mt-1 text-ink-muted" : "mt-0.5 text-[19px] leading-tight font-semibold text-ink-primary",
        )}
      >
        {approximate && !unknown && <About />}
        {value}
      </p>
      {note ? (
        <p className="studio-meta mt-0.5 truncate text-[10px] text-ink-muted">
          {noteApproximate && note !== NOT_MEASURED && <About />}
          {note}
        </p>
      ) : null}
    </div>
  );
}

/** A count as the screen prints it. Null is not zero; a captured zero is "0". */
function count(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return NOT_MEASURED;
  return value.toLocaleString();
}

/** Whether `count` would have had to say "Not measured". */
function measured(value: number | null | undefined): boolean {
  return !(value === null || value === undefined || Number.isNaN(value));
}

/** A signed percentage, for the thirty day deltas. */
function deltaOf(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return NOT_MEASURED;
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

/** The first line of a post, trimmed to `max` characters. */
function firstLine(text: string | null | undefined, max = 90): string {
  const line = (text ?? "").trim().split("\n")[0] ?? "";
  return line.length > max ? `${line.slice(0, max - 1)}...` : line;
}

/** What a panel says when its one read did not come back, or came back empty. */
function ReadState({ read, empty }: { read: Read<unknown>; empty?: string }) {
  if (read.loading) return <p className="studio-meta text-ink-muted">READING</p>;
  if (read.failed) {
    return (
      <p className="studio-meta leading-relaxed text-signal-orange-text">
        The studio did not answer. It is read again when this window comes back.
      </p>
    );
  }
  if (empty) return <Empty>{empty}</Empty>;
  return null;
}

/* -------------------------------------------------------------------------
 * The panels beside Today's own read.
 * ---------------------------------------------------------------------- */

/**
 * What worked and what did not, from the one results engine.
 *
 * /api/v1/insights/evidence answers "which of my posts worked" in 10 KB,
 * against 2,201 KB for insights/posts and 2,432 KB for analytics/posts,
 * neither of which a screen meant to paint at a glance can pay. Settled posts
 * only, and the weak end is shown beside the strong one, because showing one
 * without the other turns a comparison into a trophy cabinet.
 */
function WhatWorked({ read, grow }: { read: Read<RetrievalEvidenceBrief>; grow?: boolean }) {
  const brief = read.data;
  const top: EvidenceExemplar[] = brief?.top_exemplars ?? [];
  const bottom: EvidenceExemplar[] = brief?.bottom_exemplars ?? [];

  const row = (item: EvidenceExemplar, index: number) => (
    <li key={item.activity_urn ?? index} className="py-1">
      <p className="truncate text-[13px] text-ink-primary">{firstLine(item.text, 110)}</p>
      <p className="studio-meta mt-0.5 text-[10px] text-ink-muted">
        {count(item.reactions)} reactions
        {measured(item.comments) ? ` · ${count(item.comments)} comments` : ""}
        {` · ${count(item.qualified_leads)} qualified leads`}
      </p>
    </li>
  );

  return (
    <Panel title="What worked" note={brief?.has_evidence ? "SETTLED POSTS ONLY" : undefined} grow={grow} readable>
      {top.length === 0 ? (
        <ReadState
          read={read}
          empty={brief?.message ?? "Not enough settled posts yet to say which of yours worked."}
        />
      ) : (
        <>
          <p className="studio-label">Your strongest</p>
          <ul className="flex flex-col divide-y divide-edge">{top.map(row)}</ul>
          {bottom.length > 0 && (
            <>
              <p className="studio-label mt-2 border-t border-edge pt-2">And your weakest</p>
              <ul className="flex flex-col divide-y divide-edge">{bottom.map(row)}</ul>
            </>
          )}
        </>
      )}
    </Panel>
  );
}

const WEEK_INITIALS = ["M", "T", "W", "T", "F", "S", "S"];

/** What goes out next, and the week it goes out into. */
function NextOut({
  brief,
  slots,
  cadence,
  onOpenQueue,
  onOpenComposer,
  grow,
}: {
  brief: TodayBrief;
  slots: Read<{ slots: QueueSlot[]; scheduled: ScheduledPost[] }>;
  cadence: Read<CadenceInsights>;
  onOpenQueue?: () => void;
  onOpenComposer?: () => void;
  grow?: boolean;
}) {
  const active = (slots.data?.slots ?? []).filter((slot) => slot.is_active);
  const queued = slots.data?.scheduled ?? [];
  const queue = cadence.data?.queue;
  return (
    <Panel
      title="Next out"
      note={slots.data ? `${active.length} WEEKLY SLOTS` : undefined}
      grow={grow}
    >
      <dl className="flex flex-col gap-1.5">
        <Row
          label="Next to go out"
          value={
            brief.queue.next_scheduled
              ? `${formatLocal(brief.queue.next_scheduled.scheduled_for)}: ${brief.queue.next_scheduled.excerpt}`
              : "Nothing scheduled"
          }
        />
        <Row
          label="Next open slot"
          value={
            brief.queue.next_open_slot
              ? `${brief.queue.next_open_slot.day_name} ${formatSlotTime(brief.queue.next_open_slot.time_slot)}${
                  brief.queue.next_open_slot.label ? `, ${brief.queue.next_open_slot.label}` : ""
                }`
              : "No slot found"
          }
        />
        <Row
          label="Queued, next 14 days"
          value={
            queue
              ? `${queue.scheduled_next_14_days} of ${queue.weekly_slots * 2} slots`
              : cadence.failed
                ? "Not read"
                : NOT_MEASURED
          }
        />
      </dl>

      {/* What follows the next one. The same read that carries the week's
          slots carries the queued posts, so this costs nothing and answers
          "what goes out next" as the plural it actually is. */}
      {queued.length > 1 && (
        <div className="mt-2 border-t border-edge pt-2">
          <p className="studio-label">Then</p>
          <ul className="mt-1 flex flex-col divide-y divide-edge">
            {queued.slice(1, 5).map((post) => (
              <li key={post.id} className="flex items-baseline gap-2 py-1">
                <span className="studio-meta shrink-0 text-[10px] text-ink-muted">
                  {formatLocal(post.scheduled_for)}
                </span>
                <span className="min-w-0 flex-1 truncate text-[12px] text-ink-secondary">
                  {firstLine(post.content, 60)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* The weekly shape, not the times. Seven cells showing how many slots
          each day holds reads at a glance; seven columns of "08:30 AM" does
          not at this width, and the exact next time is the line above. */}
      {active.length > 0 && (
        <ul className="studio-meta mt-2 grid grid-cols-7 gap-1 border-t border-edge pt-2 text-center text-[10px]">
          {WEEK_INITIALS.map((initial, index) => {
            const howMany = active.filter((slot) => slot.day_of_week === index).length;
            return (
              <li key={`${initial}${index}`} className="min-w-0 rounded-sm bg-soft py-0.5">
                <span className="block text-ink-muted">{initial}</span>
                <span className={cn("block tabular-nums", howMany ? "text-ink-primary" : "text-ink-muted")}>
                  {howMany}
                </span>
              </li>
            );
          })}
        </ul>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-edge pt-2">
        {onOpenComposer && (
          <button
            type="button"
            onClick={onOpenComposer}
            className="flex items-center gap-1.5 rounded-md bg-signal-orange px-2.5 py-1 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110"
          >
            <PenLine className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
            Write the next post
          </button>
        )}
        {onOpenQueue && (
          <button
            type="button"
            onClick={onOpenQueue}
            className="rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary"
          >
            Open the Queue
          </button>
        )}
      </div>
    </Panel>
  );
}

/** The last thirty days, as one strip of four figures with their deltas. */
function ThirtyDays({ read }: { read: Read<AnalyticsKpis> }) {
  const kpis = read.data;
  // Which figures and changes LinkedIn had rounded (1.2K is anything from
  // 1,150 to 1,249). Analytics marks them with a ~ and this strip drew the
  // same figures unmarked.
  const approx = new Set(kpis?.approximate ?? []);
  return (
    <section className="shrink-0 rounded-md border border-edge px-3 py-2">
      <div className="flex items-baseline justify-between gap-3">
        <p className="studio-label">Last 30 days</p>
        {kpis && measured(kpis.days_counted) && (
          <span className="studio-meta shrink-0 text-[10px] text-ink-muted">
            {kpis.days_counted} DAYS CAPTURED
          </span>
        )}
      </div>
      {!kpis ? (
        <div className="mt-1">
          <ReadState read={read} empty="Nothing has been captured for the last 30 days." />
        </div>
      ) : (
        // No profile views: no reader on a real install writes one, so the
        // figure was a permanent "not measured" (cycle 4, decision 8).
        <div className="mt-1 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
          <Figure
            label="Impressions"
            value={count(kpis.impressions)}
            note={deltaOf(kpis.impressions_delta_pct)}
            approximate={approx.has("impressions")}
            noteApproximate={approx.has("impressions_delta_pct")}
          />
          <Figure
            label="Engagements"
            value={count(kpis.total_engagements)}
            note={deltaOf(kpis.engagements_delta_pct)}
            approximate={approx.has("total_engagements")}
            noteApproximate={approx.has("engagements_delta_pct")}
          />
          <Figure
            label="Followers"
            value={count(kpis.total_followers)}
            note={
              measured(kpis.follower_growth)
                ? `${kpis.follower_growth! > 0 ? "+" : ""}${kpis.follower_growth}`
                : NOT_MEASURED
            }
            approximate={approx.has("total_followers")}
            noteApproximate={approx.has("follower_growth")}
          />
        </div>
      )}
      {approx.size > 0 && (
        <p className="studio-meta mt-1 text-[10px] leading-snug text-ink-muted">
          ~ MARKS A FIGURE OR CHANGE BUILT FROM ONE LINKEDIN ROUNDED, SUCH AS 1.2K, SO IT IS APPROXIMATE.
        </p>
      )}
    </section>
  );
}

/** The footer line: how steadily you post, measured from your own posts. */
function Rhythm({ read }: { read: Read<CadenceInsights> }) {
  const cadence = read.data;
  return (
    <footer className="flex shrink-0 flex-wrap items-baseline gap-x-5 gap-y-1 rounded-md border border-edge px-3 py-1.5">
      <p className="studio-label shrink-0">Rhythm</p>
      {cadence ? (
        <>
          <span className="studio-meta text-[10px] text-ink-secondary">{count(cadence.posts)} POSTS READ</span>
          <span className="studio-meta text-[10px] text-ink-secondary">
            {formatDays(cadence.days_since_last)
              ? `${formatDays(cadence.days_since_last)!.toUpperCase()} SINCE YOUR LAST`
              : `SINCE YOUR LAST: ${NOT_MEASURED.toUpperCase()}`}
          </span>
          <span className="studio-meta text-[10px] text-ink-secondary">
            {`USUAL GAP ${gapOrNotMeasured(cadence.median_gap_days).toUpperCase()}`}
          </span>
          {cadence.longest_gap && (
            <span className="studio-meta text-[10px] text-ink-muted">
              LONGEST GAP {gapOrNotMeasured(cadence.longest_gap.days).toUpperCase()}
            </span>
          )}
        </>
      ) : (
        <ReadState read={read} empty="No posting rhythm measured yet." />
      )}
    </footer>
  );
}

const REMOVED_NAMES: Record<string, [string, string]> = {
  drafts: ["draft", "drafts"],
  posts: ["post", "posts"],
  leads: ["lead", "leads"],
  analytics_days: ["day of analytics", "days of analytics"],
  audience_rows: ["audience row", "audience rows"],
};

/**
 * Said once, after the studio removed sample content an earlier version had
 * seeded into every install. Rows a creator could see went, so the screen
 * says what and where the copy from before is, until they dismiss it.
 */
function DemoCleanupNotice({
  notice,
  onDismissed,
}: {
  notice: NonNullable<TodayBrief["demo_cleanup"]>;
  onDismissed: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [hidden, setHidden] = useState(false);
  if (hidden) return null;
  const counts = notice.removed
    .map(({ kind, count: howMany }) => {
      const [one, many] = REMOVED_NAMES[kind] ?? [kind.replace(/_/g, " "), kind.replace(/_/g, " ")];
      return `${howMany} ${howMany === 1 ? one : many}`;
    })
    .join(", ");

  async function dismiss() {
    setError(null);
    try {
      await dismissDemoCleanupNotice();
      setHidden(true);
      onDismissed();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The studio did not record that. Try again.");
    }
  }

  return (
    <div role="status" className="shrink-0 rounded-md border border-edge-strong bg-soft px-3 py-2">
      <p className="text-[13px] leading-relaxed break-words text-ink-secondary">
        The studio removed sample content it had added itself: {counts}.
        {notice.backup ? ` A copy of your database from before is at ${notice.backup}.` : ""}
      </p>
      <button
        type="button"
        onClick={() => void dismiss()}
        className="mt-2 rounded-md border border-edge bg-canvas px-2.5 py-0.5 text-[12px] text-ink-secondary transition-colors hover:text-ink-primary"
      >
        Dismiss
      </button>
      {error && <p role="alert" className="studio-meta mt-2 text-signal-orange-text">{error}</p>}
    </div>
  );
}

function Person({ person, onOpen }: { person: TodayPerson; onOpen: () => void }) {
  return (
    <li>
      <button type="button" onClick={onOpen} className="w-full py-2 text-left transition-colors hover:bg-soft/60">
        <div className="flex items-baseline justify-between gap-3">
          <p className="truncate text-[13px] font-medium text-ink-primary">{person.name}</p>
          <p className="studio-meta shrink-0 text-[10px] text-ink-muted">
            {person.posts_engaged > 1 ? `${person.posts_engaged} OF YOUR POSTS` : person.commented ? "COMMENTED" : "REACTED"}
            {person.engaged_at ? ` · ${ago(person.engaged_at)}` : ""}
          </p>
        </div>
        {person.headline && <p className="mt-0.5 truncate text-[11px] text-ink-muted">{person.headline}</p>}
        {/* Their own words, at the size of prose rather than of a label,
            because this is the text a creator reads rather than scans. */}
        {person.latest_comment && (
          <p className="mt-1 line-clamp-2 text-[13px] leading-snug text-ink-secondary">
            &ldquo;{person.latest_comment}&rdquo;
          </p>
        )}
      </button>
    </li>
  );
}

const METRIC_LABELS: Record<string, string> = {
  impressions: "Impressions",
  reactions: "Reactions",
  comments: "Comments",
};

function LatestPost({
  post,
  opening,
  onOpen,
}: {
  post: TodayLatestPost;
  opening: string | null;
  onOpen: (url: string) => void;
}) {
  const rows = Object.entries(post.comparison ?? {}) as [string, MetricComparison][];
  return (
    <div>
      {post.excerpt && <p className="line-clamp-2 text-[13px] leading-snug text-ink-secondary">{post.excerpt}</p>}

      {/* How it is doing now, from the one results engine every screen reads. */}
      <div className="mt-2 grid grid-cols-3 gap-3">
        <Figure label="Impressions" value={count(post.current?.impressions)} />
        <Figure label="Reactions" value={count(post.current?.reactions)} />
        <Figure label="Comments" value={count(post.current?.comments)} />
      </div>
      {post.current?.source && (
        <p className="studio-meta mt-1 text-[10px] text-ink-muted">
          READ FROM {post.current.source.replace(/_/g, " ").toUpperCase()}
          {post.current.read_at ? ` · ${ago(post.current.read_at)}` : ""}
        </p>
      )}
      {/* Whether it is still moving, in readings and with their count, and what is usual at this age, from results.movement. */}
      {post.movement?.sentence && <p className="mt-1 text-[12px] leading-snug text-ink-secondary first-letter:uppercase">{post.movement.sentence}.{post.movement.usual?.sentence ? ` Beside it: ${post.movement.usual.sentence}.` : ""}</p>}

      {rows.length > 0 ? (
        <div className="mt-2 border-t border-edge pt-2">
          <p className="studio-meta mb-1 text-[10px] text-ink-muted">AT ABOUT TWO DAYS OLD, AGAINST YOUR USUAL</p>
          {/* Two screens, two medians: this one is the median of the earlier
              posts read at the same age, Posts' is the settled-post median,
              and neither said so, though both are called "your usual". */}
          <p className="studio-meta mb-1 text-[10px] leading-snug text-ink-muted">
            YOUR USUAL HERE IS THE MEDIAN OF YOUR EARLIER POSTS READ AT THE SAME AGE. POSTS COMPARES SETTLED POSTS,
            SO ITS USUAL IS A DIFFERENT FIGURE.
          </p>
          <dl className="flex flex-col gap-1">
            {rows.map(([metric, value]) => (
              <div key={metric} className="flex items-baseline justify-between gap-3">
                <dt className="text-[12px] text-ink-secondary">{METRIC_LABELS[metric] ?? metric}</dt>
                <dd className="studio-meta text-right text-[11px] tabular-nums">
                  <span className={ratioTone(value.ratio, "text-ink-secondary")}>
                    {value.this_post.toLocaleString()} vs {Math.round(value.your_usual).toLocaleString()}
                    {value.ratio !== null ? ` (${value.ratio.toFixed(1)}x)` : ""}
                  </span>
                  <span className="ml-2 text-ink-muted">median of {value.posts_compared}</span>
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ) : (
        post.not_compared_because && (
          <p className="mt-2 border-t border-edge pt-2 text-[12px] leading-snug text-ink-muted">
            Not compared: {post.not_compared_because}.
          </p>
        )
      )}

      <div className="mt-2 flex flex-wrap gap-2">
        {/* A post published from the studio has no LinkedIn address until
            LinkedIn shows it, so there is nothing to open yet. */}
        {[
          { url: post.url, label: "Open the post" },
          { url: post.analytics_url, label: "Open its analytics" },
        ]
          .filter((link): link is { url: string; label: string } => Boolean(link.url))
          .map((link) => (
            <button
              key={link.url}
              type="button"
              disabled={opening !== null}
              onClick={() => onOpen(link.url)}
              className="flex items-center gap-1.5 rounded-md border border-edge px-2.5 py-0.5 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
            >
              {opening === link.url ? (
                <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
              ) : (
                <ExternalLink className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
              )}
              {link.label}
            </button>
          ))}
      </div>
    </div>
  );
}

/**
 * The capture state, as one line.
 *
 * Captures the extension is holding because the studio was busy were
 * readable only by calling /api/v1/extension/captures/waiting; nothing in
 * the interface said so, so a creator had no way to learn that work was
 * waiting. `measured` is false until the extension has reported, and then
 * the line says nothing about it rather than printing a zero.
 */
function freshnessLine(brief: TodayBrief, waiting: WaitingCaptures | null): string {
  const { bridge, drifting, last_capture_at, posts_held: held = 0 } = brief.freshness;
  const parts = [
    bridge.connected ? "BRIDGE CONNECTED" : bridge.last_seen_at ? `BRIDGE LAST SEEN ${ago(bridge.last_seen_at)}` : "BRIDGE NOT SEEN YET",
    last_capture_at
      ? `LAST CAPTURE ${ago(last_capture_at)}`
      : held
        ? `${held.toLocaleString()} ${held === 1 ? "POST" : "POSTS"} OF YOURS HELD`
        : "NOTHING CAPTURED YET",
  ];
  if (drifting.length) parts.push(`${drifting.length} PART${drifting.length > 1 ? "S" : ""} OF THE CAPTURE NOT WORKING`);
  if (waiting?.measured && waiting.waiting) {
    parts.push(
      `${waiting.waiting.toLocaleString()} ${waiting.waiting === 1 ? "CAPTURE" : "CAPTURES"} WAITING FOR THE STUDIO`,
    );
  }
  return parts.join(" · ");
}

function ago(iso: string): string {
  const then = new Date(iso.includes("T") || iso.endsWith("Z") ? iso : `${iso.replace(" ", "T")}Z`).getTime();
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 90) return "JUST NOW";
  if (seconds < 5400) return `${Math.round(seconds / 60)} MIN AGO`;
  if (seconds < 172800) return `${Math.round(seconds / 3600)} H AGO`;
  return `${Math.round(seconds / 86400)} DAYS AGO`;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="shrink-0 text-[12px] text-ink-muted">{label}</dt>
      <dd className="truncate text-right text-[13px] text-ink-secondary">{value}</dd>
    </div>
  );
}

// A sentence, so it is set as one. Ten pixel uppercase monospace is for
// labels and counts; a whole sentence in it was the hardest text on the page
// to read, and it is the text a new user meets first.
function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-[13px] leading-relaxed text-ink-muted">{children}</p>;
}

function Note({ text, error }: { text: string; error: boolean }) {
  const ref = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    ref.current?.scrollIntoView({ block: "nearest" });
    if (error) ref.current?.focus();
  }, [text, error]);
  return (
    <p
      ref={ref}
      tabIndex={-1}
      role={error ? "alert" : "status"}
      className={cn("studio-meta mt-2 leading-snug outline-none", error ? "text-signal-orange-text" : "text-ink-secondary")}
    >
      {text}
    </p>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid h-full place-items-center px-8">
      <p className="studio-meta max-w-[40ch] text-center leading-relaxed text-ink-muted">{children}</p>
    </div>
  );
}
