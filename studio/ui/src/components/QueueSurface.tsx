import { useCallback, useEffect, useState } from "react";
import { Pause, Play, Zap } from "lucide-react";
import {
  dispatchQueueNow,
  fetchCadenceHealth,
  fetchSmartSlots,
  toggleQueuePause,
  type CadenceHealth,
  type QueueSlot,
  type ScheduledPost,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/**
 * The smart queue (blueprint build order phase 4).
 *
 * Two things the creator needs to see at once: when the studio intends to
 * publish, and whether it currently will. Pausing is the control that exists
 * to stop publishing, so its state is read back from the server rather than
 * assumed from the click.
 */
export function QueueSurface() {
  const [slots, setSlots] = useState<QueueSlot[] | null>(null);
  const [scheduled, setScheduled] = useState<ScheduledPost[]>([]);
  const [health, setHealth] = useState<CadenceHealth | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dispatchNote, setDispatchNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [queue, cadence] = await Promise.all([fetchSmartSlots(), fetchCadenceHealth()]);
      setSlots(queue.slots);
      setScheduled(queue.scheduled);
      setHealth(cadence);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

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
          ? `${actions.length} action${actions.length === 1 ? "" : "s"} taken`
          : "Nothing was due",
      );
      await load();
    } catch {
      setDispatchNote("The dispatch run was refused");
    } finally {
      setBusy(false);
    }
  }

  if (failed) return <Centered>QUEUE UNAVAILABLE</Centered>;
  if (!slots || !health) return <Centered>LOADING QUEUE</Centered>;

  const byDay = DAYS.map((_, index) => slots.filter((slot) => slot.day_of_week === index));

  return (
    <div className="mx-auto max-w-[96ch] px-8 py-8">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h2 className="studio-title">Queue</h2>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onDispatch}
            disabled={busy}
            className="flex items-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
          >
            <Zap className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
            Run due posts
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
            {health.queue_paused ? "Resume publishing" : "Pause publishing"}
          </button>
        </div>
      </div>

      {health.queue_paused && (
        <p role="status" className="studio-meta mt-4 rounded-md border border-signal-orange/40 bg-signal-orange-subtle p-3 text-signal-orange-text">
          AUTOMATED PUBLISHING IS PAUSED. SCHEDULED POSTS WILL NOT GO OUT.
        </p>
      )}

      {dispatchNote && (
        <p role="status" className="studio-meta mt-3 text-ink-secondary">
          {dispatchNote.toUpperCase()}
        </p>
      )}

      <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-2 border-y border-edge py-4 sm:grid-cols-4">
        <Stat label="Scheduled" value={String(health.total_scheduled)} />
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
        <p className="studio-label mb-3">Scheduled posts</p>
        {scheduled.length === 0 ? (
          <p className="studio-meta text-ink-muted">NOTHING IS SCHEDULED</p>
        ) : (
          <ul className="flex flex-col">
            {scheduled.map((post) => (
              <li key={post.id} className="flex items-baseline gap-4 border-b border-edge py-2">
                <span className="studio-meta shrink-0 text-[11px]">
                  {post.scheduled_for ? post.scheduled_for.slice(0, 16).replace("T", " ") : "unscheduled"}
                </span>
                <span className="truncate text-[12px] text-ink-secondary">
                  {post.content.split("\n")[0]}
                </span>
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
