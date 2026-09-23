import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { fetchLeadTimeline, fetchLeads, type Lead, type LeadInteraction } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * The CRM (blueprint section 11).
 *
 * A split inbox and dossier rather than a grid of KPI cards. The stream is a
 * compact table; the dossier reads like a research sheet on one person.
 */
export function LeadsSurface() {
  const [leads, setLeads] = useState<Lead[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    fetchLeads()
      .then((rows) => {
        if (!live) return;
        setLeads(rows);
        // Open on the first lead so the dossier is never an empty panel next
        // to a populated list.
        setSelected((current) => current ?? rows[0]?.id ?? null);
      })
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, []);

  if (failed) return <Centered>LEAD PIPELINE UNAVAILABLE</Centered>;
  if (!leads) return <Centered>LOADING LEADS</Centered>;
  if (leads.length === 0) {
    return (
      <Centered>
        NO LEADS CAPTURED YET
        <br />
        <span className="text-ink-muted/70">CAPTURED PASSIVELY FROM PEOPLE WHO ENGAGE WITH YOUR POSTS</span>
      </Centered>
    );
  }

  return (
    <div className="flex h-full min-h-0">
      <section aria-label="Lead stream" className="flex w-[340px] shrink-0 flex-col border-r border-edge">
        <div className="flex items-baseline justify-between px-4 pt-4 pb-2">
          <p className="studio-label">Lead stream</p>
          <p className="studio-meta text-[10px]">{leads.length}</p>
        </div>
        <ul className="min-h-0 flex-1 overflow-y-auto">
          {leads.map((lead) => (
            <li key={lead.id}>
              <button
                type="button"
                onClick={() => setSelected(lead.id)}
                aria-current={selected === lead.id ? "true" : undefined}
                className={cn(
                  "relative w-full border-b border-edge px-4 py-3 text-left",
                  "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard)",
                  selected === lead.id ? "bg-soft" : "hover:bg-soft/60",
                )}
              >
                {selected === lead.id && (
                  <motion.span
                    layoutId="lead-active"
                    className="absolute inset-y-0 left-0 w-0.5 bg-signal-orange"
                    transition={{ duration: 0.22, ease: [0.32, 0.72, 0.24, 1] }}
                  />
                )}
                <p className="truncate text-[13px] font-medium text-ink-primary">{lead.name}</p>
                {lead.headline && (
                  <p className="mt-0.5 truncate text-[11px] text-ink-muted">{lead.headline}</p>
                )}
                <p className="studio-meta mt-1.5 text-[10px]">
                  {(lead.engagement_type ?? "ENGAGED").toUpperCase()}
                  <span className="mx-1.5 text-ink-muted">·</span>
                  {lead.status.toUpperCase()}
                </p>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <div className="min-w-0 flex-1 overflow-y-auto">
        {selected ? <Dossier leadId={selected} /> : null}
      </div>
    </div>
  );
}

/**
 * The person dossier. A research sheet, not a modal.
 */
function Dossier({ leadId }: { leadId: string }) {
  const [data, setData] = useState<{ lead: Lead; interactions: LeadInteraction[] } | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    setData(null);
    setFailed(false);
    fetchLeadTimeline(leadId)
      .then((result) => live && setData(result))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [leadId]);

  if (failed) return <Centered>DOSSIER UNAVAILABLE</Centered>;
  if (!data) return <Centered>LOADING DOSSIER</Centered>;

  const { lead, interactions } = data;
  // A suggested reply is stored per interaction, so the most recent one that
  // carries a draft is the one worth offering.
  const suggested = interactions.find((entry) => entry.suggested_dm_reply)?.suggested_dm_reply ?? null;

  // Left aligned against the stream rather than centred in the leftover space,
  // which on a wide window opens a gap between the two halves and makes the
  // split read as two unrelated panels.
  return (
    <article className="max-w-[70ch] px-8 py-8">
      <p className="studio-label">{lead.status}</p>
      <h2 className="studio-title mt-2">{lead.name}</h2>
      {lead.headline && <p className="mt-2 text-[14px] text-ink-secondary">{lead.headline}</p>}

      <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-2 border-y border-edge py-4">
        <Field label="Company" value={lead.company} />
        <Field label="Seniority" value={lead.seniority_level} />
        {/* Zero means never scored, which is a different statement from a
            lead scored zero, so it is reported as unscored rather than as a
            number the reader would compare against other leads. */}
        <Field label="ICP score" value={lead.icp_score > 0 ? lead.icp_score.toFixed(0) : "Not scored"} />
        <Field label="First seen" value={lead.created_at?.slice(0, 10) ?? null} />
      </dl>

      <section className="mt-6">
        <p className="studio-label mb-2">Recent interactions</p>
        {interactions.length === 0 ? (
          <p className="studio-meta text-ink-muted">NO INTERACTIONS RECORDED</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {interactions.slice(0, 8).map((entry) => (
              <li key={entry.id} className="border-l border-edge pl-3">
                <p className="studio-meta text-[10px]">
                  {(entry.interaction_type ?? "INTERACTION").toUpperCase()}
                  <span className="mx-1.5 text-ink-muted">·</span>
                  {entry.interacted_at?.slice(0, 16)}
                </p>
                {entry.comment_text && (
                  <p className="mt-1 text-[13px] leading-snug text-ink-secondary">{entry.comment_text}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {lead.notes && (
        <section className="mt-6">
          <p className="studio-label mb-2">Notes</p>
          <p className="text-[13px] leading-relaxed whitespace-pre-wrap text-ink-secondary">{lead.notes}</p>
        </section>
      )}

      <section className="mt-6">
        <p className="studio-label mb-2">Suggested reply</p>
        {suggested ? (
          <p className="rounded-md border border-edge bg-ink p-3 text-[13px] leading-relaxed whitespace-pre-wrap text-ink-secondary">
            {suggested}
          </p>
        ) : (
          /* Nothing is generated here on render. A DM is drafted through the
             CRM's own endpoint on request, and inventing one to fill the panel
             would put words in the creator's mouth. */
          <p className="studio-meta text-ink-muted">NO REPLY DRAFTED FOR THIS LEAD YET</p>
        )}
      </section>
    </article>
  );
}

function Field({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-[11px] text-ink-muted">{label}</dt>
      <dd className="studio-meta truncate text-right text-ink-secondary">{value ?? "Unknown"}</dd>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid h-full place-items-center px-8">
      <p className="studio-meta max-w-[40ch] text-center leading-relaxed text-ink-muted">{children}</p>
    </div>
  );
}
