import { useCallback, useEffect, useState } from "react";
import { motion } from "motion/react";
import { Download, Loader2 } from "lucide-react";
import {
  LEADS_CSV_URL,
  LEAD_STATUSES,
  fetchLeadTimeline,
  fetchLeads,
  generateLeadDm,
  updateLeadStatus,
  type Lead,
  type LeadInteraction,
} from "@/lib/api";
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

  // Re-read after an action so the row and the dossier cannot disagree about
  // a lead's status. The stream shows the status on every row, so a change
  // made in the dossier is visible in two places at once or in neither.
  const reload = useCallback(() => {
    fetchLeads()
      .then((rows) => {
        setLeads(rows);
        // Open on the first lead so the dossier is never an empty panel next
        // to a populated list.
        setSelected((current) => current ?? rows[0]?.id ?? null);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  if (failed) return <Centered>LEAD PIPELINE UNAVAILABLE</Centered>;
  if (!leads) return <Centered>LOADING LEADS</Centered>;
  if (leads.length === 0) {
    return (
      <Centered>
        NO LEADS CAPTURED YET
        <br />
        <span className="text-ink-muted">CAPTURED PASSIVELY FROM PEOPLE WHO ENGAGE WITH YOUR POSTS</span>
      </Centered>
    );
  }

  return (
    <div className="flex h-full min-h-0">
      <section aria-label="Lead stream" className="flex w-[340px] shrink-0 flex-col border-r border-edge">
        <div className="flex items-baseline justify-between gap-2 px-4 pt-4 pb-2">
          <p className="studio-label">Lead stream</p>
          <div className="flex items-baseline gap-2">
            <p className="studio-meta text-[10px]">{leads.length}</p>
            {/* A download, not a fetch: the route streams a file, so the
                browser is the right thing to hand it to. */}
            <a
              href={LEADS_CSV_URL}
              className="studio-meta flex items-center gap-1 text-[10px] text-ink-muted transition-colors hover:text-ink-primary"
            >
              <Download className="size-3" strokeWidth={2} aria-hidden="true" />
              CSV
            </a>
          </div>
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
        {selected ? <Dossier leadId={selected} onChanged={reload} /> : null}
      </div>
    </div>
  );
}

/**
 * The person dossier. A research sheet, not a modal.
 */
function Dossier({ leadId, onChanged }: { leadId: string; onChanged: () => void }) {
  const [data, setData] = useState<{ lead: Lead; interactions: LeadInteraction[] } | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setData(await fetchLeadTimeline(leadId));
  }, [leadId]);

  useEffect(() => {
    let live = true;
    setData(null);
    setFailed(false);
    setDraft(null);
    setActionError(null);
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
  // A DM is drafted from something the lead actually said, so without a
  // comment there is nothing to draft from and the control says so.
  const latestComment = interactions.find((entry) => entry.comment_text)?.comment_text ?? null;

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
          /* The interactions table can be empty for a lead that still records
             an engagement, because the engagement that captured the lead is
             stored on the lead row and never written as a timeline entry. The
             stream card reads that field, so a dossier that only reads the
             table said NO INTERACTIONS RECORDED next to a card that said
             COMMENTED, about the same person on the same screen.

             What is shown here is that same field and nothing more. The date
             is labelled as when the studio recorded the lead, which is what
             created_at means, rather than presented as the moment they
             engaged, which is not stored. */
          lead.engagement_type ? (
            <div className="border-l border-edge pl-3">
              <p className="studio-meta text-[10px]">
                {lead.engagement_type.toUpperCase()}
                <span className="mx-1.5 text-ink-muted">·</span>
                CAPTURED {lead.created_at?.slice(0, 10)}
              </p>
              <p className="studio-meta mt-1 text-[10px] text-ink-muted">
                THE ENGAGEMENT THAT CAPTURED THIS LEAD. NO TIMELINE ENTRIES BEYOND IT.
              </p>
            </div>
          ) : (
            <p className="studio-meta text-ink-muted">NO INTERACTIONS RECORDED</p>
          )
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
        <p className="studio-label mb-2">Pipeline</p>
        {/* The four the backend accepts. Anything else is a 400, so the
            control offers exactly those rather than free text. Writing through
            the endpoint also keeps `status` and `lead_status` in step: they are
            two vocabularies over one lead, and a direct write to either leaves
            the funnel reading the other. */}
        <div className="flex flex-wrap gap-1">
          {LEAD_STATUSES.map((candidate) => (
            <button
              key={candidate}
              type="button"
              disabled={busy}
              onClick={async () => {
                if (candidate === lead.status) return;
                setBusy(true);
                setActionError(null);
                try {
                  await updateLeadStatus(lead.id, candidate);
                  await refresh();
                  onChanged();
                } catch (caught) {
                  setActionError(caught instanceof Error ? caught.message : "The change was refused.");
                } finally {
                  setBusy(false);
                }
              }}
              aria-pressed={candidate === lead.status}
              className={cn(
                "rounded-full border px-2.5 py-0.5 text-[11px]",
                "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard)",
                candidate === lead.status
                  ? "border-edge-strong bg-soft text-ink-primary"
                  : "border-edge text-ink-muted hover:text-ink-secondary",
                busy && "opacity-50",
              )}
            >
              {candidate}
            </button>
          ))}
        </div>
      </section>

      <section className="mt-6">
        <div className="mb-2 flex items-baseline justify-between gap-3">
          <p className="studio-label">Suggested reply</p>
          <button
            type="button"
            disabled={busy || !latestComment}
            title={latestComment ? undefined : "A reply is drafted from a comment this lead left"}
            onClick={async () => {
              if (!latestComment) return;
              setBusy(true);
              setActionError(null);
              try {
                setDraft(await generateLeadDm(lead.name, latestComment));
              } catch (caught) {
                setActionError(caught instanceof Error ? caught.message : "The draft was refused.");
              } finally {
                setBusy(false);
              }
            }}
            className="studio-meta flex items-center gap-1 text-[10px] text-ink-muted transition-colors hover:text-ink-primary disabled:opacity-40"
          >
            {busy && <Loader2 className="size-3 animate-spin" aria-hidden="true" />}
            DRAFT ONE
          </button>
        </div>

        {draft ?? suggested ? (
          <p className="rounded-md border border-edge bg-ink p-3 text-[13px] leading-relaxed whitespace-pre-wrap text-ink-secondary">
            {draft ?? suggested}
          </p>
        ) : (
          /* Nothing is generated on render. Drafting is an action the creator
             takes, because these are words that go out under their name. */
          <p className="studio-meta text-ink-muted">
            {latestComment
              ? "NO REPLY DRAFTED FOR THIS LEAD YET"
              : "NO COMMENT FROM THIS LEAD TO DRAFT A REPLY FROM"}
          </p>
        )}

        {actionError && (
          <p role="status" className="studio-meta mt-2 text-signal-orange-text">
            {actionError}
          </p>
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
