import { useCallback, useEffect, useRef, useState } from "react";
import { ExternalLink, Loader2 } from "lucide-react";
import {
  fetchReplies,
  launchBridge,
  markReplyAnswered,
  unmarkReplyAnswered,
  type ReplyComment,
  type ReplyPostGroup,
  type RepliesPage,
  type RepliesView,
} from "@/lib/api";
import { useRefresh } from "@/lib/refresh";
import { formatLocal, formatLocalDay } from "@/lib/time";
import { cn } from "@/lib/utils";

/**
 * Replies: who commented on my posts that I have not answered, oldest seen
 * first?
 *
 * Today names five people. Every comment on the creator's own posts was held
 * and shown nowhere as a set: one person at a time in the dossier, one post at
 * a time in Posts. This is the whole list for the window, grouped by post, the
 * comment that has waited longest first, in the commenter's own words.
 *
 * Two things the screen will not claim. When someone commented: the studio
 * records when it first saw the comment, which is when the bridge read the
 * page, so every time here is "seen by the studio". And whether the creator
 * replied: LinkedIn does not tell the bridge, so "answered" is the creator's
 * own mark, which they set and can take back.
 *
 * Ordered by when each comment was first seen, never by anyone's score.
 */
const WINDOWS = [7, 14, 30] as const;

/** Read again while open, so a comment the bridge reads in the other window arrives. */
const POLL_MS = 60_000;

export function RepliesSurface({
  onOpenLead,
  onOpenSetup,
}: {
  onOpenLead?: (leadId: string) => void;
  onOpenSetup?: () => void;
} = {}) {
  const [days, setDays] = useState<number>(14);
  const [view, setView] = useState<RepliesView>("waiting");
  const [page, setPage] = useState<RepliesPage | null>(null);
  /** The comments shown so far, by post, across every page read. */
  const [groups, setGroups] = useState<ReplyPostGroup[]>([]);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);
  /** The last comment marked here, so the mark can be taken back. */
  const [lastMarked, setLastMarked] = useState<ReplyComment | null>(null);
  const shown = useRef(0);

  // The first page, or as many comments as are already on screen, so a read
  // while the creator works down the list does not take away what they loaded.
  const load = useCallback(async () => {
    try {
      const first = await fetchReplies(days, view, 0);
      let merged = first.posts;
      let last = first;
      while (last.next_offset !== null && countOf(merged) < shown.current) {
        last = await fetchReplies(days, view, last.next_offset);
        merged = mergeGroups(merged, last.posts);
      }
      setPage({ ...first, next_offset: last.next_offset });
      setGroups(merged);
      shown.current = countOf(merged);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, [days, view]);

  useEffect(() => {
    shown.current = 0;
    setPage(null);
    void load();
  }, [load]);
  useRefresh(load, POLL_MS);

  async function more() {
    if (!page || page.next_offset === null) return;
    setBusy("more");
    try {
      const next = await fetchReplies(days, view, page.next_offset);
      setGroups((current) => {
        const merged = mergeGroups(current, next.posts);
        shown.current = countOf(merged);
        return merged;
      });
      setPage((current) => (current ? { ...current, next_offset: next.next_offset } : next));
    } catch (caught) {
      setNote({ text: caught instanceof Error ? caught.message : "The next comments could not be read.", error: true });
    } finally {
      setBusy(null);
    }
  }

  async function mark(comment: ReplyComment) {
    setBusy(keyOf(comment));
    setNote(null);
    try {
      await markReplyAnswered(comment);
      setLastMarked(comment);
      shown.current = Math.max(0, shown.current - 1);
      await load();
    } catch (caught) {
      setNote({ text: caught instanceof Error ? caught.message : "The mark could not be saved.", error: true });
    } finally {
      setBusy(null);
    }
  }

  async function unmark(comment: ReplyComment) {
    setBusy(keyOf(comment));
    setNote(null);
    try {
      await unmarkReplyAnswered(comment);
      setLastMarked(null);
      await load();
    } catch (caught) {
      setNote({ text: caught instanceof Error ? caught.message : "The mark could not be taken back.", error: true });
    } finally {
      setBusy(null);
    }
  }

  async function openPost(url: string) {
    setBusy(url);
    setNote(null);
    try {
      setNote({ text: (await launchBridge("auto", url)).message || "Opened in the bridge browser.", error: false });
    } catch (caught) {
      setNote({ text: caught instanceof Error ? caught.message : "The browser could not be opened.", error: true });
    } finally {
      setBusy(null);
    }
  }

  if (failed && !page) {
    return (
      <div className="grid h-full place-items-center px-8">
        <div className="max-w-[44ch] text-center">
          <p className="studio-label text-signal-orange-text">REPLIES ARE UNAVAILABLE</p>
          <p className="mt-2 text-[13px] text-ink-muted">
            The studio is not answering, or refused this screen&apos;s request. Check that it is still running, then retry.
          </p>
          <button
            type="button"
            onClick={() => void load()}
            className="mt-4 rounded-md border border-edge bg-soft px-3 py-1.5 text-[12px] font-medium text-ink-primary hover:bg-raised"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!page) {
    return (
      <div className="grid h-full place-items-center px-8">
        <div className="flex items-center gap-2 text-ink-muted">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          <span className="studio-meta text-[11px]">READING THE COMMENTS ON YOUR POSTS</span>
        </div>
      </div>
    );
  }

  const { counts, window } = page;

  return (
    // tabIndex, because a long list scrolls and a region that scrolls with
    // nothing focusable in it cannot be scrolled by keyboard.
    <div className="px-6 py-6 lg:px-8" tabIndex={0} aria-labelledby="replies-title">
      <header className="flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
        <div>
          <p className="studio-label">Replies</p>
          <h1 id="replies-title" className="studio-title mt-1">Who is waiting on a reply</h1>
        </div>
        <p className="max-w-[64ch] text-[12px] leading-snug text-ink-secondary">
          Comments on your posts that the studio first saw in the {window.label}, from people you have not answered,
          the longest waiting first. A time here is when the studio saw the comment, which is when the bridge read the
          page. Whether you replied is not something the bridge can read, so Answered is your own mark.
        </p>
      </header>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="Which comments" className="flex items-center gap-1">
          {(["waiting", "answered"] as const).map((candidate) => (
            <button
              key={candidate}
              type="button"
              aria-pressed={view === candidate}
              onClick={() => setView(candidate)}
              className={cn(
                "rounded-md px-3 py-1.5 text-[12px] font-medium transition-colors",
                view === candidate ? "bg-soft text-ink-primary" : "text-ink-muted hover:text-ink-secondary",
              )}
            >
              {candidate === "waiting" ? "Waiting" : "Marked answered"}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-[12px] text-ink-secondary">
          Window
          <select
            value={days}
            onChange={(event) => setDays(Number(event.target.value))}
            className="rounded-md border border-edge bg-canvas px-2 py-1 text-[12px] text-ink-primary"
          >
            {WINDOWS.map((choice) => (
              <option key={choice} value={choice}>
                last {choice} days
              </option>
            ))}
          </select>
        </label>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-px border border-edge bg-edge sm:grid-cols-4">
        <Figure label={`Comments waiting, ${window.label}`} value={counts.waiting.toLocaleString()} />
        <Figure label="People waiting" value={counts.people.toLocaleString()} />
        <Figure label="Posts they are on" value={counts.posts.toLocaleString()} />
        <Figure label="Marked answered, last 7 days" value={counts.answered_last_7_days.toLocaleString()} />
      </dl>

      {(note || lastMarked) && (
        <div role="status" className="mt-3 flex flex-wrap items-baseline gap-x-3 text-[12px] leading-snug">
          {lastMarked && view === "waiting" && (
            <span className="text-ink-secondary">
              Marked {lastMarked.name}&apos;s comment answered.{" "}
              <button
                type="button"
                onClick={() => void unmark(lastMarked)}
                disabled={busy !== null}
                className="underline decoration-edge-strong underline-offset-2 hover:text-ink-primary disabled:opacity-40"
              >
                Undo
              </button>
            </span>
          )}
          {note && <span className={note.error ? "text-signal-orange-text" : "text-ink-muted"}>{note.text}</span>}
        </div>
      )}

      {!page.identity_known ? (
        <div className="mt-6 max-w-[60ch]">
          <p className="text-[13px] leading-relaxed text-ink-secondary">
            Once you confirm your profile in Setup, the comments people leave on your posts appear here.
          </p>
          {onOpenSetup && (
            <button
              type="button"
              onClick={onOpenSetup}
              className="mt-3 rounded-md bg-signal-orange px-3 py-1.5 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110"
            >
              Go to Setup
            </button>
          )}
        </div>
      ) : groups.length === 0 ? (
        <p className="mt-6 max-w-[64ch] text-[13px] leading-relaxed text-ink-secondary">
          {view === "waiting"
            ? `Nobody from the ${window.label} is waiting on a reply. ${answeredSentence(counts.answered_last_7_days)}`
            : `You have not marked any comment from the ${window.label} answered.`}
        </p>
      ) : (
        <div className="mt-4 grid items-start gap-4 xl:grid-cols-2">
          {groups.map((group) => (
            <section key={group.post_id} className="rounded-md border border-edge" aria-label={postName(group)}>
              <div className="flex items-start justify-between gap-3 border-b border-edge px-3 py-2">
                <div className="min-w-0">
                  <p className="line-clamp-2 text-[13px] leading-snug text-ink-primary">{postName(group)}</p>
                  <p className="studio-meta mt-0.5 text-[10px] text-ink-muted">
                    {group.published_at ? `PUBLISHED ${formatLocalDay(group.published_at).toUpperCase()} · ` : ""}
                    {group.waiting.toLocaleString()} WAITING · {group.answered.toLocaleString()} MARKED ANSWERED
                  </p>
                </div>
                {group.url && (
                  <button
                    type="button"
                    onClick={() => void openPost(group.url as string)}
                    disabled={busy !== null}
                    className="flex shrink-0 items-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
                  >
                    {busy === group.url ? (
                      <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                    ) : (
                      <ExternalLink className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                    )}
                    Open the post
                  </button>
                )}
              </div>
              <ul className="flex flex-col divide-y divide-edge">
                {group.comments.map((comment) => (
                  <li key={keyOf(comment)} className="px-3 py-2">
                    <div className="flex items-baseline justify-between gap-3">
                      <div className="min-w-0">
                        {onOpenLead ? (
                          <button
                            type="button"
                            onClick={() => onOpenLead(comment.lead_id)}
                            className="text-left text-[13px] font-medium text-ink-primary underline decoration-edge-strong underline-offset-2 hover:text-signal-orange-text"
                          >
                            {comment.name}
                          </button>
                        ) : (
                          <span className="text-[13px] font-medium text-ink-primary">{comment.name}</span>
                        )}
                        {comment.headline && <p className="truncate text-[11px] text-ink-muted">{comment.headline}</p>}
                      </div>
                      {view === "waiting" ? (
                        <button
                          type="button"
                          onClick={() => void mark(comment)}
                          disabled={busy !== null}
                          // Named for the comment, because every row has one
                          // and a list of controls all called "Answered" says
                          // nothing about which is which.
                          aria-label={`Answered, ${comment.name}'s comment`}
                          className="shrink-0 rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
                        >
                          {busy === keyOf(comment) ? "Marking" : "Answered"}
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => void unmark(comment)}
                          disabled={busy !== null}
                          aria-label={`Not answered, ${comment.name}'s comment`}
                          className="shrink-0 rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
                        >
                          Not answered
                        </button>
                      )}
                    </div>
                    {comment.comment_text ? (
                      <p className="mt-1 line-clamp-4 text-[13px] leading-snug text-ink-secondary">
                        &ldquo;{comment.comment_text}&rdquo;
                      </p>
                    ) : (
                      <p className="mt-1 text-[12px] text-ink-muted">The bridge read no words in this comment.</p>
                    )}
                    <p className="studio-meta mt-1 text-[10px] text-ink-muted">
                      SEEN BY THE STUDIO {ago(comment.seen_at)}
                      {comment.marked_at ? ` · MARKED ANSWERED ${formatLocal(comment.marked_at).toUpperCase()}` : ""}
                    </p>
                  </li>
                ))}
                {group.comments.length < group.in_view && (
                  <li className="px-3 py-1.5 text-[11px] text-ink-muted">
                    {group.comments.length} of {group.in_view} on this post shown; the rest follow below.
                  </li>
                )}
              </ul>
            </section>
          ))}
        </div>
      )}

      {page.next_offset !== null && groups.length > 0 && (
        <div className="mt-4 flex items-center gap-3">
          <button
            type="button"
            onClick={() => void more()}
            disabled={busy !== null}
            className="rounded-md border border-edge px-3 py-1.5 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
          >
            {busy === "more" ? "Reading" : "Show more"}
          </button>
          <span className="studio-meta text-[10px] text-ink-muted">
            {countOf(groups).toLocaleString()} OF {page.total.toLocaleString()} SHOWN
          </span>
        </div>
      )}
    </div>
  );
}

function keyOf(comment: Pick<ReplyComment, "lead_id" | "post_urn" | "comment_key">): string {
  return `${comment.lead_id}|${comment.post_urn}|${comment.comment_key}`;
}

function countOf(groups: ReplyPostGroup[]): number {
  return groups.reduce((sum, group) => sum + group.comments.length, 0);
}

/** A later page's groups joined to the ones on screen, one card per post. */
function mergeGroups(current: ReplyPostGroup[], next: ReplyPostGroup[]): ReplyPostGroup[] {
  const merged = current.map((group) => ({ ...group, comments: [...group.comments] }));
  for (const group of next) {
    const found = merged.find((existing) => existing.post_id === group.post_id);
    if (found) found.comments.push(...group.comments.filter((c) => !found.comments.some((d) => keyOf(d) === keyOf(c))));
    else merged.push(group);
  }
  return merged;
}

function postName(group: ReplyPostGroup): string {
  return group.excerpt ?? "A post of yours the studio does not hold the text of";
}

function answeredSentence(count: number): string {
  if (count === 0) return "You have marked none answered in the last 7 days.";
  return `You marked ${count.toLocaleString()} answered in the last 7 days.`;
}

/** How long ago the studio saw it, from a stored UTC time that may carry no zone. */
function ago(stamp: string): string {
  const then = new Date(stamp.includes("T") || stamp.endsWith("Z") ? stamp : `${stamp.replace(" ", "T")}Z`).getTime();
  if (Number.isNaN(then)) return stamp;
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 90) return "JUST NOW";
  if (seconds < 5400) return `${Math.round(seconds / 60)} MIN AGO`;
  if (seconds < 172800) return `${Math.round(seconds / 3600)} H AGO`;
  return `${Math.round(seconds / 86400)} DAYS AGO`;
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-ink px-3 py-1.5">
      <dt className="studio-meta text-[10px] text-ink-muted">{label.toUpperCase()}</dt>
      <dd className="text-[14px] tabular-nums text-ink-primary">{value}</dd>
    </div>
  );
}
