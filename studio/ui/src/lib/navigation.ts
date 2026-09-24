import {
  PenLine,
  CalendarClock,
  Users,
  Bookmark,
  BarChart3,
  Terminal,
  BookOpen,
  Settings2,
  Wrench,
  type LucideIcon,
} from "lucide-react";

export type SectionId =
  | "composer"
  | "queue"
  | "leads"
  | "swipe"
  | "analytics"
  | "command"
  | "docs"
  | "settings"
  | "devtools";

export interface StudioSection {
  id: SectionId;
  /** Shown in the floating rail label, the tray and the context breadcrumb. */
  label: string;
  /** One line of orientation, shown in the expanded tray only. */
  blurb: string;
  icon: LucideIcon;
}

/**
 * The studio rail, in blueprint order (section 5).
 *
 * Icons come from lucide, which is the one row of the reference table that
 * survives contact with this architecture: it is MIT licensed, ships as React
 * components, and tree shakes, so only the glyphs referenced here enter the
 * bundle. The vanilla interface uses a 37 symbol coolicons sprite instead, and
 * the two sets are not mixed inside one surface.
 */
export const STUDIO_SECTIONS: StudioSection[] = [
  { id: "composer", label: "Composer", blurb: "Write, re-hook and stage the next post", icon: PenLine },
  { id: "queue", label: "Queue", blurb: "Scheduled posts and peak engagement slots", icon: CalendarClock },
  { id: "leads", label: "Leads", blurb: "Lead stream and person dossiers", icon: Users },
  { id: "swipe", label: "Swipe File", blurb: "Saved specimens and structural patterns", icon: Bookmark },
  { id: "analytics", label: "Analytics", blurb: "Time series, observations and comparisons", icon: BarChart3 },
  { id: "command", label: "Command", blurb: "Agent runs and local model routing", icon: Terminal },
  { id: "docs", label: "Docs", blurb: "Offline playbook and strategy search", icon: BookOpen },
  { id: "settings", label: "Brand Studio", blurb: "Identity, watermark and local security", icon: Settings2 },
  // Last, and only present when the maintainer surface is on. A consumer
  // build answers 404 for everything behind it.
  { id: "devtools", label: "Devtools", blurb: "Internal sheet and screen registry", icon: Wrench },
];

export function sectionById(id: SectionId): StudioSection {
  const found = STUDIO_SECTIONS.find((section) => section.id === id);
  if (!found) {
    throw new Error(`Unknown studio section: ${id}`);
  }
  return found;
}
