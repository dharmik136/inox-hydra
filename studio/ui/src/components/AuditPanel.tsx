import { useEffect, useState } from "react";
import { AlertTriangle, Lightbulb } from "lucide-react";
import { auditDraft, auditGovernance, type AlgorithmAudit, type GStackAudit } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * How long the draft has to stop changing before it is audited.
 *
 * The audit is a round trip per call, and a keystroke is not a meaningful unit
 * of change for a reach verdict.
 */
const SETTLE_MS = 700;

/**
 * A violation without the team role it is filed under.
 *
 * The server prefixes each one with its gate and a role, "Gate 2 (Eng
 * Manager): ...", which told a creator nothing they could act on.
 */
function plainly(violation: string): string {
  return violation.replace(/^Gate \d+ \([^)]*\):\s*/, "");
}

/**
 * The audit inspector (blueprint section 10).
 *
 * The score is a secondary summary at the top rather than the visual centre.
 * What the author acts on is the list of findings underneath it.
 */
export function AuditPanel({ draft }: { draft: string }) {
  const [audit, setAudit] = useState<AlgorithmAudit | null>(null);
  const [gates, setGates] = useState<GStackAudit | null>(null);
  const [failed, setFailed] = useState(false);

  const empty = !draft.trim();

  useEffect(() => {
    // Nothing to audit, so nothing is asked. The server scored an empty draft
    // 100, which read as a perfect post.
    if (!draft.trim()) return;
    let live = true;
    const timer = window.setTimeout(() => {
      auditDraft(draft)
        .then((result) => {
          if (!live) return;
          setAudit(result);
          setFailed(false);
        })
        .catch(() => live && setFailed(true));

      // The governance gates are a separate check with its own six rules, so
      // a failure in one must not blank the other.
      auditGovernance(draft)
        .then((result) => live && setGates(result))
        .catch(() => live && setGates(null));
    }, SETTLE_MS);

    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [draft]);

  if (empty) {
    return (
      <p className="studio-meta pt-8 text-center text-ink-muted">
        NOTHING TO AUDIT YET. WRITE IN THE COMPOSER AND THE CHECKS RUN AS YOU GO.
      </p>
    );
  }
  if (failed) return <p className="studio-meta pt-8 text-center text-ink-muted">AUDIT UNAVAILABLE</p>;
  if (!audit) return <p className="studio-meta pt-8 text-center text-ink-muted">AUDITING</p>;

  // The backend's own thresholds, so the colour and the label never disagree.
  const tone =
    audit.safety_score >= 85
      ? "text-signal-green-text"
      : audit.safety_score >= 60
        ? "text-signal-blue"
        : "text-signal-orange-text";

  return (
    <div className="flex flex-col gap-5">
      {/* Secondary summary. Small, at the top, not a gauge. */}
      <div className="flex items-baseline justify-between border-b border-edge pb-3">
        <span className="studio-label">Distribution</span>
        <span className="studio-meta">
          <span className={cn("text-[13px] font-medium", tone)}>{audit.safety_score}</span>
          <span className="mx-1.5 text-ink-muted">·</span>
          {audit.status_label.toUpperCase()}
        </span>
      </div>

      {/* Measured state, one row per thing the rules actually count. Each of
          these is a field the audit returns, not a derivation of it. */}
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
        <Measure label="Outbound links" value={audit.has_outbound_links ? "PRESENT" : "NONE"} bad={audit.has_outbound_links} />
        <Measure label="Hashtags" value={String(audit.hashtag_count)} bad={audit.hashtag_count > 5} />
        <Measure label="Mentions" value={String(audit.mention_count)} bad={audit.mention_count > 3} />
        <Measure label="Words" value={String(audit.word_count)} bad={false} />
        <Measure label="Est. dwell" value={`${audit.estimated_dwell_seconds}s`} bad={false} />
      </dl>

      {audit.penalties.length > 0 && (
        <Findings
          icon={AlertTriangle}
          title="Penalties"
          tone="text-signal-orange-text"
          items={audit.penalties}
        />
      )}

      {audit.recommendations.length > 0 && (
        /* Deliberately a separate list rather than a remedy attached to each
           penalty above. The backend appends recommendations that have no
           corresponding penalty, including one that is praise for landing in
           the optimal dwell window, so pairing them by position would put the
           wrong advice against the wrong finding. */
        <Findings
          icon={Lightbulb}
          title="Suggestions"
          tone="text-ink-muted"
          items={audit.recommendations}
        />
      )}

      {audit.penalties.length === 0 && (
        <p className="studio-meta text-signal-green-text">NO DISTRIBUTION PENALTIES DETECTED</p>
      )}

      {/* Advice, and said as advice. BLOCKED read as a stop, though nothing
          is ever blocked by these checks, and the score out of 100 was a count
          of six restated as a percentage. */}
      {gates && (
        <section className="border-t border-edge pt-4">
          <div className="mb-2 flex items-baseline justify-between">
            <p className="studio-label">Checks</p>
            <span className="studio-meta">
              <span
                className={cn(
                  "text-[13px] font-medium",
                  gates.passed ? "text-signal-green-text" : "text-signal-orange-text",
                )}
              >
                {passing(gates)} OF {Object.keys(gates.gates).length} PASS
              </span>
              <span className="mx-1.5 text-ink-muted">·</span>
              {gates.passed ? "ALL CLEAR" : "WORTH A LOOK"}
            </span>
          </div>
          {gates.violations.length === 0 ? (
            <p className="studio-meta text-ink-muted">ALL SIX CHECKS PASS</p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {gates.violations.map((violation) => (
                <li key={violation} className="text-[12px] leading-snug text-ink-secondary">
                  {plainly(violation)}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}

/** How many of the checks passed, counted from the server's own per-check verdicts. */
function passing(audit: GStackAudit): number {
  return Object.values(audit.gates).filter((gate) => (gate as { passed?: unknown })?.passed === true).length;
}

function Measure({ label, value, bad }: { label: string; value: string; bad: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <dt className="text-[11px] text-ink-muted">{label}</dt>
      <dd className={cn("studio-meta", bad ? "text-signal-orange-text" : "text-ink-secondary")}>{value}</dd>
    </div>
  );
}

function Findings({
  icon: Icon,
  title,
  tone,
  items,
}: {
  icon: typeof AlertTriangle;
  title: string;
  tone: string;
  items: string[];
}) {
  return (
    <section>
      <p className="studio-label mb-2">{title}</p>
      <ul className="flex flex-col gap-2">
        {items.map((item) => (
          <li key={item} className="flex gap-2">
            <Icon className={cn("mt-0.5 size-3.5 shrink-0", tone)} strokeWidth={1.75} aria-hidden="true" />
            <span className="text-[12px] leading-snug text-ink-secondary">{item}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
