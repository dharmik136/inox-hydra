import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import { ArrowLeft, Copy, Download, ExternalLink, Loader2 } from "lucide-react";
import {
  DM_STYLES,
  LEADS_CSV_URL,
  LEAD_STATUSES,
  copyExtensionPath,
  fetchBrowserBridge,
  fetchLeadDmScript,
  fetchLeadOfferDraft,
  fetchLeadReview,
  fetchLeadTimeline,
  type FoldedReactions,
  fetchLeads,
  forgetLead,
  launchBridge,
  generateLeadDm,
  removeLeadsNotOnYourPosts,
  updateLeadNotes,
  updateLeadStatus,
  type BrowserBridge,
  type Lead,
  type LeadInteraction,
  type LeadReview,
  type LeadStageEvent,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import type { SearchFocus } from "@/lib/search";

/** The timeline's lead: whether it was scored at all, and its tier under the one rule. */
type DossierLead = Lead & { scored?: boolean; qualification_tier?: string };

const TIER_LABELS: Record<string, string> = {
  TIER_1_VIP: "VIP",
  QUALIFIED: "Qualified",
  NURTURE: "Nurture",
  DISQUALIFIED: "Disqualified",
};

/** How many rows the stream draws before asking. Five thousand drawn at once was 30,000 nodes. */
const STREAM_PAGE = 200;

/** Lower case without accents, so "zoe" finds Zoë and "angstrom" finds Ångström. */
function folded(text: string): string {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

/**
 * The CRM (blueprint section 11).
 *
 * A split inbox and dossier rather than a grid of KPI cards. The stream is a
 * compact table; the dossier reads like a research sheet on one person.
 */
export function LeadsSurface({ focus = null }: { focus?: SearchFocus | null } = {}) {
  const [leads, setLeads] = useState<Lead[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [selected, setSelected] = useState<string | null>(focus?.id ?? null);
  // Below the md breakpoint there is room for one pane. A fixed 340 pixel
  // stream beside the rail left the dossier 0 pixels wide on a phone, so
  // choosing a lead changed nothing visible. There the stream and the dossier
  // take turns; from md up both are always shown and this has no effect.
  const [pane, setPane] = useState<"stream" | "dossier">(focus ? "dossier" : "stream");
  // The stream had no way to narrow it, so five thousand leads were one list
  // drawn in full. The box and the stage filter work on the loaded list, and
  // only the first STREAM_PAGE matches are drawn until the creator asks for more.
  const [query, setQuery] = useState("");
  const [stage, setStage] = useState("All");
  const [limit, setLimit] = useState(STREAM_PAGE);
  const [notice, setNotice] = useState<string | null>(null);
  const shown = useMemo(() => {
    const words = folded(query).split(/\s+/).filter(Boolean);
    return (leads ?? []).filter(
      (lead) =>
        (stage === "All" || lead.status === stage) &&
        words.every((word) =>
          folded([lead.name, lead.company, lead.headline, lead.notes].filter(Boolean).join(" ")).includes(word),
        ),
    );
  }, [leads, query, stage]);

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

  // A lead opened from search is selected, and its row brought into view, once
  // the list holding it has rendered. Keyed on the nonce so choosing the same
  // person twice still scrolls back to them.
  useEffect(() => {
    if (!focus || !leads) return;
    const index = leads.findIndex((lead) => lead.id === focus.id);
    if (index < 0) return;
    setSelected(focus.id);
    setPane("dossier");
    // The row must be drawn to be scrolled to.
    setQuery("");
    setStage("All");
    setLimit((current) => Math.max(current, index + 1));
    window.requestAnimationFrame(() => {
      document.querySelector(`[data-lead-id="${CSS.escape(focus.id)}"]`)?.scrollIntoView({ block: "nearest" });
    });
  }, [focus, leads]);

  if (failed) return <Centered>LEAD PIPELINE UNAVAILABLE</Centered>;
  if (!leads) return <Centered>LOADING LEADS</Centered>;
  if (leads.length === 0) {
    return <EmptyStream />;
  }

  return (
    <div className="flex h-full min-h-0">
      <section
        aria-label="Lead stream"
        className={cn(
          "w-full shrink-0 flex-col border-edge md:flex md:w-[340px] md:border-r",
          pane === "stream" ? "flex" : "hidden",
        )}
      >
        <div className="flex items-baseline justify-between gap-2 px-4 pt-4 pb-2">
          <h1 className="studio-label">Lead stream</h1>
          <div className="flex items-baseline gap-2">
            <p className="studio-meta text-[10px]">
              {shown.length === leads.length ? leads.length : `${shown.length} OF ${leads.length}`}
            </p>
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
        <div className="flex gap-2 px-4 pb-2">
          <input
            type="search"
            aria-label="Find a lead"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setLimit(STREAM_PAGE);
            }}
            placeholder="Name, company, headline or notes"
            className="min-w-0 flex-1 rounded-md border border-edge bg-ink px-2.5 py-1 text-[12px] text-ink-primary placeholder:text-ink-muted focus:border-edge-strong focus:outline-none"
          />
          <select
            aria-label="Stage"
            value={stage}
            onChange={(event) => {
              setStage(event.target.value);
              setLimit(STREAM_PAGE);
            }}
            className="rounded-md border border-edge bg-ink px-1.5 py-1 text-[12px] text-ink-secondary focus:border-edge-strong focus:outline-none"
          >
            <option value="All">Every stage</option>
            {LEAD_STATUSES.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
        </div>
        {notice && (
          <p role="status" className="studio-meta border-b border-edge px-4 py-2 text-[10px] leading-snug text-ink-secondary">
            {notice}
          </p>
        )}
        <LeadReviewPanel onChanged={reload} />
        <ul className="min-h-0 flex-1 overflow-y-auto">
          {shown.length === 0 && (
            <li className="studio-meta px-4 py-3 text-[10px] text-ink-muted">NO LEAD MATCHES</li>
          )}
          {shown.slice(0, limit).map((lead) => (
            <li key={lead.id}>
              <button
                type="button"
                data-lead-id={lead.id}
                onClick={() => {
                  setSelected(lead.id);
                  setPane("dossier");
                }}
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
          {shown.length > limit && (
            <li className="px-4 py-3">
              <button
                type="button"
                onClick={() => setLimit((current) => current + STREAM_PAGE)}
                className="studio-meta text-[10px] text-ink-muted transition-colors hover:text-ink-primary"
              >
                Show more
              </button>
              <span className="studio-meta ml-2 text-[10px] text-ink-muted">
                {shown.length - limit} NOT SHOWN YET
              </span>
            </li>
          )}
        </ul>
      </section>

      <div className={cn("min-w-0 flex-1 overflow-y-auto md:block", pane === "dossier" ? "block" : "hidden")}>
        <button
          type="button"
          onClick={() => setPane("stream")}
          className="studio-meta flex items-center gap-1 px-4 pt-4 text-[10px] text-ink-muted transition-colors hover:text-ink-primary md:hidden"
        >
          <ArrowLeft className="size-3" strokeWidth={2} aria-hidden="true" />
          Back to the lead stream
        </button>
        {selected ? (
          <Dossier
            leadId={selected}
            onChanged={reload}
            onForgotten={(name) => {
              setNotice(`FORGOT ${name.toUpperCase()}, WITH EVERYTHING THE STUDIO HAD RECORDED ABOUT THEM.`);
              setSelected(null);
              setPane("stream");
              reload();
            }}
          />
        ) : null}
      </div>
    </div>
  );
}

/**
 * The person dossier. A research sheet, not a modal.
 */
/**
 * Reactions older than 24 months that Storage and privacy folded into
 * counts. They are still engagements, so the dossier counts them rather than
 * dropping them; which posts they were on is what the fold gave up.
 */
function FoldedReactionsNote({ folded }: { folded: FoldedReactions }) {
  return (
    <p className="studio-meta mt-3 border-l border-edge pl-3 text-[10px] text-ink-muted">
      {folded.count} {folded.count === 1 ? "REACTION" : "REACTIONS"} MORE THAN 24 MONTHS AGO
      {folded.on_your_posts ? `, ${folded.on_your_posts} ON YOUR POSTS` : ""}. KEPT AS A COUNT; WHICH POSTS IS NO
      LONGER RECORDED.
    </p>
  );
}

function Dossier({
  leadId,
  onChanged,
  onForgotten,
}: {
  leadId: string;
  onChanged: () => void;
  onForgotten: (name: string) => void;
}) {
  const [data, setData] = useState<{ lead: DossierLead; interactions: LeadInteraction[]; stage_history?: LeadStageEvent[]; folded_reactions?: FoldedReactions | null } | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  // The label travels with the text, so the panel can say which of the four
  // controls wrote what is in it. A draft whose provenance is invisible is one
  // the creator cannot judge.
  const [draft, setDraft] = useState<{ label: string; text: string } | null>(null);
  const [drafting, setDrafting] = useState<string | null>(null);
  const [topic, setTopic] = useState("");
  const [offer, setOffer] = useState("");
  const [copied, setCopied] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setData(await fetchLeadTimeline(leadId));
  }, [leadId]);

  /**
   * One path for all four drafting controls.
   *
   * They differ only in which route they call, so sharing the in-flight key,
   * the error surface and the panel write keeps them from drifting into four
   * slightly different behaviours on failure.
   */
  const draftWith = useCallback(
    async (key: string, label: string, produce: () => Promise<string>) => {
      setDrafting(key);
      setActionError(null);
      setCopied(false);
      try {
        setDraft({ label, text: await produce() });
      } catch (caught) {
        setActionError(caught instanceof Error ? caught.message : "The draft was refused.");
      } finally {
        setDrafting(null);
      }
    },
    [],
  );

  useEffect(() => {
    let live = true;
    setData(null);
    setFailed(false);
    setDraft(null);
    setDrafting(null);
    setCopied(false);
    // The topic is about the creator's own posting, not about the lead, so it
    // survives moving between people in the stream. Clearing it would make a
    // creator retype the same subject for every lead in a session.
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
  const folded = data.folded_reactions ?? null;
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
    <article className="max-w-[70ch] px-4 py-6 md:px-8 md:py-8">
      <p className="studio-label">{lead.status}</p>
      {/* A section of the Leads page, whose heading is the stream's label. */}
      <h2 className="studio-title mt-2">{lead.name}</h2>
      {lead.headline && <p className="mt-2 text-[14px] text-ink-secondary">{lead.headline}</p>}
      {/* Stored on every captured lead and never shown, so a creator who
          wanted to look at the person before messaging them had to search
          LinkedIn by name, and could open the wrong one. */}
      {profileLink(lead) && (
        <a
          href={profileLink(lead) as string}
          target="_blank"
          rel="noreferrer"
          className="studio-meta mt-2 inline-flex items-center gap-1 text-[10px] text-ink-muted transition-colors hover:text-ink-primary"
        >
          <ExternalLink className="size-3" strokeWidth={2} aria-hidden="true" />
          OPEN THEIR PROFILE ON LINKEDIN
        </a>
      )}

      <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-2 border-y border-edge py-4">
        <Field label="Company" value={lead.company} />
        <Field label="Seniority" value={lead.seniority_level} />
        {/* A captured lead is scored at capture, and a student's 0 is a low
            fit, not a missing score. Only a lead added by hand has none; the
            server says which, with the tier under the one rule. Reading every
            0 as unscored made a low fit look like a capture problem. */}
        <Field
          label="ICP score"
          value={
            lead.scored === false
              ? "Not scored"
              : `${lead.icp_score.toFixed(0)}${lead.qualification_tier ? ` · ${TIER_LABELS[lead.qualification_tier] ?? lead.qualification_tier}` : ""}`
          }
        />
        <Field label="First seen" value={lead.created_at ? localDate(lead.created_at) : null} />
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
          folded ? (
            <FoldedReactionsNote folded={folded} />
          ) : lead.engagement_type ? (
            <div className="border-l border-edge pl-3">
              <p className="studio-meta text-[10px]">
                {lead.engagement_type.toUpperCase()}
                <span className="mx-1.5 text-ink-muted">·</span>
                CAPTURED {lead.created_at ? localDate(lead.created_at).toUpperCase() : ""}
              </p>
              <p className="studio-meta mt-1 text-[10px] text-ink-muted">
                THE ENGAGEMENT THAT CAPTURED THIS LEAD. NO TIMELINE ENTRIES BEYOND IT.
              </p>
            </div>
          ) : (
            <p className="studio-meta text-ink-muted">NO INTERACTIONS RECORDED</p>
          )
        ) : (
          <>
          <ul className="flex flex-col gap-3">
            {interactions.slice(0, 8).map((entry) => (
              <li key={entry.id} className="border-l border-edge pl-3">
                <p className="studio-meta text-[10px]">
                  {(entry.interaction_type ?? "INTERACTION").toUpperCase()}
                  <span className="mx-1.5 text-ink-muted">·</span>
                  {entry.interacted_at ? localDateTime(entry.interacted_at).toUpperCase() : ""}
                </p>
                {entry.comment_text && (
                  <p className="mt-1 text-[13px] leading-snug text-ink-secondary">{entry.comment_text}</p>
                )}
                {/* Which post it was on. The URN was stored and never shown,
                    and the reply controls asked the creator to type the post
                    from memory. */}
                {entry.post_origin === "yours" && (
                  <p className="studio-meta mt-1 text-[10px] text-ink-muted">
                    ON YOUR POST{entry.post_excerpt ? `: ${entry.post_excerpt}` : ""}
                  </p>
                )}
                {entry.post_origin === "not_yours" && (
                  <p className="studio-meta mt-1 text-[10px] text-signal-orange-text">
                    ON SOMEONE ELSE&rsquo;S POST, CAPTURED BEFORE THE STUDIO KNEW WHICH POSTS WERE YOURS
                  </p>
                )}
              </li>
            ))}
          </ul>
          {folded && <FoldedReactionsNote folded={folded} />}
          </>
        )}
      </section>

      <LeadNotes
        leadId={lead.id}
        notes={lead.notes}
        onSaved={async () => {
          await refresh();
          onChanged();
        }}
      />

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
        {/* How this lead got here. Each change is recorded now, so "which
            post brought people I ended up talking to" has an answer. */}
        {(data.stage_history ?? []).length > 0 && (
          <ol className="mt-2 flex flex-col gap-0.5">
            {(data.stage_history ?? []).map((event) => (
              <li key={event.changed_at} className="studio-meta text-[10px] text-ink-muted">
                {localDate(event.changed_at).toUpperCase()}: {event.from_status ?? "NEW"} TO {event.to_status.toUpperCase()}
              </li>
            ))}
          </ol>
        )}
      </section>

      {/* Drafting a message.
       *
       * This used to offer one control, a reply built from something the lead
       * said, which left every lead who reacted rather than commented with a
       * disabled button and the sentence NO COMMENT TO DRAFT A REPLY FROM. That
       * read as a limit of the product and was not one: the backend also writes
       * three openers from the stored row alone, which is present for every
       * lead in the stream, and nothing called it.
       *
       * So the four sit together, and which ones are available depends on what
       * is actually known about the person rather than on which route existed
       * first. The reply is listed last because it needs a comment; the two
       * openers never do, and the offer needs only what you would share. */}
      <section className="mt-6">
        <p className="studio-label mb-1">Draft a message</p>
        <p className="mb-3 text-[12px] leading-snug text-ink-muted">
          Written only from this lead&rsquo;s record and what you type below, then yours to edit.
          Nothing is sent from here; LinkedIn DMs are not something this studio can do on your behalf.
        </p>

        {/* The template writes "my recent post on ...", and the studio does not
            know which post they engaged with, so it guesses a subject. A
            creator whose work is about something else would send a draft that
            names the wrong topic, which is worth one input to avoid. */}
        <label className="mb-3 block">
          <span className="studio-meta text-[10px] text-ink-muted">THE POST THEY ENGAGED WITH</span>
          <input
            type="text"
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            placeholder="Optional. Left blank, the draft says only “my recent post”"
            className="mt-1 w-full rounded-md border border-edge bg-ink px-2.5 py-1.5 text-[13px] text-ink-primary placeholder:text-ink-muted focus:border-edge-strong focus:outline-none"
          />
        </label>

        {/* An offer is only true when you say what it is. The control used to
            offer the original author's "architecture blueprint" and a diagram
            under every creator's name. */}
        <label className="mb-3 block">
          <span className="studio-meta text-[10px] text-ink-muted">WHAT YOU WOULD SHARE WITH THEM</span>
          <input
            type="text"
            value={offer}
            onChange={(event) => setOffer(event.target.value)}
            placeholder="Needed for Offer something, for example “the checklist I use for orders”"
            className="mt-1 w-full rounded-md border border-edge bg-ink px-2.5 py-1.5 text-[13px] text-ink-primary placeholder:text-ink-muted focus:border-edge-strong focus:outline-none"
          />
        </label>

        <div className="flex flex-wrap gap-1">
          {DM_STYLES.map((style) => (
            <DraftButton
              key={style.id}
              label={style.label}
              pending={drafting === style.id}
              disabled={drafting !== null}
              onPress={() =>
                void draftWith(style.id, style.label, () => fetchLeadDmScript(lead.id, style.id, topic))
              }
            />
          ))}
          <DraftButton
            label="Offer something"
            pending={drafting === "offer"}
            disabled={drafting !== null || !offer.trim()}
            hint={offer.trim() ? undefined : "Say what you would share with them, above"}
            onPress={() =>
              void draftWith("offer", "Offer something", () => fetchLeadOfferDraft(lead.id, offer, topic))
            }
          />
          <DraftButton
            label="Reply to their comment"
            pending={drafting === "reply"}
            disabled={drafting !== null || !latestComment}
            hint={latestComment ? undefined : "This lead has left no comment to reply to"}
            onPress={() =>
              void draftWith("reply", "Reply to their comment", () =>
                generateLeadDm(lead.name, latestComment as string, topic || undefined),
              )
            }
          />
        </div>

        {draft ?? suggested ? (
          <div className="mt-3">
            <div className="mb-1.5 flex items-baseline justify-between gap-3">
              <p className="studio-meta text-[10px] text-ink-muted">
                {draft ? draft.label.toUpperCase() : "SAVED WITH AN EARLIER INTERACTION"}
              </p>
              <button
                type="button"
                onClick={() => {
                  // COPIED once the browser has taken the text, and not before.
                  // The draft is above the message line, and a later copy that
                  // works takes the refusal away; other messages stay.
                  const refusal = "The browser refused the copy. Select the text above and copy it.";
                  const refused = () => setActionError(refusal);
                  if (!navigator.clipboard?.writeText) {
                    refused();
                    return;
                  }
                  navigator.clipboard
                    .writeText(draft?.text ?? suggested ?? "")
                    .then(() => {
                      setActionError((current) => (current === refusal ? null : current));
                      setCopied(true);
                      window.setTimeout(() => setCopied(false), 1600);
                    })
                    .catch(refused);
                }}
                className="studio-meta flex items-center gap-1 text-[10px] text-ink-muted transition-colors hover:text-ink-primary"
              >
                <Copy className="size-3" strokeWidth={2} aria-hidden="true" />
                {copied ? "COPIED" : "COPY"}
              </button>
            </div>
            <p className="rounded-md border border-edge bg-ink p-3 text-[13px] leading-relaxed whitespace-pre-wrap text-ink-secondary">
              {draft?.text ?? suggested}
            </p>
          </div>
        ) : (
          /* Nothing is generated on render. Drafting is an action the creator
             takes, because these are words that go out under their name. */
          <p className="studio-meta mt-3 text-ink-muted">NOTHING DRAFTED FOR THIS LEAD YET</p>
        )}

        {actionError && (
          <p role="status" className="studio-meta mt-2 text-signal-orange-text">
            {actionError}
          </p>
        )}
      </section>

      <ForgetLead lead={lead} onForgotten={() => onForgotten(lead.name)} />
    </article>
  );
}

/**
 * The creator's own notes on a lead.
 *
 * They were shown and could not be changed here, so a note was only ever what
 * a capture or an import had written. Saving writes the notes and nothing
 * else; the stage is the pipeline control's.
 */
function LeadNotes({ leadId, notes, onSaved }: { leadId: string; notes: string | null; onSaved: () => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(notes ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setText(notes ?? "");
    setEditing(false);
    setError(null);
  }, [leadId, notes]);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await updateLeadNotes(leadId, text);
      await onSaved();
      setEditing(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The notes were not saved.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mt-6">
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <p className="studio-label">Notes</p>
        {!editing && (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="studio-meta text-[10px] text-ink-muted transition-colors hover:text-ink-primary"
          >
            Edit notes
          </button>
        )}
      </div>
      {editing ? (
        <>
          <textarea
            aria-label="Notes about this lead"
            value={text}
            maxLength={2000}
            rows={4}
            onChange={(event) => setText(event.target.value)}
            className="w-full rounded-md border border-edge bg-ink px-2.5 py-1.5 text-[13px] leading-relaxed text-ink-primary focus:border-edge-strong focus:outline-none"
          />
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => void save()}
              className="flex items-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[11px] text-ink-secondary transition-colors hover:bg-soft disabled:opacity-40"
            >
              {busy && <Loader2 className="size-3 animate-spin" aria-hidden="true" />}
              Save notes
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setText(notes ?? "");
                setEditing(false);
              }}
              className="studio-meta text-[10px] text-ink-muted hover:text-ink-primary"
            >
              CANCEL
            </button>
          </div>
        </>
      ) : notes ? (
        <p className="text-[13px] leading-relaxed whitespace-pre-wrap text-ink-secondary">{notes}</p>
      ) : (
        <p className="studio-meta text-ink-muted">NO NOTES YET</p>
      )}
      {error && (
        <p role="status" className="studio-meta mt-2 text-signal-orange-text">
          {error}
        </p>
      )}
    </section>
  );
}

/**
 * Forgetting a person, from their own dossier.
 *
 * The only removal on this screen was the bulk review of other people's
 * posts, so a creator asked to delete someone's data, or who captured the
 * wrong person, had to call the API. One press arms it and names the person;
 * the second removes them, with everything recorded about them, on the server
 * in one step.
 */
function ForgetLead({ lead, onForgotten }: { lead: Lead; onForgotten: () => void }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setConfirming(false);
    setError(null);
  }, [lead.id]);

  async function forget() {
    setBusy(true);
    setError(null);
    try {
      await forgetLead(lead.id);
      onForgotten();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The person was not forgotten.");
      setBusy(false);
    }
  }

  return (
    <section className="mt-8 border-t border-edge pt-4">
      <p className="mb-2 text-[12px] leading-snug text-ink-muted">
        Forgetting removes this person, everything they said, their stage history and your notes
        from this studio. Backups and exports you made earlier still hold them.
      </p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => (confirming ? void forget() : setConfirming(true))}
          className={cn(
            "rounded-md border px-2.5 py-1 text-[11px] transition-colors disabled:opacity-40",
            confirming
              ? "border-signal-orange bg-signal-orange text-on-signal"
              : "border-edge text-ink-secondary hover:bg-soft",
          )}
        >
          {confirming ? `Forget ${lead.name}, it cannot be undone` : "Forget this person"}
        </button>
        {confirming && (
          <button
            type="button"
            disabled={busy}
            onClick={() => setConfirming(false)}
            className="studio-meta text-[10px] text-ink-muted hover:text-ink-primary"
          >
            CANCEL
          </button>
        )}
      </div>
      {error && (
        <p role="status" className="studio-meta mt-2 text-signal-orange-text">
          {error}
        </p>
      )}
    </section>
  );
}

/**
 * One of the four drafting controls.
 *
 * Disabled carries a reason whenever there is one: a control that is greyed out
 * and silent about why reads as broken rather than as unavailable.
 */
function DraftButton({
  label,
  pending,
  disabled,
  hint,
  onPress,
}: {
  label: string;
  pending: boolean;
  disabled: boolean;
  hint?: string;
  onPress: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      title={hint}
      onClick={onPress}
      className={cn(
        "flex items-center gap-1 rounded-full border border-edge px-2.5 py-0.5 text-[11px] text-ink-secondary",
        "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard)",
        "hover:border-edge-strong hover:text-ink-primary",
        disabled && "opacity-40 hover:border-edge hover:text-ink-secondary",
      )}
    >
      {pending && <Loader2 className="size-3 animate-spin" aria-hidden="true" />}
      {label}
    </button>
  );
}

/**
 * A stored time, read as the moment it was.
 *
 * SQLite writes UTC with no zone ("2026-10-19 04:43:00"). Sliced and printed
 * as it was, a comment made at 10:13 in India read 04:43, and a stage change
 * after 18:30 was dated the next day, while Today showed the same event in
 * local time. A stamp without a zone is UTC; the reader sees their own clock.
 */
function storedTime(stamp: string): Date {
  if (/^\d{4}-\d{2}-\d{2}$/.test(stamp)) return new Date(`${stamp}T00:00:00`);
  const iso = stamp.includes("T") ? stamp : stamp.replace(" ", "T");
  return new Date(/(Z|[+-]\d{2}:?\d{2})$/i.test(iso) ? iso : `${iso}Z`);
}

function localDate(stamp: string): string {
  const when = storedTime(stamp);
  return Number.isNaN(when.getTime())
    ? stamp.slice(0, 10)
    : when.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function localDateTime(stamp: string): string {
  const when = storedTime(stamp);
  return Number.isNaN(when.getTime())
    ? stamp.slice(0, 16)
    : when.toLocaleString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
}

/** A link to the person's LinkedIn profile, from whichever column holds it. */
function profileLink(lead: Lead): string | null {
  for (const candidate of [lead.profile_url, lead.linkedin_urn]) {
    if (candidate && /^https?:\/\/([a-z]+\.)?linkedin\.com\/in\//i.test(candidate)) return candidate;
  }
  return null;
}

/**
 * Leads captured before the studio could tell your posts from anyone else's.
 *
 * Until onboarding, the capture kept anyone engaging with any post on the
 * feed. Those people are not your audience and a message to them would thank
 * them for engaging with a post that was not yours. They are listed here only
 * once your post history has been imported to the end, because before that a
 * post the studio does not recognise may just be an older post of yours.
 *
 * Removal is a list you read and then confirm, never automatic, and the
 * studio re-checks each name at the moment of removal.
 */
function LeadReviewPanel({ onChanged }: { onChanged: () => void }) {
  const [review, setReview] = useState<LeadReview | null>(null);
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchLeadReview().then(setReview).catch(() => setReview(null));
  }, []);
  useEffect(load, [load]);

  if (!review) return null;
  const count = review.counts.not_yours;

  if (!review.history_complete) {
    if (review.counts.unknown === 0) return null;
    return (
      <p className="studio-meta border-b border-edge px-4 py-2 text-[10px] leading-snug text-ink-muted">
        IMPORT YOUR POSTS IN SETUP AND THE STUDIO CAN TELL WHICH OF THESE LEADS CAME FROM YOUR POSTS.
      </p>
    );
  }
  if (count === 0 && !note) return null;

  return (
    <div className="border-b border-edge px-4 py-2.5">
      {note && <p className="studio-meta text-[10px] text-ink-secondary">{note}</p>}
      {count > 0 && (
        <>
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            className="studio-meta text-left text-[10px] leading-snug text-signal-orange-text"
          >
            {count} {count === 1 ? "LEAD" : "LEADS"} ENGAGED ONLY WITH OTHER PEOPLE&rsquo;S POSTS. {open ? "HIDE" : "REVIEW"}
          </button>
          {open && (
            <div className="mt-2">
              <ul className="max-h-48 overflow-y-auto">
                {review.not_yours.map((lead) => (
                  <li key={lead.id} className="truncate text-[12px] text-ink-secondary">
                    {lead.name}
                    {lead.headline && <span className="text-ink-muted">, {lead.headline}</span>}
                  </li>
                ))}
              </ul>
              <div className="mt-2 flex items-center gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={async () => {
                    if (!confirming) {
                      setConfirming(true);
                      return;
                    }
                    setBusy(true);
                    try {
                      const result = await removeLeadsNotOnYourPosts(review.not_yours.map((l) => l.id));
                      setNote(
                        `REMOVED ${result.removed}.${result.kept ? ` KEPT ${result.kept} THAT HAVE SINCE ENGAGED WITH YOUR POSTS.` : ""}`,
                      );
                      setConfirming(false);
                      setOpen(false);
                      load();
                      onChanged();
                    } catch (caught) {
                      setNote(caught instanceof Error ? caught.message : "The removal was refused.");
                    } finally {
                      setBusy(false);
                    }
                  }}
                  className={cn(
                    "rounded-md border px-2.5 py-1 text-[11px] transition-colors disabled:opacity-40",
                    confirming
                      ? "border-signal-orange bg-signal-orange text-on-signal"
                      : "border-edge text-ink-secondary hover:bg-soft",
                  )}
                >
                  {confirming ? `Delete these ${count}, it cannot be undone` : `Remove these ${count}`}
                </button>
                {confirming && (
                  <button
                    type="button"
                    onClick={() => setConfirming(false)}
                    className="studio-meta text-[10px] text-ink-muted hover:text-ink-primary"
                  >
                    CANCEL
                  </button>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
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

/**
 * The empty stream, and the reason it is empty.
 *
 * Leads arrive from an extension watching LinkedIn pages you open yourself.
 * Until it is loaded there is nothing to capture, so this surface stays empty
 * no matter how long it is left, and the previous copy stated that outcome
 * without offering the step that changes it.
 *
 * Which browsers can carry it is a measured fact, not a preference. Chrome
 * accepts --load-extension and ignores it, so listing it as an equal option
 * would send someone to the one browser where this silently does nothing.
 */
function EmptyStream() {
  const [bridge, setBridge] = useState<BrowserBridge | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    fetchBrowserBridge()
      .then((result) => live && setBridge(result))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, []);

  async function open(browserId: string) {
    setBusy(browserId);
    setNote(null);
    try {
      const result = await launchBridge(browserId);
      setNote(result.message);
    } catch (caught) {
      setNote(caught instanceof Error ? caught.message : "The browser could not be launched.");
    } finally {
      setBusy(null);
    }
  }

  async function copyPath() {
    setBusy("copy");
    setNote(null);
    try {
      const copied = await copyExtensionPath();
      if (copied.ok) {
        setNote(`Copied to the clipboard: ${copied.path}`);
      } else {
        // The server's reason, with the path selected so Ctrl+C finishes the
        // job. Announcing a copy here sent people to paste whatever was
        // already on the clipboard into Load unpacked.
        setNote(copied.message || "The path could not be copied. Copy it from above by hand.");
        const shown = document.getElementById("extension-folder-path");
        if (shown) window.getSelection()?.selectAllChildren(shown);
      }
    } catch {
      setNote("The path could not be copied.");
    } finally {
      setBusy(null);
    }
  }

  const carriers = (bridge?.browsers ?? []).filter((b) => b.carries_extension === true);
  const others = (bridge?.browsers ?? []).filter((b) => b.carries_extension !== true);

  return (
    <div className="grid h-full place-items-center px-8">
      <div className="max-w-[54ch]">
        <h1 className="studio-label">No leads captured yet</h1>
        <p className="mt-3 text-[14px] leading-relaxed text-ink-secondary">
          Leads are captured passively, by an extension watching the LinkedIn pages you open
          yourself, and only from people engaging with your own posts. The studio needs to know
          which posts are yours, so this stays empty until the bridge is running and you have
          confirmed your profile in Setup.
        </p>

        {failed ? (
          <p className="studio-meta mt-5 text-ink-muted">BROWSER DETECTION UNAVAILABLE</p>
        ) : bridge === null ? (
          <p className="studio-meta mt-5 text-ink-muted">LOOKING FOR A BROWSER</p>
        ) : bridge.browsers.length === 0 ? (
          <p className="studio-meta mt-5 leading-relaxed text-ink-muted">
            NO CHROMIUM BROWSER FOUND ON THIS MACHINE. INSTALL EDGE OR BRAVE TO RUN THE BRIDGE.
          </p>
        ) : (
          <>
            {carriers.length > 0 && (
              <div className="mt-5">
                <p className="studio-meta mb-2 text-[10px]">OPEN LINKEDIN WITH THE BRIDGE</p>
                <div className="flex flex-wrap gap-2">
                  {carriers.map((browser) => (
                    <button
                      key={browser.id}
                      type="button"
                      onClick={() => void open(browser.id)}
                      disabled={busy !== null}
                      className="flex items-center gap-1.5 rounded-md bg-signal-orange px-3 py-1 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-40"
                    >
                      {busy === browser.id ? (
                        <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                      ) : (
                        <ExternalLink className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                      )}
                      {browser.name}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {others.length > 0 && (
              <p className="studio-meta mt-4 leading-relaxed text-ink-muted">
                {others.map((b) => b.name.toUpperCase()).join(", ")}{" "}
                {others.length === 1 ? "IS" : "ARE"} INSTALLED BUT{" "}
                {others.some((b) => b.carries_extension === false)
                  ? "IGNORES THE EXTENSION FLAG, SO THE BRIDGE WOULD NOT ATTACH."
                  : "HAS NOT BEEN CHECKED ON THIS MACHINE."}
              </p>
            )}

            <div className="mt-5 border-t border-edge pt-4">
              <p className="studio-meta mb-2 text-[10px]">OR LOAD IT BY HAND</p>
              <p className="text-[13px] leading-relaxed text-ink-secondary">
                Open your browser&rsquo;s extensions page, turn on developer mode, choose Load
                unpacked, and point it at this folder.
              </p>
              <button
                type="button"
                onClick={() => void copyPath()}
                disabled={busy !== null}
                className="mt-2 flex items-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
              >
                <Copy className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                Copy the folder path
              </button>
              <p id="extension-folder-path" className="studio-meta mt-2 break-all text-[10px] text-ink-muted">
                {bridge.extension_path}
              </p>
            </div>
          </>
        )}

        {note && (
          <p role="status" className="studio-meta mt-4 leading-snug text-ink-secondary">
            {note}
          </p>
        )}
      </div>
    </div>
  );
}
