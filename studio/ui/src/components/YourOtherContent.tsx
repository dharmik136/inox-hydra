import { useEffect, useState } from "react";
import { fetchContentFigures, fetchOwnReposts, type ContentFigure, type ContentItem, type OwnRepost } from "@/lib/api";
import { useStudioBack } from "@/lib/refresh";
import { formatLocalDay } from "@/lib/time";

/**
 * Your own reposts, and your articles and newsletters (cycle 4, track 5's
 * phase 2), beside your posts: each with its own figures, the window its page
 * named, when it was read, and "not read" for a figure the page did not show.
 *
 * A repost keeps that it is one, its date and its own figures; the original's
 * author, words and figures are never kept, so a repost has no text here. An
 * article or newsletter is known by its kind and the day it was first read.
 * Drawn only once one of them has been read, and the newest few of each.
 */
const SHOWN = 6;

const REPOST_FIGURES: [keyof OwnRepost, string][] = [
  ["reactions", "reactions"],
  ["comments", "comments"],
  ["reposts", "reposts"],
  ["impressions", "impressions"],
];

const CONTENT_FIGURES: Record<ContentItem["kind"], [string, string][]> = {
  article: [
    ["views", "article views"],
    ["impressions", "impressions"],
    ["members_reached", "members reached"],
    ["reactions", "reactions"],
    ["comments", "comments"],
    ["reposts", "reposts"],
  ],
  newsletter: [
    ["subscribers", "subscribers"],
    ["views", "article views"],
    ["impressions", "impressions"],
    ["email_sends", "email sends"],
    ["email_open_rate_pct", "email open rate"],
  ],
};

export function YourOtherContent() {
  const [reposts, setReposts] = useState<OwnRepost[] | null>(null);
  const [content, setContent] = useState<ContentItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  // Read again when the studio answers after an outage.
  const back = useStudioBack();

  useEffect(() => {
    let live = true;
    Promise.all([fetchOwnReposts(), fetchContentFigures()])
      .then(([foundReposts, foundContent]) => {
        if (!live) return;
        setReposts(foundReposts);
        setContent(foundContent);
        setFailed(false);
      })
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [back]);

  if (failed) {
    return (
      <p className="studio-meta mt-6 text-[10px] leading-snug text-ink-muted">
        YOUR REPOSTS, ARTICLES AND NEWSLETTERS COULD NOT BE READ.
      </p>
    );
  }
  if (!reposts || !content || (reposts.length === 0 && content.length === 0)) return null;

  return (
    <div className="mt-6 grid gap-6 lg:grid-cols-2">
      {reposts.length > 0 && (
        <section aria-labelledby="your-reposts">
          <p id="your-reposts" className="studio-label mb-1">
            Your reposts
          </p>
          <p className="mb-2 text-[12px] leading-snug text-ink-muted">
            Read from your Activity tab: when you reposted, and the repost&apos;s own figures where the page told them
            apart from the original&apos;s, which are never kept.
            {reposts.length > SHOWN ? ` The newest ${SHOWN} of ${reposts.length}.` : ""}
          </p>
          <ul className="flex flex-col divide-y divide-edge border-y border-edge">
            {reposts.slice(0, SHOWN).map((repost) => (
              <li key={repost.activity_urn} className="py-1.5">
                <p className="text-[12px] text-ink-secondary">
                  Reposted {formatLocalDay(repost.reposted_at, "on a day not read")}
                </p>
                <p className="studio-meta text-[10px] text-ink-muted">
                  {REPOST_FIGURES.map(([key, label]) => {
                    const value = repost[key] as number | null;
                    return value === null ? `${label} not read` : `${value.toLocaleString()} ${label}`;
                  })
                    .join(" · ")
                    .toUpperCase()}
                  {` · READ ${formatLocalDay(repost.last_seen_at, "").toUpperCase()}`}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {content.length > 0 && (
        <section aria-labelledby="your-articles">
          <p id="your-articles" className="studio-label mb-1">
            Your articles and newsletters
          </p>
          <p className="mb-2 text-[12px] leading-snug text-ink-muted">
            Read from each one&apos;s own analytics page: every figure as that page last showed it, with the window it
            named, or as its total when it named none.
            {content.length > SHOWN ? ` The newest ${SHOWN} of ${content.length}.` : ""}
          </p>
          <ul className="flex flex-col divide-y divide-edge border-y border-edge">
            {[...content]
              .sort((a, b) => firstRead(b).localeCompare(firstRead(a)))
              .slice(0, SHOWN)
              .map((item) => (
                <li key={item.content_urn} className="py-1.5">
                  <p className="text-[12px] text-ink-secondary">
                    {item.kind === "article" ? "Article" : "Newsletter"}, first read{" "}
                    {formatLocalDay(firstRead(item) || null, "on a day not read")}
                  </p>
                  <ul className="mt-0.5 flex flex-col gap-0.5">
                    {CONTENT_FIGURES[item.kind].map(([key, label]) => (
                      <li key={key} className="studio-meta text-[10px] text-ink-muted">
                        {contentLine(label, key, item.latest[key]).toUpperCase()}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function firstRead(item: ContentItem): string {
  const first = item.readings[0] as { observed_at?: string } | undefined;
  return first?.observed_at ?? "";
}

/** One figure of an article or newsletter, with its window and when it was read, or "not read". */
function contentLine(label: string, key: string, figure: ContentFigure | undefined): string {
  if (!figure) return `${label} not read`;
  const value = key === "email_open_rate_pct" ? `${figure.value}%` : figure.value.toLocaleString();
  const about = figure.precision === "rounded" ? "about " : "";
  const days = /^(\d{1,3})d$/.exec(figure.period_label ?? "");
  const window = days ? `over the past ${days[1]} days` : "as its page showed it";
  return `${about}${value} ${label} ${window}, read ${formatLocalDay(figure.read_at, "")}`;
}
