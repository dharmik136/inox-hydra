import { useCallback, useEffect, useState } from "react";
import { CheckCheck, Copy, Pause, Play, Undo2, Zap } from "lucide-react";
import {
  dispatchQueueNow,
  fetchCadenceHealth,
  fetchDuePosts,
  fetchSmartSlots,
  publishNow,
  returnToDrafts,
  toggleQueuePause,
  type CadenceHealth,
  type QueueSlot,
  type ScheduledPost,
} from "@/lib/api";
import { useRefresh } from "@/lib/refresh";
import { formatLocal } from "@/lib/time";
import { cn } from "@/lib/utils";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/**
 * The smart queue (blueprint build order phase 4).
 *
 * The queue posts nothing. At a post's time it marks the post due, and the
 * post waits at the top of this screen for the creator to post it on LinkedIn
 * and say so. The screen used to call this publishing: "Pause publishing",
 * "Run due posts", "scheduled posts will not go out", while at the slot the
 * post was silently recorded as published and counted in Analytics although
 * nothing had been posted. Pausing stops posts being marked due, and its state
 * is read back from the server rather than assumed from the click.
 */
export function QueueSurface({ onEditText }: { onEditText?: (postId: string) => void } = {}) {
  const [slots, setSlots] = useState<QueueSlot[] | null>(null);
  const [scheduled, setScheduled] = useState<ScheduledPost[]>([]);
  const [due, setDue] = useState<ScheduledPost[]>([]);
  const [dueNote, setDueNote] = useState<string | null>(null);
  const [health, setHealth] = useState<CadenceHealth | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dispatchNote, setDispatchNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [queue, cadence, duePosts] = await Promise.all([
        fetchSmartSlots(),
        fetchCadenceHealth(),
        fetchDuePosts(),
      ]);
      setSlots(queue.slots);
      setScheduled(queue.scheduled);
      setDue(duePosts);
      setHealth(cadence);
      setFailed(false);
    } catch {
      setFailed(true);
    }
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
          ? `${actions.length} post${actions.length === 1 ? "" : "s"} marked due or moved to a later slot`
          : "Nothing was due",
      );
      await load();
    } catch (error) {
      setDispatchNote(error instanceof Error ? error.message : "The check was refused");
    } finally {
      setBusy(false);
    }
  }

  async function onCopy(post: ScheduledPost) {
    try {
      await navigator.clipboard.writeText(post.content);
      setDueNote("Copied. Paste it into LinkedIn, post it, then press I posted it.");
    } catch {
      setDueNote("This browser did not allow copying to the clipboard.");
    }
  }

  async function onBackToDrafts(post: ScheduledPost) {
    setBusy(true);
    setDueNote(null);
    try {
      // For a post the creator has decided not to post: off the Queue, text
      // kept, and nothing recorded as published.
      await returnToDrafts(post.id);
      setDueNote("Moved back to your drafts. Search for it with Ctrl K to open it in the Composer.");
      await load();
    } catch (error) {
      setDueNote(error instanceof Error ? error.message : "The studio refused to move it.");
    } finally {
      setBusy(false);
    }
  }

  async function onPosted(post: ScheduledPost) {
    setBusy(true);
    setDueNote(null);
    try {
      // Recorded only now, on the creator's word, which is when it is true.
      await publishNow(post.id);
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

  const byDay = DAYS.map((_, index) => slots.filter((slot) => slot.day_of_week === index));

  return (
    <div className="mx-auto max-w-[96ch] px-8 py-8">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="studio-title">Queue</h1>
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

      <p className="mt-2 max-w-[70ch] text-[13px] leading-relaxed text-ink-secondary">
        The queue does not post anything. When a queued post&apos;s time comes, it moves to Due
        below, for you to post on LinkedIn yourself. It counts as published only once you press I
        posted it, or once the bridge sees it on LinkedIn.
      </p>

      {health.queue_paused && (
        <p role="status" className="studio-meta mt-4 rounded-md border border-signal-orange/40 bg-signal-orange-subtle p-3 text-signal-orange-text">
          THE QUEUE IS PAUSED. QUEUED POSTS STAY QUEUED AND ARE NOT MARKED DUE UNTIL YOU RESUME IT.
        </p>
      )}

      {dispatchNote && (
        <p role="status" className="studio-meta mt-3 text-ink-secondary">
          {dispatchNote.toUpperCase()}
        </p>
      )}

      <section className="mt-6" aria-labelledby="queue-due">
        <p id="queue-due" className="studio-label mb-3">
          Due, waiting for you to post it
        </p>
        {dueNote && (
          <p role="status" className="studio-meta mb-2 text-ink-secondary">
            {dueNote.toUpperCase()}
          </p>
        )}
        {due.length === 0 ? (
          <p className="studio-meta text-ink-muted">NOTHING IS DUE</p>
        ) : (
          <ul className="flex flex-col">
            {due.map((post) => (
              <li key={post.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-edge py-2">
                <span className="studio-meta shrink-0 text-[11px] text-signal-orange-text">
                  DUE {formatLocal(post.scheduled_for).toUpperCase()}
                </span>
                <span className="min-w-0 flex-1 truncate text-[12px] text-ink-primary">
                  {post.content.split("\n")[0]}
                </span>
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
              </li>
            ))}
          </ul>
        )}
      </section>

      <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-2 border-y border-edge py-4 sm:grid-cols-4">
        <Stat label="Queued" value={String(health.total_scheduled)} />
        <Stat label="Cadence health" value={`${health.cadence_health_score}%`} />
        <Stat
          label="Collisions"
          value={String(health.collision_count)}
          bad={health.collision_count > 0}
        />
        <Stat
          label="Closest spacing"
          value={health.min_spacing_hours === null ? "Not measured" : `${health.min_spacing_hours}h`}
        />
      </dl>

      {health.next_smart_slot && (
        <section className="mt-6">
          <p className="studio-label mb-1.5">Next slot</p>
          <p className="text-[14px] text-ink-primary">
            {health.next_smart_slot.day_name} {health.next_smart_slot.time_slot}
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
        </section>
      )}

      <section className="mt-8">
        <p className="studio-label mb-3">Weekly slots</p>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
          {byDay.map((daySlots, index) => (
            <div key={DAYS[index]} className="rounded-md border border-edge p-2">
              <p className="studio-meta text-[10px]">{DAYS[index].toUpperCase()}</p>
              {daySlots.length === 0 ? (
                <p className="mt-1.5 text-[11px] text-ink-muted">None</p>
              ) : (
                <ul className="mt-1.5 flex flex-col gap-1">
                  {daySlots.map((slot) => (
                    <li key={slot.id} className="text-[12px] text-ink-primary">
                      {slot.time_slot}
                      <span className="block text-[10px] text-ink-muted">{slot.label}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      </section>

      <section className="mt-8">
        <p className="studio-label mb-3">Queued posts</p>
        {scheduled.length === 0 ? (
          <p className="studio-meta text-ink-muted">NOTHING IS QUEUED</p>
        ) : (
          <ul className="flex flex-col">
            {scheduled.map((post) => (
              <li key={post.id} className="flex items-baseline gap-4 border-b border-edge py-2">
                <span className="studio-meta shrink-0 text-[11px]">{formatLocal(post.scheduled_for)}</span>
                <span className="truncate text-[12px] text-ink-secondary">
                  {post.content.split("\n")[0]}
                </span>
                {/* Opens the post in the Composer, which asks before it
                    changes a queued post's text. */}
                {onEditText && (
                  <button
                    type="button"
                    onClick={() => onEditText(post.id)}
                    className="ml-auto shrink-0 rounded-md border border-edge px-2 py-0.5 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary"
                  >
                    Edit text
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
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

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid h-full place-items-center px-8">
      <p className="studio-meta max-w-[40ch] text-center leading-relaxed text-ink-muted">{children}</p>
    </div>
  );
}
