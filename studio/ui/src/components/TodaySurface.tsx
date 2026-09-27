import { useCallback, useEffect, useState } from "react";
import { ExternalLink, Loader2 } from "lucide-react";
import {
  fetchToday,
  launchBridge,
  type MetricComparison,
  type TodayBrief,
  type TodayLatestPost,
  type TodayPerson,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Today: what to do in the next hour.
 *
 * The first screen once the studio knows who you are. Every section is
 * something to act on now, and nothing here is ranked by the ICP score: who
 * engaged with you twice this week is a fact, a keyword guess about a job
 * title is not. The comparison with "your usual" appears only when it is fair,
 * meaning both sides were read at about two days old and there are enough
 * earlier posts; otherwise the screen says why it is not shown.
 */
export function TodaySurface({
  onOpenLead,
  onOpenSetup,
}: {
  onOpenLead: (leadId: string) => void;
  onOpenSetup: () => void;
}) {
  const [brief, setBrief] = useState<TodayBrief | null>(null);
  const [failed, setFailed] = useState(false);
  const [opening, setOpening] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchToday()
      .then((result) => {
        setBrief(result);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, []);

  useEffect(() => {
    load();
    // Captures arrive while this screen is open, from the other window.
    const timer = window.setInterval(load, 30000);
    return () => window.clearInterval(timer);
  }, [load]);

  async function open(url: string) {
    setOpening(url);
    setNote(null);
    try {
      setNote((await launchBridge("auto", url)).message);
    } catch (caught) {
      setNote(caught instanceof Error ? caught.message : "The browser could not be opened.");
    } finally {
      setOpening(null);
    }
  }

  if (failed && !brief) return <Centered>TODAY IS UNAVAILABLE. IS THE STUDIO RUNNING?</Centered>;
  if (!brief) return <Centered>LOADING TODAY</Centered>;

  return (
    <article className="mx-auto max-w-[72ch] px-8 py-8">
      <p className="studio-label">Today</p>
      <h2 className="studio-title mt-2">What to do in the next hour</h2>
      <p className="studio-meta mt-2 text-[10px] leading-snug text-ink-muted">{freshnessLine(brief)}</p>

      <section className="mt-6 rounded-md border border-edge-strong p-4">
        <p className="studio-meta text-[10px] text-ink-muted">ONE THING TO OPEN</p>
        <p className="mt-1.5 text-[14px] leading-snug text-ink-primary">{brief.open_next.reason}</p>
        <div className="mt-3">
          {brief.open_next.action === "open" && brief.open_next.url ? (
            <button
              type="button"
              disabled={opening !== null}
              onClick={() => void open(brief.open_next.url as string)}
              className="flex items-center gap-1.5 rounded-md bg-signal-orange px-3 py-1.5 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-40"
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
              className="rounded-md bg-signal-orange px-3 py-1.5 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110"
            >
              Go to Setup
            </button>
          )}
        </div>
      </section>

      <Section label="Reply to">
        {!brief.identity.known ? (
          <Empty>ONCE YOU CONFIRM YOUR PROFILE, PEOPLE WHO ENGAGED WITH YOUR POSTS APPEAR HERE.</Empty>
        ) : brief.reply_to.length === 0 ? (
          <Empty>NOBODY FROM THE LAST TWO WEEKS IS WAITING ON A REPLY.</Empty>
        ) : (
          <ul className="flex flex-col divide-y divide-edge border-y border-edge">
            {brief.reply_to.map((person) => (
              <Person key={person.lead_id} person={person} onOpen={() => onOpenLead(person.lead_id)} />
            ))}
          </ul>
        )}
      </Section>

      <Section label="Your latest post">
        {brief.latest_post ? (
          <LatestPost post={brief.latest_post} opening={opening} onOpen={(url) => void open(url)} />
        ) : (
          <Empty>
            {brief.identity.known
              ? "NO POST OF YOURS HAS BEEN IMPORTED YET. IMPORT YOUR POSTS IN SETUP."
              : "YOUR POSTS APPEAR HERE ONCE THE STUDIO KNOWS WHO YOU ARE."}
          </Empty>
        )}
      </Section>

      <Section label="Queue">
        <dl className="flex flex-col gap-2">
          <Row
            label="Next to go out"
            value={
              brief.queue.next_scheduled
                ? `${formatWhen(brief.queue.next_scheduled.scheduled_for)}: ${brief.queue.next_scheduled.excerpt}`
                : "Nothing scheduled"
            }
          />
          <Row
            label="Next open slot"
            value={
              brief.queue.next_open_slot
                ? `${brief.queue.next_open_slot.day_name} ${brief.queue.next_open_slot.time_slot}${
                    brief.queue.next_open_slot.label ? `, ${brief.queue.next_open_slot.label}` : ""
                  }`
                : "No slot found"
            }
          />
        </dl>
      </Section>

      {note && (
        <p role="status" className="studio-meta mt-6 leading-snug text-ink-secondary">
          {note}
        </p>
      )}
    </article>
  );
}

function Person({ person, onOpen }: { person: TodayPerson; onOpen: () => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className="w-full py-3 text-left transition-colors hover:bg-soft/60"
      >
        <div className="flex items-baseline justify-between gap-3">
          <p className="truncate text-[13px] font-medium text-ink-primary">{person.name}</p>
          <p className="studio-meta shrink-0 text-[10px] text-ink-muted">
            {person.posts_engaged > 1 ? `${person.posts_engaged} OF YOUR POSTS` : person.commented ? "COMMENTED" : "REACTED"}
            {person.last_seen_at ? ` · ${ago(person.last_seen_at)}` : ""}
          </p>
        </div>
        {person.headline && <p className="mt-0.5 truncate text-[11px] text-ink-muted">{person.headline}</p>}
        {person.latest_comment && (
          <p className="mt-1.5 line-clamp-2 text-[13px] leading-snug text-ink-secondary">
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
      {post.excerpt && <p className="text-[13px] leading-snug text-ink-secondary">{post.excerpt}</p>}
      <p className="studio-meta mt-1.5 text-[10px] text-ink-muted">
        {post.age_hours < 48 ? `${Math.round(post.age_hours)} HOURS OLD` : `${Math.round(post.age_hours / 24)} DAYS OLD`}
        {post.current?.reactions != null ? ` · ${post.current.reactions} REACTIONS` : ""}
        {post.current?.comments != null ? ` · ${post.current.comments} COMMENTS` : ""}
      </p>

      {rows.length > 0 ? (
        <div className="mt-3">
          <p className="studio-meta mb-1.5 text-[10px] text-ink-muted">AT ABOUT TWO DAYS OLD, AGAINST YOUR USUAL</p>
          <dl className="flex flex-col gap-1">
            {rows.map(([metric, value]) => (
              <div key={metric} className="flex items-baseline justify-between gap-3">
                <dt className="text-[12px] text-ink-secondary">{METRIC_LABELS[metric] ?? metric}</dt>
                <dd className="studio-meta text-right text-[11px] tabular-nums">
                  <span
                    className={cn(
                      value.ratio !== null && value.ratio >= 1.2 && "text-signal-green-text",
                      value.ratio !== null && value.ratio <= 0.8 && "text-signal-orange-text",
                      (value.ratio === null || (value.ratio > 0.8 && value.ratio < 1.2)) && "text-ink-secondary",
                    )}
                  >
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
          <p className="mt-3 text-[12px] leading-snug text-ink-muted">Not compared: {post.not_compared_because}.</p>
        )
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {[
          { url: post.url, label: "Open the post" },
          { url: post.analytics_url, label: "Open its analytics" },
        ].map((link) => (
          <button
            key={link.url}
            type="button"
            disabled={opening !== null}
            onClick={() => onOpen(link.url)}
            className="flex items-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
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

function freshnessLine(brief: TodayBrief): string {
  const { bridge, drifting, last_capture_at } = brief.freshness;
  const parts = [
    bridge.connected ? "BRIDGE CONNECTED" : bridge.last_seen_at ? `BRIDGE LAST SEEN ${ago(bridge.last_seen_at)}` : "BRIDGE NOT SEEN YET",
    last_capture_at ? `LAST CAPTURE ${ago(last_capture_at)}` : "NOTHING CAPTURED YET",
  ];
  if (drifting.length) parts.push(`${drifting.length} PART${drifting.length > 1 ? "S" : ""} OF THE CAPTURE NOT WORKING`);
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

function formatWhen(iso: string): string {
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? iso : when.toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" });
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <p className="studio-label mb-3">{label}</p>
      {children}
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="shrink-0 text-[12px] text-ink-muted">{label}</dt>
      <dd className="truncate text-right text-[13px] text-ink-secondary">{value}</dd>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="studio-meta text-[10px] leading-snug text-ink-muted">{children}</p>;
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid h-full place-items-center px-8">
      <p className="studio-meta max-w-[40ch] text-center leading-relaxed text-ink-muted">{children}</p>
    </div>
  );
}
