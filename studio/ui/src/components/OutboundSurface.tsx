import { useEffect, useState } from "react";
import { fetchOutboundInsights, type OutboundInsights } from "@/lib/api";
import { useStudioBack } from "@/lib/refresh";
import { EmptySurface } from "./EmptySurface";

/**
 * Outbound: whose content you spend your attention on, and whether it comes
 * back.
 *
 * Built from your own reactions and comments on other people's posts. Who
 * "engaged back" is matched by display name, because a reaction records the
 * author's name and not their profile, and the screen says so. "One-way" is
 * shown only once the studio has read who engaged with at least half your
 * posts; before that it would list everyone, on the strength of the studio
 * not having looked.
 */
export function OutboundSurface({ onOpenSetup }: { onOpenSetup?: () => void } = {}) {
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
          reads the authors and adds them to these.
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

  return (
    <article className="mx-auto max-w-[80ch] px-8 py-8">
      <p className="studio-label">Outbound</p>
      <h1 className="studio-title mt-2">Where your attention goes</h1>
      <p className="mt-2 text-[13px] leading-relaxed text-ink-secondary">
        {totals.reactions.toLocaleString()} reactions and {totals.comments.toLocaleString()} comments on posts by{" "}
        {totals.authors.toLocaleString()} people and pages.
        {totals.without_author > 0 &&
          ` ${totals.without_author.toLocaleString()} more, from LinkedIn\u2019s archive or without an author recorded, ` +
            "are not ranked: run \u201cPosts you reacted to\u201d and \u201cComments you left\u201d in Setup to add their authors."}
      </p>

      <section className="mt-6 grid gap-6 sm:grid-cols-2">
        <div>
          <p className="studio-label mb-2">Engaged back</p>
          {data.reciprocal.length ? (
            <ul className="flex flex-col gap-1 text-[13px] text-ink-secondary">
              {data.reciprocal.map((name) => (
                <li key={name}>{name}</li>
              ))}
            </ul>
          ) : (
            <Note>NOBODY YOU ENGAGE WITH HAS BEEN SEEN ON YOUR POSTS YET.</Note>
          )}
        </div>
        <div>
          <p className="studio-label mb-2">One-way</p>
          {coverage.one_way_judged ? (
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
        </div>
      </section>

      <section className="mt-8">
        <p className="studio-label mb-2">Most engaged with</p>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[12px]">
            <thead>
              <tr className="studio-meta text-[10px] text-ink-muted">
                <th className="py-1.5 font-normal">NAME</th>
                <th className="py-1.5 text-right font-normal">REACTIONS</th>
                <th className="py-1.5 text-right font-normal">COMMENTS</th>
                <th className="py-1.5 text-right font-normal">ON YOUR POSTS</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-edge border-y border-edge">
              {data.authors.map((author) => (
                <tr key={author.name}>
                  <td className="py-1.5 text-ink-primary">{author.name}</td>
                  <td className="py-1.5 text-right tabular-nums text-ink-secondary">{author.reactions}</td>
                  <td className="py-1.5 text-right tabular-nums text-ink-secondary">{author.comments}</td>
                  <td className="py-1.5 text-right tabular-nums text-ink-secondary">{author.engaged_back || "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="studio-meta mt-2 text-[10px] leading-snug text-ink-muted">
          &ldquo;ON YOUR POSTS&rdquo; IS MATCHED BY {data.matched_by.toUpperCase()}: A REACTION RECORDS THE AUTHOR&rsquo;S
          NAME, NOT THEIR PROFILE.
        </p>
      </section>
    </article>
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
