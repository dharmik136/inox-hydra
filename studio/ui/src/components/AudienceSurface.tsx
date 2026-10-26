import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Loader2, Search } from "lucide-react";
import {
  fetchAudience,
  fetchAudienceConnections,
  fetchAudienceCounts,
  type AudienceConnections,
  type AudienceCounts,
  type AudienceOverview,
  type AudiencePerson,
} from "@/lib/api";
import { useRefresh } from "@/lib/refresh";
import { formatLocalDay } from "@/lib/time";
import { cn } from "@/lib/utils";

/**
 * Audience: among the people the bridge has seen, who keeps coming back, who
 * has gone quiet, and who is already a connection?
 *
 * Leads is one person and the next step; this is the set. Every list is
 * ordered by facts, how many of your posts a person engaged with and how
 * recently the studio saw them do it, never by the ICP score.
 *
 * Each list says what it rests on, because none of it is complete: the bridge
 * reads who engaged with a post only when you open that post, so the repeat
 * list counts posts "whose engagers were read"; a week in which the bridge
 * read nothing says so rather than showing nobody new; the connections are
 * LinkedIn's archive as of the day you imported it.
 */

/** People drawn in each list before Show all; the server sends up to 25. */
const FIRST_SHOWN = 10;

/** Connections drawn per page of the search. */
const CONNECTIONS_SHOWN = 12;

/** A stored UTC time that may carry no zone ("2026-10-20 08:55:00"), as the browser should read it. */
function utc(stamp: string): string {
  return stamp.includes("T") || stamp.endsWith("Z") ? stamp : `${stamp.replace(" ", "T")}Z`;
}

function day(stamp: string | null | undefined, missing = "not seen"): string {
  return stamp ? formatLocalDay(utc(stamp)) : missing;
}

export function AudienceSurface({
  onOpenLead,
  onOpenSetup,
}: {
  onOpenLead?: (leadId: string) => void;
  onOpenSetup?: () => void;
} = {}) {
  const [view, setView] = useState<AudienceOverview | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    try {
      setView(await fetchAudience());
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);
  // Read again on coming back and after an outage. The set changes slowly,
  // so it is not polled while open.
  useRefresh(load);

  if (failed && !view) {
    return (
      <div className="grid h-full place-items-center px-8">
        <div className="max-w-[44ch] text-center">
          <p className="studio-label text-signal-orange-text">AUDIENCE IS UNAVAILABLE</p>
          <p className="mt-2 text-[13px] text-ink-muted">
            The studio is not answering, or refused this screen&apos;s request. Check that it is still running, then retry.
          </p>
          <button
            type="button"
            onClick={() => void load()}
            className="mt-4 rounded-md border border-edge bg-soft px-3 py-1.5 text-[12px] font-medium text-ink-primary hover:bg-raised"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!view) {
    return (
      <div className="grid h-full place-items-center px-8">
        <div className="flex items-center gap-2 text-ink-muted">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          <span className="studio-meta text-[11px]">READING WHO ENGAGED WITH YOUR POSTS</span>
        </div>
      </div>
    );
  }

  const { repeat, quiet, new_people: weeks, connections } = view;
  const thisWeek = weeks.weeks[weeks.weeks.length - 1];

  return (
    <div className="px-6 py-6 lg:px-8" tabIndex={0} aria-labelledby="audience-title">
      <header className="flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
        <div>
          <p className="studio-label">Audience</p>
          <h1 id="audience-title" className="studio-title mt-1">Who keeps coming back</h1>
        </div>
        <p className="max-w-[64ch] text-[12px] leading-snug text-ink-secondary">
          The people the bridge has seen engage with your posts, ordered by how many of your posts and how recently, never
          by score. The bridge reads who engaged with a post only when you open it, so each list says what it rests on.
        </p>
      </header>

      <dl className="mt-4 grid grid-cols-2 gap-px border border-edge bg-edge sm:grid-cols-4">
        <Figure label={`Repeat engagers, ${repeat.label}`} value={repeat.count.toLocaleString()} />
        <Figure
          label={`Gone quiet, since your last ${quiet.recent_posts} read posts began`}
          value={quiet.judged ? quiet.count.toLocaleString() : "not judged yet"}
        />
        <Figure
          label="New people this week, partial"
          value={thisWeek && thisWeek.read ? (thisWeek.new ?? 0).toLocaleString() : "nothing read yet"}
        />
        <Figure
          label={connections.as_of ? `Connections, as of ${day(connections.as_of)}` : "Connections"}
          value={connections.count ? connections.count.toLocaleString() : "no archive imported"}
        />
      </dl>

      {view.own_posts === 0 ? (
        <div className="mt-6 max-w-[60ch]">
          <p className="text-[13px] leading-relaxed text-ink-secondary">
            Once your posts are imported in Setup and the bridge has read who engaged with them, the people appear here.
          </p>
          {onOpenSetup && (
            <button
              type="button"
              onClick={onOpenSetup}
              className="mt-3 rounded-md bg-signal-orange px-3 py-1.5 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110"
            >
              Go to Setup
            </button>
          )}
        </div>
      ) : (
        <div className="mt-4 grid items-start gap-5 md:grid-cols-2 xl:grid-cols-4">
          <Column title="Keep coming back">
            {repeat.people.length === 0 ? (
              <Muted>
                Nobody has engaged with {repeat.min_posts} or more of the {repeat.posts_read.toLocaleString()} posts whose
                engagers were read yet.
              </Muted>
            ) : (
              <>
                <Muted>
                  {repeat.count.toLocaleString()} people engaged with {repeat.min_posts} or more of your posts, {repeat.label}.
                </Muted>
                <div className="mt-2">
                  <People people={repeat.people} total={repeat.count} onOpenLead={onOpenLead} />
                </div>
              </>
            )}
          </Column>

          <Column
            title="Gone quiet"
            note={quiet.judged && quiet.since ? `not seen since ${day(quiet.since)}` : undefined}
          >
            {!quiet.judged ? (
              <Muted>
                Not judged until the engagers of {quiet.recent_posts} of your posts have been read; {quiet.posts_read} have
                been so far. Before that, &ldquo;not seen&rdquo; would only mean &ldquo;not looked&rdquo;.
              </Muted>
            ) : quiet.people.length === 0 ? (
              <Muted>
                Nobody who engaged with two or more of your posts has gone quiet since your last {quiet.recent_posts} posts
                whose engagers were read began, on {day(quiet.since)}.
              </Muted>
            ) : (
              <>
                <Muted>
                  Engaged with two or more of your posts, and not seen engaging since your last {quiet.recent_posts} posts
                  whose engagers were read began.
                </Muted>
                <div className="mt-2">
                  <People people={quiet.people} total={quiet.count} onOpenLead={onOpenLead} />
                </div>
              </>
            )}
          </Column>

          <Column title="New people by week" note="partial">
            <Muted>
              People the studio first saw engage with one of your posts, by the week it saw them, on the posts whose
              engagers were read. A week the bridge read nothing says so.
            </Muted>
            <table className="mt-2 w-full text-left text-[12px]">
              <thead>
                <tr className="studio-meta text-[10px] text-ink-muted">
                  <th className="py-1 font-normal">WEEK OF</th>
                  <th className="py-1 text-right font-normal">NEW PEOPLE</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-edge border-y border-edge">
                {[...weeks.weeks].reverse().map((week) => (
                  <tr key={week.week}>
                    <td className="py-0.5 text-ink-secondary">{formatLocalDay(`${week.week}T00:00:00Z`)}</td>
                    <td className={cn("py-0.5 text-right tabular-nums", week.read ? "text-ink-primary" : "text-ink-muted")}>
                      {week.read ? (week.new ?? 0).toLocaleString() : "nothing read"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Column>

          <Column
            title="Connections"
            note={connections.as_of ? `as of the archive of ${day(connections.as_of)}` : undefined}
          >
            <ConnectionsList summary={connections} onOpenLead={onOpenLead} onOpenSetup={onOpenSetup} />
          </Column>
        </div>
      )}

      <SecondLevel />
    </div>
  );
}

function People({
  people,
  total,
  onOpenLead,
}: {
  people: AudiencePerson[];
  total: number;
  onOpenLead?: (leadId: string) => void;
}) {
  const [all, setAll] = useState(false);
  const shown = all ? people : people.slice(0, FIRST_SHOWN);
  return (
    <>
      <ul className="flex flex-col divide-y divide-edge border-y border-edge">
        {shown.map((person) => (
          <li key={person.lead_id} className="py-1.5">
            {onOpenLead ? (
              <button
                type="button"
                onClick={() => onOpenLead(person.lead_id)}
                className="text-left text-[13px] font-medium text-ink-primary underline decoration-edge-strong underline-offset-2 hover:text-signal-orange-text"
              >
                {person.name ?? "No name recorded"}
              </button>
            ) : (
              <span className="text-[13px] font-medium text-ink-primary">{person.name ?? "No name recorded"}</span>
            )}
            {person.headline && <p className="truncate text-[11px] text-ink-muted">{person.headline}</p>}
            <p className="studio-meta text-[10px] text-ink-muted">
              {person.posts_engaged.toLocaleString()} OF YOUR POSTS · LATEST SEEN {day(person.latest_at).toUpperCase()}
            </p>
          </li>
        ))}
      </ul>
      {(people.length > FIRST_SHOWN || total > people.length) && (
        <p className="mt-1.5 text-[11px] text-ink-muted">
          {people.length > FIRST_SHOWN && (
            <button
              type="button"
              onClick={() => setAll(!all)}
              className="mr-2 underline decoration-edge-strong underline-offset-2 hover:text-ink-primary"
            >
              {all ? `Show the first ${FIRST_SHOWN}` : `Show ${people.length}`}
            </button>
          )}
          {total > people.length && `The first ${people.length.toLocaleString()} of ${total.toLocaleString()}.`}
        </p>
      )}
    </>
  );
}

function ConnectionsList({
  summary,
  onOpenLead,
  onOpenSetup,
}: {
  summary: AudienceOverview["connections"];
  onOpenLead?: (leadId: string) => void;
  onOpenSetup?: () => void;
}) {
  const [q, setQ] = useState("");
  const [page, setPage] = useState<AudienceConnections | null>(null);
  const [rows, setRows] = useState<AudienceConnections["connections"]>([]);
  const [failed, setFailed] = useState(false);
  const asked = useRef(0);

  // Asked again 250 ms after typing stops, and only the latest answer is kept.
  useEffect(() => {
    if (!summary.count) return;
    const ticket = ++asked.current;
    const timer = window.setTimeout(() => {
      fetchAudienceConnections(q)
        .then((answer) => {
          if (ticket !== asked.current) return;
          setPage(answer);
          setRows(answer.connections.slice(0, CONNECTIONS_SHOWN));
          setFailed(false);
        })
        .catch(() => ticket === asked.current && setFailed(true));
    }, q ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [q, summary.count]);

  if (!summary.count) {
    return (
      <>
        <Muted>
          No connections are held. They come from LinkedIn&apos;s data archive, which Setup imports; nothing else in the
          studio knows who you are connected to.
        </Muted>
        {onOpenSetup && (
          <button
            type="button"
            onClick={onOpenSetup}
            className="mt-2 rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary"
          >
            Go to Setup
          </button>
        )}
      </>
    );
  }

  const more = page ? page.connections.length > rows.length || page.next_offset !== null : false;

  return (
    <>
      <Muted>
        {summary.leads_matched.toLocaleString()} of your leads are connections, matched by profile.
        {summary.leads_by_member_id > 0 &&
          ` ${summary.leads_by_member_id.toLocaleString()} more the bridge knows only by a member number, which cannot be matched to the archive.`}
      </Muted>
      <label className="mt-2 flex items-center gap-2 rounded-md border border-edge bg-canvas px-2 py-1 text-[12px] text-ink-secondary focus-within:border-edge-strong">
        <Search className="size-3.5 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden="true" />
        <span className="sr-only">Search your connections</span>
        <input
          type="search"
          value={q}
          onChange={(event) => setQ(event.target.value)}
          placeholder="Name, company or role"
          className="min-w-0 flex-1 bg-transparent text-ink-primary outline-none placeholder:text-ink-muted"
        />
      </label>
      {failed ? (
        <p className="mt-2 text-[12px] text-signal-orange-text">The connections could not be read.</p>
      ) : !page ? (
        <Muted>Reading your connections.</Muted>
      ) : rows.length === 0 ? (
        <p className="mt-2 text-[12px] text-ink-muted">No connection matches &ldquo;{page.q}&rdquo;.</p>
      ) : (
        <ul className="mt-2 flex flex-col divide-y divide-edge border-y border-edge">
          {rows.map((row) => (
            <li key={row.profile_url} className="py-1.5">
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate text-[13px] text-ink-primary">{row.name ?? "No name in the archive"}</span>
                {row.lead_id && onOpenLead && (
                  <button
                    type="button"
                    onClick={() => onOpenLead(row.lead_id as string)}
                    aria-label={`Open ${row.name ?? "this person"} in Leads`}
                    className="studio-meta shrink-0 text-[10px] text-ink-muted underline decoration-edge-strong underline-offset-2 hover:text-ink-primary"
                  >
                    LEAD
                  </button>
                )}
              </div>
              {(row.position || row.company) && (
                <p className="truncate text-[11px] text-ink-muted">
                  {[row.position, row.company].filter(Boolean).join(" at ")}
                </p>
              )}
              <p className="studio-meta text-[10px] text-ink-muted">
                {row.connected_on ? `CONNECTED ${row.connected_on.toUpperCase()}` : "NO DATE IN THE ARCHIVE"}
              </p>
            </li>
          ))}
        </ul>
      )}
      {page && rows.length > 0 && (
        <p className="mt-1.5 text-[11px] text-ink-muted">
          {more && (
            <button
              type="button"
              onClick={() => {
                if (page.connections.length > rows.length) {
                  setRows(page.connections.slice(0, rows.length + CONNECTIONS_SHOWN));
                  return;
                }
                if (page.next_offset === null) return;
                void fetchAudienceConnections(q, page.next_offset).then((next) => {
                  setPage({ ...next, connections: [...page.connections, ...next.connections] });
                  setRows([...rows, ...next.connections.slice(0, CONNECTIONS_SHOWN)]);
                });
              }}
              className="mr-2 underline decoration-edge-strong underline-offset-2 hover:text-ink-primary"
            >
              Show more
            </button>
          )}
          {rows.length.toLocaleString()} of {page.total.toLocaleString()} shown.
        </p>
      )}
    </>
  );
}

/** The funnel and companies, as counts, read only when opened. */
function SecondLevel() {
  const [open, setOpen] = useState(false);
  const [counts, setCounts] = useState<AudienceCounts | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open || counts) return;
    fetchAudienceCounts()
      .then(setCounts)
      .catch(() => setFailed(true));
  }, [open, counts]);

  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <section className="mt-6 border-t border-edge pt-3">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex items-center gap-1 text-[12px] font-medium text-ink-secondary hover:text-ink-primary"
      >
        <Chevron className="size-3.5 text-ink-muted" strokeWidth={1.75} aria-hidden="true" />
        Your pipeline and companies, as counts
      </button>
      {open &&
        (failed ? (
          <p className="mt-2 text-[12px] text-signal-orange-text">The counts could not be read.</p>
        ) : !counts ? (
          <Muted>Counting.</Muted>
        ) : (
          <div className="mt-3 grid gap-6 md:grid-cols-2">
            <div>
              <p className="studio-label mb-1">Stages you set in Leads</p>
              <Muted>Everyone in Leads, {counts.people.toLocaleString()} people, by the stage you gave them.</Muted>
              <dl className="mt-2 flex flex-col gap-0.5">
                {counts.funnel.map((stage) => (
                  <div key={stage.status} className="flex items-baseline justify-between gap-4 text-[12px]">
                    <dt className="text-ink-secondary">{stage.label}</dt>
                    <dd className="tabular-nums text-ink-primary">{stage.people.toLocaleString()}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <div>
              <p className="studio-label mb-1">Companies, as headlines name them</p>
              <Muted>
                {counts.companies_named.toLocaleString()} companies named; {counts.no_company.toLocaleString()} people
                name none. The most named:
              </Muted>
              <dl className="mt-2 flex flex-col gap-0.5">
                {counts.companies.map((company) => (
                  <div key={company.company} className="flex items-baseline justify-between gap-4 text-[12px]">
                    <dt className="truncate text-ink-secondary">{company.company}</dt>
                    <dd className="tabular-nums text-ink-primary">{company.people.toLocaleString()}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </div>
        ))}
    </section>
  );
}

function Column({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <section className="min-w-0">
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <p className="studio-label">{title}</p>
        {note && <span className="studio-meta truncate text-[10px] text-ink-muted">{note.toUpperCase()}</span>}
      </div>
      {children}
    </section>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  const unmeasured = /^(not|no |nothing)/.test(value);
  return (
    <div className="bg-ink px-3 py-1.5">
      <dt className="studio-meta text-[10px] text-ink-muted">{label.toUpperCase()}</dt>
      <dd className={cn("tabular-nums", unmeasured ? "text-[12px] text-ink-muted" : "text-[14px] text-ink-primary")}>
        {value}
      </dd>
    </div>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return <p className="text-[12px] leading-snug text-ink-muted">{children}</p>;
}
