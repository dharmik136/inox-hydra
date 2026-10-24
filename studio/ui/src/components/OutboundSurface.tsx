import { useEffect, useState } from "react";
import { fetchOutboundInsights, type GoneQuietAuthor, type OutboundInsights } from "@/lib/api";
import { useStudioBack } from "@/lib/refresh";
import { formatLocalDay } from "@/lib/time";
import { EmptySurface } from "./EmptySurface";

/**
 * Outbound: whose content you spend your attention on, and whether it comes
 * back.
 *
 * Built from your own reactions and comments on other people's posts. A
 * reaction records the author's display name and not their profile, so who
 * "engaged back" is found by name: a name exactly one captured person answers
 * to is theirs, and a name several answer to says how many rather than adding
 * their engagement together. "One-way" and "gone quiet" are shown only once
 * the studio has read who engaged with at least half your posts; before that
 * both would list everyone, on the strength of the studio not having looked.
 *
 * Every author here came from one capture path: own_pages.js reading your own
 * Activity page while it is open. LinkedIn's own export, which Setup's
 * archive import reads, does not name the author of a post you reacted to, so
 * an author only ever arrives the first way, one visit at a time. The rows an
 * archive import left without one are counted in the opening line and never
 * guessed into a name.
 *
 * Laid out across the window rather than down a reading column: this screen is
 * rows of names and counts, and it used 34% of the width it was given.
 */
export function OutboundSurface({
  onOpenSetup,
  onOpenLead,
}: { onOpenSetup?: () => void; onOpenLead?: (leadId: string) => void } = {}) {
  const [data, setData] = useState<OutboundInsights | null>(null);
  const [failed, setFailed] = useState(false);
  // Read again when the studio answers after an outage, so a screen that
  // failed while it was down does not stay failed once it is back.
  const back = useStudioBack();

  useEffect(() => {
    fetchOutboundInsights()
      .then((result) => {
        setData(result);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, [back]);

  if (failed && !data) return <Centered>OUTBOUND IS UNAVAILABLE. IS THE STUDIO RUNNING?</Centered>;
  if (!data) return <Centered>LOADING YOUR ACTIVITY</Centered>;
  const { totals, coverage } = data;
  if (!data.authors.length) {
    // LinkedIn's archive names the post but not its author, so an archive
    // import fills the totals and no author. This said "none imported"
    // right after Setup reported 15 comments and 25 reactions.
    if (totals.reactions + totals.comments > 0) {
      return (
        <EmptySurface label="Outbound" title="Where your attention goes" onOpenSetup={onOpenSetup}>
          {totals.reactions.toLocaleString()} reactions and {totals.comments.toLocaleString()} comments are imported,
          but LinkedIn&rsquo;s archive does not name the author of the posts they were on, so they cannot be ranked by
          person yet. In Setup, run &ldquo;Posts you reacted to&rdquo; and &ldquo;Comments you left&rdquo;: the bridge
          reads each card&rsquo;s author as it goes and adds them to these.
        </EmptySurface>
      );
    }
    return (
      <EmptySurface label="Outbound" title="Where your attention goes" onOpenSetup={onOpenSetup}>
        None of your reactions or comments have been imported yet. Import them in Setup to see whose
        posts you engage with, and which of those people engage back.
      </EmptySurface>
    );
  }

  const judged = coverage.one_way_judged;

  return (
    // tabIndex, because at phone width this screen is taller than the window
    // and the region that scrolls holds nothing focusable, so a keyboard could
    // not scroll it at all (axe: scrollable-region-focusable). Patterns and
    // Today solved the same thing the same way.
    <div className="px-6 py-6 lg:px-8" tabIndex={0} aria-labelledby="outbound-title">
      <header className="flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
        <div>
          <p className="studio-label">Outbound</p>
          <h1 id="outbound-title" className="studio-title mt-1">Where your attention goes</h1>
        </div>
        <p className="max-w-[62ch] text-[12px] leading-snug text-ink-secondary">
          {totals.reactions.toLocaleString()} reactions and {totals.comments.toLocaleString()} comments of yours, on
          posts by {totals.authors.toLocaleString()} people and pages.
          {totals.without_author > 0 &&
            ` ${totals.without_author.toLocaleString()} more are not ranked: LinkedIn’s archive does not name the author of a post you reacted to, so the bridge reads it from the card instead. Run “Posts you reacted to” and “Comments you left” in Setup.`}
        </p>
      </header>

      {/* Four figures, each one counted rather than derived from a sample. */}
      <dl className="mt-4 grid grid-cols-2 gap-px border border-edge bg-edge sm:grid-cols-4">
        <Figure label="Reactions you gave" value={totals.reactions.toLocaleString()} />
        <Figure label="Comments you left" value={totals.comments.toLocaleString()} />
        <Figure label="People and pages" value={totals.authors.toLocaleString()} />
        {/* Of the names that are one person's, not of every name: on a
            history where no name belongs to one captured person this read
            "0 of 1,540" and the reason was a footnote under the table. */}
        <Figure
          label={`Engaged back, of ${data.matched_names.toLocaleString()} named people`}
          value={`${data.reciprocal_count.toLocaleString()} of ${data.matched_names.toLocaleString()}`}
        />
      </dl>

      <div className="mt-4 grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <section>
          <p className="studio-label mb-2">Most engaged with</p>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[12px]">
              <thead>
                <tr className="studio-meta text-[10px] text-ink-muted">
                  <th className="py-1 font-normal">NAME</th>
                  <th className="py-1 font-normal">WHAT YOU LAST SAID TO THEM</th>
                  <th className="py-1 text-right font-normal">REACTIONS</th>
                  <th className="py-1 text-right font-normal">COMMENTS</th>
                  <th className="py-1 text-right font-normal">ON YOUR POSTS</th>
                  <th className="py-1 text-right font-normal">LAST FROM THEM</th>
                  <th className="py-1 text-right font-normal">LAST FROM YOU</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-edge border-y border-edge">
                {data.authors.map((author) => (
                  <tr key={author.name}>
                    <td className="py-1 text-ink-primary">
                      {/* Opens the person, so "they engaged back" can become a
                          reply. Plain text when the name is not one lead's
                          alone, because the match is by display name and a
                          wrong dossier is worse than none. */}
                      {author.lead_id && onOpenLead ? (
                        <button
                          type="button"
                          onClick={() => onOpenLead(author.lead_id as string)}
                          className="text-left text-ink-primary underline decoration-edge-strong underline-offset-2 transition-colors hover:text-signal-orange-text"
                        >
                          {author.name}
                        </button>
                      ) : (
                        author.name
                      )}
                      {author.gone_quiet && judged && (
                        <span className="studio-meta ml-2 text-[10px] text-signal-orange-text">QUIET</span>
                      )}
                    </td>
                    {/* Your own words, which is the half of "where your
                        attention goes" that a count cannot show. Reacting
                        without commenting leaves nothing to show, and that
                        reads as what it is rather than as a gap. */}
                    <td className="max-w-[46ch] truncate py-1 text-ink-secondary">
                      {author.last_comment ?? <span className="text-ink-muted">Only reactions</span>}
                    </td>
                    <td className="py-1 text-right tabular-nums text-ink-secondary">{author.reactions}</td>
                    <td className="py-1 text-right tabular-nums text-ink-secondary">{author.comments}</td>
                    {/* A name more than one captured person answers to is
                        not a match: the studio cannot tell which of them
                        engaged, so the row says that rather than adding them
                        together. */}
                    {author.named_people > 1 ? (
                      <td colSpan={2} className="py-1 text-right text-ink-muted">
                        {author.named_people} people of this name
                      </td>
                    ) : (
                      <>
                        <td className="py-1 text-right tabular-nums text-ink-secondary">{author.engaged_back || "0"}</td>
                        <td className="py-1 text-right text-ink-secondary">
                          {author.last_inbound_at
                            ? formatLocalDay(author.last_inbound_at)
                            : judged
                              ? "None"
                              : "Not read"}
                        </td>
                      </>
                    )}
                    <td className="py-1 text-right text-ink-secondary">
                      {formatLocalDay(author.last_outbound_at, "Not measured")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="studio-meta mt-2 text-[10px] leading-snug text-ink-muted">
            &ldquo;ON YOUR POSTS&rdquo; AND &ldquo;LAST FROM THEM&rdquo; ARE MATCHED BY {data.matched_by.toUpperCase()}:
            A REACTION RECORDS THE AUTHOR&rsquo;S NAME, NOT THEIR PROFILE.{" "}
            {data.shared_names > 0 &&
              `${data.shared_names} OF THESE NAMES BELONG TO MORE THAN ONE PERSON YOU HAVE CAPTURED, SO THEY ARE NOT MATCHED. `}
            {judged
              ? "“NONE” MEANS THE STUDIO READ YOUR POSTS’ ENGAGERS AND THIS ACCOUNT WAS NOT AMONG THEM."
              : "“NOT READ” MEANS THE STUDIO HAS NOT READ ENOUGH OF YOUR POSTS’ ENGAGERS TO SAY."}
          </p>
        </section>

        <div className="flex flex-col gap-5">
          <People label="Engaged back" names={data.reciprocal}>
            NOBODY YOU ENGAGE WITH HAS BEEN SEEN ON YOUR POSTS YET.
          </People>

          {/* Separate from one-way on purpose: this is attention that used to
              come back and has stopped, which is a different thing from
              attention that never came back, and reads as a different thing. */}
          <section>
            <p className="studio-label mb-2">Gone quiet</p>
            {judged ? (
              data.gone_quiet.length ? (
                <ul className="flex flex-col gap-1 text-[13px] text-ink-secondary">
                  {data.gone_quiet.map((author: GoneQuietAuthor) => (
                    <li key={author.name} className="flex items-baseline justify-between gap-3">
                      <span>{author.name}</span>
                      <span className="studio-meta shrink-0 text-[10px] text-ink-muted">
                        {author.days_since.toLocaleString()} DAYS
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <Note>
                  EVERYONE WHO HAS ENGAGED BACK HAS DONE SO WITHIN {data.gone_quiet_days} DAYS.
                </Note>
              )
            ) : (
              <Note>NOT JUDGED YET, FOR THE SAME REASON AS ONE-WAY.</Note>
            )}
            <p className="studio-meta mt-1 text-[10px] leading-snug text-ink-muted">
              ENGAGED BACK BEFORE, BUT NOT ON ANY POST OF YOURS IN {data.gone_quiet_days} DAYS.
            </p>
          </section>

          <section>
            <p className="studio-label mb-2">One-way</p>
            {judged ? (
              data.one_way.length ? (
                <ul className="flex flex-col gap-1 text-[13px] text-ink-secondary">
                  {data.one_way.map((name) => (
                    <li key={name}>{name}</li>
                  ))}
                </ul>
              ) : (
                <Note>EVERYONE YOU ENGAGE WITH OFTEN HAS ENGAGED BACK.</Note>
              )
            ) : (
              <Note>
                NOT JUDGED YET. THE STUDIO HAS READ WHO ENGAGED WITH {coverage.posts_read} OF YOUR{" "}
                {coverage.posts_with_engagement} POSTS, AND NEEDS AT LEAST HALF. OPEN YOUR POSTS IN THE BRIDGE BROWSER,
                OR USE POSTS TO OPEN THEM ONE BY ONE.
              </Note>
            )}
            <p className="studio-meta mt-1 text-[10px] leading-snug text-ink-muted">
              ENGAGED WITH THREE TIMES OR MORE, AND NEVER ONCE ON A POST OF YOURS.
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-ink px-3 py-1.5">
      <dt className="studio-meta text-[10px] text-ink-muted">{label.toUpperCase()}</dt>
      <dd className="text-[14px] tabular-nums text-ink-primary">{value}</dd>
    </div>
  );
}

function People({ label, names, children }: { label: string; names: string[]; children: React.ReactNode }) {
  return (
    <section>
      <p className="studio-label mb-2">{label}</p>
      {names.length ? (
        <ul className="flex flex-col gap-1 text-[13px] text-ink-secondary">
          {names.map((name) => (
            <li key={name}>{name}</li>
          ))}
        </ul>
      ) : (
        <Note>{children}</Note>
      )}
    </section>
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
