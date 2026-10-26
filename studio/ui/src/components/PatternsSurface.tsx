import { useEffect, useState } from "react";
import {
  fetchPatternsInsights,
  fetchContrastInsights,
  type ContrastFinding,
  type PatternsInsights,
  type ContrastInsights,
  type SettleCurve,
  type SettledAfter,
} from "@/lib/api";
import { useStudioBack } from "@/lib/refresh";
import { ratioTone } from "@/lib/results";
import { cn } from "@/lib/utils";
import { EmptySurface } from "./EmptySurface";

/**
 * Patterns: what your own posts suggest.
 *
 * Patterns compare your week-old posts that have a form against those that do
 * not, by median reactions, always with both counts. The wording is "went
 * with", never "causes", and a pattern whose two sides come from different
 * periods is marked, because then the difference may be about when you
 * posted rather than how.
 *
 * Every line is the contrast engine's own record (contrast_engine), the
 * records the Composer's Evidence panel is built from, so a line this screen
 * calls a finding is one the panel calls a finding. Your topics are forms
 * too: the posts that mention a topic's word against those that do not,
 * through the same engine. They were a table of qualified leads per topic,
 * which ranked a keyword guess about job titles (cycle 4, decision 7).
 *
 * How steadily you post is the Queue's: this screen drew the same cadence
 * payload as the Queue's "Against your own rhythm" a second time, and the
 * week lives on the Queue (cycle 4, track 3, batch 1).
 */
export function PatternsSurface({ onOpenSetup }: { onOpenSetup?: () => void } = {}) {
  const [patterns, setPatterns] = useState<PatternsInsights | null>(null);
  const [contrasts, setContrasts] = useState<ContrastInsights | null>(null);
  const [failed, setFailed] = useState(false);
  // Read again when the studio answers after an outage, so a screen that
  // failed while it was down does not stay failed once it is back.
  const back = useStudioBack();

  useEffect(() => {
    Promise.all([fetchPatternsInsights(), fetchContrastInsights().catch(() => null)])
      .then(([p, co]) => {
        setPatterns(p);
        setContrasts(co);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, [back]);

  if (failed && !patterns) return <Centered>PATTERNS ARE UNAVAILABLE. IS THE STUDIO RUNNING?</Centered>;
  if (!patterns) return <Centered>LOADING PATTERNS</Centered>;
  if (!patterns.posts_held) {
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
  const settled = contrasts?.settled_after ?? patterns.settled_after ?? null;
  const minPerSide = contrasts?.min_arm_size ?? patterns.min_per_side;

  return (
    // Focusable, because nothing else on this screen is: the page scrolls in
    // the shell's main region, and with no focusable element inside it a
    // keyboard could not scroll it at all (axe scrollable-region-focusable).
    <article className="mx-auto max-w-[120ch] px-8 py-6" tabIndex={0} aria-labelledby="patterns-title">
      <p className="studio-label">Patterns</p>
      <h1 id="patterns-title" className="studio-title mt-2">What your own posts suggest</h1>
      <p className="mt-2 text-[13px] leading-relaxed text-ink-secondary">
        Each line compares your posts that have a form with those that do not, by median reactions, across your{" "}
        {contrasts?.settled_posts_count ?? patterns.posts_compared} posts whose figures have settled, with reactions
        recorded. These are differences between your posts, not causes: treat a large one as something to try, not a
        rule.
        {/* The engine's own minimum a side, which the Evidence panel uses
            too, so nothing is published here that the panel would suppress,
            and a line below it is listed as not enough rather than tagged. */}
        {` Each side needs ${minPerSide} posts before a line is shown.`}
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
          <Comparisons lines={contrasts?.contrasts} minPerSide={minPerSide} noun="FORM" />
        </div>

        <div className="min-w-0">
          <section aria-labelledby="patterns-topics">
            <p id="patterns-topics" className="studio-label mb-1">
              Your topics, compared the same way
            </p>
            {/* The topics are words, not meanings, and the reader is told so.
                They were four fixed software buckets, so a bakery's posts all
                landed in one of them. */}
            <p className="mb-3 text-[12px] leading-snug text-ink-muted">
              The words and hashtags that recur across your own posts, each compared like a form: your settled posts
              that mention it against those that do not. A keyword match, not a reading of what a post means.
            </p>
            {contrasts && !(contrasts.topics ?? []).length ? (
              <Note>NO WORD RECURS ACROSS ENOUGH OF YOUR POSTS TO BE A TOPIC YET.</Note>
            ) : (
              <Comparisons lines={contrasts?.topics} minPerSide={minPerSide} noun="TOPIC" />
            )}
          </section>
        </div>

        <div className="min-w-0">
          <SettleCurveSection curve={patterns.settle_curve} settled={settled} />
        </div>
      </div>
    </article>
  );
}

/**
 * One list of the engine's records, in its buckets: what went with more or
 * fewer reactions, what made no difference, what is mixed up with when you
 * posted, what has no ratio, and what the engine abstained on.
 */
function Comparisons({
  lines,
  minPerSide,
  noun,
}: {
  /** Undefined when the engine's answer did not come back. */
  lines: ContrastFinding[] | undefined;
  minPerSide: number;
  /** FORM or TOPIC, in the notes. */
  noun: "FORM" | "TOPIC";
}) {
  // How the "went with more or fewer reactions" list orders itself: by how
  // far from 1x the ratio sits, or by how many posts the line rests on, for
  // a creator who trusts a bigger sample over a bigger number.
  const [order, setOrder] = useState<"difference" | "sample">("difference");
  const [expanded, setExpanded] = useState<string | null>(null);
  if (!lines) {
    // A read that did not come back is not an empty comparison.
    return <Note>THE COMPARISONS COULD NOT BE READ. THEY ARE READ AGAIN WHEN THE STUDIO ANSWERS.</Note>;
  }
  const verdict = (c: ContrastFinding) => c.difference?.verdict;
  const conclusive = lines.filter((c) => c.status === "conclusive");
  // A line whose own verdict is "none" is a difference too small for this
  // creator's posts to separate (results.difference), and it is said rather
  // than printed as a finding: a 1.1x line over 1,417 posts read as a rule to
  // follow when it is noise.
  const findings = conclusive.filter((c) => verdict(c) === "more" || verdict(c) === "fewer");
  const clean = [...findings].sort((a, b) =>
    order === "sample"
      ? b.n_with + b.n_without - (a.n_with + a.n_without)
      : Math.abs((b.ratio ?? 1) - 1) - Math.abs((a.ratio ?? 1) - 1),
  );
  const same = conclusive.filter((c) => verdict(c) === "none");
  // Enough posts on both sides, but no ratio: the posts without the form
  // have a median of 0 reactions, so there is nothing to divide by. Such a
  // line sat in the list of findings and, opened, was worded "not enough
  // posts to say", which is a different verdict. It is named for what it is.
  const unmeasured = conclusive.filter((c) => verdict(c) === "not_measured");
  const confounded = lines.filter((c) => c.status === "different_period");
  // The engine abstains below its minimum a side, and says with how many.
  const tooFew = lines.filter((c) => c.status === "not_enough_data");
  const toggle = (key: string) => setExpanded((current) => (current === key ? null : key));

  return (
    <>
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
                  onClick={() => setOrder(candidate.key)}
                  aria-pressed={order === candidate.key}
                  className={cn(
                    "rounded-full border px-2.5 py-0.5 text-[11px]",
                    order === candidate.key
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
            {clean.map((c) => (
              <PatternRow key={c.key} line={c} expanded={expanded === c.key} onToggle={() => toggle(c.key)} />
            ))}
          </ul>
        ) : same.length ? (
          <Note>NO {noun} WENT WITH A DIFFERENCE YOUR OWN POSTS CAN SEPARATE.</Note>
        ) : confounded.length ? (
          <Note>NO {noun} YET HAS POSTS FROM THE SAME PERIOD ON BOTH SIDES. THE LINES BELOW MAY BE ABOUT WHEN YOU POSTED.</Note>
        ) : (
          <Note>NO {noun} HAS ENOUGH POSTS WITH REACTIONS RECORDED ON BOTH SIDES YET.</Note>
        )}
      </section>

      {same.length > 0 && (
        <section className="mt-5">
          <p className="studio-label mb-1">No difference your own posts can separate</p>
          <p className="mb-2 text-[12px] leading-snug text-ink-muted">
            These were compared and came out close enough to be the same. Nothing here is a finding.
          </p>
          <ul className="flex flex-col divide-y divide-edge border-y border-edge">
            {same.map((c) => (
              <PatternRow key={c.key} line={c} muted expanded={expanded === c.key} onToggle={() => toggle(c.key)} />
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
            {confounded.map((c) => (
              <PatternRow key={c.key} line={c} muted expanded={expanded === c.key} onToggle={() => toggle(c.key)} />
            ))}
          </ul>
        </section>
      )}

      {unmeasured.length > 0 && (
        <p className="studio-meta mt-3 text-[10px] leading-snug text-ink-muted">
          NO RATIO CAN BE MEASURED FOR:{" "}
          {unmeasured
            .map((c) => `${c.label.toUpperCase()} (MEDIAN ${c.median_without} REACTIONS ON THE ${c.n_without} POSTS WITHOUT IT)`)
            .join("; ")}
          . A MEDIAN OF 0 ON ONE SIDE LEAVES NOTHING TO COMPARE AGAINST.
        </p>
      )}

      {tooFew.length > 0 && (
        <p className="studio-meta mt-3 text-[10px] leading-snug text-ink-muted">
          NOT ENOUGH POSTS TO COMPARE:{" "}
          {tooFew.map((c) => `${c.label.toUpperCase()} (${c.n_with} WITH, ${c.n_without} WITHOUT)`).join("; ")}
          . EACH SIDE NEEDS {minPerSide}.
        </p>
      )}
    </>
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
function verdictWord(line: ContrastFinding): string {
  switch (line.difference?.verdict) {
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

/** One comparison, as the contrast engine answered it. */
function PatternRow({
  line,
  muted = false,
  expanded = false,
  onToggle,
}: {
  line: ContrastFinding;
  muted?: boolean;
  expanded?: boolean;
  onToggle: () => void;
}) {
  const ratio = line.ratio ?? null;
  return (
    <li className="py-2.5">
      <button type="button" onClick={onToggle} aria-expanded={expanded} className="w-full text-left">
        <div className="flex items-baseline justify-between gap-4">
          <p className={cn("text-[13px]", muted ? "text-ink-secondary" : "text-ink-primary")}>{line.label}</p>
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
          MEDIAN {line.median_with} REACTIONS ON {line.n_with} POSTS WITH IT, {line.median_without} ON {line.n_without}{" "}
          WITHOUT
          {line.status === "different_period" &&
            ` · MOSTLY ${line.typical_year_with} AGAINST MOSTLY ${line.typical_year_without}`}
        </p>
      </button>
      {expanded && (
        <p className="mt-1.5 border-l border-edge pl-3 text-[12px] leading-snug text-ink-secondary">
          This form {verdictWord(line)}, from {line.n_with} posts with it against {line.n_without} without. Each side
          needs at least {line.difference?.min_per_side ?? line.min_required} posts before a line like this is shown at
          all.
        </p>
      )}
    </li>
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
