import {
  Activity,
  PenLine,
  CalendarClock,
  Users,
  BarChart3,
  BookOpen,
  Settings2,
  Wrench,
  UserCheck,
  Sunrise,
  Newspaper,
  Send,
  Shapes,
  BookMarked,
  type LucideIcon,
} from "lucide-react";

export type SectionId =
  | "setup"
  | "today"
  | "record"
  | "activity"
  | "posts"
  | "outbound"
  | "patterns"
  | "composer"
  | "queue"
  | "leads"
  | "analytics"
  | "docs"
  | "settings"
  | "devtools";

export interface StudioSection {
  id: SectionId;
  /**
   * The key this section has in the backend's screen registry
   * (devtools.SCREEN_REGISTRY). Every section has one: an annotation filed
   * from a screen resolves through it, and seven sections declared none, so
   * everything filed from them landed under "unknown".
   *
   * The two vocabularies differ: the registry calls the composer "studio"
   * and leads "crm". tests/test_qc4_t3_screen_registry.py holds that every
   * section declares a key and the registry lists no section that no
   * longer exists; a rename on either side with no change here fails it.
   */
  screenKey: string;
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
  // First, because it is where a new install starts.
  { id: "setup", screenKey: "setup", label: "Setup", blurb: "Connect the browser and teach the studio who you are", icon: UserCheck },
  // Where a creator starts once the studio knows who they are: who to reply
  // to, how the latest post is doing, and the one page worth opening.
  { id: "today", screenKey: "today", label: "Today", blurb: "Who to reply to and how your latest post is doing", icon: Sunrise },
  // Third in the Now group once Replies exists (cycle 4, track 4 restructures
  // the rail into five groups): what from your own record, and from what
  // you asked, is worth writing from today. One batch a day, computed once.
  { id: "record", screenKey: "record", label: "From your record", blurb: "What from your own record, and what you asked, is worth writing from today", icon: BookMarked },
  { id: "activity", screenKey: "activity", label: "Activity", blurb: "What the bridge has read from your LinkedIn, as it arrives", icon: Activity },
  { id: "composer", screenKey: "studio", label: "Composer", blurb: "Write, re-hook and stage the next post", icon: PenLine },
  { id: "queue", screenKey: "queue", label: "Queue", blurb: "Scheduled posts and peak engagement slots", icon: CalendarClock },
  { id: "leads", screenKey: "crm", label: "Leads", blurb: "Lead stream and person dossiers", icon: Users },
  { id: "posts", screenKey: "posts", label: "Posts", blurb: "Which of your posts worked, and who each one brought", icon: Newspaper },
  { id: "patterns", screenKey: "patterns", label: "Patterns", blurb: "What your own posts suggest, and how steadily you post", icon: Shapes },
  { id: "outbound", screenKey: "outbound", label: "Outbound", blurb: "Whose content you engage with, and whether it comes back", icon: Send },
  { id: "analytics", screenKey: "analytics", label: "Analytics", blurb: "Time series, observations and comparisons", icon: BarChart3 },
  // No Swipe File and no Command. The Swipe File drew the same
  // viral_templates rows as the Composer’s hook rail through a second
  // endpoint, and nothing could put a specimen into it or take one out;
  // Command was a textarea and a tick box whose answer could not reach
  // the draft it was about, and is now a block in the Composer’s Prompt
  // panel, beside the text it operates on. A hook form found through
  // Ctrl+K opens the Composer, where the rail applies it.
  { id: "docs", screenKey: "docs", label: "Docs", blurb: "Offline playbook and strategy search", icon: BookOpen },
  { id: "settings", screenKey: "settings", label: "Brand Studio", blurb: "Identity, watermark and local security", icon: Settings2 },
  // Last, and only present when the maintainer surface is on. A consumer
  // build answers 404 for everything behind it.
  { id: "devtools", screenKey: "devtools", label: "Devtools", blurb: "Internal sheet and screen registry", icon: Wrench },
];

export function sectionById(id: SectionId): StudioSection {
  const found = STUDIO_SECTIONS.find((section) => section.id === id);
  if (!found) {
    throw new Error(`Unknown studio section: ${id}`);
  }
  return found;
}
