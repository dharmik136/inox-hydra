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
