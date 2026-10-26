import { useState } from "react";
import {
  fetchRecordModelPreview,
  setRecordSettings,
  type RecordModelPreview,
  type RecordModelState,
  type RecordSettings,
} from "@/lib/api";

/**
 * The model stage, on What the studio knows: whether your own AI provider is
 * asked for one idea a day when you open the section, what it costs at most,
 * what the provider says it does with what it is sent, and the exact text
 * the next call would send. Off, or with no key, nothing is sent.
 */
export function RecordModelSettings({
  state,
  settings,
  onChanged,
}: {
  state?: RecordModelState;
  settings: RecordSettings;
  onChanged: () => void;
}) {
  const [ceiling, setCeiling] = useState(settings.cost_ceiling_usd.toFixed(2));
  const [preview, setPreview] = useState<RecordModelPreview | null>(null);
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);

  async function run(work: () => Promise<unknown>, said: string) {
    try {
      await work();
      setNote({ text: said, error: false });
      onChanged();
    } catch (error) {
      setNote({ text: error instanceof Error ? error.message : "That did not work.", error: true });
    }
  }

  return (
    <section aria-labelledby="record-model-title">
      <p id="record-model-title" className="studio-label mb-2">
        Your own model
      </p>
      {!state?.configured ? (
        <p className="text-[12px] leading-snug text-ink-secondary">
          No AI provider is connected, so nothing is sent and the fifth card waits for the Inox library. Connect your
          own in the Composer&rsquo;s Prompt tab to add one idea a day, written from your own posts and asks.
        </p>
      ) : (
        <>
          <label className="flex items-center gap-2 text-[12px] text-ink-secondary">
            <input
              type="checkbox"
              checked={settings.model_stage === "on"}
              onChange={(event) =>
                void run(
                  () => setRecordSettings({ model_stage: event.target.checked ? "on" : "off" }),
                  event.target.checked ? "On from your next first open of the day." : "Off. Nothing is sent.",
                )
              }
              className="size-4 accent-[var(--studio-orange)]"
            />
            Ask {state.provider_label} ({state.model}) for one idea a day, the first time I open this section
          </label>
          <p className="mt-1 text-[11px] leading-snug text-ink-muted">
            It is sent the first 300 characters of up to ten of your posts, the studio&rsquo;s word for how each did
            (never a figure), your asks, and your habits in words. Never another person&rsquo;s name or words, your
            connections or a score. {state.statement}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[12px] text-ink-secondary">
            <label htmlFor="record-ceiling">Daily ceiling, US dollars</label>
            <input
              id="record-ceiling"
              inputMode="decimal"
              value={ceiling}
              onChange={(event) => setCeiling(event.target.value)}
              className="w-20 rounded-md border border-edge bg-ink px-2 py-1 text-[12px] text-ink-primary"
            />
            <button
              type="button"
              onClick={() => void run(() => setRecordSettings({ cost_ceiling_usd: Number(ceiling) }), "Saved.")}
              className="rounded-md border border-edge px-2 py-1 text-[12px] hover:text-ink-primary"
            >
              Save
            </button>
          </div>
          <p className="mt-1 text-[11px] leading-snug text-ink-muted">
            {state.priced
              ? `Each call is held under this before it is made, ${state.price_basis}. Spent today: ${
                  state.spent_today_usd === null ? "nothing" : `$${state.spent_today_usd.toFixed(4)}`
                }.`
              : `Not sent while ${state.price_basis}.`}
          </p>
          <button
            type="button"
            onClick={() =>
              void fetchRecordModelPreview()
                .then(setPreview)
                .catch((error) => setNote({ text: error instanceof Error ? error.message : "Not read.", error: true }))
            }
            className="mt-2 rounded-md border border-edge px-2 py-1 text-[12px] text-ink-secondary hover:text-ink-primary"
          >
            See what would be sent
          </button>
          {preview && (
            <pre className="mt-2 max-h-64 overflow-auto rounded-md border border-edge bg-ink p-2 text-[11px] leading-snug whitespace-pre-wrap text-ink-secondary" tabIndex={0}>
              {preview.system}
              {"\n\n"}
              {preview.prompt}
            </pre>
          )}
        </>
      )}
      {note && (
        <p role="status" className={note.error ? "mt-1 text-[12px] text-signal-orange-text" : "mt-1 text-[12px] text-ink-muted"}>
          {note.text}
        </p>
      )}
    </section>
  );
}
