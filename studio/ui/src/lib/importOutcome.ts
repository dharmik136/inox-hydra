// How one history import ended, in words and a tone, for the Activity
// screen's Imports tab. The outcome values are the ones
// studio/backend/onboarding.py records. Only "end_of_list" read the whole
// list; every other ending read part of it or nothing, and is drawn as such,
// because a partial history shown as a whole one is how real leads were
// offered for deletion as strangers.

export type ImportTone = "done" | "partial" | "running" | "neutral";

export interface ImportEnding {
  label: string;
  tone: ImportTone;
}

const ENDINGS: Record<string, ImportEnding> = {
  end_of_list: { label: "Read to the end", tone: "done" },
  stopped: { label: "Stopped, part read", tone: "partial" },
  left_page: { label: "Left the page, part read", tone: "partial" },
  stalled: { label: "List stopped loading, part read", tone: "partial" },
  round_limit: { label: "Read the most one import reads", tone: "partial" },
  nothing_read: { label: "Nothing read", tone: "partial" },
  expired: { label: "Expired, not run", tone: "partial" },
  not_opened: { label: "Not started, no bridge browser", tone: "partial" },
  superseded: { label: "Replaced by a newer import", tone: "neutral" },
};

// What an older extension sent, and what earlier studios stored for it: it
// said "completed" whether or not it reached the end.
const OLDER_EXTENSION: ImportEnding = { label: "Older extension, end not known", tone: "partial" };

export function importEnding(entry: { outcome: string | null; started_at: string | null; finished_at: string | null }): ImportEnding {
  if (!entry.finished_at) {
    // The extension waits while its LinkedIn tab is hidden, and says so.
    if (entry.outcome === "paused_hidden") return { label: "Paused, LinkedIn tab hidden", tone: "partial" };
    return { label: entry.started_at ? "Running" : "Waiting for the page", tone: "running" };
  }
  return ENDINGS[entry.outcome ?? ""] ?? OLDER_EXTENSION;
}
