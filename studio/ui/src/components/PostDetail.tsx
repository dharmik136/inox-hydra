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
  /** Opens the person in Leads, with this post, so a stage change made there records it. */
  onOpenLead: (leadId: string, fromPost?: string) => void;
}) {
  const [post, setPost] = useState<PostDetailData | null>(null);
  const [engagers, setEngagers] = useState<PostEngager[] | null>(null);
  const [engagersMessage, setEngagersMessage] = useState<string | null>(null);
  // People kept only as counts: the reactors the retention job folded. The
  // row's people count includes them and this list cannot name them.
  const [foldedPeople, setFoldedPeople] = useState(0);
  const [failed, setFailed] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  useModalFocus(panelRef, true, onClose);

  useEffect(() => {
    let live = true;
    setPost(null);
    setEngagers(null);
    setFoldedPeople(0);
    setFailed(false);
    fetchPostDetail(activityUrn)
      .then((data) => live && setPost(data))
      .catch(() => live && setFailed(true));
    fetchPostEngagers(activityUrn)
      .then((data) => {
        if (!live) return;
        setEngagers(data.engagers);
        setEngagersMessage(data.message ?? null);
        setFoldedPeople(data.folded_people);
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
              {/* A figure LinkedIn wrote as 12K is about 12,000, and the detail says so. */}
              {post.approximate && post.approximate.length > 0 && <p className="studio-meta mt-1 text-[10px] text-ink-muted">ABOUT: {post.approximate.join(", ").toUpperCase()}, WHICH LINKEDIN MAY HAVE ROUNDED (SUCH AS 12K)</p>}

              {/* Two facts the bridge reads beside the figures (track 5): when
                  the post was first seen marked edited on your Activity tab,
                  and a video's watch time from its analytics page, each with
                  when it was read. A video whose watch time was never read
                  says so; any other post has none to read. */}
              {post.edited_first_seen_at && (
                <p className="studio-meta mt-1 text-[10px] text-ink-muted">
                  MARKED EDITED ON LINKEDIN, FIRST SEEN {formatLocalDay(post.edited_first_seen_at, "").toUpperCase()}
                </p>
              )}
              <WatchTime post={post} />
              <TwoDay post={post} />

              {post.url && <OpenThePost url={post.url} />}

              <Readings post={post} />

              <section className="mt-5">
                <p className="studio-label mb-2">Who engaged</p>
                {engagers === null ? (
                  <p className="studio-meta text-ink-muted">READING WHO ENGAGED</p>
                ) : engagers.length === 0 && foldedPeople === 0 ? (
                  <p className="studio-meta text-[10px] leading-snug text-ink-muted">
                    {engagersMessage?.toUpperCase() ?? "NOBODY CAPTURED FROM THIS POST YET."}
                  </p>
                ) : (
                  <>
                    {engagers.length > 0 && (
                      <ul className="flex flex-col gap-2">
                        {engagers.map((person) => (
                          <li key={`${person.id}-${person.interaction_type ?? ""}`}>
                            <button
                              type="button"
                              onClick={() => onOpenLead(person.id, activityUrn)}
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
                    {/* Every person folded is still a person: a post whose every
                        reactor was folded is not shown as having nobody. */}
                    {foldedPeople > 0 && (
                      <p className="studio-meta mt-2 text-[10px] leading-snug text-ink-muted">
                        {engagers.length > 0
                          ? `${foldedPeople} MORE`
                          : `${foldedPeople} ${foldedPeople === 1 ? "PERSON" : "PEOPLE"}`}{" "}
                        FROM REACTIONS OVER 24 MONTHS OLD, KEPT AS A COUNT WITHOUT NAMES (STORAGE AND PRIVACY)
                      </p>
                    )}
                  </>
                )}
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/** The pages a reading comes from, in the words the rest of the studio uses. */
const PAGES: Record<string, string> = {
  activity_page: "your Activity page",
  post_analytics: "its analytics page",
  voyager_network: "network reading",
};

/**
 * The reading nearest two days old, which Today compares this post at, or
 * which of three reasons there is none (the studio's own words for each).
 */
function TwoDay({ post }: { post: PostDetailData }) {
  const two = post.two_day;
  if (!two) return null;
  if (two.state === "read" && two.reading) {
    const r = two.reading;
    const parts = [
      r.impressions != null ? `${r.impressions.toLocaleString()} IMPRESSIONS` : null,
      r.reactions != null ? `${r.reactions.toLocaleString()} REACTIONS` : null,
      r.comments != null ? `${r.comments.toLocaleString()} COMMENTS` : null,
    ].filter(Boolean);
    return (
      <p className="studio-meta mt-1 text-[10px] text-ink-muted">
        AT ABOUT TWO DAYS OLD (READ AT {Math.round(r.age_hours)} H FROM {(PAGES[r.source ?? ""] ?? r.source ?? "A PAGE").toUpperCase()}):{" "}
        {parts.length ? parts.join(" · ") : "NO FIGURE READ"}
      </p>
    );
  }
  const why: Record<string, string> = {
    too_new: `NOT TWO DAYS OLD YET: POSTS ARE COMPARED AT ABOUT ${two.at_hours} HOURS, AND THIS ONE IS ${Math.round(two.age_hours ?? 0)}`,
    not_yet: "NOT READ YET AT ABOUT TWO DAYS OLD: OPEN ITS ANALYTICS PAGE NOW AND IT WILL BE",
    missed: `NOT READ WHILE IT WAS ABOUT TWO DAYS OLD (${two.window[0]} TO ${two.window[1]} HOURS), SO IT CANNOT BE COMPARED AT THAT AGE`,
    unknown_age: "NOT COMPARED AT TWO DAYS: ITS PUBLISH TIME IS NOT KNOWN",
  };
  return <p className="studio-meta mt-1 text-[10px] text-ink-muted">{why[two.state] ?? ""}</p>;
}

/**
 * Every reading the studio keeps of this post, as a series per page, oldest
 * first: how it grew, and how many times each page was read. "Read N times"
 * counts the readings kept, and the roll-up thins older ones, which is said.
 */
function Readings({ post }: { post: PostDetailData }) {
  const readings = post.readings ?? [];
  if (readings.length === 0) {
    return <p className="studio-meta mt-4 text-[10px] text-ink-muted">NO READING OF THIS POST IS KEPT YET</p>;
  }
  const sources = Array.from(new Set(readings.map((reading) => reading.source)));
  const cell = (value: number | null, approximate: boolean) =>
    value === null ? "not read" : `${approximate ? "about " : ""}${value.toLocaleString()}`;
  return (
    <section className="mt-5">
      <p className="studio-label mb-2">Readings</p>
      {sources.map((source) => {
        const series = readings.filter((reading) => reading.source === source);
        return (
          <div key={source} className="mb-3">
            <p className="studio-meta text-[10px] text-ink-muted">
              FROM {(PAGES[source] ?? source.replace(/_/g, " ")).toUpperCase()}, READ {series.length}{" "}
              {series.length === 1 ? "TIME" : "TIMES"}
            </p>
            <table className="mt-1 w-full text-left text-[11px]">
              <thead>
                <tr className="studio-meta text-[10px] text-ink-muted">
                  <th className="py-0.5 font-normal">AGE</th>
                  <th className="py-0.5 font-normal">READ</th>
                  <th className="py-0.5 text-right font-normal">IMPRESSIONS</th>
                  <th className="py-0.5 text-right font-normal">REACTIONS</th>
                  <th className="py-0.5 text-right font-normal">COMMENTS</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-edge text-ink-secondary">
                {series.map((reading) => {
                  const rounded = reading.precision === "rounded";
                  return (
                    <tr key={reading.observed_at}>
                      <td className="py-0.5 tabular-nums">{reading.age_hours === null ? "not known" : `${Math.round(reading.age_hours)} h`}</td>
                      <td className="py-0.5">{formatLocalDay(reading.observed_at)}</td>
                      <td className="py-0.5 text-right tabular-nums">{cell(reading.impressions, rounded)}</td>
                      <td className="py-0.5 text-right tabular-nums">{cell(reading.reactions, rounded)}</td>
                      <td className="py-0.5 text-right tabular-nums">{cell(reading.comments, rounded)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        );
      })}
      {post.readings_thinned_after_days != null && (
        <p className="studio-meta text-[10px] leading-snug text-ink-muted">
          READINGS OLDER THAN {post.readings_thinned_after_days} DAYS KEEP THE FIRST AND LAST OF EACH DAY AND EVERY ONE AT 36
          TO 72 HOURS OLD, SO AN OLDER POST MAY HAVE BEEN READ MORE OFTEN THAN THIS SAYS.
        </p>
      )}
    </section>
  );
}

/** Seconds as a duration a person reads: "45 s", "12 min 5 s", "1 h 2 min". */
function duration(seconds: number): string {
  const whole = Math.round(seconds);
  if (whole < 60) return `${whole} s`;
  if (whole < 3600) return `${Math.floor(whole / 60)} min${whole % 60 ? ` ${whole % 60} s` : ""}`;
  const minutes = Math.round((whole % 3600) / 60);
  return `${Math.floor(whole / 3600)} h${minutes ? ` ${minutes} min` : ""}`;
}

function WatchTime({ post }: { post: PostDetailData }) {
  const total = post.per_post?.watch_time_seconds ?? null;
  const average = post.per_post?.average_watch_seconds ?? null;
  if (!total && !average) {
    return post.format === "video" ? (
      <p className="studio-meta mt-1 text-[10px] text-ink-muted">WATCH TIME NOT READ</p>
    ) : null;
  }
  const read = (total ?? average)?.read_at;
  return (
    <p className="studio-meta mt-1 text-[10px] text-ink-muted">
      WATCH TIME {total ? duration(total.value).toUpperCase() : "NOT READ"} · AVERAGE{" "}
      {average ? duration(average.value).toUpperCase() : "NOT READ"}
      {read ? ` · READ ${formatLocalDay(read, "").toUpperCase()}` : ""}
    </p>
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
