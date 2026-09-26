import { Check, Loader2 } from "lucide-react";
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
  draftRef: string;
  title: string;
  chars: number;
  foldLabel: string;
  pastFold: boolean;
  readSeconds: number;
  saveState: SaveState;
  savedAt: string | null;
  saveError: string | null;
  onSave: () => void;
  onPublish: () => void;
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
  draftRef,
  title,
  chars,
  foldLabel,
  pastFold,
  readSeconds,
  saveState,
  savedAt,
  saveError,
  onSave,
  onPublish,
}: ContextBarProps) {
  return (
    <header className="flex h-12 shrink-0 items-center gap-4 border-b border-edge bg-ink px-4">
      <div className="flex min-w-0 items-baseline gap-3">
        <span className="studio-meta shrink-0 uppercase">
          {kind} / {draftRef}
        </span>
        <h1 className="truncate text-[13px] font-medium text-ink-primary">{title}</h1>
      </div>

      {/* Centre telemetry. tabular-nums comes from .studio-meta so the numbers
          do not jitter sideways while typing. */}
      <p className="studio-meta mx-auto hidden shrink-0 md:block" aria-live="off">
        {chars.toLocaleString()} chars
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
              {(savedAt ?? "MARKED AS PUBLISHED").toUpperCase()}
            </span>
          )}
          {saveState === "failed" && (
            <span className="text-signal-orange-text" title={saveError ?? undefined}>
              SAVE FAILED
            </span>
          )}
          {saveState === "dirty" && <span className="text-signal-orange-text">UNSAVED</span>}
          {saveState === "idle" && <span className="text-ink-muted">UNCHANGED</span>}
        </span>

        <span className="h-4 w-px bg-edge" aria-hidden="true" />

        <button
          type="button"
          onClick={onSave}
          className={cn(
            "rounded-md px-2.5 py-1 text-xs font-medium text-ink-secondary",
            "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard)",
            "hover:bg-soft hover:text-ink-primary",
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
