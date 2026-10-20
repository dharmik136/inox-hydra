import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, Check, CheckCheck, Copy, ExternalLink, Loader2 } from "lucide-react";
import {
  fetchToday,
  launchBridge,
  publishNow,
  syncAllActivity,
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
  onOpenActivity,
  onOpenQueue,
}: {
  onOpenLead: (leadId: string) => void;
  onOpenSetup: () => void;
  onOpenActivity?: () => void;
  onOpenQueue?: () => void;
}) {
  const [brief, setBrief] = useState<TodayBrief | null>(null);
  const [failed, setFailed] = useState(false);
  const [opening, setOpening] = useState<string | null>(null);
  // What happened after a click, shown in the section that was clicked
  // rather than at the foot of the page, out of sight.
  const [note, setNote] = useState<{ text: string; at: "top" | "latest" | "due"; error: boolean } | null>(null);

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
      setNote({ text: caught instanceof Error ? caught.message : "Sync could not be started.", at: "top", error: true });
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
      setNote({ text: "Marked as published.", at: "due", error: false });
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

  if (failed && !brief) return <Centered>TODAY IS UNAVAILABLE. IS THE STUDIO RUNNING?</Centered>;
  if (!brief) return <Centered>LOADING TODAY</Centered>;

  return (
    <article className="mx-auto max-w-[72ch] px-8 py-8">
      <p className="studio-label">Today</p>
      <h1 className="studio-title mt-2">What to do in the next hour</h1>
      <p className="studio-meta mt-2 text-[10px] leading-snug text-ink-muted">{freshnessLine(brief)}</p>

      {/* First, because it has a time on it. A queued post is not posted by
          the studio: at its time it waits here and on the Queue. */}
      {brief.queue.due.length > 0 && (
        <section className="mt-6 rounded-md border border-signal-orange p-4">
          <p className="studio-meta text-[10px] text-signal-orange-text">
            {brief.queue.due.length === 1 ? "A POST IS DUE" : `${brief.queue.due.length} POSTS ARE DUE`}
          </p>
          <p className="mt-1.5 text-[14px] leading-snug text-ink-primary">
            Its time has come. Copy the text, post it on LinkedIn yourself, then press I posted it.
          </p>
          <ul className="mt-3 flex flex-col divide-y divide-edge border-y border-edge">
            {brief.queue.due.map((post) => (
              <li key={post.post_id} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 py-2">
                <span className="studio-meta shrink-0 text-[10px] text-signal-orange-text">
                  DUE {formatWhen(post.scheduled_for).toUpperCase()}
                </span>
                <span className="min-w-0 flex-1 truncate text-[13px] text-ink-secondary">{post.excerpt}</span>
                <span className="flex shrink-0 items-center gap-2">
                  <button
                    type="button"
                    onClick={() => void copyDue(post.content)}
                    className="flex items-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary"
                  >
                    <Copy className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                    Copy text
                  </button>
                  <button
                    type="button"
                    disabled={opening !== null}
                    onClick={() => void markPosted(post.post_id)}
                    className="flex items-center gap-1.5 rounded-md bg-signal-orange px-2.5 py-1 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-40"
                  >
                    {opening === post.post_id ? (
                      <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                    ) : (
                      <CheckCheck className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                    )}
                    I posted it
                  </button>
                </span>
              </li>
            ))}
          </ul>
          {onOpenQueue && (
            <button
              type="button"
              onClick={onOpenQueue}
              className="mt-3 text-[12px] text-ink-secondary underline underline-offset-2 hover:text-ink-primary"
            >
              Not posting it? Move it back to drafts from the Queue
            </button>
          )}
          {note?.at === "due" && <Note text={note.text} error={note.error} />}
        </section>
      )}

      <section className="mt-6 rounded-md border border-edge-strong p-4">
        <p className="studio-meta text-[10px] text-ink-muted">ONE THING TO OPEN</p>
        <p className="mt-1.5 text-[14px] leading-snug text-ink-primary">{brief.open_next.reason}</p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
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
          <button
            type="button"
            disabled={opening !== null}
            onClick={() => void syncAll()}
            className="flex items-center gap-1.5 rounded-md border border-edge bg-soft px-3 py-1.5 text-[12px] font-medium text-ink-primary transition-[filter] hover:brightness-110 disabled:opacity-40"
          >
            {opening === "sync-all" ? (
              <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
            ) : (
              <Check className="size-3.5" strokeWidth={2} aria-hidden="true" />
            )}
            Sync Activity via Bridge
          </button>
          {onOpenActivity && (
            <button
              type="button"
              onClick={onOpenActivity}
              className="flex items-center gap-1.5 rounded-md border border-edge bg-soft px-3 py-1.5 text-[12px] font-medium text-ink-primary transition-[filter] hover:brightness-110"
            >
              <Activity className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
              Open Activity
            </button>
          )}
        </div>
        {note?.at === "top" && <Note text={note.text} error={note.error} />}
      </section>

      <Section label="Reply to">
        {!brief.identity.known ? (
          <Empty>Once you confirm your profile, people who engaged with your posts appear here.</Empty>
        ) : brief.reply_to.length === 0 ? (
          <Empty>Nobody from the last two weeks is waiting on a reply.</Empty>
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
          <LatestPost post={brief.latest_post} opening={opening} onOpen={(url) => void open(url, "latest")} />
        ) : (
          <Empty>
            {brief.identity.known
              ? "No post of yours has been imported yet. Import your posts in Setup."
              : "Your posts appear here once the studio knows who you are."}
          </Empty>
        )}
        {note?.at === "latest" && <Note text={note.text} error={note.error} />}
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
    </article>
  );
}

/** engaged_at: when the studio first saw their latest comment, not when it was last re-read. */
type ReplyPerson = TodayPerson & { engaged_at?: string | null };

function Person({ person, onOpen }: { person: ReplyPerson; onOpen: () => void }) {
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
            {person.engaged_at ? ` · ${ago(person.engaged_at)}` : ""}
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
      className={cn("studio-meta mt-3 leading-snug outline-none", error ? "text-signal-orange-text" : "text-ink-secondary")}
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
