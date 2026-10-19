import { useEffect, useState } from "react";
import { currentConnection, onConnectionChange, pingStudio, type Connection } from "@/lib/api";

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
 */
export function StudioStatusBanner() {
  const [connection, setConnection] = useState<Connection>(currentConnection());

  useEffect(() => onConnectionChange(setConnection), []);

  // While the studio is unreachable, ask again now and then, so the banner
  // goes away by itself when the studio is back.
  useEffect(() => {
    if (connection.state !== "offline") return;
    const timer = window.setInterval(() => void pingStudio(), RETRY_MS);
    return () => window.clearInterval(timer);
  }, [connection.state]);

  if (connection.state === "online") return null;

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
