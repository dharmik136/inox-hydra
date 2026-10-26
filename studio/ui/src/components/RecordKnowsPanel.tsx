import { useCallback, useEffect, useState } from "react";
import {
  fetchRecordKnows,
  removeRecordAsk,
  setRecordSettings,
  unhideAllRecord,
  updateRecordAsk,
  type RecordAsk,
  type RecordKnows,
} from "@/lib/api";
import { formatLocal, formatLocalDay } from "@/lib/time";
import { RecordSetupFields } from "./RecordSetupFields";
import { RecordModelSettings } from "./RecordModelSettings";
import { RecordLibraryPanel } from "./RecordLibraryPanel";

/**
 * What the studio knows: everything From your record has been told and has
 * kept, on one page, editable and reversible. The asks and where each came
 * from, the Setup answers, the marks and what is hidden, what the archive
 * brought, how long the daily batches are kept, the model stage and the
 * library. Nothing here is sent anywhere.
 */
const SOURCE_WORDS: Record<string, string> = {
  setup: "at Setup",
  ask_box: "in the ask box",
  composer: "from a Composer instruction you ticked",
  telegram: "from Telegram",
  more_of_this: "with More of this",
  archive_search: "from your archive's searches",
};

const ARCHIVE_WORDS: Record<string, string> = {
  saved_item: "saved posts",
  member_follow: "members you follow",
  company_follow: "companies you follow",
  vote: "poll votes",
  article: "articles you published",
  search_query: "searches you made",
};

export function RecordKnowsPanel() {
  const [knows, setKnows] = useState<RecordKnows | null>(null);
  const [failed, setFailed] = useState(false);
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);

  const load = useCallback(() => {
    fetchRecordKnows()
      .then((data) => {
        setKnows(data);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, []);
  useEffect(load, [load]);

  async function run(work: () => Promise<unknown>, said?: string) {
    try {
      await work();
      if (said) setNote({ text: said, error: false });
      load();
    } catch (error) {
      setNote({ text: error instanceof Error ? error.message : "That did not work.", error: true });
    }
  }

  if (failed && !knows) return <p className="studio-meta text-[10px] text-ink-muted">WHAT THE STUDIO KNOWS COULD NOT BE READ. IS THE STUDIO RUNNING?</p>;
  if (!knows) return <p className="studio-meta text-[10px] text-ink-muted">READING WHAT THE STUDIO KNOWS</p>;

  const open = knows.asks.filter((ask) => ask.status !== "retired" && ask.source !== "setup");
  const retired = knows.asks.filter((ask) => ask.status === "retired" && ask.source !== "setup");
  const archive = Object.entries(knows.archive);

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="flex flex-col gap-6">
        <section aria-labelledby="record-asks-title">
          <p id="record-asks-title" className="studio-label mb-2">
            Your asks ({open.length})
          </p>
          {open.length === 0 ? (
            <p className="text-[12px] text-ink-muted">Nothing asked yet. Type into the ask box on Today, or answer the questions below.</p>
          ) : (
            <ul className="flex flex-col divide-y divide-edge border-y border-edge">
              {open.map((ask) => (
                <AskRow key={ask.id} ask={ask} onChanged={load} onError={(text) => setNote({ text, error: true })} />
              ))}
            </ul>
          )}
          {retired.length > 0 && (
            <details className="mt-2 text-[12px] text-ink-secondary">
              <summary className="cursor-pointer text-ink-muted">Retired asks ({retired.length})</summary>
              <ul className="mt-1 flex flex-col gap-1">
                {retired.map((ask) => (
                  <li key={ask.id} className="flex flex-wrap items-center gap-2">
                    <span>&ldquo;{ask.text}&rdquo;</span>
                    <button type="button" className="text-[11px] underline underline-offset-2" onClick={() => void run(() => updateRecordAsk(ask.id, { status: "open" }), "Back in use from tomorrow.")}>
                      Use again
                    </button>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>

        <RecordSetupFields />

        <section aria-labelledby="record-marks-title">
          <p id="record-marks-title" className="studio-label mb-2">
            Your marks
          </p>
          <p className="text-[12px] leading-snug text-ink-secondary">
            {knows.marks.keep} kept, {knows.marks.skip} skipped, {knows.marks.hide} hidden; {knows.marks.used} cards drafted
            from and {knows.marks.posted} of those posted. Marks change which cards come back, never a figure.
          </p>
          {knows.hidden.length > 0 && (
            <>
              <ul className="mt-2 flex flex-col gap-1 text-[12px] text-ink-muted">
                {knows.hidden.map((item) => (
                  <li key={`${item.day}-${item.card_id}`}>
                    {item.title ?? item.kind ?? "A card"}
                    {item.excerpt ? `: "${item.excerpt}"` : ""} (hidden {formatLocalDay(item.at)})
                  </li>
                ))}
              </ul>
              <button
                type="button"
                className="mt-2 rounded-md border border-edge px-2 py-1 text-[12px] text-ink-secondary hover:text-ink-primary"
                onClick={() => void run(async () => {
                  const done = await unhideAllRecord();
                  setNote({ text: `${done.cards} cards unhidden. ${done.message}`, error: false });
                })}
              >
                Unhide all
              </button>
            </>
          )}
        </section>
      </div>

      <div className="flex flex-col gap-6">
        <section aria-labelledby="record-archive-title">
          <p id="record-archive-title" className="studio-label mb-2">
            From your LinkedIn archive
          </p>
          {archive.length === 0 ? (
            <p className="text-[12px] text-ink-muted">
              Nothing beyond your posts, comments and reactions. Saved posts, follows, poll votes and articles arrive with
              your archive in Setup; searches only if you tick them there.
            </p>
          ) : (
            <p className="text-[12px] leading-snug text-ink-secondary">
              {archive.map(([kind, count]) => `${count.toLocaleString()} ${ARCHIVE_WORDS[kind] ?? kind}`).join(", ")}.
            </p>
          )}
        </section>

        <section aria-labelledby="record-keep-title">
          <p id="record-keep-title" className="studio-label mb-2">
            How long the daily cards are kept
          </p>
          <div className="flex flex-wrap items-center gap-2 text-[12px] text-ink-secondary">
            <label htmlFor="record-keep-days">Keep each day&rsquo;s cards</label>
            <select
              id="record-keep-days"
              value={knows.settings.keep_days}
              onChange={(event) => void run(() => setRecordSettings({ keep_days: event.target.value }), "Saved.")}
              className="rounded-md border border-edge bg-ink px-2 py-1 text-[12px] text-ink-primary"
            >
              {knows.settings.keep_days_options.map((option) => (
                <option key={option} value={option}>
                  {option === "forever" ? "for good" : `${option} days`}
                </option>
              ))}
            </select>
          </div>
          <p className="mt-1 text-[11px] leading-snug text-ink-muted">
            {knows.batches.days.toLocaleString()} days of cards are kept
            {knows.batches.first ? `, from ${formatLocalDay(knows.batches.first)}` : ""}. A day a mark or a draft refers
            to is never removed.{" "}
            {knows.prune.days > 0
              ? `${knows.prune.days} older days (${knows.prune.cards} cards) go at the next daily run.`
              : "Nothing is old enough to go yet."}
          </p>
        </section>

        <RecordModelSettings state={knows.model} settings={knows.settings} onChanged={load} />

        <RecordLibraryPanel state={knows.library} onChanged={load} />

        <section aria-labelledby="record-job-title">
          <p id="record-job-title" className="studio-label mb-2">
            The daily batch
          </p>
          <p className="text-[12px] leading-snug text-ink-secondary">
            Built the first time the studio runs each day: checked {knows.job.checked}.{" "}
            {knows.job.today_built ? "Today's is built." : "Today's has not been built yet."}{" "}
            {knows.job.last_run
              ? `Last built for ${formatLocalDay(knows.job.last_run.day)}, at ${formatLocal(knows.job.last_run.finished_at, "a time not recorded")}${
                  knows.job.last_run.carried_from ? `, carried forward from ${formatLocalDay(knows.job.last_run.carried_from)}` : ""
                }.`
              : "No batch has been built yet."}
          </p>
        </section>
      </div>

      {note && (
        <p role="status" className={note.error ? "text-[12px] text-signal-orange-text xl:col-span-2" : "text-[12px] text-ink-muted xl:col-span-2"}>
          {note.text}
        </p>
      )}
    </div>
  );
}

function AskRow({ ask, onChanged, onError }: { ask: RecordAsk; onChanged: () => void; onError: (text: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(ask.text);

  async function run(work: () => Promise<unknown>) {
    try {
      await work();
      setEditing(false);
      onChanged();
    } catch (error) {
      onError(error instanceof Error ? error.message : "That did not work.");
    }
  }

  return (
    <li className="py-2">
      {editing ? (
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor={`record-ask-${ask.id}`} className="sr-only">
            Edit this ask
          </label>
          <input
            id={`record-ask-${ask.id}`}
            value={text}
            maxLength={2000}
            onChange={(event) => setText(event.target.value)}
            className="min-w-[16rem] flex-1 rounded-md border border-edge bg-ink px-2 py-1 text-[13px] text-ink-primary"
          />
          <button type="button" className="rounded-md border border-edge px-2 py-1 text-[12px]" onClick={() => void run(() => updateRecordAsk(ask.id, { text }))}>
            Save
          </button>
          <button type="button" className="px-1 text-[12px] text-ink-muted underline underline-offset-2" onClick={() => setEditing(false)}>
            Cancel
          </button>
        </div>
      ) : (
        <p className="text-[13px] text-ink-primary">&ldquo;{ask.text}&rdquo;</p>
      )}
      <div className="mt-1 flex flex-wrap items-center gap-3 text-[11px] text-ink-muted">
        <span>
          {SOURCE_WORDS[ask.source] ?? ask.source}, {formatLocalDay(ask.created_at)}
          {ask.last_used_at ? `; drafted from ${formatLocalDay(ask.last_used_at)}` : ""}
        </span>
        {!editing && (
          <button type="button" className="underline underline-offset-2 hover:text-ink-primary" onClick={() => setEditing(true)}>
            Edit
          </button>
        )}
        <button type="button" className="underline underline-offset-2 hover:text-ink-primary" onClick={() => void run(() => updateRecordAsk(ask.id, { status: "retired" }))}>
          Retire
        </button>
        <button type="button" className="underline underline-offset-2 hover:text-ink-primary" onClick={() => void run(() => removeRecordAsk(ask.id))}>
          Remove for good
        </button>
      </div>
    </li>
  );
}
