import { useEffect, useState } from "react";
import { fetchAiStatus, type AiStatus } from "@/lib/api";
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
 * The prompt inspector (blueprint section 10).
 *
 * Which engine is answering, and whether anything leaves this machine to do
 * it. That second question is the product's central claim, so it is the line
 * with the colour on it.
 */
export function PromptPanel() {
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    fetchAiStatus()
      .then((result) => live && setStatus(result))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, []);

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
            tone={local ? "text-signal-green" : "text-signal-orange-text"}
          />
        </dl>
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

      {local && (
        <p className="studio-meta border-t border-edge pt-3 leading-relaxed text-ink-muted">
          NO PROVIDER KEY IS CONFIGURED
          <br />
          <span className="text-ink-muted">EVERY FEATURE ABOVE STILL ANSWERS, DETERMINISTICALLY</span>
        </p>
      )}
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
