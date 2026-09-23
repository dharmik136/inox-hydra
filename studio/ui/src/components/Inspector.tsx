import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { PanelRightClose } from "lucide-react";
import { PreviewStage } from "./PreviewStage";
import { AuditPanel } from "./AuditPanel";
import { MediaPanel } from "./MediaPanel";
import { BrandPanel } from "./BrandPanel";
import { PromptPanel } from "./PromptPanel";
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
 * panels. Every mode reads from the studio's own endpoints, and where a thing
 * genuinely does not exist yet, the panel says so rather than rendering a
 * convincing shell over nothing. That is the failure
 * tests/test_no_fabricated_metrics.py exists to prevent elsewhere in this
 * product, and it applies just as much to an interface.
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
              {mode === "Preview" && <PreviewStage draft={draft} />}
              {mode === "Audit" && <AuditPanel draft={draft} />}
              {mode === "Media" && <MediaPanel />}
              {mode === "Brand" && <BrandPanel />}
              {mode === "Prompt" && <PromptPanel />}
            </div>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
