import { useEffect, useRef, useState } from "react";
import { ExternalLink, FileSpreadsheet, Loader2 } from "lucide-react";
import {
  discardAnalyticsExport,
  fetchAnalyticsExportState,
  importAnalyticsExport,
  markAnalyticsExportRequested,
  previewAnalyticsExport,
  uploadAnalyticsExport,
  type ExportImport,
  type ExportPreview,
  type ExportState,
} from "@/lib/api";

const LOOK_MS = 4000;

/**
 * Setup, LinkedIn's analytics export, beside the archive.
 *
 * The archive carries no figures. LinkedIn's analytics page has an Export
 * button that writes an .xlsx of the creator's own figures for up to a year,
 * exact rather than rounded, and handing that file over touches nothing of
 * LinkedIn's. The steps are the archive's: open the page, say you exported,
 * the studio looks in Downloads, nothing is written until the preview has
 * been seen sheet by sheet, and what is not recognised is said so and left
 * out. The sentence on whether the layout has been checked against a real
 * export is the server's, so it changes here the day it changes there.
 */
export function AnalyticsExportImport({
  busyUrl,
  onOpenPage,
}: {
  busyUrl: string | null;
  onOpenPage: (url: string) => void;
}) {
  const [state, setState] = useState<ExportState | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [preview, setPreview] = useState<ExportPreview | null>(null);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<ExportImport["summary"] | null>(null);
  const picker = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let live = true;
    const look = () =>
      fetchAnalyticsExportState()
        .then((fresh) => live && setState(fresh))
        .catch(() => undefined);
    void look();
    // Downloads is looked in only while the creator has said they exported and nothing has been imported since.
    const timer = window.setInterval(() => {
      if (state?.waiting) void look();
    }, LOOK_MS);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [state?.waiting]);

  async function run(key: string, work: () => Promise<void>) {
    setBusy(key);
    setNote(null);
    try {
      await work();
    } catch (caught) {
      setNote(caught instanceof Error ? caught.message : "That did not work.");
    } finally {
      setBusy(null);
    }
  }

  function show(next: ExportPreview) {
    setResult(null);
    setPreview(next);
    setTicked(new Set(next.sheets.filter((sheet) => sheet.importable && sheet.default).map((sheet) => sheet.name)));
  }

  function close() {
    if (preview && !result && preview.source.startsWith("upload:")) void discardAnalyticsExport(preview.source);
    setPreview(null);
    setResult(null);
  }

  if (!state) return null;

  return (
    <section className="mt-6 border-t border-edge pt-4" aria-labelledby="analytics-export-title">
      <p id="analytics-export-title" className="studio-label">
        LinkedIn&apos;s analytics export, for exact figures
      </p>
      <p className="mt-1.5 text-[13px] leading-relaxed text-ink-secondary">
        The archive carries your posts but no figures. On LinkedIn&apos;s analytics page, choose a range of up to a
        year and press Export. LinkedIn&apos;s help says the file holds your impressions and engagements for that
        range, exact rather than rounded; the studio also looks in it for new followers by day, your top and most
        recent posts, and the demographics LinkedIn gives as percentages.
        Bring it here and nothing is written until you have seen what is in it.
      </p>
      <p className="studio-meta mt-1.5 leading-relaxed text-signal-orange-text">{state.verification.toUpperCase()}</p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={busyUrl !== null}
          onClick={() => onOpenPage(state.analytics_page)}
          className="flex items-center gap-1.5 rounded-md bg-signal-orange px-3 py-1.5 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-40"
        >
          {busyUrl === state.analytics_page ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
          ) : (
            <ExternalLink className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
          )}
          Open LinkedIn&apos;s analytics page
        </button>
        {!state.waiting && (
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => void run("requested", async () => setState(await markAnalyticsExportRequested()))}
            className="rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
          >
            I have exported it
          </button>
        )}
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => picker.current?.click()}
          className="flex items-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
        >
          {busy === "upload" ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
          ) : (
            <FileSpreadsheet className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
          )}
          Choose the file
        </button>
        <input
          ref={picker}
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          tabIndex={-1}
          className="sr-only"
          aria-label="Choose your LinkedIn analytics export"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) void run("upload", async () => show(await uploadAnalyticsExport(file)));
          }}
        />
      </div>

      {state.waiting && (
        <div className="mt-3">
          <p className="studio-meta text-ink-muted">
            {state.found.length ? "IN YOUR DOWNLOADS FOLDER" : `LOOKING IN ${state.watching.join(", ") || "YOUR DOWNLOADS FOLDER"}`}
          </p>
          <ul className="mt-1.5 flex flex-col gap-1.5">
            {state.found.map((hit) => (
              <li key={hit.path} className="flex flex-wrap items-center justify-between gap-2 text-[12px] text-ink-primary">
                <span className="min-w-0 truncate">{hit.name}</span>
                {hit.downloading ? (
                  <span className="studio-meta text-ink-muted">STILL DOWNLOADING</span>
                ) : (
                  <button
                    type="button"
                    disabled={busy !== null}
                    onClick={() => void run(hit.path, async () => show(await previewAnalyticsExport(`downloads:${hit.path}`)))}
                    className="rounded-md border border-edge px-2 py-0.5 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
                  >
                    {hit.imported ? "Already imported. See what is in it" : "See what is in it"}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {preview && (
        <div className="mt-4 rounded-md border border-edge-strong px-3 py-3">
          <p className="text-[13px] font-medium text-ink-primary">{preview.file.name}</p>
          <p className="studio-meta mt-0.5 text-ink-muted">
            {preview.range.start && preview.range.end
              ? `COVERS ${preview.range.start} TO ${preview.range.end}, READ FROM ${(preview.range.from ?? "").toUpperCase()}`
              : "THE RANGE IT COVERS COULD NOT BE READ"}
          </p>
          {!preview.recognised && (
            <p className="mt-2 text-[12px] leading-relaxed text-signal-orange-text">
              Nothing in this file is recognised, so nothing can be imported from it.
            </p>
          )}
          <ul className="mt-3 flex flex-col gap-2.5">
            {preview.sheets.map((sheet) => (
              <li key={sheet.name} className="text-[12px] leading-relaxed">
                <label className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    disabled={!sheet.importable || result !== null}
                    checked={ticked.has(sheet.name)}
                    onChange={(event) => {
                      const next = new Set(ticked);
                      if (event.target.checked) next.add(sheet.name);
                      else next.delete(sheet.name);
                      setTicked(next);
                    }}
                  />
                  <span className="min-w-0">
                    <span className="text-ink-primary">{sheet.kind ? sheet.label : sheet.name}</span>
                    <span className="studio-meta ml-2 text-ink-muted">
                      {sheet.kind ? `SHEET ${sheet.name}` : "NOT RECOGNISED"}
                      {sheet.importable ? `, ${sheet.rows.toLocaleString()} ${sheet.rows === 1 ? "ROW" : "ROWS"}` : ""}
                    </span>
                    {sheet.importable && sheet.writes && <span className="block text-ink-secondary">{sheet.writes}</span>}
                    {sheet.note && <span className="block text-ink-muted">{sheet.note}</span>}
                  </span>
                </label>
              </li>
            ))}
          </ul>

          {result ? (
            <div className="mt-3">
              <p className="studio-label">Imported</p>
              <ul className="mt-1 flex flex-col gap-1 text-[12px] text-ink-secondary">
                {Object.entries(result).map(([name, tally]) => (
                  <li key={name}>{resultLine(name, tally)}</li>
                ))}
              </ul>
              <button
                type="button"
                onClick={close}
                className="mt-2 rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary"
              >
                Done
              </button>
            </div>
          ) : (
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={busy !== null || ticked.size === 0}
                onClick={() =>
                  void run("import", async () => {
                    const done = await importAnalyticsExport(preview.source, [...ticked]);
                    setResult(done.summary);
                    setState(await fetchAnalyticsExportState());
                  })
                }
                className="flex items-center gap-1.5 rounded-md bg-signal-orange px-3 py-1.5 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-40"
              >
                {busy === "import" && <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />}
                Import what is ticked
              </button>
              <button
                type="button"
                onClick={close}
                className="rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary"
              >
                Not now
              </button>
            </div>
          )}
        </div>
      )}

      {!preview && state.last_import && (
        <p className="studio-meta mt-3 text-ink-muted">
          LAST IMPORTED {localDate(state.last_import.imported_at).toUpperCase()} FROM {state.last_import.file}
        </p>
      )}

      {note && (
        <p role="status" className="mt-2 text-[12px] text-signal-orange-text">
          {note}
        </p>
      )}
    </section>
  );
}

/** One sheet's outcome in words, from the counts the server returned. */
function resultLine(name: string, tally: Record<string, unknown>): string {
  const count = (key: string) => (typeof tally[key] === "number" ? (tally[key] as number) : 0);
  if (typeof tally.left_out === "string") return `${name}: left out. ${tally.left_out}`;
  if (name === "days") {
    return `Days: ${count("added")} added, ${count("updated")} brought up to date, ${count("kept_as_read")} kept as your analytics page read them.`;
  }
  if ("published_outside_the_range" in tally) {
    return `${name}: ${count("added")} of your posts read; ${count("published_outside_the_range")} published outside the range left out; ${count("not_yours")} not among your recorded posts.`;
  }
  if ("days_read" in tally) return `${name}: ${count("days_read")} days read.`;
  if ("shares_kept" in tally) {
    const bounds = count("left_out_as_bounds");
    return `${name}: ${count("shares_kept")} shares kept, dated ${String(tally.dated)}${bounds ? `; ${bounds} given only as a bound, such as < 1%, left out` : ""}.`;
  }
  if (tally.kept && typeof tally.kept === "object") return `${name}: kept with the record of this import.`;
  if ("added" in tally) return `${name}: ${count("added") ? "read" : "not among your recorded posts"}.`;
  return `${name}: done.`;
}

function localDate(iso: string): string {
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? iso.slice(0, 10) : when.toLocaleDateString(undefined, { dateStyle: "medium" });
}
