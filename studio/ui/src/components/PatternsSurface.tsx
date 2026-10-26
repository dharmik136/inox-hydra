import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronsUpDown } from "lucide-react";
import {
  fetchCadenceInsights,
  fetchPatternsInsights,
  fetchContrastInsights,
  fetchTopicAttribution,
  type CadenceInsights,
  type PatternFinding,
  type PatternsInsights,
  type ContrastInsights,
  type SettleCurve,
  type SettledAfter,
  type TopicAttributionInsights,
} from "@/lib/api";
import { gapOrNotMeasured } from "@/lib/cadence";
import { useStudioBack } from "@/lib/refresh";
import { ratioTone } from "@/lib/results";
import { cn } from "@/lib/utils";
import { EmptySurface } from "./EmptySurface";

/** A topic as the attribution route returns it: people counted once, and a rate only when someone was captured. */
type TopicRow = Omit<TopicAttributionInsights["topics"][number], "lead_conversion_rate"> & {
  people_engaged?: number;
  lead_conversion_rate: number | null;
};

type TopicSortKey = "topic" | "posts" | "total_reactions" | "people_engaged" | "qualified_leads" | "lead_conversion_rate";

/**
 * Patterns and cadence: what your own posts suggest, and how steadily you post.
 *
 * Patterns compare your week-old posts that have a form against those that do
 * not, by median reactions, always with both counts. The wording is "went
 * with", never "causes", and a pattern whose two sides come from different
 * periods is marked, because then the difference may be about when you
 * posted rather than how. Cadence shows counts and gaps and deliberately names
 * no best day: you chose the days you posted on, so they cannot be separated
 * from everything else about those posts.
 */
export function PatternsSurface({ onOpenSetup }: { onOpenSetup?: () => void } = {}) {
  const [patterns, setPatterns] = useState<PatternsInsights | null>(null);
  const [cadence, setCadence] = useState<CadenceInsights | null>(null);
  // How the "went with more or fewer reactions" list orders itself: by how
  // far from 1x the ratio sits (the server's own order), or by how many
  // posts the line rests on, for a creator who trusts a bigger sample over a
  // bigger number.
  const [patternOrder, setPatternOrder] = useState<"difference" | "sample">("difference");
  const [expandedPattern, setExpandedPattern] = useState<string | null>(null);
  const [topicSort, setTopicSort] = useState<{ key: TopicSortKey; dir: "asc" | "desc" }>({
    key: "qualified_leads",
    dir: "desc",
  });
  const [contrasts, setContrasts] = useState<ContrastInsights | null>(null);
  const [attribution, setAttribution] = useState<TopicAttributionInsights | null>(null);
  const [failed, setFailed] = useState(false);
  // Read again when the studio answers after an outage, so a screen that
  // failed while it was down does not stay failed once it is back.
  const back = useStudioBack();

  useEffect(() => {
    Promise.all([
      fetchPatternsInsights(),
      fetchCadenceInsights(),
      fetchContrastInsights().catch(() => null),
      fetchTopicAttribution().catch(() => null),
    ])
      .then(([p, c, co, a]) => {
        setPatterns(p);
        setCadence(c);
        if (co) setContrasts(co);
        if (a) setAttribution(a);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, [back]);

  if (failed && !patterns) return <Centered>PATTERNS ARE UNAVAILABLE. IS THE STUDIO RUNNING?</Centered>;
  if (!patterns || !cadence) return <Centered>LOADING PATTERNS</Centered>;
  if (!cadence.posts) {
    return (
      <EmptySurface label="Patterns" title="What your own posts suggest" onOpenSetup={onOpenSetup}>
        None of your posts have been imported yet. Once they are, this compares the ones that share a
        form with the ones that do not, and says only what the sample supports.
      </EmptySurface>
    );
  }

  const unread = patterns as PatternsInsights & {
    settled_without_reactions?: number;
    settled_without_reactions_from_archive?: number;
  };
  // A line whose own verdict is "none" is a difference too small for this
  // creator's posts to separate (results.difference), and it is said rather
  // than printed as a finding: a 1.1x line over 1,417 posts read as a rule to
  // follow when it is noise.
  const verdict = (p: PatternFinding) => p.difference?.verdict;
  // Enough posts on both sides, but no ratio: the posts without the form
  // have a median of 0 reactions, so there is nothing to divide by. Such a
  // line sat in the list of findings and, opened, was worded "not enough
  // posts to say", which is a different verdict. It is named for what it is.
  const unmeasured = patterns.patterns.filter((p) => verdict(p) === "not_measured");
  const cleanUnordered = patterns.patterns.filter(
    (p) => !p.different_period && verdict(p) !== "none" && verdict(p) !== "not_measured",
  );
  const clean =
    patternOrder === "sample"
      ? [...cleanUnordered].sort((a, b) => b.with_posts + b.without_posts - (a.with_posts + a.without_posts))
      : cleanUnordered;
  const same = patterns.patterns.filter((p) => !p.different_period && verdict(p) === "none");
  const confounded = patterns.patterns.filter((p) => p.different_period);
  // The same seven forms were compared twice on this screen: here, with 3
  // posts a side, and again below as "Binary feature comparisons", with 8 a
  // side and the words ABSTAIN and PER ARM. One list now, and one number of
  // posts a side (results.MIN_PER_SIDE), so a line this screen publishes is
  // one the Evidence panel publishes too.
  const settled = patterns.settled_after ?? null;
  const early = new Set((contrasts?.contrasts ?? []).filter((c) => c.status === "not_enough_data").map((c) => c.key));

  return (
    // Focusable, because nothing else on this screen is: the page scrolls in
    // the shell's main region, and with no focusable element inside it a
    // keyboard could not scroll it at all (axe scrollable-region-focusable).
    <article className="mx-auto max-w-[120ch] px-8 py-6" tabIndex={0} aria-labelledby="patterns-title">
      <p className="studio-label">Patterns</p>
      <h1 id="patterns-title" className="studio-title mt-2">What your own posts suggest</h1>
      <p className="mt-2 text-[13px] leading-relaxed text-ink-secondary">
        Each line compares your posts that have a form with those that do not, by median reactions, across your{" "}
        {patterns.posts_compared} posts whose figures have settled, with reactions recorded. These are differences
        between your posts, not causes: treat a large one as something to try, not a rule.
        {/* Both lists now ask for the same number of posts a side, so nothing
            is published that the panel beside it would suppress, and a line
            below that number is listed as not enough rather than tagged. */}
        {` Each side needs ${patterns.min_per_side} posts before a line is shown.`}
        {settled &&
          (settled.measured
            ? ` Settled means ${Math.round(settled.hours / 24)} days or older, measured from your own ${settled.posts} posts' readings.`
            : ` Settled means ${Math.round(settled.hours / 24)} days or older, which the studio assumes until your readings can say.`)}
      </p>
      {/* Posts with no reactions recorded are left out because of that, not
          because of their age, and the screen says which. */}
      {(unread.settled_without_reactions ?? 0) > 0 && (
        <p className="studio-meta mt-2 text-[10px] leading-snug text-ink-muted">
          {unread.settled_without_reactions} MORE {unread.settled_without_reactions === 1 ? "POST IS" : "POSTS ARE"} LEFT
          OUT: NO REACTIONS ARE RECORDED FOR {unread.settled_without_reactions === 1 ? "IT" : "THEM"}
          {(unread.settled_without_reactions_from_archive ?? 0) > 0 ? ", AS LINKEDIN\u2019S ARCHIVE DOES NOT INCLUDE THEM" : ""}.
          PRESS IMPORT YOUR HISTORY IN SETUP SO THE BRIDGE READS THEM.
        </p>
      )}

      <div className="mt-5 grid gap-x-6 gap-y-5 lg:grid-cols-2 xl:grid-cols-3">
        <div className="min-w-0">
          <section>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="studio-label mb-2">Went with more or fewer reactions</p>
              {clean.length > 1 && (
                <div className="flex items-center gap-1" role="group" aria-label="Order">
                  {(
                    [
                      { key: "difference", label: "Biggest difference" },
                      { key: "sample", label: "Most posts" },
                    ] as const
                  ).map((candidate) => (
                    <button
                      key={candidate.key}
                      type="button"
                      onClick={() => setPatternOrder(candidate.key)}
                      aria-pressed={patternOrder === candidate.key}
                      className={cn(
                        "rounded-full border px-2.5 py-0.5 text-[11px]",
                        patternOrder === candidate.key
                          ? "border-edge-strong bg-soft text-ink-primary"
                          : "border-edge text-ink-muted hover:text-ink-secondary",
                      )}
                    >
                      {candidate.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {clean.length ? (
              <ul className="flex flex-col divide-y divide-edge border-y border-edge">
                {clean.map((p) => (
                  <PatternRow
                    key={p.key}
                    pattern={p}
                    early={early.has(p.key)}
                    expanded={expandedPattern === p.key}
                    onToggle={() => setExpandedPattern((current) => (current === p.key ? null : p.key))}
                  />
                ))}
              </ul>
            ) : same.length ? (
              <Note>NO FORM WENT WITH A DIFFERENCE YOUR OWN POSTS CAN SEPARATE.</Note>
            ) : confounded.length ? (
              <Note>NO PATTERN YET HAS POSTS FROM THE SAME PERIOD ON BOTH SIDES. THE LINES BELOW MAY BE ABOUT WHEN YOU POSTED.</Note>
            ) : (
              <Note>NO FORM HAS ENOUGH POSTS WITH REACTIONS RECORDED ON BOTH SIDES YET.</Note>
            )}
          </section>

          {same.length > 0 && (
            <section className="mt-5">
              <p className="studio-label mb-1">No difference your own posts can separate</p>
              <p className="mb-2 text-[12px] leading-snug text-ink-muted">
                These forms were compared and came out close enough to be the same. Nothing here is a finding.
              </p>
              <ul className="flex flex-col divide-y divide-edge border-y border-edge">
                {same.map((p) => (
                  <PatternRow key={p.key} pattern={p} early={early.has(p.key)} muted expanded={expandedPattern === p.key} onToggle={() => setExpandedPattern((current) => (current === p.key ? null : p.key))} />
                ))}
              </ul>
            </section>
          )}

          {confounded.length > 0 && (
            <section className="mt-5">
              <p className="studio-label mb-1">Mixed up with when you posted</p>
              <p className="mb-2 text-[12px] leading-snug text-ink-muted">
                The posts on each side of these come mostly from different years, when your account and audience were
                different, so the difference may be about the time rather than the form.
              </p>
              <ul className="flex flex-col divide-y divide-edge border-y border-edge">
                {confounded.map((p) => (
                  <PatternRow key={p.key} pattern={p} early={early.has(p.key)} muted expanded={expandedPattern === p.key} onToggle={() => setExpandedPattern((current) => (current === p.key ? null : p.key))} />
                ))}
              </ul>
            </section>
          )}

          {unmeasured.length > 0 && (
            <p className="studio-meta mt-3 text-[10px] leading-snug text-ink-muted">
              NO RATIO CAN BE MEASURED FOR:{" "}
              {unmeasured
                .map((p) => `${p.label.toUpperCase()} (MEDIAN ${p.without_median} REACTIONS ON THE ${p.without_posts} POSTS WITHOUT IT)`)
                .join("; ")}
              . A MEDIAN OF 0 ON ONE SIDE LEAVES NOTHING TO COMPARE AGAINST.
            </p>
          )}

          {patterns.not_enough_posts.length > 0 && (
            <p className="studio-meta mt-3 text-[10px] leading-snug text-ink-muted">
              NOT ENOUGH POSTS TO COMPARE:{" "}
              {patterns.not_enough_posts
                .map((p) => `${p.label.toUpperCase()} (${p.with_posts} WITH, ${p.without_posts} WITHOUT)`)
                .join("; ")}
              . EACH SIDE NEEDS {patterns.min_per_side}.
            </p>
          )}
        </div>

        <div className="min-w-0">
          <section>
            <p className="studio-label">Cadence</p>
            <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 border-y border-edge py-3 sm:grid-cols-4">
              <Stat label="Posts" value={`${cadence.posts}`} />
              <Stat label="Since last post" value={gapOrNotMeasured(cadence.days_since_last)} />
              <Stat label="Usual gap" value={gapOrNotMeasured(cadence.median_gap_days)} />
              <Stat
                label="Queued, next 14 days"
                value={`${cadence.queue?.scheduled_next_14_days ?? 0} of ${Math.min(cadence.queue?.weekly_slots ?? 0, 99) * 2} slots`}
              />
            </dl>
            {cadence.longest_gap && (
              <p className="mt-2 text-[12px] text-ink-muted">
                Longest gap: {gapOrNotMeasured(cadence.longest_gap.days)}, {cadence.longest_gap.from} to {cadence.longest_gap.to}.
              </p>
            )}

            <MonthStrip months={cadence.by_month ?? []} />

            <div className="mt-4">
              <p className="studio-meta mb-1.5 text-[10px] text-ink-muted">POSTS BY WEEKDAY</p>
              <div className="flex gap-3">
                {(cadence.by_weekday ?? []).map((d) => (
                  <div key={d.day} className="text-center">
                    <p className="text-[13px] tabular-nums text-ink-primary">{d.posts}</p>
                    <p className="studio-meta text-[10px] text-ink-muted">{d.day.toUpperCase()}</p>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-[12px] leading-snug text-ink-muted">
                No best day is named. You chose the days you posted on, and a few posts per day cannot separate the day from
                everything else about those posts.
              </p>
            </div>
          </section>
        </div>

        <div className="min-w-0">
          <SettleCurveSection curve={patterns.settle_curve} settled={settled} />
        </div>
      </div>

      {attribution && (
        <TopicAttributionSection attribution={attribution} sort={topicSort} onSort={setTopicSort} />
      )}
    </article>
  );
}

/**
 * How your posts settle, measured.
 *
 * The studio holds 362,996 readings of how each post grew and nothing read
 * them: two modules assumed "mostly arrived by a week" and the screens
 * judged posts against that guess. This is the creator's own curve, and the
 * age their figures settle at is read off it rather than assumed.
 */
function SettleCurveSection({ curve, settled }: { curve?: SettleCurve; settled: SettledAfter | null }) {
  if (!curve || !curve.points.length) return null;
  const enough = curve.points.filter((point) => point.posts >= curve.min_posts_per_bucket);
  if (!enough.length) {
    return (
      <section>
        <p className="studio-label mb-1">How your posts settle</p>
        <Note>
          NOT ENOUGH READINGS YET TO MEASURE YOUR OWN SETTLE CURVE: EACH AGE NEEDS {curve.min_posts_per_bucket}{" "}
          POSTS READ NEAR IT. UNTIL THEN THE STUDIO ASSUMES A WEEK.
        </Note>
      </section>
    );
  }
  return (
    <section>
      <p className="studio-label mb-1">How your posts settle</p>
      <p className="mb-2 text-[12px] leading-snug text-ink-muted">
        The share of a post&rsquo;s final figures it had reached by each age, measured from {curve.posts.toLocaleString()}{" "}
        of your own posts&rsquo; readings.{" "}
        {curve.measured_hours
          ? `Your posts reach ${Math.round(curve.settled_share * 100)}% of their reactions by ${
              curve.measured_hours >= 24
                ? `${Math.round(curve.measured_hours / 24)} days`
                : `${curve.measured_hours} hours`
            }, which is what settled means here.`
          : "No age yet holds enough posts to say when they settle, so the studio assumes a week."}
      </p>
      <table className="w-full text-left text-[12px]">
        <thead>
          <tr className="studio-label border-b border-edge text-[10px]">
            <th scope="col" className="py-1.5 font-normal">Age</th>
            <th scope="col" className="py-1.5 text-right font-normal">Reactions</th>
            <th scope="col" className="py-1.5 text-right font-normal">Impressions</th>
            <th scope="col" className="py-1.5 text-right font-normal">Posts</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-edge">
          {enough.map((point) => (
            <tr key={point.age_hours} className={cn(settled && point.age_hours === curve.measured_hours && "text-ink-primary")}>
              <td className="py-1 tabular-nums text-ink-secondary">
                {/* Hours up to three days, then days: 36 and 48 hours both
                    read "2d" rounded, and two rows cannot carry one label. */}
                {point.age_hours < 72 ? `${point.age_hours}h` : `${Math.round(point.age_hours / 24)}d`}
              </td>
              <td className="py-1 text-right tabular-nums text-ink-secondary">
                {Math.round(point.reactions_share * 100)}%
              </td>
              <td className="py-1 text-right tabular-nums text-ink-secondary">
                {Math.round(point.impressions_share * 100)}%
              </td>
              <td className="py-1 text-right tabular-nums text-ink-muted">{point.posts.toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {enough.length < curve.points.length && (
        <Note>
          {curve.points.length - enough.length} MORE{" "}
          {curve.points.length - enough.length === 1 ? "AGE IS" : "AGES ARE"} LEFT OUT: FEWER THAN{" "}
          {curve.min_posts_per_bucket} OF YOUR POSTS WERE READ NEAR{" "}
          {curve.points.length - enough.length === 1 ? "IT" : "THEM"}.
        </Note>
      )}
    </section>
  );
}

/** The plain word for a line's own verdict (results.difference), never a rank. */
function verdictWord(pattern: PatternFinding): string {
  switch (pattern.difference?.verdict) {
    case "more":
      return "went with more reactions";
    case "fewer":
      return "went with fewer reactions";
    case "none":
      return "no difference your own posts can separate";
    case "too_few_posts":
      return "not enough posts to say";
    case "not_measured":
      return "has no ratio: the posts without it have a median of 0 reactions";
    default:
      return "was not judged";
  }
}

function PatternRow({
  pattern,
  early = false,
  muted = false,
  expanded = false,
  onToggle,
}: {
  pattern: PatternFinding;
  early?: boolean;
  muted?: boolean;
  expanded?: boolean;
  onToggle: () => void;
}) {
  const ratio = pattern.ratio ?? null;
  return (
    <li className="py-2.5">
      <button type="button" onClick={onToggle} aria-expanded={expanded} className="w-full text-left">
        <div className="flex items-baseline justify-between gap-4">
          <p className={cn("text-[13px]", muted ? "text-ink-secondary" : "text-ink-primary")}>{pattern.label}</p>
          {ratio !== null && (
            <p
              className={cn(
                "studio-meta shrink-0 text-[11px] tabular-nums",
                muted ? "text-ink-muted" : ratioTone(ratio, "text-ink-secondary"),
              )}
            >
              {ratio.toFixed(1)}x
            </p>
          )}
        </div>
        <p className="studio-meta mt-0.5 text-[10px] text-ink-muted">
          MEDIAN {pattern.with_median} REACTIONS ON {pattern.with_posts} POSTS WITH IT, {pattern.without_median} ON{" "}
          {pattern.without_posts} WITHOUT
          {pattern.different_period && ` · MOSTLY ${pattern.typical_year_with} AGAINST MOSTLY ${pattern.typical_year_without}`}
          {early && " · EARLY"}
        </p>
      </button>
      {expanded && (
        <p className="mt-1.5 border-l border-edge pl-3 text-[12px] leading-snug text-ink-secondary">
          This form {verdictWord(pattern)}, from {pattern.with_posts} posts with it against{" "}
          {pattern.without_posts} without. Each side needs at least {pattern.difference?.min_per_side ?? "a few"}{" "}
          posts before a line like this is shown at all.
        </p>
      )}
    </li>
  );
}

const TOPIC_COLUMNS: { key: TopicSortKey; label: string; align: "left" | "right" }[] = [
  { key: "topic", label: "Topic", align: "left" },
  { key: "posts", label: "Posts", align: "right" },
  { key: "total_reactions", label: "Reactions", align: "right" },
  { key: "people_engaged", label: "People captured", align: "right" },
  { key: "qualified_leads", label: "Qualified", align: "right" },
  { key: "lead_conversion_rate", label: "Share qualified", align: "right" },
];

function topicValue(t: TopicRow, key: TopicSortKey): number | string {
  switch (key) {
    case "topic":
      return t.topic;
    case "posts":
      return t.post_count ?? t.posts_count ?? 0;
    case "people_engaged":
      return t.people_engaged ?? 0;
    case "lead_conversion_rate":
      return t.lead_conversion_rate ?? -1;
    default:
      return (t[key] as number | undefined) ?? 0;
  }
}

function TopicAttributionSection({
  attribution,
  sort,
  onSort,
}: {
  attribution: TopicAttributionInsights;
  sort: { key: TopicSortKey; dir: "asc" | "desc" };
  onSort: (next: { key: TopicSortKey; dir: "asc" | "desc" }) => void;
}) {
  // Computed before the early return below, so this hook runs on every
  // render of this component rather than being skipped on the renders that
  // take the cold start branch (the rule React hooks enforce).
  const topics = useMemo(() => {
    const rows = [...(attribution.topics as TopicRow[])];
    rows.sort((a, b) => {
      const av = topicValue(a, sort.key);
      const bv = topicValue(b, sort.key);
      const cmp = typeof av === "string" || typeof bv === "string" ? String(av).localeCompare(String(bv)) : av - bv;
      return sort.dir === "asc" ? cmp : -cmp;
    });
    return rows;
  }, [attribution.topics, sort]);

  if (attribution.status === "cold_start" || !attribution.topics.length) {
    return (
      <section className="mt-10">
        <p className="studio-label">Topic to Qualified Lead Attribution</p>
        <p className="mt-2 text-[13px] text-ink-secondary">{attribution.summary_sentence}</p>
        <Note>PUBLISH OR INGEST POSTS TO VIEW QUALIFIED LEAD ATTRIBUTION BY TOPIC.</Note>
      </section>
    );
  }

  function toggle(key: TopicSortKey) {
    onSort({ key, dir: sort.key === key && sort.dir === "desc" ? "asc" : "desc" });
  }

  return (
    <section className="mt-8">
      <p className="studio-label">Topic to Qualified Lead Attribution</p>
      <h2 className="studio-title mt-2 text-[15px]">Which topics bring qualified pipeline</h2>
      <p className="mt-1 text-[13px] leading-relaxed text-ink-secondary">
        {attribution.summary_sentence}
      </p>
      {/* The topics are words, not meanings, and the reader is told so. They
          were four fixed software buckets, so a bakery's posts all landed in
          one of them. */}
      <p className="mt-1 text-[12px] leading-snug text-ink-muted">
        Topics are the {(attribution as { grouping?: string }).grouping ?? "words that recur across your own posts"}.
        A post goes under the first of them it mentions, and one that mentions none goes under Other posts. This is a
        keyword grouping, not a reading of what a post means.
      </p>
      {/* Scrolls sideways at phone width, so it takes focus to scroll by keyboard. */}
      <div className="mt-4 overflow-x-auto border-y border-edge" tabIndex={0} role="region" aria-label="Topics">
        <table className="w-full text-left text-[12px]">
          <thead>
            <tr className="border-b border-edge text-[10px] text-ink-muted uppercase">
              {TOPIC_COLUMNS.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  aria-sort={sort.key === column.key ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}
                  className={cn("py-2 px-3 font-normal first:pl-0 first:pr-4 last:pr-0", column.align === "right" && "text-right")}
                >
                  <button
                    type="button"
                    onClick={() => toggle(column.key)}
                    className={cn(
                      "inline-flex items-center gap-1 uppercase hover:text-ink-secondary",
                      column.align === "right" && "flex-row-reverse",
                    )}
                  >
                    {column.label}
                    {sort.key === column.key ? (
                      <ChevronDown className={cn("size-3", sort.dir === "asc" && "rotate-180")} aria-hidden="true" />
                    ) : (
                      <ChevronsUpDown className="size-3 opacity-50" aria-hidden="true" />
                    )}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-edge">
            {topics.map((t) => {
              const count = t.post_count ?? t.posts_count ?? 0;
              // Qualified people over the people captured on the topic's posts,
              // so it cannot pass 100%. It was qualified leads over posts, which
              // read 600% for three people who each commented and reacted.
              const rate = t.lead_conversion_rate;
              return (
                <tr key={t.topic} className="py-2">
                  <td className="py-2.5 pr-4 text-ink-primary font-medium">{t.topic}</td>
                  <td className="py-2.5 px-3 text-right tabular-nums text-ink-secondary">{count}</td>
                  <td className="py-2.5 px-3 text-right tabular-nums text-ink-secondary">{t.total_reactions}</td>
                  <td className="py-2.5 px-3 text-right tabular-nums text-ink-secondary">{t.people_engaged ?? 0}</td>
                  <td className="py-2.5 px-3 text-right tabular-nums text-ink-primary font-semibold">{t.qualified_leads}</td>
                  <td className="py-2.5 pl-3 text-right tabular-nums text-ink-secondary">
                    {rate == null ? <span className="text-ink-muted">not measured</span> : `${(rate * 100).toFixed(0)}%`}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function MonthStrip({ months }: { months: { month: string; posts: number }[] }) {
  if (!months.length) return null;
  const peak = Math.max(1, ...months.map((m) => m.posts));
  return (
    <div className="mt-6">
      <p className="studio-meta mb-1.5 text-[10px] text-ink-muted">
        POSTS BY MONTH, {months[0].month} TO {months[months.length - 1].month}. THE TALLEST BAR IS {peak}{" "}
        {peak === 1 ? "POST" : "POSTS"}
      </p>
      <div className="flex h-16 items-end gap-px overflow-x-auto" role="img" aria-label="Posts per month" tabIndex={0}>
        {months.map((m) => (
          <div
            key={m.month}
            title={`${m.month}: ${m.posts} post${m.posts === 1 ? "" : "s"}`}
            className={cn("w-2 shrink-0 rounded-t-sm", m.posts ? "bg-ink-secondary" : "bg-edge")}
            style={{ height: m.posts ? `${Math.max(12, (m.posts / peak) * 100)}%` : "3px" }}
          />
        ))}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] text-ink-muted">{label}</dt>
      <dd className="text-[14px] tabular-nums text-ink-primary">{value}</dd>
    </div>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return <p className="studio-meta text-[10px] leading-snug text-ink-muted">{children}</p>;
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid h-full place-items-center px-8">
      <p className="studio-meta max-w-[40ch] text-center leading-relaxed text-ink-muted">{children}</p>
    </div>
  );
}
