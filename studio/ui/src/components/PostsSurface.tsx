import { useCallback, useEffect, useState } from "react";
import { Activity, ChevronDown, ExternalLink, Loader2 } from "lucide-react";
import { fetchPostsInsights, launchBridge, type PostInsight, type PostsInsights } from "@/lib/api";
import { useRefresh } from "@/lib/refresh";
import { formatLocalDay } from "@/lib/time";
import { cn } from "@/lib/utils";
import { EmptySurface } from "./EmptySurface";

/** Settled posts with no figures at all, and how many of those came from LinkedIn's archive. */
type Unmeasured = { settled_without_figures?: number; settled_without_figures_from_archive?: number };

/**
 * Posts: which of your posts worked, and whom each one brought.
 *
 * "Worked" means against your own median, never a benchmark, and only for
 * posts at least a week old: before that a low number may just be a young
 * post. The two settled posts furthest above your usual are marked as worth
 * repurposing, because their form already worked for your audience.
 */
export function PostsSurface({
  onOpenLead,
  onOpenActivity,
  onOpenSetup,
}: {
  onOpenLead: (leadId: string) => void;
  onOpenActivity?: () => void;
  onOpenSetup?: () => void;
}) {
  const [data, setData] = useState<PostsInsights | null>(null);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(
    () =>
      fetchPostsInsights()
        .then((result) => {
          setData(result);
          setFailed(false);
        })
        .catch(() => setFailed(true)),
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);
  // Figures the bridge read from the other window appear on coming back to
  // this one, and a list that failed in an outage returns by itself.
  useRefresh(load);

  if (failed && !data) return <Centered>POSTS ARE UNAVAILABLE. IS THE STUDIO RUNNING?</Centered>;
  if (!data) return <Centered>LOADING YOUR POSTS</Centered>;
  if (!data.posts.length) {
    return (
      <EmptySurface label="Posts" title="What worked, and who it brought" onOpenSetup={onOpenSetup}>
        None of your posts have been imported yet. Import them in Setup, and each one appears here
        against your usual, with the people it brought.
      </EmptySurface>
    );
  }

  const { usual } = data;
  const usualLine = (["reactions", "comments", "impressions"] as const)
    .filter((metric) => usual[metric].median !== null)
    .map((metric) => `${Math.round(usual[metric].median as number).toLocaleString()} ${metric}`)
    .join(", ");

  return (
    <article className="mx-auto max-w-[80ch] px-8 py-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="studio-label">Posts</p>
          <h1 className="studio-title mt-2">What worked, and who it brought</h1>
        </div>
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
      <p className="mt-2 text-[13px] leading-relaxed text-ink-secondary">
        {usualLine
          ? `Your usual, the median of your posts older than ${data.settled_after_days} days: ${usualLine}.`
          : noUsualReason(data as PostsInsights & Unmeasured)}{" "}
        A post is compared with it only once it is {data.settled_after_days} days old.
      </p>

      <ul className="mt-6 flex flex-col divide-y divide-edge border-y border-edge">
        {data.posts.map((post) => (
          <PostRow
            key={post.activity_urn}
            post={post}
            best={data.best.includes(post.activity_urn)}
            expanded={open === post.activity_urn}
            onToggle={() => setOpen((current) => (current === post.activity_urn ? null : post.activity_urn))}
            onOpenLead={onOpenLead}
          />
        ))}
      </ul>
    </article>
  );
}

/**
 * Why there is no usual yet. Posts imported from LinkedIn's archive carry no
 * figures, and the screen used to say they were not old enough, next to a
 * list of posts from years ago.
 */
function noUsualReason(data: PostsInsights & Unmeasured): string {
  const unmeasured = data.settled_without_figures ?? 0;
  if (!unmeasured) return "Not enough settled posts yet to know your usual.";
  const archive = (data.settled_without_figures_from_archive ?? 0) > 0;
  return (
    `No usual yet: ${unmeasured} of your posts older than ${data.settled_after_days} days have no reactions, ` +
    `comments or impressions recorded${archive ? ", because LinkedIn's archive does not include them" : ""}. ` +
    `Press Import your history in Setup so the bridge reads their figures.`
  );
}

function PostRow({
  post,
  best,
  expanded,
  onToggle,
  onOpenLead,
}: {
  post: PostInsight;
  best: boolean;
  expanded: boolean;
  onToggle: () => void;
  onOpenLead: (leadId: string) => void;
}) {
  return (
    <li className="py-3">
      <button type="button" onClick={onToggle} aria-expanded={expanded} className="w-full text-left">
        <div className="flex items-baseline justify-between gap-4">
          <p className="studio-meta text-[10px] text-ink-muted">
            {formatLocalDay(post.published_at, "Date unknown").toUpperCase()}
            {!post.settled && " · STILL GROWING"}
            {best && <span className="ml-2 text-signal-green-text">WORTH REPURPOSING</span>}
          </p>
          <ChevronDown
            className={cn("size-3.5 shrink-0 text-ink-muted transition-transform", expanded && "rotate-180")}
            aria-hidden="true"
          />
        </div>
        <p className="mt-1 line-clamp-2 text-[13px] leading-snug text-ink-primary">{post.excerpt ?? "(no text)"}</p>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
          <Figure label="reactions" value={post.reactions} ratio={post.against_usual?.reactions} />
          <Figure label="comments" value={post.comments} ratio={post.against_usual?.comments} />
          <Figure label="impressions" value={post.impressions} ratio={post.against_usual?.impressions} />
          <span className="studio-meta text-[10px] text-ink-muted">
            {post.people_count} {post.people_count === 1 ? "PERSON" : "PEOPLE"} CAPTURED
            {post.conversations > 0 && ` · ${post.conversations} CONVERSATION${post.conversations > 1 ? "S" : ""}`}
          </span>
        </div>
      </button>

      {expanded && (
        <div className="mt-3 border-l border-edge pl-3">
          {post.people.length ? (
            <ul className="flex flex-col gap-1">
              {post.people.map((person) => (
                <li key={person.lead_id}>
                  <button
                    type="button"
                    onClick={() => onOpenLead(person.lead_id)}
                    className="text-[12px] text-ink-secondary hover:text-ink-primary"
                  >
                    {person.name}
                    <span className="studio-meta ml-2 text-[10px] text-ink-muted">
                      {person.commented ? "COMMENTED" : "REACTED"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="studio-meta text-[10px] leading-snug text-ink-muted">
              NOBODY CAPTURED FROM THIS POST YET. OPEN IT IN THE BRIDGE BROWSER AND ITS COMMENTERS ARE READ.
            </p>
          )}
          <OpenThePost url={post.url} />
        </div>
      )}
    </li>
  );
}

/**
 * Opens the post in the bridge browser, and says what came of it.
 *
 * The launch used to be fired and forgotten: no sign it was under way, and a
 * failure surfaced only as an uncaught error in the console, so nobody could
 * tell a browser opening behind the window from one that never started.
 */
function OpenThePost({ url }: { url: string }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function open() {
    setBusy(true);
    setNote(null);
    try {
      setNote((await launchBridge("auto", url)).message || "Opened in the bridge browser.");
    } catch (caught) {
      setNote(caught instanceof Error ? caught.message : "The browser could not be opened.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => void open()}
        disabled={busy}
        className="mt-2 flex items-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-50"
      >
        {busy ? (
          <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
        ) : (
          <ExternalLink className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
        )}
        Open the post
      </button>
      {note && (
        <p role="status" className="mt-1.5 text-[12px] leading-snug text-ink-secondary">
          {note}
        </p>
      )}
    </>
  );
}

function Figure({ label, value, ratio }: { label: string; value: number | null; ratio?: number }) {
  if (value === null) return null;
  return (
    <span className="studio-meta text-[10px] tabular-nums text-ink-secondary">
      {value.toLocaleString()} {label.toUpperCase()}
      {ratio !== undefined && (
        <span
          className={cn(
            "ml-1",
            ratio >= 1.2 ? "text-signal-green-text" : ratio <= 0.8 ? "text-signal-orange-text" : "text-ink-muted",
          )}
        >
          ({ratio.toFixed(1)}x)
        </span>
      )}
    </span>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid h-full place-items-center px-8">
      <p className="studio-meta max-w-[40ch] text-center leading-relaxed text-ink-muted">{children}</p>
    </div>
  );
}
