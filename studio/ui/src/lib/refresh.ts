import { useEffect, useRef, useState } from "react";
import { onStudioBack } from "@/lib/api";

/** Data older than this is read again when the window comes back into view. */
const STALE_ON_RETURN_MS = 15_000;

/**
 * Keeps an open screen's data current, without polling a window nobody sees.
 *
 * Queue, Leads and Posts read once when opened, so a post that came due, or
 * a person the bridge captured from the other window, appeared only after
 * moving away and back; and a screen that failed while the studio was down
 * stayed failed after it returned. This reads `load` again:
 *
 * - when the studio answers again after an outage;
 * - when the window comes back into view and the data is older than
 *   STALE_ON_RETURN_MS, which is the cheap answer to "left open overnight";
 * - every `everyMs` while the window is in view, for the few screens whose
 *   point is to show change as it happens. A hidden window is not polled.
 *
 * The screen's own first read stays the screen's; this only reads again.
 * `load` may change between renders; the latest one is used.
 */
export function useRefresh(load: () => unknown, everyMs?: number): void {
  const latest = useRef(load);
  latest.current = load;
  const lastRead = useRef(Date.now());

  useEffect(() => {
    // A read that fails leaves the screen as its own loader decides; it is
    // never an unhandled rejection in the console.
    const read = () => {
      lastRead.current = Date.now();
      const pending = latest.current();
      if (pending instanceof Promise) pending.catch(() => undefined);
    };
    const onReturn = () => {
      if (document.visibilityState === "visible" && Date.now() - lastRead.current >= STALE_ON_RETURN_MS) read();
    };
    const stopBack = onStudioBack(read);
    window.addEventListener("focus", onReturn);
    document.addEventListener("visibilitychange", onReturn);
    const timer = everyMs
      ? window.setInterval(() => {
          if (document.visibilityState === "visible") read();
        }, everyMs)
      : undefined;
    return () => {
      stopBack();
      window.removeEventListener("focus", onReturn);
      document.removeEventListener("visibilitychange", onReturn);
      if (timer !== undefined) window.clearInterval(timer);
    };
  }, [everyMs]);
}

/**
 * A count that goes up each time the studio answers again after an outage.
 *
 * For a screen that reads its data in an effect: listed among the effect's
 * dependencies, it runs that read again when the studio is back.
 */
export function useStudioBack(): number {
  const [returns, setReturns] = useState(0);
  useEffect(() => onStudioBack(() => setReturns((count) => count + 1)), []);
  return returns;
}
