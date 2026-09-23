/*
 * Service worker: registered so the browser will offer to install this as an
 * application, and doing nothing else.
 *
 * Chrome and Edge will only show the install prompt for a page that registers
 * a service worker with a fetch handler. That is the entire reason this file
 * exists. It is not here to make the studio work offline.
 *
 * It deliberately caches nothing.
 *
 * A caching service worker in front of a local server is all cost and no
 * benefit. The server is on the same machine, so there is no latency to hide,
 * and there is no offline case to solve because if the machine is off the
 * server is off too. What a cache would add is a way to serve a stale app.js
 * after an update, which is a genuinely hard bug to diagnose from a user's
 * description. So every request passes straight through, and the worker holds
 * no state that could go out of date.
 *
 * Strict Invariants:
 * - Zero em-dashes.
 * - Never cache. If this file ever gains a caches.open call, the update story
 *   has to be designed first.
 */

self.addEventListener("install", () => {
  // Take over immediately rather than waiting for every tab to close, so a
  // reinstall does not leave two generations of worker running.
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  // Pass through, untouched. The handler must exist for installability, but
  // it must not interpose on requests carrying the studio token.
  event.respondWith(fetch(event.request));
});
