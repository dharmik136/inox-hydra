/**
 * Whether the bridge is connected, as the last screen to ask was told.
 *
 * Today, Setup and Activity each read the bridge's state, and the header's
 * mark beside Activity read it on its own once a minute, so for up to a
 * minute Today said BRIDGE CONNECTED beside a hollow "not connected" mark.
 * Each of them now reports what it read here, and the mark shows the latest.
 */
type Listener = (connected: boolean) => void;

const listeners = new Set<Listener>();

/** Tells the header what a screen just read about the bridge. */
export function reportBridge(connected: boolean): void {
  for (const listener of listeners) listener(connected);
}

/** Calls the listener with each report. Returns the unsubscribe. */
export function onBridgeReport(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
