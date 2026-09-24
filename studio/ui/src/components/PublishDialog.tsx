import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { CalendarClock, CheckCheck, Loader2 } from "lucide-react";
import {
  fetchNextSlot,
  publishNow,
  schedulePost,
  validateCadence,
  type CadenceVerdict,
  type NextSlot,
} from "@/lib/api";
import { cn } from "@/lib/utils";

interface PublishDialogProps {
  open: boolean;
  postId: string | null;
  onClose: () => void;
  onDone: (message: string) => void;
}

/**
 * Recording a post as out, and queueing one for later.
 *
 * Neither of these sends anything to LinkedIn, and the copy here says so,
 * because the first version did not. It offered to "send this now", called
 * the action "Publish now", and the composer answered with a green check
 * reading PUBLISHED. What actually happens is that /api/posts/{id}/publish-now
 * sets a row's status and stamps published_at. The backend makes no outbound
 * HTTP request anywhere, which is the product's headline claim, so a studio
 * that reported a delivery was reporting one that cannot occur.
 *
 * Posting happens in LinkedIn, by the author. The extension is a passive
 * bridge by design (docs/EXTENSION_AND_SYNC.md), and the post is tied back to
 * the record afterwards through its activity URN. So the honest verb for this
 * control is "mark", and the queue path is genuinely a local schedule.
 *
 * The scheduling path validates the cadence before committing, because the
 * write rejects an invalid time with a 400 and a rejection after the click
 * reads as a broken control rather than as the twelve hour rule it is.
 */
export function PublishDialog({ open, postId, onClose, onDone }: PublishDialogProps) {
  const [slot, setSlot] = useState<NextSlot | null>(null);
  const [verdict, setVerdict] = useState<CadenceVerdict | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let live = true;
    setError(null);
    setVerdict(null);
    fetchNextSlot()
      .then(async (next) => {
        if (!live) return;
        setSlot(next);
        if (next) {
          // Checked on open rather than on click, so the warning is visible
          // while the choice is still being made.
          setVerdict(await validateCadence(next.slot_datetime, postId ?? undefined));
        }
      })
      .catch(() => live && setSlot(null));
    return () => {
      live = false;
    };
  }, [open, postId]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  async function run(action: "now" | "schedule") {
    if (!postId) return;
    setBusy(true);
    setError(null);
    try {
      if (action === "now") {
        await publishNow(postId);
        onDone("Marked as published");
      } else {
        if (!slot) throw new Error("No slot is available to schedule into.");
        await schedulePost(postId, slot.slot_datetime);
        onDone(`Scheduled for ${slot.day_name} ${slot.time_slot}`);
      }
      onClose();
    } catch (caught) {
      // Nothing is reported as done. The draft is untouched and the dialog
      // stays open carrying the server's reason.
      setError(caught instanceof Error ? caught.message : "The request was refused.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.12 }}
          onClick={onClose}
          className="fixed inset-0 z-50 grid place-items-center bg-canvas/70 p-4 backdrop-blur-sm"
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="Publish"
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.22, ease: [0.32, 0.72, 0.24, 1] }}
            onClick={(event) => event.stopPropagation()}
            className="w-full max-w-md rounded-lg border border-edge bg-raised p-5 shadow-2xl"
          >
            <p className="studio-label">Publish</p>

            {!postId ? (
              <p className="mt-3 text-[13px] leading-relaxed text-ink-secondary">
                Save the draft first. Publishing acts on a stored post, and this one has not been
                written to the studio yet.
              </p>
            ) : (
              <>
                <p className="mt-3 text-[13px] leading-relaxed text-ink-secondary">
                  Mark this as published in your record, or put it in the queue.
                </p>
                <p className="studio-meta mt-2 leading-snug text-ink-muted">
                  NEITHER SENDS ANYTHING TO LINKEDIN. BOTH WRITE TO THIS MACHINE ONLY,
                  SO THE POST ITSELF IS STILL YOURS TO MAKE.
                </p>

                {slot && (
                  <div className="mt-4 rounded-md border border-edge bg-ink p-3">
                    <p className="studio-meta text-[10px]">NEXT SLOT</p>
                    <p className="mt-1 text-[13px] text-ink-primary">
                      {slot.day_name} {slot.time_slot}
                      <span className="mx-2 text-ink-muted">·</span>
                      <span className="text-ink-secondary">{slot.label}</span>
                    </p>
                    {verdict && !verdict.valid && (
                      <p className="studio-meta mt-2 leading-snug text-signal-orange-text">
                        {(verdict.error ?? "This time breaks the cadence rule.").toUpperCase()}
                      </p>
                    )}
                    {verdict?.valid && verdict.warning && (
                      <p className="studio-meta mt-2 leading-snug text-signal-orange-text">
                        {verdict.warning.toUpperCase()}
                      </p>
                    )}
                  </div>
                )}

                {error && (
                  <p role="status" className="studio-meta mt-3 leading-snug text-signal-orange-text">
                    {error}
                  </p>
                )}

                <div className="mt-5 flex items-center justify-end gap-2">
                  <button
                    type="button"
                    onClick={onClose}
                    className="rounded-md px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={busy || !slot || verdict?.valid === false}
                    onClick={() => run("schedule")}
                    className={cn(
                      "flex items-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary",
                      "transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40",
                    )}
                  >
                    <CalendarClock className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                    Queue it
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => run("now")}
                    className="flex items-center gap-1.5 rounded-md bg-signal-orange px-3 py-1 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-40"
                  >
                    {busy ? (
                      <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                    ) : (
                      <CheckCheck className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                    )}
                    Mark as published
                  </button>
                </div>
              </>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
