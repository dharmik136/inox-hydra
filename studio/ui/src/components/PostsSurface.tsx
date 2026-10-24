import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, ChevronLeft, ChevronRight, Search } from "lucide-react";
import { fetchPostsInsights, type PostInsight, type PostsInsights, type PostsQuery } from "@/lib/api";
import { useRefresh } from "@/lib/refresh";
import { formatLocalDay } from "@/lib/time";
import { cn } from "@/lib/utils";
import { EmptySurface } from "./EmptySurface";
import { PostDetail } from "./PostDetail";

/** Settled posts with no figures at all, and how many of those came from LinkedIn's archive. */
type Unmeasured = { settled_without_figures?: number; settled_without_figures_from_archive?: number };

const PAGE_SIZE = 20;

const SORTS: { key: PostsQuery["sort"] & string; label: string }[] = [
  { key: "newest", label: "Newest" },
  { key: "oldest", label: "Oldest" },
  { key: "reactions", label: "Most reactions" },
  { key: "impressions", label: "Most impressions" },
  { key: "comments", label: "Most comments" },
];

const SETTLED_FILTERS: { key: "" | "settled" | "growing"; label: string }[] = [
  { key: "", label: "All" },
  { key: "settled", label: "Settled" },
  { key: "growing", label: "Still growing" },
];

/**
 * Posts: a table, not a column of cards.
 *
 * It used to render every post the creator had ever written down one column,
 * 324,344 characters, 176 screens tall, with no way to reach a post past the
 * fiftieth without opening the network tab. This is a table: sorted,
 * filtered and paged, with a visible count, with reach and response shown as
 * a pair per post (results.pair) and a settle state (measured or assumed,
 * from results.settled_after_hours). A row opens one post into its detail
 * rather than rendering everything inline.
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
  const [sort, setSort] = useState<PostsQuery["sort"] & string>("newest");
  const [settledFilter, setSettledFilter] = useState<"" | "settled" | "growing">("");
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);

  // The search box asks the server only after the typing pauses, so a
  // keystroke does not fire a request on a table of 1,417 posts.
  useEffect(() => {
    const id = window.setTimeout(() => setQuery(queryInput.trim()), 300);
    return () => window.clearTimeout(id);
  }, [queryInput]);

  // Any change to how the table is sorted or filtered starts again from its
  // first page: an offset carried over from a longer, unfiltered list would
  // either repeat rows or skip past the end of a shorter one.
  useEffect(() => {
    setOffset(0);
  }, [sort, settledFilter, query]);

  const load = useCallback(
    () =>
      fetchPostsInsights({
        limit: PAGE_SIZE,
        offset,
        sort,
        settled_state: settledFilter || undefined,
        q: query || undefined,
      })
        .then((result) => {
          setData(result);
          setFailed(false);
        })
        .catch(() => setFailed(true)),
    [offset, sort, settledFilter, query],
  );
  useEffect(() => {
    void load();
  }, [load]);
  // Figures the bridge read from the other window appear on coming back to
  // this one, and a list that failed in an outage returns by itself.
  useRefresh(load);

  const bestSet = useMemo(() => new Set(data?.best ?? []), [data?.best]);
  const worstSet = useMemo(() => new Set(data?.worst ?? []), [data?.worst]);

  if (failed && !data) return <Centered>POSTS ARE UNAVAILABLE. IS THE STUDIO RUNNING?</Centered>;
  if (!data) return <Centered>LOADING YOUR POSTS</Centered>;
  if (data.total === 0 && !query && !settledFilter) {
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

  const shownFrom = data.total === 0 ? 0 : data.offset + 1;
  const shownTo = data.offset + data.returned;

  return (
    <article className="mx-auto max-w-[120ch] px-8 py-8">
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

      {/* Filter, search and sort: the whole history is behind the table, so
          every one of these asks the server again rather than narrowing a
          page already in hand. */}
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <div className="relative">
          <Search
            className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-ink-muted"
            strokeWidth={1.75}
            aria-hidden="true"
          />
          <input
            value={queryInput}
            onChange={(event) => setQueryInput(event.target.value)}
            placeholder="Search your posts"
            aria-label="Search your posts"
            className="w-56 rounded-md border border-edge bg-ink py-1.5 pr-3 pl-8 text-[12px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
          />
        </div>
        <div className="flex items-center gap-1" role="group" aria-label="Settled state">
          {SETTLED_FILTERS.map((candidate) => (
            <button
              key={candidate.key || "all"}
              type="button"
              onClick={() => setSettledFilter(candidate.key)}
              aria-pressed={settledFilter === candidate.key}
              className={cn(
                "rounded-full border px-2.5 py-0.5 text-[11px]",
                settledFilter === candidate.key
                  ? "border-edge-strong bg-soft text-ink-primary"
                  : "border-edge text-ink-muted hover:text-ink-secondary",
              )}
            >
              {candidate.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1" role="group" aria-label="Sort">
          {SORTS.map((candidate) => (
            <button
              key={candidate.key}
              type="button"
              onClick={() => setSort(candidate.key)}
              aria-pressed={sort === candidate.key}
              className={cn(
                "flex items-center gap-1 rounded-md px-2.5 py-1 text-[11px] font-medium",
                sort === candidate.key ? "bg-soft text-ink-primary" : "text-ink-muted hover:text-ink-secondary",
              )}
            >
              {candidate.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4 overflow-x-auto border-y border-edge">
        <table className="w-full text-left">
          <thead>
            <tr className="studio-label border-b border-edge">
              <th scope="col" className="py-2 pr-3 font-medium">Post</th>
              <th scope="col" className="py-2 pr-3 font-medium">Date</th>
              <th scope="col" className="py-2 pr-3 text-right font-medium">Reach &amp; response</th>
              <th scope="col" className="py-2 pr-3 text-right font-medium">Reactions</th>
              <th scope="col" className="py-2 pr-3 text-right font-medium">Comments</th>
              <th scope="col" className="py-2 pr-3 text-right font-medium">Impressions</th>
              <th scope="col" className="py-2 font-medium">People</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-edge">
            {data.posts.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-6 text-center">
                  <span className="studio-meta text-ink-muted">NO POST MATCHES THIS SEARCH AND FILTER.</span>
                </td>
              </tr>
            ) : (
              data.posts.map((post) => (
                <PostRow
                  key={post.activity_urn}
                  post={post}
                  best={bestSet.has(post.activity_urn)}
                  worst={worstSet.has(post.activity_urn)}
                  onOpen={() => setOpen(post.activity_urn)}
                />
              ))
            )}
          </tbody>
        </table>
      </div>

      <p className="studio-meta mt-2 text-[10px] leading-snug text-ink-muted">
        REACH AND RESPONSE ARE WHERE A POST SITS AMONG YOUR OWN POSTS READ AT THE SAME AGE, AS PERCENTILES, AND ARE
        READ TOGETHER. A FIGURE IN BRACKETS IS THE POST AGAINST YOUR USUAL. A POST STILL GROWING IS NOT COMPARED.
      </p>

      {/* The count and the control that reaches the rest of 1,417 posts: the
          screen used to show fifty of them with nothing beyond that fiftieth. */}
      <div className="mt-3 flex items-center justify-between gap-3">
        <p className="studio-meta text-[11px] text-ink-muted">
          {data.total === 0 ? "0 of 0" : `${shownFrom}–${shownTo} of ${data.total.toLocaleString()}`}
        </p>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}
            disabled={offset === 0}
            aria-label="Previous page"
            className="grid size-7 place-items-center rounded-md border border-edge text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
          >
            <ChevronLeft className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
          </button>
          <p className="studio-meta px-1 text-[11px] text-ink-muted">
            PAGE {Math.floor(offset / PAGE_SIZE) + 1} OF {Math.max(1, Math.ceil(data.total / PAGE_SIZE))}
          </p>
          <button
            type="button"
            onClick={() => setOffset((current) => current + PAGE_SIZE)}
            disabled={!data.has_more}
            aria-label="Next page"
            className="grid size-7 place-items-center rounded-md border border-edge text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
          >
            <ChevronRight className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
          </button>
        </div>
      </div>

      {open && <PostDetail activityUrn={open} onClose={() => setOpen(null)} onOpenLead={onOpenLead} />}
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
  worst,
  onOpen,
}: {
  post: PostInsight;
  best: boolean;
  worst: boolean;
  onOpen: () => void;
}) {
  const pair = post.reach_and_response;
  return (
    <tr className="align-top">
      <td className="max-w-[46ch] py-2.5 pr-3">
        <button type="button" onClick={onOpen} className="text-left text-[13px] leading-snug text-ink-primary hover:underline">
          <span className="line-clamp-2">{post.excerpt ?? "(no text)"}</span>
        </button>
        {(best || worst) && (
          <p className="studio-meta mt-1 text-[10px]">
            {best && <span className="text-signal-green-text">WORTH REPURPOSING</span>}
            {best && worst && " · "}
            {worst && <span className="text-signal-orange-text">UNDERPERFORMED</span>}
          </p>
        )}
      </td>
      <td className="py-2.5 pr-3">
        <p className="studio-meta text-[10px] text-ink-muted whitespace-nowrap">
          {formatLocalDay(post.published_at, "Date unknown").toUpperCase()}
        </p>
        <p className="studio-meta mt-0.5 text-[10px] text-ink-muted">
          {post.settled ? "SETTLED" : "STILL GROWING"}
        </p>
      </td>
      <td className="py-2.5 pr-3 text-right">
        {/* Both numbers or neither: a post can sit at p5 for reach and p86
            for response at the same moment, and either alone reads as the
            opposite of the truth (results.pair). */}
        {pair ? (
          <span className="studio-meta text-[10px] tabular-nums text-ink-secondary" title={pair.shape}>
            p{pair.reach.percentile} / p{pair.response.percentile}
          </span>
        ) : (
          <span className="studio-meta text-[10px] text-ink-muted">not read at a comparable age</span>
        )}
      </td>
      <RatioCell value={post.reactions} ratio={post.against_usual?.reactions} />
      <RatioCell value={post.comments} ratio={post.against_usual?.comments} />
      <RatioCell value={post.impressions} ratio={post.against_usual?.impressions} />
      <td className="py-2.5">
        <span className="studio-meta text-[10px] tabular-nums text-ink-secondary">
          {post.people_count} {post.people_count === 1 ? "PERSON" : "PEOPLE"}
          {post.conversations > 0 && ` · ${post.conversations} CONVO${post.conversations > 1 ? "S" : ""}`}
        </span>
      </td>
    </tr>
  );
}

function RatioCell({ value, ratio }: { value: number | null; ratio?: number }) {
  return (
    <td className="py-2.5 pr-3 text-right">
      {value === null ? (
        <span className="studio-meta text-[10px] text-ink-muted">not measured</span>
      ) : (
        <span className="studio-meta text-[10px] tabular-nums text-ink-secondary">
          {value.toLocaleString()}
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
      )}
    </td>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid h-full place-items-center px-8">
      <p className="studio-meta max-w-[40ch] text-center leading-relaxed text-ink-muted">{children}</p>
    </div>
  );
}
