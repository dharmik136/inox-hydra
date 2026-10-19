import { useEffect, useState } from "react";
import {
  currentConnection,
  fetchAccounts,
  onConnectionChange,
  pingStudio,
  watchProfileSwitches,
  type Connection,
} from "@/lib/api";
import * as unsaved from "@/lib/unsaved";

/**
 * Reloads through the unsaved-work guard: asks first when anything would be
 * lost, as the profile switcher does, and reloads only on a yes.
 *
 * reloadStudio is read off the module rather than imported by name: it is
 * the registry's way to reload once the author has agreed, so the page's own
 * leave guard does not ask a second time, and a build without it falls back
 * to a plain reload after the same question.
 */
function reloadAfterAsking(): void {
  const guard = unsaved as typeof unsaved & {
    unsavedWorkLabels?: () => string[];
    reloadStudio?: () => void;
  };
  if (guard.hasUnsavedWork()) {
    const lost = guard.unsavedWorkLabels?.() ?? [];
    const what = lost.length ? lost.join(" and ") : "The post in the Composer";
    if (!window.confirm(`${what} ${lost.length > 1 ? "have" : "has"} unsaved changes. Reloading discards them. Reload anyway?`)) {
      return;
    }
  }
  if (guard.reloadStudio) guard.reloadStudio();
  else window.location.reload();
}

/** How often a window that has lost the studio asks again. */
const RETRY_MS = 5000;

/**
 * One line across the top of every screen when this window cannot be trusted.
 *
 * Losing the studio used to be announced nowhere: each surface showed its own
 * "Failed to fetch", or kept showing the last data it had as though it were
 * live. The request core now reports the studio unreachable the moment a
 * request cannot reach it, and this says so once, for the whole window, until
 * a request gets through again.
 *
 * The same line says when another window has switched the studio to a
 * different creator profile. This window still shows the profile it loaded
 * with, and the studio refuses its writes, so the creator has to know before
 * they type anything more here.
 */
export function StudioStatusBanner() {
  const [connection, setConnection] = useState<Connection>(currentConnection());
  const [names, setNames] = useState<Record<string, string>>({});

  useEffect(() => onConnectionChange(setConnection), []);

  // A switch in another window of this browser arrives at once. A switch in
  // another browser, or in the desktop window beside a browser tab, is noticed
  // on the next answer, so coming back to this window asks for one.
  useEffect(() => {
    const stop = watchProfileSwitches();
    const onVisible = () => {
      if (document.visibilityState === "visible") void pingStudio();
    };
    window.addEventListener("focus", onVisible);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stop();
      window.removeEventListener("focus", onVisible);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  // While the studio is unreachable, ask again now and then, so the banner
  // goes away by itself when the studio is back.
  useEffect(() => {
    if (connection.state !== "offline") return;
    const timer = window.setInterval(() => void pingStudio(), RETRY_MS);
    return () => window.clearInterval(timer);
  }, [connection.state]);

  // The profiles' names, so the line says which two profiles are involved.
  useEffect(() => {
    if (connection.state !== "stale-profile") return;
    let live = true;
    fetchAccounts()
      .then((res) => {
        if (live) setNames(Object.fromEntries(res.accounts.map((account) => [account.id, account.name])));
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [connection.state]);

  if (connection.state === "online") return null;

  if (connection.state === "stale-profile") {
    const shown = names[connection.shown] ?? "another profile";
    const active = names[connection.active] ?? "a different profile";
    return (
      <div
        role="alert"
        className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-signal-orange/40 bg-signal-orange-subtle px-4 py-2 text-[12px] text-signal-orange-text"
      >
        <span className="min-w-0 flex-1">
          This window shows {shown}, but the studio has switched to {active} in another window.
          The studio refuses saves from this window, so nothing lands in the wrong profile. Copy
          anything you have not saved, then reload.
        </span>
        <button
          type="button"
          onClick={reloadAfterAsking}
          className="shrink-0 rounded-md bg-signal-orange px-2.5 py-1 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110"
        >
          Reload this window
        </button>
      </div>
    );
  }

  return (
    <div
      role="alert"
      className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-signal-orange/40 bg-signal-orange-subtle px-4 py-2 text-[12px] text-signal-orange-text"
    >
      <span className="min-w-0 flex-1">
        The studio is not answering. It may have stopped, or this computer may have been asleep.
        Nothing on this screen is being saved or updated until it is back; this line goes away by
        itself when it is.
      </span>
    </div>
  );
}
