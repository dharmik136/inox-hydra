import { useEffect, useState } from "react";
import { Check, Copy, FilePlus2, Files, Loader2 } from "lucide-react";
import { POST_LIMIT_CHARS } from "@/lib/text";
import { cn } from "@/lib/utils";

/**
 * "idle" is the load state, before anything is edited. "dirty" is the one
 * that matters: edits exist that are not on disk. Collapsing it into "idle"
 * would show UNCHANGED over unsaved work. "failed" is not a variant of
 * "dirty": both mean the work is unsaved, but only one of them means the
 * author already asked for it to be saved and it did not happen.
 */
export type SaveState = "idle" | "dirty" | "saving" | "saved" | "failed" | "published";

interface ContextBarProps {
  kind: string;
  title: string;
  /** Every character as stored, the count LinkedIn's limit and Gate 2 apply. */
  storedChars: number;
  foldLabel: string;
  pastFold: boolean;
  readSeconds: number;
  saveState: SaveState;
  savedAt: string | null;
  saveError: string | null;
  onSave: () => void;
  onPublish: () => void;
  /** Opens the drafts list. */
  onDrafts: () => void;
  /** Starts an empty post; the post open now stays in the drafts list. */
  onNewPost: () => void;
  /** Copies the text in the editor exactly. Resolves whether the clipboard took it. */
  onCopy: () => Promise<boolean>;
}

/**
 * The slim editorial status strip (blueprint section 6).
 *
 * Telemetry reads as publishing metadata rather than AI monitoring, which is
 * mostly a typography decision: monospace, tabular figures, lowercase units,
 * no pills and no glow.
 */
export function ContextBar({
  kind,
  title,
  storedChars,
  foldLabel,
  pastFold,
  readSeconds,
  saveState,
  savedAt,
  saveError,
  onSave,
  onPublish,
  onDrafts,
  onNewPost,
  onCopy,
}: ContextBarProps) {
  // What the last Copy did, said on the button for a few seconds.
  const [copied, setCopied] = useState<"copied" | "refused" | null>(null);
  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(null), 3000);
    return () => window.clearTimeout(timer);
  }, [copied]);
  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b border-edge bg-ink px-3 sm:gap-4 sm:px-4">
      {/* flex-1 with min-w-0, so the title is what gives way on a narrow
          window. The reference used to keep its width and slide under the
          save status on a phone. */}
      <div className="flex min-w-0 flex-1 items-baseline gap-3 md:flex-initial">
        <span className="studio-meta hidden shrink-0 uppercase sm:inline">
          {kind}
        </span>
        <h1 className="truncate text-[13px] font-medium text-ink-primary">{title}</h1>
      </div>

      {/* Centre telemetry. tabular-nums comes from .studio-meta so the numbers
          do not jitter sideways while typing. */}
      <p className="studio-meta mx-auto hidden shrink-0 md:block" aria-live="off">
        {/* Against the limit, so the strip and the Audit's Gate 2 give the
            same answer. It used to show a bare count with no limit at all. */}
        <span className={storedChars > POST_LIMIT_CHARS ? "text-signal-orange-text" : undefined}>
          {storedChars.toLocaleString()} / {POST_LIMIT_CHARS.toLocaleString()} chars
        </span>
        <span className="mx-1.5 text-ink-muted">·</span>
        <span className={pastFold ? "text-signal-orange-text" : undefined}>{foldLabel}</span>
        <span className="mx-1.5 text-ink-muted">·</span>~{readSeconds}s read
      </p>

      <div className="ml-auto flex shrink-0 items-center gap-3">
        {/* Save reports itself here and nowhere else. Blueprint
            micro-interaction 6 is explicit that saving does not raise a toast,
            so this mark is the entire feedback channel: if it does not update,
            the author has no other way to know. */}
        <span
          className="studio-meta flex items-center gap-1.5 tabular-nums"
          role="status"
          aria-live="polite"
        >
          {saveState === "saving" && (
            <>
              <Loader2 className="size-3 animate-spin text-ink-muted" aria-hidden="true" />
              SAVING
            </>
          )}
          {saveState === "saved" && savedAt && (
            <>
              <Check className="size-3 text-signal-green-text" aria-hidden="true" />
              SAVED {savedAt}
            </>
          )}
          {saveState === "published" && (
            <span className="flex items-center gap-1.5 text-signal-green-text">
              <Check className="size-3" aria-hidden="true" />
              {(savedAt ?? "MARKED AS POSTED").toUpperCase()}
            </span>
          )}
          {saveState === "failed" && (
            <span className="text-signal-orange-text">
              SAVE FAILED
              {/* The reason, announced with the mark. It used to be a title
                  attribute, which keyboard, touch and screen reader users
                  never get. */}
              {saveError && <span className="sr-only">. {saveError}</span>}
            </span>
          )}
          {saveState === "dirty" && <span className="text-signal-orange-text">UNSAVED</span>}
          {saveState === "idle" && <span className="text-ink-muted">UNCHANGED</span>}
        </span>

        <span className="hidden h-4 w-px bg-edge sm:block" aria-hidden="true" />

        {/* Every draft, and a fresh post beside them. The Composer used to
            hold one draft, and the next idea could only be written over it. */}
        <button
          type="button"
          onClick={onDrafts}
          className={cn(
            "flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-ink-secondary",
            "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard) hover:bg-soft hover:text-ink-primary",
          )}
        >
          <Files className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
          <span className="max-lg:sr-only">Drafts</span>
        </button>
        <button
          type="button"
          onClick={onNewPost}
          className={cn(
            "flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-ink-secondary",
            "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard) hover:bg-soft hover:text-ink-primary",
          )}
        >
          <FilePlus2 className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
          <span className="max-lg:sr-only">New post</span>
        </button>

        {/* The text exactly as written, for pasting into LinkedIn. No
            screen that showed a post used to offer this. */}
        <button
          type="button"
          onClick={() => void onCopy().then((ok) => setCopied(ok ? "copied" : "refused"))}
          className={cn(
            "flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium",
            copied === "refused" ? "text-signal-orange-text" : "text-ink-secondary",
            "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard) hover:bg-soft hover:text-ink-primary",
          )}
        >
          {copied === "copied" ? (
            <Check className="size-3.5 text-signal-green-text" aria-hidden="true" />
          ) : (
            <Copy className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
          )}
          <span className="max-lg:sr-only">
            {copied === "copied" ? "Copied" : copied === "refused" ? "Copy refused" : "Copy"}
          </span>
        </button>

        {/* Disabled while a save is out, so a second press cannot start a
            second write. */}
        <button
          type="button"
          onClick={onSave}
          disabled={saveState === "saving"}
          className={cn(
            "rounded-md px-2.5 py-1 text-xs font-medium text-ink-secondary",
            "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard)",
            "hover:bg-soft hover:text-ink-primary disabled:opacity-50 disabled:hover:bg-transparent",
          )}
        >
          Save
        </button>

        <button
          type="button"
          onClick={onPublish}
          className={cn(
            "rounded-md bg-signal-orange px-3 py-1 text-xs font-medium text-on-signal",
            "transition-[filter] duration-(--studio-motion-fast) ease-(--ease-standard)",
            "hover:brightness-110",
          )}
        >
          Publish
        </button>
      </div>
    </header>
  );
}

/** A way past what the line under the bar says, such as Keep this version. */
export interface BarAction {
  label: string;
  onClick: () => void;
}

/**
 * Why the last save failed, or what the Composer is holding, in words under
 * the bar.
 *
 * The bar has room for the mark, not the sentence, and the sentence is the
 * part the author has to act on: the 5,000 character limit, an empty editor,
 * a draft changed in another window, a post that is already queued. A failure
 * is hidden from assistive technology only because the status in the bar
 * already announces it; a note is not announced anywhere else, so it is read.
 */
export function SaveReason({
  reason,
  actions = [],
  tone = "failed",
}: {
  reason: string;
  actions?: BarAction[];
  tone?: "failed" | "note";
}) {
  // A note is a landmark of its own, so it is not text floating outside one.
  const Box = tone === "note" ? "aside" : "div";
  return (
    <Box
      aria-label={tone === "note" ? "About the post in the Composer" : undefined}
      className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-edge bg-ink px-3 py-1.5 sm:px-4"
    >
      <p
        className={cn(
          "min-w-0 flex-1 basis-60 text-[12px] leading-snug",
          tone === "failed" ? "text-signal-orange-text" : "text-ink-secondary",
        )}
        aria-hidden={tone === "failed" ? "true" : undefined}
      >
        {reason}
      </p>
      {actions.map((action) => (
        <button
          key={action.label}
          type="button"
          onClick={action.onClick}
          className="shrink-0 rounded-md border border-edge px-2.5 py-1 text-xs font-medium text-ink-secondary transition-colors hover:border-edge-strong hover:text-ink-primary"
        >
          {action.label}
        </button>
      ))}
    </Box>
  );
}
