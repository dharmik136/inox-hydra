import { useEffect, useState } from "react";
import { AlertTriangle, Lightbulb } from "lucide-react";
import { auditDraft, type AlgorithmAudit } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * How long the draft has to stop changing before it is audited.
 *
 * The audit is a round trip per call, and a keystroke is not a meaningful unit
 * of change for a reach verdict.
 */
const SETTLE_MS = 700;

/**
 * The audit inspector (blueprint section 10).
 *
 * The score is a secondary summary at the top rather than the visual centre.
 * What the author acts on is the list of findings underneath it.
 */
export function AuditPanel({ draft }: { draft: string }) {
  const [audit, setAudit] = useState<AlgorithmAudit | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    const timer = window.setTimeout(() => {
      auditDraft(draft)
        .then((result) => {
          if (!live) return;
          setAudit(result);
          setFailed(false);
        })
        .catch(() => live && setFailed(true));
    }, SETTLE_MS);

    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [draft]);

  if (failed) return <p className="studio-meta pt-8 text-center text-ink-muted">AUDIT UNAVAILABLE</p>;
  if (!audit) return <p className="studio-meta pt-8 text-center text-ink-muted">AUDITING</p>;

  // The backend's own thresholds, so the colour and the label never disagree.
  const tone =
    audit.safety_score >= 85
      ? "text-signal-green"
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
        <p className="studio-meta text-signal-green">NO DISTRIBUTION PENALTIES DETECTED</p>
      )}
    </div>
  );
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
