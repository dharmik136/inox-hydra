import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowUpRight,
  Check,
  Copy,
  Download,
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
import { importEnding } from "@/lib/importOutcome";
import { reportBridge } from "@/lib/bridgeState";
import { ANY_CHANGE, useRefresh } from "@/lib/refresh";
import { formatLocalDay } from "@/lib/time";
import { cn } from "@/lib/utils";

/**
 * A stored time as the browser reads it in UTC.
 *
 * The studio stores times in UTC, and some tables store them without a zone.
 * `new Date("2026-10-20 08:55:00")` is read as local time, so a line's clock
 * and the day it is filed under disagreed by the machine's offset.
 */
function utc(iso: string): string {
  return iso.includes("T") || iso.endsWith("Z") ? iso : `${iso.replace(" ", "T")}Z`;
}

function ago(iso: string): string {
  const then = new Date(utc(iso)).getTime();
  if (Number.isNaN(then)) return iso;
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 15) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

/** A stored time as the local clock reads it, for the log's left column. */
function clockTime(iso: string): string {
  const when = new Date(utc(iso));
  if (Number.isNaN(when.getTime())) return "";
  return when.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

/** The local day a stored time falls on, as the key the log groups by. */
function dayKey(iso: string): string {
  const when = new Date(utc(iso));
  if (Number.isNaN(when.getTime())) return iso;
  return `${when.getFullYear()}-${when.getMonth() + 1}-${when.getDate()}`;
}

/**
 * A figure as Posts writes it, "4,100", and "not measured" when the bridge
 * never read it. A missing count used to read 0 here, and impressions read
 * "4100" beside Posts' "4,100".
 */
function measured(value: number | null | undefined): string {
  return value === null || value === undefined ? "not measured" : value.toLocaleString();
}

/** One line in the log: something the bridge read, and when it read it. */
interface Entry {
  key: string;
  kind: "post" | "comment" | "reaction" | "lead" | "import";
  at: string;
  /** What it was about, in the creator's own words where there are any. */
  subject: string;
  /** The figures or outcome that go with it, already in words. */
  detail: string;
  /** Orange for an import that did not read to the end; nothing otherwise. */
  tone?: "partial" | "done";
  urn?: string;
  leadId?: string;
}

const KINDS: { id: Entry["kind"] | "all"; label: string }[] = [
  { id: "all", label: "Everything" },
  { id: "post", label: "Your posts" },
  { id: "comment", label: "Your comments" },
  { id: "reaction", label: "Your reactions" },
  { id: "lead", label: "People" },
  { id: "import", label: "Imports" },
];

const KIND_LABELS: Record<Entry["kind"], string> = {
  post: "POST",
  comment: "COMMENT",
  reaction: "REACTION",
  lead: "PERSON",
  import: "IMPORT",
};

/**
 * How many of each kind the screen asks the studio for, and how many lines it
 * draws. It asked for 50 of each and drew all 250 as cards, which on three
 * years of one creator was 13,669 characters down a column 6.1 viewports
 * tall, read from a 56 KB answer that the screen's own poll re-read every
 * 2.5 seconds. A log of what just happened does not need the whole history:
 * the counts above it say how much there is, Posts and Leads hold the rest.
 */
const ASK_PER_KIND = 12;
const LINES = 24;

/**
 * Activity: what the bridge read, as a log.
 *
 * One list, newest first, grouped by the day it happened on, one line each,
 * filtered by kind rather than split across five panels of cards. The two
 * controls that only make sense on a post of your own (copy its URN, open it
 * in the bridge browser) stay on its line.
 */
export function ActivitySurface({
  onOpenLead,
}: {
  onOpenLead?: (leadId: string) => void;
}) {
  const [stream, setStream] = useState<ActivityStreamData | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  /** When the studio last answered, the one thing a refresh measures. */
  const [loadedAt, setLoadedAt] = useState<Date | null>(null);
  const [kind, setKind] = useState<Entry["kind"] | "all">("all");
  const [copiedUrn, setCopiedUrn] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncNotice, setSyncNotice] = useState<string | null>(null);
  const [openingPost, setOpeningPost] = useState<string | null>(null);
  /** What the last action on a post row came to, shown under that row. */
  const [rowNote, setRowNote] = useState<{ urn: string; text: string } | null>(null);

  const loadData = useCallback(async () => {
    try {
      const result = await fetchActivityStream(ASK_PER_KIND);
      setStream(result);
      reportBridge(result.summary.bridge_connected);
      setLoadedAt(new Date());
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

  // Every 2.5 seconds while auto refresh is on and the window is in view. It
  // used to poll a hidden tab at the same rate for as long as it stayed open,
  // the largest steady load the interface put on the database while the
  // bridge was writing. Also read on coming back, and after an outage.
  useRefresh(loadData, autoRefresh ? 2500 : undefined, autoRefresh ? ANY_CHANGE : undefined);

  // One list out of the five the studio answers with, newest first. Built
  // from the answer alone, so a kind the creator filters to is already here
  // and no filter costs another read.
  const entries = useMemo<Entry[]>(() => {
    if (!stream) return [];
    const all: Entry[] = [];
    for (const post of stream.recent_posts) {
      const figures = [`Reactions: ${measured(post.reactions)}`, `Comments: ${measured(post.comments)}`];
      if (post.reposts) figures.push(`Reposts: ${measured(post.reposts)}`);
      if (post.impressions !== null) figures.push(`Impressions: ${measured(post.impressions)}`);
      all.push({
        key: `post-${post.activity_urn}`,
        kind: "post",
        at: post.last_seen_at,
        subject: post.excerpt || "Authored post without excerpt",
        detail: figures.join(" · "),
        urn: post.activity_urn,
      });
    }
    stream.recent_comments.forEach((comment, index) => {
      all.push({
        key: `comment-${comment.target_activity_urn}-${index}`,
        kind: "comment",
        at: comment.last_seen_at,
        subject: comment.my_text || comment.target_excerpt || "A comment of yours",
        detail: `On ${comment.target_author || "an unnamed author"}’s post`,
      });
    });
    stream.recent_reactions.forEach((reaction, index) => {
      all.push({
        key: `reaction-${reaction.target_activity_urn}-${index}`,
        kind: "reaction",
        at: reaction.last_seen_at,
        subject: reaction.target_excerpt || "A post you reacted to",
        detail: `${(reaction.reaction_kind || "like").toUpperCase()} on ${reaction.target_author || "an unnamed author"}’s post`,
      });
    });
    for (const lead of stream.recent_leads) {
      all.push({
        key: `lead-${lead.id}`,
        kind: "lead",
        at: lead.created_at,
        subject: lead.name,
        detail: [lead.headline, lead.company ? `at ${lead.company}` : "", `ICP ${lead.icp_score}`]
          .filter(Boolean)
          .join(" · "),
        leadId: lead.id,
      });
    }
    for (const request of stream.recent_imports) {
      // Green only for an import read to the end, orange for one that was
      // not: importEnding is the one place that decides which.
      const ending = importEnding(request);
      all.push({
        key: `import-${request.id}`,
        kind: "import",
        at: request.finished_at || request.started_at || request.requested_at,
        subject: `${request.kind} import: ${ending.label.toLowerCase()}`,
        detail: request.items_seen === null ? "Items: not measured" : `Items: ${request.items_seen.toLocaleString()}`,
        tone: ending.tone === "done" ? "done" : ending.tone === "partial" ? "partial" : undefined,
      });
    }
    return all.sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));
  }, [stream]);

  const shown = useMemo(() => {
    const picked = kind === "all" ? entries : entries.filter((entry) => entry.kind === kind);
    return { lines: picked.slice(0, LINES), total: picked.length };
  }, [entries, kind]);

  // The lines of one day, under that day's heading.
  const days = useMemo(() => {
    const grouped: { key: string; label: string; lines: Entry[] }[] = [];
    for (const entry of shown.lines) {
      const key = dayKey(entry.at);
      const last = grouped[grouped.length - 1];
      if (last && last.key === key) last.lines.push(entry);
      else grouped.push({ key, label: formatLocalDay(utc(entry.at)), lines: [entry] });
    }
    return grouped;
  }, [shown.lines]);

  async function handleSyncAll() {
    setSyncing(true);
    setSyncNotice(null);
    try {
      const response = await syncAllActivity();
      setSyncNotice(response.message);
      await loadData();
    } catch (err) {
      setSyncNotice(err instanceof Error ? err.message : "The import could not be started.");
    } finally {
      setSyncing(false);
    }
  }

  // The outcome is shown under the row, success or failure. Discarding the
  // error left a click that changed nothing on screen when no browser opened.
  async function openBridgePost(activityUrn: string) {
    setOpeningPost(activityUrn);
    setRowNote(null);
    try {
      const postUrl = `https://www.linkedin.com/feed/update/${activityUrn}/`;
      const launched = await launchBridge("auto", postUrl);
      setRowNote({ urn: activityUrn, text: launched.message || "Opened in the bridge browser." });
    } catch (caught) {
      setRowNote({
        urn: activityUrn,
        text: caught instanceof Error ? caught.message : "The browser could not be opened.",
      });
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
            The studio is not answering, or refused this page&apos;s request. Check that it is still running, then retry.
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
          <span className="studio-meta text-[11px]">LOADING ACTIVITY</span>
        </div>
      </div>
    );
  }

  if (!stream) return null;

  const { summary } = stream;
  const bridgeOnline = summary.bridge_connected;

  return (
    <div className="px-6 py-6 lg:px-8">
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
              {bridgeOnline ? "Bridge connected" : "Bridge not connected"}
            </span>
          </div>
          <h1 className="studio-title mt-1.5">What the bridge has read</h1>
          <p className="mt-1 max-w-[86ch] text-[12px] leading-snug text-ink-secondary">
            The newest {LINES} things the browser extension read from your LinkedIn, kept on this machine. The counts
            are everything it has read; Posts and Leads hold the rest.
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
            <span>{autoRefresh ? "Auto refresh on" : "Auto refresh off"}</span>
          </button>
          {/* This said "Live updates on" while the studio was down and the
              list was stale. It says when the studio last answered instead,
              and that it has stopped when it has. */}
          {loadedAt && (
            <span className={cn("studio-meta text-[10px]", failed ? "text-signal-orange-text" : "text-ink-muted")}>
              {failed
                ? `Studio not answering. Updated ${loadedAt.toLocaleTimeString()}`
                : `Updated ${loadedAt.toLocaleTimeString()}`}
            </span>
          )}
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

      {/* The bridge, the identity and the one import control, on one line
          rather than in a card of its own. */}
      <section className="mt-3 flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-y border-edge py-2">
        <div className="flex flex-wrap items-center gap-2 text-[12px] text-ink-primary">
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
          {summary.active_sync_chain && (
            <span className="text-[11px] text-signal-orange-text">
              Import in progress: step {summary.active_sync_chain.current_index + 1} of{" "}
              {summary.active_sync_chain.sequence.length} ({summary.active_sync_chain.sequence[summary.active_sync_chain.current_index]})
            </span>
          )}
          {syncNotice && <span className="text-[11px] text-ink-secondary">{syncNotice}</span>}
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
            <Download className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
          )}
          <span>Import your history</span>
        </button>
      </section>

      {/* Counts as one ruled row, not four cards. Blueprint section 18
          retires the grid of KPI cards as a default, and these are a tally
          of what has been read, not performance. */}
      <dl className="mt-3 grid grid-cols-2 border-b border-edge sm:grid-cols-4">
        {[
          { label: "Your posts", value: summary.posts_count },
          { label: "Your comments", value: summary.comments_count },
          { label: "Your reactions", value: summary.reactions_count },
          { label: "Leads", value: summary.leads_count },
        ].map((item, index) => (
          <div
            key={item.label}
            className={cn("px-3 py-2", index > 0 && "sm:border-l sm:border-edge", index % 2 === 1 && "border-l border-edge")}
          >
            <dt className="studio-label">{item.label}</dt>
            <dd className="mt-0.5 font-mono text-[17px] tabular-nums text-ink-primary">{item.value.toLocaleString()}</dd>
          </div>
        ))}
      </dl>

      {/* One log, filtered by kind. These were five tabs of fifty cards. */}
      <div className="mt-3 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
        <div className="flex flex-wrap gap-1">
          {KINDS.map((option) => {
            const count = option.id === "all" ? entries.length : entries.filter((entry) => entry.kind === option.id).length;
            return (
              <button
                key={option.id}
                type="button"
                onClick={() => setKind(option.id)}
                aria-pressed={kind === option.id}
                className={cn(
                  "rounded-full border px-2.5 py-0.5 text-[11px] transition-colors",
                  kind === option.id
                    ? "border-edge-strong bg-soft text-ink-primary"
                    : "border-edge text-ink-muted hover:text-ink-secondary",
                )}
              >
                {option.label} ({count})
              </button>
            );
          })}
        </div>
        <p className="studio-meta text-[10px] text-ink-muted">
          {shown.total > shown.lines.length
            ? `NEWEST ${shown.lines.length} OF ${shown.total.toLocaleString()} READ IN THIS ANSWER`
            : `${shown.total.toLocaleString()} ${shown.total === 1 ? "LINE" : "LINES"}`}
        </p>
      </div>

      {shown.lines.length === 0 ? (
        <p className="border-y border-edge py-8 text-center text-[12px] text-ink-muted">
          Nothing of this kind has been read yet. Press Import your history, or open your LinkedIn in the bridge
          browser.
        </p>
      ) : (
        <div className="mt-2 border-t border-edge">
          {days.map((day) => (
            <section key={day.key}>
              <h2 className="studio-meta sticky top-0 bg-ink py-1 text-[10px] text-ink-muted">{day.label.toUpperCase()}</h2>
              <ul className="flex flex-col divide-y divide-edge border-y border-edge">
                {day.lines.map((entry) => (
                  <li key={entry.key} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-1.5">
                    <span className="studio-meta w-12 shrink-0 text-[10px] tabular-nums text-ink-muted">
                      {clockTime(entry.at)}
                    </span>
                    <span
                      className={cn(
                        "studio-meta w-[72px] shrink-0 text-[10px]",
                        entry.tone === "partial"
                          ? "text-signal-orange-text"
                          : entry.tone === "done"
                            ? "text-signal-green-text"
                            : "text-ink-muted",
                      )}
                    >
                      {KIND_LABELS[entry.kind]}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-[13px] text-ink-primary">{entry.subject}</span>
                    <span className="shrink-0 text-[11px] text-ink-muted">{entry.detail}</span>
                    {entry.urn && (
                      <span className="flex shrink-0 items-center gap-1">
                        <button
                          type="button"
                          onClick={() => copyUrn(entry.urn as string)}
                          title="Copy activity URN"
                          aria-label="Copy activity URN"
                          className="grid size-6 place-items-center rounded border border-edge bg-soft text-ink-muted hover:text-ink-primary"
                        >
                          {copiedUrn === entry.urn ? (
                            <Check className="size-3 text-signal-green-text" aria-hidden="true" />
                          ) : (
                            <Copy className="size-3" aria-hidden="true" />
                          )}
                        </button>
                        <button
                          type="button"
                          onClick={() => void openBridgePost(entry.urn as string)}
                          disabled={openingPost === entry.urn}
                          title="Open in Bridge Browser"
                          aria-label="Open in Bridge Browser"
                          className="grid size-6 place-items-center rounded border border-edge bg-soft text-ink-muted hover:text-ink-primary disabled:opacity-50"
                        >
                          {openingPost === entry.urn ? (
                            <Loader2 className="size-3 animate-spin" aria-hidden="true" />
                          ) : (
                            <ExternalLink className="size-3" aria-hidden="true" />
                          )}
                        </button>
                      </span>
                    )}
                    {entry.leadId && onOpenLead && (
                      <button
                        type="button"
                        onClick={() => onOpenLead(entry.leadId as string)}
                        className="flex shrink-0 items-center gap-1 rounded border border-edge bg-soft px-2 py-0.5 text-[11px] text-ink-primary hover:bg-raised"
                      >
                        <span>View Lead</span>
                        <ArrowUpRight className="size-3" aria-hidden="true" />
                      </button>
                    )}
                    {entry.urn && rowNote && rowNote.urn === entry.urn && (
                      <p role="status" className="w-full text-[11px] break-all text-ink-secondary">
                        {rowNote.text}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
