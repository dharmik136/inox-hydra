import { useEffect, useState } from "react";
import {
  fetchCadenceInsights,
  fetchPatternsInsights,
  fetchContrastInsights,
  fetchTopicAttribution,
  type CadenceInsights,
  type PatternFinding,
  type PatternsInsights,
  type ContrastInsights,
  type TopicAttributionInsights,
} from "@/lib/api";
import { useStudioBack } from "@/lib/refresh";
import { cn } from "@/lib/utils";
import { EmptySurface } from "./EmptySurface";

/** A topic as the attribution route returns it: people counted once, and a rate only when someone was captured. */
type TopicRow = Omit<TopicAttributionInsights["topics"][number], "lead_conversion_rate"> & {
  people_engaged?: number;
  lead_conversion_rate: number | null;
};

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
  const clean = patterns.patterns.filter((p) => !p.different_period && verdict(p) !== "none");
  const same = patterns.patterns.filter((p) => !p.different_period && verdict(p) === "none");
  const confounded = patterns.patterns.filter((p) => p.different_period);
  // The same seven forms were compared twice on this screen: here, with 3
  // posts a side, and again below as "Binary feature comparisons", with 8 a
  // side and the words ABSTAIN and PER ARM. One list now, and one number of
  // posts a side (results.MIN_PER_SIDE), so a line this screen publishes is
  // one the Evidence panel publishes too.
  const settled = patterns.settled_after ?? null;
  const early = new Set(
    (contrasts?.contrasts ?? []).filter((c) => (c.status as string) === "not_enough_data").map((c) => c.key),
  );

  return (
    // Focusable, because nothing else on this screen is: the page scrolls in
    // the shell's main region, and with no focusable element inside it a
    // keyboard could not scroll it at all (axe scrollable-region-focusable).
    <article className="mx-auto max-w-[80ch] px-8 py-8" tabIndex={0} aria-labelledby="patterns-title">
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

      <section className="mt-6">
        <p className="studio-label mb-2">Went with more or fewer reactions</p>
        {clean.length ? (
          <ul className="flex flex-col divide-y divide-edge border-y border-edge">
            {clean.map((p) => (
              <PatternRow key={p.key} pattern={p} early={early.has(p.key)} />
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
        <section className="mt-6">
          <p className="studio-label mb-1">No difference your own posts can separate</p>
          <p className="mb-2 text-[12px] leading-snug text-ink-muted">
            These forms were compared and came out close enough to be the same. Nothing here is a finding.
          </p>
          <ul className="flex flex-col divide-y divide-edge border-y border-edge">
            {same.map((p) => (
              <PatternRow key={p.key} pattern={p} early={early.has(p.key)} muted />
            ))}
          </ul>
        </section>
      )}

      {confounded.length > 0 && (
        <section className="mt-6">
          <p className="studio-label mb-1">Mixed up with when you posted</p>
          <p className="mb-2 text-[12px] leading-snug text-ink-muted">
            The posts on each side of these come mostly from different years, when your account and audience were
            different, so the difference may be about the time rather than the form.
          </p>
          <ul className="flex flex-col divide-y divide-edge border-y border-edge">
            {confounded.map((p) => (
              <PatternRow key={p.key} pattern={p} early={early.has(p.key)} muted />
            ))}
          </ul>
        </section>
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

      <section className="mt-10">
        <p className="studio-label">Cadence</p>
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 border-y border-edge py-3 sm:grid-cols-4">
          <Stat label="Posts" value={`${cadence.posts}`} />
          <Stat label="Since last post" value={`${Math.round(cadence.days_since_last ?? 0)} days`} />
          <Stat label="Usual gap" value={cadence.median_gap_days != null ? `${Math.round(cadence.median_gap_days)} days` : "Unknown"} />
          <Stat
            label="Queued, next 14 days"
            value={`${cadence.queue?.scheduled_next_14_days ?? 0} of ${Math.min(cadence.queue?.weekly_slots ?? 0, 99) * 2} slots`}
          />
        </dl>
        {cadence.longest_gap && (
          <p className="mt-2 text-[12px] text-ink-muted">
            Longest gap: {Math.round(cadence.longest_gap.days)} days, {cadence.longest_gap.from} to {cadence.longest_gap.to}.
          </p>
        )}

        <MonthStrip months={cadence.by_month ?? []} />

        <div className="mt-6">
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

      {attribution && <TopicAttributionSection attribution={attribution} />}
    </article>
  );
}

function PatternRow({
  pattern,
  early = false,
  muted = false,
}: {
  pattern: PatternFinding;
  early?: boolean;
  muted?: boolean;
}) {
  const ratio = pattern.ratio ?? null;
  return (
    <li className="py-2.5">
      <div className="flex items-baseline justify-between gap-4">
        <p className={cn("text-[13px]", muted ? "text-ink-secondary" : "text-ink-primary")}>{pattern.label}</p>
        {ratio !== null && (
          <p
            className={cn(
              "studio-meta shrink-0 text-[11px] tabular-nums",
              muted ? "text-ink-muted" : ratio >= 1.2 ? "text-signal-green-text" : ratio <= 0.8 ? "text-signal-orange-text" : "text-ink-secondary",
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
    </li>
  );
}

function TopicAttributionSection({ attribution }: { attribution: TopicAttributionInsights }) {
  if (attribution.status === "cold_start" || !attribution.topics.length) {
    return (
      <section className="mt-10">
        <p className="studio-label">Topic to Qualified Lead Attribution</p>
        <p className="mt-2 text-[13px] text-ink-secondary">{attribution.summary_sentence}</p>
        <Note>PUBLISH OR INGEST POSTS TO VIEW QUALIFIED LEAD ATTRIBUTION BY TOPIC.</Note>
      </section>
    );
  }

  return (
    <section className="mt-10">
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
              <th className="py-2 pr-4 font-normal">Topic</th>
              <th className="py-2 px-3 text-right font-normal">Posts</th>
              <th className="py-2 px-3 text-right font-normal">Reactions</th>
              <th className="py-2 px-3 text-right font-normal">People captured</th>
              <th className="py-2 px-3 text-right font-normal">Qualified</th>
              <th className="py-2 pl-3 text-right font-normal">Share qualified</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-edge">
            {(attribution.topics as TopicRow[]).map((t) => {
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
