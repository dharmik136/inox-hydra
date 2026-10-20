import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import {
  fetchImageProvider,
  saveImageProvider,
  type ImageProviderOption,
  type ImageProviderState,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/** The groups the choice is offered in, by who makes the image. */
const GROUPS: { kind: ImageProviderOption["kind"]; label: string }[] = [
  { kind: "public", label: "Free, no account" },
  { kind: "cloud", label: "Your own account" },
  { kind: "local", label: "On your own machine" },
  { kind: "off", label: "None" },
];

/** How the current provider came to be the one Generate uses. */
const SOURCE: Record<string, string> = {
  chosen: "Chosen here",
  ai_provider: "Your AI provider's key",
  default: "The default",
};

/** An address on this computer, where a local web UI's prompt stays. */
function onThisComputer(url: string): boolean {
  return /^https?:\/\/(127\.|localhost(:|\/|$)|\[::1\])/i.test(url.trim());
}

/**
 * The image provider, beside the AI provider in the Prompt tab (R7).
 *
 * Who makes the image when Generate is pressed: the free public generator,
 * a cloud account of the creator's own, a web UI on their own machine, or
 * nobody. What leaves this machine is shown for the option being looked at,
 * before it is saved, because that is when it can still change the choice.
 */
export function ImageProviderSettings() {
  const [state, setState] = useState<ImageProviderState | null>(null);
  const [failed, setFailed] = useState(false);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ text: string; ok: boolean } | null>(null);

  const load = useCallback(async () => {
    const next = await fetchImageProvider();
    setState(next);
    return next;
  }, []);

  useEffect(() => {
    load()
      .then((next) => {
        const current = next.providers.find((option) => option.id === next.config.provider);
        setProvider(next.config.provider);
        setModel(next.config.model);
        setBaseUrl(next.config.base_url || current?.default_url || "");
        setModels(current?.models ?? []);
      })
      .catch(() => setFailed(true));
  }, [load]);

  if (failed) return <p className="studio-meta border-t border-edge pt-4 text-ink-muted">IMAGE PROVIDER UNAVAILABLE</p>;
  if (!state) return <p className="studio-meta border-t border-edge pt-4 text-ink-muted">READING IMAGE PROVIDER</p>;

  const { config, providers } = state;
  const option = providers.find((candidate) => candidate.id === provider) ?? providers[0];
  const savedHere = config.provider === provider && config.source === "chosen";

  function onChoose(id: string) {
    const next = providers.find((candidate) => candidate.id === id);
    setProvider(id);
    setNote(null);
    setApiKey("");
    setModel(id === config.provider ? config.model : next?.default_model ?? "");
    setBaseUrl(id === config.provider && config.base_url ? config.base_url : next?.default_url ?? "");
    setModels(next?.models ?? []);
  }

  async function onSave() {
    if (!option) return;
    setBusy(true);
    setNote(null);
    try {
      const result = await saveImageProvider({
        provider: option.id,
        api_key: apiKey,
        model: model.trim(),
        base_url: option.needs_url ? baseUrl.trim() : "",
      });
      setApiKey("");
      setNote({ text: result.message, ok: true });
      if (result.models.length) setModels(result.models);
      setModel(result.config.model);
      await load();
    } catch (caught) {
      setNote({ text: caught instanceof Error ? caught.message : "The provider could not be checked.", ok: false });
    } finally {
      setBusy(false);
    }
  }

  let keyPlaceholder = "API key";
  if (savedHere && config.has_key && config.key_from === "own") {
    keyPlaceholder = `Leave blank to keep the saved key (${config.api_key_masked})`;
  } else if (option?.shares_ai_key && state.ai_provider === option.id) {
    keyPlaceholder = "Leave blank to use your AI provider's key";
  }

  const leavesForTypedUrl = option?.needs_url && baseUrl.trim() !== "" && !onThisComputer(baseUrl);
  const refusedHere = !state.image_egress_allowed && config.disclosure.leaves;

  return (
    <section aria-label="Image provider settings" className="border-t border-edge pt-4">
      <p className="studio-label mb-2">Images</p>
      <dl className="flex flex-col gap-1.5">
        <Row label="Generate" value={config.name} />
        <Row label="Model" value={config.model || (config.kind === "local" ? "The one loaded in the web UI" : "None")} />
        <Row label="Set by" value={SOURCE[config.source] ?? config.source} />
        {config.kind === "cloud" && <Row label="Key" value={config.has_key ? config.api_key_masked : "None"} />}
        {(config.kind === "cloud" || config.kind === "local") && (
          <Row label="Checked" value={config.verified_at ? config.verified_at.replace("T", " ") : "Not checked"} />
        )}
        <Row
          label="Egress"
          value={config.kind === "off" ? "NONE, GENERATE IS OFF" : config.disclosure.leaves ? "SENDS THE PROMPT OUT" : "NONE, STAYS ON THIS COMPUTER"}
          tone={config.disclosure.leaves ? "text-signal-orange-text" : "text-signal-green-text"}
        />
      </dl>
      {config.not_ready && (
        <p role="status" className="mt-2 text-[12px] leading-snug text-signal-orange-text">
          {config.not_ready}
        </p>
      )}
      {refusedHere && (
        <p role="status" className="mt-2 text-[12px] leading-snug text-signal-orange-text">
          Outbound image requests are switched off on this computer, so Generate will be refused until you choose a web UI
          on this computer or turn them back on.
        </p>
      )}

      <p className="studio-label mb-2 mt-4">Change image provider</p>
      <div className="flex flex-col gap-2">
        <select
          value={provider}
          onChange={(event) => onChoose(event.target.value)}
          aria-label="Image provider"
          className="rounded-md border border-edge bg-ink px-2 py-1.5 text-[12px] text-ink-primary outline-none focus-visible:border-edge-strong"
        >
          {GROUPS.map((group) => (
            <optgroup key={group.kind} label={group.label}>
              {providers
                .filter((candidate) => candidate.kind === group.kind)
                .map((candidate) => (
                  <option key={candidate.id} value={candidate.id}>
                    {candidate.name}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>

        {option && (
          <div className="flex flex-col gap-1 rounded-md border border-edge p-2">
            <p className="studio-meta text-[10px] text-ink-muted">WHAT LEAVES THIS MACHINE WITH THIS CHOICE</p>
            <dl className="flex flex-col gap-1">
              <Said label="Sends" text={option.disclosure.sends} />
              {/* A web UI's destination is the address being typed, not the
                  default the catalogue was described with. */}
              <Said
                label="To"
                text={
                  option.needs_url
                    ? `${option.name} at ${baseUrl.trim() || option.default_url}${leavesForTypedUrl ? "." : ", on this computer."}`
                    : option.disclosure.to
                }
              />
              <Said label="Account" text={option.disclosure.account} />
            </dl>
            {leavesForTypedUrl && (
              <p className="text-[12px] leading-snug text-signal-orange-text">
                That address is not this computer, so the prompt leaves it for that machine.
              </p>
            )}
          </div>
        )}

        {option?.needs_url && (
          <input
            type="url"
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.target.value)}
            placeholder={option.default_url}
            aria-label="Web UI address"
            spellCheck={false}
            className="rounded-md border border-edge bg-ink px-2 py-1.5 text-[12px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
          />
        )}

        {option && option.kind !== "off" && (
          <>
            <input
              type="text"
              value={model}
              onChange={(event) => setModel(event.target.value)}
              list="image-model-options"
              placeholder={option.kind === "local" ? "Model (blank: the one loaded)" : "Model"}
              aria-label="Image model"
              spellCheck={false}
              className="rounded-md border border-edge bg-ink px-2 py-1.5 text-[12px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
            />
            <datalist id="image-model-options">
              {models.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
            {/* Beside the field, so a requirement or a price change is read
                before the model is saved (gpt-image-1 needs organisation
                verification). */}
            {option.model_notes?.[model.trim()] && (
              <p className="text-[11px] leading-snug text-ink-muted">{option.model_notes[model.trim()]}</p>
            )}
          </>
        )}

        {option?.needs_key && (
          <>
            <input
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder={keyPlaceholder}
              aria-label="Image provider API key"
              autoComplete="off"
              className="rounded-md border border-edge bg-ink px-2 py-1.5 text-[12px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
            />
            {option.key_hint && <p className="text-[11px] leading-snug text-ink-muted">{option.key_hint}</p>}
          </>
        )}

        <button
          type="button"
          onClick={onSave}
          disabled={busy || !option}
          className="flex items-center justify-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
        >
          {busy && <Loader2 className="size-3 animate-spin" aria-hidden="true" />}
          {option?.checks ? "Verify and save" : "Save"}
        </button>

        {note && (
          <p
            role="status"
            className={cn("text-[12px] leading-snug", note.ok ? "text-ink-secondary" : "text-signal-orange-text")}
          >
            {note.text}
          </p>
        )}

        <p className="studio-meta leading-relaxed text-ink-muted">
          A KEY IS STORED IN THIS MACHINE&apos;S ENCRYPTED VAULT AND SHOWN ONLY AS ITS LAST FOUR CHARACTERS. WITH AN AI
          PROVIDER SET UP ABOVE, YOUR DESCRIPTION ALSO GOES TO IT FIRST, TO WRITE THE SCENE.
        </p>
      </div>
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

function Said({ label, text }: { label: string; text: string }) {
  return (
    <div className="flex gap-3">
      <dt className="w-14 shrink-0 text-[11px] text-ink-muted">{label}</dt>
      <dd className="text-[12px] leading-snug text-ink-secondary">{text}</dd>
    </div>
  );
}
