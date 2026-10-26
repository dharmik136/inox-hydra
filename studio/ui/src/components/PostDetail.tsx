import { useEffect, useRef, useState } from "react";
import { ExternalLink, Loader2, X } from "lucide-react";
import { fetchPostDetail, fetchPostEngagers, launchBridge, type PostDetail as PostDetailData, type PostEngager } from "@/lib/api";
import { useModalFocus } from "@/lib/modalFocus";
import { ratioTone } from "@/lib/results";
import { formatLocalDay } from "@/lib/time";
import { cn } from "@/lib/utils";

/**
 * One post, opened from the Posts table rather than rendered inline.
 *
 * The table used to render every post's full text and every one of its
 * people down a column 176 screens tall. The table now shows a row; this is
 * where the whole post lives, read once, when a creator asks for it.
 */
export function PostDetail({
  activityUrn,
  onClose,
  onOpenLead,
}: {
  activityUrn: string;
  onClose: () => void;
  onOpenLead: (leadId: string) => void;
}) {
  const [post, setPost] = useState<PostDetailData | null>(null);
  const [engagers, setEngagers] = useState<PostEngager[] | null>(null);
  const [engagersMessage, setEngagersMessage] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  useModalFocus(panelRef, true, onClose);

  useEffect(() => {
    let live = true;
    setPost(null);
    setEngagers(null);
    setFailed(false);
    fetchPostDetail(activityUrn)
      .then((data) => live && setPost(data))
      .catch(() => live && setFailed(true));
    fetchPostEngagers(activityUrn)
      .then((data) => {
        if (!live) return;
        setEngagers(data.engagers);
        setEngagersMessage(data.message ?? null);
      })
      .catch(() => live && setEngagers([]));
    return () => {
      live = false;
    };
  }, [activityUrn]);

  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-canvas/60 p-4" onClick={onClose}>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Post detail"
        onClick={(event) => event.stopPropagation()}
        className="flex max-h-[85vh] w-full max-w-[72ch] flex-col rounded-lg border border-edge bg-raised shadow-2xl"
      >
        <div className="flex shrink-0 items-center gap-2 border-b border-edge px-5 py-3">
          <p className="studio-label flex-1">Post</p>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close post detail"
            className="grid size-7 place-items-center rounded-md text-ink-muted transition-colors hover:bg-soft hover:text-ink-primary"
          >
            <X className="size-4" strokeWidth={1.75} aria-hidden="true" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {failed ? (
            <p className="studio-meta text-ink-muted">THIS POST COULD NOT BE READ. IS THE STUDIO RUNNING?</p>
          ) : !post ? (
            <p className="studio-meta flex items-center gap-2 text-ink-muted">
              <Loader2 className="size-3 animate-spin" aria-hidden="true" />
              READING THIS POST
            </p>
          ) : (
            <>
              <p className="studio-meta text-[10px] text-ink-muted">
                {formatLocalDay(post.published_at, "Date unknown").toUpperCase()}
                {!post.settled && " · STILL GROWING"}
              </p>
              <p className="mt-2 whitespace-pre-wrap text-[13px] leading-relaxed text-ink-primary">{post.text || "(no text)"}</p>

              <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 border-y border-edge py-3">
                <Figure label="impressions" value={post.impressions} ratio={post.against_usual?.impressions} />
                <Figure label="reactions" value={post.reactions} ratio={post.against_usual?.reactions} />
                <Figure label="comments" value={post.comments} ratio={post.against_usual?.comments} />
                <Figure label="reposts" value={post.reposts} />
                <span className="studio-meta text-[10px] tabular-nums text-ink-secondary">
                  {post.engagement_rate === null
                    ? post.engagement_rate_note ?? "rate not measured"
                    : `${post.engagement_rate}% ENGAGEMENT`}
                </span>
              </div>

              {post.reach_and_response && (
                <p className="mt-3 text-[12px] leading-relaxed text-ink-secondary">
                  Reach and response, together: <span className="text-ink-primary">{post.reach_and_response.shape}</span>.
                  Reach sat at the {post.reach_and_response.reach.percentile}th percentile of your own posts read at a
                  comparable age, response at the {post.reach_and_response.response.percentile}th, among{" "}
                  {post.reach_and_response.posts_compared} posts compared.
                </p>
              )}

              {post.figures_source && (
                <p className="studio-meta mt-2 text-[10px] text-ink-muted">
                  READ FROM {post.figures_source.replace(/_/g, " ").toUpperCase()}
                  {post.figures_read_at ? ` · ${formatLocalDay(post.figures_read_at, "").toUpperCase()}` : ""}
                </p>
              )}

              {post.url && <OpenThePost url={post.url} />}

              <section className="mt-5">
                <p className="studio-label mb-2">Who engaged</p>
                {engagers === null ? (
                  <p className="studio-meta text-ink-muted">READING WHO ENGAGED</p>
                ) : engagers.length === 0 ? (
                  <p className="studio-meta text-[10px] leading-snug text-ink-muted">
                    {engagersMessage?.toUpperCase() ?? "NOBODY CAPTURED FROM THIS POST YET."}
                  </p>
                ) : (
                  <ul className="flex flex-col gap-2">
                    {engagers.map((person) => (
                      <li key={`${person.id}-${person.interaction_type ?? ""}`}>
                        <button
                          type="button"
                          onClick={() => onOpenLead(person.id)}
                          className="flex w-full flex-col items-start text-left text-[12px] text-ink-secondary hover:text-ink-primary"
                        >
                          <span>
                            {person.full_name || person.name || "Unnamed"}
                            {person.company && <span className="text-ink-muted"> at {person.company}</span>}
                            <span className="studio-meta ml-2 text-[10px] text-ink-muted">
                              {(person.interaction_type ?? "reacted").toUpperCase()}
                            </span>
                          </span>
                          {person.comment_text && (
                            <span className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-ink-muted">
                              {person.comment_text}
                            </span>
                          )}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </>
          )}
        </div>
      </div>
    </div>
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
            ratioTone(ratio),
          )}
        >
          ({ratio.toFixed(1)}x)
        </span>
      )}
    </span>
  );
}

/** Opens the post in the bridge browser, and says what came of it. */
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
        className="mt-3 flex items-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-50"
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
