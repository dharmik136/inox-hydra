import { useCallback, useEffect, useState } from "react";
import { CheckCheck, Copy, Pause, Play, Plus, Trash2, Undo2, Zap } from "lucide-react";
import {
  addQueueSlot,
  deleteQueueSlot,
  dispatchQueueNow,
  fetchCadenceHealth,
  fetchCadenceInsights,
  fetchDuePosts,
  fetchNextSlot,
  fetchRecentDrafts,
  fetchSmartSlots,
  publishNow,
  returnToDrafts,
  schedulePost,
  toggleQueuePause,
  type CadenceHealth,
  type CadenceInsights,
  type DraftSummary,
  type QueueSlot,
  type ScheduledPost,
  type TodayDuePost,
  updateQueueSlot,
} from "@/lib/api";
import { NOT_MEASURED, formatDays, gapOrNotMeasured } from "@/lib/cadence";
import { useRefresh } from "@/lib/refresh";
import { formatLocal, formatSlotTime } from "@/lib/time";
import { cn } from "@/lib/utils";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/**
 * How many of the waiting drafts the Queue lists.
 *
 * Enough that a creator can see what is there and put one in a slot, few
 * enough that this stays the Queue rather than a second drafts screen: an
 * install with 150 drafts should not render 150 rows here.
 */
const DRAFTS_SHOWN = 8;
const DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

/** Today at midnight local time, which is where the next seven days start. */
function startOfToday(now: Date): Date {
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

/**
 * Which of the next seven days a stored time falls on, or null for a time
 * outside them.
 *
 * The grid used to draw the calendar Monday to Sunday week containing today,
 * which meant that on any day but Monday some of its cells were already
 * past, and a post queued for next Tuesday landed in no cell at all while
 * the cell headed TUE read EMPTY above the list naming that post's Tuesday.
 * Seven days from today is the window the question is actually about: when
 * does the next post go out.
 *
 * Parsed the way lib/time.ts parses it, so a post sits on the day the rest
 * of the screen prints beside it. Reading the stored string as UTC instead
 * put a Saturday 10:57 PM post in the Sunday cell on a clock five and a half
 * hours ahead, while the row below it said Saturday.
 */
function dayInWindow(iso: string | null, windowStart: Date): number | null {
  if (!iso) return null;
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return null;
  // Midnight to midnight, rounded, so the hour a clock change adds or takes
  // from a day does not move a post into the day beside it.
  const day = new Date(when.getFullYear(), when.getMonth(), when.getDate());
  const days = Math.round((day.getTime() - windowStart.getTime()) / 86_400_000);
  return days >= 0 && days < 7 ? days : null;
}

/**
 * The smart queue: the week at a glance.
 *
 * The queue posts nothing. At a post's time it marks the post due, and the
 * post waits at the top of this screen for the creator to post it on LinkedIn
 * and say so. The screen used to call this publishing: "Pause publishing",
 * "Run due posts", "scheduled posts will not go out", while at the slot the
 * post was silently recorded as published and counted in Analytics although
 * nothing had been posted. Pausing stops posts being marked due, and its state
 * is read back from the server rather than assumed from the click.
 *
 * It also used to hold 770 characters and three controls on a three year
 * install, in a column using 57% of the width it was given, and it did not
 * say that a post had been missed or why (research: ONEVIEW.md section 1).
 * It now opens on the week itself, with each day's slots and what sits in
 * them, the missed note the scheduler left, and the creator's own measured
 * rhythm beside the cadence of what is queued.
 */
export function QueueSurface({ onEditText }: { onEditText?: (postId: string) => void } = {}) {
  const [slots, setSlots] = useState<QueueSlot[] | null>(null);
  const [scheduled, setScheduled] = useState<ScheduledPost[]>([]);
  const [due, setDue] = useState<TodayDuePost[]>([]);
  const [dueNote, setDueNote] = useState<string | null>(null);
  const [health, setHealth] = useState<CadenceHealth | null>(null);
  const [rhythm, setRhythm] = useState<CadenceInsights | null>(null);
  const [drafts, setDrafts] = useState<DraftSummary[]>([]);
  const [draftNote, setDraftNote] = useState<string | null>(null);
  const [queueing, setQueueing] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dispatchNote, setDispatchNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [queue, cadence, duePosts, waiting] = await Promise.all([
        fetchSmartSlots(),
        fetchCadenceHealth(),
        fetchDuePosts(),
        // The drafts that could go in a slot. Bounded, because every draft
        // is 259 KB on a three year install and this is a list of the few
        // waiting, not the drafts screen.
        fetchRecentDrafts(DRAFTS_SHOWN).catch(() => [] as DraftSummary[]),
      ]);
      setSlots(queue.slots);
      setScheduled(queue.scheduled);
      setDue(duePosts);
      setHealth(cadence);
      setDrafts(waiting);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  // How steadily the creator actually posts, from their own history. Read
  // once: it moves on the scale of days, not of a queue dispatch.
  useEffect(() => {
    let live = true;
    fetchCadenceInsights()
      .then((result) => live && setRhythm(result))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    void load();
  }, [load]);
  // "When a queued post's time comes, it moves to Due below": only if the
  // screen reads again, which it did not while open. Every 30 seconds while
  // in view, on coming back to the window, and after an outage.
  useRefresh(load, 30000);

  async function onTogglePause() {
    if (!health) return;
    setBusy(true);
    try {
      // The returned value is the state the server read back after writing,
      // not the state that was requested.
      const now = await toggleQueuePause(!health.queue_paused);
      setHealth({ ...health, queue_paused: now });
    } catch {
      // The queue is left showing whatever it last actually was.
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function onDispatch() {
    setBusy(true);
    setDispatchNote(null);
    try {
      const actions = await dispatchQueueNow();
      setDispatchNote(
        actions.length
          ? `${actions.length} post${actions.length === 1 ? "" : "s"} marked due`
          : "Nothing was due",
      );
      await load();
    } catch (error) {
      setDispatchNote(error instanceof Error ? error.message : "The check was refused");
    } finally {
      setBusy(false);
    }
  }

  async function onCopy(post: TodayDuePost) {
    try {
      await navigator.clipboard.writeText(post.content);
      setDueNote("Copied. Paste it into LinkedIn, post it, then press I posted it.");
    } catch {
      setDueNote("This browser did not allow copying to the clipboard.");
    }
  }

  async function onBackToDrafts(post: TodayDuePost) {
    setBusy(true);
    setDueNote(null);
    try {
      // For a post the creator has decided not to post: off the Queue, text
      // kept, and nothing recorded as published.
      await returnToDrafts(post.post_id);
      setDueNote("Moved back to your drafts. Search for it with Ctrl K to open it in the Composer.");
      await load();
    } catch (error) {
      setDueNote(error instanceof Error ? error.message : "The studio refused to move it.");
    } finally {
      setBusy(false);
    }
  }

  /**
   * Puts a waiting draft in the next slot the scheduler offers, from the
   * screen that shows the slots.
   *
   * The same two routes the Publish dialog uses, in the same order, so the
   * 12 hour rule and the collision check are the server's as they always
   * were; whatever it says about the time it chose is repeated here.
   */
  async function onQueueDraft(draft: DraftSummary) {
    setQueueing(draft.id);
    setDraftNote(null);
    try {
      const slot = await fetchNextSlot();
      if (!slot) {
        setDraftNote("There is no slot to put it in. Add one under Weekly slots, and it can be queued.");
        return;
      }
      await schedulePost(draft.id, slot.slot_datetime);
      await load();
      setDraftNote(
        `Queued for ${formatLocal(slot.slot_datetime)}${slot.cooldown_satisfied ? "" : ", which is inside your 12 hour cooldown"}.`,
      );
    } catch (error) {
      setDraftNote(error instanceof Error ? error.message : "The studio refused to queue it.");
    } finally {
      setQueueing(null);
    }
  }

  async function onPosted(post: TodayDuePost) {
    setBusy(true);
    setDueNote(null);
    try {
      // Recorded only now, on the creator's word, which is when it is true.
      await publishNow(post.post_id);
      setDueNote("Marked as published.");
      await load();
    } catch (error) {
      setDueNote(error instanceof Error ? error.message : "The studio refused to mark it as published.");
    } finally {
      setBusy(false);
    }
  }

  if (failed && !slots) return <Centered>QUEUE UNAVAILABLE</Centered>;
  if (!slots || !health) return <Centered>LOADING QUEUE</Centered>;

  const missed = due.filter((post) => post.missed);

  return (
    <div className="mx-auto w-full max-w-[150ch] px-6 py-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
          <h1 className="studio-title">Queue</h1>
          <p className="max-w-[72ch] text-[12px] leading-snug text-ink-secondary">
            The queue does not post anything. When a queued post&apos;s time comes, it moves to Due below, for
            you to post on LinkedIn yourself. It counts as published only once you press I posted it, or once
            the bridge sees it on LinkedIn.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onDispatch}
            disabled={busy}
            className="flex items-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
          >
            <Zap className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
            Check for due posts
          </button>
          <button
            type="button"
            onClick={onTogglePause}
            disabled={busy}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-medium transition-[filter]",
              health.queue_paused
                ? "bg-signal-orange text-on-signal hover:brightness-110"
                : "border border-edge text-ink-secondary hover:bg-soft hover:text-ink-primary",
              busy && "opacity-40",
            )}
          >
            {health.queue_paused ? (
              <Play className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
            ) : (
              <Pause className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
            )}
            {health.queue_paused ? "Resume the queue" : "Pause the queue"}
          </button>
        </div>
      </div>

      {health.queue_paused && (
        <p role="status" className="studio-meta mt-3 rounded-md border border-signal-orange/40 bg-signal-orange-subtle p-2.5 text-signal-orange-text">
          THE QUEUE IS PAUSED. QUEUED POSTS STAY QUEUED AND ARE NOT MARKED DUE UNTIL YOU RESUME IT.
        </p>
      )}

      {dispatchNote && (
        <p role="status" className="studio-meta mt-2 text-ink-secondary">
          {dispatchNote.toUpperCase()}
        </p>
      )}

      <ThisWeek slots={slots} scheduled={scheduled} due={due} />

      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="min-w-0">
        <section aria-labelledby="queue-due">
          <div className="mb-2 flex items-baseline justify-between gap-3">
            <p id="queue-due" className="studio-label">
              Due, waiting for you to post it
            </p>
            {missed.length > 0 && (
              <span className="studio-meta shrink-0 text-[10px] text-signal-orange-text">
                {missed.length === 1 ? "1 WAS MISSED" : `${missed.length} WERE MISSED`}
              </span>
            )}
          </div>
          {dueNote && (
            <p role="status" className="studio-meta mb-2 text-ink-secondary">
              {dueNote.toUpperCase()}
            </p>
          )}
          {due.length === 0 ? (
            <p className="text-[13px] leading-relaxed text-ink-muted">
              Nothing is due. A queued post appears here at its own time, and waits for you.
            </p>
          ) : (
            <ul className="flex flex-col divide-y divide-edge border-y border-edge">
              {due.map((post) => (
                <li key={post.post_id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2">
                  <span
                    className={cn(
                      "studio-meta shrink-0 text-[11px]",
                      post.missed ? "text-signal-orange-text" : "text-ink-muted",
                    )}
                  >
                    {post.missed ? "MISSED, WAS DUE " : "DUE "}
                    {formatLocal(post.scheduled_for).toUpperCase()}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[12px] text-ink-primary">{post.excerpt}</span>
                  <span className="flex shrink-0 items-center gap-2">
                    <button
                      type="button"
                      onClick={() => void onCopy(post)}
                      className="flex items-center gap-1.5 rounded-md border border-edge px-2 py-0.5 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary"
                    >
                      <Copy className="size-3" strokeWidth={1.75} aria-hidden="true" />
                      Copy text
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void onBackToDrafts(post)}
                      className="flex items-center gap-1.5 rounded-md border border-edge px-2 py-0.5 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
                    >
                      <Undo2 className="size-3" strokeWidth={1.75} aria-hidden="true" />
                      Back to drafts
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void onPosted(post)}
                      className="flex items-center gap-1.5 rounded-md bg-signal-orange px-2 py-0.5 text-[11px] font-medium text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-40"
                    >
                      <CheckCheck className="size-3" strokeWidth={1.75} aria-hidden="true" />
                      I posted it
                    </button>
                  </span>
                  {/* Why it was missed, in the scheduler's own terms: it was
                      not posted at its time because nothing was running then,
                      and the studio noticed this much later. Nothing moved
                      it; it still carries the time the creator chose. */}
                  {post.missed && (
                    <p className="w-full text-[12px] leading-snug text-ink-muted">
                      Missed because the studio was closed or the machine asleep at its time.
                      {post.missed.late_minutes !== null && post.missed.late_minutes !== undefined
                        ? ` Noticed ${lateness(post.missed.late_minutes)} late`
                        : " Noticed later"}
                      {post.missed.noticed_at ? `, at ${formatLocal(post.missed.noticed_at)}` : ""}. It kept its
                      time; nothing moved it.
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}

        </section>

        {/* Its own region: what is due and what is merely queued are two
            different questions, and a due post is the one with a decision
            waiting on it. */}
        <section aria-labelledby="queue-scheduled" className="mt-5">
          <p id="queue-scheduled" className="studio-label mb-2">
            Queued posts
          </p>
          {scheduled.length === 0 ? (
            <p className="text-[13px] leading-relaxed text-ink-muted">
              Nothing is queued yet. The drafts waiting below can go into the next open slot.
            </p>
          ) : (
            <ul className="flex flex-col divide-y divide-edge border-y border-edge">
              {scheduled.map((post) => (
                <li key={post.id} className="flex items-baseline gap-4 py-2">
                  <span className="studio-meta shrink-0 text-[11px]">{formatLocal(post.scheduled_for)}</span>
                  <span className="min-w-0 flex-1 truncate text-[12px] text-ink-secondary">
                    {post.content.split("\n")[0]}
                  </span>
                  {/* Opens the post in the Composer, which asks before it
                      changes a queued post's text. */}
                  {onEditText && (
                    <button
                      type="button"
                      onClick={() => onEditText(post.id)}
                      className="shrink-0 rounded-md border border-edge px-2 py-0.5 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary"
                    >
                      Edit text
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* What could go in a slot. The screen used to send a creator to the
            Composer to queue something while holding 150 drafts of their
            own and leaving half of itself blank. */}
        <section aria-labelledby="queue-drafts" className="mt-5">
          <div className="mb-2 flex items-baseline justify-between gap-3">
            <p id="queue-drafts" className="studio-label">
              Drafts waiting
            </p>
            {drafts.length > 0 && (
              <span className="studio-meta shrink-0 text-[10px] text-ink-muted">
                {drafts.length >= DRAFTS_SHOWN ? `NEWEST ${DRAFTS_SHOWN}` : `${drafts.length}`}
              </span>
            )}
          </div>
          {draftNote && (
            <p role="status" className="mb-2 text-[12px] text-ink-secondary">
              {draftNote}
            </p>
          )}
          {drafts.length === 0 ? (
            <p className="text-[13px] leading-relaxed text-ink-muted">
              No drafts are waiting. What you write in the Composer appears here, ready for a slot.
            </p>
          ) : (
            <ul className="flex flex-col divide-y divide-edge border-y border-edge">
              {drafts.map((draft) => (
                <li key={draft.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
                  <span className="min-w-0 flex-1 truncate text-[12px] text-ink-primary">
                    {draft.content.split("\n")[0] || "Untitled draft"}
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    {onEditText && (
                      <button
                        type="button"
                        onClick={() => onEditText(draft.id)}
                        className="rounded-md border border-edge px-2 py-0.5 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary"
                      >
                        Edit text
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={queueing !== null}
                      onClick={() => void onQueueDraft(draft)}
                      className="rounded-md border border-edge px-2 py-0.5 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
                    >
                      Queue it
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
        </div>

        <div className="flex flex-col gap-4">
          <Cadence health={health} rhythm={rhythm} slots={slots} />
          <WeeklySlots slots={slots} onChanged={load} />
        </div>
      </div>
    </div>
  );
}

/** How late a missed post was noticed, in the coarsest unit that is still true. */
function lateness(minutes: number): string {
  if (minutes < 90) return `${Math.round(minutes)} minutes`;
  const hours = minutes / 60;
  if (hours < 48) return `${hours.toFixed(1)} hours`;
  return `${Math.round(hours / 24)} days`;
}

/**
 * The week itself: each day, its slots, and what sits in them.
 *
 * This is what the screen opens on now, because the question it exists to
 * answer is when the next post goes out, and a week of seven named days
 * answers it in one look. A day holding a due or missed post is marked, so
 * the thing needing a decision is visible before anything is scrolled.
 */
function ThisWeek({
  slots,
  scheduled,
  due,
}: {
  slots: QueueSlot[];
  scheduled: ScheduledPost[];
  due: TodayDuePost[];
}) {
  const windowStart = startOfToday(new Date());
  const active = slots.filter((slot) => slot.is_active);
  // The next seven days, today first, each with the real date it is, so the
  // Monday in the grid cannot be mistaken for the Monday a post is queued
  // for. getDay is 0 for Sunday; DAYS starts on Monday, as the slots do.
  const days = Array.from({ length: 7 }, (_, offset) => {
    const date = new Date(windowStart.getFullYear(), windowStart.getMonth(), windowStart.getDate() + offset);
    return { offset, date, slotDay: (date.getDay() + 6) % 7 };
  });

  return (
    <section aria-labelledby="queue-week-at-a-glance" className="mt-4">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p id="queue-week-at-a-glance" className="studio-label">
          Next seven days
        </p>
        <span className="studio-meta text-[10px] text-ink-muted">
          {`${active.length} ${active.length === 1 ? "SLOT" : "SLOTS"} A WEEK · TIMES ARE THIS COMPUTER'S LOCAL TIME`}
        </span>
      </div>
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
        {days.map(({ offset, date, slotDay }) => {
          const daySlots = active.filter((slot) => slot.day_of_week === slotDay);
          const dayQueued = scheduled.filter((post) => dayInWindow(post.scheduled_for, windowStart) === offset);
          const dayDue = due.filter((post) => dayInWindow(post.scheduled_for, windowStart) === offset);
          const anyMissed = dayDue.some((post) => post.missed);
          return (
            <li
              key={date.toISOString()}
              className={cn(
                "rounded-md border p-2",
                anyMissed ? "border-signal-orange" : offset === 0 ? "border-edge-strong bg-soft" : "border-edge",
              )}
            >
              <div className="flex items-baseline justify-between gap-2">
                <p className="studio-meta text-[10px] text-ink-muted">
                  {DAYS[slotDay].toUpperCase()} {date.getDate()}
                </p>
                {offset === 0 && <span className="studio-meta text-[9px] text-ink-secondary">TODAY</span>}
              </div>
              {daySlots.length === 0 ? (
                <p className="mt-1 text-[11px] text-ink-muted">No slot</p>
              ) : (
                <ul className="mt-1 flex flex-col gap-1">
                  {daySlots.map((slot) => (
                    <li key={slot.id} className="text-[12px] leading-tight text-ink-primary">
                      {formatSlotTime(slot.time_slot)}
                      <span className="block truncate text-[10px] text-ink-muted">{slot.label}</span>
                    </li>
                  ))}
                </ul>
              )}
              <p
                className={cn(
                  "studio-meta mt-1.5 border-t border-edge pt-1 text-[10px]",
                  anyMissed ? "text-signal-orange-text" : dayQueued.length ? "text-ink-secondary" : "text-ink-muted",
                )}
              >
                {anyMissed
                  ? `${dayDue.filter((post) => post.missed).length} MISSED`
                  : dayDue.length
                    ? `${dayDue.length} DUE`
                    : dayQueued.length
                      ? `${dayQueued.length} QUEUED`
                      : "EMPTY"}
              </p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/**
 * Cadence: what the queue holds, against how steadily the creator actually
 * posts.
 *
 * The cadence health percentage is the queue's own arithmetic about
 * collisions and spacing. On its own it said "100%" beside "Collisions 0" on
 * an install with nothing queued, which is a number about nothing. Beside it
 * now is the creator's measured rhythm from their own posts: how many the
 * studio has read, the usual gap between them, and how long it has been.
 */
function Cadence({
  health,
  rhythm,
  slots,
}: {
  health: CadenceHealth;
  rhythm: CadenceInsights | null;
  slots: QueueSlot[];
}) {
  const weekly = slots.filter((slot) => slot.is_active).length;
  const usual = rhythm?.median_gap_days;
  // Both as a gap in days, which is the one unit they can be compared in.
  const slotGap = weekly > 0 ? 7 / weekly : null;
  return (
    <section aria-labelledby="queue-cadence">
      <p id="queue-cadence" className="studio-label mb-2">
        Cadence
      </p>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 border-y border-edge py-3">
        <Stat label="Queued" value={String(health.total_scheduled)} />
        <Stat
          label="Collisions"
          value={String(health.collision_count)}
          bad={health.collision_count > 0}
        />
        <Stat
          label="Closest spacing"
          value={health.min_spacing_hours === null ? "Not measured" : `${health.min_spacing_hours}h`}
        />
        <Stat label="Slots a week" value={String(weekly)} />
      </dl>

      <div className="mt-3 border-b border-edge pb-3">
        <p className="studio-label mb-1.5">Against your own rhythm</p>
        {!rhythm ? (
          <p className="text-[13px] leading-relaxed text-ink-muted">
            Your posting rhythm has not been read yet. It is measured from the posts the studio holds.
          </p>
        ) : (
          <>
            <dl className="flex flex-col gap-1.5">
              <Line label="Posts read" value={rhythm.posts.toLocaleString()} />
              <Line
                label="Your usual gap"
                value={
                  formatDays(usual) === null
                    ? NOT_MEASURED
                    : `${formatDays(usual)} between posts`
                }
              />
              <Line
                label="Since your last"
                value={gapOrNotMeasured(rhythm.days_since_last)}
              />
              <Line
                label="These slots"
                value={slotGap === null ? "No slots set" : `one post every ${formatDays(slotGap)}`}
              />
            </dl>
            {/* One sentence, and only when both numbers were measured. A
                comparison with half of itself missing is not a comparison. */}
            {slotGap !== null && usual !== null && usual !== undefined && (
              <p className="mt-2 text-[12px] leading-snug text-ink-secondary">
                {slotGap < usual * 0.75
                  ? `Your slots ask for more than you have posted: one every ${formatDays(slotGap)} against your usual ${formatDays(usual)}.`
                  : slotGap > usual * 1.5
                    ? `Your slots ask for less than you have posted: one every ${formatDays(slotGap)} against your usual ${formatDays(usual)}.`
                    : `Your slots are about the rhythm you have kept: one every ${formatDays(slotGap)} against your usual ${formatDays(usual)}.`}
              </p>
            )}
          </>
        )}
      </div>

      {health.next_smart_slot && (
        <div className="mt-3">
          <p className="studio-label mb-1">Next slot offered</p>
          <p className="text-[13px] text-ink-primary">
            {health.next_smart_slot.day_name} {formatSlotTime(health.next_smart_slot.time_slot)}
            <span className="mx-2 text-ink-muted">·</span>
            <span className="text-ink-secondary">{health.next_smart_slot.label}</span>
          </p>
          <p className="studio-meta mt-1">
            {health.next_smart_slot.cooldown_satisfied ? (
              <span className="text-signal-green-text">
                {health.next_smart_slot.hours_clearance}H CLEAR OF THE LAST POST
              </span>
            ) : (
              <span className="text-signal-orange-text">
                ONLY {health.next_smart_slot.hours_clearance}H SINCE THE LAST POST
              </span>
            )}
          </p>
        </div>
      )}
    </section>
  );
}

/**
 * The creator's posting week: the times Queue it offers, in this machine's
 * local time.
 *
 * These were thirteen fixed slots named after the original author's own
 * themes, with no way to change them. Each one can now be retimed, renamed
 * or removed, and slots added. A slot left unnamed is called after its day
 * and the part of the day. Posts already queued keep their times.
 */
function WeeklySlots({ slots, onChanged }: { slots: QueueSlot[]; onChanged: () => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);
  const [draft, setDraft] = useState<Record<number, { time: string; label: string }>>({});
  const [adding, setAdding] = useState({ day: 0, time: "09:00", label: "" });

  async function act(work: () => Promise<unknown>, done: string) {
    setBusy(true);
    setNote(null);
    try {
      await work();
      await onChanged();
      setNote({ text: done, error: false });
    } catch (caught) {
      setNote({ text: caught instanceof Error ? caught.message : "The studio refused the change.", error: true });
    } finally {
      setBusy(false);
    }
  }

  const edited = (slot: QueueSlot) => draft[slot.id] ?? { time: slot.time_slot, label: slot.label ?? "" };

  return (
    <section aria-labelledby="queue-week">
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <p id="queue-week" className="studio-label">
          Weekly slots
        </p>
        <button
          type="button"
          onClick={() => {
            setEditing((open) => !open);
            setDraft({});
            setNote(null);
          }}
          className="rounded-md border border-edge px-2.5 py-0.5 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary"
        >
          {editing ? "Done" : "Change slots"}
        </button>
      </div>
      {note && (
        <p role="status" className={cn("mb-2 text-[12px]", note.error ? "text-signal-orange-text" : "text-ink-secondary")}>
          {note.text}
        </p>
      )}
      {!editing ? (
        <p className="text-[12px] leading-snug text-ink-muted">
          Queue it offers the next of these that is at least 12 hours from your other posts. The week above
          shows them in place. Posts already queued keep their times.
        </p>
      ) : (
        <div className="rounded-md border border-edge p-3">
          <p className="text-[12px] leading-snug text-ink-secondary">
            Times are this computer&apos;s local time. Queue it offers the next of these that is at least
            12 hours from your other posts. Posts already queued keep their times.
          </p>
          {slots.length === 0 && <p className="mt-3 text-[12px] text-ink-muted">No slots. Add one below.</p>}
          <ul className="mt-3 flex flex-col divide-y divide-edge">
            {slots.map((slot) => {
              const value = edited(slot);
              const changed = value.time !== slot.time_slot || value.label !== (slot.label ?? "");
              const name = `${DAY_NAMES[slot.day_of_week]} ${slot.time_slot}`;
              return (
                <li key={slot.id} className="flex flex-wrap items-center gap-2 py-2">
                  <span className="w-24 shrink-0 text-[12px] text-ink-primary">{DAY_NAMES[slot.day_of_week]}</span>
                  <input
                    type="time"
                    value={value.time}
                    aria-label={`Time of the ${name} slot`}
                    onChange={(event) => setDraft({ ...draft, [slot.id]: { ...value, time: event.target.value } })}
                    className="rounded-md border border-edge bg-ink px-2 py-1 text-[12px] text-ink-primary"
                  />
                  <input
                    value={value.label}
                    maxLength={80}
                    aria-label={`Name of the ${name} slot`}
                    placeholder="Named after its day if left empty"
                    onChange={(event) => setDraft({ ...draft, [slot.id]: { ...value, label: event.target.value } })}
                    className="min-w-0 flex-1 basis-40 rounded-md border border-edge bg-ink px-2 py-1 text-[12px] text-ink-primary placeholder:text-ink-muted"
                  />
                  <button
                    type="button"
                    disabled={busy || !changed}
                    onClick={() =>
                      void act(
                        () => updateQueueSlot(slot.id, { time_slot: value.time, label: value.label }),
                        `Saved the ${DAY_NAMES[slot.day_of_week]} slot.`,
                      ).then(() => setDraft(({ [slot.id]: _gone, ...rest }) => rest))
                    }
                    className="rounded-md border border-edge px-2 py-1 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
                  >
                    Save
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    aria-label={`Remove the ${name} slot`}
                    onClick={() => void act(() => deleteQueueSlot(slot.id), `Removed the ${name} slot.`)}
                    className="grid size-7 place-items-center rounded-md border border-edge text-ink-muted transition-colors hover:border-edge-strong hover:text-ink-primary disabled:opacity-40"
                  >
                    <Trash2 className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                  </button>
                </li>
              );
            })}
          </ul>
          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-edge pt-3">
            <select
              value={adding.day}
              aria-label="Day of the new slot"
              onChange={(event) => setAdding({ ...adding, day: Number(event.target.value) })}
              className="rounded-md border border-edge bg-ink px-2 py-1 text-[12px] text-ink-primary"
            >
              {DAY_NAMES.map((day, index) => (
                <option key={day} value={index}>
                  {day}
                </option>
              ))}
            </select>
            <input
              type="time"
              value={adding.time}
              aria-label="Time of the new slot"
              onChange={(event) => setAdding({ ...adding, time: event.target.value })}
              className="rounded-md border border-edge bg-ink px-2 py-1 text-[12px] text-ink-primary"
            />
            <input
              value={adding.label}
              maxLength={80}
              aria-label="Name of the new slot"
              placeholder="Name, optional"
              onChange={(event) => setAdding({ ...adding, label: event.target.value })}
              className="min-w-0 flex-1 basis-40 rounded-md border border-edge bg-ink px-2 py-1 text-[12px] text-ink-primary placeholder:text-ink-muted"
            />
            <button
              type="button"
              disabled={busy || !adding.time}
              onClick={() =>
                void act(
                  () => addQueueSlot({ day_of_week: adding.day, time_slot: adding.time, label: adding.label }),
                  `Added ${DAY_NAMES[adding.day]} ${adding.time}.`,
                ).then(() => setAdding({ ...adding, label: "" }))
              }
              className="flex items-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
            >
              <Plus className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
              Add slot
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function Stat({ label, value, bad }: { label: string; value: string; bad?: boolean }) {
  return (
    <div>
      <dt className="text-[11px] text-ink-muted">{label}</dt>
      <dd className={cn("studio-meta mt-0.5 text-[13px]", bad ? "text-signal-orange-text" : "text-ink-primary")}>
        {value}
      </dd>
    </div>
  );
}

function Line({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="shrink-0 text-[12px] text-ink-muted">{label}</dt>
      <dd className="truncate text-right text-[12px] text-ink-secondary">{value}</dd>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid h-full place-items-center px-8">
      <p className="studio-meta max-w-[40ch] text-center leading-relaxed text-ink-muted">{children}</p>
    </div>
  );
}
