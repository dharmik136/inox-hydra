/**
 * Calls to the local studio.
 *
 * Authentication is a cookie the server sets on every non-/api response, and it
 * is HttpOnly by design, so there is nothing to read or attach here: the only
 * requirement is that fetch is told to send it. A same origin GET carries no
 * Origin header, which the middleware allows explicitly, so these requests are
 * authorised by the cookie and the loopback Host check alone.
 */

// ---------------------------------------------------------------------------
// The request core
// ---------------------------------------------------------------------------

/**
 * Names the creator profile this window is showing, on every request.
 *
 * The active profile is one value for the whole studio, so a second window
 * left on profile A kept saving into profile B after another window switched,
 * while still showing A. The studio now refuses a write whose window shows a
 * profile that is no longer active, and names the profile it served on every
 * answer, which is how a window learns which profile it loaded with.
 */
const PROFILE_HEADER = "X-Inox-Profile";

/** What a window shows when the studio cannot be reached at all. */
export const UNREACHABLE =
  "The studio is not answering. It may have stopped, or this computer may have been asleep. Start it again, then retry.";

/**
 * A refusal or a failure, carrying the reason in words.
 *
 * status is 0 when the studio could not be reached. code is the studio's own
 * name for a refusal when it gave one, for the few callers that act on a
 * particular refusal rather than only showing it.
 */
export class StudioError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(message: string, status: number, code: string | null = null) {
    super(message);
    this.name = "StudioError";
    this.status = status;
    this.code = code;
  }
}

/** Whether this window can reach the studio, and whether it shows the active profile. */
export type Connection =
  | { state: "online" }
  | { state: "offline" }
  | { state: "stale-profile"; shown: string; active: string };

let connection: Connection = { state: "online" };
const connectionListeners = new Set<(next: Connection) => void>();

/** The profile this window loaded with: the first one the studio answered for. */
let shownProfile: string | null = null;

function setConnection(next: Connection): void {
  const same =
    next.state === connection.state &&
    (next.state !== "stale-profile" ||
      (connection.state === "stale-profile" && connection.active === next.active));
  if (same) return;
  connection = next;
  for (const listener of connectionListeners) listener(next);
}

export function currentConnection(): Connection {
  return connection;
}

/** Calls the listener whenever the connection state changes. Returns the unsubscribe. */
export function onConnectionChange(listener: (next: Connection) => void): () => void {
  connectionListeners.add(listener);
  return () => {
    connectionListeners.delete(listener);
  };
}

/** The profile id this window is showing, once the studio has answered once. */
export function shownProfileId(): string | null {
  return shownProfile;
}

/** Records which profile answered, and that the studio answered at all. */
function noteProfile(served: string | null): void {
  if (served) {
    if (shownProfile === null) shownProfile = served;
    if (served !== shownProfile) {
      setConnection({ state: "stale-profile", shown: shownProfile, active: served });
      return;
    }
  } else if (connection.state === "stale-profile") {
    // An answer that names no profile (a crash page, a 401) says nothing
    // about which profile is active, and the studio is still refusing this
    // window's writes. Only an answer for the shown profile clears it.
    return;
  }
  setConnection({ state: "online" });
}

/**
 * fetch, carrying the cookie and the profile this window shows.
 *
 * A request that cannot reach the studio at all is the browser's TypeError,
 * whose message is "Failed to fetch". That reached the screen verbatim; it now
 * becomes a sentence, and every listener learns the studio is unreachable.
 */
async function studioFetch(path: string, init: RequestInit = {}, json = true): Promise<Response> {
  const headers = new Headers(init.headers);
  if (json && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (shownProfile) headers.set(PROFILE_HEADER, shownProfile);

  let response: Response;
  try {
    // Without credentials the cookie is not sent and every call is a 401.
    response = await fetch(path, { ...init, credentials: "same-origin", headers });
  } catch (caught) {
    if (caught instanceof DOMException && caught.name === "AbortError") throw caught;
    if (connection.state !== "stale-profile") setConnection({ state: "offline" });
    throw new StudioError(UNREACHABLE, 0, "unreachable");
  }
  noteProfile(response.headers.get(PROFILE_HEADER));
  return response;
}

/**
 * The reason a refused response gives, in words, never a bare status code.
 *
 * FastAPI puts the reason in "detail", in three shapes: a string (the 5,000
 * character limit, spelled out), an object some routes use to carry the
 * provider's or LinkedIn's own message beside a code, and a list for a
 * request that failed validation. Only the first was read, so the other two
 * showed as "400" or "502" while the studio had said exactly what was wrong.
 */
export async function refusalFrom(response: Response): Promise<StudioError> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // Not JSON: a proxy page or a crash. The status is all there is.
  }
  const detail = body && typeof body === "object" ? (body as { detail?: unknown }).detail : undefined;

  let message: string | null = null;
  let code: string | null = null;
  if (typeof detail === "string" && detail.trim()) {
    message = detail;
  } else if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => (item && typeof item === "object" ? (item as { msg?: unknown }).msg : null))
      .filter((part): part is string => typeof part === "string" && part.trim() !== "");
    if (parts.length) message = `The studio could not accept this: ${parts.join("; ")}.`;
  } else if (detail && typeof detail === "object") {
    const fields = detail as Record<string, unknown>;
    const said = [fields.error, fields.message].filter(
      (part): part is string => typeof part === "string" && part.trim() !== "",
    );
    if (said.length) message = Array.from(new Set(said)).join(": ");
    if (typeof fields.code === "string") code = fields.code;
  }
  return new StudioError(
    message ?? `The studio refused this request (${response.status}${response.statusText ? ` ${response.statusText}` : ""}).`,
    response.status,
    code,
  );
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await studioFetch(path, init);
  if (!response.ok) throw await refusalFrom(response);
  return (await response.json()) as T;
}

/**
 * Asks the studio for the cheapest thing it has, to learn whether it is back
 * and which profile it is on. The answer itself is not used.
 */
export async function pingStudio(): Promise<void> {
  try {
    await studioFetch("/api/queue/status");
  } catch {
    // Already recorded as unreachable.
  }
}

const PROFILE_CHANNEL = "inox-hydra-profile";

/** Tells every other window of this browser that the active profile changed. */
function announceProfileSwitch(active: string): void {
  if (typeof BroadcastChannel === "undefined") return;
  const channel = new BroadcastChannel(PROFILE_CHANNEL);
  channel.postMessage({ active });
  channel.close();
}

/**
 * Listens for a profile switch made in another window of this browser.
 *
 * A window in another browser, or the desktop window beside a browser tab,
 * cannot hear this; it learns of the switch from the next answer the studio
 * gives it, which names the active profile.
 */
export function watchProfileSwitches(): () => void {
  if (typeof BroadcastChannel === "undefined") return () => undefined;
  const channel = new BroadcastChannel(PROFILE_CHANNEL);
  channel.onmessage = (event: MessageEvent) => {
    const active = (event.data as { active?: unknown } | null)?.active;
    if (typeof active === "string" && shownProfile && active !== shownProfile) {
      setConnection({ state: "stale-profile", shown: shownProfile, active });
    }
  };
  return () => channel.close();
}

export interface Draft {
  id: string;
  content: string;
}

interface PostRow {
  id: string;
  content: string;
  created_at?: string;
  // Read when one post is asked for by id, so a post that has gone out is not
  // loaded into an editor whose Save would write over it.
  status?: string;
}

/**
 * The draft the composer reopens, or null on a first run.
 *
 * list_posts orders by COALESCE(scheduled_for, created_at) ASC, so the newest
 * draft is the last row rather than the first. Taking posts[0] would reopen the
 * oldest draft the creator ever wrote.
 */
export async function fetchLatestDraft(): Promise<Draft | null> {
  // One row, because that is all this answers with. Reading every draft to
  // find the newest cost 259 KB on a three year install, on every load of
  // the interface, which is the largest single read on the Today screen.
  const data = await call<{ posts?: PostRow[] }>("/api/posts?status=draft&limit=1");
  const rows = data.posts ?? [];
  const newest = rows[rows.length - 1];
  return newest ? { id: newest.id, content: newest.content } : null;
}

/** Creates a draft and returns the id the server assigned it. */
export async function createDraft(content: string): Promise<string> {
  const data = await call<{ id?: string }>("/api/posts", {
    method: "POST",
    body: JSON.stringify({ content, status: "draft" }),
  });
  if (!data.id) throw new Error("the server created no draft id");
  return data.id;
}

/**
 * Writes new content over an existing draft.
 *
 * base is the text the editor last loaded or saved for this draft. The server
 * refuses the write when the stored draft no longer matches it, because
 * someone saved it from another window in between; see
 * isDraftChangedElsewhere. Leaving it out overwrites whatever is stored.
 *
 * editPostedText says the author means to change the text of a post that is
 * already queued, published or sent; without it the server refuses, see
 * isPostedTextLocked.
 */
export async function updateDraft(id: string, content: string, base?: string, editPostedText = false): Promise<void> {
  const body: Record<string, unknown> = base === undefined ? { content } : { content, base_content: base };
  if (editPostedText) body.edit_posted_text = true;
  await call(`/api/posts/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export interface HookTemplate {
  id: number;
  archetype: string;
  hook_text: string;
  /** Null for a neutral starter form, which nobody rated. */
  velocity_score: number | null;
  engagement_multiplier: string | null;
  pacing_style: string | null;
}

/**
 * Hook archetypes, already ranked by velocity score in SQL. The order is the
 * server's, and the filmstrip's index numbers are that ranking, so nothing is
 * re-sorted here.
 */
export async function fetchHookTemplates(limit = 12): Promise<HookTemplate[]> {
  const data = await call<{ templates?: HookTemplate[] }>(
    `/api/v1/intelligence/templates?limit=${limit}`,
  );
  return data.templates ?? [];
}

/** The formatters the selection toolbar offers, and their endpoints. */
export type FormatKind =
  | "bold"
  | "italic"
  | "underline"
  | "monospace"
  | "strikethrough"
  | "clean";

const FORMAT_PATHS: Record<FormatKind, string> = {
  bold: "/api/format/bold",
  italic: "/api/format/italic",
  underline: "/api/format/underline",
  monospace: "/api/format/monospace",
  strikethrough: "/api/format/strikethrough",
  clean: "/api/format/clean",
};

/**
 * Formats a selection through the backend rather than reimplementing the
 * Unicode maps in the browser. There is one set of formatters in this product
 * and a second copy would drift from it, which matters because the fold verdict
 * is computed from whatever these return.
 */
export async function formatText(kind: FormatKind, text: string): Promise<string> {
  const data = await call<{ formatted?: string; cleaned?: string }>(FORMAT_PATHS[kind], {
    method: "POST",
    body: JSON.stringify({ text }),
  });
  // /api/format/clean answers with "cleaned" while the rest answer with
  // "formatted". Reading only one of those returns undefined for the other and
  // silently wipes the selection.
  const result = data.formatted ?? data.cleaned;
  if (typeof result !== "string") {
    throw new Error(`${kind} returned no text`);
  }
  return result;
}

export interface GeneratedHook {
  archetype: string;
  /**
   * The field is hook_text, not hook. generate_10x_hooks builds dicts keyed
   * "hook" internally, but the endpoint enriches each one before returning it
   * and renames the body in the process. Reading the inner name yields
   * undefined, and a specimen card that renders an empty body rather than an
   * obvious error.
   */
  hook_text: string;
  char_count: number;
  mobile_safe: boolean;
}

/**
 * Ten alternative openings for the given text, from /api/format/re-hook.
 *
 * This is the one action in the toolbar that calls a model when the creator has
 * configured one. With no key it still answers, from deterministic templates,
 * which is why it is safe to offer unconditionally.
 */
export async function generateHooks(text: string): Promise<GeneratedHook[]> {
  const data = await call<{ hooks?: GeneratedHook[] }>("/api/format/re-hook", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
  return data.hooks ?? [];
}

export interface AlgorithmAudit {
  safety_score: number;
  status_label: string;
  word_count: number;
  estimated_dwell_seconds: number;
  /** What the feed is expected to punish. May be empty. */
  penalties: string[];
  /**
   * Advice, which is NOT a per-penalty pairing.
   *
   * audit_linkedin_algorithm_safety appends a recommendation with no matching
   * penalty in three branches: no hashtags at all, a read under fifteen
   * seconds, and a read inside the optimal window, the last of which is
   * praise rather than a fix. Zipping the two arrays by index therefore
   * attributes the wrong remedy to the wrong finding, and on a clean draft it
   * invents findings that do not exist.
   */
  recommendations: string[];
  has_outbound_links: boolean;
  hashtag_count: number;
  mention_count: number;
}

/** Audits a draft against the six distribution rules the backend checks. */
export async function auditDraft(text: string): Promise<AlgorithmAudit> {
  return call<AlgorithmAudit>("/api/format/algorithm-audit", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

/**
 * Every field the profile carries.
 *
 * All ten are listed because saving replaces the stored record wholesale:
 * update_creator_profile does INSERT OR REPLACE with the serialised payload,
 * so a partial write silently resets whatever it left out to the model's
 * defaults. Anything editing this has to send back what it read.
 */
export interface CreatorProfile {
  name: string;
  headline: string;
  company: string;
  brand_watermark_text: string;
  brand_watermark_position: string;
  brand_watermark_style: string;
  brand_watermark_enabled: boolean;
  eliminate_provider_watermark_default: boolean;
  default_aspect_ratio: string;
  default_visual_style: string;
}

/** Writes the whole profile back. See the note on CreatorProfile. */
export async function saveProfile(profile: CreatorProfile): Promise<void> {
  await call("/api/settings/profile", {
    method: "POST",
    body: JSON.stringify(profile),
  });
}

export interface ProfileResponse {
  profile: CreatorProfile;
  /**
   * Whether this install knows who its creator is.
   *
   * The backend is explicit that a caller must tell "never configured" apart
   * from "configured to an empty string", and names the feed simulator as one
   * of the surfaces that has to ask before rendering a name rather than
   * falling back to one it invented. So the preview reads this flag and shows
   * unnamed placeholders when it is false.
   */
  is_set: boolean;
  linkedin_connected: boolean;
}

export async function fetchProfile(): Promise<ProfileResponse> {
  return call<ProfileResponse>("/api/settings/profile");
}

export interface MediaAsset {
  id: string;
  filename: string;
  media_type: string;
  mime_type: string;
  size_bytes: number;
  dimensions: string | null;
  page_count: number | null;
  duration_seconds: number | null;
  created_at: string;
}

export async function fetchMedia(): Promise<MediaAsset[]> {
  const data = await call<{ assets?: MediaAsset[] }>("/api/media");
  return data.assets ?? [];
}

export interface AiStatus {
  provider: string;
  has_api_key: boolean;
  model: string;
  active_mode: string;
  capabilities: string[];
}

/** What a Composer writing request carries beyond your words (GET /api/v1/composer/told). */
export interface ModelTold {
  provider: { configured: boolean; provider: string | null; model: string | null };
  voice: {
    sent: boolean;
    /** Lines about you, from your confirmed profile. */
    who: string[];
    /** "Measured across N of their posts:" and the habits, once habits_need posts are held. */
    habits: string[];
    posts_measured: number;
    habits_need: number;
    /** The opening lines of your best posts, as they are appended. */
    openers: string[];
    openers_rule: string;
    sent_with: string[];
  };
  scar_tissue: { phrases: string[]; checked_on: string[]; named_in_command: string[] };
  grounding: { sources: number; sources_on: number; sent_with: string[] };
  images: { model_writes: string | null; studio_adds: string[]; refused_when: string };
  /** The things to remember that go with writing, as you chose: all, the ticked ones, or none. */
  remembered?: { mode: "all" | "chosen" | "off"; sent: string[]; sent_with: string[] };
}

export async function fetchModelTold(): Promise<ModelTold> {
  return call<ModelTold>("/api/v1/composer/told");
}

export async function fetchAiStatus(): Promise<AiStatus> {
  return call<AiStatus>("/api/ai/status");
}

// ---------------------------------------------------------------------------
// Reverse CRM
// ---------------------------------------------------------------------------

export interface Lead {
  id: string;
  name: string;
  headline: string | null;
  company: string | null;
  profile_url: string | null;
  /** The CRM writer stores the profile here rather than in profile_url. */
  linkedin_urn?: string | null;
  engagement_type: string | null;
  status: string;
  seniority_level: string | null;
  /** Deterministic ICP score. 0 means unscored, not "scored zero". */
  icp_score: number;
  notes: string | null;
  created_at: string;
}

export async function fetchLeads(status?: string): Promise<Lead[]> {
  const query = status && status !== "All" ? `?status=${encodeURIComponent(status)}` : "";
  const data = await call<{ leads?: Lead[] }>(`/api/leads${query}`);
  return data.leads ?? [];
}

export interface LeadInteraction {
  id: number;
  post_id: string | null;
  post_urn?: string | null;
  interaction_type: string | null;
  comment_text: string | null;
  suggested_dm_reply: string | null;
  interacted_at: string;
  /**
   * Whether this was on one of your posts. "unknown" until your post history
   * has been imported to the end, and for captures that named no post.
   */
  post_origin?: "yours" | "not_yours" | "unknown";
  /** The opening of the post it was on, when the studio holds that post. */
  post_excerpt?: string | null;
}

export interface LeadReview {
  history_complete: boolean;
  counts: { yours: number; not_yours: number; unknown: number };
  not_yours: { id: string; name: string; headline: string | null; interactions: number }[];
}

export async function fetchLeadReview(): Promise<LeadReview> {
  return call<LeadReview>("/api/v1/leads/review");
}

/** Deletes those of the named leads that are still classified as not from your posts. */
export async function removeLeadsNotOnYourPosts(leadIds: string[]): Promise<{ removed: number; kept: number }> {
  return call("/api/v1/leads/review/remove", { method: "POST", body: JSON.stringify({ lead_ids: leadIds }) });
}

export interface LeadStageEvent {
  from_status: string | null;
  to_status: string;
  changed_at: string;
  /** The post the change came from; null for one made with no post in view. */
  post_urn?: string | null;
  /** That post's opening, when the studio holds the post. */
  post_excerpt?: string | null;
}

/** Reactions older than 24 months that retention folded into counts (studio/backend/retention.py). */
export interface FoldedReactions {
  count: number;
  on_your_posts: number;
  on_others_posts: number;
  on_unknown_posts: number;
  folded_through: string | null;
}

export async function fetchLeadTimeline(
  leadId: string,
): Promise<{
  lead: Lead;
  interactions: LeadInteraction[];
  stage_history?: LeadStageEvent[];
  folded_reactions?: FoldedReactions | null;
}> {
  return call(`/api/v1/crm/leads/${encodeURIComponent(leadId)}/timeline`);
}

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------

export type AnalyticsRange = "7d" | "30d" | "90d";

export interface AnalyticsPoint {
  date: string;
  impressions: number | null;
  reactions: number | null;
  comments: number | null;
  shares: number | null;
  engagement_rate: number | null;
  followers: number | null;
  profile_views: number | null;
  /**
   * Where the row came from: "observed", "manual" or "seed".
   *
   * This column exists because the studio once generated ninety days of
   * analytics by modulo arithmetic at every boot with nothing marking them
   * synthetic, and every chart, KPI and export drew from it indistinguishably
   * from real capture. Any surface that renders these numbers has to render
   * this too.
   */
  source: string | null;
}

export async function fetchAnalyticsOverview(range: AnalyticsRange): Promise<AnalyticsPoint[]> {
  const data = await call<{ series?: AnalyticsPoint[] }>(`/api/analytics/overview?range=${range}`);
  return data.series ?? [];
}

export interface AnalyticsKpis {
  /** Days of single-day figures the totals are made of. */
  days_counted?: number;
  /** Captured days left out because their window was not one day. */
  days_excluded_unknown_window?: number;
  impressions: number | null;
  impressions_delta_pct: number | null;
  total_engagements: number | null;
  engagements_delta_pct: number | null;
  avg_engagement_rate: number | null;
  engagement_rate_delta: number | null;
  total_followers: number | null;
  follower_growth: number | null;
  profile_views: number | null;
  profile_views_delta_pct: number | null;
  /**
   * Fields built from a figure LinkedIn rounded, such as 1.2K, which is
   * anything from 1,150 to 1,249. Every screen that draws these figures
   * marks them: Analytics did, and Today's thirty days drew them unmarked.
   */
  approximate?: string[];
  /** Changes not shown because they are smaller than that rounding. */
  within_rounding?: string[];
}

export async function fetchAnalyticsKpis(range: AnalyticsRange): Promise<AnalyticsKpis> {
  return call<AnalyticsKpis>(`/api/analytics/kpis?range=${range}`);
}

/**
 * Which posts worked, from the whole history and one engine (results.py), not
 * from the page this screen happens to have fetched.
 */
export interface AnalyticsBest {
  best: string[];
  worst: string[];
  metric: string;
  ranked_posts: number;
  settled_posts: number;
  settled_after_hours: number;
  usual: Record<string, { median: number | null; posts: number }>;
  /**
   * Each named post's figures and how they compare with the creator's own
   * median. They travel with the answer because the post that worked best is
   * usually not on the page of the table the screen is showing.
   */
  named: Record<
    string,
    {
      impressions: number | null;
      reactions: number | null;
      comments: number | null;
      reposts: number | null;
      source: string | null;
      against_usual: Record<string, number>;
    }
  >;
}

/**
 * The posts that did best and worst against the creator's own median, from
 * the whole history (results.best), for the Analytics aside. It came beside
 * a fourteen-row post table that the Posts screen holds in full; the table
 * moved there, and the aside reads the engine's answer on its own.
 */
export async function fetchAnalyticsBest(): Promise<AnalyticsBest | null> {
  const data = await call<{ best?: AnalyticsBest }>("/api/analytics/best");
  return data.best ?? null;
}

// ---------------------------------------------------------------------------
// Smart queue and scheduler
// ---------------------------------------------------------------------------

export interface QueueSlot {
  id: number;
  day_of_week: number;
  day_name: string;
  time_slot: string;
  label: string;
  is_active: number;
}

export interface ScheduledPost {
  id: string;
  content: string;
  scheduled_for: string | null;
  /**
   * Its nearest post inside the cadence rule (validate_schedule_cadence), or
   * null when nothing is that close: which post, when, and how far apart.
   */
  collision?: {
    other_id: string;
    other_excerpt: string | null;
    other_status: string | null;
    other_at: string | null;
    distance_hours: number;
    kind: "duplicate" | "cadence";
  } | null;
}

/** One decision the scheduler made about a post whose time came (queue_dispatches). */
export interface QueueDispatch {
  post_id: string;
  scheduled_for: string | null;
  noticed_at: string;
  late_minutes: number | null;
  outcome: "due_on_time" | "due_within_grace" | "missed_due" | "published_by_linkedin";
}

/** A month of your posts by your own calendar day (GET /api/queue/calendar). */
export interface QueueCalendar {
  month: string;
  /** 0 is Monday. */
  first_weekday: number;
  days_in_month: number;
  days: Record<string, {
    kind: "published" | "scheduled" | "due" | "missed";
    at: string | null;
    ref: string;
    excerpt: string | null;
    late_minutes?: number | null;
    /** What became of a missed post: its status when next seen ("published", "scheduled", "draft"), or "deleted". */
    resolution?: string | null;
  }[]>;
  counts: Record<"published" | "scheduled" | "due" | "missed", number>;
  /** The month's own published posts by weekday, Monday first. */
  by_weekday: number[];
  /** Published posts in each of the twelve months ending with this one. */
  months: { month: string; published: number }[];
}

export async function fetchQueueCalendar(month: string): Promise<QueueCalendar> {
  return call<QueueCalendar>(`/api/queue/calendar?month=${encodeURIComponent(month)}`);
}

export interface NextSlot {
  day_name: string;
  time_slot: string;
  label: string;
  local_datetime: string;
  slot_datetime: string;
  hours_clearance: number;
  cooldown_satisfied: boolean;
}

export interface CadenceHealth {
  total_scheduled: number;
  cadence_health_score: number;
  collision_count: number;
  min_spacing_hours: number | null;
  next_smart_slot: NextSlot | null;
  queue_paused: boolean;
}

export async function fetchSmartSlots(): Promise<{ slots: QueueSlot[]; scheduled: ScheduledPost[] }> {
  const data = await call<{ slots?: QueueSlot[]; scheduled_posts?: ScheduledPost[] }>(
    "/api/queue/smart-slots",
  );
  return { slots: data.slots ?? [], scheduled: data.scheduled_posts ?? [] };
}

/**
 * Queued posts whose time has come, waiting for the creator to post them.
 *
 * The queue posts nothing. At a post's time it marks it due, and the post is
 * published only when the creator says they posted it (publishNow) or the
 * bridge sees it on LinkedIn.
 */
/**
 * Queued posts whose time has come, with why one was missed when it was.
 *
 * Reads the one place that builds this list (today.due_posts on the server),
 * which also backs Today's due section, instead of the generic posts
 * endpoint, which carried no missed note at all.
 */
export async function fetchDuePosts(): Promise<TodayDuePost[]> {
  const data = await call<{ due?: TodayDuePost[] }>("/api/queue/due");
  return data.due ?? [];
}

/**
 * Takes a due post off the Queue and back to the drafts, text kept, for a
 * post the creator has decided not to post now. Only the status changes.
 */
export async function returnToDrafts(postId: string): Promise<void> {
  await call(`/api/posts/${encodeURIComponent(postId)}`, {
    method: "PUT",
    body: JSON.stringify({ status: "draft" }),
  });
}

export async function fetchCadenceHealth(): Promise<CadenceHealth> {
  return call<CadenceHealth>("/api/queue/cadence-health");
}

/**
 * Pauses or resumes automated publishing.
 *
 * The server reads the state back after writing and reports what it actually
 * is, because a failed write that returned success told the creator their
 * queue was paused while the dispatcher went on publishing. So the caller uses
 * the returned value rather than assuming the request took effect.
 */
export async function toggleQueuePause(paused: boolean): Promise<boolean> {
  const data = await call<{ queue_paused?: boolean }>("/api/queue/toggle-pause", {
    method: "POST",
    body: JSON.stringify({ paused }),
  });
  if (typeof data.queue_paused !== "boolean") {
    throw new Error("the server did not report the queue state back");
  }
  return data.queue_paused;
}

/** What one check of the queue decided, post by post: which rule, and how late. */
export interface DispatchAction {
  post_id: string;
  action: QueueDispatch["outcome"];
  overdue_minutes: number;
}

export async function dispatchQueueNow(): Promise<DispatchAction[]> {
  const data = await call<{ actions?: unknown }>("/api/v1/scheduler/dispatch/now", { method: "POST" });
  const actions = data.actions;
  return Array.isArray(actions)
    ? actions.filter((a): a is DispatchAction => typeof a === "object" && a !== null && "action" in a)
    : [];
}

// ---------------------------------------------------------------------------
// Offline documentation
// ---------------------------------------------------------------------------

/** One of the seven hand written module manuals. */
export interface DocModule {
  id: string;
  /** "01" through "06", or "Master". A label, despite the name. */
  number: string;
  title: string;
  summary: string;
  category: string;
}

/**
 * One file in the offline library.
 *
 * The search index has always covered every markdown file under the docs
 * directory and the product listed seven, so most of what a search could match
 * had no route and the hit could not be opened. This is the whole set, each
 * entry carrying the id that opens it.
 */
export interface DocLibraryEntry {
  id: string;
  /** Forward slashed, relative to the docs directory. Relative links resolve against it. */
  path: string;
  title: string;
  category: string;
  words: number;
  /** The document's own opening line. Markdown, rendered through the parser. */
  excerpt: string;
  /** Which help section this is filed under. See HELP_SECTIONS in docs_engine.py. */
  section: string;
  /** Set when this file is also one of the curated modules. */
  module_id: string | null;
}

/**
 * One part of the help, and what is filed under it.
 *
 * Documents used to be grouped by the folder they sit in, which put "Prudent
 * Handoff" and "Builder Feedback" at the top level of a help centre. Those are
 * facts about the filesystem: nobody looking for what leaves this machine
 * would guess to look under a directory named after a handoff process.
 *
 * Sections carry ids rather than repeating the records, so a grouping cannot
 * drift away from the library it groups.
 */
export interface DocSection {
  id: string;
  title: string;
  blurb: string;
  /** Help for the user, reference for a maintainer, or retired material kept for the record. */
  kind: "help" | "reference" | "retired";
  /** Left out of the Docs home and of search: maintainer and retired documents, unless dev mode is on. */
  hidden?: boolean;
  count: number;
  words: number;
  document_ids: string[];
}

export interface DocHit {
  filename: string;
  section: string;
  /** Carries the FTS5 <mark> pairs. Parse with lib/snippet.ts, never innerHTML. */
  snippet: string;
  relevance_rank: number;
  /** The document this section lives in, which is what makes a hit a destination. */
  document_id: string;
  /** That document's title, so a result reads as an answer and not a filename. */
  document_title: string;
  /**
   * Which part of the help it came from.
   *
   * Deliberately not called "section": that name is taken by the heading FTS5
   * matched inside the document, and the anchor a result scrolls to is derived
   * from it. Reusing the name broke every jump to a passage while leaving the
   * result list looking right.
   */
  help_section: string;
}

export interface DocLibrary {
  modules: DocModule[];
  library: DocLibraryEntry[];
  sections: DocSection[];
}

export interface DocContent {
  id: string;
  title: string;
  path: string;
  category: string;
  /** The help section it is filed under, which is the reader's breadcrumb. */
  section: string;
  /** Kept for the record, and contradicted by the code in places. */
  retired: boolean;
  words: number;
  content: string;
}

export async function fetchDocLibrary(): Promise<DocLibrary> {
  const data = await call<{ modules?: DocModule[]; library?: DocLibraryEntry[]; sections?: DocSection[] }>(
    "/api/docs",
  );
  return { modules: data.modules ?? [], library: data.library ?? [], sections: data.sections ?? [] };
}

export async function searchDocs(query: string, limit = 20): Promise<DocHit[]> {
  const data = await call<{ results?: DocHit[] }>(
    `/api/docs/search?q=${encodeURIComponent(query)}&limit=${limit}`,
  );
  return data.results ?? [];
}

export async function fetchDocument(documentId: string): Promise<DocContent> {
  const data = await call<Partial<DocContent> & { markdown?: string }>(
    `/api/docs/${encodeURIComponent(documentId)}`,
  );
  return {
    id: data.id ?? documentId,
    // The response had no title field and the client read one, so every
    // document in the reader used to be headed by its own raw id.
    title: data.title ?? documentId,
    path: data.path ?? "",
    category: data.category ?? "",
    section: data.section ?? "",
    retired: data.retired ?? false,
    words: data.words ?? 0,
    content: data.content ?? data.markdown ?? "",
  };
}

// ---------------------------------------------------------------------------
// Agent command
// ---------------------------------------------------------------------------

export async function runAiCommand(command: string, context?: string): Promise<Record<string, unknown>> {
  return call<Record<string, unknown>>("/api/ai/command", {
    method: "POST",
    body: JSON.stringify({ command, context: context ?? null }),
  });
}

// ---------------------------------------------------------------------------
// CRM actions
// ---------------------------------------------------------------------------

/** The four the backend accepts. Anything else is rejected with a 400. */
export const LEAD_STATUSES = ["New Lead", "Outreach Sent", "Connected", "Meeting Booked"] as const;

/**
 * Moves a lead to a stage. postUrn is the post the change came from, when the
 * dossier was opened from one; the studio refuses it (422) for a post the
 * person never engaged with rather than record it.
 */
export async function updateLeadStatus(leadId: string, status: string, postUrn?: string | null): Promise<void> {
  await call(`/api/leads/${encodeURIComponent(leadId)}/status`, {
    method: "PUT",
    body: JSON.stringify(postUrn ? { status, post_urn: postUrn } : { status }),
  });
}

export async function generateLeadDm(
  leadName: string,
  commentText: string,
  postTopic?: string,
): Promise<string> {
  const data = await call<{ suggested_dm?: string }>("/api/v1/crm/leads/generate-dm", {
    method: "POST",
    body: JSON.stringify({
      lead_name: leadName,
      comment_text: commentText,
      // No default topic. The server drafts nothing without one rather than
      // naming a post the creator may never have written.
      post_topic: postTopic || null,
    }),
  });
  if (!data.suggested_dm) {
    throw new Error(
      postTopic
        ? "No reply could be drafted from this comment."
        : "Say which post they commented on, above, and a reply can be drafted.",
    );
  }
  return data.suggested_dm;
}

/**
 * The three openers the backend writes, and the only DM path that needs no
 * comment.
 *
 * generateLeadDm above drafts a reply to something the lead said, so a lead who
 * reacted rather than commented had no draft available at all. This one builds
 * from the stored row, their name, company and how they engaged, which is
 * present for every lead in the stream.
 *
 * The offer is not among them: it used to offer the original author's
 * "architecture blueprint" under every creator's name, and now needs the
 * creator to say what they would share. See fetchLeadOfferDraft.
 */
export const DM_STYLES = [
  { id: "value_add", label: "Peer question" },
  { id: "quick_chat", label: "Suggest a call" },
] as const;

export type DmStyle = (typeof DM_STYLES)[number]["id"];

export async function fetchLeadDmScript(
  leadId: string,
  style: DmStyle,
  topic?: string,
): Promise<string> {
  const params = new URLSearchParams({ style });
  if (topic?.trim()) params.set("topic", topic.trim());
  const data = await call<{ dm_script?: string; error?: string }>(
    `/api/leads/${encodeURIComponent(leadId)}/dm-script?${params}`,
  );
  // The route answers 200 with an error field rather than a status code, so a
  // missing lead would otherwise render as an empty draft panel.
  if (data.error) throw new Error(data.error);
  if (!data.dm_script) throw new Error("the server returned no draft");
  return data.dm_script;
}

/** The CSV route streams a file, so it is a navigation rather than a fetch. */
export const LEADS_CSV_URL = "/api/leads/export/csv";

// ---------------------------------------------------------------------------
// Media
// ---------------------------------------------------------------------------

export interface UploadedMedia {
  asset_id: string;
  filename: string;
  url: string;
  media_type: string;
  size_bytes: number;
}

/**
 * Uploads one file.
 *
 * No Content-Type is set: the browser has to write the multipart boundary
 * itself, and naming the type here omits it, which makes the server reject a
 * body it cannot parse.
 */
export async function uploadMedia(file: File): Promise<UploadedMedia> {
  const form = new FormData();
  form.append("file", file);

  const response = await studioFetch("/api/media/upload", { method: "POST", body: form }, false);
  if (!response.ok) throw await refusalFrom(response);
  return (await response.json()) as UploadedMedia;
}

export async function deleteMedia(assetId: string): Promise<void> {
  await call(`/api/media/${encodeURIComponent(assetId)}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Image studio
// ---------------------------------------------------------------------------

export interface ImageProgress {
  /**
   * The server's own field names, not guessed ones.
   *
   * get_progress returns progress_percent, status_message, result_url and
   * error_message. Reading "percentage" or "image_url" here would yield
   * undefined and render a task stuck at zero that had actually finished,
   * which is the same mistake the hook filmstrip made with hook_text.
   */
  progress_percent: number;
  status_message: string;
  status: string;
  result_url: string | null;
  error_message: string | null;
  /** What the creator should know about a finished image, such as a quote that was not drawn. */
  notice: string | null;
}

export async function startImageGeneration(concept: string, aspectRatio: string): Promise<string> {
  const data = await call<{ task_id?: string }>("/api/image/generate", {
    method: "POST",
    body: JSON.stringify({ concept, aspect_ratio: aspectRatio }),
  });
  if (!data.task_id) throw new Error("the server started no task");
  return data.task_id;
}

export async function fetchImageProgress(taskId: string): Promise<ImageProgress> {
  const data = await call<Record<string, unknown>>(
    `/api/image/progress/${encodeURIComponent(taskId)}`,
  );
  return {
    progress_percent: typeof data.progress_percent === "number" ? data.progress_percent : 0,
    status_message: typeof data.status_message === "string" ? data.status_message : "",
    status: typeof data.status === "string" ? data.status : "unknown",
    result_url: typeof data.result_url === "string" ? data.result_url : null,
    error_message: typeof data.error_message === "string" ? data.error_message : null,
    notice: typeof data.notice === "string" ? data.notice : null,
  };
}

// ---------------------------------------------------------------------------
// Publishing
// ---------------------------------------------------------------------------

/**
 * Marks a stored post as published in the local record.
 *
 * This does not post to LinkedIn and cannot: the handler writes the row's
 * status and published_at and opens no connection. It is the right control for
 * a post the author published themselves, which is still the ordinary case.
 *
 * stageToLinkedIn below is the one that really sends. They are separate calls
 * because they do genuinely different things, and one of them cannot be
 * undone from here.
 */
export async function publishNow(postId: string): Promise<void> {
  await call(`/api/posts/${encodeURIComponent(postId)}/publish-now`, { method: "POST" });
}

export interface StagedToLinkedIn {
  status: string;
  mode: string;
  scheduled_urn: string;
  scheduled_for: string;
  message: string;
}

/**
 * Hands a post to LinkedIn's own scheduler. This one really sends.
 *
 * It schedules rather than posts: LinkedIn holds the post and publishes it at
 * the given time, which is the point, because a local scheduler cannot fire
 * while the laptop is asleep.
 *
 * `confirm` is required by the backend and passed explicitly here rather than
 * defaulted, so a reader of this call site can see that a confirmation
 * happened somewhere. The call cannot be undone from this side: once LinkedIn
 * has the post, cancelling means going to LinkedIn.
 *
 * Three refusals are expected rather than exceptional, and each arrives as a
 * thrown error carrying the server's own words, because each one tells the
 * author something different about what to do next: no saved session, the
 * linkedin egress category still switched off, or LinkedIn itself declining.
 *
 * Two more carry a code. "send_unknown": the post went out and LinkedIn never
 * answered, so it may hold it already. "send_unconfirmed": a later send of
 * that post, refused until the creator has checked LinkedIn and sends again
 * with `confirmResend`.
 */
export async function stageToLinkedIn(
  postId: string,
  scheduledAt: string,
  confirmResend = false,
  /** The account the confirmation named (its vanity). The send goes only as that account. */
  confirmAccount: string | null = null,
): Promise<StagedToLinkedIn> {
  return call<StagedToLinkedIn>(
    `/api/v1/posts/${encodeURIComponent(postId)}/stage-to-linkedin`,
    {
      method: "POST",
      body: JSON.stringify({
        scheduled_at: scheduledAt,
        confirm: true,
        confirm_resend: confirmResend,
        confirm_account: confirmAccount,
      }),
    },
  );
}

export interface CadenceVerdict {
  valid: boolean;
  error: string | null;
  warning: string | null;
  has_collision: boolean;
  cadence_health_score: number | null;
}

/**
 * Checks a proposed time against the twelve hour cooldown before committing.
 *
 * Scheduling calls this first because create and update reject an invalid
 * cadence with a 400, and a rejection after the fact reads as a broken button
 * rather than as the rule it is.
 */
export async function validateCadence(scheduledFor: string, postId?: string): Promise<CadenceVerdict> {
  const data = await call<{ validation?: Record<string, unknown> }>("/api/queue/validate-cadence", {
    method: "POST",
    body: JSON.stringify({ scheduled_for: scheduledFor, post_id: postId ?? null }),
  });
  const v = data.validation ?? {};
  return {
    valid: v.valid !== false,
    error: typeof v.error === "string" ? v.error : null,
    warning: typeof v.warning === "string" ? v.warning : null,
    has_collision: v.has_collision === true,
    cadence_health_score:
      typeof v.cadence_health_score === "number" ? v.cadence_health_score : null,
  };
}

/**
 * Puts a post in a slot. `expectedStatus` is the state the caller read the
 * post in: given, the server moves the post only if it is still in that
 * state at the moment of the write, and refuses with a sentence otherwise,
 * so a stale screen cannot move a post queued since or requeue one published
 * since. A published post is never requeued, whoever asks.
 */
export async function schedulePost(postId: string, scheduledFor: string, expectedStatus?: string): Promise<void> {
  await call(`/api/posts/${encodeURIComponent(postId)}/reschedule`, {
    method: "POST",
    body: JSON.stringify({ scheduled_for: scheduledFor, ...(expectedStatus ? { expected_status: expectedStatus } : {}) }),
  });
}

export async function fetchNextSlot(): Promise<NextSlot | null> {
  const data = await call<{ slot?: NextSlot | null }>("/api/queue/next-slot");
  return data.slot ?? null;
}

// ---------------------------------------------------------------------------
// Bring your own AI
// ---------------------------------------------------------------------------

export interface AiConfig {
  provider: string;
  model: string | null;
  is_configured: boolean;
}

export async function fetchAiConfig(): Promise<{ config: AiConfig; providers: string[] }> {
  const data = await call<{ config?: Record<string, unknown>; supported_providers?: unknown }>(
    "/api/ai/config",
  );
  const cfg = data.config ?? {};
  const providers = Array.isArray(data.supported_providers)
    ? data.supported_providers.map(String)
    : Object.keys(data.supported_providers ?? {});
  return {
    config: {
      provider: typeof cfg.provider === "string" ? cfg.provider : "",
      model: typeof cfg.model === "string" ? cfg.model : null,
      is_configured: cfg.is_configured === true,
    },
    providers,
  };
}

/**
 * Saves a provider only if a live ping to it succeeds.
 *
 * The endpoint verifies before writing and answers 400 without changing
 * anything when it cannot connect, so a rejection here means the existing
 * configuration is intact rather than half replaced.
 */
export async function configureAi(provider: string, apiKey: string, model?: string): Promise<void> {
  await call("/api/ai/configure", {
    method: "POST",
    body: JSON.stringify({ provider, api_key: apiKey, model: model || null }),
  });
}

/** The analytics CSV streams as a file, so it is a link rather than a fetch. */
export const ANALYTICS_CSV_URL = "/api/analytics/export?format=csv";

// ---------------------------------------------------------------------------
// LinkedIn session
// ---------------------------------------------------------------------------

export interface AuthStatus {
  status: string;
  is_connected: boolean;
  /** Whether the client actually holds usable tokens, as opposed to a status string. */
  client_session: boolean;
  /**
   * Said once: the session an earlier version kept in this profile, which is
   * not the first, was removed when this version started (decision D9).
   */
  session_removed?: { at: string; message: string } | null;
  /** Whether anything is stored, usable or not: a stored session the client cannot use is still deletable. */
  stored?: boolean;
  /** When the stored session was saved; null when none is held. */
  saved_at?: string | null;
  /** Whose it is, known only for a session the extension's Sync captured. */
  account?: { vanity: string } | null;
}

export async function fetchAuthStatus(): Promise<AuthStatus> {
  return call<AuthStatus>("/api/auth/status");
}

/** The creator has read the removed-session notice; it is not said again. */
export async function dismissSessionRemovedNotice(): Promise<void> {
  await call("/api/auth/session-removed/dismiss", { method: "POST" });
}

/**
 * Stores the session cookies locally.
 *
 * Deliberately does not contact LinkedIn. The endpoint used to fire an
 * authenticated request on every save, which produced traffic the creator
 * never asked for from a product that promises not to; the sync is a separate,
 * opted-into call now. The interface says so rather than leaving the creator
 * to assume one way or the other.
 */
export async function saveSessionCookies(liAt: string, jsessionId: string): Promise<void> {
  await call("/api/auth/cookies", {
    method: "POST",
    body: JSON.stringify({ li_at: liAt, JSESSIONID: jsessionId }),
  });
}

// ---------------------------------------------------------------------------
// Governance gates
// ---------------------------------------------------------------------------

export interface GStackAudit {
  passed: boolean;
  score: number;
  /** Six named gates, each a role's check. The keys are the server's. */
  gates: Record<string, unknown>;
  violations: string[];
}

export async function auditGovernance(content: string, title?: string): Promise<GStackAudit> {
  const data = await call<{ audit?: Record<string, any> }>("/api/v1/gstack/audit", {
    method: "POST",
    body: JSON.stringify({ content, title: title || null }),
  });
  const audit = data.audit ?? {};
  return {
    passed: audit.passed === true,
    score: typeof audit.score === "number" ? audit.score : 0,
    gates: audit.gates ?? {},
    violations: Array.isArray(audit.violations) ? audit.violations.map(String) : [],
  };
}

// ---------------------------------------------------------------------------
// Maintainer surfaces
// ---------------------------------------------------------------------------

export interface DevtoolsStatus {
  dev_mode: boolean;
  env_flag: string;
  env_permits: boolean;
  screens: { key: string; label: string; owner: string; tab_id: string }[];
}

/**
 * Whether the maintainer surface is available at all.
 *
 * This is the one devtools route that stays reachable in a consumer build, so
 * it can be asked before anything else is attempted. Every other internal
 * sheet route is behind require_dev_mode and answers 404 otherwise, which is
 * the invariant those 404s exist to maintain.
 */
export async function fetchDevtoolsStatus(): Promise<DevtoolsStatus> {
  const data = await call<Record<string, any>>("/api/v1/devtools/status");
  return {
    dev_mode: data.dev_mode === true,
    env_flag: typeof data.env_flag === "string" ? data.env_flag : "",
    env_permits: data.env_permits === true,
    screens: Array.isArray(data.screens) ? data.screens : [],
  };
}

export interface InternalIssue {
  id: number;
  title: string;
  description: string;
  category: string;
  severity: string;
  status: string;
  screen_key: string | null;
  target_selector: string | null;
  created_at: string;
}

export interface InternalSheet {
  issues: InternalIssue[];
  summary: { total: number; open: number; resolved: number; critical: number };
}

export async function fetchInternalSheet(): Promise<InternalSheet> {
  const data = await call<Record<string, any>>("/api/v1/internal-sheet/issues");
  const summary = data.summary ?? {};
  return {
    issues: Array.isArray(data.issues) ? data.issues : [],
    summary: {
      total: summary.total ?? 0,
      open: summary.open ?? 0,
      resolved: summary.resolved ?? 0,
      critical: summary.critical ?? 0,
    },
  };
}

export async function createInternalIssue(fields: {
  title: string;
  description: string;
  target_selector: string;
  category?: string;
  severity?: string;
}): Promise<void> {
  await call("/api/v1/internal-sheet/issues", {
    method: "POST",
    body: JSON.stringify({
      target_selector: fields.target_selector,
      title: fields.title,
      description: fields.description,
      category: fields.category || "bug",
      severity: fields.severity || "medium",
    }),
  });
}

export async function setInternalIssueStatus(issueId: number, status: string): Promise<void> {
  await call(`/api/v1/internal-sheet/issues/${issueId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export const INTERNAL_SHEET_CSV_URL = "/api/v1/internal-sheet/export.csv";

// ---------------------------------------------------------------------------
// Image prompt preview
// ---------------------------------------------------------------------------

export interface SynthesizedPrompt {
  master_prompt: string;
  negative_prompt: string;
  aspect_ratio: string;
}

/** The prompt the image studio would send, shown before anything is rendered. */
export async function synthesizeImagePrompt(
  concept: string,
  aspectRatio: string,
): Promise<SynthesizedPrompt> {
  const data = await call<{ synthesized?: Record<string, any> }>("/api/image/synthesize-prompt", {
    method: "POST",
    body: JSON.stringify({ concept, aspect_ratio: aspectRatio }),
  });
  const s = data.synthesized ?? {};
  return {
    master_prompt: typeof s.master_prompt === "string" ? s.master_prompt : "",
    negative_prompt: typeof s.negative_prompt === "string" ? s.negative_prompt : "",
    aspect_ratio: typeof s.aspect_ratio === "string" ? s.aspect_ratio : aspectRatio,
  };
}

// ---------------------------------------------------------------------------
// Grounding (MCP)
// ---------------------------------------------------------------------------

export interface McpServer {
  name: string;
  command: string[];
  description: string;
  enabled: boolean;
}

export interface EgressReport {
  leaves_this_machine: boolean;
  provider: string;
  summary: string;
}

export async function fetchMcpServers(): Promise<{ servers: McpServer[]; egress: EgressReport }> {
  const data = await call<{ servers?: McpServer[]; egress?: EgressReport }>("/api/v1/mcp/servers");
  return {
    servers: data.servers ?? [],
    egress: data.egress ?? { leaves_this_machine: false, provider: "", summary: "" },
  };
}

/**
 * Registers a server, switched off.
 *
 * There is no enabled field here on purpose, and the interface does not offer
 * one: agreeing that a command exists and agreeing to be read by it are
 * different acts, so they are two deliberate steps rather than one.
 */
export async function addMcpServer(
  name: string,
  command: string[],
  description?: string,
): Promise<void> {
  await call("/api/v1/mcp/servers", {
    method: "POST",
    body: JSON.stringify({ name, command, description: description || "" }),
  });
}

export async function setMcpServerEnabled(name: string, enabled: boolean): Promise<void> {
  await call(`/api/v1/mcp/servers/${encodeURIComponent(name)}/enabled`, {
    method: "POST",
    body: JSON.stringify({ enabled }),
  });
}

export async function removeMcpServer(name: string): Promise<void> {
  await call(`/api/v1/mcp/servers/${encodeURIComponent(name)}`, { method: "DELETE" });
}

export interface GroundingPreview {
  egress: EgressReport;
  material: { server: string; text: string }[];
  errors: string[];
  bytes_used: number;
  bytes_budget: number;
}

/**
 * What would be gathered, and whether it is about to leave this machine.
 *
 * Reads the enabled servers by the same path a draft takes, so this is the
 * real thing rather than a description of it. Showing the material before it
 * is used is the difference between consent and a setting.
 */
export async function previewGrounding(): Promise<GroundingPreview> {
  const data = await call<Record<string, any>>("/api/v1/mcp/preview");
  return {
    egress: data.egress ?? { leaves_this_machine: false, provider: "", summary: "" },
    material: Array.isArray(data.material) ? data.material : [],
    errors: Array.isArray(data.errors) ? data.errors.map(String) : [],
    bytes_used: typeof data.bytes_used === "number" ? data.bytes_used : 0,
    bytes_budget: typeof data.bytes_budget === "number" ? data.bytes_budget : 0,
  };
}


// ---------------------------------------------------------------------------
// Your data
//
// Everything the studio holds lives in one SQLite file. The backup and export
// endpoints have existed and been tested since before this interface did, and
// nothing ever called them, so the only way to take a copy was the CLI. For a
// product whose whole claim is that your work stays on your machine, that put
// the burden of not losing it entirely on the machine.
// ---------------------------------------------------------------------------

export interface BackupArchive {
  name: string;
  bytes: number;
  modified: string;
  /** Whether the studio can restore it: a ZIP backup or a database copy. */
  restorable?: boolean;
  /** "backup" for a ZIP of database and media, "database" for a database copy alone. */
  kind?: string;
  /** Whether its integrity check passed when it was made; null when no check was recorded. */
  verified?: boolean | null;
  /** The schema version of the database it holds, or null when unreadable. */
  schema_version?: number | null;
}

export interface BackupListing {
  directory: string;
  count: number;
  backups: BackupArchive[];
}

export async function fetchBackups(): Promise<BackupListing> {
  const data = await call<Partial<BackupListing>>("/api/v1/support/backups");
  return {
    directory: data.directory ?? "",
    count: data.count ?? 0,
    backups: Array.isArray(data.backups) ? data.backups : [],
  };
}

/** Snapshots the database and media. Returns the archive path on disk. */
export async function createBackup(label = "manual"): Promise<{ archive: string; bytes: number }> {
  const data = await call<{ archive?: string; bytes?: number }>("/api/v1/support/backup", {
    method: "POST",
    body: JSON.stringify({ label }),
  });
  return { archive: data.archive ?? "", bytes: data.bytes ?? 0 };
}

/**
 * Writes your content out in a portable format.
 *
 * "obsidian" writes a folder of linked notes rather than one file: posts,
 * the people who engaged with them, topics and drafts, ready to open as a vault.
 *
 * Content only. The server excludes credentials deliberately, and the note it
 * returns says so, which is worth showing rather than paraphrasing.
 */
export async function exportData(format: "json" | "csv" | "obsidian"): Promise<{ path: string; note: string }> {
  const data = await call<{ path?: string; note?: string }>("/api/v1/support/export", {
    method: "POST",
    body: JSON.stringify({ format }),
  });
  return { path: data.path ?? "", note: data.note ?? "" };
}


// ---------------------------------------------------------------------------
// Egress
//
// What has actually left this machine, counted at the one chokepoint every
// outbound call now passes through. The Local security tab used to assert
// that nothing but provider prompts ever left, which was untrue of four other
// features and impossible for a reader to verify. Counters can be checked.
// ---------------------------------------------------------------------------

export interface EgressCategory {
  name: string;
  allowed: boolean;
  flag: string;
  default_allowed: boolean;
  performed: number;
  refused: number;
  last_destination: string | null;
  last_refused_endpoint: string | null;
}

export interface EgressStatus {
  master_off: boolean;
  master_flag: string;
  categories: EgressCategory[];
  total_performed: number;
  total_refused: number;
}

export async function fetchEgressStatus(): Promise<EgressStatus> {
  const data = await call<Partial<EgressStatus>>("/api/v1/egress/status");
  return {
    master_off: data.master_off ?? false,
    master_flag: data.master_flag ?? "INOX_NO_EGRESS",
    categories: Array.isArray(data.categories) ? data.categories : [],
    total_performed: data.total_performed ?? 0,
    total_refused: data.total_refused ?? 0,
  };
}


// ---------------------------------------------------------------------------
// The browser bridge
//
// Leads are captured by an extension observing LinkedIn pages you open, so
// until it is loaded the Leads surface can only ever be empty. Four endpoints
// have existed for this since before the interface did and none was reachable,
// which left the one question a new install actually has, "how do leads get
// here", with no answer on screen.
// ---------------------------------------------------------------------------

export interface DetectedBrowser {
  id: string;
  name: string;
  path: string;
  is_available: boolean;
  /**
   * Whether this browser loads an unpacked extension from --load-extension.
   * False for Chrome, which accepts the flag and ignores it. Null means it was
   * never probed, which is a different statement from "will not work".
   */
  carries_extension: boolean | null;
}

export interface BrowserBridge {
  browsers: DetectedBrowser[];
  extension_path: string;
  /**
   * The studio could not be asked which browsers this computer has, so an
   * empty list means nothing. Setup printed "No Chromium browser was found"
   * over an outage, because the failure was swallowed into an empty list.
   */
  unreachable?: boolean;
}

export async function fetchBrowserBridge(): Promise<BrowserBridge> {
  const data = await call<{ browsers?: Record<string, DetectedBrowser>; extension_path?: string }>(
    "/api/v1/browser/status",
  );
  return {
    browsers: Object.values(data.browsers ?? {}),
    extension_path: data.extension_path ?? "",
  };
}

export interface BrowserLaunch {
  browser: string;
  carries_extension: boolean | null;
  message: string;
  extension_path: string;
}

/** Opens a browser on LinkedIn with the bridge attached, where it can be. */
export async function launchBridge(browserId: string, url?: string): Promise<BrowserLaunch> {
  const data = await call<Partial<BrowserLaunch>>("/api/v1/browser/launch", {
    method: "POST",
    // The backend accepts only https LinkedIn URLs and falls back to the feed
    // for anything else, so a URL here is a destination, never a command.
    body: JSON.stringify(url ? { browser_id: browserId, url } : { browser_id: browserId }),
  });
  return {
    browser: data.browser ?? "",
    carries_extension: data.carries_extension ?? null,
    message: data.message ?? "",
    extension_path: data.extension_path ?? "",
  };
}

/**
 * Puts the extension folder on the clipboard, for Load Unpacked by hand.
 *
 * The server answers 200 whether or not the clipboard took it, with the
 * outcome in status, so ok is read from there. Reporting only the path made a
 * failed copy look like a successful one.
 */
export async function copyExtensionPath(): Promise<{ ok: boolean; message: string; path: string }> {
  const data = await call<{ status?: string; message?: string; path?: string; extension_path?: string }>(
    "/api/v1/browser/copy-path",
    { method: "POST" },
  );
  return {
    ok: data.status === "success",
    message: data.message ?? "",
    path: data.path ?? data.extension_path ?? "",
  };
}

// -------------------------------------------------------------
// Onboarding: who the creator is, and their own history
// -------------------------------------------------------------

export interface BridgeStatus {
  connected: boolean;
  last_seen_at: string | null;
  seconds_ago: number | null;
  extension_version: string | null;
  page_kind: string | null;
  /** Each browser the bridge runs in, newest first (cycle 4, track 1, phase 2). */
  bridges?: BridgeEntry[];
}

/** One browser the bridge runs in, from its own latest heartbeat. */
export interface BridgeEntry {
  browser_instance_id: string | null;
  /** The browser's own name, when it gave one. */
  browser: string | null;
  /** The LinkedIn account the browser is signed in to: the creator's own. */
  signed_in_vanity: string | null;
  connected: boolean;
  last_seen_at: string;
  seconds_ago: number;
  extension_version: string | null;
  contract_version: number | null;
  /** LinkedIn pages open, by kind; null from an extension older than the field. */
  open_pages: Record<string, number> | null;
  /** Captures held for an account no creator profile here holds, by account. */
  held: Record<string, number> | null;
  tabs_needing_reload: number | null;
  self_reload: boolean | null;
  files_version: string | null;
  /** Whether the extension could read its own folder at its last look; false when the folder is gone. */
  files_readable?: boolean | null;
  files_checked_at?: string | null;
}

export interface IdentityCandidate {
  vanity: string;
  display_name: string | null;
  headline: string | null;
  location: string | null;
  /** Why the studio thinks this profile is yours, in words to show. */
  evidence: string[];
  observed_at: string | null;
}

export interface CreatorIdentity {
  vanity: string;
  profile_url: string | null;
  display_name: string | null;
  headline: string | null;
  location: string | null;
  about: string | null;
  current_company: string | null;
  follower_count: number | null;
  connection_count: number | null;
  email: string | null;
  phone: string | null;
  birthday: string | null;
  websites: string[];
  profile_observed_at: string | null;
  contact_observed_at: string | null;
  confirmed_at: string;
  positions: { title: string | null; company: string | null; date_range: string | null; location: string | null }[];
  education: { school: string | null; degree: string | null; date_range: string | null }[];
  skills: string[];
}

export type SelfImportKind = "posts" | "comments" | "reactions";

export interface SelfImport {
  id: number;
  kind: SelfImportKind;
  requested_at: string;
  started_at: string | null;
  finished_at: string | null;
  items_seen: number | null;
  outcome: string | null;
}

export interface CaptureHealth {
  extractor: string;
  label: string;
  last_run_at: string | null;
  last_good_at: string | null;
  /** Required fields the latest run could not read on a page that had them. */
  drift: string[];
  /** Why the studio refused the latest run, when it did ("identity"). */
  refused: string | null;
  state: "never_run" | "working" | "read_nothing" | "drifting" | "refused";
  /** The reader's own timing on its latest run; null is not measured. */
  duration_ms: number | null;
  reads: number | null;
  slow_reads: number | null;
  long_tasks: number | null;
  long_task_ms: number | null;
}

// ---------------------------------------------------------------------------
// LinkedIn's data archive: request, find, preview, import
// ---------------------------------------------------------------------------

export interface FoundArchive {
  name: string;
  path: string;
  bytes: number;
  modified: string;
}

export type ArchiveKindTally =
  | { added: number; already_there: number; skipped: number }
  | { filled: string[] }
  | { left_out: true }
  | { not_understood: true; columns: string[] };

export interface ArchiveState {
  download_page: string;
  requested_at: string | null;
  /** Asked for, and nothing imported since: the Setup step looks in Downloads while this is true. */
  waiting: boolean;
  /** LinkedIn export files in Downloads. Only GET /api/v1/archive looks; elsewhere this is empty. */
  found: FoundArchive[];
  /** One sentence when the last import is older than a month; null otherwise. */
  age_nudge?: string | null;
  last_import: { archive_name: string; imported_at: string; summary: Record<string, ArchiveKindTally> } | null;
}

export interface ArchiveFile {
  kind: string;
  label: string;
  file: string;
  /** null when the columns are not the ones the studio knows. */
  rows: number | null;
  importable: boolean;
  default: boolean;
  note: string;
}

export interface ArchivePreview {
  status: string;
  source: string;
  archive: { name: string; bytes: number };
  files: ArchiveFile[];
  not_imported: { file: string; note: string }[];
  recognised: boolean;
}

/** Looks in Downloads for LinkedIn's export. Called by the Setup step only, while it waits. */
export async function fetchArchiveState(): Promise<ArchiveState> {
  return call<ArchiveState>("/api/v1/archive");
}

export async function discardArchive(source: string): Promise<void> {
  await call("/api/v1/archive/discard", { method: "POST", body: JSON.stringify({ source }) });
}

export async function markArchiveRequested(): Promise<ArchiveState> {
  return call<ArchiveState>("/api/v1/archive/requested", { method: "POST" });
}

export async function previewArchive(source: string): Promise<ArchivePreview> {
  return call<ArchivePreview>("/api/v1/archive/preview", { method: "POST", body: JSON.stringify({ source }) });
}

/**
 * Sends a chosen archive to the studio on this machine, which keeps it until
 * it is imported. The file is the request body itself, so the studio can stop
 * at its size cap as the bytes arrive.
 */
export async function uploadArchive(file: File): Promise<ArchivePreview> {
  const response = await studioFetch("/api/v1/archive/upload", {
    method: "POST",
    headers: { "Content-Type": "application/zip", "X-Archive-Name": encodeURIComponent(file.name) },
    body: file,
  });
  if (!response.ok) throw await refusalFrom(response);
  return (await response.json()) as ArchivePreview;
}

/**
 * Imports what is ticked. `confirmOwner` is the creator's word that the
 * archive is theirs, which the studio needs when the archive names someone
 * else or no profile is confirmed yet (409 without it).
 */
export async function importArchive(
  source: string,
  include: string[],
  confirmOwner = false,
): Promise<{ status: string; archive: { name: string; bytes: number }; summary: Record<string, ArchiveKindTally> }> {
  return call("/api/v1/archive/import", {
    method: "POST",
    body: JSON.stringify({ source, include, confirm_owner: confirmOwner }),
  });
}

export interface OnboardingState {
  /** LinkedIn's own archive of the creator's record, and where its import stands. */
  archive: ArchiveState;
  health: CaptureHealth[];
  /** Whether a LinkedIn session is stored for the live send. Never the value. */
  session: { stored: boolean; saved_at: string | null };
  bridge: BridgeStatus;
  candidate: IdentityCandidate | null;
  identity: CreatorIdentity | null;
  counts: { posts: number; comments: number; reactions: number };
  imports: SelfImport[];
  /** history: your posts read to the end of the list, the last of Setup's steps. */
  steps: { bridge: boolean; identity: boolean; posts: boolean; activity: boolean; archive: boolean; history?: boolean };
  /** "Network reading was retired in 2.10.2: ...", only where network reading once ran; else null. */
  network_reading_retired?: string | null;
}

export async function fetchOnboardingState(): Promise<OnboardingState> {
  return call<OnboardingState>("/api/v1/onboarding/state");
}

export async function confirmIdentity(vanity: string): Promise<void> {
  await call("/api/v1/identity/confirm", { method: "POST", body: JSON.stringify({ vanity }) });
}

export async function rejectIdentityCandidate(): Promise<void> {
  await call("/api/v1/identity/reject", { method: "POST" });
}

export async function forgetIdentity(): Promise<void> {
  await call("/api/v1/identity", { method: "DELETE" });
}

/** Asks the extension to scroll one of your activity pages. Returns the page to open. */
export async function requestSelfImport(kind: SelfImportKind): Promise<string> {
  const data = await call<{ open_url?: string }>("/api/v1/self/imports", {
    method: "POST",
    body: JSON.stringify({ kind }),
  });
  if (!data.open_url) throw new Error("the studio did not say which page to open");
  return data.open_url;
}

export async function deleteLinkedInSession(): Promise<void> {
  await call("/api/auth/cookies", { method: "DELETE" });
}

export interface SyncActivityResult {
  status: string;
  current_kind: string;
  target_url: string;
  counts: { posts: number; comments: number; reactions: number };
  browser: string;
  message: string;
}

/** Triggers unified autonomous sync across all three activity streams. */
export async function syncAllActivity(): Promise<SyncActivityResult> {
  return call<SyncActivityResult>("/api/v1/self/sync-all", {
    method: "POST",
  });
}

export interface ActivityPostItem {
  activity_urn: string;
  excerpt: string;
  published_at: string | null;
  reactions: number | null;
  comments: number | null;
  reposts: number | null;
  impressions: number | null;
  last_seen_at: string;
}

export interface ActivityCommentItem {
  target_author: string;
  my_text: string;
  target_excerpt: string;
  target_activity_urn: string;
  last_seen_at: string;
}

export interface ActivityReactionItem {
  target_author: string;
  reaction_kind: string;
  target_excerpt: string;
  target_activity_urn: string;
  last_seen_at: string;
}

export interface ActivityLeadItem {
  id: string;
  name: string;
  headline: string;
  company: string;
  engagement_type: string;
  icp_score: number;
  status: string;
  created_at: string;
}

export interface ActivityImportItem {
  id: number;
  kind: string;
  requested_at: string;
  started_at: string | null;
  finished_at: string | null;
  items_seen: number | null;
  outcome: string;
}

export interface ActivityStreamData {
  status: string;
  creator: string | null;
  summary: {
    posts_count: number;
    comments_count: number;
    reactions_count: number;
    leads_count: number;
    bridge_connected: boolean;
    bridge_last_seen: string | null;
    active_sync_chain: {
      sequence: string[];
      current_index: number;
      active: boolean;
      started_at: string;
      vanity: string;
    } | null;
  };
  recent_posts: ActivityPostItem[];
  recent_comments: ActivityCommentItem[];
  recent_reactions: ActivityReactionItem[];
  recent_leads: ActivityLeadItem[];
  recent_imports: ActivityImportItem[];
}

/** Fetches real-time inspection records of all loaded data and activity streams. */
export async function fetchActivityStream(limit = 25): Promise<ActivityStreamData> {
  return call<ActivityStreamData>(`/api/v1/self/activity-stream?limit=${limit}`);
}

/** LinkedIn's alias for the signed-in member's own profile. */
export const OWN_PROFILE_URL = "https://www.linkedin.com/in/me/";

// ---------------------------------------------------------------------------
// Universal search
// ---------------------------------------------------------------------------

/** Where a result opens. Chosen by the server from the row's own state. */
export type SearchOpens = "composer" | "queue" | "posts" | "leads" | "docs";

export interface SearchResult {
  kind: "post" | "lead" | "specimen" | "help";
  id: string;
  title: string;
  /** Plain text. Help snippets carry FTS5 mark pairs; read them through lib/snippet. */
  snippet: string;
  meta: string;
  opens: SearchOpens;
  status?: string;
  document_title?: string;
  /** The heading a help hit matched, which is what its anchor is derived from. */
  anchor_text?: string;
  retired?: boolean;
}

export interface SearchResponse {
  terms: string[];
  groups: { posts: SearchResult[]; leads: SearchResult[]; specimens: SearchResult[]; help: SearchResult[] };
  total: number;
  /** A group that could not be searched, so its silence is not read as "no matches". */
  failures: Record<string, string>;
}

export async function searchEverything(query: string, limit = 6): Promise<SearchResponse> {
  const data = await call<Partial<SearchResponse>>(
    `/api/v1/search?q=${encodeURIComponent(query)}&limit=${limit}`,
  );
  return {
    terms: data.terms ?? [],
    groups: {
      posts: data.groups?.posts ?? [],
      leads: data.groups?.leads ?? [],
      specimens: data.groups?.specimens ?? [],
      help: data.groups?.help ?? [],
    },
    total: data.total ?? 0,
    failures: data.failures ?? {},
  };
}

/**
 * One draft by id, read fresh from the database the Composer saves to.
 *
 * Asks for the one post. This used to read every draft and search the list in
 * the browser, because there was no single-post route: 259 KB and 1,044 rows
 * on a three year install to put one post in the editor. GET /api/posts/{id}
 * answers the one row.
 *
 * Only drafts: a published or queued post is never loaded into the editor,
 * because Save writes over whatever it holds, so a post that has gone out is
 * refused here even though the route would return it.
 */
export async function fetchDraftById(id: string): Promise<Draft | null> {
  const data = await call<{ post?: PostRow }>(`/api/posts/${encodeURIComponent(id)}`);
  const row = data.post;
  if (!row || row.status !== "draft") return null;
  return { id: row.id, content: row.content };
}

// -------------------------------------------------------------
// Today
// -------------------------------------------------------------

export interface TodayPerson {
  lead_id: string;
  name: string;
  headline: string | null;
  /** How many of your posts they engaged with in the last two weeks. */
  posts_engaged: number;
  commented: boolean;
  latest_comment: string | null;
  /** When the studio first saw their latest comment, not when it was last re-read. */
  engaged_at: string | null;
  last_seen_at: string | null;
}

export interface MetricComparison {
  this_post: number;
  your_usual: number;
  posts_compared: number;
  ratio: number | null;
}

export interface TodayLatestPost {
  activity_urn: string;
  excerpt: string | null;
  published_at: string;
  age_hours: number;
  /**
   * How the post is doing now, as results.figures answers it for every
   * screen: one reading, with the page it came from named. Today used to show
   * the two day old reading here, so one post read 19,943 impressions on this
   * screen and 50,118 on Posts in the same minute.
   */
  current: {
    impressions: number | null;
    reactions: number | null;
    comments: number | null;
    reposts: number | null;
    source: string | null;
    read_at: string | null;
    read_at_age_hours: number | null;
  } | null;
  /** Present only when the post and enough earlier ones were read at about two days old. */
  comparison: Partial<Record<"impressions" | "reactions" | "comments", MetricComparison>> | null;
  not_compared_because: string | null;
  /**
   * Whether the post is still moving, from results.movement: the change
   * between its last two readings as a sentence with its reading count, which
   * abstains with one reading and says "about" when a reading was rounded.
   */
  movement?: {
    verdict: string;
    sentence: string;
    readings: number;
    approximate?: boolean;
    /** What is usual at this age, from the settle curve, or its "not enough posts" below 20 a bucket. */
    usual?: { verdict: string; sentence: string } | null;
  } | null;
  /** Null for a post published from the studio that LinkedIn has not shown yet. */
  url: string | null;
  analytics_url: string | null;
}

export interface TodayBrief {
  identity: { known: boolean; name: string | null };
  freshness: { bridge: BridgeStatus; drifting: string[]; last_capture_at: string | null; posts_held?: number };
  reply_to: TodayPerson[];
  /** Every comment waiting in the window, as Replies counts them; reply_to is five people of them. */
  replies?: { waiting: number; window_days: number };
  latest_post: TodayLatestPost | null;
  /** The newest post marked published here that the bridge has not yet seen on LinkedIn. */
  marked_published?: { post_id: string; published_at: string; excerpt: string | null } | null;
  queue: {
    next_scheduled: { post_id: string; scheduled_for: string; excerpt: string } | null;
    next_open_slot: { local_datetime: string; day_name: string; time_slot: string; label: string | null } | null;
    /** Queued posts whose time has come, oldest first. The creator posts them. */
    due?: { post_id: string; scheduled_for: string; content: string; excerpt: string }[];
  };
  open_next: {
    action: "open" | "setup";
    url?: string;
    reason: string;
    /**
     * Present when the page to open is one the phone asked for through the
     * Telegram bot. short_link is set for an lnkd.in link whose post is not
     * known yet: the url opens it with #inox-desk-<id>, and Done closes it.
     */
    phone_request?: { id: number; activity_urn: string; asked_at: string; source: string; short_link?: string | null };
  };
  /** What the demo cleanup removed, until dismissed; null when there is nothing to say. */
  demo_cleanup?: { removed: { kind: string; count: number }[]; backup: string | null; removed_at: string | null } | null;
  /** The archive age nudge, the same sentence Setup's archive step says; null when the archive is recent. */
  archive_age?: string | null;
}

export async function fetchToday(): Promise<TodayBrief> {
  return call<TodayBrief>("/api/v1/today");
}

/** Today's Not now for a post the phone asked for. Says whether there was an open request to close. */
export async function dismissDeskRequest(id: number): Promise<boolean> {
  const data = await call<{ dismissed?: boolean }>(`/api/v1/desk-requests/${id}/dismiss`, { method: "POST" });
  return !!data.dismissed;
}

/** Today's Done, for a short link from the phone whose post the browser never reported. */
export async function markDeskRequestDone(id: number): Promise<boolean> {
  const data = await call<{ done?: boolean }>(`/api/v1/desk-requests/${id}/done`, { method: "POST" });
  return !!data.done;
}

// -------------------------------------------------------------
// Insights: your posts, and your attention
// -------------------------------------------------------------

/** What a caller needs to ask for the rest of a paged answer. */
export interface Paging {
  total: number;
  limit: number;
  offset: number;
  returned: number;
  has_more: boolean;
}

export interface PostInsightPerson {
  lead_id: string;
  name: string | null;
  commented: boolean;
  status: string | null;
}

/**
 * Where a post sits among the creator's own posts at the same age, for reach
 * and for response, together: a post can sit at p5 for impressions and p86
 * for reactions at the same moment, and either number alone reads as the
 * opposite of the truth. Null when the studio has no reading at a
 * comparable age.
 */
export interface ReachAndResponse {
  band: string;
  band_hours: number | null;
  posts_compared: number;
  read_at_age_hours: number;
  source: string | null;
  reach: { impressions: number | null; percentile: number };
  response: { reactions: number | null; percentile: number };
  shape: string;
}

export interface PostInsight {
  activity_urn: string;
  excerpt: string | null;
  published_at: string | null;
  age_days: number | null;
  /** Old enough (measured or assumed, per settled_after) for its numbers to have mostly arrived. */
  settled: boolean;
  reactions: number | null;
  comments: number | null;
  reposts: number | null;
  impressions: number | null;
  figures_source?: string | null;
  figures_read_at?: string | null;
  /** Against your own median, only for settled posts. 1.0 is your usual. */
  against_usual: Partial<Record<"reactions" | "comments" | "impressions", number>> | null;
  reach_and_response: ReachAndResponse | null;
  people: PostInsightPerson[];
  people_count: number;
  conversations: number;
  /** Null for a post published from the studio that LinkedIn has not shown yet. */
  url: string | null;
}

export interface PostsInsights extends Paging {
  posts: PostInsight[];
  usual: Record<"reactions" | "comments" | "impressions", { median: number | null; posts: number }>;
  best: string[];
  worst: string[];
  settled_after_days: number;
  /** Whether that age was measured from the creator's own readings or assumed (results.settled_after_hours). */
  settled_after?: SettledAfter;
  sort: string;
  settled_state: string | null;
  q: string | null;
}

/** What the Posts table can ask for: which page, sorted and filtered how. */
export interface PostsQuery {
  limit?: number;
  offset?: number;
  sort?: "newest" | "oldest" | "reactions" | "impressions" | "comments";
  settled_state?: "settled" | "growing" | null;
  q?: string;
}

export async function fetchPostsInsights(query: PostsQuery = {}): Promise<PostsInsights> {
  const params = new URLSearchParams();
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  if (query.sort) params.set("sort", query.sort);
  if (query.settled_state) params.set("settled_state", query.settled_state);
  if (query.q?.trim()) params.set("q", query.q.trim());
  return call<PostsInsights>(`/api/v1/insights/posts${params.toString() ? `?${params}` : ""}`);
}

/** One post, in full: the detail view the Posts table opens into. */
export interface PostDetail {
  activity_urn: string;
  text: string;
  published_at: string | null;
  age_days: number | null;
  settled: boolean;
  settled_after_days: number;
  reactions: number | null;
  comments: number | null;
  reposts: number | null;
  impressions: number | null;
  figures_source: string | null;
  figures_read_at: string | null;
  /** How precisely the reading was read: "exact", "rounded", or null when the reader did not say. */
  figures_precision?: string | null;
  /** The figures LinkedIn abbreviated (12K), by name, so the screen says "about" beside those alone. */
  approximate?: string[];
  engagement_rate: number | null;
  engagement_rate_unmeasured?: string | null;
  engagement_rate_note?: string | null;
  against_usual: Partial<Record<"reactions" | "comments" | "impressions", number>> | null;
  reach_and_response: ReachAndResponse | null;
  url: string | null;
  /**
   * LinkedIn's own per-post figures from the post's analytics page, each from
   * the newest reading that showed it (track 5), such as watch_time_seconds
   * and average_watch_seconds. Null when that page was never read.
   */
  per_post?: Record<string, { value: number; read_at: string; read_at_age_hours: number | null; precision: string | null }> | null;
  /** When the bridge first saw the post marked edited on your Activity tab, or null. */
  edited_first_seen_at?: string | null;
  /** The kind of post when a source said (post_format.py): "video", "text" and so on, or "unknown". */
  format?: string | null;
  /** Every reading the studio keeps of the post, from every page, oldest first. */
  readings?: PostReading[];
  /** The reading nearest two days old, which Today compares at, or why there is none. */
  two_day?: TwoDayReading;
  /** Readings older than this many days are thinned by the roll-up; null when it is off. */
  readings_thinned_after_days?: number | null;
}

/** One reading of a post, from one page, at one moment. */
export interface PostReading {
  observed_at: string;
  age_hours: number | null;
  source: string;
  precision: string | null;
  impressions: number | null;
  reactions: number | null;
  comments: number | null;
  reposts: number | null;
}

export interface TwoDayReading {
  /** read; too_new (younger than the window); not_yet (in it, unread); missed (past it, unread); unknown_age. */
  state: "read" | "too_new" | "not_yet" | "missed" | "unknown_age";
  reading: (Partial<PostReading> & { age_hours: number; source: string | null }) | null;
  age_hours: number | null;
  at_hours: number;
  window: [number, number];
}

export async function fetchPostDetail(activityUrn: string): Promise<PostDetail> {
  return call<PostDetail>(`/api/v1/insights/posts/${encodeURIComponent(activityUrn)}`);
}

export interface PostEngager {
  id: string;
  full_name: string | null;
  name: string | null;
  headline: string | null;
  company: string | null;
  seniority_level: string | null;
  icp_score: number | null;
  profile_url: string | null;
  interaction_type: string | null;
  comment_text: string | null;
  interacted_at: string | null;
}

/**
 * Who engaged with one post, for any identifier the product uses
 * (post_identity.resolve), and how many more are kept only as counts: the
 * reactors the retention job folded, who have no names to list.
 */
export async function fetchPostEngagers(
  postId: string,
): Promise<{ status: string; count: number; engagers: PostEngager[]; message?: string; folded_people: number }> {
  const data = await call<Record<string, any>>(`/api/v1/posts/${encodeURIComponent(postId)}/engagers`);
  return {
    status: data.status ?? "success",
    count: data.count ?? 0,
    engagers: data.engagers ?? [],
    message: data.message,
    folded_people: data.folded?.people ?? 0,
  };
}

/** A post marked published here that the bridge has not seen on LinkedIn yet. */
export interface PublishedNotSeen {
  id: string;
  excerpt: string;
  published_at: string | null;
}

/**
 * Posts marked published in the studio with no publication record: sent to
 * LinkedIn and not yet read back by the bridge. Posts lists them as a short
 * group of their own; Analytics' removed table was the one list that held
 * them (review round 2, B2 b).
 */
export async function fetchPublishedNotSeen(): Promise<PublishedNotSeen[]> {
  const data = await call<{ posts?: PublishedNotSeen[] }>("/api/v1/posts/published-not-seen");
  return data.posts ?? [];
}

export interface OutboundAuthor {
  name: string;
  reactions: number;
  comments: number;
  total: number;
  last_outbound_at: string | null;
  last_inbound_at: string | null;
  engaged_back: number;
  gone_quiet: boolean;
  /** The last comment you left on one of their posts, clipped. */
  last_comment: string | null;
  /** The lead this is, when exactly one lead answers to the name. */
  lead_id: string | null;
  /** How many captured people answer to this name. More than 1 cannot be told apart. */
  named_people: number;
  /** When the studio first saw you engage with them: when it read your Activity page, not when you engaged. */
  first_seen_at: string | null;
  /** Your last reaction to them: like, celebrate, support, love, insightful or funny. */
  last_reaction_kind: string | null;
  /** The opening of the last post of theirs you engaged with, clipped. */
  last_excerpt: string | null;
}

/** One account one level down (GET /api/v1/insights/outbound/author). */
export interface OutboundAuthorDetail {
  name: string;
  named_people: number;
  lead_id: string | null;
  /** Every post of theirs you engaged with, newest first, as the studio first saw each. */
  targets: {
    target_activity_urn: string;
    target_excerpt: string | null;
    kind: "reaction" | "comment";
    reaction_kind: string | null;
    my_text: string | null;
    first_seen_at: string;
    last_seen_at: string;
  }[];
  /** Theirs on your posts, newest first; null when the name is not one captured person's. */
  inbound: { post_urn: string; interaction_type: string | null; interacted_at: string; post_excerpt: string | null }[] | null;
  /** From each engagement of yours to their next one on a post of yours, as the studio saw both. */
  lags: { from: string; to: string; days: number }[] | null;
  matched_by: string;
}

export async function fetchOutboundAuthor(name: string): Promise<OutboundAuthorDetail> {
  return call<OutboundAuthorDetail>(`/api/v1/insights/outbound/author?name=${encodeURIComponent(name)}`);
}

export interface GoneQuietAuthor {
  name: string;
  days_since: number;
}

export interface OutboundInsights {
  totals: { reactions: number; comments: number; authors: number; without_author: number };
  coverage: { posts_read: number; posts_with_engagement: number; share: number; one_way_judged: boolean };
  authors: OutboundAuthor[];
  one_way: string[];
  reciprocal: string[];
  /** Every account that has engaged back, counted over all of them, not the page. */
  reciprocal_count: number;
  /** The names that are one captured person's, which reciprocity can be read for. */
  matched_names: number;
  gone_quiet: GoneQuietAuthor[];
  gone_quiet_days: number;
  /** Names that more than one captured person answers to, so cannot be matched. */
  shared_names: number;
  matched_by: string;
}

export async function fetchOutboundInsights(): Promise<OutboundInsights> {
  return call<OutboundInsights>("/api/v1/insights/outbound");
}

export interface PatternFinding {
  key: string;
  label: string;
  with_posts: number;
  without_posts: number;
  with_median?: number;
  without_median?: number;
  ratio?: number | null;
  /** The two sides come from different periods, so the difference may be about when. */
  different_period?: boolean;
  typical_year_with?: number;
  typical_year_without?: number;
  /**
   * What this line is allowed to say: "more", "fewer", "none" when the two
   * sides are too close for the creator's own posts to separate, or
   * "too_few_posts" (results.difference).
   */
  difference?: { verdict: string; notable: boolean; n_with: number; n_without: number; min_per_side: number };
}

/**
 * How old a post of this creator's has to be before its figures are judged:
 * measured from their own readings where they can say so, and assumed where
 * they cannot (results.settled_after_hours).
 */
export interface SettledAfter {
  hours: number;
  measured: boolean;
  posts: number;
}

/**
 * How much of its final figures a post of this creator's has reached by each
 * age, measured from their own readings (results.settle_curve). A point
 * resting on fewer than min_posts_per_bucket posts is noise, and the screen
 * says so rather than drawing it as a measurement.
 */
export interface SettleCurve {
  points: { age_hours: number; posts: number; reactions_share: number; impressions_share: number }[];
  measured_hours: number | null;
  posts: number;
  min_posts_per_bucket: number;
  settled_share: number;
}

export interface PatternsInsights {
  /** How many of the creator's posts the studio holds, whatever their age or figures. */
  posts_held: number;
  posts_compared: number;
  metric: string;
  patterns: PatternFinding[];
  not_enough_posts: PatternFinding[];
  min_per_side: number;
  settled_after?: SettledAfter;
  settle_curve?: SettleCurve;
}

export async function fetchPatternsInsights(): Promise<PatternsInsights> {
  return call<PatternsInsights>("/api/v1/insights/patterns");
}

export interface CadenceInsights {
  posts: number;
  first_post?: string;
  last_post?: string;
  days_since_last?: number;
  median_gap_days?: number | null;
  longest_gap?: { days: number; from: string; to: string } | null;
  by_month?: { month: string; posts: number }[];
  by_weekday?: { day: string; posts: number }[];
  queue?: { scheduled_next_14_days: number; weekly_slots: number };
}

export async function fetchCadenceInsights(): Promise<CadenceInsights> {
  return call<CadenceInsights>("/api/v1/insights/cadence");
}

export interface ContrastFinding {
  key: string;
  label: string;
  /**
   * The engine's own words (contrast_engine.evaluate_contrast_for_posts):
   * "not_enough_data" when a side is short of posts, "different_period" when
   * the two sides come mostly from different years. This said
   * "insufficient_sample", a word the engine uses only for a confidence
   * field, and a cast on the Patterns screen hid the mismatch.
   */
  status: "conclusive" | "not_enough_data" | "different_period";
  n_with: number;
  n_without: number;
  median_with?: number | null;
  median_without?: number | null;
  ratio?: number | null;
  planted_or_significant?: boolean;
  /** What the line is allowed to say, from results.difference. */
  difference?: { verdict: string; notable: boolean; n_with: number; n_without: number; min_per_side: number };
  /** The typical year of each side, when the two sides were dated (results.different_periods). */
  typical_year_with?: number;
  typical_year_without?: number;
  min_required: number;
  reason?: string;
}

/**
 * The contrast engine's comparisons, which Patterns draws its lines from and
 * the Composer's Evidence panel is built from.
 */
export interface ContrastInsights {
  status: string;
  /** The settled posts, with reactions recorded, that every comparison rests on. */
  settled_posts_count: number;
  /** How many posts each side needs before the engine says anything (results.MIN_PER_SIDE). */
  min_arm_size: number;
  settled_after?: SettledAfter;
  contrasts: ContrastFinding[];
  /**
   * The creator's own topics, each compared as a form by the same engine:
   * posts that mention the topic's word against those that do not. They
   * replace the qualified-leads-per-topic table (cycle 4, decision 7).
   */
  topics?: ContrastFinding[];
}

export async function fetchContrastInsights(): Promise<ContrastInsights> {
  return call<ContrastInsights>("/api/v1/insights/contrasts");
}

export interface EvidenceExemplar {
  activity_urn?: string;
  text: string;
  reactions: number;
  comments?: number;
  qualified_leads: number;
}

export interface RetrievalEvidenceBrief {
  has_evidence: boolean;
  message?: string;
  top_exemplars: EvidenceExemplar[];
  bottom_exemplars: EvidenceExemplar[];
  contrast_findings: ContrastFinding[];
  brief_section: string;
  /** How many settled posts the brief needs before it says anything (results.MIN_FOR_MEDIAN). */
  min_settled_posts: number;
  /** How many posts each side of a contrast needs before it is a finding (results.MIN_PER_SIDE). */
  min_per_side: number;
}

export async function fetchEvidenceBrief(): Promise<RetrievalEvidenceBrief> {
  return call<RetrievalEvidenceBrief>("/api/v1/insights/evidence");
}

// ---------------------------------------------------------------------------
// Multi-tenant creator accounts and profile switching
// ---------------------------------------------------------------------------

export interface CreatorAccount {
  id: string;
  name: string;
  vanity: string;
  headline: string;
  avatar_initials: string;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
  posts_count: number;
  drafts_count: number;
  leads_count: number;
}

export interface AccountsResponse {
  status: string;
  accounts: CreatorAccount[];
  active_account_id: string;
  /** How many profiles the licence in effect allows. Each has its own database. */
  profile_limit: number;
}

export async function fetchAccounts(): Promise<AccountsResponse> {
  return call<AccountsResponse>("/api/v1/accounts");
}

export async function createAccount(data: {
  name: string;
  headline?: string;
  vanity?: string;
  id?: string;
}): Promise<{ status: string; account: CreatorAccount }> {
  return call("/api/v1/accounts", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function switchAccount(accountId: string): Promise<{ status: string; active_account_id: string; account?: CreatorAccount }> {
  const result = await call<{ status: string; active_account_id: string; account?: CreatorAccount }>(
    "/api/v1/accounts/switch",
    {
      method: "POST",
      body: JSON.stringify({ account_id: accountId }),
    },
  );
  // Every other window of this browser is now showing a profile that is not
  // the active one, and has to say so before it saves anything.
  announceProfileSwitch(result.active_account_id ?? accountId);
  return result;
}

/** Deletes the profile's folder and everything in it. `confirm` repeats its name. */
export async function deleteAccount(
  accountId: string,
  confirm: string,
): Promise<{ status: string; message: string; active_account_id?: string }> {
  return call(`/api/v1/accounts/${encodeURIComponent(accountId)}`, {
    method: "DELETE",
    body: JSON.stringify({ confirm }),
  });
}

// ---------------------------------------------------------------------------
// Licence, checked on this machine against the vendor's public key
// ---------------------------------------------------------------------------

export interface LicenceDetails {
  email: string;
  name: string;
  tier: "creator" | "agency";
  kind: "annual" | "monthly" | "lifetime";
  profiles: number;
  issued_at: string | null;
  expires_at: string | null;
  updates_until: string | null;
}

export interface LicenceState {
  status: "none" | "active" | "expired" | "invalid";
  tier: "free" | "creator" | "agency";
  tier_label: string;
  licence: LicenceDetails | null;
  reason: string;
  beta_open: boolean;
  profile_limit: number;
  prices: { tier: string; label: string; price: string; includes: string }[];
}

export async function fetchLicence(): Promise<LicenceState> {
  return call<LicenceState>("/api/v1/licence");
}

export async function installLicence(key: string): Promise<{ status: string; licence: LicenceState }> {
  return call("/api/v1/licence", { method: "POST", body: JSON.stringify({ key }) });
}

export async function removeLicence(): Promise<{ status: string; licence: LicenceState }> {
  return call("/api/v1/licence", { method: "DELETE" });
}

/** Removes what the last archive import added, and the record of it. Counts per kind. */
export async function undoArchiveImport(): Promise<{
  status: string;
  archive: { name: string };
  removed: Record<string, number>;
}> {
  return call("/api/v1/archive/undo", { method: "POST" });
}

/** The creator says their LinkedIn account has no posts, so the archive step is done without any. */
export async function markArchiveNoPosts(): Promise<ArchiveState> {
  return call<ArchiveState>("/api/v1/archive/no-posts", { method: "POST" });
}

/** One provider as /api/ai/config describes it, for the Prompt tab's model field. */
export interface AiProviderOption {
  id: string;
  /** The model a blank model field means. */
  defaultModel: string;
  /** Models to suggest. Empty for an endpoint that accepts any name. */
  models: string[];
}

/**
 * The saved setup and every provider with its models, from /api/ai/config.
 *
 * fetchAiConfig keeps only the provider ids, and the Prompt tab needs each
 * one's default and list to offer a model field. Without one, a provider
 * whose default had been retired could not be connected from the interface.
 */
export async function fetchAiProviders(): Promise<{ config: AiConfig; providers: AiProviderOption[] }> {
  const data = await call<{ config?: Record<string, unknown>; supported_providers?: Record<string, unknown> }>(
    "/api/ai/config",
  );
  const cfg = data.config ?? {};
  const listed = data.supported_providers && typeof data.supported_providers === "object" ? data.supported_providers : {};
  const providers = Object.entries(listed).map(([id, raw]) => {
    const meta = (raw ?? {}) as Record<string, unknown>;
    const models = Array.isArray(meta.supported_models) ? meta.supported_models.map(String) : [];
    return {
      id,
      defaultModel: typeof meta.default_model === "string" ? meta.default_model : "",
      models: models.filter((name) => name !== "*"),
    };
  });
  return {
    config: {
      provider: typeof cfg.provider === "string" ? cfg.provider : "",
      model: typeof cfg.model === "string" ? cfg.model : null,
      is_configured: cfg.is_configured === true,
    },
    providers,
  };
}

// -------------------------------------------------------------
// Drafts changed in another window
// -------------------------------------------------------------

/** How the server's refusal of a stale draft save begins (routers/posts.py). */
const DRAFT_CHANGED_ELSEWHERE = "This draft was changed in another window";

/** Whether a failed updateDraft was refused because the draft changed elsewhere. */
export function isDraftChangedElsewhere(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  // Other refusals also answer 409 (a write from a window showing another
  // profile), so the server's own words decide, not the status.
  return error.message.includes(DRAFT_CHANGED_ELSEWHERE);
}

// ---------------------------------------------------------------------------
// Leads: the offer draft, notes and forgetting a person
// ---------------------------------------------------------------------------

/**
 * The "Offer something" opener. The creator says what they would share; the
 * server refuses without it rather than offer something they never made.
 */
export async function fetchLeadOfferDraft(leadId: string, offer: string, topic?: string): Promise<string> {
  const params = new URLSearchParams({ style: "resource_share", offer: offer.trim() });
  if (topic?.trim()) params.set("topic", topic.trim());
  const data = await call<{ dm_script?: string; error?: string }>(
    `/api/leads/${encodeURIComponent(leadId)}/dm-script?${params}`,
  );
  if (data.error) throw new Error(data.error);
  if (!data.dm_script) throw new Error("the server returned no draft");
  return data.dm_script;
}

/** Writes the creator's own notes on a lead. The pipeline stage is left alone. */
export async function updateLeadNotes(leadId: string, notes: string): Promise<string> {
  const data = await call<{ notes?: string }>(`/api/leads/${encodeURIComponent(leadId)}`, {
    method: "PATCH",
    body: JSON.stringify({ notes }),
  });
  return data.notes ?? "";
}

/**
 * Forgets a person: the lead, their engagements, their stage history and any
 * enrichment, in one step on the server. It cannot be undone.
 */
export async function forgetLead(leadId: string): Promise<void> {
  await call(`/api/leads/${encodeURIComponent(leadId)}`, { method: "DELETE" });
}

// -------------------------------------------------------------
// The text of a post that is no longer a draft
// -------------------------------------------------------------

/** Statuses whose text the server keeps unless asked on purpose (routers/posts.py). */
export const POSTED_STATUSES = new Set(["published", "scheduled", "queued", "due", "sent"]);

/** The code the server gives when it refuses new text over such a post. */
const POSTED_TEXT_LOCKED = "posted_text_locked";

/** Whether a failed updateDraft was refused because the post is queued, published or sent. */
export function isPostedTextLocked(error: unknown): boolean {
  return error instanceof Error && (error as Error & { code?: unknown }).code === POSTED_TEXT_LOCKED;
}

export interface StoredPost {
  id: string;
  content: string;
  status: string;
}

/** One post by id, whatever its status, or null when there is none. */
export async function fetchPostById(id: string): Promise<StoredPost | null> {
  const data = await call<{ posts?: (PostRow & { status?: string })[] }>("/api/posts");
  const row = (data.posts ?? []).find((post) => post.id === id);
  return row ? { id: row.id, content: row.content, status: row.status ?? "draft" } : null;
}

/** Hides Today's note on removed demo content. The record of it is kept. */
export async function dismissDemoCleanupNotice(): Promise<boolean> {
  const res = await call<{ dismissed: boolean }>("/api/v1/today/demo-cleanup-notice/dismiss", { method: "POST" });
  return res.dismissed;
}

export interface LeadsPage {
  leads: Lead[];
  /** Leads that match the stage and the search, across every page. */
  matching: number;
  /** Every lead the studio holds. */
  total: number;
  /** Pass back to read the next page; null on the last one. */
  next_cursor: string | null;
}

/**
 * One page of the lead stream, newest first, filtered on the server: the
 * stage, and the search box, where every word must be the start of a word
 * in the person's name, company, headline or notes.
 */
export async function fetchLeadsPage(options: {
  status?: string;
  query?: string;
  cursor?: string | null;
  limit?: number;
}): Promise<LeadsPage> {
  const params = new URLSearchParams({ limit: String(options.limit ?? 200) });
  if (options.status && options.status !== "All") params.set("status", options.status);
  if (options.query?.trim()) params.set("q", options.query.trim());
  if (options.cursor) params.set("cursor", options.cursor);
  const data = await call<Partial<LeadsPage>>(`/api/leads?${params}`);
  return {
    leads: data.leads ?? [],
    matching: data.matching ?? 0,
    total: data.total ?? 0,
    next_cursor: data.next_cursor ?? null,
  };
}

// ---------------------------------------------------------------------------
// Storage and privacy (studio/backend/routers/storage.py)
// ---------------------------------------------------------------------------

export type RetentionJob = "telemetry" | "readings" | "reactions";

export interface RetentionRules {
  daily_backup: "on" | "off";
  telemetry_days: "7" | "30" | "90";
  readings: "on" | "off" | "ask";
  readings_days: "30" | "90" | "365";
  fold_reactions: "on" | "off" | "ask";
  lead_review: "ask" | "off";
}

export interface StorageCategory {
  key: string;
  label: string;
  /** null when this SQLite build cannot measure it: shown as not measured. */
  bytes: number | null;
  rows: number | null;
}

export interface BackupSummary {
  name: string;
  made_at: string;
  bytes: number;
  /** null for a backup made before checks were recorded. */
  verified: boolean | null;
}

export interface RetentionLogEntry {
  job: string;
  started_at: string;
  finished_at: string | null;
  outcome: string;
  removed: number;
  backup: string | null;
}

export interface StorageOverview {
  rules: RetentionRules;
  defaults: Record<keyof RetentionRules, string>;
  options: Record<keyof RetentionRules, string[]>;
  sizes: {
    measured: boolean;
    categories: StorageCategory[];
    database_bytes: number;
    free_bytes: number;
    telemetry_bytes: number;
    media_bytes: number;
    backups_bytes: number;
  };
  backups: {
    enabled: boolean;
    last: BackupSummary | null;
    next_due: string | null;
    automatic_count: number;
    zip_count: number;
    keeps: { daily: number; weekly: number; monthly: number; database_copies: number };
    directory: string;
    last_daily: { ok: boolean; at: string; archive: string | null; bytes: number | null; error: string | null } | null;
    rotation_reach_days: number;
    /** How old the newest backup is, or null when there has never been one. */
    age_hours: number | null;
    /**
     * Whether the backup schedule has stopped producing backups: the newest
     * one is older than twice the daily interval. False while there has
     * never been a backup at all, which "never" says instead.
     */
    stale: boolean;
    never: boolean;
    stale_after_hours: number;
  };
  review: { count: number; silent_days: number; state: "ask" | "off" };
  scrub: { people: number; since: string | null };
  fold_days: number;
  log: RetentionLogEntry[];
}

export interface RetentionPreview {
  job: RetentionJob;
  rows: number;
  total_rows?: number;
  posts?: number;
  people?: number;
  people_left_without_engagement?: number;
  comments_kept?: number;
  older_than_days: number;
  bytes: number | null;
  state: "on" | "off" | "ask";
}

export interface SilentLead {
  id: string;
  name: string | null;
  headline: string | null;
  company: string | null;
  interactions: number;
  last_activity: string;
}

export interface BackupDisclosure {
  automatic_backups: number;
  your_backups: number;
  database_copies: number;
  automatic_gone_by: string;
}

export interface ForgetResult {
  forgotten: number;
  kept_since: number;
  backup: string | null;
  backups: BackupDisclosure;
}

export interface ScrubResult {
  rewritten?: number;
  unchanged?: number;
  failed?: { name: string; error: string }[];
  people?: number;
}

export async function fetchStorage(): Promise<StorageOverview> {
  return call<StorageOverview>("/api/v1/storage");
}

export async function saveRetentionRules(rules: Partial<RetentionRules>): Promise<RetentionRules> {
  const data = await call<{ rules: RetentionRules }>("/api/v1/storage/rules", {
    method: "PUT",
    body: JSON.stringify({ rules }),
  });
  return data.rules;
}

/** What a cleanup would remove now. Removes nothing. */
export async function previewRetention(job: RetentionJob): Promise<RetentionPreview> {
  return call<RetentionPreview>(`/api/v1/storage/preview/${job}`);
}

/** Backs up, then runs the cleanup, and keeps it on from now on. */
export async function runRetention(job: RetentionJob): Promise<{ removed: number; backup: string | null; free_bytes: number }> {
  return call(`/api/v1/storage/run/${job}`, { method: "POST" });
}

export async function fetchSilentLeads(limit = 200): Promise<{ count: number; silent_days: number; leads: SilentLead[] }> {
  return call(`/api/v1/storage/review?limit=${limit}`);
}

export async function forgetSilentLeads(leadIds: string[]): Promise<ForgetResult> {
  return call("/api/v1/storage/review/forget", { method: "POST", body: JSON.stringify({ lead_ids: leadIds }) });
}

export async function keepSilentLeads(leadIds: string[]): Promise<{ kept: number }> {
  return call("/api/v1/storage/review/keep", { method: "POST", body: JSON.stringify({ lead_ids: leadIds }) });
}

/** Removes forgotten people from every backup too, or with leave, lets rotation remove them. */
export async function scrubBackups(leave = false): Promise<ScrubResult> {
  return call("/api/v1/storage/backups/scrub", { method: "POST", body: JSON.stringify({ leave }) });
}

export async function compactDatabase(): Promise<{ before_bytes: number; after_bytes: number }> {
  return call("/api/v1/storage/compact", { method: "POST" });
}

/**
 * Calls the listener each time the studio answers again after this window
 * could not reach it. Returns the unsubscribe.
 *
 * The banner said "this line goes away by itself when it is" back, and it
 * did, while the screen under it kept its "could not be read" until the
 * creator moved away and back: nothing told a screen that the studio had
 * returned. A screen that subscribes reads its data again. A window left on
 * another profile has not come back, so that does not count.
 */
export function onStudioBack(listener: () => void): () => void {
  let away = connection.state === "offline";
  return onConnectionChange((next) => {
    if (next.state === "offline") {
      away = true;
    } else if (away && next.state === "online") {
      away = false;
      listener();
    }
  });
}

export interface RestoreOutcome {
  restoredFrom: string;
  safetyBackup: string | null;
  safetyNote: string;
  /** People forgotten since the backup was made, forgotten again after it. */
  forgottenAgain: number;
}

/**
 * Restores one archive from the backups folder, by its file name there.
 *
 * The studio takes a safety backup of the current state first and swaps all
 * or nothing. A refusal carries its reason, and a restore that stopped part
 * way names the safety backup.
 */
export async function restoreBackup(name: string): Promise<RestoreOutcome> {
  const data = await call<{ restored_from?: string; safety_backup?: string | null; safety_note?: string; forgotten_again?: number }>(
    "/api/v1/support/restore",
    { method: "POST", body: JSON.stringify({ name }) },
  );
  return {
    restoredFrom: data.restored_from ?? name,
    safetyBackup: data.safety_backup ?? null,
    safetyNote: data.safety_note ?? "",
    forgottenAgain: data.forgotten_again ?? 0,
  };
}

// ---------------------------------------------------------------------------
// Writing and publishing (cycle 2, R6)
// ---------------------------------------------------------------------------

/** A due post on Today, with the note the scheduler leaves when it was missed. */
export interface TodayDuePost {
  post_id: string;
  scheduled_for: string;
  content: string;
  excerpt: string;
  /** Present when the post was missed while the studio was closed or asleep. */
  missed?: { scheduled_for: string; noticed_at: string | null; late_minutes: number | null } | null;
  /** How late it was when the studio marked it due, and by which rule (the Queue's list only). */
  dispatch?: QueueDispatch | null;
}

/**
 * Queues a due post again at the next free slot, on the creator's word.
 *
 * The scheduler never moves a post by itself: a post missed while the machine
 * slept stays due at its own time until the creator chooses this.
 */
export async function moveToNextSlot(postId: string): Promise<{ scheduled_for: string; message: string }> {
  return call<{ scheduled_for: string; message: string }>(
    `/api/posts/${encodeURIComponent(postId)}/move-to-next-slot`,
    { method: "POST" },
  );
}

/** A draft in the drafts list. `created_at` is when it was first saved, in UTC. */
export interface DraftSummary {
  id: string;
  content: string;
  created_at: string | null;
}

/** Every draft, newest first. */
export async function fetchDrafts(): Promise<DraftSummary[]> {
  const data = await call<{ posts?: PostRow[] }>("/api/posts?status=draft");
  return (data.posts ?? [])
    .map((row) => ({ id: row.id, content: row.content ?? "", created_at: row.created_at ?? null }))
    .sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""));
}

/** Deletes a draft. The server refuses a post that has gone out, and answers 404 for nothing. */
export async function deleteDraft(id: string): Promise<void> {
  await call(`/api/posts/${encodeURIComponent(id)}`, { method: "DELETE" });
}

/** One earlier send of a post to LinkedIn: what was sent, and LinkedIn's answer. */
export interface LinkedInSendRecord {
  at: string;
  account: string | null;
  author_urn: string | null;
  scheduled_for: string;
  outcome: "accepted" | "refused_by_linkedin" | "no_answer" | "failed_to_reach" | "not_sent";
  http_status: number | null;
  linkedin_answer: string | null;
  message: string | null;
  scheduled_urn: string | null;
}

/** Whether Send to LinkedIn can work for a post now, as which account, and its earlier sends. */
export interface LinkedInSendState {
  ready: boolean;
  /**
   * Why not: not_first_profile (decision D9: sending works in the first
   * creator profile only, and the reason is the sentence that says why),
   * no_session, no_identity, account_unknown, other_account, author_unknown,
   * egress_off or risk_not_acknowledged. The last one is the one-time
   * acknowledgement of the account risk, kept in the profile's own settings,
   * and the only one the dialog can settle itself, with
   * acknowledgeLinkedInRisk below.
   */
  code: string | null;
  reason: string | null;
  account: { vanity: string; name: string | null; profile_url: string; member_urn_known: boolean } | null;
  egress_allowed: boolean;
  sends: LinkedInSendRecord[];
}

/** Reads this machine only: the saved session's account, and the send record for the post. */
export async function fetchLinkedInSend(postId: string): Promise<LinkedInSendState> {
  return call<LinkedInSendState>(`/api/v1/posts/${encodeURIComponent(postId)}/linkedin-send`);
}

/**
 * Records this installation's one-time acknowledgement of the Send to LinkedIn
 * account risk: that it writes to LinkedIn's private scheduling API, outside
 * LinkedIn's published terms.
 *
 * Asked once per installation, never per send. The per-send confirmation in
 * the Publish dialog is separate and still happens every time: it names the
 * account and the time, which is not the same thing as naming the risk.
 */
export async function acknowledgeLinkedInRisk(): Promise<{ acknowledged: boolean; at: string }> {
  return call<{ acknowledged: boolean; at: string }>("/api/v1/linkedin/risk-ack", {
    method: "POST",
    body: JSON.stringify({ acknowledge: true }),
  });
}

/** A weekly slot as the creator sets it: a day (0 is Monday), a local time and an optional name. */
export interface SlotChange {
  day_of_week?: number;
  time_slot?: string;
  label?: string;
}

/** Adds a weekly slot. With no name it is called after its day and part of the day. */
export async function addQueueSlot(slot: SlotChange): Promise<QueueSlot> {
  const data = await call<{ slot: QueueSlot }>("/api/queue/slots", { method: "POST", body: JSON.stringify(slot) });
  return data.slot;
}

/** Changes a weekly slot's day, time or name. Posts already queued keep their times. */
export async function updateQueueSlot(id: number, change: SlotChange): Promise<QueueSlot> {
  const data = await call<{ slot: QueueSlot }>(`/api/queue/slots/${id}`, {
    method: "PUT",
    body: JSON.stringify(change),
  });
  return data.slot;
}

/** Removes a weekly slot. Posts already queued for it keep their times. */
export async function deleteQueueSlot(id: number): Promise<void> {
  await call(`/api/queue/slots/${id}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Image provider (R7): who makes the image when you press Generate
// ---------------------------------------------------------------------------

/** What leaves this machine with one image provider, in the server's words. */
export interface ImageDisclosure {
  sends: string;
  to: string;
  account: string;
  leaves: boolean;
}

export interface ImageProviderOption {
  id: string;
  name: string;
  kind: "public" | "cloud" | "local" | "off";
  needs_key: boolean;
  needs_url: boolean;
  default_url: string;
  default_model: string;
  models: string[];
  key_hint: string;
  /** What a model needs or costs, said beside the model field. */
  model_notes: Record<string, string>;
  checks: boolean;
  shares_ai_key: boolean;
  disclosure: ImageDisclosure;
}

export interface ImageProviderConfig {
  provider: string;
  name: string;
  kind: string;
  model: string;
  base_url: string;
  /** "chosen" here, taken from the "ai_provider", or the "default". */
  source: string;
  has_key: boolean;
  api_key_masked: string;
  key_from: string;
  verified_at: string;
  check: string;
  ready: boolean;
  not_ready: string | null;
  disclosure: ImageDisclosure;
}

export interface ImageProviderState {
  config: ImageProviderConfig;
  providers: ImageProviderOption[];
  ai_provider: string | null;
  image_egress_allowed: boolean;
}

export async function fetchImageProvider(): Promise<ImageProviderState> {
  return call<ImageProviderState>("/api/image/provider");
}

/** Checks the setup without making an image and saves it; throws the reason when it fails. */
export async function saveImageProvider(setup: {
  provider: string;
  api_key?: string;
  model?: string;
  base_url?: string;
}): Promise<{ message: string; models: string[]; config: ImageProviderConfig }> {
  return call("/api/image/provider", { method: "POST", body: JSON.stringify(setup) });
}

// ---------------------------------------------------------------------------
// Captures the extension is holding (T5: surfaced on Today, was endpoint only)
// ---------------------------------------------------------------------------

/** The backup schedule on its own, as /api/v1/storage/backups answers it. */
export type BackupSchedule = StorageOverview["backups"];

/**
 * Whether the backup schedule is still producing backups, and the newest one.
 *
 * The same block the Storage and privacy panel reads inside its overview,
 * answered on its own: the overview measures every table on the way, which
 * is 578 ms on a three year install against 1.7 ms for this, and Today says
 * when the schedule has gone stale.
 */
export async function fetchBackupSchedule(): Promise<BackupSchedule> {
  return call<BackupSchedule>("/api/v1/storage/backups");
}

export interface WaitingCaptures {
  /** Null while the extension has not reported since the studio started. */
  waiting: number | null;
  measured: boolean;
  oldest_at: string | null;
  reported_at: string | null;
  message: string | null;
  refusals: { refusals: Record<string, number>; total: number; since: string };
}

/**
 * How many captures the extension is holding for a studio that was busy, as
 * the extension last said. This was readable only by calling the endpoint
 * directly; nothing in the interface showed it.
 */
export async function fetchWaitingCaptures(): Promise<WaitingCaptures> {
  return call<WaitingCaptures>("/api/v1/extension/captures/waiting");
}

/**
 * Removes the opt-in engineering creator pack from the hook library, or adds
 * it back.
 *
 * The Swipe File was its only screen and is gone, so the hook rail is the one
 * caller: it offers the way out while pack forms are in the library, and
 * nothing offers the way in until those 36 first-person claims are rewritten.
 */
export async function setEngineeringPack(enabled: boolean): Promise<{ added?: number; removed?: number }> {
  return call<{ added?: number; removed?: number }>("/api/v1/intelligence/packs/engineering", {
    method: "POST",
    body: JSON.stringify({ enabled }),
  });
}

/** How many drafts are waiting, and the newest of them. */
export interface DraftsWaiting {
  /** Null when the studio answered without a count, so no number is printed. */
  total: number | null;
  newest: DraftSummary | null;
}

/**
 * How many drafts are waiting, and the newest, for the Queue's one action.
 *
 * One row and the count beside it. The Queue listed the newest eight here
 * while the Composer's Drafts lists every one (decision 6: a count, with one
 * action); fetchDrafts answers with every draft, 259 KB on a three year
 * install, which only the drafts panel and its search need.
 */
export async function fetchDraftsWaiting(): Promise<DraftsWaiting> {
  const data = await call<{ posts?: PostRow[]; total?: number }>("/api/posts?status=draft&limit=1");
  const rows = data.posts ?? [];
  const newest = rows[rows.length - 1];
  return {
    total: typeof data.total === "number" ? data.total : null,
    newest: newest ? { id: newest.id, content: newest.content ?? "", created_at: newest.created_at ?? null } : null,
  };
}

// ---------------------------------------------------------------------------
// From your record (cycle 4, track 7)
// ---------------------------------------------------------------------------

/** The six provenance labels, and the explicit abstention. Defined once, in record_cards.py. */
export type RecordLabel = "measured" | "derived" | "typed" | "suggested" | "retrieved" | "curated" | "abstained";

/** A figure on a card, with the row it was read from and when. */
export interface RecordFigure {
  name: string;
  value: number;
  table: string;
  id: string | null;
  observed_at: string | null;
  source: string;
}

/** One of the creator's own posts that shares an ask's words. */
export interface RecordMatch {
  activity_urn: string;
  excerpt: string;
  date: string | null;
  url: string | null;
}

export interface RecordCardPayload {
  title?: string;
  badge?: string;
  excerpt?: string;
  date?: string | null;
  url?: string | null;
  figures?: RecordFigure[];
  figure_sentence?: string;
  because?: string;
  source_sentence?: string;
  method_sentence?: string;
  draft_text?: string;
  /** An abstention's sentence: what is missing and what will fill it. */
  sentence?: string;
  block_label?: string;
  matches?: RecordMatch[];
  counts?: Record<string, number | null>;
  topic?: string | null;
  /** The provider that wrote a suggested card, when one did. */
  provider?: string | null;
  /** A suggested card's angle, the model's own reason, and the words it quoted from your post. */
  angle?: string;
  model_why?: string;
  quote?: string;
  /** The section of the studio's playbook that shares an ask's words: its heading and its document in Docs. */
  playbook?: { document_id: string; section: string } | null;
  /** On the Monday card: last week's cards and the marks on them, as counts, in a sentence. */
  record_week?: { shown: number; kept: number; skipped: number; hidden: number; drafted: number; posted: number; sentence: string };
}

export interface RecordCard {
  day: string;
  card_id: string;
  slot: number;
  block: string;
  kind: string;
  label: RecordLabel;
  method: string;
  status: "shown" | "abstained" | "dropped" | "replaced";
  payload: RecordCardPayload;
  provenance: Record<string, unknown>;
  marks?: string[];
  kept_day?: string;
  kept_at?: string;
}

export interface RecordRun {
  day: string;
  finished_at: string | null;
  seed: number | null;
  rerolled_at: string | null;
  model_status: string | null;
  model_note: string | null;
  dropped_cards: number;
  note: string | null;
  carried_from: string | null;
  estimated_cost_usd: number | null;
  price_date: string | null;
}

/** What the model stage can do today, said as the screen says it. */
export interface RecordModelState {
  configured: boolean;
  allowed: boolean;
  stage: "on" | "off";
  status: string;
  should_run: boolean;
  provider: string | null;
  provider_label: string | null;
  statement: string | null;
  ceiling_usd: number;
  spent_today_usd: number | null;
  price_date: string | null;
  price_basis: string | null;
  priced: boolean;
  model: string | null;
  reason: string | null;
}

export interface RecordToday {
  day: string;
  batch_day: string | null;
  computed: string;
  nothing_new: string | null;
  run: RecordRun | null;
  cards: RecordCard[];
  days: string[];
  model?: RecordModelState;
}

export async function fetchRecord(): Promise<RecordToday> {
  return call<RecordToday>("/api/v1/record");
}

export async function fetchRecordDay(day: string): Promise<{ day: string; run: RecordRun | null; cards: RecordCard[] }> {
  return call(`/api/v1/record/days/${encodeURIComponent(day)}`);
}

export async function rerollRecord(): Promise<void> {
  await call("/api/v1/record/reroll", { method: "POST" });
}

export type RecordMark = "keep" | "skip" | "hide";

export async function markRecordCard(day: string, cardId: string, mark: RecordMark): Promise<{ message: string }> {
  return call("/api/v1/record/marks", { method: "POST", body: JSON.stringify({ day, card_id: cardId, mark }) });
}

export async function unmarkRecordCard(day: string, cardId: string, mark: RecordMark): Promise<{ message: string }> {
  return call("/api/v1/record/marks/remove", { method: "POST", body: JSON.stringify({ day, card_id: cardId, mark }) });
}

export async function unhideAllRecord(): Promise<{ cards: number; message: string }> {
  return call("/api/v1/record/unhide-all", { method: "POST" });
}

/** More of this: the card's topic becomes an ask. */
export async function moreOfThis(day: string, cardId: string): Promise<{ text: string; message: string }> {
  return call("/api/v1/record/more", { method: "POST", body: JSON.stringify({ day, card_id: cardId }) });
}

/** Draft from this: a Composer draft that records the card it came from. */
export async function draftFromCard(day: string, cardId: string): Promise<{ id: string; content: string }> {
  return call("/api/v1/record/draft", { method: "POST", body: JSON.stringify({ day, card_id: cardId }) });
}

export async function fetchKept(): Promise<RecordCard[]> {
  const data = await call<{ kept?: RecordCard[] }>("/api/v1/record/kept");
  return data.kept ?? [];
}

export interface RecordAsk {
  id: number;
  text: string;
  source: string;
  field: string | null;
  status: "open" | "kept" | "retired";
  created_at: string;
  updated_at: string;
  last_used_at: string | null;
}

export interface RecordSettings {
  keep_days: string;
  keep_days_options: string[];
  model_stage: "on" | "off";
  cost_ceiling_usd: number;
  cost_ceiling_default_usd: number;
}

export interface RecordKnows {
  asks: RecordAsk[];
  setup: Record<string, string | null>;
  marks: Record<string, number>;
  hidden: { day: string; card_id: string; at: string; kind: string | null; title: string | null; excerpt: string | null }[];
  archive: Record<string, number>;
  batches: { days: number; first: string | null; last: string | null };
  prune: { keep: string; days: number; cards: number; older_than?: string };
  notes: { month: string; text: string; at: string }[];
  settings: RecordSettings;
  job: {
    checked: string;
    today: string;
    today_built: boolean;
    last_run: { day: string; finished_at: string | null; note: string | null; carried_from: string | null } | null;
  };
  library?: RecordLibraryState;
  model?: RecordModelState;
}

export interface RecordLibraryState {
  version: string | null;
  signed_at: string | null;
  key_id: string | null;
  entries: number;
  fetched_at: string | null;
  source: string;
  address: string;
  contains: string;
  sends: string;
  keys: string[];
}

export async function fetchRecordKnows(): Promise<RecordKnows> {
  return call<RecordKnows>("/api/v1/record/knows");
}

/** An ask typed into the section's box, or a Composer instruction the creator ticked to remember. */
export async function addRecordAsk(text: string, source: "ask_box" | "composer"): Promise<{ message: string }> {
  return call("/api/v1/record/asks", { method: "POST", body: JSON.stringify({ text, source }) });
}

export async function updateRecordAsk(id: number, changes: { text?: string; status?: string }): Promise<void> {
  await call(`/api/v1/record/asks/${id}`, { method: "PUT", body: JSON.stringify(changes) });
}

export async function removeRecordAsk(id: number): Promise<void> {
  await call(`/api/v1/record/asks/${id}`, { method: "DELETE" });
}

export type RecordSetupField = "topics" | "audience" | "avoid";

// -------------------------------------------------------------
// Your collection: what the creator sent their Telegram bot
// -------------------------------------------------------------

export type CollectionKind = "note" | "idea" | "forward" | "post" | "link" | "bookmark" | "photo" | "voice";
export type CollectionStatus = "new" | "used" | "not_now";

/** One thing sent to the bot: its words, what it is, and what it became. */
export interface CollectionItem {
  id: number;
  received_at: string;
  kind: CollectionKind;
  /** The kind as the box says it: Note, Idea, Forwarded, Your post, Link, Bookmark. */
  kind_said: string;
  /** The creator's own words; a forward's text, never its origin. */
  text: string;
  /** A post's address rebuilt from its id, or a short link; never another person's slug. */
  link: string | null;
  tags: string[];
  topic: string | null;
  status: CollectionStatus;
  source: "telegram" | "studio";
  /** A draft, and where it is now; the request on Today, and its state; a photo in the media library; or null. */
  became: { kind: "draft" | "request" | "media"; said: string; post_id?: string } | null;
  /** A photo or a voice note as it was sent, kept in the profile's assets folder; never read. */
  media: CollectionMedia | null;
  /** Opening lines Angles found for it, kept for the box and the bot. */
  angles: string[];
}

export interface CollectionListing {
  items: CollectionItem[];
  counts: Record<CollectionStatus | "all", number>;
}

export async function fetchCollection(
  options: { status?: CollectionStatus | "all"; kind?: CollectionKind | ""; q?: string } = {},
): Promise<CollectionListing> {
  const params = new URLSearchParams();
  params.set("status", options.status ?? "new");
  if (options.kind) params.set("kind", options.kind);
  if (options.q?.trim()) params.set("q", options.q.trim());
  return call<CollectionListing>(`/api/v1/collection?${params.toString()}`);
}

export async function setCollectionStatus(id: number, status: "new" | "not_now"): Promise<void> {
  await call(`/api/v1/collection/${id}/status`, { method: "POST", body: JSON.stringify({ status }) });
}

/** Use as a draft: the item's words, as they are, as a Composer draft. */
export async function draftFromCollection(id: number): Promise<{ id: string; content: string }> {
  return call<{ id: string; content: string }>(`/api/v1/collection/${id}/draft`, { method: "POST" });
}

export async function removeCollectionItem(id: number): Promise<void> {
  await call(`/api/v1/collection/${id}`, { method: "DELETE" });
}

/** A photo or a voice note sent to the bot, as the studio keeps it. */
export interface CollectionMedia {
  /** Served by the studio, under /assets/phone/. */
  path: string;
  mime: string;
  bytes: number;
  width?: number;
  height?: number;
  /** A voice note's length, in seconds. */
  duration?: number;
}

/** A photo from the phone, copied into the media library, where a post's images are kept. */
export async function photoToMediaLibrary(id: number): Promise<CollectionItem> {
  const data = await call<{ item: CollectionItem }>(`/api/v1/collection/${id}/media`, { method: "POST" });
  return data.item;
}

/** What writing from the collection made, or why nothing was written. */
export type CollectionWritten =
  | { status: "drafted"; id: string; content: string; items: number[] }
  | { status: "no_provider" | "refused"; said: string };

/** Make a post (one item) or Combine (several), through the creator's own provider. */
export async function writeFromCollection(items: number[], angle?: string): Promise<CollectionWritten> {
  return call<CollectionWritten>("/api/v1/collection/write", {
    method: "POST",
    body: JSON.stringify(angle ? { items, angle } : { items }),
  });
}

/** Angles: the creator's number of opening lines for a post from one item. */
export async function anglesForItem(
  id: number,
): Promise<{ status: "success"; angles: string[] } | { status: "no_provider" | "refused"; said: string }> {
  return call(`/api/v1/collection/${id}/angles`, { method: "POST" });
}

// -------------------------------------------------------------
// How the studio writes for you: the writing preferences (phase 3)
// -------------------------------------------------------------

export type IdeaSource = "collection" | "posts" | "asks";

export interface WritingPreferences {
  length_words: number;
  tone: string;
  /** Empty for the language of what you wrote. */
  language: string;
  /** Empty for a first line that stops the scroll, or one of Re-Hook's forms. */
  opening: string;
  emojis: string;
  hashtags: string;
  line_breaks: string;
  ending: string;
  avoid: string[];
  angles: number;
  sources: IdeaSource[];
  /** Which things to remember go with writing: all, chosen (the ticked ones) or off. */
  memory: "all" | "chosen" | "off";
  /** How many ideas the daily model stage asks your provider for. */
  ideas: number;
  /** The rewrite buttons under a draft the bot wrote (phase 4): each a label and what it asks for. */
  reshapes: ReshapeButton[];
}

/** One rewrite button: its label on the phone, and what it asks the writer for, in the creator's words. */
export interface ReshapeButton {
  label: string;
  asks: string;
}

export interface WritingDescribed {
  values: WritingPreferences;
  defaults: WritingPreferences;
  choices: {
    length_words: number[];
    angles: number[];
    opening: string[];
    emojis: Record<string, string>;
    hashtags: Record<string, string>;
    line_breaks: Record<string, string>;
    ending: Record<string, string>;
    sources: IdeaSource[];
    memory: string[];
    ideas: number[];
  };
  labels: {
    emojis: Record<string, string>;
    hashtags: Record<string, string>;
    line_breaks: Record<string, string>;
    ending: Record<string, string>;
    sources: Record<IdeaSource, string>;
    memory: Record<string, string>;
    language: string;
    opening: string;
  };
  limits: {
    tone: number;
    language: number;
    avoid: number;
    avoid_phrase: number;
    reshapes: number;
    reshape_label: number;
    reshape_asks: number;
  };
  /** The provider every writing request goes to, as connected on the Composer's Prompt tab. */
  provider: { configured: boolean; provider: string | null; model: string | null };
}

export async function fetchWritingPreferences(): Promise<WritingDescribed> {
  return call<WritingDescribed>("/api/v1/writing/preferences");
}

/** The Composer's "From your collection": new items whose words the draft shares, matched locally. */
export async function fetchRelatedFromCollection(text: string): Promise<CollectionItem[]> {
  const data = await call<{ items?: CollectionItem[] }>("/api/v1/collection/related", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
  return data.items ?? [];
}

/** Add to the draft: the item's words went into this draft, so it is used. */
export async function markCollectionUsed(id: number, postId: string): Promise<void> {
  await call(`/api/v1/collection/${id}/used`, { method: "POST", body: JSON.stringify({ post_id: postId }) });
}

/** What a draft the studio wrote was written from, and with which things to remember, by id. */
export interface MadeWith {
  items: number[];
  remembered: number[];
  angle?: boolean;
  provider?: string;
  model?: string;
  at?: string;
  /** The texts the bot's rewrites replaced, the newest last, each with the button that replaced it (phase 4). */
  earlier?: { text: string; at: string; by: string }[];
}

/** A draft's own record of how it was made, or null for one written by hand. */
export async function fetchMadeWith(postId: string): Promise<MadeWith | null> {
  const data = await call<{ post?: { made_with?: string | null } }>(`/api/posts/${encodeURIComponent(postId)}`);
  const raw = data.post?.made_with;
  if (!raw) return null;
  try {
    return JSON.parse(raw) as MadeWith;
  } catch {
    return null;
  }
}

export type RememberedAbout = "you" | "audience" | "offer" | "date";

/** A thing to remember: a fact the creator told the studio. */
export interface RememberedFact {
  id: number;
  text: string;
  about: RememberedAbout;
  about_said: string;
  /** Goes with writing while only the ticked ones go. */
  in_use: boolean;
  source: "studio" | "telegram";
  used_count: number;
  last_used_at: string | null;
}

export async function fetchRemembered(): Promise<{ facts: RememberedFact[]; mode: string; about: Record<RememberedAbout, string> }> {
  return call("/api/v1/remembered");
}

export async function addRemembered(text: string, about: RememberedAbout): Promise<RememberedFact> {
  const data = await call<{ fact: RememberedFact }>("/api/v1/remembered", {
    method: "POST",
    body: JSON.stringify({ text, about }),
  });
  return data.fact;
}

export async function updateRemembered(
  id: number,
  change: { text?: string; about?: RememberedAbout; in_use?: boolean },
): Promise<void> {
  await call(`/api/v1/remembered/${id}`, { method: "PUT", body: JSON.stringify(change) });
}

export async function removeRemembered(id: number): Promise<void> {
  await call(`/api/v1/remembered/${id}`, { method: "DELETE" });
}

/** Saves the preferences sent; one left out keeps its value. Outside its choices, nothing is saved. */
export async function saveWritingPreferences(change: Partial<WritingPreferences>): Promise<WritingDescribed> {
  return call<WritingDescribed>("/api/v1/writing/preferences", { method: "PUT", body: JSON.stringify(change) });
}

export async function fetchRecordSetup(): Promise<Record<RecordSetupField, string | null>> {
  const data = await call<{ fields: Record<RecordSetupField, string | null> }>("/api/v1/record/setup");
  return data.fields;
}

export async function setRecordSetupField(field: RecordSetupField, text: string): Promise<void> {
  await call(`/api/v1/record/setup/${field}`, { method: "PUT", body: JSON.stringify({ text }) });
}

export async function setRecordSettings(changes: Partial<Pick<RecordSettings, "keep_days" | "model_stage" | "cost_ceiling_usd">>): Promise<RecordSettings> {
  return call("/api/v1/record/settings", { method: "PUT", body: JSON.stringify({ changes }) });
}

export async function saveRecordNote(month: string, text: string): Promise<void> {
  await call("/api/v1/record/notes", { method: "POST", body: JSON.stringify({ month, text }) });
}

/**
 * The creator opened From your record: today's one call to their own model,
 * if it has not run and may. Answers at once; the idea arrives into today's
 * batch when the model has answered, so read the batch again after.
 */
export async function runRecordModel(): Promise<{ status: string; reason?: string }> {
  return call("/api/v1/record/model", { method: "POST" });
}

/** Exactly what the next call to the creator's model would send. Sends nothing. */
export interface RecordModelPreview {
  provider: string;
  model: string;
  system: string;
  prompt: string;
  posts: number;
  asks: number;
}

export async function fetchRecordModelPreview(): Promise<RecordModelPreview> {
  return call<RecordModelPreview>("/api/v1/record/model/preview");
}

/** A share under the studio's sample rules: the counts always, a rate only at 20 or more. */
export interface RecordShare {
  part: number;
  whole: number;
  said: string;
  rate: number | null;
}

export interface RecordFunnelRow {
  name: string;
  shown: number;
  kept: RecordShare;
  drafted: RecordShare;
  posted: RecordShare;
}

export interface RecordEvaluation {
  funnel: { by_kind: RecordFunnelRow[]; by_label: RecordFunnelRow[]; total: RecordFunnelRow | null; note: string };
  comparison: { sentence: string; verdict: string; n_with: number; n_without: number; window_days: number };
  months: { month: string; template: "A" | "B" | "C"; sentence: string }[];
  notes: Record<string, string>;
  this_month: string;
}

export async function fetchRecordEvaluation(): Promise<RecordEvaluation> {
  return call<RecordEvaluation>("/api/v1/record/evaluation");
}

/** From your record on Today: today's cards, one line each, once today's batch exists. */
export interface RecordLines {
  day: string;
  built: boolean;
  computed_at?: string | null;
  not_yet: number;
  lines: { slot: number; card_id: string; label: string; block_label: string | null; title: string | null; line: string }[];
}

export async function fetchRecordLines(): Promise<RecordLines> {
  return call<RecordLines>("/api/v1/record/lines");
}

/** From your record on Health: each part as the studio holds it, with its sentence. */
export interface RecordHealth {
  job: { today_built: boolean; carried_from: string | null; sentence: string; checked: string };
  model: { configured: boolean; stage: string; spent_today_usd: number | null; ceiling_usd: number; sentence: string };
  library: { state: "none" | "verified" | "key_not_held"; entries: number; sentence: string };
}

export async function fetchRecordHealth(): Promise<RecordHealth> {
  return call<RecordHealth>("/api/v1/record/health");
}

/** The creator pressed Fetch: one request for the signed Inox library, carrying nothing of theirs. */
export async function fetchLibraryBundle(): Promise<{ status: string; message: string }> {
  return call("/api/v1/record/library/fetch", { method: "POST" });
}

/** A signed library file chosen by hand, verified exactly as a fetched one is. */
export async function importLibraryBundle(text: string): Promise<{ status: string; message: string }> {
  return call("/api/v1/record/library/import", { method: "POST", body: JSON.stringify({ text }) });
}

// -------------------------------------------------------------
// Your phone, through Telegram: the settings behind Local security
// -------------------------------------------------------------

/** A chat the bot refused since it was set, kept by the studio in memory only, for "Is that you?". */
export interface RefusedChat {
  chat_id: string;
  count: number;
  first_at: string;
  last_at: string;
  /** The first characters of the first message refused from this chat. */
  first: string;
  /** Your own chat with a bot is a positive number; a group's can never be saved. */
  own_chat: boolean;
}

/** The bot's switches, each kept in the profile the bot belongs to. */
export interface IngressOptions {
  /** The bot confirms each message with a short fixed sentence. On unless turned off. */
  replies: boolean;
  /** The bot may answer /today with your own figures. Off unless turned on. */
  figures: boolean;
  /** Tell the paired chat when a queued post is due: a count. Off unless turned on. */
  notify_due: boolean;
  /** Send the latest post's figures at about 24 hours, once. Off unless turned on. */
  notify_24h: boolean;
  /** Notifications wait during quiet hours and go when they end. On unless turned off. */
  quiet_hours: boolean;
  /** Quiet hours, whole hours on the computer's clock: from 23 to 7 unless changed. */
  quiet_from: number;
  quiet_to: number;
  /** The bot's answers carry what it writes from the collection (its words). Off unless turned on. */
  collection_words: boolean;
  /** An idea from the collection each morning, on these days (0 is Monday) at this hour. Off unless turned on. */
  morning: boolean;
  morning_days: number[];
  morning_hour: number;
  /** The angles button's number, set in Brand under Writing; shown here. */
  angles?: number;
  /** Send a weekly summary to the paired chat. Off unless turned on. */
  weekly: boolean;
  /** The weekly summary's day, 0 is Monday, and its whole hour on the computer's clock: Monday 09:00 unless changed. */
  weekly_day: number;
  weekly_hour: number;
}

export interface IngressSettings {
  profile: string;
  /** Both the token and the chat id are set, so the studio asks Telegram for messages. */
  configured: boolean;
  /** A token and no chat id yet: every message is refused, and the chats that wrote are listed to pair one. */
  pairing: boolean;
  /** Whether a token is held. The token itself is sealed and never answered. */
  has_token: boolean;
  chat_id: string;
  /** The studio is asking Telegram for this profile's messages. */
  running: boolean;
  /** One bot is asked at a time, and the one being asked was set up in another profile. */
  running_for_another_profile: boolean;
  configured_from: "settings" | "environment" | null;
  last_poll_at: string | null;
  last_error: string | null;
  total_messages_processed: number;
  /** Posts the phone asked the desk to read that have not been read yet. */
  open_requests: number;
  /** The newest links from the phone, newest first, each with what became of it in a sentence. */
  recent_links: {
    id: number;
    /** Empty for a short link whose post is not known yet. */
    activity_urn: string;
    /** The lnkd.in short link the phone sent, or null for a full post link. */
    link: string | null;
    asked_at: string;
    done_at: string | null;
    state: "open" | "read" | "expired" | "dismissed" | "done" | "refused";
    said: string;
  }[];
  /** The chats this profile's bot refused, newest first; This is me saves one. */
  refused_chats: RefusedChat[];
  /** A message from the chat saved here has been saved on this computer. */
  tested_against_real_service: boolean;
  /** The server's own sentence until then; null once a message from your chat has been saved. */
  not_yet_tested: string | null;
  options: IngressOptions;
  /** Quiet hours are on and it is now inside them: the bot's notifications wait. */
  quiet_now: boolean;
  /** When the next weekly summary goes, on this computer's clock, such as "Mon 02 Nov, 09:00"; null while it is off. */
  weekly_next: string | null;
  /** Why the bot's last message to Telegram did not go, in plain words; null when it went. */
  last_send_error: string | null;
  replies_waiting: number;
  /** The last time Telegram answered the studio's check for messages; null before the first. */
  last_check_at: string | null;
  /**
   * A day the studio did not check Telegram (phase 4): when it last checked,
   * when it checked again, the moment a day before that, and the server's own
   * words for it. Shown until Got it; null when there is none.
   */
  gap: { from: string; to: string; since: string; said: string } | null;
  /** Telegram holds the bot's "/" menu for the paired chat, as the commands are now (phase 4). */
  menu: boolean;
}

export async function fetchIngressSettings(): Promise<IngressSettings> {
  return call<IngressSettings>("/api/v1/ingress/settings");
}

/**
 * Both empty removes the bot and stops asking Telegram. An empty field keeps
 * what is held: a token alone starts pairing, and a chat id alone (This is
 * me) pairs that chat with the token already saved.
 */
/** One fixed sentence to the paired chat, now: whether Telegram took it, and why not in plain words. */
export async function sendIngressTestMessage(): Promise<{ sent: boolean; said: string }> {
  const data = await call<{ sent?: boolean; said?: string }>("/api/v1/ingress/test-message", { method: "POST" });
  return { sent: !!data.sent, said: data.said ?? "" };
}

/** Got it, under the notice of a day the studio did not check Telegram: the panel stops showing it. */
export async function seeIngressGap(): Promise<IngressSettings> {
  return call<IngressSettings>("/api/v1/ingress/gap/seen", { method: "POST" });
}

/** Saves the switches sent; a switch left out keeps its value. */
export async function saveIngressOptions(options: Partial<IngressOptions>): Promise<IngressSettings> {
  return call<IngressSettings>("/api/v1/ingress/options", { method: "POST", body: JSON.stringify(options) });
}

export async function saveIngressSettings(bot_token: string, chat_id: string): Promise<IngressSettings> {
  return call<IngressSettings>("/api/v1/ingress/settings", {
    method: "POST",
    body: JSON.stringify({ bot_token, chat_id }),
  });
}

// -------------------------------------------------------------
// LinkedIn's analytics export: request, find, preview, import
// -------------------------------------------------------------

export interface FoundExport {
  name: string;
  path: string;
  bytes: number;
  modified: string;
  downloading: boolean;
  imported?: boolean;
}

export interface ExportRange {
  start: string | null;
  end: string | null;
  /** What the range was read from: the file's name, the days in it, or nothing. */
  from: string | null;
}

/** One sheet of the export, as the studio recognised it or did not. */
export interface ExportSheet {
  name: string;
  /** Null when the studio does not recognise the sheet: it is listed, and nothing in it is imported. */
  kind: string | null;
  label: string;
  rows: number;
  importable: boolean;
  default: boolean;
  writes: string | null;
  recognised: string[];
  not_recognised: string[];
  left_out: string[];
  note: string | null;
  truncated: boolean;
}

export interface ExportPreview {
  source: string;
  file: { name: string; bytes: number };
  range: ExportRange;
  sheets: ExportSheet[];
  recognised: boolean;
  verified_against_real_file: boolean;
  /** The server's own sentence on whether the layout has been checked against a real export. */
  verification: string;
}

export interface ExportImport {
  file: string;
  imported_at: string;
  range: ExportRange;
  summary: Record<string, Record<string, unknown>>;
}

export interface ExportState {
  analytics_page: string;
  requested_at: string | null;
  waiting: boolean;
  /** Spreadsheets in Downloads named like LinkedIn's export; looked for only once you say you exported. */
  found: FoundExport[];
  watching: string[];
  last_import: ExportImport | null;
  verified_against_real_file: boolean;
  verification: string;
}

export async function fetchAnalyticsExportState(): Promise<ExportState> {
  return call<ExportState>("/api/v1/analytics-export");
}

export async function markAnalyticsExportRequested(): Promise<ExportState> {
  return call<ExportState>("/api/v1/analytics-export/requested", { method: "POST" });
}

export async function previewAnalyticsExport(source: string): Promise<ExportPreview> {
  return call<ExportPreview>("/api/v1/analytics-export/preview", { method: "POST", body: JSON.stringify({ source }) });
}

/**
 * Sends a chosen export to the studio on this machine, which keeps it until
 * it is imported. The browser's own record of when the file was written goes
 * with it, because that is when a post's own export was read.
 */
export async function uploadAnalyticsExport(file: File): Promise<ExportPreview> {
  const response = await studioFetch("/api/v1/analytics-export/upload", {
    method: "POST",
    headers: {
      "Content-Type": "application/octet-stream",
      "X-Export-Name": encodeURIComponent(file.name),
      "X-File-Modified": String(file.lastModified),
    },
    body: file,
  });
  if (!response.ok) throw await refusalFrom(response);
  return (await response.json()) as ExportPreview;
}

export async function importAnalyticsExport(
  source: string,
  include: string[],
): Promise<{ file: { name: string; bytes: number }; range: ExportRange; summary: ExportImport["summary"] }> {
  return call("/api/v1/analytics-export/import", { method: "POST", body: JSON.stringify({ source, include }) });
}

export async function discardAnalyticsExport(source: string): Promise<void> {
  await call("/api/v1/analytics-export/discard", { method: "POST", body: JSON.stringify({ source }) });
}

// ---------------------------------------------------------------------------
// Health: is the bridge reading, and what could it not read
//
// The section stands on routes that already existed (extension health, schema
// status, the backup schedule, the update preference) plus one new field, the
// run rows per reader, which capture_health read with LIMIT 1 and dropped.
// ---------------------------------------------------------------------------

/** One run of one reader on one page, as the extension reported it. */
export interface HealthReaderRun {
  observed_at: string;
  page_kind: string | null;
  items_seen: number | null;
  items_kept: number | null;
  /** Required fields the run could not read on a page that had them. */
  drift: string[];
  /** Why the studio refused this run, when it did. */
  refused: string | null;
  extension_version: string | null;
}

/** One reader's day: rolled up as each run lands, kept past the log's week. */
export interface HealthReaderDay {
  day: string;
  runs: number;
  /** Null while no run of the day measured it: an unmeasured day, not a day of zero. */
  items_seen: number | null;
  items_kept: number | null;
  drift_runs: number;
  first_run_at: string | null;
  last_run_at: string | null;
}

export interface HealthReader {
  extractor: string;
  label: string;
  state: CaptureHealth["state"];
  last_run_at: string | null;
  last_good_at: string | null;
  drift: string[];
  /** Why the studio refused the latest run, when it did ("identity"). */
  refused: string | null;
  /** Runs inside the window, and what they saw and kept: null when no run measured it. */
  runs: number;
  items_seen: number | null;
  items_kept: number | null;
  drift_runs: number;
  /** How many day rows the studio holds for this reader; the rows are one level down. */
  days_held: number;
}

/** One reader one level down: the newest runs in the window, and every day row kept. */
export interface HealthReaderDetail {
  extractor: string;
  label: string;
  window: { days: number; label: string; since: string };
  days_window: { days: number; label: string };
  runs: number;
  rows: HealthReaderRun[];
  days: HealthReaderDay[];
}

export interface HealthHeartbeats {
  window_days: number;
  label: string;
  count: number;
  first_seen_at: string | null;
  last_seen_at: string | null;
  versions: { extension_version: string | null; first_seen_at: string; last_seen_at: string; count: number }[];
  page_kinds: Record<string, number>;
  /** Null when fewer than two heartbeats were heard: no gap can be measured. */
  longest_silence_minutes: number | null;
  longest_silence_ended_at: string | null;
}

export interface HealthReaders {
  /** The capture log's window: "last 7 days", because the log is pruned to it. */
  window: { days: number; label: string; since: string };
  /** How long the day rows are kept. */
  days_window: { days: number; label: string };
  readers: HealthReader[];
  /** "Network reading was retired in 2.10.2: ...", only where network reading once ran; else null. */
  network_reading_retired: string | null;
  /** Every reader together, a row per day, newest first. */
  by_day: {
    days: number;
    label: string;
    /** The first day the studio kept; a day before it is "not_kept", never silence. */
    first_held: string | null;
    rows: {
      day: string;
      state: "read" | "nothing_read" | "not_kept";
      runs: number | null;
      items_seen: number | null;
      items_kept: number | null;
      drift_runs: number | null;
    }[];
  };
  heartbeats: HealthHeartbeats;
}

export async function fetchHealthReaders(): Promise<HealthReaders> {
  return call<HealthReaders>("/api/v1/bridge/readers");
}

export async function fetchHealthReader(extractor: string): Promise<HealthReaderDetail> {
  return call<HealthReaderDetail>(`/api/v1/bridge/readers/${encodeURIComponent(extractor)}`);
}

export interface ExtensionHealth {
  bridge: BridgeStatus;
  extractors: CaptureHealth[];
  contract: {
    contract_version: number;
    extension_contract_version: number | null;
    extension_version: string | null;
    last_seen_at: string | null;
    /** null when nothing the extension said is fresh enough to judge: not known, never "stale". */
    reload_required: boolean | null;
    message: string | null;
    /** The extension's files are newer than it, and it is reloading itself. */
    updating?: boolean;
    tabs_needing_reload?: number | null;
    tabs_message?: string | null;
  };
  waiting_captures: {
    waiting: number | null;
    measured: boolean;
    oldest_at: string | null;
    reported_at: string | null;
    message: string | null;
  };
  refusals: { refusals: Record<string, number>; total: number; since: string };
}

export async function fetchExtensionHealth(): Promise<ExtensionHealth> {
  return call<ExtensionHealth>("/api/v1/extension/health");
}

export interface SchemaStatus {
  current_version: number;
  target_version: number;
  pending: { version: number; description: string }[];
  up_to_date: boolean;
  too_new: boolean;
  app_version: string;
  advice: string;
}

export async function fetchSchemaStatus(): Promise<SchemaStatus> {
  return call<SchemaStatus>("/api/v1/schema/status");
}

/** The update preference, read without any network request being made. */
export interface UpdateStatus {
  current_version: string;
  /** Off by default; the one outbound request the product makes is never made while this is false. */
  enabled: boolean;
  asked: boolean;
  last_checked: string | null;
  last_seen_version: string | null;
  releases_url: string;
}

/** Your profile as LinkedIn last showed it (GET /api/v1/brand/profile). */
export interface BrandProfile {
  confirmed: boolean;
  profile: {
    vanity: string | null;
    name: string | null;
    headline: string | null;
    about: string | null;
    location: string | null;
    company: string | null;
    followers: number | null;
    connections: number | null;
    /** One read of your profile page writes these fields together. */
    read_at: string | null;
    confirmed_at: string | null;
  } | null;
  positions: { title: string | null; company: string | null; date_range: string | null; location: string | null; description: string | null; read_at: string | null }[];
  education: { school: string | null; degree: string | null; date_range: string | null; read_at: string | null }[];
  skills: { skill: string; read_at: string | null }[];
  /** Follower and connection counts on the days they were read. */
  audience: { date: string; followers: number | null; connections: number | null }[];
}

export async function fetchBrandProfile(): Promise<BrandProfile> {
  return call<BrandProfile>("/api/v1/brand/profile");
}

/** What Settings opens on (GET /api/v1/settings/overview). */
export interface SettingsOverview {
  backup: { enabled: boolean; last: { name: string; made_at: string; bytes: number; verified: boolean | null } | null; next_due: string | null; stale: boolean; never: boolean };
  cleanup: { runs: string; jobs: { job: string; state: "on" | "off" | "waiting for you"; rows: number | null }[] };
  egress: { total_performed: number; total_refused: number; master_off: boolean; since: string };
  licence: { status: string; tier_label: string; expires_at: string | null; updates_until: string | null };
  updates: { enabled: boolean; last_checked: string | null; last_seen_version: string | null; current_version: string };
  autostart: { supported: boolean; enabled: boolean; available: boolean; platform: string | null };
}

export async function fetchSettingsOverview(): Promise<SettingsOverview> {
  return call<SettingsOverview>("/api/v1/settings/overview");
}

/** Starts the studio with your computer, or stops doing so (POST /api/v1/desktop/autostart). */
export async function setAutostart(enabled: boolean): Promise<void> {
  await call("/api/v1/desktop/autostart", { method: "POST", body: JSON.stringify({ enabled }) });
}

/** The people you kept from the review, and when (GET /api/v1/storage/kept). */
export interface KeptPerson {
  lead_id: string;
  name: string | null;
  headline: string | null;
  kept_at: string;
}

export async function fetchKeptList(): Promise<KeptPerson[]> {
  const data = await call<{ kept?: KeptPerson[] }>("/api/v1/storage/kept");
  return data.kept ?? [];
}

export async function unkeepLead(leadId: string): Promise<number> {
  const data = await call<{ removed?: number }>(`/api/v1/storage/kept/${encodeURIComponent(leadId)}`, { method: "DELETE" });
  return data.removed ?? 0;
}

export async function fetchUpdateStatus(): Promise<UpdateStatus> {
  return call<UpdateStatus>("/api/v1/updates/status");
}

export async function setUpdatePreference(enabled: boolean): Promise<{ enabled: boolean; asked: boolean }> {
  return call("/api/v1/updates/preference", { method: "POST", body: JSON.stringify({ enabled }) });
}

export interface UpdateCheck {
  checked: boolean;
  enabled?: boolean;
  reason?: string;
  error?: string;
  latest_version?: string;
  update_available?: boolean;
  notes?: string;
  current_version?: string;
}

/** Performs the check only when the preference is on; nothing is downloaded or run. */
export async function runUpdateCheck(): Promise<UpdateCheck> {
  return call<UpdateCheck>("/api/v1/updates/check", { method: "POST", body: JSON.stringify({}) });
}

// ---------------------------------------------------------------------------
// Replies: every comment waiting on your posts, and your own Answered mark
//
// Whether you replied is not something the bridge reads, so "answered" is the
// mark you set. A comment's time is when the studio first saw it, never when
// it was written: LinkedIn's own time is not captured.
// ---------------------------------------------------------------------------

export interface ReplyComment {
  lead_id: string;
  post_urn: string;
  comment_key: string;
  comment_text: string | null;
  /** When the studio first saw the comment. Not when it was written. */
  seen_at: string;
  name: string;
  headline: string | null;
  /** When you marked it answered, or null. */
  marked_at: string | null;
}

export interface ReplyPostGroup {
  post_id: string;
  activity_urn: string;
  excerpt: string | null;
  published_at: string | null;
  /** Null for a post LinkedIn has not given the studio a link for. */
  url: string | null;
  /** In this view, on this post, across every page. */
  in_view: number;
  waiting: number;
  answered: number;
  comments: ReplyComment[];
}

export type RepliesView = "waiting" | "answered";

export interface RepliesPage {
  identity_known: boolean;
  view: RepliesView;
  window: { days: number; label: string; since: string };
  counts: { waiting: number; people: number; posts: number; answered_in_window: number; answered_last_7_days: number };
  /** "posts": a page of posts with their first few comments each; "comments": one post's comments. */
  unit: "posts" | "comments";
  post: string | null;
  per_post: number;
  offset: number;
  limit: number;
  total: number;
  next_offset: number | null;
  posts: ReplyPostGroup[];
}

/** A page of posts with their first comments, or with `post` that post's comments. */
export async function fetchReplies(
  days: number,
  view: RepliesView,
  offset = 0,
  options: { limit?: number; post?: string | null } = {},
): Promise<RepliesPage> {
  const query = new URLSearchParams({ days: String(days), view, offset: String(offset) });
  if (options.limit) query.set("limit", String(options.limit));
  if (options.post) query.set("post", options.post);
  return call<RepliesPage>(`/api/v1/replies?${query.toString()}`);
}

type CommentRef = Pick<ReplyComment, "lead_id" | "post_urn" | "comment_key">;

export async function markReplyAnswered(comment: CommentRef): Promise<{ marked_at: string }> {
  return call("/api/v1/replies/mark", {
    method: "POST",
    body: JSON.stringify({ lead_id: comment.lead_id, post_urn: comment.post_urn, comment_key: comment.comment_key }),
  });
}

export async function unmarkReplyAnswered(comment: CommentRef): Promise<{ removed: number }> {
  return call("/api/v1/replies/unmark", {
    method: "POST",
    body: JSON.stringify({ lead_id: comment.lead_id, post_urn: comment.post_urn, comment_key: comment.comment_key }),
  });
}

// ---------------------------------------------------------------------------
// Audience: the set of people the bridge has seen, ordered by facts
//
// Never by the ICP score. Every list says what it rests on: the posts whose
// engagers were read, the weeks the bridge read anything, the archive's date.
// ---------------------------------------------------------------------------

export interface AudiencePerson {
  lead_id: string;
  name: string | null;
  headline: string | null;
  /** Of your posts whose engagers were read. */
  posts_engaged: number;
  first_seen_at: string | null;
  latest_at: string | null;
}

export interface AudienceWeek {
  /** The Monday the week starts on (UTC). */
  week: string;
  /** Whether the bridge read any engagement that week; when not, new is null. */
  read: boolean;
  new: number | null;
}

export interface AudienceOverview {
  own_posts: number;
  repeat: { posts_read: number; label: string; min_posts: number; count: number; people: AudiencePerson[] };
  quiet: {
    judged: boolean;
    recent_posts: number;
    posts_read: number;
    /** Exactly what is measured: "not seen on your last 5 posts whose engagers were read". */
    label: string;
    count: number;
    people: AudiencePerson[];
  };
  new_people: { partial: boolean; label: string; weeks: AudienceWeek[] };
  connections: { count: number; as_of: string | null; leads_matched: number; leads_by_member_id: number };
}

export async function fetchAudience(): Promise<AudienceOverview> {
  return call<AudienceOverview>("/api/v1/audience");
}

export interface AudienceConnection {
  name: string | null;
  company: string | null;
  position: string | null;
  connected_on: string | null;
  as_of: string;
  profile_url: string;
  /** The lead this connection is, matched by profile; null when they are not one. */
  lead_id: string | null;
}

export interface AudienceConnections {
  q: string;
  total: number;
  as_of: string | null;
  offset: number;
  next_offset: number | null;
  connections: AudienceConnection[];
}

export async function fetchAudienceConnections(q: string, offset = 0): Promise<AudienceConnections> {
  const query = new URLSearchParams({ offset: String(offset) });
  if (q.trim()) query.set("q", q.trim());
  return call<AudienceConnections>(`/api/v1/audience/connections?${query.toString()}`);
}

export interface AudienceCounts {
  people: number;
  funnel: { status: string; label: string; people: number }[];
  companies: { company: string; people: number }[];
  companies_named: number;
  no_company: number;
}

export async function fetchAudienceCounts(): Promise<AudienceCounts> {
  return call<AudienceCounts>("/api/v1/audience/counts");
}

export interface AudiencePersonFacts {
  first_seen_at: string | null;
  last_seen_at: string | null;
  /** How many times the bridge read an engagement of theirs; null when it never did. */
  times_seen: number | null;
  engagements: number;
  connection: { connected_on: string | null; as_of: string } | null;
  connections_held: number;
  connections_as_of: string | null;
  /** The bridge read their link as a member number, which the archive's connections cannot be matched to. */
  member_id_only: boolean;
}

export async function fetchAudiencePerson(leadId: string): Promise<AudiencePersonFacts> {
  return call<AudiencePersonFacts>(`/api/v1/audience/people/${encodeURIComponent(leadId)}`);
}

/**
 * Per figure the post analytics reader added in cycle 4 (track 5): when one
 * of your post analytics pages last carried it, and how many such pages were
 * read since, in the sentence the studio writes for it. A figure LinkedIn
 * does not show on every post is not drift, so this is where one that never
 * appears shows.
 */
export interface PostFieldSightings {
  post_analytics_readings: number;
  fields: { field: string; label: string; last_read_at: string | null; readings_since: number; sentence: string }[];
  meaning: string;
}

export async function fetchPostFieldSightings(): Promise<PostFieldSightings> {
  return call<PostFieldSightings>("/api/analytics/post-field-sightings");
}


// ---------------------------------------------------------------------------
// The creator's own surfaces read in cycle 4 (track 5, phase 2): profile views
// and search appearances, articles and newsletters, and their own reposts.
// Every count keeps the window its page named; a figure a page did not show
// is null, which the screens say as "not read", never 0.
// ---------------------------------------------------------------------------

export interface AccountReading {
  date: string;
  value: number;
  /** The window the page named, such as "90d". */
  period_label: string;
  precision: string | null;
  /** The page it was read from: account_analytics, profile_views or search_appearances. */
  source: string;
  read_at: string;
  /** The window in words, from the route: "90 days", or "an unknown window". */
  covers: string;
  label: string;
}

export interface AccountFigures {
  range_days: number;
  from?: string;
  to?: string;
  profile_views: AccountReading[];
  search_appearances: AccountReading[];
}

export async function fetchAccountFigures(range: AnalyticsRange): Promise<AccountFigures> {
  return call<AccountFigures>(`/api/analytics/account-figures?range=${range}`);
}

export interface ContentFigure {
  value: number;
  read_at: string;
  /** The window the page named, or "" for the total the page showed. */
  period_label: string;
  precision: string | null;
}

export interface ContentItem {
  content_urn: string;
  kind: "article" | "newsletter";
  readings: Record<string, unknown>[];
  latest: Record<string, ContentFigure>;
}

export async function fetchContentFigures(): Promise<ContentItem[]> {
  const data = await call<{ content?: ContentItem[] }>("/api/analytics/content-figures");
  return data.content ?? [];
}

export interface OwnRepost {
  activity_urn: string;
  reposted_at: string | null;
  reactions: number | null;
  comments: number | null;
  reposts: number | null;
  impressions: number | null;
  first_seen_at: string;
  last_seen_at: string;
}

export async function fetchOwnReposts(): Promise<OwnRepost[]> {
  const data = await call<{ reposts?: OwnRepost[] }>("/api/v1/insights/reposts");
  return data.reposts ?? [];
}
