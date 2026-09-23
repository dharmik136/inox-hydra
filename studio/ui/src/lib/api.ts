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
    throw new Error(`${init?.method ?? "GET"} ${path} failed: ${response.status}`);
  }
  return (await response.json()) as T;
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
