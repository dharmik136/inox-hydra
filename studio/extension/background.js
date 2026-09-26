// -------------------------------------------------------------
// LinkedIn Studio Bridge: Background Service Worker (Manifest V3)
// -------------------------------------------------------------
const STUDIO_ORIGIN = "http://127.0.0.1:8000";

// Both hosts the studio publishes. Cookies are scoped by host, so a creator
// who opened the studio at localhost has the token stored under "localhost"
// and nothing under "127.0.0.1". Checking only one meant the worker found no
// token, sent every capture request unauthenticated, got a 401 it never
// inspected, and LinkedIn capture failed silently and permanently.
const STUDIO_COOKIE_ORIGINS = [
  "http://127.0.0.1:8000",
  "http://localhost:8000"
];
const LOCAL_API_AUTH = STUDIO_ORIGIN + "/api/auth/cookies";
const LOCAL_INGEST_URL = STUDIO_ORIGIN + "/api/analytics/ingest";

const STUDIO_TOKEN_COOKIE = "inox_studio_token";
const STUDIO_TOKEN_HEADER = "X-Inox-Token";

// Paths the content script is permitted to reach through this worker.
//
// The content script runs inside the LinkedIn page, which means anything else
// running in that page can send it messages. An exact allowlist keeps a
// compromised or hostile page script from using this worker as a general
// purpose proxy into the creator's local database.
const RELAYABLE_PATHS = new Set([
  "/api/analytics/ingest",
  "/api/v1/posts/bind-urn",
  "/api/v1/crm/interactions/ingest",
  // Onboarding (own_pages.js). Every write is refused by the studio unless it
  // belongs to the creator the studio has confirmed.
  "/api/v1/bridge/heartbeat",
  "/api/v1/identity/me",
  "/api/v1/identity/observe",
  "/api/v1/self/posts/ingest",
  "/api/v1/self/outbound/ingest",
  "/api/v1/self/imports/pending",
  "/api/v1/self/imports/event"
]);

/**
 * Reads the studio's access token.
 *
 * The token is issued to 127.0.0.1 as an HttpOnly, SameSite=Strict cookie, so
 * neither another site nor a script on the studio page itself can read it.
 * chrome.cookies.get is a privileged API and reads HttpOnly cookies given the
 * host permission the user granted at install, which is why this works and a
 * page script would not.
 */
function getStudioToken() {
  return new Promise((resolve) => {
    let remaining = STUDIO_COOKIE_ORIGINS.length;
    let found = null;

    const settle = () => {
      remaining -= 1;
      if (found || remaining === 0) resolve(found);
    };

    try {
      STUDIO_COOKIE_ORIGINS.forEach((origin) => {
        chrome.cookies.get({ url: origin, name: STUDIO_TOKEN_COOKIE }, (cookie) => {
          if (!found && cookie && cookie.value) found = cookie.value;
          settle();
        });
      });
    } catch (err) {
      resolve(null);
    }
  });
}

/**
 * The only way this extension talks to the studio.
 *
 * Every call goes out from the service worker, so the request carries
 * Origin: chrome-extension://<id> rather than https://www.linkedin.com. That
 * distinction is the whole point: the studio trusts this extension, and must
 * not trust arbitrary scripts running on a page the creator happens to visit.
 */
async function studioFetch(path, options) {
  const token = await getStudioToken();
  const headers = Object.assign(
    { "Content-Type": "application/json" },
    (options && options.headers) || {}
  );
  if (token) headers[STUDIO_TOKEN_HEADER] = token;

  return fetch(STUDIO_ORIGIN + path, Object.assign({}, options || {}, { headers }));
}

// Sensitive authentication token keys to sanitize from telemetry
const SENSITIVE_AUTH_KEYS = new Set([
  "li_at",
  "JSESSIONID",
  "bcookie",
  "bscookie",
  "lidc",
  "authorization",
  "x-li-track",
  "csrf-token",
  "csrftoken",
  "cookie",
  "cookies",
  "sessionkey",
  "authtoken",
  "accesstoken"
]);

/**
 * Recursively strips authentication credentials and sensitive tokens from payloads.
 */
function sanitizeTelemetryPayload(obj) {
  if (!obj || typeof obj !== "object") {
    return obj;
  }
  if (Array.isArray(obj)) {
    return obj.map(sanitizeTelemetryPayload);
  }
  const clean = {};
  for (const [key, val] of Object.entries(obj)) {
    const lowerKey = key.toLowerCase();
    if (SENSITIVE_AUTH_KEYS.has(key) || SENSITIVE_AUTH_KEYS.has(lowerKey)) {
      continue;
    }
    if (typeof val === "object" && val !== null) {
      clean[key] = sanitizeTelemetryPayload(val);
    } else {
      clean[key] = val;
    }
  }
  return clean;
}

// The session is captured when the creator asks, never on a timer.
//
// This used to copy li_at and JSESSIONID into the studio every 15 minutes.
// Nothing that reads LinkedIn needs them: every capture reads the page the
// creator has open. The one feature that does is the live send, which hands a
// post to LinkedIn's scheduler, and the creator chose to keep that feature on
// the condition that the session is stored only for it. So the popup's Sync
// button captures it, the live send's refusal says to press that button, and
// the Setup screen shows whether one is held with a Delete control.
//
// An install that ran an earlier version still has the alarm registered, and
// alarms outlive the code that created them, so it is cleared here as well as
// no longer created.
chrome.runtime.onInstalled.addListener(() => {
  console.log(`[Studio Bridge v${chrome.runtime.getManifest().version}] Service worker installed.`);
  chrome.alarms.clear("studio_periodic_sync");
});
chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.clear("studio_periodic_sync");
});

// Check and sync session tokens
async function syncActiveSessionToStudio() {
  try {
    const li_at = await getCookie("li_at");
    const jsessionid = await getCookie("JSESSIONID");

    if (li_at && jsessionid) {
      const response = await studioFetch("/api/auth/cookies", {
        method: "POST",
        body: JSON.stringify({
          li_at: li_at.value,
          JSESSIONID: jsessionid.value
        })
      });
      if (response && !response.ok) {
        console.warn(
          "[Studio Bridge] The studio refused the session sync (" + response.status +
          "). If this is 401 the extension has no token: open the studio once so it issues one."
        );
      } else {
        console.log("[Studio Bridge] Background session sync completed successfully.");
      }
    }
  } catch (err) {
    console.debug("[Studio Bridge] Background sync skipped (server offline or not logged in):", err.message);
  }
}

function getCookie(name) {
  return new Promise((resolve) => {
    chrome.cookies.get({ url: "https://www.linkedin.com", name: name }, (cookie) => {
      resolve(cookie);
    });
  });
}

/**
 * Forwards sanitized passive telemetry events to the local sharded ingress endpoint.
 */
async function forwardPassiveTelemetry(eventType, metadata) {
  try {
    const cleanPayload = sanitizeTelemetryPayload({
      event_type: eventType,
      source: "chrome_mv3_observer",
      timestamp: new Date().toISOString(),
      metadata: metadata || {}
    });

    await studioFetch("/api/analytics/ingest", {
      method: "POST",
      body: JSON.stringify(cleanPayload)
    });
    console.log(`[Studio Bridge] Passive telemetry dispatched for ${eventType}`);
  } catch (err) {
    console.debug("[Studio Bridge] Telemetry dispatch skipped (studio offline):", err.message);
  }
}

// Intercept LinkedIn Voyager API responses passively
chrome.webRequest.onCompleted.addListener(
  (details) => {
    const url = details.url;

    // 1. Post impressions and feed analytics
    if (url.includes("/voyager/api/feed/updatesV2")) {
      console.log("[Studio Bridge] Passively intercepted Feed Updates response:", url);
      forwardPassiveTelemetry("feed_updates_v2", {
        url: url.split("?")[0],
        statusCode: details.statusCode,
        method: details.method
      });
    }

    // 2. Profile views and viewer seniority
    else if (url.includes("/voyager/api/identity/profiles")) {
      console.log("[Studio Bridge] Passively intercepted Profile Telemetry response:", url);
      forwardPassiveTelemetry("profile_views_seniority", {
        url: url.split("?")[0],
        statusCode: details.statusCode,
        method: details.method
      });
    }

    // 3. Creator Analytics and GraphQL creator telemetry
    else if (url.includes("voyager/api/identity/dash/creatorAnalytics") || 
        (url.includes("voyager/api/graphql") && url.includes("creator"))) {
      // Observed, not intercepted: onCompleted carries no response body.
      // This branch used to also call syncActiveSessionToStudio(), which made
      // the backend issue its own authenticated request to LinkedIn. Observing
      // that a page loaded must never cause a new request.
      console.log("[Studio Bridge] Observed creator analytics request:", url);
      forwardPassiveTelemetry("creator_analytics", {
        url: url.split("?")[0],
        statusCode: details.statusCode
      });
    }
  },
  { urls: ["https://www.linkedin.com/voyager/api/*"] }
);

// Message broker between Side Panel, Popup, and Content Script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "OPEN_SIDE_PANEL") {
    chrome.sidePanel.open({ windowId: sender.tab ? sender.tab.windowId : undefined })
      .then(() => sendResponse({ status: "opened" }))
      .catch((err) => sendResponse({ status: "error", error: err.message }));
    return true;
  }

  if (message.action === "SYNC_NOW") {
    syncActiveSessionToStudio()
      .then(() => sendResponse({ status: "synced" }))
      .catch((err) => sendResponse({ status: "error", error: err.message }));
    return true;
  }

  // Relay for the content script.
  //
  // The content script can no longer call the studio directly, because a
  // request it makes carries the LinkedIn origin and the studio refuses that.
  // It asks this worker instead, and only for paths on the allowlist.
  if (message.action === "STUDIO_API") {
    const path = message.path || "";
    if (!RELAYABLE_PATHS.has(path)) {
      sendResponse({ status: "error", error: "path not permitted: " + path });
      return true;
    }
    studioFetch(path, {
      method: message.method || "POST",
      body: message.body ? JSON.stringify(sanitizeTelemetryPayload(message.body)) : undefined
    })
      .then(res => res.json().catch(() => ({})).then(data => ({ ok: res.ok, httpStatus: res.status, data })))
      // The HTTP code is reported as httpStatus, never as status. Spreading a
      // result carrying its own `status` over this object silently replaced
      // the literal "success" with the number 200, and the content script
      // tests `response.status !== "success"`, so every relayed capture
      // resolved to null while appearing to succeed.
      .then(result => sendResponse({
        status: result.ok ? "success" : "error",
        httpStatus: result.httpStatus,
        data: result.data
      }))
      .catch(err => sendResponse({ status: "error", error: err.message }));
    return true;
  }

  if (message.action === "INGEST_ANALYTICS") {
    const cleanPayload = sanitizeTelemetryPayload(message.payload);
    studioFetch("/api/analytics/ingest", {
      method: "POST",
      body: JSON.stringify(cleanPayload)
    })
      .then(res => res.json())
      .then(data => sendResponse({ status: "success", data }))
      .catch(err => sendResponse({ status: "error", error: err.message }));
    return true;
  }
});
