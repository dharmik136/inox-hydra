import { useEffect, useState } from "react";
import { ExternalLink, Sparkles, TrendingUp, TrendingDown, HelpCircle } from "lucide-react";
import { fetchEvidenceBrief, type RetrievalEvidenceBrief, type EvidenceExemplar } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * CP2 Evidence-Backed Composer Panel.
 *
 * Sourced solely from real settled post contrasts (n >= 8 per arm guard)
 * and historical top/bottom post exemplars. Zero cloud egress.
 */
export function EvidencePanel() {
  const [brief, setBrief] = useState<RetrievalEvidenceBrief | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    fetchEvidenceBrief()
      .then((data) => {
        if (!live) return;
        setBrief(data);
        setFailed(false);
      })
      .catch(() => live && setFailed(true));

    return () => {
      live = false;
    };
  }, []);

  if (failed) {
    return <p className="studio-meta pt-8 text-center text-ink-muted">EVIDENCE UNAVAILABLE</p>;
  }

  if (!brief) {
    return <p className="studio-meta pt-8 text-center text-ink-muted">READING LOCAL POST EVIDENCE</p>;
  }

  if (!brief.has_evidence) {
    return (
      <div className="flex flex-col gap-4">
        <div className="border-b border-edge pb-3">
          <p className="studio-label">Evidence-Backed Engine</p>
          <p className="studio-meta text-ink-muted mt-1">COLD START</p>
        </div>
        <p className="text-[12px] leading-relaxed text-ink-muted">
          Fewer than 3 settled posts found in local database. Ingest your LinkedIn activity
          to unlock contrast findings and grounded exemplars.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Header telemetry */}
      <div className="flex items-baseline justify-between border-b border-edge pb-3">
        <span className="studio-label">Evidence Grounding</span>
        <span className="studio-meta text-signal-green-text">
          {brief.contrast_findings.length} CONCLUSIVE CONTRAST{brief.contrast_findings.length === 1 ? "" : "S"}
        </span>
      </div>

      {/* CP1/CP2 Conclusive Contrast Findings */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <p className="studio-label">Observed Contrast Effects</p>
          <span className="text-[11px] text-ink-muted flex items-center gap-1">
            <HelpCircle className="size-3" aria-hidden="true" />
            n &ge; 8 guard
          </span>
        </div>

        {brief.contrast_findings.length === 0 ? (
          <div className="rounded-md border border-edge bg-soft/40 p-3 text-[12px] text-ink-muted leading-relaxed">
            No format arm has reached n &ge; 8 settled posts with a statistically conclusive gap yet.
            Continuing to publish builds this sample size.
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {brief.contrast_findings.map((c) => {
              const ratio = c.ratio ?? 1.0;
              const isPositive = ratio > 1.0;
              const ratioDisplay = `${ratio.toFixed(2)}x`;
              return (
                <div
                  key={c.key}
                  className="rounded-md border border-edge bg-soft/50 p-3 flex flex-col gap-1.5"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-[12px] font-medium text-ink-primary flex items-center gap-1.5">
                      {isPositive ? (
                        <TrendingUp className="size-3.5 text-signal-green-text shrink-0" aria-hidden="true" />
                      ) : (
                        <TrendingDown className="size-3.5 text-signal-orange-text shrink-0" aria-hidden="true" />
                      )}
                      {c.label}
                    </span>
                    <span
                      className={cn(
                        "studio-meta shrink-0 px-1.5 py-0.5 rounded text-[11px] font-semibold",
                        isPositive ? "bg-signal-green-text/10 text-signal-green-text" : "bg-signal-orange-text/10 text-signal-orange-text"
                      )}
                    >
                      {ratioDisplay}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-ink-muted">
                    <span>
                      {c.median_with} vs {c.median_without} median reactions
                    </span>
                    <span>
                      n = {c.n_with} with / {c.n_without} without
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Top Performing Exemplars */}
      {brief.top_exemplars && brief.top_exemplars.length > 0 && (
        <section>
          <p className="studio-label mb-2">Top Performing Exemplars</p>
          <div className="flex flex-col gap-2.5">
            {brief.top_exemplars.map((post, idx) => (
              <ExemplarCard key={post.activity_urn || idx} post={post} rank={idx + 1} />
            ))}
          </div>
        </section>
      )}

      {/* Grounded Copilot Brief summary */}
      {brief.brief_section && (
        <section className="border-t border-edge pt-4">
          <p className="studio-label mb-2 flex items-center gap-1.5">
            <Sparkles className="size-3.5 text-signal-blue" aria-hidden="true" />
            Active Copilot Grounding
          </p>
          <p className="text-[11px] leading-relaxed text-ink-muted">
            These exact contrast ratios and exemplar posts are injected directly into your BYO-AI
            Copilot prompt context, ensuring recommendations quote real creator history.
          </p>
        </section>
      )}
    </div>
  );
}

function ExemplarCard({ post, rank }: { post: EvidenceExemplar; rank: number }) {
  const urn = post.activity_urn || "";
  const permalink = urn.startsWith("urn:li:activity:")
    ? `https://www.linkedin.com/feed/update/${urn}/`
    : null;

  return (
    <div className="rounded-md border border-edge bg-soft/40 p-2.5 flex flex-col gap-1.5">
      <div className="flex items-center justify-between text-[11px]">
        <span className="font-mono text-ink-muted">#{rank}</span>
        <div className="flex items-center gap-2">
          <span className="text-signal-green-text font-medium">{post.reactions} reactions</span>
          {post.qualified_leads > 0 && (
            <span className="text-signal-blue font-medium">· {post.qualified_leads} leads</span>
          )}
          {permalink && (
            <a
              href={permalink}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="View on LinkedIn"
              className="text-ink-muted hover:text-ink-primary transition-colors"
            >
              <ExternalLink className="size-3" aria-hidden="true" />
            </a>
          )}
        </div>
      </div>
      <p className="text-[12px] leading-snug text-ink-secondary line-clamp-3">
        {post.text}
      </p>
      {urn && (
        <span className="font-mono text-[10px] text-ink-muted truncate">
          {urn}
        </span>
      )}
    </div>
  );
}
