import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { CalendarClock, CheckCheck, Loader2, Send } from "lucide-react";
import {
  fetchNextSlot,
  publishNow,
  schedulePost,
  stageToLinkedIn,
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
 * Recording a post as out, queueing one locally, and handing one to LinkedIn.
 *
 * Two of these three touch nothing but this machine, and the copy still says
 * so, because an earlier version did not: it offered to "send this now",
 * called the action "Publish now", and answered with a green check reading
 * PUBLISHED, when all that happened was a row's status being written.
 *
 * The third one is new and genuinely sends. It hands the post to LinkedIn's
 * own scheduler, which is the only way a scheduled post survives the laptop
 * being asleep. It is deliberately not a peer of the other two in this layout:
 * it sits below a rule, it names LinkedIn in the label, and it asks a second
 * time before it fires, because it is the one action here that cannot be
 * undone from this side.
 *
 * Everything else about the passive-observer design is unchanged. The
 * extension is still a passive bridge (docs/EXTENSION_AND_SYNC.md), the
 * backend still refuses the linkedin egress category by default, and a post
 * the author publishes themselves is still recorded with "mark", which is the
 * ordinary case and the honest verb for it.
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
  // The live send asks twice. This holds the state between the two asks, and is
  // cleared whenever the dialog opens so a previous confirmation cannot carry
  // over into a new post.
  const [confirmingSend, setConfirmingSend] = useState(false);

  useEffect(() => {
    if (!open) return;
    let live = true;
    setError(null);
    setVerdict(null);
    setConfirmingSend(false);
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

  async function run(action: "now" | "schedule" | "send") {
    if (!postId) return;
    setBusy(true);
    setError(null);
    try {
      if (action === "now") {
        await publishNow(postId);
        onDone("Marked as published");
      } else if (action === "send") {
        if (!slot) throw new Error("No slot is available to send into.");
        const staged = await stageToLinkedIn(postId, slot.slot_datetime);
        // The server's own sentence, not a cheerful rewrite of it. It is the
        // thing that distinguishes "LinkedIn has this" from "a row moved".
        onDone(staged.message);
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
      // A failed send un-primes the button. Leaving it armed after a refusal
      // invites a second press at the exact moment the author is least sure
      // what just happened.
      setConfirmingSend(false);
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
                  Mark this as published in your record, or put it in the local queue.
                </p>
                <p className="studio-meta mt-2 leading-snug text-ink-muted">
                  NEITHER OF THOSE TWO SENDS ANYTHING. BOTH WRITE TO THIS MACHINE ONLY,
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

                {/* Below a rule and after the two local actions, because it is
                    not one of them. The label names LinkedIn, the confirm step
                    names what cannot be undone, and the slot it would use is
                    the one shown above, so nothing about the timing is
                    implicit. */}
                <div className="mt-5 border-t border-edge pt-4">
                  <p className="studio-meta leading-snug text-ink-muted">
                    OR HAND IT TO LINKEDIN&apos;S OWN SCHEDULER, WHICH PUBLISHES IT EVEN IF
                    THIS MACHINE IS ASLEEP. THIS ONE REALLY SENDS.
                  </p>
                  {confirmingSend ? (
                    <div className="mt-3">
                      <p className="text-[13px] leading-relaxed text-signal-orange-text">
                        This sends the post to LinkedIn for{" "}
                        {slot ? `${slot.day_name} ${slot.time_slot}` : "the selected slot"}.
                        It cannot be undone from here: after this, changing it means going
                        to LinkedIn.
                      </p>
                      <div className="mt-3 flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => setConfirmingSend(false)}
                          className="rounded-md px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary"
                        >
                          Keep it here
                        </button>
                        <button
                          type="button"
                          disabled={busy || !slot}
                          onClick={() => run("send")}
                          className="flex items-center gap-1.5 rounded-md bg-signal-orange px-3 py-1 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-40"
                        >
                          {busy ? (
                            <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                          ) : (
                            <Send className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                          )}
                          Yes, send it to LinkedIn
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      type="button"
                      disabled={busy || !slot || verdict?.valid === false}
                      onClick={() => setConfirmingSend(true)}
                      className={cn(
                        "mt-3 flex items-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary",
                        "transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40",
                      )}
                    >
                      <Send className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                      Send to LinkedIn
                    </button>
                  )}
                </div>

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
