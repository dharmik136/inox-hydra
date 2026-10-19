import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  Check,
  Copy,
  ExternalLink,
  Loader2,
  Radio,
  RefreshCw,
} from "lucide-react";
import {
  fetchActivityStream,
  launchBridge,
  syncAllActivity,
  type ActivityStreamData,
} from "@/lib/api";
import { cn } from "@/lib/utils";

function ago(iso: string): string {
  const normalized = iso.includes("T") || iso.endsWith("Z") ? iso : `${iso.replace(" ", "T")}Z`;
  const then = new Date(normalized).getTime();
  if (Number.isNaN(then)) return iso;
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 15) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

export function ActivitySurface({
  onOpenLead,
}: {
  onOpenLead?: (leadId: string) => void;
}) {
  const [stream, setStream] = useState<ActivityStreamData | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [tab, setTab] = useState<"posts" | "comments" | "reactions" | "leads" | "imports">("posts");
  const [copiedUrn, setCopiedUrn] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncNotice, setSyncNotice] = useState<string | null>(null);
  const [openingPost, setOpeningPost] = useState<string | null>(null);
  /** What the last action on a post row came to, shown under that row. */
  const [rowNote, setRowNote] = useState<{ urn: string; text: string } | null>(null);

  const loadData = useCallback(async () => {
    try {
      const result = await fetchActivityStream(50);
      setStream(result);
      setFailed(false);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = window.setInterval(() => {
      loadData();
    }, 2500);
    return () => window.clearInterval(interval);
  }, [autoRefresh, loadData]);

  async function handleSyncAll() {
    setSyncing(true);
    setSyncNotice(null);
    try {
      const response = await syncAllActivity();
      setSyncNotice(response.message);
      await loadData();
    } catch (err) {
      setSyncNotice(err instanceof Error ? err.message : "Sync could not be started.");
    } finally {
      setSyncing(false);
    }
  }

  async function openBridgePost(activityUrn: string) {
    setOpeningPost(activityUrn);
    try {
      const postUrl = `https://www.linkedin.com/feed/update/${activityUrn}/`;
      await launchBridge("auto", postUrl);
    } catch {
      // Ignored if browser bridge cannot focus
    } finally {
      setOpeningPost(null);
    }
  }

  // The tick waits for the browser to accept the copy. A refusal leaves the
  // URN on screen to select by hand rather than claiming it is on the clipboard.
  function copyUrn(urn: string) {
    setRowNote(null);
    const refused = () => setRowNote({ urn, text: `Could not be copied. Select it by hand: ${urn}` });
    if (!navigator?.clipboard?.writeText) {
      refused();
      return;
    }
    navigator.clipboard
      .writeText(urn)
      .then(() => {
        setCopiedUrn(urn);
        window.setTimeout(() => setCopiedUrn(null), 2000);
      })
      .catch(refused);
  }

  if (failed && !stream) {
    return (
      <div className="grid h-full place-items-center px-8">
        <div className="max-w-[44ch] text-center">
          <p className="studio-label text-signal-orange-text">ACTIVITY STREAM UNAVAILABLE</p>
          <p className="mt-2 text-[13px] text-ink-muted">
            The local studio server is unreachable or returned an authentication error. Verify that the backend service is running on 127.0.0.1:8000.
          </p>
          <button
            type="button"
            onClick={() => {
              setLoading(true);
              loadData();
            }}
            className="mt-4 rounded-md border border-edge bg-soft px-3 py-1.5 text-[12px] font-medium text-ink-primary hover:bg-raised"
          >
            Retry Connection
          </button>
        </div>
      </div>
    );
  }

  if (loading && !stream) {
    return (
      <div className="grid h-full place-items-center px-8">
        <div className="flex items-center gap-2 text-ink-muted">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          <span className="studio-meta text-[11px]">LOADING LIVE ACTIVITY STREAM</span>
        </div>
      </div>
    );
  }

  if (!stream) return null;

  const { summary } = stream;
  const bridgeOnline = summary.bridge_connected;

  return (
    <article className="mx-auto max-w-[88ch] px-8 py-8">
      {/* Top Banner and Heading */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="studio-label">Activity</span>
            {/* Token colours only. The raw palette classes this used did not
                follow the theme, and failed contrast in the light one. Idle is
                not a warning, so it is not drawn as one. */}
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-medium tracking-wide uppercase",
                bridgeOnline ? "bg-signal-green-subtle text-signal-green-text" : "bg-soft text-ink-secondary",
              )}
            >
              <span
                className={cn("size-1.5 rounded-full", bridgeOnline ? "bg-signal-green" : "bg-ink-muted")}
                aria-hidden="true"
              />
              {bridgeOnline ? "Bridge running" : "Bridge idle"}
            </span>
          </div>
          <h1 className="studio-title mt-1.5">What the bridge has read</h1>
          <p className="mt-1 max-w-[62ch] text-[13px] leading-relaxed text-ink-secondary">
            Everything the browser extension has read from your LinkedIn, newest first: your posts, your
            comments and reactions elsewhere, and the people who engaged. It is kept in this studio's
            database and nowhere else.
          </p>
        </div>

        {/* Live Controls */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setAutoRefresh((prev) => !prev)}
            aria-pressed={autoRefresh}
            className={cn(
              "flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[11px] font-medium transition-colors",
              autoRefresh
                ? "border-edge-strong bg-signal-green-subtle text-signal-green-text"
                : "border-edge bg-soft text-ink-secondary hover:text-ink-primary",
            )}
          >
            <Radio className="size-3.5" aria-hidden="true" />
            <span>{autoRefresh ? "Live updates on" : "Live updates off"}</span>
          </button>
          <button
            type="button"
            onClick={() => loadData()}
            aria-label="Refresh activity feed"
            className="grid size-8 place-items-center rounded-md border border-edge bg-soft text-ink-muted transition-colors hover:bg-raised hover:text-ink-primary"
          >
            <RefreshCw className={cn("size-3.5", loading && "animate-spin")} aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* Sync Orchestration and Bridge Status Card */}
      <section className="mt-6 rounded-md border border-edge-strong bg-raised/40 p-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="studio-label">Your history</p>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-[12px] text-ink-primary">
              <span className="font-medium">
                {stream.creator ? `Creator: @${stream.creator}` : "Unconfirmed identity"}
              </span>
              <span className="text-ink-muted" aria-hidden="true">|</span>
              <span className="text-ink-secondary">
                {/* No browser is named until one has reported in. This used
                    to say Brave whenever nothing was known. */}
                {summary.bridge_carrier
                  ? `Bridge: ${summary.bridge_carrier} (${summary.bridge_last_seen ? ago(summary.bridge_last_seen) : "not heard from yet"})`
                  : summary.bridge_last_seen
                    ? `Bridge last heard from ${ago(summary.bridge_last_seen)}`
                    : "The bridge has not reported in yet"}
              </span>
            </div>
            {summary.active_sync_chain && (
              <p className="mt-1 text-[11px] text-signal-orange-text">
                Sync in progress: step {summary.active_sync_chain.current_index + 1} of{" "}
                {summary.active_sync_chain.sequence.length} ({summary.active_sync_chain.sequence[summary.active_sync_chain.current_index]})
              </p>
            )}
            {syncNotice && (
              <p className="mt-1.5 text-[11px] text-ink-secondary">{syncNotice}</p>
            )}
          </div>

          <button
            type="button"
            disabled={syncing}
            onClick={() => void handleSyncAll()}
            className="flex items-center gap-1.5 rounded-md bg-signal-orange px-3 py-1.5 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-50"
          >
            {syncing ? (
              <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
            ) : (
              <Activity className="size-3.5" strokeWidth={2} aria-hidden="true" />
            )}
            <span>Sync All Activity</span>
          </button>
        </div>
      </section>

      {/* Counts as one ruled row, not four cards. Blueprint section 18
          retires the grid of KPI cards as a default, and these are a tally
          of what has been read, not performance. */}
      <dl className="mt-6 grid grid-cols-2 border-y border-edge sm:grid-cols-4">
        {[
          { label: "Your posts", value: summary.posts_count },
          { label: "Your comments", value: summary.comments_count },
          { label: "Your reactions", value: summary.reactions_count },
          { label: "Leads", value: summary.leads_count },
        ].map((item, index) => (
          <div
            key={item.label}
            className={cn("px-3 py-3", index > 0 && "sm:border-l sm:border-edge", index % 2 === 1 && "border-l border-edge")}
          >
            <dt className="studio-label">{item.label}</dt>
            <dd className="mt-1 font-mono text-[20px] tabular-nums text-ink-primary">{item.value.toLocaleString()}</dd>
          </div>
        ))}
      </dl>

      {/* Tabs */}
      <div className="mt-8 border-b border-edge">
        <div className="flex space-x-6">
          <button
            type="button"
            onClick={() => setTab("posts")}
            className={cn(
              "pb-2.5 text-[12px] font-medium transition-colors",
              tab === "posts"
                ? "border-b-2 border-signal-orange text-ink-primary"
                : "text-ink-muted hover:text-ink-primary",
            )}
          >
            Posts ({stream.recent_posts.length})
          </button>
          <button
            type="button"
            onClick={() => setTab("comments")}
            className={cn(
              "pb-2.5 text-[12px] font-medium transition-colors",
              tab === "comments"
                ? "border-b-2 border-signal-orange text-ink-primary"
                : "text-ink-muted hover:text-ink-primary",
            )}
          >
            Outbound Comments ({stream.recent_comments.length})
          </button>
          <button
            type="button"
            onClick={() => setTab("reactions")}
            className={cn(
              "pb-2.5 text-[12px] font-medium transition-colors",
              tab === "reactions"
                ? "border-b-2 border-signal-orange text-ink-primary"
                : "text-ink-muted hover:text-ink-primary",
            )}
          >
            Reactions ({stream.recent_reactions.length})
          </button>
          <button
            type="button"
            onClick={() => setTab("leads")}
            className={cn(
              "pb-2.5 text-[12px] font-medium transition-colors",
              tab === "leads"
                ? "border-b-2 border-signal-orange text-ink-primary"
                : "text-ink-muted hover:text-ink-primary",
            )}
          >
            Leads ({stream.recent_leads.length})
          </button>
          <button
            type="button"
            onClick={() => setTab("imports")}
            className={cn(
              "pb-2.5 text-[12px] font-medium transition-colors",
              tab === "imports"
                ? "border-b-2 border-signal-orange text-ink-primary"
                : "text-ink-muted hover:text-ink-primary",
            )}
          >
            Diagnostics ({stream.recent_imports.length})
          </button>
        </div>
      </div>

      {/* Tab Panels */}
      <div className="mt-6">
        {tab === "posts" && (
          <div className="flex flex-col divide-y divide-edge border-y border-edge">
            {stream.recent_posts.length === 0 ? (
              <p className="py-8 text-center text-[12px] text-ink-muted">
                No authored posts have been loaded yet. Run a sync or browse your posts in LinkedIn to ingest.
              </p>
            ) : (
              stream.recent_posts.map((post) => (
                <div key={post.activity_urn} className="py-3.5">
                  <div className="flex items-start justify-between gap-4">
                    <p className="text-[13px] leading-snug text-ink-primary">
                      {post.excerpt || "Authored post without excerpt"}
                    </p>
                    <div className="flex shrink-0 items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => copyUrn(post.activity_urn)}
                        title="Copy activity URN"
                        aria-label="Copy activity URN"
                        className="grid size-7 place-items-center rounded border border-edge bg-soft text-ink-muted hover:text-ink-primary"
                      >
                        {copiedUrn === post.activity_urn ? (
                          <Check className="size-3.5 text-signal-green-text" aria-hidden="true" />
                        ) : (
                          <Copy className="size-3.5" aria-hidden="true" />
                        )}
                      </button>
                      <button
                        type="button"
                        onClick={() => void openBridgePost(post.activity_urn)}
                        disabled={openingPost === post.activity_urn}
                        title="Open in Bridge Browser"
                        aria-label="Open in Bridge Browser"
                        className="grid size-7 place-items-center rounded border border-edge bg-soft text-ink-muted hover:text-ink-primary disabled:opacity-50"
                      >
                        {openingPost === post.activity_urn ? (
                          <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                        ) : (
                          <ExternalLink className="size-3.5" aria-hidden="true" />
                        )}
                      </button>
                    </div>
                  </div>

                  <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-ink-muted">
                    <span className="tabular-nums">Reactions: {post.reactions ?? 0}</span>
                    <span aria-hidden="true">·</span>
                    <span className="tabular-nums">Comments: {post.comments ?? 0}</span>
                    <span aria-hidden="true">·</span>
                    <span className="tabular-nums">Reposts: {post.reposts ?? 0}</span>
                    {post.impressions !== null && (
                      <>
                        <span aria-hidden="true">·</span>
                        <span className="tabular-nums">Impressions: {post.impressions}</span>
                      </>
                    )}
                    <span aria-hidden="true">·</span>
                    <span>Loaded {ago(post.last_seen_at)}</span>
                  </div>
                  {rowNote?.urn === post.activity_urn && (
                    <p role="status" className="mt-1.5 text-[11px] break-all text-ink-secondary">
                      {rowNote.text}
                    </p>
                  )}
                </div>
              ))
            )}
          </div>
        )}

        {tab === "comments" && (
          <div className="flex flex-col divide-y divide-edge border-y border-edge">
            {stream.recent_comments.length === 0 ? (
              <p className="py-8 text-center text-[12px] text-ink-muted">
                No outbound comments recorded yet.
              </p>
            ) : (
              stream.recent_comments.map((comment, index) => (
                <div key={`${comment.target_activity_urn}-${index}`} className="py-3.5">
                  <div className="flex items-baseline justify-between gap-2">
                    <p className="text-[12px] font-medium text-ink-primary">
                      Reply on {comment.target_author || "Unknown"}&apos;s post
                    </p>
                    <span className="text-[11px] text-ink-muted">{ago(comment.last_seen_at)}</span>
                  </div>
                  {comment.my_text && (
                    <blockquote className="mt-1.5 rounded bg-soft/70 px-3 py-2 text-[13px] text-ink-secondary">
                      &ldquo;{comment.my_text}&rdquo;
                    </blockquote>
                  )}
                  {comment.target_excerpt && (
                    <p className="mt-1.5 text-[11px] text-ink-muted line-clamp-2">
                      Original: {comment.target_excerpt}
                    </p>
                  )}
                </div>
              ))
            )}
          </div>
        )}

        {tab === "reactions" && (
          <div className="flex flex-col divide-y divide-edge border-y border-edge">
            {stream.recent_reactions.length === 0 ? (
              <p className="py-8 text-center text-[12px] text-ink-muted">
                No outbound reactions recorded yet.
              </p>
            ) : (
              stream.recent_reactions.map((reaction, index) => (
                <div key={`${reaction.target_activity_urn}-${index}`} className="flex items-center justify-between py-2.5">
                  <div className="flex items-center gap-2.5">
                    <span className="inline-flex items-center rounded bg-soft px-2 py-0.5 text-[11px] font-medium uppercase text-ink-primary">
                      {reaction.reaction_kind || "like"}
                    </span>
                    <span className="text-[13px] text-ink-primary">
                      {reaction.target_author || "LinkedIn Post"}
                    </span>
                  </div>
                  <span className="text-[11px] text-ink-muted">{ago(reaction.last_seen_at)}</span>
                </div>
              ))
            )}
          </div>
        )}

        {tab === "leads" && (
          <div className="flex flex-col divide-y divide-edge border-y border-edge">
            {stream.recent_leads.length === 0 ? (
              <p className="py-8 text-center text-[12px] text-ink-muted">
                No audience leads identified yet. Commenters and high-intent engagers will be recorded here automatically.
              </p>
            ) : (
              stream.recent_leads.map((lead) => (
                <div key={lead.id} className="flex items-center justify-between py-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="text-[13px] font-medium text-ink-primary">{lead.name}</p>
                      <span className="rounded bg-soft px-1.5 py-0.5 text-[10px] text-ink-muted">
                        ICP: {lead.icp_score}
                      </span>
                    </div>
                    <p className="mt-0.5 text-[11px] text-ink-secondary">
                      {lead.headline || "Professional on LinkedIn"}
                      {lead.company ? ` at ${lead.company}` : ""}
                    </p>
                  </div>
                  {onOpenLead && (
                    <button
                      type="button"
                      onClick={() => onOpenLead(lead.id)}
                      className="flex items-center gap-1 rounded border border-edge bg-soft px-2.5 py-1 text-[11px] text-ink-primary hover:bg-raised"
                    >
                      <span>View Lead</span>
                      <ArrowUpRight className="size-3" aria-hidden="true" />
                    </button>
                  )}
                </div>
              ))
            )}
          </div>
        )}

        {tab === "imports" && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[12px]">
              <thead>
                <tr className="studio-meta text-[10px] text-ink-muted">
                  <th className="py-2 font-normal">KIND</th>
                  <th className="py-2 font-normal">OUTCOME</th>
                  <th className="py-2 text-right font-normal">ITEMS</th>
                  <th className="py-2 text-right font-normal">REQUESTED</th>
                  <th className="py-2 text-right font-normal">COMPLETED</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-edge border-y border-edge">
                {stream.recent_imports.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-6 text-center text-ink-muted">
                      No background import runs recorded.
                    </td>
                  </tr>
                ) : (
                  stream.recent_imports.map((req) => (
                    <tr key={req.id}>
                      <td className="py-2 font-medium uppercase text-ink-primary">{req.kind}</td>
                      <td className="py-2">
                        <span
                          className={cn(
                            "rounded px-1.5 py-0.5 text-[10px] uppercase font-medium",
                            req.outcome === "completed"
                              ? "bg-signal-green-subtle text-signal-green-text"
                              : req.outcome === "pending"
                              ? "bg-signal-orange-subtle text-signal-orange-text"
                              : "bg-soft text-ink-secondary",
                          )}
                        >
                          {req.outcome}
                        </span>
                      </td>
                      <td className="py-2 text-right tabular-nums text-ink-secondary">
                        {req.items_seen ?? "-"}
                      </td>
                      <td className="py-2 text-right tabular-nums text-ink-muted">
                        {ago(req.requested_at)}
                      </td>
                      <td className="py-2 text-right tabular-nums text-ink-muted">
                        {req.finished_at ? ago(req.finished_at) : "-"}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </article>
  );
}
