import { useRef, useState } from "react";
import { fetchLibraryBundle, importLibraryBundle, type RecordLibraryState } from "@/lib/api";
import { formatLocalDay } from "@/lib/time";

/**
 * The Inox library, on What the studio knows: what the company's signed
 * bundle holds, when it was signed, where it came from, and the two ways to
 * get it: Fetch, which sends one request carrying nothing of yours, and
 * Import, for a machine that never connects. A file whose signature does
 * not verify is refused and changes nothing.
 */
export function RecordLibraryPanel({ state, onChanged }: { state?: RecordLibraryState; onChanged: () => void }) {
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const picker = useRef<HTMLInputElement | null>(null);

  async function run(work: () => Promise<{ message: string }>) {
    if (busy) return;
    setBusy(true);
    try {
      const answer = await work();
      setNote({ text: answer.message, error: false });
      onChanged();
    } catch (error) {
      setNote({ text: error instanceof Error ? error.message : "That did not work.", error: true });
    } finally {
      setBusy(false);
    }
  }

  async function chosen(file: File | undefined) {
    if (!file) return;
    const text = await file.text();
    await run(() => importLibraryBundle(text));
    if (picker.current) picker.current.value = "";
  }

  return (
    <section aria-labelledby="record-library-title">
      <p id="record-library-title" className="studio-label mb-2">
        The Inox library
      </p>
      <p className="text-[12px] leading-snug text-ink-secondary">
        {state && state.entries > 0
          ? `${state.entries} entries, bundle ${state.version}, signed ${formatLocalDay(state.signed_at)} with ${state.key_id}; ${state.source}${
              state.fetched_at ? `, ${formatLocalDay(state.fetched_at)}` : ""
            }. An entry that suits one of your topics fills the fifth card when your own model does not.`
          : "Not fetched yet. Once it is, an entry that suits one of your topics fills the fifth card whenever your own model's idea does not."}
      </p>
      {state && (
        <p className="mt-1 text-[11px] leading-snug text-ink-muted">
          {state.contains} {state.sends} Each file is checked against the library key this studio ships before
          anything in it is kept.
        </p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void run(fetchLibraryBundle)}
          className="rounded-md border border-edge px-2 py-1 text-[12px] text-ink-secondary hover:text-ink-primary disabled:opacity-60"
        >
          Fetch the Inox library
        </button>
        <label className="rounded-md border border-edge px-2 py-1 text-[12px] text-ink-secondary hover:text-ink-primary">
          Import a library file
          <input
            ref={picker}
            type="file"
            accept=".ilb,text/plain"
            className="sr-only"
            onChange={(event) => void chosen(event.target.files?.[0])}
          />
        </label>
      </div>
      {note && (
        <p role="status" className={note.error ? "mt-1 text-[12px] text-signal-orange-text" : "mt-1 text-[12px] text-ink-muted"}>
          {note.text}
        </p>
      )}
    </section>
  );
}
