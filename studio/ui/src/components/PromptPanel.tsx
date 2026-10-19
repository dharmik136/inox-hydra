import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { configureAi, fetchAiConfig, fetchAiStatus, type AiStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

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
 * Which engine is answering, and whether anything leaves this machine to do
 * it. That second question is the product's central claim, so it is the line
 * with the colour on it.
 */
export function PromptPanel() {
  const [status, setStatus] = useState<StatusWithFailure | null>(null);
  const [failed, setFailed] = useState(false);

  const [providers, setProviders] = useState<string[]>([]);
  const [provider, setProvider] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [current, config] = await Promise.all([
      fetchAiStatus(),
      fetchAiConfig().catch(() => ({ config: null, providers: [] as string[] })),
    ]);
    setStatus(current);
    setProviders(config.providers);
    setProvider((existing) => existing || config.config?.provider || config.providers[0] || "");
  }, []);

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
      await configureAi(provider, apiKey);
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
          <Row label="Mode" value={status.active_mode} />
          <Row label="Provider" value={status.provider} />
          <Row label="Model" value={status.model} />
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
            onChange={(event) => setProvider(event.target.value)}
            aria-label="Model provider"
            className="rounded-md border border-edge bg-ink px-2 py-1.5 text-[12px] text-ink-primary outline-none focus-visible:border-edge-strong"
          >
            {providers.length === 0 && <option value="">No providers reported</option>}
            {providers.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>

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
    </div>
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
