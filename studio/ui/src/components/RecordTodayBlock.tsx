import { useCallback, useEffect, useState } from "react";
import { fetchRecordLines, type RecordLines } from "@/lib/api";
import { useRefresh } from "@/lib/refresh";

/**
 * From your record, on Today: the day's cards, one line each, each a link
 * into the section where the card can be kept, drafted from or opened.
 *
 * Drawn only once today's batch exists: before the daily job has built it,
 * and on a day it carried yesterday's batch forward but has not run yet,
 * there is nothing of today's to show and nothing is drawn. The read is a
 * SELECT of the stored batch (record_daily.lines_today); nothing is computed
 * on Today's load. It reads again when the studio says the day's cards
 * changed (the "ideas" change), not on a timer.
 */
export function RecordTodayBlock() {
  const [lines, setLines] = useState<RecordLines | null>(null);
  const load = useCallback(
    () =>
      fetchRecordLines()
        .then(setLines)
        .catch(() => setLines(null)),
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);
  useRefresh(load, undefined, ["ideas"]);

  if (!lines || !lines.built || lines.lines.length === 0) return null;

  return (
    <section aria-labelledby="today-record-title" className="mt-2 rounded-md border border-edge">
      <div className="flex items-baseline justify-between gap-3 border-b border-edge px-3 py-1.5">
        <p id="today-record-title" className="studio-label">
          From your record, today
        </p>
        <a href="#/record" className="studio-meta shrink-0 text-[10px] text-ink-muted hover:text-ink-primary">
          {lines.not_yet > 0 ? `${lines.not_yet} NOT YET · ` : ""}OPEN THE CARDS
        </a>
      </div>
      <ul className="grid gap-x-4 gap-y-1 px-3 py-2 md:grid-cols-2 xl:grid-cols-5">
        {lines.lines.map((line) => (
          <li key={line.card_id} className="min-w-0">
            {/* The block is said to a screen reader and left out of sight, so the
                line's own words have the width: five lines share one row. */}
            <a href="#/record" className="block truncate text-[12px] text-ink-secondary hover:text-ink-primary">
              {line.block_label && <span className="sr-only">{line.block_label}: </span>}
              <span className="text-ink-primary">{line.title}</span>
              {line.line ? ` ${line.line}` : ""}
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
