import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { PanelRightClose } from "lucide-react";
import { FOLD_CHARS } from "./ComposerCanvas";
import { AuditPanel } from "./AuditPanel";
import { cn } from "@/lib/utils";

type InspectorMode = "Preview" | "Audit" | "Media" | "Brand" | "Prompt";

const MODES: InspectorMode[] = ["Preview", "Audit", "Media", "Brand", "Prompt"];

interface InspectorProps {
  open: boolean;
  onClose: () => void;
  draft: string;
}

/**
 * The contextual inspector (blueprint section 10).
 *
 * It slides in from the edge rather than occupying five permanently visible
 * panels. Preview and Audit are implemented. The remaining modes say so plainly
 * instead of rendering a convincing shell over nothing, which is the failure
 * tests/test_no_fabricated_metrics.py exists to prevent elsewhere in this
 * product.
 */
export function Inspector({ open, onClose, draft }: InspectorProps) {
  const [mode, setMode] = useState<InspectorMode>("Preview");

  return (
    <AnimatePresence>
      {open && (
        <motion.aside
          initial={{ width: 0, opacity: 0 }}
          animate={{ width: 380, opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={{ duration: 0.22, ease: [0.32, 0.72, 0.24, 1] }}
          aria-label="Inspector"
          className="shrink-0 overflow-hidden border-l border-edge bg-ink"
        >
          <div className="flex h-full w-[380px] flex-col">
            <div className="flex h-12 shrink-0 items-center gap-1 border-b border-edge px-2">
              {MODES.map((candidate) => (
                <button
                  key={candidate}
                  type="button"
                  onClick={() => setMode(candidate)}
                  aria-pressed={mode === candidate}
                  className={cn(
                    "rounded-md px-2 py-1 text-[11px] font-medium tracking-wide uppercase",
                    "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard)",
                    mode === candidate ? "bg-soft text-ink-primary" : "text-ink-muted hover:text-ink-secondary",
                  )}
                >
                  {candidate}
                </button>
              ))}
              <button
                type="button"
                onClick={onClose}
                aria-label="Close inspector"
                className="ml-auto grid size-7 place-items-center rounded-md text-ink-muted transition-colors hover:bg-soft hover:text-ink-primary"
              >
                <PanelRightClose className="size-4" strokeWidth={1.75} aria-hidden="true" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              {mode === "Preview" && <FeedPreview draft={draft} />}
              {mode === "Audit" && <AuditPanel draft={draft} />}
              {mode !== "Preview" && mode !== "Audit" && (
                <p className="studio-meta pt-8 text-center leading-relaxed text-ink-muted">
                  {mode.toUpperCase()} INSPECTOR
                  <br />
                  NOT BUILT YET
                </p>
              )}
            </div>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

/**
 * The feed preview, rendered from the real draft rather than sample copy.
 * Truncation mirrors what LinkedIn does at the fold, so the "see more" control
 * appears for exactly the posts that will actually collapse.
 */
function FeedPreview({ draft }: { draft: string }) {
  const [expanded, setExpanded] = useState(false);
  const collapses = draft.length > FOLD_CHARS;
  const shown = collapses && !expanded ? draft.slice(0, FOLD_CHARS) : draft;

  return (
    <div className="rounded-lg border border-edge bg-raised p-4">
      <div className="flex items-center gap-2">
        <div className="size-9 rounded-full bg-soft" aria-hidden="true" />
        <div className="min-w-0">
          {/* No name, headline or follower count is invented here. The
              identity fields stay empty until the studio has a real profile
              to read, because a plausible placeholder is indistinguishable
              from real data in a screenshot. */}
          <div className="h-2.5 w-28 rounded-full bg-soft" aria-hidden="true" />
          <div className="mt-1.5 h-2 w-20 rounded-full bg-soft/70" aria-hidden="true" />
        </div>
      </div>

      <p className="mt-3 text-[14px] leading-[1.55] whitespace-pre-wrap text-ink-primary">
        {shown || <span className="text-ink-muted">Nothing written yet.</span>}
        {collapses && !expanded && (
          <>
            <span className="text-ink-muted">... </span>
            <button
              type="button"
              onClick={() => setExpanded(true)}
              className="text-ink-muted underline-offset-2 hover:underline"
            >
              see more
            </button>
          </>
        )}
      </p>

      <p className="studio-meta mt-4 border-t border-edge pt-3">
        {collapses ? `COLLAPSES AT ${FOLD_CHARS} CHARS` : "FITS ABOVE THE FOLD"}
      </p>
    </div>
  );
}
