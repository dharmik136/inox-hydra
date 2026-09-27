import { useEffect, useState } from "react";
import { ChevronDown, ExternalLink } from "lucide-react";
import { fetchPostsInsights, launchBridge, type PostInsight, type PostsInsights } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Posts: which of your posts worked, and whom each one brought.
 *
 * "Worked" means against your own median, never a benchmark, and only for
 * posts at least a week old: before that a low number may just be a young
 * post. The two settled posts furthest above your usual are marked as worth
 * repurposing, because their form already worked for your audience.
 */
export function PostsSurface({ onOpenLead }: { onOpenLead: (leadId: string) => void }) {
  const [data, setData] = useState<PostsInsights | null>(null);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    fetchPostsInsights().then(setData).catch(() => setFailed(true));
  }, []);

  if (failed) return <Centered>POSTS ARE UNAVAILABLE. IS THE STUDIO RUNNING?</Centered>;
  if (!data) return <Centered>LOADING YOUR POSTS</Centered>;
  if (!data.posts.length) {
    return <Centered>NO POSTS OF YOURS HAVE BEEN IMPORTED. IMPORT THEM FROM SETUP.</Centered>;
  }

  const { usual } = data;
  const usualLine = (["reactions", "comments", "impressions"] as const)
    .filter((metric) => usual[metric].median !== null)
    .map((metric) => `${Math.round(usual[metric].median as number).toLocaleString()} ${metric}`)
    .join(", ");

  return (
    <article className="mx-auto max-w-[80ch] px-8 py-8">
      <p className="studio-label">Posts</p>
      <h2 className="studio-title mt-2">What worked, and who it brought</h2>
      <p className="mt-2 text-[13px] leading-relaxed text-ink-secondary">
        {usualLine
          ? `Your usual, the median of your posts older than ${data.settled_after_days} days: ${usualLine}.`
          : "Not enough settled posts yet to know your usual."}{" "}
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
            {post.published_at ? post.published_at.slice(0, 10) : "DATE UNKNOWN"}
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
          <button
            type="button"
            onClick={() => void launchBridge("auto", post.url)}
            className="mt-2 flex items-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary"
          >
            <ExternalLink className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
            Open the post
          </button>
        </div>
      )}
    </li>
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
