import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Download } from "lucide-react";
import {
  fetchAnalyticsKpis,
  fetchAnalyticsOverview,
  fetchAnalyticsPosts,
  type AnalyticsKpis,
  type AnalyticsPoint,
  type AnalyticsPost,
  type AnalyticsRange,
  ANALYTICS_CSV_URL,
} from "@/lib/api";
import { TimeSeriesChart, type SeriesPoint } from "./TimeSeriesChart";
import { cn } from "@/lib/utils";

const RANGES: AnalyticsRange[] = ["7d", "30d", "90d"];

/** The measures worth plotting on their own axis, one at a time. */
const METRICS = [
  { key: "impressions", label: "Impressions" },
  { key: "reactions", label: "Reactions" },
  { key: "comments", label: "Comments" },
  { key: "profile_views", label: "Profile views" },
  { key: "followers", label: "Followers" },
] as const;

type MetricKey = (typeof METRICS)[number]["key"];

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
  const [series, setSeries] = useState<AnalyticsPoint[] | null>(null);
  const [kpis, setKpis] = useState<AnalyticsKpis | null>(null);
  const [posts, setPosts] = useState<AnalyticsPost[]>([]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    setSeries(null);
    Promise.all([fetchAnalyticsOverview(range), fetchAnalyticsKpis(range), fetchAnalyticsPosts()])
      .then(([overview, kpiData, postRows]) => {
        if (!live) return;
        setSeries(overview);
        setKpis(kpiData);
        setPosts(postRows);
        setFailed(false);
      })
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [range]);

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

  if (failed) return <Centered>ANALYTICS UNAVAILABLE</Centered>;
  if (!series) return <Centered>LOADING ANALYTICS</Centered>;

  const metricLabel = METRICS.find((m) => m.key === metric)?.label ?? metric;

  return (
    <div className="mx-auto max-w-[110ch] px-8 py-8">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h2 className="studio-title">Analytics</h2>
        <div className="flex items-center gap-3">
          {/* A file download, so the browser handles it rather than fetch. */}
          <a
            href={ANALYTICS_CSV_URL}
            className="studio-meta flex items-center gap-1 text-[10px] text-ink-muted transition-colors hover:text-ink-primary"
          >
            <Download className="size-3" strokeWidth={2} aria-hidden="true" />
            CSV
          </a>
        <div className="flex items-center gap-1" role="group" aria-label="Date range">
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

      <div className="mt-6 flex flex-wrap items-center gap-1" role="group" aria-label="Measure">
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

      <div className="mt-4 grid gap-6 lg:grid-cols-[1fr_260px]">
        <div>
          {/* A single series, so the heading names it and no legend box is drawn. */}
          <p className="studio-label mb-2">{metricLabel} per day</p>
          <TimeSeriesChart points={points} label={metricLabel} />
        </div>

        <Observations kpis={kpis} posts={posts} />
      </div>

      <section className="mt-10">
        <p className="studio-label mb-3">Post comparison</p>
        {posts.length === 0 ? (
          <p className="studio-meta text-ink-muted">NO PUBLISHED POSTS TO COMPARE</p>
        ) : (
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
                <tr key={post.id} className="border-b border-edge">
                  <td className="max-w-[40ch] truncate py-2 pr-4 text-[12px] text-ink-secondary">
                    {post.content.split("\n")[0]}
                  </td>
                  <Cell value={post.impressions} />
                  <Cell value={post.reactions} />
                  <Cell value={post.comments} />
                  <Cell value={post.engagement_rate} suffix="%" />
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
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
function Observations({ kpis, posts }: { kpis: AnalyticsKpis | null; posts: AnalyticsPost[] }) {
  if (!kpis) return null;

  const pct = (value: number | null) =>
    value === null ? null : `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;

  const best = posts.reduce<AnalyticsPost | null>(
    (acc, post) =>
      post.engagement_rate !== null && (acc === null || post.engagement_rate > (acc.engagement_rate ?? -1))
        ? post
        : acc,
    null,
  );

  return (
    <aside className="flex flex-col gap-5 border-l border-edge pl-5">
      <section>
        <p className="studio-label mb-1.5">What changed</p>
        <ul className="flex flex-col gap-1">
          <Line label="Impressions" value={pct(kpis.impressions_delta_pct)} />
          <Line label="Engagements" value={pct(kpis.engagements_delta_pct)} />
          <Line label="Profile views" value={pct(kpis.profile_views_delta_pct)} />
          <Line
            label="Followers"
            value={kpis.follower_growth === null ? null : `${kpis.follower_growth > 0 ? "+" : ""}${kpis.follower_growth}`}
          />
        </ul>
      </section>

      <section>
        <p className="studio-label mb-1.5">What moved with it</p>
        <p className="text-[12px] leading-relaxed text-ink-secondary">
          {describeRelationship(kpis)}
        </p>
      </section>

      <section>
        <p className="studio-label mb-1.5">What to look at next</p>
        {best ? (
          <p className="text-[12px] leading-relaxed text-ink-secondary">
            Your strongest post in this set ran at{" "}
            <span className="text-ink-primary">{best.engagement_rate?.toFixed(2)}%</span> engagement.
            Comparing its opening against the weaker ones is the one comparison this data supports.
          </p>
        ) : (
          <p className="text-[12px] leading-relaxed text-ink-muted">
            No post carries a measured engagement rate yet, so there is nothing to compare.
          </p>
        )}
      </section>
    </aside>
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

function Line({ label, value }: { label: string; value: string | null }) {
  return (
    <li className="flex items-baseline justify-between gap-3">
      <span className="text-[11px] text-ink-muted">{label}</span>
      <span className="studio-meta text-ink-secondary">{value ?? "not measured"}</span>
    </li>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid h-full place-items-center px-8">
      <p className="studio-meta max-w-[40ch] text-center leading-relaxed text-ink-muted">{children}</p>
    </div>
  );
}
