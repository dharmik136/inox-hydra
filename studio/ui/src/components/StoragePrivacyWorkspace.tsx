import { useCallback, useEffect, useState } from "react";
import { Archive, Loader2 } from "lucide-react";
import {
  compactDatabase,
  fetchSilentLeads,
  fetchStorage,
  forgetSilentLeads,
  keepSilentLeads,
  previewRetention,
  runRetention,
  saveRetentionRules,
  scrubBackups,
  type ForgetResult,
  type RetentionJob,
  type RetentionPreview,
  type RetentionRules,
  type SilentLead,
  type StorageOverview,
} from "@/lib/api";
import { formatLocal } from "@/lib/time";
import { cn } from "@/lib/utils";

/**
 * Brand Studio, Storage and privacy.
 *
 * What this profile holds and for how long, in one place. Nothing used to
 * expire, and nothing on screen said so: three heavy years were 368 MB, a
 * backup was made only when the creator pressed the button, and a person
 * they forgot stayed in every backup for ever. The rules live in
 * studio/backend/retention.py; this panel shows each one with its default,
 * previews every cleanup before it removes anything, and says plainly what
 * happens to forgotten people in backups.
 */

const BUTTON =
  "flex items-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40";
const PRIMARY =
  "flex items-center gap-1.5 rounded-md bg-signal-orange px-3 py-1 text-xs font-medium text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-40";
const SELECT =
  "rounded-md border border-edge bg-canvas px-2 py-1 text-[12px] text-ink-primary focus:border-signal-orange focus:outline-none";

const JOB_NAME: Record<string, string> = {
  telemetry: "Network readings log",
  readings: "Post readings",
  reactions: "Old reactions",
  daily_backup: "Daily backup",
  forget_silent_leads: "Forgot silent people",
  remove_from_backups: "Removed from backups",
  compact: "Compacted",
};

function readableBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "not measured";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** The server's cleanup times are UTC without a zone; read them as UTC. */
function utc(stamp: string | null | undefined): string | null {
  if (!stamp) return null;
  return /[zZ]|[+-]\d\d:\d\d$/.test(stamp) ? stamp : `${stamp.replace(" ", "T")}Z`;
}

function count(n: number | undefined): string {
  return (n ?? 0).toLocaleString();
}

function failure(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback;
}

export function StoragePrivacyWorkspace() {
  const [view, setView] = useState<StorageOverview | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setView(await fetchStorage());
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  /** One request at a time, its outcome said in words, then a fresh read. */
  async function act(what: string, run: () => Promise<string | null>) {
    setBusy(what);
    setNote(null);
    try {
      setNote(await run());
    } catch (caught) {
      setNote(failure(caught, "The request was refused."));
    } finally {
      setBusy(null);
      await load();
    }
  }

  if (failed) return <p className="studio-meta text-ink-muted">STORAGE COULD NOT BE READ</p>;
  if (!view) return <p className="studio-meta text-ink-muted">READING</p>;

  const changeRule = (rules: Partial<RetentionRules>) =>
    act("rules", async () => {
      await saveRetentionRules(rules);
      return "Saved.";
    });

  return (
    <div className="flex max-w-[64ch] flex-col gap-6">
      {note && (
        <p role="status" className="text-[13px] leading-relaxed break-words text-ink-secondary">
          {note}
        </p>
      )}

      <Holdings view={view} busy={busy} act={act} />
      <Backups view={view} busy={busy} changeRule={changeRule} />
      <Rules view={view} busy={busy} act={act} changeRule={changeRule} />
      <Review view={view} busy={busy} act={act} changeRule={changeRule} />
      <ForgottenInBackups view={view} busy={busy} act={act} />
      <CleanupLog view={view} />
    </div>
  );
}

type Act = (what: string, run: () => Promise<string | null>) => Promise<void>;
type ChangeRule = (rules: Partial<RetentionRules>) => Promise<void>;

function Holdings({ view, busy, act }: { view: StorageOverview; busy: string | null; act: Act }) {
  const { sizes } = view;
  return (
    <section aria-labelledby="storage-holds">
      <h2 id="storage-holds" className="studio-label mb-2">
        What this profile holds
      </h2>
      <p className="mb-3 text-[13px] leading-relaxed text-ink-secondary">
        All of it is in this creator profile&apos;s folder on this machine.
        {!sizes.measured && " This copy of SQLite cannot measure each part, so only the file sizes are shown."}
      </p>
      <dl className="flex flex-col gap-1.5 text-[13px]">
        {sizes.categories
          .filter((category) => category.bytes !== 0 || (category.rows ?? 0) > 0)
          .map((category) => (
            <SizeRow
              key={category.key}
              label={category.label}
              rows={category.rows}
              bytes={readableBytes(category.bytes)}
            />
          ))}
        <SizeRow label="The database file" bytes={readableBytes(sizes.database_bytes)} total />
        <SizeRow label="Network readings log (a separate file)" bytes={readableBytes(sizes.telemetry_bytes)} />
        <SizeRow label="Media" bytes={readableBytes(sizes.media_bytes)} />
        <SizeRow label="Backups folder" bytes={readableBytes(sizes.backups_bytes)} />
      </dl>

      {sizes.free_bytes > 0 && (
        <div className="mt-4">
          <p className="text-[13px] leading-relaxed text-ink-secondary">
            {readableBytes(sizes.free_bytes)} of the database file is space freed by forgetting people or by a
            cleanup. Deleted words are already overwritten; compacting gives the space back to the disk and drops
            anything a version before this one left in it. It takes about a second for every 300 MB, and only
            when you ask.
          </p>
          <button
            type="button"
            className={cn(BUTTON, "mt-2")}
            disabled={busy !== null}
            onClick={() =>
              void act("compact", async () => {
                const done = await compactDatabase();
                return `Compacted: ${readableBytes(done.before_bytes)} to ${readableBytes(done.after_bytes)}.`;
              })
            }
          >
            {busy === "compact" && <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />}
            Compact the database
          </button>
        </div>
      )}
    </section>
  );
}

function SizeRow({ label, rows, bytes, total }: { label: string; rows?: number | null; bytes: string; total?: boolean }) {
  return (
    <div className={cn("flex items-baseline gap-4", total && "border-t border-edge pt-1.5")}>
      <dt className={cn("min-w-0 flex-1", total ? "text-ink-primary" : "text-ink-secondary")}>{label}</dt>
      <dd className="studio-meta shrink-0 text-ink-muted">
        {rows === null || rows === undefined ? "" : `${count(rows)} ROWS`}
      </dd>
      <dd className="studio-meta w-[10ch] shrink-0 text-right text-ink-primary">{bytes}</dd>
    </div>
  );
}

function Backups({ view, busy, changeRule }: { view: StorageOverview; busy: string | null; changeRule: ChangeRule }) {
  const { backups, rules, defaults } = view;
  const last = backups.last;
  const failedDaily = backups.last_daily && !backups.last_daily.ok ? backups.last_daily : null;
  return (
    <section aria-labelledby="storage-backups" className="border-t border-edge pt-5">
      <h2 id="storage-backups" className="studio-label mb-2">
        Backups
      </h2>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <label htmlFor="rule-daily-backup" className="text-[13px] text-ink-secondary">
          Back up automatically once a day
        </label>
        <select
          id="rule-daily-backup"
          className={SELECT}
          value={rules.daily_backup}
          disabled={busy !== null}
          onChange={(event) => void changeRule({ daily_backup: event.target.value as RetentionRules["daily_backup"] })}
        >
          <option value="on">On</option>
          <option value="off">Off</option>
        </select>
        <span className="studio-meta text-ink-muted">DEFAULT {defaults.daily_backup.toUpperCase()}</span>
      </div>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1.5 text-[13px]">
        <dt className="text-ink-muted">Last backup</dt>
        <dd className="break-all text-ink-secondary">
          {last
            ? `${formatLocal(last.made_at)}, ${readableBytes(last.bytes)}, ${
                last.verified === true ? "checked when made" : last.verified === false ? "failed its check" : "made before checks were recorded"
              }`
            : "No full backup yet"}
        </dd>
        <dt className="text-ink-muted">Next automatic backup</dt>
        <dd className="text-ink-secondary">
          {backups.next_due ? `${formatLocal(backups.next_due)} or soon after, while the studio is open` : "Off"}
        </dd>
        <dt className="text-ink-muted">Folder</dt>
        <dd className="break-all text-ink-secondary">{backups.directory}</dd>
      </dl>
      {failedDaily && (
        <p className="mt-2 text-[13px] text-signal-orange-text">
          The automatic backup at {formatLocal(failedDaily.at)} did not complete: {failedDaily.error}. Nothing was
          cleaned up that day, and your earlier backups are unchanged.
        </p>
      )}
      <p className="mt-3 text-[13px] leading-relaxed text-ink-secondary">
        Each backup is checked as it is made: the database copy must pass SQLite&apos;s integrity check and the
        archive is read back, or it is not kept. The studio keeps the newest automatic backup of each of the last{" "}
        {backups.keeps.daily} days, then of {backups.keeps.weekly} weeks, then of {backups.keeps.monthly} months,
        about {backups.keeps.daily + backups.keeps.weekly + backups.keeps.monthly} in all, and the last{" "}
        {backups.keeps.database_copies} copies taken before an upgrade. Backups you make with{" "}
        <span className="text-ink-primary">Back up now</span> are kept until you delete them.
      </p>
    </section>
  );
}

const RULE_COPY: Record<RetentionJob, { title: string; confirm: string }> = {
  telemetry: { title: "Network readings log", confirm: "Back up, then remove" },
  readings: { title: "Post readings", confirm: "Back up, then roll up" },
  reactions: { title: "Reactions older than 24 months", confirm: "Back up, then fold" },
};

function describePreview(preview: RetentionPreview): string {
  const size = preview.bytes === null ? "" : `, about ${readableBytes(preview.bytes)}`;
  if (preview.rows === 0) return "Nothing to remove now.";
  if (preview.job === "telemetry") {
    return `Removes ${count(preview.rows)} entries older than ${preview.older_than_days} days${size}.`;
  }
  if (preview.job === "readings") {
    return (
      `Removes ${count(preview.rows)} of ${count(preview.total_rows)} readings, on ${count(preview.posts)} posts${size}. ` +
      "Kept: the last reading of every day, every reading from 36 to 72 hours after a post went out, and everything " +
      `from the last ${preview.older_than_days} days, so Today's two-day comparison and each post's latest figures are exactly what they were.`
    );
  }
  return (
    `Folds ${count(preview.rows)} reactions on ${count(preview.posts)} posts, from ${count(preview.people)} people, ` +
    `into a count per post${size}. Who reacted is no longer listed on those posts; how many reacted is kept. ` +
    `${count(preview.comments_kept)} comments are kept, all of them.` +
    (preview.people_left_without_engagement
      ? ` ${count(preview.people_left_without_engagement)} people reacted only in that time; they stay in your leads with no engagement shown.`
      : "")
  );
}

function Rules({
  view,
  busy,
  act,
  changeRule,
}: {
  view: StorageOverview;
  busy: string | null;
  act: Act;
  changeRule: ChangeRule;
}) {
  const [previews, setPreviews] = useState<Partial<Record<RetentionJob, RetentionPreview>>>({});
  const { rules, defaults } = view;

  async function showPreview(job: RetentionJob) {
    await act(`preview-${job}`, async () => {
      const preview = await previewRetention(job);
      setPreviews((current) => ({ ...current, [job]: preview }));
      return null;
    });
  }

  function confirm(job: RetentionJob) {
    void act(`run-${job}`, async () => {
      const done = await runRetention(job);
      setPreviews((current) => ({ ...current, [job]: undefined }));
      return done.backup
        ? `Done: ${count(done.removed)} removed, behind the checked backup ${done.backup}.`
        : "Done: nothing to remove now, and the rule is on.";
    });
  }

  const state: Record<RetentionJob, string> = {
    telemetry: "on",
    readings: rules.readings,
    reactions: rules.fold_reactions,
  };

  return (
    <section aria-labelledby="storage-rules" className="border-t border-edge pt-5">
      <h2 id="storage-rules" className="studio-label mb-2">
        What is kept, and for how long
      </h2>
      <p className="mb-4 text-[13px] leading-relaxed text-ink-secondary">
        Your posts, drafts, notes, daily analytics, comments and connections are kept for good. The rules below
        cover what grows without end. Each cleanup can be previewed, runs after a checked backup, and is listed
        under Recent cleanups. Where readings or reactions were already here, nothing is removed until you
        confirm the preview.
      </p>

      <ul className="flex flex-col gap-5">
        {(["telemetry", "readings", "reactions"] as RetentionJob[]).map((job) => {
          const preview = previews[job];
          const on = state[job] === "on";
          return (
            <li key={job} className="flex flex-col gap-2">
              <div className="flex flex-wrap items-baseline justify-between gap-3">
                <span className="text-[13px] text-ink-primary">{RULE_COPY[job].title}</span>
                <span
                  className={cn(
                    "studio-meta",
                    state[job] === "ask" ? "text-signal-orange-text" : on ? "text-signal-green-text" : "text-ink-muted",
                  )}
                >
                  {state[job] === "ask" ? "WAITING FOR YOU" : on ? "ON" : "OFF"}
                </span>
              </div>

              {job === "telemetry" && (
                <div className="flex flex-wrap items-center gap-3">
                  <label htmlFor="rule-telemetry" className="text-[13px] text-ink-secondary">
                    What the extension saw of LinkedIn&apos;s network requests, kept for
                  </label>
                  <select
                    id="rule-telemetry"
                    className={SELECT}
                    value={rules.telemetry_days}
                    disabled={busy !== null}
                    onChange={(event) =>
                      void changeRule({ telemetry_days: event.target.value as RetentionRules["telemetry_days"] })
                    }
                  >
                    {view.options.telemetry_days.map((days) => (
                      <option key={days} value={days}>
                        {days} days
                      </option>
                    ))}
                  </select>
                  <span className="studio-meta text-ink-muted">DEFAULT {defaults.telemetry_days} DAYS</span>
                </div>
              )}
              {job === "readings" && (
                <div className="flex flex-wrap items-center gap-3">
                  <label htmlFor="rule-readings" className="text-[13px] text-ink-secondary">
                    Every reading of a post&apos;s figures is kept for
                  </label>
                  <select
                    id="rule-readings"
                    className={SELECT}
                    value={rules.readings_days}
                    disabled={busy !== null}
                    onChange={(event) =>
                      void changeRule({ readings_days: event.target.value as RetentionRules["readings_days"] })
                    }
                  >
                    {view.options.readings_days.map((days) => (
                      <option key={days} value={days}>
                        {days} days
                      </option>
                    ))}
                  </select>
                  <span className="text-[13px] text-ink-secondary">then the last of each day.</span>
                  <span className="studio-meta text-ink-muted">DEFAULT {defaults.readings_days} DAYS</span>
                </div>
              )}
              {job === "reactions" && (
                <p className="text-[13px] leading-relaxed text-ink-secondary">
                  A reaction nobody has seen again for 24 months becomes part of its post&apos;s count of folded
                  reactions. Comments are always kept. Default: on for a new install.
                </p>
              )}

              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  className={BUTTON}
                  disabled={busy !== null}
                  onClick={() => void showPreview(job)}
                >
                  {busy === `preview-${job}` && <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />}
                  {on || job === "telemetry" ? "Preview" : "Preview and turn on"}
                </button>
                {on && job !== "telemetry" && (
                  <button
                    type="button"
                    className={BUTTON}
                    disabled={busy !== null}
                    onClick={() =>
                      void changeRule(job === "readings" ? { readings: "off" } : { fold_reactions: "off" })
                    }
                  >
                    Turn off
                  </button>
                )}
              </div>

              {preview && (
                <div className="rounded-md border border-edge p-3">
                  <p className="text-[13px] leading-relaxed text-ink-secondary">{describePreview(preview)}</p>
                  {(preview.rows > 0 || !on) && (
                    <button
                      type="button"
                      className={cn(PRIMARY, "mt-2")}
                      disabled={busy !== null}
                      onClick={() => confirm(job)}
                    >
                      {busy === `run-${job}` && <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />}
                      {preview.rows > 0 ? RULE_COPY[job].confirm : "Turn on"}
                    </button>
                  )}
                  {job !== "telemetry" && (
                    <p className="mt-2 text-[12px] text-ink-muted">
                      Confirming also keeps this on: from then on the daily run does it after the daily backup.
                    </p>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Review({
  view,
  busy,
  act,
  changeRule,
}: {
  view: StorageOverview;
  busy: string | null;
  act: Act;
  changeRule: ChangeRule;
}) {
  const [leads, setLeads] = useState<SilentLead[] | null>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [confirming, setConfirming] = useState(false);
  const [result, setResult] = useState<ForgetResult | null>(null);
  const months = Math.round(view.review.silent_days / 30.4);

  async function open() {
    await act("review", async () => {
      const listing = await fetchSilentLeads();
      setLeads(listing.leads);
      setChosen(new Set());
      return null;
    });
  }

  function toggle(id: string) {
    setChosen((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function forget() {
    const ids = [...chosen];
    setConfirming(false);
    await act("forget", async () => {
      const done = await forgetSilentLeads(ids);
      setResult(done);
      setLeads((current) => (current ? current.filter((lead) => !ids.includes(lead.id)) : current));
      setChosen(new Set());
      return (
        `Forgot ${count(done.forgotten)}.` +
        (done.kept_since ? ` Kept ${count(done.kept_since)} who have engaged or been acted on since the list was shown.` : "") +
        (done.backup ? ` A backup was made first: ${done.backup}.` : "")
      );
    });
  }

  async function keep() {
    const ids = [...chosen];
    await act("keep", async () => {
      const done = await keepSilentLeads(ids);
      setLeads((current) => (current ? current.filter((lead) => !ids.includes(lead.id)) : current));
      setChosen(new Set());
      return `Kept ${count(done.kept)}. They will not be listed here again.`;
    });
  }

  return (
    <section aria-labelledby="storage-review" className="border-t border-edge pt-5">
      <h2 id="storage-review" className="studio-label mb-2">
        People silent for {months} months
      </h2>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <label htmlFor="rule-lead-review" className="text-[13px] text-ink-secondary">
          People you never acted on, silent for {months} months
        </label>
        <select
          id="rule-lead-review"
          className={SELECT}
          value={view.rules.lead_review}
          disabled={busy !== null}
          onChange={(event) => void changeRule({ lead_review: event.target.value as RetentionRules["lead_review"] })}
        >
          <option value="ask">List them for me to review</option>
          <option value="off">Do not list them</option>
        </select>
        <span className="studio-meta text-ink-muted">DEFAULT: LIST THEM</span>
      </div>

      {view.rules.lead_review === "ask" && (
        <>
          <p className="text-[13px] leading-relaxed text-ink-secondary">
            {view.review.count === 0
              ? `Nobody right now. Someone appears here when they are still New, you have written no note, changed no stage and enriched nothing, and nothing has been seen from them for ${months} months.`
              : `${count(view.review.count)} ${view.review.count === 1 ? "person is" : "people are"} still New, with no note, no stage change and no enrichment, and nothing seen from them for ${months} months. Nobody is forgotten unless you choose them here.`}
          </p>
          {view.review.count > 0 && leads === null && (
            <button type="button" className={cn(BUTTON, "mt-2")} disabled={busy !== null} onClick={() => void open()}>
              {busy === "review" && <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />}
              Review them
            </button>
          )}
        </>
      )}

      {leads !== null && leads.length > 0 && (
        <div className="mt-3">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <button
              type="button"
              className={BUTTON}
              disabled={busy !== null}
              onClick={() => setChosen(chosen.size === leads.length ? new Set() : new Set(leads.map((lead) => lead.id)))}
            >
              {chosen.size === leads.length ? "Choose none" : `Choose all ${count(leads.length)} shown`}
            </button>
            <button
              type="button"
              className={BUTTON}
              disabled={busy !== null || chosen.size === 0}
              onClick={() => setConfirming(true)}
            >
              Forget {count(chosen.size)}
            </button>
            <button type="button" className={BUTTON} disabled={busy !== null || chosen.size === 0} onClick={() => void keep()}>
              {busy === "keep" && <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />}
              Keep {count(chosen.size)}
            </button>
          </div>

          {confirming && (
            <div role="alertdialog" aria-labelledby="forget-confirm" className="mb-3 rounded-md border border-edge p-3">
              <p id="forget-confirm" className="text-[13px] leading-relaxed text-ink-primary">
                Forget {count(chosen.size)} {chosen.size === 1 ? "person" : "people"}? Their lead, engagement and
                history are removed from this database. A backup is made first, and copies stay in backups made
                before now until those are removed; see below.
              </p>
              <div className="mt-2 flex gap-2">
                <button type="button" className={PRIMARY} disabled={busy !== null} onClick={() => void forget()}>
                  {busy === "forget" && <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />}
                  Forget them
                </button>
                <button type="button" className={BUTTON} onClick={() => setConfirming(false)}>
                  Cancel
                </button>
              </div>
            </div>
          )}

          <ul className="flex max-h-[320px] flex-col gap-1 overflow-y-auto">
            {leads.map((lead) => (
              <li key={lead.id}>
                <label className="flex items-baseline gap-2 text-[13px]">
                  <input type="checkbox" checked={chosen.has(lead.id)} onChange={() => toggle(lead.id)} />
                  <span className="text-ink-primary">{lead.name || "No name recorded"}</span>
                  <span className="truncate text-ink-muted">{[lead.headline, lead.company].filter(Boolean).join(", ")}</span>
                  <span className="studio-meta ml-auto shrink-0 text-ink-muted">
                    {lead.interactions === 0 ? "NO ENGAGEMENT KEPT" : `LAST SEEN ${formatLocal(utc(lead.last_activity))}`}
                  </span>
                </label>
              </li>
            ))}
          </ul>
          {view.review.count > leads.length && (
            <p className="mt-2 text-[12px] text-ink-muted">
              The first {count(leads.length)} of {count(view.review.count)}, longest silent first.
            </p>
          )}
        </div>
      )}

      {result && result.forgotten > 0 && (
        <p className="mt-3 text-[13px] leading-relaxed text-ink-secondary">
          Copies of them remain in {count(result.backups.automatic_backups + result.backups.your_backups)} backup
          {result.backups.automatic_backups + result.backups.your_backups === 1 ? "" : "s"} and{" "}
          {count(result.backups.database_copies)} pre-upgrade cop{result.backups.database_copies === 1 ? "y" : "ies"}.
          Automatic backups holding them are removed by rotation by {result.backups.automatic_gone_by}. To remove
          them from every backup now, use Remove from backups too below.
        </p>
      )}
    </section>
  );
}

function ForgottenInBackups({ view, busy, act }: { view: StorageOverview; busy: string | null; act: Act }) {
  const reach = view.backups.rotation_reach_days;
  return (
    <section aria-labelledby="storage-forgotten" className="border-t border-edge pt-5">
      <h2 id="storage-forgotten" className="studio-label mb-2">
        Forgotten people and backups
      </h2>
      <p className="text-[13px] leading-relaxed text-ink-secondary">
        Forgetting someone removes them from this database at once, and the words are overwritten, not only
        marked deleted. Copies stay in backups made before then: in automatic backups until rotation removes
        them, within {reach} days; in copies taken before an upgrade
        until two more upgrades; and in backups you made yourself until you delete them.
      </p>
      {view.scrub.people > 0 && (
        <div className="mt-3 rounded-md border border-edge p-3">
          <p className="text-[13px] leading-relaxed text-ink-primary">
            {count(view.scrub.people)} {view.scrub.people === 1 ? "person" : "people"} removed from your leads may still be
            in older backups.
          </p>
          <p className="mt-1 text-[12px] leading-relaxed text-ink-muted">
            Remove from backups too rewrites each backup without them, checks it, and only then replaces the
            original, keeping its date. It can take a minute for a large studio. The studio keeps a list of who to
            remove only until you choose.
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              className={PRIMARY}
              disabled={busy !== null}
              onClick={() =>
                void act("scrub", async () => {
                  const done = await scrubBackups(false);
                  const failed = done.failed ?? [];
                  return (
                    `Removed from ${count(done.rewritten)} backup${done.rewritten === 1 ? "" : "s"}; ` +
                    `${count(done.unchanged)} did not hold them.` +
                    (failed.length
                      ? ` ${failed.length} could not be rewritten and still hold them: ${failed.map((f) => `${f.name} (${f.error})`).join("; ")}.`
                      : "")
                  );
                })
              }
            >
              {busy === "scrub" ? (
                <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
              ) : (
                <Archive className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
              )}
              Remove from backups too
            </button>
            <button
              type="button"
              className={BUTTON}
              disabled={busy !== null}
              onClick={() =>
                void act("leave", async () => {
                  await scrubBackups(true);
                  return "Left to rotation. Backups you made yourself still hold them until you delete them.";
                })
              }
            >
              Leave them until the backups expire
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function CleanupLog({ view }: { view: StorageOverview }) {
  return (
    <section aria-labelledby="storage-log" className="border-t border-edge pt-5">
      <h2 id="storage-log" className="studio-label mb-2">
        Recent cleanups
      </h2>
      {view.log.length === 0 ? (
        <p className="studio-meta text-ink-muted">NONE YET</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {view.log.slice(0, 8).map((entry, index) => (
            <li key={`${entry.started_at}-${index}`} className="flex items-baseline justify-between gap-3 text-[12px]">
              <span className="text-ink-secondary">
                {JOB_NAME[entry.job] ?? entry.job}: {entry.outcome}
                {entry.removed ? `, ${count(entry.removed)}` : ""}
              </span>
              <span className="studio-meta shrink-0 text-ink-muted">{formatLocal(utc(entry.started_at))}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
