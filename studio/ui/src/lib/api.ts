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
}

/**
 * The draft the composer reopens, or null on a first run.
 *
 * list_posts orders by COALESCE(scheduled_for, created_at) ASC, so the newest
 * draft is the last row rather than the first. Taking posts[0] would reopen the
 * oldest draft the creator ever wrote.
 */
export async function fetchLatestDraft(): Promise<Draft | null> {
  const data = await call<{ posts?: PostRow[] }>("/api/posts?status=draft");
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
 */
export async function updateDraft(id: string, content: string, base?: string): Promise<void> {
  await call(`/api/posts/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(base === undefined ? { content } : { content, base_content: base }),
  });
}

export interface HookTemplate {
  id: number;
  archetype: string;
  hook_text: string;
  velocity_score: number;
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
}

export async function fetchLeadTimeline(
  leadId: string,
): Promise<{ lead: Lead; interactions: LeadInteraction[]; stage_history?: LeadStageEvent[] }> {
  return call(`/api/v1/crm/leads/${encodeURIComponent(leadId)}/timeline`);
}

// ---------------------------------------------------------------------------
// Swipe file
// ---------------------------------------------------------------------------

export interface Inspiration {
  id: number;
  archetype: string;
  topic: string;
  content: string;
  key_hook: string | null;
  author_name: string | null;
  author_headline: string | null;
  /**
   * Null for a specimen that was never posted, which is all of the ones
   * shipped in the box. The endpoint used to synthesise these from the
   * velocity score, so the wall reported reactions on posts that had never
   * existed. A number here means someone captured it.
   */
  likes_count: number | null;
  comments_count: number | null;
  /** A real stored rating of the form, unlike the two fields above. */
  velocity_score: number;
  pacing_style: string | null;
  /** 'shipped' came in the box, 'captured' was saved by the creator. */
  origin: string | null;
}

export async function fetchInspirations(): Promise<Inspiration[]> {
  const data = await call<{ inspirations?: Inspiration[] }>("/api/inspirations");
  return data.inspirations ?? [];
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
}

export async function fetchAnalyticsKpis(range: AnalyticsRange): Promise<AnalyticsKpis> {
  return call<AnalyticsKpis>(`/api/analytics/kpis?range=${range}`);
}

export interface AnalyticsPost {
  id: string;
  content: string;
  impressions: number | null;
  reactions: number | null;
  comments: number | null;
  shares: number | null;
  engagement_rate: number | null;
  published_at: string | null;
}

export async function fetchAnalyticsPosts(): Promise<AnalyticsPost[]> {
  const data = await call<{ posts?: AnalyticsPost[] }>("/api/analytics/posts");
  return data.posts ?? [];
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
export async function fetchDuePosts(): Promise<ScheduledPost[]> {
  const data = await call<{ posts?: ScheduledPost[] }>("/api/posts?status=due");
  return data.posts ?? [];
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

export async function dispatchQueueNow(): Promise<string[]> {
  const data = await call<{ actions?: unknown }>("/api/v1/scheduler/dispatch/now", { method: "POST" });
  const actions = data.actions;
  if (Array.isArray(actions)) return actions.map((a) => (typeof a === "string" ? a : JSON.stringify(a)));
  return [];
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

export async function updateLeadStatus(leadId: string, status: string): Promise<void> {
  await call(`/api/leads/${encodeURIComponent(leadId)}/status`, {
    method: "PUT",
    body: JSON.stringify({ status }),
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
 */
export const DM_STYLES = [
  { id: "value_add", label: "Peer question" },
  { id: "resource_share", label: "Offer a blueprint" },
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
): Promise<StagedToLinkedIn> {
  return call<StagedToLinkedIn>(
    `/api/v1/posts/${encodeURIComponent(postId)}/stage-to-linkedin`,
    {
      method: "POST",
      body: JSON.stringify({ scheduled_at: scheduledAt, confirm: true, confirm_resend: confirmResend }),
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

export async function schedulePost(postId: string, scheduledFor: string): Promise<void> {
  await call(`/api/posts/${encodeURIComponent(postId)}/reschedule`, {
    method: "POST",
    body: JSON.stringify({ scheduled_for: scheduledFor }),
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

/**
 * Streams AI completions token by token using Server Sent Events (SSE).
 * Calls /api/ai/stream with prompt, system_prompt, max_tokens, and temperature.
 * Invokes onChunk callback as tokens arrive and resolves with the full text.
 */
export async function streamAiCompletion(
  prompt: string,
  options?: {
    systemPrompt?: string;
    maxTokens?: number;
    temperature?: number;
    onChunk?: (chunk: string) => void;
  },
): Promise<string> {
  const response = await studioFetch("/api/ai/stream", {
    method: "POST",
    body: JSON.stringify({
      prompt,
      system_prompt: options?.systemPrompt ?? null,
      max_tokens: options?.maxTokens ?? 1200,
      temperature: options?.temperature ?? 0.7,
    }),
  });

  if (!response.ok) throw await refusalFrom(response);

  const reader = response.body?.getReader();
  if (!reader) {
    return "";
  }

  const decoder = new TextDecoder();
  let accumulated = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const text = decoder.decode(value, { stream: true });
    const lines = text.split("\n");
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const payloadStr = line.slice(6).trim();
        if (payloadStr === "[DONE]") {
          continue;
        }
        try {
          const payload = JSON.parse(payloadStr);
          if (payload && typeof payload.token === "string") {
            accumulated += payload.token;
            if (options?.onChunk) {
              options.onChunk(payload.token);
            }
          }
        } catch {
          // ignore incomplete or malformed chunk
        }
      }
    }
  }

  return accumulated;
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
}

export async function fetchAuthStatus(): Promise<AuthStatus> {
  return call<AuthStatus>("/api/auth/status");
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
// Post attribution
// ---------------------------------------------------------------------------

export interface AttributedLead {
  lead_id: string;
  name: string;
  headline: string | null;
  company: string | null;
  icp_score: number;
  lead_status: string | null;
  qualification_tier: string | null;
  latest_comment: string | null;
}

export interface PostAttribution {
  post_identifier: string;
  summary: {
    total_leads_generated: number;
    total_interactions: number;
    vip_leads_count: number;
    avg_icp_score: number;
    comments_count: number;
    likes_count: number;
  };
  leads: AttributedLead[];
}

/** Which leads a given post actually produced. */
export async function fetchPostAttribution(postId: string): Promise<PostAttribution> {
  const data = await call<Record<string, any>>(
    `/api/v1/analytics/posts/${encodeURIComponent(postId)}/leads`,
  );
  const summary = data.attribution_summary ?? {};
  return {
    post_identifier: typeof data.post_identifier === "string" ? data.post_identifier : postId,
    summary: {
      total_leads_generated: summary.total_leads_generated ?? 0,
      total_interactions: summary.total_interactions ?? 0,
      vip_leads_count: summary.vip_leads_count ?? 0,
      avg_icp_score: summary.avg_icp_score ?? 0,
      comments_count: summary.comments_count ?? 0,
      likes_count: summary.likes_count ?? 0,
    },
    leads: Array.isArray(data.leads) ? data.leads : [],
  };
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

/** Puts the extension folder on the clipboard, for Load Unpacked by hand. */
export async function copyExtensionPath(): Promise<string> {
  const data = await call<{ path?: string; extension_path?: string }>(
    "/api/v1/browser/copy-path",
    { method: "POST" },
  );
  return data.path ?? data.extension_path ?? "";
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
  state: "never_run" | "working" | "drifting";
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
  steps: { bridge: boolean; identity: boolean; posts: boolean; activity: boolean; archive: boolean };
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
    bridge_carrier: string | null;
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
export type SearchOpens = "composer" | "queue" | "analytics" | "leads" | "swipe" | "docs";

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
 * There is no single-post route, and the draft list is small, so this reads
 * the list rather than adding one. Only drafts: a published or queued post is
 * never loaded into the editor, because Save writes over whatever it holds.
 */
export async function fetchDraftById(id: string): Promise<Draft | null> {
  const data = await call<{ posts?: PostRow[] }>("/api/posts?status=draft");
  const row = (data.posts ?? []).find((post) => post.id === id);
  return row ? { id: row.id, content: row.content } : null;
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
  current: { age_hours: number | null; impressions: number | null; reactions: number | null; comments: number | null } | null;
  /** Present only when the post and enough earlier ones were read at about two days old. */
  comparison: Partial<Record<"impressions" | "reactions" | "comments", MetricComparison>> | null;
  not_compared_because: string | null;
  url: string;
  analytics_url: string;
}

export interface TodayBrief {
  identity: { known: boolean; name: string | null };
  freshness: { bridge: BridgeStatus; drifting: string[]; last_capture_at: string | null };
  reply_to: TodayPerson[];
  latest_post: TodayLatestPost | null;
  queue: {
    next_scheduled: { post_id: string; scheduled_for: string; excerpt: string } | null;
    next_open_slot: { local_datetime: string; day_name: string; time_slot: string; label: string | null } | null;
  };
  open_next: { action: "open" | "setup"; url?: string; reason: string };
}

export async function fetchToday(): Promise<TodayBrief> {
  return call<TodayBrief>("/api/v1/today");
}

// -------------------------------------------------------------
// Insights: your posts, and your attention
// -------------------------------------------------------------

export interface PostInsightPerson {
  lead_id: string;
  name: string | null;
  commented: boolean;
  status: string | null;
}

export interface PostInsight {
  activity_urn: string;
  excerpt: string | null;
  published_at: string | null;
  age_days: number | null;
  /** Old enough (a week) for its numbers to have mostly arrived. */
  settled: boolean;
  reactions: number | null;
  comments: number | null;
  reposts: number | null;
  impressions: number | null;
  /** Against your own median, only for settled posts. 1.0 is your usual. */
  against_usual: Partial<Record<"reactions" | "comments" | "impressions", number>> | null;
  people: PostInsightPerson[];
  people_count: number;
  conversations: number;
  url: string;
}

export interface PostsInsights {
  posts: PostInsight[];
  usual: Record<"reactions" | "comments" | "impressions", { median: number | null; posts: number }>;
  best: string[];
  settled_after_days: number;
}

export async function fetchPostsInsights(): Promise<PostsInsights> {
  return call<PostsInsights>("/api/v1/insights/posts");
}

export interface OutboundAuthor {
  name: string;
  reactions: number;
  comments: number;
  total: number;
  last_at: string | null;
  engaged_back: number;
}

export interface OutboundInsights {
  totals: { reactions: number; comments: number; authors: number; without_author: number };
  coverage: { posts_read: number; posts_with_engagement: number; share: number; one_way_judged: boolean };
  authors: OutboundAuthor[];
  one_way: string[];
  reciprocal: string[];
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
}

export interface PatternsInsights {
  posts_compared: number;
  metric: string;
  patterns: PatternFinding[];
  not_enough_posts: PatternFinding[];
  min_per_side: number;
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
  status: "conclusive" | "insufficient_sample";
  n_with: number;
  n_without: number;
  median_with?: number | null;
  median_without?: number | null;
  ratio?: number | null;
  planted_or_significant?: boolean;
  min_required: number;
  reason?: string;
}

export interface ContrastInsights {
  status: string;
  settled_posts_count: number;
  min_arm_size: number;
  contrasts: ContrastFinding[];
}

export async function fetchContrastInsights(): Promise<ContrastInsights> {
  return call<ContrastInsights>("/api/v1/insights/contrasts");
}

export interface TopicAttributionItem {
  topic: string;
  post_count?: number;
  posts_count?: number;
  total_reactions: number;
  median_reactions?: number;
  qualified_leads: number;
  lead_conversion_rate: number;
  summary?: string;
}

export interface TopicAttributionInsights {
  status: "success" | "cold_start";
  message?: string;
  settled_posts_analyzed?: number;
  qualified_leads_attributed?: number;
  topics: TopicAttributionItem[];
  summary_sentence: string;
}

export async function fetchTopicAttribution(): Promise<TopicAttributionInsights> {
  return call<TopicAttributionInsights>("/api/v1/insights/attribution");
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
  return (error as Error & { status?: number }).status === 409 || error.message.includes(DRAFT_CHANGED_ELSEWHERE);
}
