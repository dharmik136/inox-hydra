import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ShieldCheck } from "lucide-react";
import { type SectionId, type StudioSection } from "@/lib/navigation";
import { cn } from "@/lib/utils";

interface StudioRailProps {
  sections: StudioSection[];
  active: SectionId;
  onSelect: (id: SectionId) => void;
  trayOpen: boolean;
  onToggleTray: () => void;
}

/**
 * The 56px studio rail (blueprint section 5).
 *
 * No text labels by default. Hovering an item floats a label beside it;
 * clicking the brand mark morphs the navigation into a tray drawn OVER the
 * work surface rather than resizing the application, which is what keeps the
 * writing column from reflowing every time someone navigates.
 */
export function StudioRail({ sections, active, onSelect, trayOpen, onToggleTray }: StudioRailProps) {
  const [hovered, setHovered] = useState<SectionId | null>(null);

  return (
    <nav
      aria-label="Studio sections"
      className="relative z-30 flex h-full w-14 shrink-0 flex-col items-center border-r border-edge bg-ink"
    >
      <button
        type="button"
        onClick={onToggleTray}
        aria-label={trayOpen ? "Close navigation tray" : "Open navigation tray"}
        aria-expanded={trayOpen}
        className={cn(
          "mt-3 grid size-9 place-items-center rounded-md",
          "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard)",
          "hover:bg-soft",
          trayOpen && "bg-soft",
        )}
      >
        {/* The product mark. A square with a cut corner reads as a page,
            which is the editorial identity the blueprint asks for, and it
            stays legible at 18px where a detailed glyph would not. */}
        <svg viewBox="0 0 24 24" className="size-[18px]" aria-hidden="true">
          <path
            d="M5 3h9l5 5v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinejoin="round"
            className="text-ink-primary"
          />
          <path d="M14 3v5h5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" className="text-ink-primary" />
          <path d="M8 13h8M8 17h5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" className="text-signal-orange-text" />
        </svg>
      </button>

      <div className="mt-2 h-px w-6 bg-edge" />

      <ul className="mt-2 flex flex-1 flex-col items-center gap-1">
        {sections.map((section) => {
          const Icon = section.icon;
          const isActive = section.id === active;

          return (
            <li key={section.id} className="relative">
              <button
                type="button"
                onClick={() => onSelect(section.id)}
                onMouseEnter={() => setHovered(section.id)}
                onMouseLeave={() => setHovered(null)}
                onFocus={() => setHovered(section.id)}
                onBlur={() => setHovered(null)}
                /* Icon only, so the accessible name has to come from here.
                   Fourteen controls in the vanilla interface announced as
                   nothing but "button" for exactly this reason. */
                aria-label={section.label}
                aria-current={isActive ? "page" : undefined}
                className={cn(
                  "grid size-9 place-items-center rounded-md",
                  "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard)",
                  isActive ? "text-ink-primary" : "text-ink-muted hover:text-ink-secondary hover:bg-soft",
                )}
              >
                {isActive && (
                  <motion.span
                    layoutId="rail-active"
                    className="absolute inset-0 rounded-md bg-soft"
                    transition={{ duration: 0.22, ease: [0.32, 0.72, 0.24, 1] }}
                  />
                )}
                <Icon className="relative size-[18px]" strokeWidth={1.75} aria-hidden="true" />
                {isActive && (
                  <motion.span
                    layoutId="rail-active-edge"
                    className="absolute left-0 h-4 w-0.5 rounded-full bg-signal-orange"
                    transition={{ duration: 0.22, ease: [0.32, 0.72, 0.24, 1] }}
                  />
                )}
              </button>

              {/* Soft floating label. Pointer events are off so it can never
                  sit between the cursor and the control it describes. */}
              <AnimatePresence>
                {hovered === section.id && !trayOpen && (
                  <motion.span
                    initial={{ opacity: 0, x: -4 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -4 }}
                    transition={{ duration: 0.12, ease: [0.32, 0.72, 0.24, 1] }}
                    role="presentation"
                    className="pointer-events-none absolute top-1/2 left-[calc(100%+10px)] z-40 -translate-y-1/2 whitespace-nowrap rounded-md border border-edge bg-raised px-2 py-1 text-xs text-ink-primary shadow-lg"
                  >
                    {section.label}
                  </motion.span>
                )}
              </AnimatePresence>
            </li>
          );
        })}
      </ul>

      {/* Local shield. Blueprint section 14 asks for a persistent trust signal
          that stays calm rather than shouting. It is the one always visible
          piece of state that is not about the document. */}
      <div className="mb-3 flex flex-col items-center gap-1" title="All processing is local to this machine">
        <ShieldCheck className="size-[18px] text-signal-green-text" strokeWidth={1.75} aria-hidden="true" />
        <span className="studio-meta text-[9px] tracking-wider text-ink-muted">LOCAL</span>
      </div>
    </nav>
  );
}
