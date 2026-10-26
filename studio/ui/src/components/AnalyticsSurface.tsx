import { memo, useEffect, useMemo, useState } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, Download } from "lucide-react";
import {
  fetchAnalyticsKpis,
  fetchAnalyticsOverview,
  fetchAnalyticsPosts,
  type AnalyticsKpis,
  type AnalyticsPoint,
  type AnalyticsBest,
  type AnalyticsPost,
  type AnalyticsRange,
  ANALYTICS_CSV_URL,
  fetchPostAttribution,
  fetchPostDetail,
  type PostAttribution,
} from "@/lib/api";
import { TimeSeriesChart, type SeriesPoint } from "./TimeSeriesChart";
import { useStudioBack } from "@/lib/refresh";
import { cn } from "@/lib/utils";

const RANGES: AnalyticsRange[] = ["7d", "30d", "90d"];

// A summary, not a second copy of the Posts table: most seen first, a
// handful at a time. The full, sortable, searchable table of every post
// lives on the Posts screen; this answers "how are my posts doing", not
// "show me all of them again".
const ANALYTICS_PAGE_SIZE = 14;

/** The measures worth plotting on their own axis, one at a time. */
const METRICS = [
  { key: "impressions", label: "Impressions" },
  { key: "reactions", label: "Reactions" },
  { key: "comments", label: "Comments" },
  { key: "profile_views", label: "Profile views" },
  { key: "followers", label: "Followers" },
] as const;

type MetricKey = (typeof METRICS)[number]["key"];

/** What the KPI route reports beyond the shared type: how much of each period was captured. */
type Kpis = AnalyticsKpis & {
  previous_days_counted?: number;
  days_needed_to_compare?: number;
  /** Days each figure was read on, this period and the one before. */
  coverage?: Record<"impressions" | "engagements" | "rate", { current: number; previous: number }>;
  /** Fields built from a figure LinkedIn rounded, such as 1.2K. */
  approximate?: string[];
  /** Changes not shown because they are smaller than that rounding. */
  within_rounding?: string[];
};

/** A day as the overview route returns it, with how precisely LinkedIn wrote its figures. */
type Point = AnalyticsPoint & { precision?: string | null };

/**
 * Analytics (blueprint section 13).
 *
 * A newspaper composition: range across the top, one large time series, three
 * written observations beside it, and a comparison table underneath. Not a
 * grid of glowing metric cards.
 */
export function AnalyticsSurface() {
  const [range, setRange] = useState<AnalyticsRange>("30d");
  const [metric, setMetric] = useState<MetricKey>("impressions");
  const [series, setSeries] = useState<Point[] | null>(null);
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [posts, setPosts] = useState<AnalyticsPost[] | null>(null);
  const [best, setBest] = useState<AnalyticsBest | null>(null);
  const [postsTotal, setPostsTotal] = useState(0);
  const [postsOffset, setPostsOffset] = useState(0);
  const [postsHasMore, setPostsHasMore] = useState(false);
  // The opening lines of the two posts the engine named, which are almost
  // never among the rows this page holds: the answer carries their figures
  // but not their text, and a URN names nothing a creator recognises.
  const [named, setNamed] = useState<Record<string, string>>({});
  const [loadingRange, setLoadingRange] = useState(false);
  const [failed, setFailed] = useState(false);
  // Read again when the studio answers after an outage, so a screen that
  // failed while it was down does not stay failed once it is back.
  const back = useStudioBack();

  // The posts do not depend on the range, so a range click does not read
  // them again. At 2,000 posts, fetching every one of them on every click
  // put the screen back to LOADING ANALYTICS for five seconds each time; now
  // only a page turn asks for more, and it asks for one page of them.
  useEffect(() => {
    let live = true;
    fetchAnalyticsPosts({ limit: ANALYTICS_PAGE_SIZE, offset: postsOffset })
      .then((answer) => {
        if (!live) return;
        setPosts(answer.posts);
        setBest(answer.best);
        setPostsTotal(answer.total);
        setPostsHasMore(answer.has_more);
      })
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [back, postsOffset]);

  // The opening line of each post the engine named, read one post at a time
  // from the same endpoint the Posts screen's detail view reads.
  useEffect(() => {
    const wanted = [...(best?.best ?? []), ...(best?.worst ?? [])].slice(0, 4).filter((urn) => !(urn in named));
    if (!wanted.length) return;
    let live = true;
    Promise.all(wanted.map((urn) => fetchPostDetail(urn).then((post) => [urn, post.text] as const).catch(() => null)))
      .then((answers) => {
        if (!live) return;
        const found: Record<string, string> = {};
        for (const answer of answers) if (answer) found[answer[0]] = answer[1];
        if (Object.keys(found).length) setNamed((current) => ({ ...current, ...found }));
      });
    return () => {
      live = false;
    };
  }, [best, named]);

  // A range change keeps the current chart on screen until the new one
  // arrives, rather than blanking the page.
  useEffect(() => {
    let live = true;
    setLoadingRange(true);
    Promise.all([fetchAnalyticsOverview(range), fetchAnalyticsKpis(range)])
      .then(([overview, kpiData]) => {
        if (!live) return;
        setSeries(overview);
        setKpis(kpiData);
        setFailed(false);
      })
      .catch(() => live && setFailed(true))
      .finally(() => live && setLoadingRange(false));
    return () => {
      live = false;
    };
  }, [range, back]);

  const points: SeriesPoint[] = useMemo(
    () => (series ?? []).map((row) => ({ date: row.date, value: row[metric] })),
    [series, metric],
  );

  // Provenance, counted rather than assumed. A row whose source is not
  // "observed" was not measured from LinkedIn.
  const provenance = useMemo(() => {
    if (!series || series.length === 0) return null;
    const synthetic = series.filter((row) => row.source && row.source !== "observed").length;
    return { synthetic, total: series.length };
  }, [series]);

  // Days whose plotted figure may be one LinkedIn abbreviated. Only a
  // multiple of 100 from 1,000 up can have come from "1.2K".
  const roundedDays = useMemo(
    () =>
      (series ?? []).filter((row) => {
        const value = row[metric];
        return row.precision === "rounded" && value !== null && value >= 1000 && value % 100 === 0;
      }).length,
    [series, metric],
  );

  if (failed) return <Centered>ANALYTICS UNAVAILABLE</Centered>;
  if (!series) return <Centered>LOADING ANALYTICS</Centered>;

  const metricLabel = METRICS.find((m) => m.key === metric)?.label ?? metric;

  return (
    <div className="mx-auto max-w-[120ch] px-8 py-6">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="studio-title">Analytics</h1>
        <div className="flex items-center gap-3">
          {/* A file download, so the browser handles it rather than fetch. */}
          <a
            href={ANALYTICS_CSV_URL}
            className="studio-meta flex items-center gap-1 text-[10px] text-ink-muted transition-colors hover:text-ink-primary"
          >
            <Download className="size-3" strokeWidth={2} aria-hidden="true" />
            CSV
          </a>
          {/* Exact figures for up to a year come from LinkedIn's own export, imported in Setup beside the archive. */}
          <a
            href="#/setup"
            className="studio-meta text-[10px] text-ink-muted underline underline-offset-2 transition-colors hover:text-ink-primary"
          >
            Import LinkedIn&apos;s analytics export in Setup
          </a>
        <div className="flex items-center gap-1" role="group" aria-label="Date range" aria-busy={loadingRange}>
          {RANGES.map((candidate) => (
            <button
              key={candidate}
              type="button"
              onClick={() => setRange(candidate)}
              aria-pressed={range === candidate}
              className={cn(
                "rounded-md px-2.5 py-1 text-[11px] font-medium uppercase",
                "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard)",
                range === candidate ? "bg-soft text-ink-primary" : "text-ink-muted hover:text-ink-secondary",
              )}
            >
              {candidate}
            </button>
          ))}
        </div>
        </div>
      </div>

      {/* Provenance is not a footnote here.
       *
       * The studio once generated ninety days of analytics by modulo
       * arithmetic at every boot with nothing marking them synthetic, and
       * every chart and export drew from it indistinguishably from real
       * capture. The rows now carry their origin, and a surface that renders
       * the numbers has to render that too, above the chart rather than
       * beneath it. */}
      {provenance && provenance.synthetic > 0 && (
        <p
          role="status"
          className="mt-4 flex items-start gap-2 rounded-md border border-signal-orange/40 bg-signal-orange-subtle p-3"
        >
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-signal-orange-text" strokeWidth={1.75} aria-hidden="true" />
          <span className="text-[12px] leading-snug text-ink-secondary">
            <span className="font-medium text-ink-primary">
              {provenance.synthetic} of {provenance.total} days are seeded sample data, not measurements.
            </span>{" "}
            Everything below, including the chart and the observations, is computed from them. Captured
            days replace seeded ones as they arrive.
          </span>
        </p>
      )}

      {/* The levels, with each one's own change beside it. They were in the
          aside as changes alone, so the screen printed "+4.2%" of a figure
          it never showed, and a chart of one measure at a time was the only
          number on it. */}
      <KpiStrip kpis={kpis} range={range} />

      <div className="mt-5 grid gap-x-6 gap-y-5 lg:grid-cols-[minmax(0,1fr)_270px]">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Measure">
            {METRICS.map((candidate) => (
              <button
                key={candidate.key}
                type="button"
                onClick={() => setMetric(candidate.key)}
                aria-pressed={metric === candidate.key}
                className={cn(
                  "rounded-full border px-2.5 py-0.5 text-[11px]",
                  "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard)",
                  metric === candidate.key
                    ? "border-edge-strong bg-soft text-ink-primary"
                    : "border-edge text-ink-muted hover:text-ink-secondary",
                )}
              >
                {candidate.label}
              </button>
            ))}
          </div>

          {/* A single series, so the heading names it and no legend box is drawn. */}
          <p className="studio-label mt-3 mb-2">{metricLabel} per day</p>
          <TimeSeriesChart points={points} label={metricLabel} />
          {roundedDays > 0 && (
            <p className="studio-meta mt-2 text-[10px] leading-snug text-ink-muted">
              {roundedDays} OF THESE DAYS {roundedDays === 1 ? "WAS" : "WERE"} READ FROM A FIGURE LINKEDIN
              ROUNDED, SUCH AS 1.2K, SO {roundedDays === 1 ? "ITS POINT IS" : "THEIR POINTS ARE"} APPROXIMATE.
            </p>
          )}

          {/* The comparison table sits with the chart rather than ten screens
              under it: this screen was 58.9 screens tall, and the rows a
              creator came for were all below the fold. */}
          <section className="mt-6">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="studio-label">Post comparison</p>
              {/* The order the route actually reads in, in its own words
                  (routers/analytics.py: impressions, then reactions). It
                  read "best first", which is the engine's word for a
                  different ranking: results.best ranks by reactions against
                  the creator's own median, so the panel beside this table
                  named one post while this line implied another. */}
              {posts !== null && postsTotal > 0 && (
                <p className="studio-meta text-[11px] text-ink-muted">
                  {`${postsOffset + 1}–${postsOffset + posts.length} of ${postsTotal.toLocaleString()}, most seen first`}
                </p>
              )}
            </div>
            {posts === null ? (
              <p className="studio-meta text-ink-muted">READING YOUR POSTS</p>
            ) : posts.length === 0 ? (
              <p className="studio-meta text-ink-muted">NO PUBLISHED POSTS TO COMPARE</p>
            ) : (
              <>
                <PostTable posts={posts} />
                <div className="mt-2 flex items-center justify-end gap-1">
                  <button
                    type="button"
                    onClick={() => setPostsOffset((current) => Math.max(0, current - ANALYTICS_PAGE_SIZE))}
                    disabled={postsOffset === 0}
                    aria-label="Previous posts"
                    className="grid size-7 place-items-center rounded-md border border-edge text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
                  >
                    <ChevronLeft className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setPostsOffset((current) => current + ANALYTICS_PAGE_SIZE)}
                    disabled={!postsHasMore}
                    aria-label="Next posts"
                    className="grid size-7 place-items-center rounded-md border border-edge text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
                  >
                    <ChevronRight className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                  </button>
                </div>
              </>
            )}
          </section>
        </div>

        <Observations kpis={kpis} posts={posts} best={best} named={named} />
      </div>
    </div>
  );
}

/** The five figures the range holds, each with its own change and its own honesty. */
function KpiStrip({ kpis, range }: { kpis: Kpis | null; range: AnalyticsRange }) {
  if (!kpis) return null;
  const approx = new Set(kpis.approximate ?? []);
  const figures: {
    label: string; value: number | null; suffix?: string; change: string | null;
    /** The KPI field the level is, and the one the change is: either can be approximate. */
    key: string; changeKey: string;
  }[] = [
    {
      label: "Impressions", value: kpis.impressions, key: "impressions", changeKey: "impressions_delta_pct",
      change: kpis.impressions_delta_pct === null ? null : `${kpis.impressions_delta_pct > 0 ? "+" : ""}${kpis.impressions_delta_pct.toFixed(1)}%`,
    },
    {
      label: "Engagements", value: kpis.total_engagements, key: "total_engagements", changeKey: "engagements_delta_pct",
      change: kpis.engagements_delta_pct === null ? null : `${kpis.engagements_delta_pct > 0 ? "+" : ""}${kpis.engagements_delta_pct.toFixed(1)}%`,
    },
    {
      label: "Engagement rate", value: kpis.avg_engagement_rate, suffix: "%", key: "avg_engagement_rate",
      changeKey: "engagement_rate_delta",
      change: kpis.engagement_rate_delta === null ? null : `${kpis.engagement_rate_delta > 0 ? "+" : ""}${kpis.engagement_rate_delta.toFixed(2)}pp`,
    },
    {
      label: "Followers", value: kpis.total_followers, key: "total_followers", changeKey: "follower_growth",
      change: kpis.follower_growth === null ? null : `${kpis.follower_growth > 0 ? "+" : ""}${kpis.follower_growth.toLocaleString()}`,
    },
    {
      label: "Profile views", value: kpis.profile_views, key: "profile_views", changeKey: "profile_views_delta_pct",
      change: kpis.profile_views_delta_pct === null ? null : `${kpis.profile_views_delta_pct > 0 ? "+" : ""}${kpis.profile_views_delta_pct.toFixed(1)}%`,
    },
  ];
  return (
    <>
      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 border-y border-edge py-3 sm:grid-cols-3 lg:grid-cols-5">
        {figures.map((figure) => (
          <div key={figure.label} className="min-w-0">
            <dt className="studio-meta text-[10px] text-ink-muted">{figure.label.toUpperCase()}</dt>
            <dd className="mt-0.5 text-[15px] tabular-nums text-ink-primary">
              {/* A figure read on no day of the range is not measured, not 0. */}
              {figure.value === null ? (
                <span className="text-[12px] text-ink-muted">not measured</span>
              ) : (
                <>
                  {approx.has(figure.key) && (
                    <>
                      <span aria-hidden="true">~</span>
                      <span className="sr-only">about </span>
                    </>
                  )}
                  {figure.value.toLocaleString()}
                  {figure.suffix ?? ""}
                </>
              )}
            </dd>
            <dd className="studio-meta mt-0.5 text-[10px] tabular-nums text-ink-secondary">
              {/* A change the studio cannot stand behind says so in the words
                  the rest of the product uses, and the line under the strip
                  says why. It is never a plausible looking percentage. */}
              {figure.change === null ? (
                <span className="text-ink-muted">not measured</span>
              ) : (
                <>
                  {approx.has(figure.changeKey) && (
                    <>
                      <span aria-hidden="true">~</span>
                      <span className="sr-only">about </span>
                    </>
                  )}
                  {`${figure.change} ON THE ${range.toUpperCase()} BEFORE`}
                </>
              )}
            </dd>
          </div>
        ))}
      </dl>
      <p className="studio-meta mt-2 text-[10px] leading-snug text-ink-muted">
        {kpis.days_counted ?? 0} DAY{(kpis.days_counted ?? 0) === 1 ? "" : "S"} OF THIS {range.toUpperCase()} WERE
        CAPTURED, AND {kpis.previous_days_counted ?? 0} OF THE {range.toUpperCase()} BEFORE IT. A CHANGE IS SHOWN
        ONLY WHERE BOTH PERIODS HOLD AT LEAST {kpis.days_needed_to_compare ?? 0} CAPTURED DAYS OF THAT FIGURE, SO A
        PART CAPTURED PERIOD READS NOT MEASURED RATHER THAN A PERCENTAGE.
      </p>
    </>
  );
}

/**
 * The comparison table, drawn again only when the posts change.
 *
 * The posts do not depend on the range, and at 2,000 rows redrawing them on
 * every range click took most of a second.
 */
const PostTable = memo(function PostTable({ posts }: { posts: AnalyticsPost[] }) {
  // A post whose recorded engagements exceed its impressions has no rate: the
  // two figures were read from different pages at different moments. One post
  // of 1,417 read 877 reactions against 837 impressions, and the aside beside
  // this table promoted it as "116.25% engagement".
  const impossible = posts.filter(
    (post) => post.engagement_rate_unmeasured === "more_engagements_than_impressions",
  );
  return (
    <>
    <table className="w-full text-left">
      <thead>
        <tr className="studio-label border-b border-edge">
          <th scope="col" className="py-2 font-medium">Post</th>
          <th scope="col" className="py-2 text-right font-medium">Impressions</th>
          <th scope="col" className="py-2 text-right font-medium">Reactions</th>
          <th scope="col" className="py-2 text-right font-medium">Comments</th>
          <th scope="col" className="py-2 text-right font-medium">Rate</th>
        </tr>
      </thead>
      <tbody>
        {posts.map((post) => (
          <PostRow key={post.id} post={post} />
        ))}
      </tbody>
    </table>
    {impossible.length > 0 && (
      <p className="studio-meta mt-2 text-[10px] leading-snug text-ink-muted">
        {impossible.length} POST{impossible.length === 1 ? " ON THIS PAGE HAS" : "S ON THIS PAGE HAVE"} MORE
        ENGAGEMENTS RECORDED THAN IMPRESSIONS, SO THOSE TWO FIGURES CAME FROM DIFFERENT READINGS AND NO RATE CAN
        BE MEASURED FROM THEM.
      </p>
    )}
    </>
  );
});

/**
 * One post, expandable into the leads it actually produced.
 *
 * Attribution is fetched on expand rather than for every row up front: it is
 * one query per post and most rows are never opened.
 */
function PostRow({ post }: { post: AnalyticsPost }) {
  const [open, setOpen] = useState(false);
  const [attribution, setAttribution] = useState<PostAttribution | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open || attribution) return;
    let live = true;
    fetchPostAttribution(post.id)
      .then((result) => live && setAttribution(result))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [open, attribution, post.id]);

  return (
    <>
      <tr className="border-b border-edge">
        <td className="max-w-[40ch] py-2 pr-4">
          <button
            type="button"
            onClick={() => setOpen((current) => !current)}
            aria-expanded={open}
            className="flex w-full items-center gap-1.5 text-left text-[12px] text-ink-secondary transition-colors hover:text-ink-primary"
          >
            <ChevronRight
              className={cn("size-3 shrink-0 transition-transform", open && "rotate-90")}
              strokeWidth={2}
              aria-hidden="true"
            />
            <span className="truncate">{post.content.split("\n")[0]}</span>
          </button>
        </td>
        <Cell value={post.impressions} />
        <Cell value={post.reactions} />
        <Cell value={post.comments} />
        <Cell value={post.engagement_rate} suffix="%" />
      </tr>

      {open && (
        <tr className="border-b border-edge">
          <td colSpan={5} className="py-3 pl-5">
            {failed ? (
              <p className="studio-meta text-ink-muted">ATTRIBUTION UNAVAILABLE</p>
            ) : !attribution ? (
              <p className="studio-meta text-ink-muted">READING ATTRIBUTION</p>
            ) : attribution.leads.length === 0 && attribution.summary.total_leads_generated === 0 ? (
              <p className="studio-meta text-ink-muted">NO LEADS ATTRIBUTED TO THIS POST</p>
            ) : (
              <>
                <p className="studio-meta mb-2">
                  {attribution.summary.total_leads_generated} LEAD
                  {attribution.summary.total_leads_generated === 1 ? "" : "S"}
                  <span className="mx-1.5 text-ink-muted">·</span>
                  {attribution.summary.total_interactions} INTERACTIONS
                </p>
                <ul className="flex flex-col gap-1.5">
                  {attribution.leads.map((lead) => (
                    <li key={lead.lead_id} className="border-l border-edge pl-3">
                      <p className="text-[12px] text-ink-primary">
                        {lead.name}
                        {lead.company && <span className="text-ink-muted"> at {lead.company}</span>}
                      </p>
                      {lead.latest_comment && (
                        <p className="mt-0.5 text-[11px] leading-snug text-ink-secondary">
                          {lead.latest_comment}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
                {attribution.summary.folded_leads > 0 && (
                  <p className="studio-meta mt-2 text-[10px] text-ink-muted">
                    {attribution.summary.folded_leads} MORE FROM REACTIONS OVER 24 MONTHS OLD, KEPT AS A COUNT
                    WITHOUT NAMES (STORAGE AND PRIVACY)
                  </p>
                )}
              </>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

function Cell({ value, suffix = "" }: { value: number | null; suffix?: string }) {
  return (
    <td className="studio-meta py-2 text-right text-[11px] text-ink-secondary">
      {/* An uncaptured metric is null, and null renders as "not measured"
          rather than as a zero the reader would average. */}
      {value === null ? <span className="text-ink-muted">not measured</span> : `${value.toLocaleString()}${suffix}`}
    </td>
  );
}

/**
 * The three written observations.
 *
 * Every line is a description of numbers the studio holds. None of them claims
 * a cause. The blueprint asks for "what caused it", and the honest version of
 * that here is what else moved at the same time: this product observes a feed,
 * it does not run experiments, so it cannot separate correlation from cause and
 * must not write sentences that imply it did.
 */
function Observations({
  kpis,
  posts,
  best,
  named,
}: {
  kpis: Kpis | null;
  posts: AnalyticsPost[] | null;
  best: AnalyticsBest | null;
  /** The opening lines of the posts the engine named, by URN. */
  named: Record<string, string>;
}) {
  if (!kpis) return null;
  const coverage = coverageNote(kpis);
  const approx = new Set(kpis.approximate ?? []);
  const hidden = WHAT_CHANGED.filter((line) => (kpis.within_rounding ?? []).includes(line.key)).map((l) => l.label);

  // The strongest post, as the one engine ranks it over the whole history:
  // against the creator's own median reactions, settled posts only. This
  // panel used to take the highest engagement rate out of the rows the table
  // had fetched, which after paging meant page one, and the rate had no
  // clamp, so it read "Your strongest post in this set ran at 116.25%
  // engagement" beside a table whose every row read under 1.6%.
  const strongest = best?.best?.[0] ?? null;
  const ratio = strongest ? best?.named?.[strongest]?.against_usual?.[best.metric] ?? null : null;

  return (
    <aside className="flex flex-col gap-5 lg:border-l lg:border-edge lg:pl-5">
      {/* Only when there is something to read: an empty heading over nothing
          is what the rest of this screen is being cleared of. */}
      {(WHAT_CHANGED.some((line) => approx.has(line.key)) || hidden.length > 0
        || (kpis.days_excluded_unknown_window ?? 0) > 0 || coverage) && (
      <section>
        <p className="studio-label mb-1.5">How to read the figures</p>
        {/* The changes themselves are in the strip above, beside the figure
            each one is a change in. What belongs here is what the studio
            could not measure and why, which is the part a creator cannot
            work out for themselves. */}
        {/* LinkedIn writes some figures as 1.2K, which is anything from 1,150
            to 1,249. A change built from one is approximate, and a change
            smaller than that rounding is not shown at all. */}
        {WHAT_CHANGED.some((line) => approx.has(line.key)) && (
          <p className="studio-meta mt-2 text-[10px] leading-snug text-ink-muted">
            ~ MARKS A CHANGE BUILT FROM A FIGURE LINKEDIN ROUNDED, SUCH AS 1.2K, SO IT IS APPROXIMATE.
          </p>
        )}
        {hidden.length > 0 && (
          <p className="studio-meta mt-2 text-[10px] leading-snug text-ink-muted">
            {hidden.join(" AND ").toUpperCase()} MOVED LESS THAN LINKEDIN&rsquo;S ROUNDING OF THE FIGURES (1.2K IS
            ANYTHING FROM 1,150 TO 1,249), SO NO CHANGE IS SHOWN.
          </p>
        )}
        {/* A day captured with the range selector on 7 or 28 days holds a
            multi-day total, so it is left out of every sum rather than counted
            as one day. Saying so explains a total that looks low. */}
        {(kpis.days_excluded_unknown_window ?? 0) > 0 && (
          <p className="studio-meta mt-2 text-[10px] leading-snug text-ink-muted">
            {kpis.days_excluded_unknown_window} CAPTURED{" "}
            {kpis.days_excluded_unknown_window === 1 ? "DAY IS" : "DAYS ARE"} LEFT OUT: THEIR FIGURES COVER AN
            UNKNOWN NUMBER OF DAYS. SET LINKEDIN&rsquo;S RANGE TO 24 HOURS WHEN YOU OPEN ANALYTICS.
          </p>
        )}
        {/* A change from a period that is mostly uncaptured would compare
            thirty days with four, so it is not shown, and this says why. */}
        {coverage && <p className="studio-meta mt-2 text-[10px] leading-snug text-ink-muted">{coverage}</p>}
      </section>
      )}

      <section>
        <p className="studio-label mb-1.5">What moved with it</p>
        <p className="text-[12px] leading-relaxed text-ink-secondary">
          {describeRelationship(kpis)}
        </p>
      </section>

      {/* The posts the engine named, best and weakest, with the figures it
          ranked them on. They are read from the whole history, so neither is
          usually among the rows of the table beside this. */}
      {best && (best.best.length > 0 || best.worst.length > 0) && (
        <section>
          <p className="studio-label mb-1.5">Your best and your weakest</p>
          <ul className="flex flex-col gap-2.5">
            {[...best.best.slice(0, 2).map((urn) => ({ urn, kind: "best" as const })),
              ...best.worst.slice(0, 2).map((urn) => ({ urn, kind: "worst" as const }))].map(({ urn, kind }) => {
              const figures = best.named?.[urn];
              const against = figures?.against_usual?.[best.metric];
              return (
                <li key={`${kind}-${urn}`}>
                  <p className="studio-meta text-[10px] text-ink-muted">
                    {kind === "best" ? "ABOVE YOUR USUAL" : "BELOW YOUR USUAL"}
                    {against !== undefined && (
                      <span className={kind === "best" ? "ml-1.5 text-signal-green-text" : "ml-1.5 text-signal-orange-text"}>
                        {against}x
                      </span>
                    )}
                  </p>
                  <p className="line-clamp-2 text-[12px] leading-snug text-ink-secondary">
                    {named[urn] ? openingLine(named[urn]) : "reading this post"}
                  </p>
                  <p className="studio-meta text-[10px] tabular-nums text-ink-muted">
                    {figures?.reactions === null || figures?.reactions === undefined
                      ? "REACTIONS NOT READ"
                      : `${figures.reactions.toLocaleString()} REACTIONS`}
                    {figures?.impressions != null && ` \u00b7 ${figures.impressions.toLocaleString()} IMPRESSIONS`}
                  </p>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <section>
        <p className="studio-label mb-1.5">What to look at next</p>
        {posts === null ? (
          <p className="studio-meta text-ink-muted">READING YOUR POSTS</p>
        ) : best && strongest && ratio ? (
          <p className="text-[12px] leading-relaxed text-ink-secondary">
            Your strongest post, across the {best.ranked_posts} of your posts whose figures have settled, took{" "}
            <span className="text-ink-primary">{ratio}x</span> your usual {best.metric}. Comparing its opening
            against the weaker ones is the one comparison this data supports.
          </p>
        ) : (
          <p className="text-[12px] leading-relaxed text-ink-muted">
            No post of yours has settled figures to compare yet, so there is nothing to compare.
          </p>
        )}
      </section>
    </aside>
  );
}

/** What shows before anything else on a post: its first line. */
function openingLine(text: string): string {
  const first = text.split("\n").map((line) => line.trim()).find((line) => line.length > 0);
  return first ?? "(no text)";
}

/** Why Impressions and Engagements read "not measured", when the reason is too few captured days. */
function coverageNote(kpis: Kpis): string | null {
  const need = kpis.days_needed_to_compare;
  if (need == null || !kpis.coverage) return null;
  // Counted per figure: a day whose impressions were read and whose
  // engagements were not is a captured day for one and not the other.
  const short = (["impressions", "engagements"] as const)
    .map((metric) => ({ metric, ...kpis.coverage![metric] }))
    .filter((c) => c.current < need || c.previous < need);
  if (!short.length) return null;
  return (
    `A CHANGE IS SHOWN ONLY WHEN THIS PERIOD AND THE ONE BEFORE IT EACH HAVE THAT FIGURE CAPTURED ON AT LEAST ${need} DAYS. ` +
    short
      .map((c) => `${c.metric.toUpperCase()}: ${c.current} DAYS IN THIS PERIOD, ${c.previous} IN THE ONE BEFORE.`)
      .join(" ")
  );
}

/** Describes how reach and engagement moved together. Never asserts a cause. */
function describeRelationship(kpis: AnalyticsKpis): string {
  const reach = kpis.impressions_delta_pct;
  const engagement = kpis.engagements_delta_pct;
  if (reach === null || engagement === null) {
    return "Reach and engagement were not both measured over this range, so they cannot be compared.";
  }
  if (reach > 0 && engagement <= 0) {
    return "Reach rose while engagements did not follow, so more people saw the posts and proportionally fewer acted on them.";
  }
  if (reach <= 0 && engagement > 0) {
    return "Engagements rose on flat or falling reach, so a smaller audience acted more often.";
  }
  if (reach <= 0 && engagement <= 0) {
    return "Reach and engagements fell together, which is the pattern a quieter posting cadence produces as well as a distribution change.";
  }
  return "Reach and engagements rose together, in step rather than one leading the other.";
}

/** The "What changed" lines, by the KPI field each one shows. */
const WHAT_CHANGED = [
  { key: "impressions_delta_pct", label: "Impressions" },
  { key: "engagements_delta_pct", label: "Engagements" },
  { key: "profile_views_delta_pct", label: "Profile views" },
  { key: "follower_growth", label: "Followers" },
] as const;

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid h-full place-items-center px-8">
      <p className="studio-meta max-w-[40ch] text-center leading-relaxed text-ink-muted">{children}</p>
    </div>
  );
}
