import { useEffect, useState } from "react";
import { fetchRecordEvaluation, saveRecordNote, type RecordEvaluation, type RecordFunnelRow } from "@/lib/api";

/**
 * Did these help? Three answers, each with its counts and each able to say
 * it cannot say anything yet: what you kept, drafted from and posted, which
 * is your preference and not an effect; your posts that came from a card
 * against your others of the same months, at about two days; and a sentence
 * a month. A note in your own words is kept here and sent nowhere.
 */
export function RecordEvaluationPanel() {
  const [data, setData] = useState<RecordEvaluation | null>(null);
  const [failed, setFailed] = useState(false);
  const [note, setNote] = useState("");
  const [said, setSaid] = useState<{ text: string; error: boolean } | null>(null);

  useEffect(() => {
    fetchRecordEvaluation()
      .then((answer) => {
        setData(answer);
        setNote(answer.notes[answer.this_month] ?? "");
      })
      .catch(() => setFailed(true));
  }, []);

  if (failed && !data) return <p className="studio-meta text-[10px] text-ink-muted">THIS COULD NOT BE READ. IS THE STUDIO RUNNING?</p>;
  if (!data) return <p className="studio-meta text-[10px] text-ink-muted">READING YOUR MARKS</p>;

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <section aria-labelledby="record-funnel-title">
        <p id="record-funnel-title" className="studio-label mb-2">
          What you kept, drafted from and posted
        </p>
        <p className="mb-2 max-w-[70ch] text-[12px] leading-snug text-ink-secondary">{data.funnel.note}</p>
        {data.funnel.by_kind.length === 0 ? (
          <p className="text-[12px] text-ink-muted">No cards have been shown yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[12px]">
              <thead>
                <tr className="studio-meta text-[10px] text-ink-muted">
                  <th className="py-1 font-normal">CARD</th>
                  <th className="py-1 text-right font-normal">SHOWN</th>
                  <th className="py-1 text-right font-normal">KEPT, OF KEPT OR SKIPPED</th>
                  <th className="py-1 text-right font-normal">DRAFTED FROM, OF SHOWN</th>
                  <th className="py-1 text-right font-normal">POSTED, OF DRAFTED</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-edge border-y border-edge">
                {[...data.funnel.by_kind, ...(data.funnel.total ? [data.funnel.total] : [])].map((row) => (
                  <FunnelRow key={row.name} row={row} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="flex flex-col gap-5">
        <section aria-labelledby="record-compare-title">
          <p id="record-compare-title" className="studio-label mb-2">
            Posts from cards, against your others
          </p>
          <p className="text-[12px] leading-snug text-ink-secondary">{data.comparison.sentence}</p>
        </section>

        <section aria-labelledby="record-months-title">
          <p id="record-months-title" className="studio-label mb-2">
            Month by month
          </p>
          <ul className="flex flex-col gap-1.5 text-[12px] leading-snug text-ink-secondary">
            {data.months.map((month) => (
              <li key={month.month}>{month.sentence}</li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="record-note-title">
          <label id="record-note-title" htmlFor="record-note" className="studio-label">
            Did they help this month? In your own words
          </label>
          <textarea
            id="record-note"
            rows={3}
            maxLength={2000}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            className="mt-2 w-full resize-none rounded-md border border-edge bg-ink px-2 py-1.5 text-[12px] text-ink-primary"
          />
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() =>
                void saveRecordNote(data.this_month, note)
                  .then(() => setSaid({ text: note.trim() ? "Kept here. It is sent nowhere." : "Removed.", error: false }))
                  .catch((error) => setSaid({ text: error instanceof Error ? error.message : "Not kept.", error: true }))
              }
              className="rounded-md border border-edge px-2 py-1 text-[12px] text-ink-secondary hover:text-ink-primary"
            >
              Keep this note
            </button>
            {said && (
              <span role="status" className={said.error ? "text-[12px] text-signal-orange-text" : "text-[12px] text-ink-muted"}>
                {said.text}
              </span>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function FunnelRow({ row }: { row: RecordFunnelRow }) {
  return (
    <tr>
      <td className="py-1 text-ink-primary">{row.name}</td>
      <td className="py-1 text-right tabular-nums text-ink-secondary">{row.shown}</td>
      <td className="py-1 text-right tabular-nums text-ink-secondary">{row.kept.said}</td>
      <td className="py-1 text-right tabular-nums text-ink-secondary">{row.drafted.said}</td>
      <td className="py-1 text-right tabular-nums text-ink-secondary">{row.posted.said}</td>
    </tr>
  );
}
