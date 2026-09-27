import { useEffect, useState } from "react";
import {
  fetchCadenceInsights,
  fetchPatternsInsights,
  type CadenceInsights,
  type PatternFinding,
  type PatternsInsights,
} from "@/lib/api";
import { cn } from "@/lib/utils";

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
export function PatternsSurface() {
  const [patterns, setPatterns] = useState<PatternsInsights | null>(null);
  const [cadence, setCadence] = useState<CadenceInsights | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    Promise.all([fetchPatternsInsights(), fetchCadenceInsights()])
      .then(([p, c]) => {
        setPatterns(p);
        setCadence(c);
      })
      .catch(() => setFailed(true));
  }, []);

  if (failed) return <Centered>PATTERNS ARE UNAVAILABLE. IS THE STUDIO RUNNING?</Centered>;
  if (!patterns || !cadence) return <Centered>LOADING PATTERNS</Centered>;
  if (!cadence.posts) return <Centered>NO POSTS OF YOURS HAVE BEEN IMPORTED. IMPORT THEM FROM SETUP.</Centered>;

  const clean = patterns.patterns.filter((p) => !p.different_period);
  const confounded = patterns.patterns.filter((p) => p.different_period);

  return (
    <article className="mx-auto max-w-[80ch] px-8 py-8">
      <p className="studio-label">Patterns</p>
      <h2 className="studio-title mt-2">What your own posts suggest</h2>
      <p className="mt-2 text-[13px] leading-relaxed text-ink-secondary">
        Each line compares your posts that have a form with those that do not, by median reactions, across your{" "}
        {patterns.posts_compared} posts at least a week old. These are differences between your posts, not causes: treat
        a large one as something to try, not a rule.
      </p>

      <section className="mt-6">
        <p className="studio-label mb-2">Went with more or fewer reactions</p>
        {clean.length ? (
          <ul className="flex flex-col divide-y divide-edge border-y border-edge">
            {clean.map((p) => (
              <PatternRow key={p.key} pattern={p} />
            ))}
          </ul>
        ) : (
          <Note>NO PATTERN YET HAS POSTS FROM THE SAME PERIOD ON BOTH SIDES. THE LINES BELOW MAY BE ABOUT WHEN YOU POSTED.</Note>
        )}
      </section>

      {confounded.length > 0 && (
        <section className="mt-6">
          <p className="studio-label mb-1">Mixed up with when you posted</p>
          <p className="mb-2 text-[12px] leading-snug text-ink-muted">
            The posts on each side of these come mostly from different years, when your account and audience were
            different, so the difference may be about the time rather than the form.
          </p>
          <ul className="flex flex-col divide-y divide-edge border-y border-edge">
            {confounded.map((p) => (
              <PatternRow key={p.key} pattern={p} muted />
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
    </article>
  );
}

function PatternRow({ pattern, muted = false }: { pattern: PatternFinding; muted?: boolean }) {
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
      </p>
    </li>
  );
}

function MonthStrip({ months }: { months: { month: string; posts: number }[] }) {
  if (!months.length) return null;
  const peak = Math.max(1, ...months.map((m) => m.posts));
  return (
    <div className="mt-6">
      <p className="studio-meta mb-1.5 text-[10px] text-ink-muted">POSTS BY MONTH, {months[0].month} TO {months[months.length - 1].month}</p>
      <div className="flex h-16 items-end gap-px overflow-x-auto" role="img" aria-label="Posts per month">
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
