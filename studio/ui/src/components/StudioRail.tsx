import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Radio, Search, ShieldCheck } from "lucide-react";
import { AccountSwitcher } from "@/components/AccountSwitcher";
import { STUDIO_GROUPS, type GroupId, type SectionId, type StudioSection } from "@/lib/navigation";
import { RAIL_EXPANDED_QUERY, useMediaQuery } from "@/lib/viewport";
import { cn } from "@/lib/utils";

interface StudioRailProps {
  sections: StudioSection[];
  active: SectionId;
  onSelect: (id: SectionId) => void;
  trayOpen: boolean;
  onToggleTray: () => void;
  /** Opens universal search, the same palette Ctrl+K opens. */
  onSearch: () => void;
  /** Whether the bridge has been heard from lately, as the last screen to ask was told. Null until known. */
  bridgeConnected: boolean | null;
}

const EASE = [0.32, 0.72, 0.24, 1] as const;

/**
 * The studio rail: seventeen sections in five groups (sections report,
 * decisions 15 and 16).
 *
 * From 1200 pixels wide it shows each section's name and the group names;
 * below that it is the 56 pixel column of icons, a label floating beside an
 * icon on hover or keyboard focus. Icon-only navigation is the pattern
 * measured as ignored, so it is kept only where there is no room for words.
 *
 * The group names are headers, never controls: a group is not a place to go.
 * The Studio group sits at the foot with the bridge chip, so Setup, first in
 * it, never moves: the studio opens on it until it is done.
 */
export function StudioRail({
  sections,
  active,
  onSelect,
  trayOpen,
  onToggleTray,
  onSearch,
  bridgeConnected,
}: StudioRailProps) {
  const expanded = useMediaQuery(RAIL_EXPANDED_QUERY);
  const [hovered, setHovered] = useState<SectionId | null>(null);

  const inGroup = (group: GroupId) => sections.filter((section) => section.group === group);
  const loose = sections.filter((section) => !section.group);
  const main = STUDIO_GROUPS.filter((group) => group.id !== "studio");
  const foot = STUDIO_GROUPS.find((group) => group.id === "studio");

  const entry = (section: StudioSection) => {
    const Icon = section.icon;
    const isActive = section.id === active;
    return (
      <li key={section.id} className="relative">
        <button
          type="button"
          onClick={() => onSelect(section.id)}
          onMouseEnter={() => setHovered(section.id)}
          onMouseLeave={() => setHovered(null)}
          // Keyboard focus only. A mouse click also focuses the button,
          // and the label then sat over the page until something else
          // took focus, covering the first line of the surface it opened.
          onFocus={(event) => {
            if (event.currentTarget.matches(":focus-visible")) setHovered(section.id);
          }}
          onBlur={() => setHovered(null)}
          // The name, whether or not the words are on screen: below 1200
          // pixels the button is an icon, and an icon alone announced as
          // nothing but "button" in the vanilla interface.
          aria-label={section.label}
          aria-current={isActive ? "page" : undefined}
          className={cn(
            "relative rounded-md transition-colors duration-(--studio-motion-fast) ease-(--ease-standard)",
            expanded ? "flex h-8 w-full items-center gap-2.5 px-2.5 text-left text-[13px]" : "grid size-9 place-items-center",
            isActive ? "text-ink-primary" : "text-ink-muted hover:text-ink-secondary hover:bg-soft",
          )}
        >
          {isActive && (
            <motion.span layoutId="rail-active" className="absolute inset-0 rounded-md bg-soft" transition={{ duration: 0.22, ease: EASE }} />
          )}
          <Icon className="relative size-[18px] shrink-0" strokeWidth={1.75} aria-hidden="true" />
          {expanded && <span className="relative truncate">{section.label}</span>}
          {isActive && (
            <motion.span
              layoutId="rail-active-edge"
              className="absolute left-0 h-4 w-0.5 rounded-full bg-signal-orange"
              transition={{ duration: 0.22, ease: EASE }}
            />
          )}
        </button>

        {/* Soft floating label, only where the words are not on screen.
            Pointer events are off so it can never sit between the cursor
            and the control it describes. */}
        <AnimatePresence>
          {!expanded && hovered === section.id && !trayOpen && (
            <motion.span
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -4 }}
              transition={{ duration: 0.12, ease: EASE }}
              role="presentation"
              data-rail-hover-label
              className="pointer-events-none absolute top-1/2 left-[calc(100%+10px)] z-40 -translate-y-1/2 whitespace-nowrap rounded-md border border-edge bg-raised px-2 py-1 text-xs text-ink-primary shadow-lg"
            >
              {section.label}
            </motion.span>
          )}
        </AnimatePresence>
      </li>
    );
  };

  // A group: its name as a header, and its sections. Collapsed, the name
  // is for assistive technology only and a rule marks the group's start.
  const group = (id: GroupId, label: string) => {
    const members = inGroup(id);
    if (members.length === 0) return null;
    const headerId = `rail-group-${id}`;
    return (
      <div key={id} className={cn(expanded ? "mt-3 first:mt-1" : "mt-1.5 flex flex-col items-center first:mt-0")}>
        {!expanded && <div aria-hidden="true" className="mb-1.5 h-px w-6 bg-edge" />}
        <p
          id={headerId}
          data-rail-group={id}
          className={cn(expanded ? "studio-label px-2.5 pb-1" : "sr-only")}
        >
          {label}
        </p>
        <ul aria-labelledby={headerId} className={cn("flex flex-col gap-0.5", !expanded && "items-center")}>
          {members.map(entry)}
        </ul>
      </div>
    );
  };

  const bridgeName =
    bridgeConnected === null ? "Bridge state unknown" : bridgeConnected ? "Bridge connected" : "Bridge not connected";

  return (
    <nav
      aria-label="Studio sections"
      className={cn(
        "relative z-30 flex h-full shrink-0 flex-col border-r border-edge bg-ink",
        expanded ? "w-52 px-2" : "w-14 items-center",
      )}
    >
      <div className={cn("mt-3 flex shrink-0 gap-1", expanded ? "items-center" : "flex-col items-center")}>
        <button
          type="button"
          onClick={onToggleTray}
          aria-label={trayOpen ? "Close navigation tray" : "Open navigation tray"}
          aria-expanded={trayOpen}
          className={cn(
            "grid size-9 shrink-0 place-items-center rounded-md",
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

        {/* Search was reachable only through Ctrl+K, which nothing on screen
            mentioned, so for anyone who had not read the help it did not
            exist. A control at the top of the rail, above the destinations it
            can reach, says that it does. */}
        <button
          type="button"
          onClick={onSearch}
          aria-label="Search everything (Ctrl+K)"
          title="Search everything (Ctrl+K)"
          aria-keyshortcuts="Control+K Meta+K"
          className={cn(
            "rounded-md text-ink-muted",
            "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard)",
            "hover:bg-soft hover:text-ink-primary",
            expanded ? "flex h-9 min-w-0 flex-1 items-center gap-2 px-2.5 text-[12px]" : "grid size-9 place-items-center",
          )}
        >
          <Search className="size-[18px] shrink-0" strokeWidth={1.75} aria-hidden="true" />
          {expanded && <span className="truncate">Search</span>}
          {expanded && <kbd className="studio-meta ml-auto rounded-sm border border-edge px-1 text-[10px] text-ink-muted">Ctrl K</kbd>}
        </button>
      </div>

      <div className={cn("mt-2 h-px shrink-0 bg-edge", expanded ? "mx-2.5" : "w-6")} />

      {/* Now, Make, Learn and Bridge. Scrolls inside itself in a short
          window, so the Studio group below never moves. Every row is a
          button, so the scrolling region is reachable by keyboard. */}
      <div className={cn("mt-1 min-h-0 flex-1 overflow-y-auto", !expanded && "flex w-full flex-col items-center")}>
        {main.map((g) => group(g.id, g.label))}
      </div>

      <div className={cn("shrink-0 border-t border-edge pt-1", !expanded && "flex w-full flex-col items-center")}>
        {foot && group(foot.id, foot.label)}
        {loose.length > 0 && (
          <ul className={cn("mt-0.5 flex flex-col gap-0.5", !expanded && "items-center")}>{loose.map(entry)}</ul>
        )}

        {/* The bridge chip: whether the bridge has been heard from, as the
            last screen to ask was told, and the way to Health, where the
            readers are. Nothing is claimed until something has been told. */}
        <button
          type="button"
          onClick={() => onSelect("health")}
          aria-label={`${bridgeName}. Open Health`}
          title={`${bridgeName}. Open Health`}
          className={cn(
            "mt-1.5 rounded-md border border-edge text-ink-muted transition-colors hover:border-edge-strong hover:text-ink-primary",
            expanded ? "flex h-8 w-full items-center gap-2 px-2.5 text-[12px]" : "relative grid size-9 place-items-center",
          )}
        >
          <Radio className="size-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
          <span
            aria-hidden="true"
            className={cn(
              "size-1.5 shrink-0 rounded-full",
              bridgeConnected ? "bg-signal-green" : "border border-edge-strong",
              !expanded && "absolute top-1.5 right-1.5",
            )}
          />
          {expanded && (
            <span className="truncate">
              {bridgeConnected === null ? "Bridge" : bridgeConnected ? "Bridge connected" : "Bridge not connected"}
            </span>
          )}
        </button>

        {/* Multi-tenant profile switcher */}
        <div className={cn("mt-2", expanded && "px-0.5")}>
          <AccountSwitcher condensed />
        </div>

        {/* Local shield. Blueprint section 14 asks for a persistent trust
            signal that stays calm rather than shouting. It used to say "All
            processing is local to this machine", which Send to LinkedIn and a
            connected AI provider contradict, so it says what stays and where
            to see what leaves, as Local security does. */}
        <div
          className={cn("mt-2 mb-3 flex items-center gap-1", expanded ? "px-2.5" : "flex-col")}
          title="Your work is kept on this machine. Send to LinkedIn, a connected AI provider and Generate send what you choose; Settings, Local security, lists what leaves and when."
        >
          <ShieldCheck className="size-[18px] text-signal-green-text" strokeWidth={1.75} aria-hidden="true" />
          <span className="studio-meta text-[9px] tracking-wider text-ink-muted">LOCAL</span>
        </div>
      </div>
    </nav>
  );
}
