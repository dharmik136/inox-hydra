// -------------------------------------------------------------
// LinkedIn Studio Bridge: Background Service Worker (Manifest V3)
// -------------------------------------------------------------
const LOCAL_API_AUTH = "http://127.0.0.1:8000/api/auth/cookies";
const LOCAL_INGEST_URL = "http://127.0.0.1:8000/api/analytics/ingest";

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

// Configure alarms on installation
chrome.runtime.onInstalled.addListener(() => {
  console.log(`[Studio Bridge v${chrome.runtime.getManifest().version}] Service worker installed.`);
  // Setup automated periodic sync every 15 minutes
  chrome.alarms.create("studio_periodic_sync", { periodInMinutes: 15 });
});

// Periodic alarm listener
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "studio_periodic_sync") {
    syncActiveSessionToStudio();
  }
});

// Check and sync session tokens
async function syncActiveSessionToStudio() {
  try {
    const li_at = await getCookie("li_at");
    const jsessionid = await getCookie("JSESSIONID");

    if (li_at && jsessionid) {
      await fetch(LOCAL_API_AUTH, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          li_at: li_at.value,
          JSESSIONID: jsessionid.value
        })
      });
      console.log("[Studio Bridge] Background session sync completed successfully.");
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

    await fetch(LOCAL_INGEST_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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

  if (message.action === "INGEST_ANALYTICS") {
    const cleanPayload = sanitizeTelemetryPayload(message.payload);
    fetch(LOCAL_INGEST_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cleanPayload)
    })
      .then(res => res.json())
      .then(data => sendResponse({ status: "success", data }))
      .catch(err => sendResponse({ status: "error", error: err.message }));
    return true;
  }
});
