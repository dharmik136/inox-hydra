import { useEffect, useMemo, useRef, useState } from "react";
import { FilePlus2, Loader2, Search, Trash2, X } from "lucide-react";
import { createDraft, deleteDraft, fetchDrafts, type DraftSummary } from "@/lib/api";
import { useModalFocus } from "@/lib/modalFocus";
import { measurableLength } from "@/lib/text";
import { formatLocal } from "@/lib/time";
import { cn } from "@/lib/utils";

interface DraftsPanelProps {
  open: boolean;
  onClose: () => void;
  /** The draft the Composer holds, marked in the list. */
  currentId: string | null;
  /** Bumped by the Composer after a save, so an open list is not stale. */
  refreshKey: number;
  /** Opens a draft in the Composer. Resolves false when the author chose to stay. */
  onOpen: (draft: DraftSummary) => Promise<boolean> | boolean;
  /** Starts an empty post. Resolves false when the author chose to stay. */
  onNewPost: () => boolean;
  /** Called after the draft the Composer holds was deleted. */
  onDeletedCurrent: () => void;
}

/** The first line of a draft, as the list names it. */
export function draftTitle(content: string): string {
  return content.trim().split("\n")[0]?.slice(0, 90) || "Untitled draft";
}

/** created_at is SQLite's CURRENT_TIMESTAMP: UTC, without the T or the zone. */
function startedAt(value: string | null): string {
  if (!value) return "Start time not recorded";
  return `Started ${formatLocal(value.includes("T") ? value : `${value.replace(" ", "T")}Z`)}`;
}

/**
 * Every draft, to open, start a new post beside, or delete.
 *
 * The Composer held one draft at a time. Clearing it and saving wrote the
 * next idea over the last one, and the only way back to an earlier draft was
 * a word from it typed into Ctrl K, so a creator who plans a week of posts
 * kept them outside the product. This lists them all, newest first.
 *
 * Delete is the Composer's first destructive control, so it asks first,
 * names the draft, and offers Undo, which saves the text again as a new
 * draft. Opening another draft or starting a new post over unsaved text asks
 * first as well; the Composer decides that, since it holds the text.
 */
export function DraftsPanel({
  open,
  onClose,
  currentId,
  refreshKey,
  onOpen,
  onNewPost,
  onDeletedCurrent,
}: DraftsPanelProps) {
  const [drafts, setDrafts] = useState<DraftSummary[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);
  const [deleted, setDeleted] = useState<DraftSummary | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  useModalFocus(panelRef, open, onClose);

  async function load() {
    try {
      setDrafts(await fetchDrafts());
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }

  useEffect(() => {
    if (!open) return;
    setNote(null);
    setDeleted(null);
    void load();
  }, [open, refreshKey]);

  const shown = useMemo(() => {
    const term = query.trim().toLowerCase();
    return (drafts ?? []).filter((draft) => !term || draft.content.toLowerCase().includes(term));
  }, [drafts, query]);

  async function remove(draft: DraftSummary) {
    const title = draftTitle(draft.content);
    const current = draft.id === currentId;
    const question =
      `Delete the draft "${title}"? It is removed from the studio's database.` +
      (current ? " It is the post open in the Composer, which clears." : "");
    if (!window.confirm(question)) return;
    setBusy(draft.id);
    setNote(null);
    try {
      await deleteDraft(draft.id);
      if (current) onDeletedCurrent();
      setDeleted(draft);
      setNote({ text: `Deleted "${title}".`, error: false });
      await load();
    } catch (caught) {
      setNote({ text: caught instanceof Error ? caught.message : "The studio refused to delete it.", error: true });
    } finally {
      setBusy(null);
    }
  }

  async function undo() {
    if (!deleted) return;
    setBusy("undo");
    try {
      await createDraft(deleted.content);
      setNote({ text: `"${draftTitle(deleted.content)}" is back in your drafts.`, error: false });
      setDeleted(null);
      await load();
    } catch (caught) {
      setNote({ text: caught instanceof Error ? caught.message : "The draft could not be saved again.", error: true });
    } finally {
      setBusy(null);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex justify-start bg-canvas/60" onClick={onClose}>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Drafts"
        onClick={(event) => event.stopPropagation()}
        className="flex h-full w-full max-w-sm flex-col border-r border-edge bg-raised shadow-2xl"
      >
        <div className="flex shrink-0 items-center gap-2 border-b border-edge px-4 py-3">
          <p className="studio-label flex-1">
            Drafts{drafts ? <span className="ml-1.5 text-ink-muted">{drafts.length}</span> : null}
          </p>
          <button
            type="button"
            onClick={() => {
              if (onNewPost()) onClose();
            }}
            className="flex items-center gap-1.5 rounded-md bg-signal-orange px-2.5 py-1 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110"
          >
            <FilePlus2 className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
            New post
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close drafts"
            className="grid size-7 place-items-center rounded-md text-ink-muted transition-colors hover:bg-soft hover:text-ink-primary"
          >
            <X className="size-4" strokeWidth={1.75} aria-hidden="true" />
          </button>
        </div>

        <div className="shrink-0 px-4 pt-3">
          <div className="relative">
            <Search
              className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-ink-muted"
              strokeWidth={1.75}
              aria-hidden="true"
            />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Find a draft"
              aria-label="Find a draft"
              className="w-full rounded-md border border-edge bg-ink py-1.5 pr-3 pl-8 text-[12px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
            />
          </div>
          {note && (
            <p
              role="status"
              className={cn(
                "mt-2 flex flex-wrap items-baseline gap-x-2 text-[12px] leading-snug",
                note.error ? "text-signal-orange-text" : "text-ink-secondary",
              )}
            >
              {note.text}
              {deleted && !note.error && (
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => void undo()}
                  className="text-ink-primary underline underline-offset-2 disabled:opacity-40"
                >
                  Undo
                </button>
              )}
            </p>
          )}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-2 py-3">
          {failed ? (
            <p className="px-2 text-[12px] text-signal-orange-text">
              The drafts could not be read. Is the studio running?{" "}
              <button type="button" onClick={() => void load()} className="underline underline-offset-2">
                Try again
              </button>
            </p>
          ) : !drafts ? (
            <p className="studio-meta flex items-center gap-2 px-2 text-ink-muted">
              <Loader2 className="size-3 animate-spin" aria-hidden="true" />
              READING YOUR DRAFTS
            </p>
          ) : drafts.length === 0 ? (
            <p className="px-2 text-[13px] leading-relaxed text-ink-secondary">
              No drafts yet. Write in the Composer and press Save, or press New post to start one.
            </p>
          ) : shown.length === 0 ? (
            <p className="px-2 text-[13px] text-ink-secondary">No draft has that in it.</p>
          ) : (
            <ul className="flex flex-col">
              {shown.map((draft) => {
                const title = draftTitle(draft.content);
                const current = draft.id === currentId;
                return (
                  <li key={draft.id} className="group flex items-start gap-1 rounded-md hover:bg-soft">
                    <button
                      type="button"
                      onClick={async () => {
                        if (current || (await onOpen(draft))) onClose();
                      }}
                      aria-current={current ? "true" : undefined}
                      className="min-w-0 flex-1 px-2 py-2 text-left"
                    >
                      <span className="block truncate text-[13px] text-ink-primary">{title}</span>
                      <span className="studio-meta mt-0.5 block text-[10px] text-ink-muted">
                        {current ? <span className="text-signal-orange-text">OPEN NOW · </span> : null}
                        {startedAt(draft.created_at).toUpperCase()} · {measurableLength(draft.content).toLocaleString()}{" "}
                        CHARS
                      </span>
                    </button>
                    <button
                      type="button"
                      disabled={busy !== null}
                      onClick={() => void remove(draft)}
                      aria-label={`Delete draft: ${title}`}
                      className="mt-1.5 mr-1 grid size-7 shrink-0 place-items-center rounded-md text-ink-muted transition-colors hover:bg-canvas hover:text-ink-primary disabled:opacity-40"
                    >
                      {busy === draft.id ? (
                        <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                      ) : (
                        <Trash2 className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
