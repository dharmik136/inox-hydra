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
      post_topic: postTopic || "sovereign creator stack",
    }),
  });
  if (!data.suggested_dm) throw new Error("the server returned no draft");
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
 */
export async function stageToLinkedIn(
  postId: string,
  scheduledAt: string,
): Promise<StagedToLinkedIn> {
  return call<StagedToLinkedIn>(
    `/api/v1/posts/${encodeURIComponent(postId)}/stage-to-linkedin`,
    {
      method: "POST",
      body: JSON.stringify({ scheduled_at: scheduledAt, confirm: true }),
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
 * Content only. The server excludes credentials deliberately, and the note it
 * returns says so, which is worth showing rather than paraphrasing.
 */
export async function exportData(format: "json" | "csv"): Promise<{ path: string; note: string }> {
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
export async function launchBridge(browserId: string): Promise<BrowserLaunch> {
  const data = await call<Partial<BrowserLaunch>>("/api/v1/browser/launch", {
    method: "POST",
    body: JSON.stringify({ browser_id: browserId }),
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
