// -------------------------------------------------------------
// Inox Hydra Bridge: Background Service Worker (Manifest V3)
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

// Which version of the studio's ingest contract this extension speaks.
// studio/backend/ingest_contract.py holds the same number and the whole
// contract in prose. Every write says it, so a studio newer than the
// extension can tell the creator to press Reload once, instead of the two
// sides disagreeing about a field name and losing captures quietly.
const INGEST_CONTRACT_VERSION = 1;

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
  "/api/v1/bridge/capture",
  // Voyager API interception (voyager_schema.js + content.js). Structured JSON
  // captured from LinkedIn's network layer, far more reliable than DOM scraping.
  "/api/v1/bridge/voyager-ingest",
  // Schema drift telemetry. When a Voyager response no longer matches the
  // expected field structure, the extension reports what changed so the backend
  // can serve an updated schema without requiring an extension update.
  "/api/v1/bridge/schema-drift",
  "/api/v1/identity/me",
  "/api/v1/identity/observe",
  "/api/v1/self/posts/ingest",
  "/api/v1/self/posts/analytics",
  "/api/v1/self/outbound/ingest",
  "/api/v1/self/imports/pending",
  "/api/v1/self/imports/event"
]);

// What the popup and side panel may read, through PANEL_API. Reads only, and
// only from the extension's own pages, never from a content script.
const PANEL_PATHS = [
  /^\/api\/analytics\/kpis$/,
  /^\/api\/leads$/,
  /^\/api\/posts$/,
  /^\/api\/leads\/[A-Za-z0-9_.:-]+\/dm-script$/,
  /^\/api\/v1\/onboarding\/state$/,
  /^\/api\/v1\/extension\/health$/
];

// The one write the side panel makes: bookkeeping for a post the studio itself
// just placed in LinkedIn's composer. It has its own action and its own list,
// so PANEL_API stays read-only and the page relay above stays closed to it.
// Sent through STUDIO_API it was refused there, silently, so injected posts
// never got the row that later attribution attaches to.
const PANEL_WRITE_PATHS = new Set([
  "/api/v1/posts/injected"
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
function readTokenCookie() {
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

async function getStudioToken() {
  let token = await readTokenCookie();
  if (token) return token;

  try {
    await fetch(STUDIO_ORIGIN + "/", { method: "GET", credentials: "include" });
    token = await readTokenCookie();
  } catch (err) {
    // Studio server might not be running yet.
  }
  return token;
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

// Copies the LinkedIn session into the studio, when the creator presses Sync.
//
// Returns what happened in words the popup can show, because this is now the
// only way a session reaches the studio and a silent failure here means the
// live send stays in mock mode with no explanation. The popup used to make
// this request itself with a bare fetch, which carries no studio token, so
// every press answered 401 and was reported as "server not reachable".
async function syncActiveSessionToStudio() {
  const li_at = await getCookie("li_at");
  const jsessionid = await getCookie("JSESSIONID");
  if (!li_at || !jsessionid) {
    return { status: "not_signed_in", message: "Sign in to LinkedIn in this browser first." };
  }

  // Which account the session belongs to, as own_pages.js noted it on the
  // creator's own profile, and that member's id, which Send to LinkedIn
  // names as the post's author. The id goes only with the account it was
  // read for; neither is sent once the sign-in has changed since.
  const account = await new Promise((resolve) => {
    try {
      chrome.storage.local.get(["signedInVanity", "signedInMemberUrn"], (items) => resolve(items || {}));
    } catch (err) {
      resolve({});
    }
  });
  const vanity = account.signedInVanity || null;
  const member = account.signedInMemberUrn;
  const memberUrn = member && vanity && member.vanity === vanity ? member.urn : null;

  let response;
  try {
    response = await studioFetch("/api/auth/cookies", {
      method: "POST",
      body: JSON.stringify({ li_at: li_at.value, JSESSIONID: jsessionid.value, vanity, member_urn: memberUrn })
    });
  } catch (err) {
    return { status: "unreachable", message: "The studio is not running on port 8000." };
  }
  if (response.status === 401 || response.status === 403) {
    return {
      status: "no_token",
      message: "The studio refused this browser. Open http://127.0.0.1:8000 once in this browser, then press Sync again."
    };
  }
  if (!response.ok) {
    return { status: "error", message: "The studio refused the session (" + response.status + ")." };
  }
  if (!memberUrn) {
    return {
      status: "synced",
      message: "Session saved, but not yet which account it is. Open your own LinkedIn profile in this browser, then press Sync again."
    };
  }
  return { status: "synced", message: "Session saved to the studio, for sending to LinkedIn only." };
}

function getCookie(name) {
  return new Promise((resolve) => {
    chrome.cookies.get({ url: "https://www.linkedin.com", name: name }, (cookie) => {
      resolve(cookie);
    });
  });
}

// The LinkedIn account this browser is signed in to (signedInVanity, noted by
// own_pages.js on the creator's own profile) holds only until the sign-in
// changes. Signing out, or in as someone else, removes or replaces li_at, and
// the analytics read after that must not be filed as the previous account's.
// The next visit to your own profile notes it again.
//
// A rewrite of the same value is not a change. LinkedIn refreshes the cookie,
// and forgetting on every write locked the creator out of their analytics
// each time. So the worker keeps a digest of li_at as it was when the account
// was noted (never the cookie itself) and forgets only when the cookie is
// removed or its value differs from that.
const LI_AT_DIGEST_KEY = "signedInCookieDigest";

async function liAtDigest(value) {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value || ""));
  return Array.from(new Uint8Array(bytes)).slice(0, 16).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function forgetSignedInMember() {
  chrome.storage.local.remove(["signedInVanity", "signedInMemberUrn", LI_AT_DIGEST_KEY]);
}

try {
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local" || !changes.signedInVanity || !changes.signedInVanity.newValue) return;
    chrome.cookies.get({ url: "https://www.linkedin.com", name: "li_at" }, async (cookie) => {
      if (!cookie || !cookie.value) return;
      chrome.storage.local.set({ [LI_AT_DIGEST_KEY]: await liAtDigest(cookie.value) });
    });
  });
  chrome.cookies.onChanged.addListener((change) => {
    const cookie = change && change.cookie;
    if (!cookie || cookie.name !== "li_at" || !/(^|\.)linkedin\.com$/.test(cookie.domain || "")) return;
    // An overwrite arrives as a removal followed by the new cookie; the new
    // cookie decides.
    if (change.removed && change.cause === "overwrite") return;
    if (change.removed) {
      forgetSignedInMember();
      return;
    }
    chrome.storage.local.get(LI_AT_DIGEST_KEY, async (items) => {
      const known = items && items[LI_AT_DIGEST_KEY];
      if (!known || known !== await liAtDigest(cookie.value)) forgetSignedInMember();
    });
  });
} catch (err) {
  // No cookies API (an old browser): the studio still refuses a mismatch.
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

// Notes which of LinkedIn's data requests a page made: address, status and
// method, never contents. Watching LinkedIn's requests is network reading,
// so it follows the same switch as the interceptor and is off by default.
chrome.webRequest.onCompleted.addListener(
  (details) => {
    networkReadingEnabled().then((enabled) => {
      if (enabled) observeLinkedInRequest(details);
    });
  },
  { urls: ["https://www.linkedin.com/voyager/api/*"] }
);

function observeLinkedInRequest(details) {
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
}

// Message broker between Side Panel, Popup, and Content Script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "OPEN_SIDE_PANEL") {
    chrome.sidePanel.open({ windowId: sender.tab ? sender.tab.windowId : undefined })
      .then(() => sendResponse({ status: "opened" }))
      .catch((err) => sendResponse({ status: "error", error: err.message }));
    return true;
  }

  // Reads for the popup and side panel.
  //
  // They used to fetch the studio directly. An extension page's fetch carries
  // no studio token, so every call was refused with a 401, and each page then
  // reported something else: the side panel said "No prospects yet", the popup
  // kept a green "Online" written into its HTML. The creator had no way to see
  // that nothing was working.
  //
  // So they ask this worker, which carries the token, and get the HTTP status
  // back to report. Only from the extension's own pages (a content script's
  // message carries sender.tab), only GET, and only these paths.
  if (message.action === "PANEL_API") {
    const fromOwnPage = !sender.tab && sender.id === chrome.runtime.id &&
      typeof sender.url === "string" && sender.url.startsWith(chrome.runtime.getURL(""));
    const path = String(message.path || "");
    const bare = path.split("?")[0];
    if (!fromOwnPage || !PANEL_PATHS.some((pattern) => pattern.test(bare))) {
      sendResponse({ ok: false, httpStatus: 0, reason: "refused" });
      return true;
    }
    studioFetch(path, { method: "GET" })
      .then(res => res.json().catch(() => ({})).then(data => ({ ok: res.ok, httpStatus: res.status, data })))
      .then(result => sendResponse(result))
      .catch(() => sendResponse({ ok: false, httpStatus: 0, reason: "unreachable" }));
    return true;
  }

  if (message.action === "PANEL_WRITE") {
    const fromOwnPage = !sender.tab && sender.id === chrome.runtime.id &&
      typeof sender.url === "string" && sender.url.startsWith(chrome.runtime.getURL(""));
    const path = String(message.path || "");
    if (!fromOwnPage || !PANEL_WRITE_PATHS.has(path)) {
      sendResponse({ ok: false, httpStatus: 0, reason: "refused" });
      return true;
    }
    studioFetch(path, { method: "POST", body: JSON.stringify(message.body || {}) })
      .then(res => res.json().catch(() => ({})).then(data => ({ ok: res.ok, httpStatus: res.status, data })))
      .then(result => sendResponse(result))
      .catch(() => sendResponse({ ok: false, httpStatus: 0, reason: "unreachable" }));
    return true;
  }

  if (message.action === "SYNC_NOW") {
    // From the extension's own popup only. A message from a content script
    // carries sender.tab, and copying the session is not something a LinkedIn
    // page, or anything injected into one, gets to ask for.
    if (sender.tab || sender.id !== chrome.runtime.id) {
      sendResponse({ status: "refused", message: "Session sync is only available from the extension popup." });
      return true;
    }
    syncActiveSessionToStudio()
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ status: "error", message: err.message }));
    return true;
  }

  // Relay for the content script.
  //
  // The content script can no longer call the studio directly, because a
  // request it makes carries the LinkedIn origin and the studio refuses that.
  // It asks this worker instead, and only for paths on the allowlist.
  if (message.action === "STUDIO_API") {
    const path = message.path || "";
    const tabId = sender && sender.tab && typeof sender.tab.id === "number" ? sender.tab.id : null;
    if (NETWORK_READING_PATHS.has(path)) {
      networkReadingEnabled().then((enabled) => {
        if (!enabled) {
          sendResponse({ status: "error", error: "Network reading is off." });
          return;
        }
        relayToStudio(message, path, sendResponse, tabId);
      });
      return true;
    }
    if (!RELAYABLE_PATHS.has(path)) {
      sendResponse({ status: "error", error: "path not permitted: " + path });
      return true;
    }
    relayToStudio(message, path, sendResponse, tabId);
    return true;
  }

  // The side panel opened: the creator has seen what the badge counted.
  if (message.action === "PANEL_OPENED") {
    const fromOwnPage = !sender.tab && sender.id === chrome.runtime.id;
    if (!fromOwnPage) {
      sendResponse({ status: "refused" });
      return true;
    }
    clearBadgeCounts().then(() => sendResponse({ status: "cleared" }));
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

// -------------------------------------------------------------
// A capture the studio was too busy for is kept, never dropped
// -------------------------------------------------------------
// The studio answers 503 "the studio's database is busy" with Retry-After
// when a write loses the database lock for longer than it waits, and a
// request can also end with no answer at all. This worker used to report
// either to the content script and forget it, so the person captured was
// gone from the post with nothing said. A capture is now asked again a few
// times, and if the studio is still busy it is kept in the extension's own
// storage and sent with the next relay that gets through.
//
// Repeating a capture is safe: one interaction row per person, post and
// comment (migrations.py's unique key, ON CONFLICT on
// /api/v1/crm/interactions/ingest), so a payload that arrives twice updates
// when it was last seen, exactly as reopening the post does, and never
// counts as a second engagement. tests/test_qc2_ci_windows2_capture.py
// ::test_the_same_capture_sent_twice_is_one_engagement holds this.
const BUSY_ATTEMPTS = 3;
const BUSY_WAIT_MS = 400;
const BUSY_WAIT_LEAST_MS = 50;
// Waiting out a whole Retry-After in the relay would stall the capture of
// the next engager, and the queue below means it does not have to.
const BUSY_WAIT_CAP_MS = 2000;
// What is worth keeping: a write whose payload can arrive twice without
// counting twice. A heartbeat or a read is about this moment and is not kept.
//
// This was one path of nine, so the creator's engagers survived a busy studio
// and their posts, their own posts' figures, their comments and reactions and
// their profile did not. Every path here carries the creator's own data and
// is idempotent on the studio's side: an upsert keyed on the thing itself, so
// the same payload arriving twice updates when it was last seen and never
// counts twice. The bookkeeping paths (heartbeat, capture log, schema drift,
// import events) are about a moment that has passed and are not kept.
const KEEP_WHEN_BUSY = new Set([
  "/api/v1/crm/interactions/ingest",
  "/api/v1/self/posts/ingest",
  "/api/v1/self/posts/analytics",
  "/api/v1/self/outbound/ingest",
  "/api/v1/identity/observe",
  "/api/v1/posts/bind-urn",
  "/api/v1/bridge/voyager-ingest",
  "/api/analytics/ingest"
]);
// Draining used to happen only on browser start-up or after a later
// successful relay, so a creator who closed LinkedIn with captures waiting
// kept them until the next browser start. The alarms permission was already
// in the manifest and unused.
const DRAIN_ALARM = "studio_drain_kept";
const DRAIN_EVERY_MINUTES = 1;
// Captures kept at once. A studio left busy or closed for a day must not
// grow the extension's storage without limit, so the newest are kept.
const KEPT_CAPTURES_KEY = "keptCaptures";
const KEPT_CAPTURES_LIMIT = 200;

function waitFor(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// How long to wait before asking again: what the studio asked for, with
// jitter, because a page's engagers are relayed one after another and a
// fixed wait would send them all back at the same moment.
//
// Line comments rather than a block: the file's webRequest filter holds the
// characters that open one, and more than one reader of this source pairs
// them naively.
function busyWaitMs(retryAfter, attempt) {
  const asked = Number(retryAfter);
  const base = Number.isFinite(asked) && asked >= 0
    ? asked * 1000
    : BUSY_WAIT_MS * Math.pow(2, attempt - 1);
  const bounded = Math.min(Math.max(base, BUSY_WAIT_LEAST_MS), BUSY_WAIT_CAP_MS);
  return Math.round(bounded * (0.5 + Math.random()));
}

// One request to the studio, as what happened rather than as an exception.
async function askStudio(path, method, body) {
  let response;
  try {
    response = await studioFetch(path, { method, body });
  } catch (err) {
    // No answer at all: the studio may have taken the write and never
    // replied, which is why only a repeatable payload is kept below.
    return { ok: false, httpStatus: 0, data: {}, busy: true, later: true, error: err.message };
  }
  const data = await response.json().catch(() => ({}));
  const retryAfter = response.headers && response.headers.get ? response.headers.get("Retry-After") : null;
  return {
    ok: response.ok,
    httpStatus: response.status,
    data,
    busy: response.status === 503,
    // Whether asking again can help. The studio's database being busy is one
    // reason; a browser the studio has not been paired with yet (401, 403)
    // and a studio that is restarting (any 5xx, or no answer at all) are the
    // others, and all of them end as soon as the creator opens the studio.
    // A 409, 400 or 422 is the studio deciding, and asking again cannot
    // change its mind: those used to throw away the whole waiting queue.
    later: response.status === 0 || response.status === 401 || response.status === 403
      || response.status >= 500,
    retryAfter,
    error: response.ok ? null : "the studio answered " + response.status
  };
}

function readKeptCaptures() {
  return new Promise((resolve) => {
    try {
      chrome.storage.local.get(KEPT_CAPTURES_KEY, (items) => {
        const kept = items && items[KEPT_CAPTURES_KEY];
        resolve(Array.isArray(kept) ? kept : []);
      });
    } catch (err) {
      resolve([]);
    }
  });
}

function writeKeptCaptures(kept) {
  return new Promise((resolve) => {
    try {
      chrome.storage.local.set({ [KEPT_CAPTURES_KEY]: kept.slice(-KEPT_CAPTURES_LIMIT) }, () => resolve());
    } catch (err) {
      resolve();
    }
  });
}

// One queue, one writer. Keeping and draining both read the whole array and
// write it back, so a drain that started while a capture was being kept
// overwrote it and the capture was lost. Both now take a turn in the same
// chain below.
async function keepCaptureNow(path, body) {
  const kept = await readKeptCaptures();
  kept.push({ path, body, at: new Date().toISOString() });
  if (kept.length > KEPT_CAPTURES_LIMIT) {
    console.warn("[Studio Bridge] More than " + KEPT_CAPTURES_LIMIT +
      " captures are waiting for the studio; the oldest are dropped.");
  }
  await writeKeptCaptures(kept);
  await afterQueueChanged();
}

// One turn at a time, so two relays finishing together cannot send the same
// kept capture twice, and a keep cannot race a drain.
let queueTurn = Promise.resolve();

function inTurn(work) {
  queueTurn = queueTurn.then(work).catch(() => {});
  return queueTurn;
}

function keepCapture(path, body) {
  return inTurn(() => keepCaptureNow(path, body));
}

function sendKeptCapturesLater() {
  return inTurn(sendKeptCaptures);
}

// Sends what was kept, oldest first. It stops at the first answer that asking
// again could fix, so the rest stay for the next time; this used to stop only
// on a busy studio and shift everything else off the front, which threw the
// whole queue away when the real problem was a browser the studio had not
// been paired with. A capture the studio has decided about is dropped, and
// the reason is remembered so the creator can be told.
async function sendKeptCaptures() {
  const kept = await readKeptCaptures();
  if (kept.length === 0) {
    await afterQueueChanged();
    return 0;
  }
  let sent = 0;
  while (kept.length > 0) {
    const item = kept[0];
    const answer = await askStudio(item.path, "POST", item.body);
    if (answer.later) break;
    kept.shift();
    if (answer.ok) {
      sent += 1;
      await noteCapture(item.path, answer, null, false);
    } else {
      await rememberRefusal(item.path, answer);
    }
  }
  await writeKeptCaptures(kept);
  await afterQueueChanged();
  return sent;
}

// -------------------------------------------------------------
// What is waiting, and what was refused: said once, where it can be read
// -------------------------------------------------------------
// Nothing in the product could say that work was waiting. The count goes to
// the studio on a heartbeat, so a screen can show it, and into the
// extension's own storage, so the side panel can show it without the studio.
const WAITING_KEY = "waitingCaptures";
const LAST_REFUSAL_KEY = "lastRefusal";
const RELOAD_NOTICE_KEY = "reloadNoticeFor";

function storeLocal(values) {
  return new Promise((resolve) => {
    try {
      chrome.storage.local.set(values, () => resolve());
    } catch (err) {
      resolve();
    }
  });
}

function readLocal(key) {
  return new Promise((resolve) => {
    try {
      chrome.storage.local.get(key, (items) => resolve((items && items[key]) || null));
    } catch (err) {
      resolve(null);
    }
  });
}

async function afterQueueChanged() {
  const kept = await readKeptCaptures();
  await storeLocal({ [WAITING_KEY]: { waiting: kept.length, oldest_at: kept.length ? kept[0].at : null } });
  if (kept.length > 0) scheduleDrain();
  else clearDrain();
  await paintBadge();
  reportWaiting(kept);
}

// A refusal the studio has decided on, kept so the side panel can name it.
// Every one of these used to be discarded, including the one a creator meets
// most: "import your posts first".
async function rememberRefusal(path, answer) {
  const data = (answer && answer.data) || {};
  await storeLocal({
    [LAST_REFUSAL_KEY]: {
      path,
      at: new Date().toISOString(),
      httpStatus: answer.httpStatus,
      reason: data.reason || "refused",
      message: data.message || data.detail || answer.error || "The studio refused this capture.",
      show: data.show !== false
    }
  });
}

// Tells the studio how many captures are waiting, so a screen can show the
// number. It rides on the heartbeat, which already carries the version, and
// is best effort: a studio that cannot be reached is the usual reason for a
// queue in the first place.
async function reportWaiting(kept) {
  const body = {
    extension_version: chrome.runtime.getManifest().version,
    contract_version: INGEST_CONTRACT_VERSION,
    page_kind: "service_worker",
    waiting_captures: kept.length,
    oldest_waiting_at: kept.length ? kept[0].at : null,
    // What this worker can see of network reading: the switch and whether
    // the browser holds the reader registered. A page's figures (the
    // marker, the calls it counted) are the page's to report, so they are
    // null here and the studio keeps the newest page's.
    network_reading: await workerNetworkReading()
  };
  studioFetch("/api/v1/bridge/heartbeat", {
    method: "POST",
    body: JSON.stringify(body)
  }).then((response) => response.json().catch(() => ({})))
    .then((answer) => {
      const shake = answer && answer.handshake;
      if (shake && shake.reload_required) noteReloadNeeded(shake);
    })
    .catch(() => {});
}

// The studio speaks a newer contract than this extension. Said once per
// studio contract version, because an extension that needs reloading would
// otherwise say so on every heartbeat for as long as the browser is open.
async function noteReloadNeeded(shake) {
  const seen = await readLocal(RELOAD_NOTICE_KEY);
  if (seen === shake.contract_version) return;
  await storeLocal({ [RELOAD_NOTICE_KEY]: shake.contract_version, studioHandshake: shake });
  console.warn("[Studio Bridge] " + shake.message);
}

// -------------------------------------------------------------
// The capture confirmation: the badge and the panel, not the page
// -------------------------------------------------------------
// Every relayed write passes through here, so this worker knows the moment
// a capture lands, before the studio draws anything. It writes the last
// capture to the extension's storage for the side panel and popup, which
// render from storage.onChanged with no studio call, and counts this
// session's captures on the action badge, per tab. The confirmation used to
// be a notice drawn into LinkedIn's page (decision D3 moved it here); what
// the creator must act on still appears there.
//
// The colours are the studio's tokens as chrome.action takes them, a colour
// array rather than a CSS variable, because the toolbar is not the studio's
// document: --studio-orange, --studio-green and --studio-on-signal from
// studio/ui/src/styles/tokens.css.
const LAST_CAPTURE_KEY = "lastCapture";
const BADGE_COUNTS_KEY = "badgeCounts";
const LAST_DRIFT_KEY = "lastDrift";
const LAST_VOYAGER_CAPTURE_KEY = "lastVoyagerCaptureAt";
const BADGE_ORANGE = [233, 85, 44, 255];
const BADGE_GREEN = [22, 138, 97, 255];
const BADGE_TEXT = [10, 10, 10, 255];
const DRIFT_NOTICED_PREFIX = "driftNoticed:";

function actionApi() {
  return typeof chrome !== "undefined" && chrome.action ? chrome.action : null;
}

function actionCall(method, details) {
  return new Promise((resolve) => {
    const api = actionApi();
    if (!api || typeof api[method] !== "function") {
      resolve(false);
      return;
    }
    try {
      api[method](details, () => {
        void chrome.runtime.lastError;
        resolve(true);
      });
    } catch (err) {
      resolve(false);
    }
  });
}

// What the studio answered, in the fields the creator can be shown. Never
// the capture itself: the panel names the kind of thing and when, not the
// person.
function captureOutcome(answer) {
  const data = (answer && answer.data) || {};
  const counts = {};
  for (const field of ["written", "skipped", "recorded", "buckets_ingested", "followers_saved", "items_kept"]) {
    if (typeof data[field] === "number") counts[field] = data[field];
  }
  return { outcome: data.outcome || data.status || null, counts };
}

async function noteCapture(path, answer, tabId, kept) {
  const said = captureOutcome(answer);
  const ok = !!(answer && answer.ok);
  await storeLocal({
    [LAST_CAPTURE_KEY]: {
      path,
      at: new Date().toISOString(),
      ok,
      kept: kept === true,
      httpStatus: answer ? answer.httpStatus : 0,
      outcome: kept ? "kept" : said.outcome,
      counts: said.counts,
      tabId
    }
  });
  if (ok && path === "/api/v1/bridge/voyager-ingest") {
    await storeLocal({ [LAST_VOYAGER_CAPTURE_KEY]: new Date().toISOString() });
  }
  if (ok && tabId !== null && tabId !== undefined) {
    const counts = (await readLocal(BADGE_COUNTS_KEY)) || {};
    counts[tabId] = (counts[tabId] || 0) + 1;
    await storeLocal({ [BADGE_COUNTS_KEY]: counts });
    await actionCall("setBadgeText", { tabId, text: String(counts[tabId]) });
  }
  await paintBadge();
}

async function clearBadgeCounts() {
  const counts = (await readLocal(BADGE_COUNTS_KEY)) || {};
  for (const tabId of Object.keys(counts)) {
    await actionCall("setBadgeText", { tabId: Number(tabId), text: "" });
  }
  await storeLocal({ [BADGE_COUNTS_KEY]: {} });
  await paintBadge();
}

// Badge persistence across worker restarts is undocumented, so the counts
// are kept in storage and put back when the browser starts.
async function restoreBadge() {
  const counts = (await readLocal(BADGE_COUNTS_KEY)) || {};
  for (const tabId of Object.keys(counts)) {
    await actionCall("setBadgeText", { tabId: Number(tabId), text: String(counts[tabId]) });
  }
  await paintBadge();
}

// Session storage holds what was noticed this browser session; a browser
// without it (an old harness) keeps the set in memory for this worker's life.
const driftNoticedHere = new Set();

function sessionGet(key) {
  return new Promise((resolve) => {
    try {
      if (!chrome.storage.session) {
        resolve(driftNoticedHere.has(key) ? true : null);
        return;
      }
      chrome.storage.session.get(key, (items) => resolve((items && items[key]) || null));
    } catch (err) {
      resolve(null);
    }
  });
}

function sessionSet(key, value) {
  return new Promise((resolve) => {
    try {
      if (!chrome.storage.session) {
        driftNoticedHere.add(key);
        resolve();
        return;
      }
      chrome.storage.session.set({ [key]: value }, () => resolve());
    } catch (err) {
      resolve();
    }
  });
}

async function driftNoticedThisSession() {
  if (!chrome.storage.session) return driftNoticedHere.size > 0;
  const items = await new Promise((resolve) => {
    try {
      chrome.storage.session.get(null, (found) => resolve(found || {}));
    } catch (err) {
      resolve({});
    }
  });
  return Object.keys(items).some((key) => key.startsWith(DRIFT_NOTICED_PREFIX));
}

// A reader reported fields it could not read on a page that plainly had
// them. Said once per page kind per browser session, in the panel header
// and the badge colour, never in the page: it is a measurement the reader
// made, and the one failure a creator cannot see for themselves.
async function noteDrift(body) {
  if (!body || !Array.isArray(body.drift) || body.drift.length === 0) return;
  const pageKind = String(body.page_kind || "page").slice(0, 40);
  const key = DRIFT_NOTICED_PREFIX + pageKind;
  if (await sessionGet(key)) return;
  await sessionSet(key, new Date().toISOString());
  await storeLocal({
    [LAST_DRIFT_KEY]: {
      extractor: String(body.extractor || "").slice(0, 40),
      page_kind: pageKind,
      fields: body.drift.filter((d) => typeof d === "string").slice(0, 10),
      at: new Date().toISOString()
    }
  });
  await paintBadge();
}

async function paintBadge() {
  const waiting = (await readLocal(WAITING_KEY)) || {};
  const drift = (await driftNoticedThisSession()) ? await readLocal(LAST_DRIFT_KEY) : null;
  const waitingCount = typeof waiting.waiting === "number" ? waiting.waiting : 0;
  const attention = waitingCount > 0 || !!drift;
  await actionCall("setBadgeBackgroundColor", { color: attention ? BADGE_ORANGE : BADGE_GREEN });
  await actionCall("setBadgeTextColor", { color: BADGE_TEXT });
  let title = "Inox Hydra Bridge";
  if (waitingCount > 0) {
    title = "Inox Hydra: " + waitingCount + " capture(s) waiting for the studio";
  } else if (drift) {
    title = "Inox Hydra: cannot read " + drift.fields.join(", ").replace(/_/g, " ") +
      " on LinkedIn's " + drift.page_kind + " page. See Capture health in Setup.";
  }
  await actionCall("setTitle", { title });
}

async function workerNetworkReading() {
  const enabled = await networkReadingEnabled();
  let registered = null;
  try {
    const scripts = await chrome.scripting.getRegisteredContentScripts({ ids: [INTERCEPTOR_SCRIPT_ID] });
    registered = Array.isArray(scripts) && scripts.length > 0;
  } catch (err) {
    registered = null;
  }
  return {
    switch: enabled,
    registered,
    injected: null,
    voyager_calls_seen: null,
    matched: null,
    captured: null,
    last_capture_at: (await readLocal(LAST_VOYAGER_CAPTURE_KEY)) || null
  };
}

try {
  chrome.runtime.onStartup.addListener(() => { restoreBadge(); });
  if (chrome.tabs && chrome.tabs.onRemoved) {
    chrome.tabs.onRemoved.addListener(async (tabId) => {
      const counts = (await readLocal(BADGE_COUNTS_KEY)) || {};
      if (counts[tabId] !== undefined) {
        delete counts[tabId];
        await storeLocal({ [BADGE_COUNTS_KEY]: counts });
      }
    });
  }
} catch (err) {
  // No action or tabs API: the badge is simply not drawn.
}

function scheduleDrain() {
  try {
    chrome.alarms.create(DRAIN_ALARM, { periodInMinutes: DRAIN_EVERY_MINUTES });
  } catch (err) {
    // Alarms are unavailable only if the permission was removed; the drain
    // on the next successful relay still runs.
  }
}

function clearDrain() {
  try {
    chrome.alarms.clear(DRAIN_ALARM);
  } catch (err) {
    // Nothing to clear.
  }
}

chrome.runtime.onStartup.addListener(() => { sendKeptCapturesLater(); });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm && alarm.name === DRAIN_ALARM) sendKeptCapturesLater();
});

// Every write says which contract it speaks and which build sent it, so the
// studio knows what it is talking to without the page script having to
// remember to say. A body that names them already keeps its own values.
function stamped(body) {
  const payload = sanitizeTelemetryPayload(body) || {};
  if (typeof payload !== "object" || Array.isArray(payload)) return payload;
  if (payload.contract_version === undefined) payload.contract_version = INGEST_CONTRACT_VERSION;
  if (payload.extension_version === undefined) {
    payload.extension_version = chrome.runtime.getManifest().version;
  }
  return payload;
}

async function relayToStudio(message, path, sendResponse, tabId) {
  const method = message.method || "POST";
  const body = message.body ? JSON.stringify(stamped(message.body)) : undefined;
  if (tabId === undefined) tabId = null;
  let answer = { ok: false, httpStatus: 0, data: {}, busy: false, later: false, error: "not sent" };
  for (let attempt = 1; attempt <= BUSY_ATTEMPTS; attempt += 1) {
    answer = await askStudio(path, method, body);
    if (!answer.busy || attempt === BUSY_ATTEMPTS) break;
    await waitFor(busyWaitMs(answer.retryAfter, attempt));
  }
  // The HTTP code is reported as httpStatus, never as status. Spreading a
  // result carrying its own `status` over this object silently replaced
  // the literal "success" with the number 200, and the content script
  // tests `response.status !== "success"`, so every relayed capture
  // resolved to null while appearing to succeed.
  if (answer.ok) {
    const shake = answer.data && answer.data.handshake;
    if (shake && shake.reload_required) noteReloadNeeded(shake);
    sendResponse({ status: "success", httpStatus: answer.httpStatus, data: answer.data });
    // The creator's data landed: say so where the panel and badge read it.
    // A heartbeat or a capture log row is about a moment, not a capture.
    if (KEEP_WHEN_BUSY.has(path)) await noteCapture(path, answer, tabId, false);
    else if (path === "/api/v1/bridge/capture") await noteDrift(message.body);
    // Something got through, so anything kept has a chance now.
    sendKeptCapturesLater();
    return;
  }
  // Anything the creator can act on is kept, not only a busy studio: an
  // unpaired browser and a studio that is restarting both end as soon as the
  // creator opens it, and the capture is the creator's either way.
  if (answer.later && KEEP_WHEN_BUSY.has(path)) {
    await keepCapture(path, body);
    await noteCapture(path, answer, tabId, true);
    const waiting = (await readLocal(WAITING_KEY)) || {};
    sendResponse({
      status: "error",
      httpStatus: answer.httpStatus,
      data: answer.data,
      kept: true,
      waiting: waiting.waiting || 0,
      error: answer.busy
        ? "The studio is busy, so this capture is kept and sent again shortly."
        : "Your studio could not be reached, so this capture is kept and sent again shortly."
    });
    return;
  }
  // A refusal the studio decided on. The reason and the sentence travel back
  // to whoever asked, and are remembered for the side panel: every one of
  // them used to be collapsed to an error with nothing said.
  await rememberRefusal(path, answer);
  const refusal = answer.data || {};
  sendResponse({
    status: "error",
    httpStatus: answer.httpStatus,
    data: answer.data,
    reason: refusal.reason || null,
    message: refusal.message || refusal.detail || null,
    show: refusal.show === true,
    error: answer.error
  });
}

// -------------------------------------------------------------
// Network reading: off unless the creator switches it on
// -------------------------------------------------------------
// voyager_interceptor.js wraps window.fetch inside LinkedIn's own page and
// copies the JSON of responses LinkedIn's app already fetched. It is the part
// of the bridge most visible to LinkedIn, and the page readers and LinkedIn's
// own data archive cover what it adds, so it runs only after the creator turns
// it on in the popup, where what it does is written beside the switch.
//
// It used to be a static MAIN-world content script, injected again on every
// tab update and on request from content.js, with no way to turn it off. It
// is now registered while the setting is on and unregistered when it is off,
// and the two capture paths it feeds are refused below while it is off.
const NETWORK_READING_KEY = "networkReading";
const INTERCEPTOR_SCRIPT_ID = "inox-network-reading";
const NETWORK_READING_PATHS = new Set([
  "/api/v1/bridge/voyager-ingest",
  "/api/v1/bridge/schema-drift"
]);

function networkReadingEnabled() {
  return new Promise((resolve) => {
    try {
      chrome.storage.local.get(NETWORK_READING_KEY, (items) => {
        resolve(!chrome.runtime.lastError && !!items && items[NETWORK_READING_KEY] === true);
      });
    } catch (err) {
      resolve(false);
    }
  });
}

// One change at a time: two overlapping calls could each see the script as
// not yet registered, or not yet removed, and leave it out of step.
let networkReadingChange = Promise.resolve();

function applyNetworkReading(enabled) {
  networkReadingChange = networkReadingChange.then(() => applyNetworkReadingNow(enabled));
  return networkReadingChange;
}

async function applyNetworkReadingNow(enabled) {
  try {
    const registered = await chrome.scripting.getRegisteredContentScripts({ ids: [INTERCEPTOR_SCRIPT_ID] });
    if (enabled && registered.length === 0) {
      await chrome.scripting.registerContentScripts([{
        id: INTERCEPTOR_SCRIPT_ID,
        matches: ["https://*.linkedin.com/*"],
        js: ["voyager_interceptor.js"],
        runAt: "document_start",
        world: "MAIN",
        persistAcrossSessions: true
      }]);
    } else if (!enabled && registered.length > 0) {
      await chrome.scripting.unregisterContentScripts({ ids: [INTERCEPTOR_SCRIPT_ID] });
    }
  } catch (err) {
    console.warn("[Inox Hydra Bridge] Could not apply the network reading setting:", err);
  }
}

async function syncNetworkReading() {
  await applyNetworkReading(await networkReadingEnabled());
}

// The latest stored value wins, whatever order the change events arrive in.
async function followNetworkReadingSetting() {
  await applyNetworkReading(await networkReadingEnabled());
}

chrome.runtime.onInstalled.addListener(syncNetworkReading);
chrome.runtime.onStartup.addListener(syncNetworkReading);
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes[NETWORK_READING_KEY]) {
    followNetworkReadingSetting();
  }
});
