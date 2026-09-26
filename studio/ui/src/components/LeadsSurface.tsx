import { useCallback, useEffect, useState } from "react";
import { motion } from "motion/react";
import { Copy, Download, ExternalLink, Loader2 } from "lucide-react";
import {
  DM_STYLES,
  LEADS_CSV_URL,
  LEAD_STATUSES,
  copyExtensionPath,
  fetchBrowserBridge,
  fetchLeadDmScript,
  fetchLeadTimeline,
  fetchLeads,
  launchBridge,
  generateLeadDm,
  updateLeadStatus,
  type BrowserBridge,
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
    return <EmptyStream />;
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
  // The label travels with the text, so the panel can say which of the four
  // controls wrote what is in it. A draft whose provenance is invisible is one
  // the creator cannot judge.
  const [draft, setDraft] = useState<{ label: string; text: string } | null>(null);
  const [drafting, setDrafting] = useState<string | null>(null);
  const [topic, setTopic] = useState("");
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
       * first. The reply is listed last because it needs a comment; the three
       * openers never do. */}
      <section className="mt-6">
        <p className="studio-label mb-1">Draft a message</p>
        <p className="mb-3 text-[12px] leading-snug text-ink-muted">
          Written from this lead&rsquo;s own record, then yours to edit. Nothing is sent from here;
          LinkedIn DMs are not something this studio can do on your behalf.
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
                  void navigator.clipboard.writeText(draft?.text ?? suggested ?? "");
                  setCopied(true);
                  window.setTimeout(() => setCopied(false), 1600);
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
    </article>
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
      const path = await copyExtensionPath();
      setNote(`Copied to the clipboard: ${path}`);
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
        <p className="studio-label">No leads captured yet</p>
        <p className="mt-3 text-[14px] leading-relaxed text-ink-secondary">
          Leads are captured passively, by an extension watching the LinkedIn pages you open
          yourself. Nothing is scraped and nothing is requested on your behalf, which is also why
          this stays empty until the bridge is running.
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
              <p className="studio-meta mt-2 break-all text-[10px] text-ink-muted">
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
