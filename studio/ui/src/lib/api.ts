/**
 * Calls to the local studio.
 *
 * Authentication is a cookie the server sets on every non-/api response, and it
 * is HttpOnly by design, so there is nothing to read or attach here: the only
 * requirement is that fetch is told to send it. A same origin GET carries no
 * Origin header, which the middleware allows explicitly, so these requests are
 * authorised by the cookie and the loopback Host check alone.
 */

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    // Without this the cookie is not sent and every call is a 401.
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });

  if (!response.ok) {
    // FastAPI puts the human readable reason in "detail", and some of them are
    // things the author needs to read rather than a status code: exceeding the
    // 5,000 character limit comes back as a 400 with the limit spelled out.
    let reason = `${response.status}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") reason = body.detail;
    } catch {
      // No JSON body. The status alone is all there is to report.
    }
    throw new Error(reason);
  }
  return (await response.json()) as T;
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

/** Writes new content over an existing draft. */
export async function updateDraft(id: string, content: string): Promise<void> {
  await call(`/api/posts/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify({ content }),
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
export type FormatKind = "bold" | "italic" | "monospace" | "strikethrough" | "clean";

const FORMAT_PATHS: Record<FormatKind, string> = {
  bold: "/api/format/bold",
  italic: "/api/format/italic",
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
  predicted_score: number;
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
  interaction_type: string | null;
  comment_text: string | null;
  suggested_dm_reply: string | null;
  interacted_at: string;
}

export async function fetchLeadTimeline(
  leadId: string,
): Promise<{ lead: Lead; interactions: LeadInteraction[] }> {
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
  likes_count: number;
  comments_count: number;
  velocity_score: number;
  pacing_style: string | null;
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

export interface DocModule {
  id: string;
  number: number;
  title: string;
  summary: string;
  category: string;
}

export interface DocHit {
  filename: string;
  section: string;
  snippet: string;
  relevance_rank: number;
}

export async function fetchDocModules(): Promise<DocModule[]> {
  const data = await call<{ modules?: DocModule[] }>("/api/docs");
  return data.modules ?? [];
}

export async function searchDocs(query: string, limit = 12): Promise<DocHit[]> {
  const data = await call<{ results?: DocHit[] }>(
    `/api/docs/search?q=${encodeURIComponent(query)}&limit=${limit}`,
  );
  return data.results ?? [];
}

export async function fetchDocModule(moduleId: string): Promise<{ title: string; content: string }> {
  const data = await call<{ title?: string; content?: string; markdown?: string }>(
    `/api/docs/${encodeURIComponent(moduleId)}`,
  );
  return { title: data.title ?? moduleId, content: data.content ?? data.markdown ?? "" };
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
      post_topic: postTopic || "sovereign creator stack",
    }),
  });
  if (!data.suggested_dm) throw new Error("the server returned no draft");
  return data.suggested_dm;
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

  const response = await fetch("/api/media/upload", {
    method: "POST",
    credentials: "same-origin",
    body: form,
  });
  if (!response.ok) {
    let reason = `${response.status}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") reason = body.detail;
    } catch {
      // No JSON body; the status is all there is.
    }
    throw new Error(reason);
  }
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

/** Dispatches a draft immediately and marks it published. */
export async function publishNow(postId: string): Promise<void> {
  await call(`/api/posts/${encodeURIComponent(postId)}/publish-now`, { method: "POST" });
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

/** The analytics CSV streams as a file, so it is a link rather than a fetch. */
export const ANALYTICS_CSV_URL = "/api/analytics/export?format=csv";
