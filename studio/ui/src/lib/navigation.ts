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
  type LucideIcon,
} from "lucide-react";

export type SectionId =
  | "setup"
  | "today"
  | "replies"
  | "activity"
  | "health"
  | "posts"
  | "outbound"
  | "patterns"
  | "composer"
  | "queue"
  | "leads"
  | "audience"
  | "analytics"
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
  // First, because it is where a new install starts. It has no screen
  // registry key: it is a first-run flow rather than a place work happens.
  { id: "setup", label: "Setup", blurb: "Connect the browser and teach the studio who you are", icon: UserCheck },
  // Where a creator starts once the studio knows who they are: who to reply
  // to, how the latest post is doing, and the one page worth opening.
  { id: "today", label: "Today", blurb: "Who to reply to and how your latest post is doing", icon: Sunrise },
  // Every comment on your posts waiting on a reply, where Today names five.
  { id: "replies", label: "Replies", blurb: "Every comment on your posts that is waiting on a reply", icon: MessageSquareReply },
  { id: "activity", label: "Activity", blurb: "What the bridge has read from your LinkedIn, as it arrives", icon: Activity },
  // Where a creator looks when the rest looks wrong: whether each reader
  // is reading, what it read this week, and what it could not read. It
  // was a block at the foot of Setup, which is a first-run flow.
  { id: "health", label: "Health", blurb: "Is the bridge reading, and what could it not read", icon: HeartPulse },
  { id: "composer", screenKey: "studio", label: "Composer", blurb: "Write, re-hook and stage the next post", icon: PenLine },
  { id: "queue", screenKey: "queue", label: "Queue", blurb: "Scheduled posts and peak engagement slots", icon: CalendarClock },
  { id: "leads", screenKey: "crm", label: "Leads", blurb: "Lead stream and person dossiers", icon: Users },
  // The set, where Leads is one person: who keeps coming back, who has gone
  // quiet, who is already a connection. Ordered by facts, never by score.
  { id: "audience", label: "Audience", blurb: "Who keeps coming back, who has gone quiet, and who is a connection", icon: UsersRound },
  { id: "posts", label: "Posts", blurb: "Which of your posts worked, and who each one brought", icon: Newspaper },
  { id: "patterns", label: "Patterns", blurb: "What your own posts suggest, and how steadily you post", icon: Shapes },
  { id: "outbound", label: "Outbound", blurb: "Whose content you engage with, and whether it comes back", icon: Send },
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
  { id: "devtools", label: "Devtools", blurb: "Internal sheet and screen registry", icon: Wrench },
];

export function sectionById(id: SectionId): StudioSection {
  const found = STUDIO_SECTIONS.find((section) => section.id === id);
  if (!found) {
    throw new Error(`Unknown studio section: ${id}`);
  }
  return found;
}
