import { useCallback, useEffect, useState } from "react";
import { Copy, CornerDownLeft, Loader2 } from "lucide-react";
import {
  configureAi,
  fetchAiProviders,
  fetchAiStatus,
  runAiCommand,
  type AiProviderOption,
  type AiStatus,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { ImageProviderSettings } from "./ImageProviderSettings";

/** The capability keys the backend returns, in words rather than identifiers. */
const CAPABILITY_LABELS: Record<string, string> = {
  "10x_viral_hooks": "Hook generation",
  smart_repurpose: "Repurposing",
  algorithmic_audit: "Reach audit",
  antigravity_agent_command: "Agent command",
  personalized_crm_dm: "Tailored DMs",
};

/**
 * What /api/ai/status adds to AiStatus: the last request that failed, until
 * one succeeds, and what from the creator's own profile and posts goes with
 * every Re-Hook and Command request.
 */
type StatusWithFailure = AiStatus & {
  last_error?: string | null;
  last_error_at?: string | null;
  voice_pack_sent?: string[];
};

/**
 * What each feature sends, in the order the creator meets them. The voice
 * pack goes with the first two and is listed under them from the server,
 * because it depends on what the studio knows about this creator.
 */
const SENT_BY_FEATURE: { feature: string; what: string }[] = [
  { feature: "Re-Hook", what: "the first line of your selection" },
  { feature: "Command", what: "your instruction, and your Composer draft when you tick the box to include it" },
  { feature: "Media", what: "your image description" },
];

/**
 * The prompt inspector (blueprint section 10).
 *
 * Which engine is answering, whether anything leaves this machine to do it,
 * and the instruction box that used to be a rail section of its own. That
 * second question is the product's central claim, so it is the line with the
 * colour on it.
 *
 * Command came here because the only thing it can act on is the draft, and as
 * a section it was 147 characters, three controls and an answer the creator
 * had to select with the mouse to use. Beside the draft, under the disclosure
 * that says what goes with it, it is the same engine answering about the text
 * on screen.
 */
export function PromptPanel({ draft = "" }: { draft?: string } = {}) {
  const [status, setStatus] = useState<StatusWithFailure | null>(null);
  const [failed, setFailed] = useState(false);

  const [providers, setProviders] = useState<AiProviderOption[]>([]);
  const [provider, setProvider] = useState("");
  // The model is chosen here. There was no field, so the ping always named the
  // provider's default, and when Anthropic retired that one no Claude key
  // could be connected from the interface.
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [current, setup] = await Promise.all([
      fetchAiStatus(),
      fetchAiProviders().catch(() => ({ config: null, providers: [] as AiProviderOption[] })),
    ]);
    setStatus(current);
    setProviders(setup.providers);
    setProvider((existing) => existing || setup.config?.provider || setup.providers[0]?.id || "");
    setModel((typed) => typed || setup.config?.model || "");
  }, []);

  function onChooseProvider(id: string) {
    setProvider(id);
    setModel(providers.find((option) => option.id === id)?.defaultModel ?? "");
  }

  const suggestions = providers.find((option) => option.id === provider)?.models ?? [];

  useEffect(() => {
    load().catch(() => setFailed(true));
  }, [load]);

  async function onConnect() {
    if (!provider) return;
    setBusy(true);
    setNote(null);
    try {
      // The endpoint pings the provider before saving, and answers 400 without
      // writing anything when it cannot reach it, so a failure here leaves the
      // previous configuration intact.
      await configureAi(provider, apiKey, model.trim());
      setApiKey("");
      setNote("Connected.");
      await load();
    } catch (caught) {
      setNote(caught instanceof Error ? caught.message : "The provider refused the connection.");
    } finally {
      setBusy(false);
    }
  }

  if (failed) return <p className="studio-meta pt-8 text-center text-ink-muted">ENGINE STATUS UNAVAILABLE</p>;
  if (!status) return <p className="studio-meta pt-8 text-center text-ink-muted">READING ENGINE STATUS</p>;

  // has_api_key is the difference between a local deterministic engine and a
  // configured cloud provider, which is the difference between a request that
  // stays on this machine and one that does not.
  const local = !status.has_api_key;

  return (
    <div className="flex flex-col gap-5">
      <section>
        <p className="studio-label mb-2">Engine</p>
        <dl className="flex flex-col gap-1.5">
          {/* Said in plain words. active_mode carries an internal engine
              codename for the no-model case, which meant nothing to a
              creator; the provider and model they configured do. */}
          <Row label="Mode" value={local ? "Built-in templates, no model" : "Your provider"} />
          <Row label="Provider" value={local ? "None set up" : status.provider} />
          <Row label="Model" value={local ? "None" : status.model} />
          <Row
            label="Egress"
            value={local ? "NONE, RUNS LOCALLY" : "SENDS TO PROVIDER"}
            tone={local ? "text-signal-green-text" : "text-signal-orange-text"}
          />
        </dl>
        {/* A key that stopped working used to be invisible: every feature
            kept answering from templates. */}
        {!local && status.last_error && (
          <p role="status" className="mt-2 text-[12px] leading-snug text-signal-orange-text">
            The last request failed{status.last_error_at ? ` at ${status.last_error_at.replace("T", " ")}` : ""}:{" "}
            {status.last_error}
          </p>
        )}
      </section>

      {/* Said where the choice is made. The pack went with every request
          while this tab said only that "prompt text" leaves. */}
      <section>
        <p className="studio-label mb-2">{local ? "What a provider would receive" : "What the provider receives"}</p>
        <dl className="flex flex-col gap-1.5">
          {SENT_BY_FEATURE.map(({ feature, what }) => (
            <div key={feature} className="flex gap-3">
              <dt className="w-16 shrink-0 text-[11px] text-ink-muted">{feature}</dt>
              <dd className="text-[12px] leading-snug text-ink-secondary">{what}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-2 text-[12px] leading-snug text-ink-secondary">
          {status.voice_pack_sent?.length
            ? `With every Re-Hook and Command request, from your own profile and posts: ${status.voice_pack_sent.join("; ")}.`
            : "Nothing from your profile or posts goes with them yet."}
        </p>
      </section>

      <section>
        <p className="studio-label mb-2">Available here</p>
        <ul className="flex flex-wrap gap-1">
          {status.capabilities.map((capability) => (
            <li
              key={capability}
              className="rounded border border-edge px-1.5 py-0.5 text-[10px] text-ink-secondary"
            >
              {CAPABILITY_LABELS[capability] ?? capability.replace(/_/g, " ")}
            </li>
          ))}
        </ul>
      </section>

      <CommandBlock draft={draft} />

      <section className="border-t border-edge pt-4">
        <p className="studio-label mb-2">{local ? "Connect a provider" : "Change provider"}</p>
        {local && (
          <p className="studio-meta mb-3 leading-relaxed text-ink-muted">
            NO KEY IS CONFIGURED. RE-HOOK OFFERS FILL-IN TEMPLATES AND THE AUDIT RUNS HERE. COMMAND NEEDS A
            MODEL.
          </p>
        )}

        <div className="flex flex-col gap-2">
          <select
            value={provider}
            onChange={(event) => onChooseProvider(event.target.value)}
            aria-label="Model provider"
            className="rounded-md border border-edge bg-ink px-2 py-1.5 text-[12px] text-ink-primary outline-none focus-visible:border-edge-strong"
          >
            {providers.length === 0 && <option value="">No providers reported</option>}
            {providers.map((option) => (
              <option key={option.id} value={option.id}>
                {option.id}
              </option>
            ))}
          </select>

          {/* Free text with suggestions, because an endpoint of your own takes
              whatever model names it serves. */}
          <input
            type="text"
            value={model}
            onChange={(event) => setModel(event.target.value)}
            list="prompt-model-options"
            placeholder="Model"
            aria-label="Model"
            spellCheck={false}
            className="rounded-md border border-edge bg-ink px-2 py-1.5 text-[12px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
          />
          <datalist id="prompt-model-options">
            {suggestions.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>

          <input
            type="password"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder="API key"
            aria-label="Provider API key"
            className="rounded-md border border-edge bg-ink px-2 py-1.5 text-[12px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
          />

          <button
            type="button"
            onClick={onConnect}
            disabled={busy || !provider}
            className="flex items-center justify-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
          >
            {busy && <Loader2 className="size-3 animate-spin" aria-hidden="true" />}
            Verify and save
          </button>

          {note && (
            <p role="status" className="studio-meta leading-snug text-ink-secondary">
              {note}
            </p>
          )}

          <p className="studio-meta leading-relaxed text-ink-muted">
            THE KEY IS STORED IN THIS MACHINE&apos;S ENCRYPTED VAULT. CONFIGURING ONE MEANS WHAT IS
            LISTED ABOVE LEAVES THIS MACHINE FOR THAT PROVIDER.
          </p>
        </div>
      </section>

      <ImageProviderSettings />
    </div>
  );
}

/** One instruction, and what the engine answered, for this session. */
interface Ran {
  command: string;
  response: string;
  failed: boolean;
  /** Who wrote the response, as the engine reports it. */
  engine: string | null;
  /** What went to the provider with the instruction, when one was used. */
  sent: string[];
}

/**
 * The instruction box, moved here from the Command section.
 *
 * The draft goes with an instruction only when the box under it is ticked.
 * The placeholder used to offer to work with "your draft" while the draft was
 * never sent, so "summarise my draft" was answered about nothing. An answer
 * can be copied, which it could not be on the section: the only way to use
 * one there was to select it with the mouse.
 */
function CommandBlock({ draft }: { draft: string }) {
  const [command, setCommand] = useState("");
  const [includeDraft, setIncludeDraft] = useState(false);
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<Ran[]>([]);
  const [copied, setCopied] = useState<number | null>(null);
  const hasDraft = draft.trim().length > 0;

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
      const sent = Array.isArray(result.sent) ? result.sent.map(String) : [];
      setLog((entries) => [{ command: text, response: readable, failed: false, engine, sent }, ...entries]);
      setCommand("");
    } catch (error) {
      setLog((entries) => [
        {
          command: text,
          response: error instanceof Error ? error.message : "The command was refused.",
          failed: true,
          engine: null,
          sent: [],
        },
        ...entries,
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="border-t border-edge pt-4">
      <p className="studio-label mb-2">Instruction</p>
      <form onSubmit={onSubmit}>
        <div className="flex items-start gap-2">
          <textarea
            id="agent-command"
            aria-label="Instruction"
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
            placeholder="Tell the model what to write. Tick the box below to include your draft."
            className="flex-1 resize-none rounded-md border border-edge bg-ink px-2 py-1.5 text-[12px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
          />
          <button
            type="submit"
            disabled={busy || !command.trim()}
            aria-label="Run the command"
            className="grid size-8 shrink-0 place-items-center rounded-md bg-signal-orange text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-40"
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
          Include my draft
          {!hasDraft && <span className="text-ink-muted">(the editor is empty)</span>}
        </label>
      </form>

      {log.length === 0 ? (
        <p className="studio-meta mt-3 text-ink-muted">NOTHING RUN YET IN THIS SESSION</p>
      ) : (
        <ul className="mt-3 flex flex-col gap-4">
          {log.map((entry, index) => (
            <li key={`${index}-${entry.command}`} className="border-l border-edge pl-3">
              <div className="flex items-baseline justify-between gap-2">
                <p className="studio-meta text-[10px]">
                  {entry.failed ? "REFUSED" : "RAN"}
                  {entry.engine && <span className="text-ink-muted"> · {entry.engine}</span>}
                </p>
                {!entry.failed && (
                  <button
                    type="button"
                    onClick={() => {
                      // COPIED once the browser has taken the text, and not
                      // before. An answer that cannot be copied has to be
                      // selected with the mouse, which is what the section it
                      // came from was criticised for.
                      if (!navigator.clipboard?.writeText) return;
                      navigator.clipboard
                        .writeText(entry.response)
                        .then(() => {
                          setCopied(index);
                          window.setTimeout(() => setCopied(null), 1600);
                        })
                        .catch(() => setCopied(null));
                    }}
                    className="studio-meta flex items-center gap-1 text-[10px] text-ink-muted transition-colors hover:text-ink-primary"
                  >
                    <Copy className="size-3" strokeWidth={2} aria-hidden="true" />
                    {copied === index ? "COPIED" : "COPY"}
                  </button>
                )}
              </div>
              <p className="mt-1 text-[12px] text-ink-primary">{entry.command}</p>
              <pre className="mt-1.5 font-editorial text-[12px] leading-relaxed whitespace-pre-wrap text-ink-secondary">
                {entry.response}
              </pre>
              {entry.sent.length > 0 && (
                <p className="mt-1.5 text-[11px] leading-snug text-ink-muted">Sent with it: {entry.sent.join("; ")}.</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Row({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="shrink-0 text-[11px] text-ink-muted">{label}</dt>
      <dd className={cn("studio-meta truncate text-right uppercase", tone ?? "text-ink-secondary")}>{value}</dd>
    </div>
  );
}
