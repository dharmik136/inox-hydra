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
  /**
   * The key this section has in the backend's screen registry, when it has
   * one. Devtools is not a product screen, so it declares none.
   *
   * The two vocabularies differ: the registry calls the composer
   * "studio", leads "crm" and command "ai_command". An annotation filed
   * from a screen resolves through this, so a rename on either side with
   * no change here files everything under "unknown".
   */
  screenKey?: string;
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
  { id: "composer", screenKey: "studio", label: "Composer", blurb: "Write, re-hook and stage the next post", icon: PenLine },
  { id: "queue", screenKey: "queue", label: "Queue", blurb: "Scheduled posts and peak engagement slots", icon: CalendarClock },
  { id: "leads", screenKey: "crm", label: "Leads", blurb: "Lead stream and person dossiers", icon: Users },
  { id: "swipe", screenKey: "swipe", label: "Swipe File", blurb: "Saved specimens and structural patterns", icon: Bookmark },
  { id: "analytics", screenKey: "analytics", label: "Analytics", blurb: "Time series, observations and comparisons", icon: BarChart3 },
  { id: "command", screenKey: "ai_command", label: "Command", blurb: "Agent runs and local model routing", icon: Terminal },
  { id: "docs", screenKey: "docs", label: "Docs", blurb: "Offline playbook and strategy search", icon: BookOpen },
  { id: "settings", screenKey: "settings", label: "Brand Studio", blurb: "Identity, watermark and local security", icon: Settings2 },
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
