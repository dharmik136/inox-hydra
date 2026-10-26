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
  HeartPulse,
  MessageSquareReply,
  UsersRound,
  Palette,
  BookMarked,
  type LucideIcon,
} from "lucide-react";

export type SectionId =
  | "today"
  | "replies"
  | "record"
  | "composer"
  | "queue"
  | "outbound"
  | "posts"
  | "leads"
  | "audience"
  | "patterns"
  | "analytics"
  | "brand"
  | "activity"
  | "health"
  | "setup"
  | "docs"
  | "settings"
  | "devtools";

/**
 * The five groups the rail is read in, by how often their question is asked
 * (sections report, decision 15). They are headers and never controls: a
 * group is not a place to go, so clicking its name does nothing, and nothing
 * is nested a level below a section that is not that section's own view.
 */
export type GroupId = "now" | "make" | "learn" | "bridge" | "studio";

export const STUDIO_GROUPS: { id: GroupId; label: string }[] = [
  { id: "now", label: "Now" },
  { id: "make", label: "Make" },
  { id: "learn", label: "Learn" },
  { id: "bridge", label: "Bridge" },
  { id: "studio", label: "Studio" },
];

export interface StudioSection {
  id: SectionId;
  /** The rail group the section sits under. Devtools has none: it is not a product section. */
  group?: GroupId;
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
  /** Shown in the rail, the tray, the palette and the context breadcrumb. */
  label: string;
  /** One line of orientation, shown in the expanded tray only. */
  blurb: string;
  icon: LucideIcon;
}

/**
 * The studio rail: seventeen sections in five groups, in the order of the
 * sections report's proposed rail (cycle 4), with From your record (track 7)
 * third in Now. This array is the one definition
 * of the rail; the rail, the tray, the palette, the screen audit
 * (tools/ui_audit.py) and the help's rail table follow it, and
 * tests/test_qc4_t4_rail.py holds them to it.
 *
 * Icons come from lucide, which is the one row of the reference table that
 * survives contact with this architecture: it is MIT licensed, ships as React
 * components, and tree shakes, so only the glyphs referenced here enter the
 * bundle.
 */
export const STUDIO_SECTIONS: StudioSection[] = [
  // Now: what to do in the next hour, and who is waiting on a reply.
  { id: "today", group: "now", screenKey: "today", label: "Today", blurb: "Who to reply to and how your latest post is doing", icon: Sunrise },
  { id: "replies", group: "now", screenKey: "replies", label: "Replies", blurb: "Every comment on your posts that is waiting on a reply", icon: MessageSquareReply },
  // What from your own record, and from what you asked, is worth writing
  // from today. One batch a day, computed once (track 7).
  { id: "record", group: "now", screenKey: "record", label: "From your record", blurb: "What from your own record, and what you asked, is worth writing from today", icon: BookMarked },
  // Make: writing, the queue, and where your own attention goes.
  { id: "composer", group: "make", screenKey: "studio", label: "Composer", blurb: "Write, re-hook and stage the next post", icon: PenLine },
  { id: "queue", group: "make", screenKey: "queue", label: "Queue", blurb: "Scheduled posts and peak engagement slots", icon: CalendarClock },
  { id: "outbound", group: "make", screenKey: "outbound", label: "Outbound", blurb: "Whose content you engage with, and whether it comes back", icon: Send },
  // Learn: your posts, the people, and what your own history suggests.
  { id: "posts", group: "learn", screenKey: "posts", label: "Posts", blurb: "Which of your posts worked, and who each one brought", icon: Newspaper },
  { id: "leads", group: "learn", screenKey: "crm", label: "Leads", blurb: "Lead stream and person dossiers", icon: Users },
  // The set, where Leads is one person: who keeps coming back, who has gone
  // quiet, who is already a connection. Ordered by facts, never by score.
  { id: "audience", group: "learn", screenKey: "audience", label: "Audience", blurb: "Who keeps coming back, who has gone quiet, and who is a connection", icon: UsersRound },
  { id: "patterns", group: "learn", screenKey: "patterns", label: "Patterns", blurb: "What your own posts suggest, and how steadily you post", icon: Shapes },
  { id: "analytics", group: "learn", screenKey: "analytics", label: "Analytics", blurb: "Time series, observations and comparisons", icon: BarChart3 },
  // Brand and Settings both open Brand Studio until the two are split
  // (track 4, phase b): Brand for who you are, Settings for the rest.
  { id: "brand", group: "learn", screenKey: "brand", label: "Brand", blurb: "Your identity and watermark, in Brand Studio", icon: Palette },
  // Bridge: what the bridge read, and whether it is reading.
  { id: "activity", group: "bridge", screenKey: "activity", label: "Activity", blurb: "What the bridge has read from your LinkedIn, as it arrives", icon: Activity },
  // Where a creator looks when the rest looks wrong: whether each reader
  // is reading, what it read this week, and what it could not read. It
  // was a block at the foot of Setup, which is a first-run flow.
  { id: "health", group: "bridge", screenKey: "health", label: "Health", blurb: "Is the bridge reading, and what could it not read", icon: HeartPulse },
  // Studio, at the foot of the rail. Setup is first among them and stays
  // where it is: the studio opens on it until it is done (decision 5), and a
  // place that moves is a place nobody can find twice. No Swipe File and no
  // Command: the Swipe File drew the same rows as the Composer's hook rail,
  // and Command is a block in the Composer's Prompt panel.
  { id: "setup", group: "studio", screenKey: "setup", label: "Setup", blurb: "Connect the browser and teach the studio who you are", icon: UserCheck },
  { id: "docs", group: "studio", screenKey: "docs", label: "Docs", blurb: "Offline playbook and strategy search", icon: BookOpen },
  { id: "settings", group: "studio", screenKey: "settings", label: "Settings", blurb: "Grounding, local security, storage and your licence, in Brand Studio", icon: Settings2 },
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
