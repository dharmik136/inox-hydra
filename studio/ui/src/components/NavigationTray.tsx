import { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "motion/react";
import { type SectionId, type StudioSection } from "@/lib/navigation";
import { cn } from "@/lib/utils";

interface NavigationTrayProps {
  sections: StudioSection[];
  open: boolean;
  active: SectionId;
  onSelect: (id: SectionId) => void;
  onClose: () => void;
}

/**
 * The morphing navigation tray (blueprint section 5 and micro-interaction 1).
 *
 * It is drawn over the work surface and anchored to the rail, so opening it
 * never changes the width of the writing column underneath. Closing restores
 * focus to whatever opened it, which is the part that is easy to leave out and
 * strands keyboard users in the page body.
 */
export function NavigationTray({ sections, open, active, onSelect, onClose }: NavigationTrayProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreFocusTo = useRef<Element | null>(null);

  useEffect(() => {
    if (open) {
      restoreFocusTo.current = document.activeElement;
      panelRef.current?.focus();
      return;
    }
    if (restoreFocusTo.current instanceof HTMLElement) {
      restoreFocusTo.current.focus();
      restoreFocusTo.current = null;
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Scrim. Dismisses on click, and is inert to assistive technology
              because the tray itself carries the dialog semantics. */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.22 }}
            onClick={onClose}
            aria-hidden="true"
            className="absolute inset-0 z-20 bg-canvas/60 backdrop-blur-[2px]"
          />

          <motion.div
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-label="Studio navigation"
            tabIndex={-1}
            initial={{ opacity: 0, x: -12, scale: 0.98 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: -12, scale: 0.98 }}
            /* Expressive tier: this is a navigation morph, not a hover. */
            transition={{ duration: 0.46, ease: [0.32, 0.72, 0.24, 1] }}
            className="absolute top-3 left-3 z-30 w-80 origin-top-left rounded-lg border border-edge bg-raised p-2 shadow-2xl outline-none"
          >
            <p className="studio-label px-2 pt-2 pb-1">Workspaces</p>
            <ul className="flex flex-col">
              {sections.map((section) => {
                const Icon = section.icon;
                const isActive = section.id === active;
                return (
                  <li key={section.id}>
                    <button
                      type="button"
                      onClick={() => {
                        onSelect(section.id);
                        onClose();
                      }}
                      aria-current={isActive ? "page" : undefined}
                      className={cn(
                        "flex w-full items-start gap-3 rounded-md px-2 py-2 text-left",
                        "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard)",
                        isActive ? "bg-soft" : "hover:bg-soft",
                      )}
                    >
                      <Icon
                        className={cn("mt-0.5 size-[18px] shrink-0", isActive ? "text-signal-orange-text" : "text-ink-muted")}
                        strokeWidth={1.75}
                        aria-hidden="true"
                      />
                      <span className="min-w-0">
                        <span className="block text-[13px] font-medium text-ink-primary">{section.label}</span>
                        <span className="block truncate text-xs text-ink-muted">{section.blurb}</span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
