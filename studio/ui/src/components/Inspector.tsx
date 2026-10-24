import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { PanelRightClose } from "lucide-react";
import { PreviewStage } from "./PreviewStage";
import { AuditPanel } from "./AuditPanel";
import { EvidencePanel } from "./EvidencePanel";
import { MediaPanel } from "./MediaPanel";
import { BrandPanel } from "./BrandPanel";
import { PromptPanel } from "./PromptPanel";
import { cn } from "@/lib/utils";
import { useMediaQuery } from "@/lib/viewport";

type InspectorMode = "Preview" | "Audit" | "Evidence" | "Media" | "Brand" | "Prompt";

const MODES: InspectorMode[] = ["Preview", "Audit", "Evidence", "Media", "Brand", "Prompt"];

interface InspectorProps {
  open: boolean;
  onClose: () => void;
  draft: string;
  /**
   * Drawn over the editor instead of beside it, for windows too narrow to
   * give up the width. It then behaves as an overlay: a scrim, Escape to
   * close, and focus handed back to whatever opened it.
   */
  overlay?: boolean;
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
export function Inspector({ open, onClose, draft, overlay = false }: InspectorProps) {
  const [mode, setMode] = useState<InspectorMode>("Preview");
  // Six mode labels need about 420 pixels. Where the window can spare that,
  // the panel takes it; below, the label strip scrolls rather than clipping.
  const wide = useMediaQuery("(min-width: 1280px)");
  const width = wide ? 420 : 380;

  const panelRef = useRef<HTMLElement>(null);
  const restoreFocusTo = useRef<Element | null>(null);

  useEffect(() => {
    if (!overlay) return;
    if (open) {
      restoreFocusTo.current = document.activeElement;
      panelRef.current?.focus();
      return;
    }
    if (restoreFocusTo.current instanceof HTMLElement) {
      restoreFocusTo.current.focus();
      restoreFocusTo.current = null;
    }
  }, [open, overlay]);

  useEffect(() => {
    if (!open || !overlay) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, overlay, onClose]);

  const body = (
    <div className="flex h-full w-full flex-col">
      <div className="flex h-12 shrink-0 items-center gap-1 border-b border-edge px-2">
        {/* The labels scroll inside their own strip, so the close control
            after them can never be pushed out of reach. It was, at every
            width: the sixth label clipped and the close button with it. */}
        <div className="studio-scroll-strip flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
          {MODES.map((candidate) => (
            <button
              key={candidate}
              type="button"
              onClick={() => setMode(candidate)}
              aria-pressed={mode === candidate}
              className={cn(
                "shrink-0 rounded-md px-1.5 py-1 text-[11px] font-medium tracking-wide uppercase",
                "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard)",
                mode === candidate ? "bg-soft text-ink-primary" : "text-ink-muted hover:text-ink-secondary",
              )}
            >
              {candidate}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close inspector"
          className="grid size-7 shrink-0 place-items-center rounded-md text-ink-muted transition-colors hover:bg-soft hover:text-ink-primary"
        >
          <PanelRightClose className="size-4" strokeWidth={1.75} aria-hidden="true" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {mode === "Preview" && <PreviewStage draft={draft} />}
        {mode === "Audit" && <AuditPanel draft={draft} />}
        {mode === "Evidence" && <EvidencePanel />}
        {mode === "Media" && <MediaPanel />}
        {mode === "Brand" && <BrandPanel />}
        {mode === "Prompt" && <PromptPanel draft={draft} />}
      </div>
    </div>
  );

  if (overlay) {
    return (
      <AnimatePresence>
        {open && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.22 }}
              onClick={onClose}
              aria-hidden="true"
              className="absolute inset-0 z-20 bg-canvas/60 backdrop-blur-[2px]"
            />
            <motion.aside
              ref={panelRef}
              tabIndex={-1}
              aria-label="Inspector"
              initial={{ x: "100%" }}
              animate={{ x: 0 }}
              exit={{ x: "100%" }}
              transition={{ duration: 0.22, ease: [0.32, 0.72, 0.24, 1] }}
              className="absolute inset-y-0 right-0 z-30 w-full max-w-[380px] border-l border-edge bg-ink shadow-2xl outline-none"
            >
              {body}
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    );
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.aside
          initial={{ width: 0, opacity: 0 }}
          animate={{ width, opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={{ duration: 0.22, ease: [0.32, 0.72, 0.24, 1] }}
          aria-label="Inspector"
          className="shrink-0 overflow-hidden border-l border-edge bg-ink"
        >
          {/* A fixed inner width, so the content does not reflow while the
              outer width animates open. */}
          <div className={cn("h-full", wide ? "w-[420px]" : "w-[380px]")}>
            {body}
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
