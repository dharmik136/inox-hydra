import { useEffect, useState } from "react";
import { CornerDownLeft, Loader2 } from "lucide-react";
import { fetchAiStatus, runAiCommand, type AiStatus } from "@/lib/api";

interface Entry {
  command: string;
  response: string;
  failed: boolean;
  /** Who wrote the response, as the engine reports it. */
  engine: string | null;
}

/**
 * The agent command console (blueprint build order phase 4).
 *
 * The engine banner is not decoration. Whether a command stays on this machine
 * or is sent to a provider depends entirely on whether a key is configured,
 * and the person typing is the one who needs to know which it is before they
 * type anything into it.
 *
 * The Composer draft goes with an instruction only when the box under it is
 * ticked. The placeholder used to offer to work with "your draft" while the
 * draft was never sent, so "summarise my draft" was answered about nothing.
 */
export function CommandSurface({ draft = "" }: { draft?: string }) {
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [command, setCommand] = useState("");
  const [includeDraft, setIncludeDraft] = useState(false);
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<Entry[]>([]);
  const hasDraft = draft.trim().length > 0;

  useEffect(() => {
    let live = true;
    fetchAiStatus()
      .then((result) => live && setStatus(result))
      .catch(() => {
        // The banner is omitted rather than guessing which engine answers.
      });
    return () => {
      live = false;
    };
  }, []);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const text = command.trim();
    if (!text || busy) return;

    setBusy(true);
    try {
      const result = await runAiCommand(text, includeDraft && hasDraft ? draft : undefined);
      // The engine answers in "output". That field was never read, so every
      // answer was printed as the whole JSON payload with its line breaks
      // escaped. The payload is still the last resort, rather than "undefined".
      const readable =
        typeof result.output === "string"
          ? result.output
          : typeof result.message === "string"
            ? result.message
            : JSON.stringify(result, null, 2);
      const engine = typeof result.engine === "string" ? result.engine : null;
      setLog((entries) => [{ command: text, response: readable, failed: false, engine }, ...entries]);
      setCommand("");
    } catch (error) {
      setLog((entries) => [
        {
          command: text,
          response: error instanceof Error ? error.message : "The command was refused.",
          failed: true,
          engine: null,
        },
        ...entries,
      ]);
    } finally {
      setBusy(false);
    }
  }

  const local = status ? !status.has_api_key : null;

  return (
    <div className="mx-auto max-w-[86ch] px-8 py-8">
      <h1 className="studio-title">Command</h1>

      {status && (
        <p className="studio-meta mt-3">
          {status.active_mode.toUpperCase()}
          <span className="mx-2 text-ink-muted">·</span>
          <span className={local ? "text-signal-green-text" : "text-signal-orange-text"}>
            {local ? "STAYS ON THIS MACHINE" : "SENT TO THE PROVIDER"}
          </span>
        </p>
      )}

      <form onSubmit={onSubmit} className="mt-6">
        <label className="studio-label mb-2 block" htmlFor="agent-command">
          Instruction
        </label>
        <div className="flex items-start gap-2">
          <textarea
            id="agent-command"
            value={command}
            onChange={(event) => setCommand(event.target.value)}
            onKeyDown={(event) => {
              // Enter sends; shift and enter makes a new line. A console that
              // needs a mouse to submit is not a console.
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void onSubmit(event as unknown as React.FormEvent);
              }
            }}
            rows={3}
            placeholder="Tell the model what to write. Tick the box below to include your Composer draft."
            className="flex-1 resize-none rounded-md border border-edge bg-ink px-3 py-2 text-[13px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
          />
          <button
            type="submit"
            disabled={busy || !command.trim()}
            aria-label="Run the command"
            className="grid size-9 shrink-0 place-items-center rounded-md bg-signal-orange text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-40"
          >
            {busy ? (
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <CornerDownLeft className="size-4" strokeWidth={1.75} aria-hidden="true" />
            )}
          </button>
        </div>
        <label className="mt-2 flex items-center gap-2 text-[12px] text-ink-secondary">
          <input
            type="checkbox"
            name="include-draft"
            checked={includeDraft && hasDraft}
            disabled={!hasDraft}
            onChange={(event) => setIncludeDraft(event.target.checked)}
            className="size-4 accent-[var(--studio-orange)]"
          />
          Include my Composer draft
          {!hasDraft && <span className="text-ink-muted">(the Composer is empty)</span>}
        </label>
      </form>

      <section className="mt-8">
        {log.length === 0 ? (
          <p className="studio-meta text-ink-muted">NOTHING RUN YET IN THIS SESSION</p>
        ) : (
          <ul className="flex flex-col gap-6">
            {log.map((entry, index) => (
              <li key={`${index}-${entry.command}`} className="border-l border-edge pl-4">
                <p className="studio-meta text-[10px]">
                  {entry.failed ? "REFUSED" : "RAN"}
                  {entry.engine && <span className="text-ink-muted"> · {entry.engine}</span>}
                </p>
                <p className="mt-1 text-[13px] text-ink-primary">{entry.command}</p>
                <pre className="mt-2 font-editorial text-[13px] leading-relaxed whitespace-pre-wrap text-ink-secondary">
                  {entry.response}
                </pre>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
