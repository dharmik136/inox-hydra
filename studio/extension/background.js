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
  // The creator's own account and content pages (own_insights.js, track 5).
  "/api/analytics/page-figures",
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
  // The LinkedIn account a capture was read in, which the studio routes by.
  if (options && options.account) headers[ACCOUNT_HEADER] = options.account;
  const init = Object.assign({}, options || {}, { headers });
  delete init.account;
  return fetch(STUDIO_ORIGIN + path, init);
}

// -------------------------------------------------------------
// One bridge per browser: where each capture came from
// -------------------------------------------------------------
// Every capture names where it was read (cycle 4, track 1, phase 2): an id
// minted once for this browser's install, the browser's name, the tab,
// window and document it came from, and the LinkedIn account the browser is
// signed in to, which is the creator's own (signedInVanity, noted on their
// own profile). The studio keeps one heartbeat and one capture row per
// browser and minute by it, hands a history import to one tab, and files
// each capture in the creator profile of that account (X-Inox-Account).
// Nothing in it names another member.
const BROWSER_INSTANCE_KEY = "browserInstanceId";
const ACCOUNT_HEADER = "X-Inox-Account";
let browserInstancePromise = null;

function browserInstanceId() {
  if (!browserInstancePromise) {
    browserInstancePromise = (async () => {
      const stored = await readLocal(BROWSER_INSTANCE_KEY);
      if (typeof stored === "string" && /^[A-Za-z0-9-]{8,64}$/.test(stored)) return stored;
      const minted = crypto.randomUUID();
      await storeLocal({ [BROWSER_INSTANCE_KEY]: minted });
      return minted;
    })().catch(() => {
      browserInstancePromise = null;
      return null;
    });
  }
  return browserInstancePromise;
}

// The browser's own name, for Setup to tell two bridges apart. A label only.
function browserName() {
  try {
    const brands = ((navigator.userAgentData && navigator.userAgentData.brands) || []).map((b) => b.brand);
    for (const name of ["Brave", "Microsoft Edge", "Opera", "Vivaldi", "Google Chrome", "Chromium"]) {
      if (brands.includes(name)) return name;
    }
  } catch (err) {
    // No client hints: unnamed.
  }
  return null;
}

async function signedInAccount() {
  const vanity = await readLocal("signedInVanity");
  return typeof vanity === "string" && vanity ? vanity : null;
}

async function stampFor(sender) {
  const tab = (sender && sender.tab) || {};
  return {
    browser_instance_id: await browserInstanceId(),
    browser: browserName(),
    tab_id: typeof tab.id === "number" ? tab.id : null,
    window_id: typeof tab.windowId === "number" ? tab.windowId : null,
    tab_active: typeof tab.active === "boolean" ? tab.active : null,
    frame_id: sender && typeof sender.frameId === "number" ? sender.frameId : null,
    document_id: sender && typeof sender.documentId === "string" ? sender.documentId : null,
    signed_in_vanity: await signedInAccount()
  };
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
    // The studio's own sentence when it gives one: a creator profile beyond
    // the first cannot keep a session (decision D9), and "409" says nothing.
    let said = null;
    try {
      const body = await response.json();
      const detail = body && body.detail;
      said = detail && typeof detail === "object" ? detail.message : detail;
    } catch (err) {
      said = null;
    }
    return {
      status: "error",
      message: typeof said === "string" && said ? said : "The studio refused the session (" + response.status + ")."
    };
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
        relayToStudio(message, path, sendResponse, sender);
      });
      return true;
    }
    if (!RELAYABLE_PATHS.has(path)) {
      sendResponse({ status: "error", error: "path not permitted: " + path });
      return true;
    }
    relayToStudio(message, path, sendResponse, sender);
    return true;
  }

  // What a LinkedIn tab reports about itself: its kind of page, whether it
  // is visible, and network reading as the page sees it. The worker keeps
  // it for its own heartbeat, one per browser per minute; tabs no longer
  // send the studio one each.
  if (message.action === "PAGE_STATE") {
    const fromLinkedIn = !!sender.tab && typeof sender.tab.id === "number" && sender.id === chrome.runtime.id &&
      typeof sender.url === "string" && /^https:\/\/([a-z0-9-]+\.)*linkedin\.com\//i.test(sender.url);
    if (!fromLinkedIn) {
      sendResponse({ status: "refused" });
      return true;
    }
    notePageState(sender.tab.id, message).then(() => sendResponse({ status: "noted" }));
    return true;
  }

  // The side panel opened: the creator has seen what the badge counted, and
  // the notice at the top of the panel.
  if (message.action === "PANEL_OPENED") {
    const fromOwnPage = !sender.tab && sender.id === chrome.runtime.id;
    if (!fromOwnPage) {
      sendResponse({ status: "refused" });
      return true;
    }
    markNoticeSeen().then(clearBadgeCounts).then(() => sendResponse({ status: "cleared" }));
    return true;
  }

  // A sentence one of this extension's scripts on a LinkedIn page has for
  // the creator, which used to be drawn into LinkedIn's page (decision D3;
  // the review's S7). Only from a LinkedIn tab.
  if (message.action === "PAGE_NOTICE") {
    const fromLinkedIn = !!sender.tab && sender.id === chrome.runtime.id &&
      typeof sender.url === "string" && /^https:\/\/([a-z0-9-]+\.)*linkedin\.com\//i.test(sender.url);
    if (!fromLinkedIn) {
      sendResponse({ status: "refused" });
      return true;
    }
    notePageNotice(message).then(() => sendResponse({ status: "noted" }));
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
  "/api/analytics/ingest",
  // The creator's own account and content figures (own_insights.js, 2.8.0):
  // their own data, kept for a busy studio like the rest. The studio keeps
  // one reading per page, window and hour, so a later replay is the same row.
  "/api/analytics/page-figures"
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

// At most this many requests to the studio at once (the capture report's
// backpressure budget): ten tabs reading at once used to send everything
// together, and a busy studio answered most of it 503.
const MAX_IN_FLIGHT = 4;
let inFlight = 0;
const waitingForSlot = [];

function takeSlot() {
  if (inFlight < MAX_IN_FLIGHT) {
    inFlight += 1;
    return Promise.resolve();
  }
  return new Promise((resolve) => waitingForSlot.push(resolve));
}

function giveSlot() {
  const next = waitingForSlot.shift();
  if (next) next();
  else inFlight -= 1;
}

// One request to the studio, as what happened rather than as an exception.
async function askStudio(path, method, body, account) {
  await takeSlot();
  let response;
  let data;
  try {
    try {
      response = await studioFetch(path, { method, body, account });
    } catch (err) {
      // No answer at all: the studio may have taken the write and never
      // replied, which is why only a repeatable payload is kept below.
      return { ok: false, httpStatus: 0, data: {}, busy: true, later: true, error: err.message };
    }
    data = await response.json().catch(() => ({}));
  } finally {
    giveSlot();
  }
  const retryAfter = response.headers && response.headers.get ? response.headers.get("Retry-After") : null;
  // An account no creator profile holds: the studio wrote nothing, and the
  // capture waits here until a profile for that account exists.
  if (response.status === 202 && data && data.outcome === "held") {
    return { ok: false, httpStatus: 202, data, busy: false, later: false, held: true,
      heldFor: data.account || null, error: null };
  }
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
async function keepCaptureNow(path, body, account, heldFor) {
  const kept = await readKeptCaptures();
  const item = { path, body, at: new Date().toISOString() };
  if (account) item.account = account;
  if (heldFor) item.heldFor = heldFor;
  kept.push(item);
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

function keepCapture(path, body, account, heldFor) {
  return inTurn(() => keepCaptureNow(path, body, account, heldFor));
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
//
// A capture held for an account no creator profile holds stays where it is
// until the studio's heartbeat answer names that account, and is then sent
// with the rest; it never blocks the captures behind it.
async function sendKeptCaptures() {
  const kept = await readKeptCaptures();
  if (kept.length === 0) {
    await afterQueueChanged();
    return 0;
  }
  const homes = new Set((await readLocal(PROFILE_VANITIES_KEY)) || []);
  const still = [];
  let sent = 0;
  let unreachable = false;
  for (const item of kept) {
    if (unreachable || (item.heldFor && !homes.has(item.heldFor))) {
      still.push(item);
      continue;
    }
    const answer = await askStudio(item.path, "POST", item.body, item.account || null);
    if (answer.held) {
      still.push(Object.assign({}, item, { heldFor: answer.heldFor || item.heldFor || item.account || null }));
      continue;
    }
    if (answer.later) {
      still.push(item);
      unreachable = true;
      continue;
    }
    if (answer.ok) {
      sent += 1;
      await noteCapture(item.path, answer, null, false);
    } else {
      await rememberRefusal(item.path, answer);
    }
  }
  await writeKeptCaptures(still);
  await afterQueueChanged();
  return sent;
}

// How many captures wait for a profile, per account.
function heldCounts(kept) {
  const counts = {};
  for (const item of kept) {
    if (item.heldFor) counts[item.heldFor] = (counts[item.heldFor] || 0) + 1;
  }
  return counts;
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
  // Waiting is what the studio can take now; a capture held for an account
  // with no profile is counted on its own, by account.
  const deliverable = kept.filter((item) => !item.heldFor);
  const before = (await readLocal(WAITING_KEY)) || {};
  const now = { waiting: deliverable.length, oldest_at: deliverable.length ? deliverable[0].at : null,
    held: heldCounts(kept) };
  await storeLocal({ [WAITING_KEY]: now });
  if (deliverable.length > 0) scheduleDrain();
  else clearDrain();
  await paintBadge();
  // The studio hears the new counts at once, so a screen can show them.
  if (before.waiting !== now.waiting || JSON.stringify(before.held || {}) !== JSON.stringify(now.held)) {
    scheduleHeartbeat(0);
  }
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

// -------------------------------------------------------------
// The worker's heartbeat: one per browser per minute
// -------------------------------------------------------------
// Every LinkedIn tab sent the studio a heartbeat a minute of its own, so ten
// tabs wrote ten rows a minute. The worker now beats for the browser, on a
// minute's alarm and soon after something changes, and carries what the
// tabs report to it (PAGE_STATE): the LinkedIn pages open, by kind, and
// network reading as the newest visible page sees it; with how many
// captures are waiting, how many are held for an account no profile holds,
// how many tabs still carry an older copy of the readers, and whether this
// install reloads itself when its files change. The registry of tabs lives
// in session storage, which survives the worker being stopped and is
// emptied when the browser closes, as a tab is.
const HEARTBEAT_ALARM = "inox_bridge_heartbeat";
const TAB_REGISTRY_KEY = "tabRegistry";
const NEEDS_RELOAD_KEY = "tabsNeedingReload";
const PROFILE_VANITIES_KEY = "profileVanities";
const FILES_VERSION_KEY = "filesVersion";
// When the extension last read its own folder, and whether it could.
const FILES_CHECK_KEY = "filesCheck";
const PAGE_KIND = /^[a-z0-9_-]{1,40}$/;
let heartbeatTimer = null;

function scheduleHeartbeat(delayMs) {
  if (heartbeatTimer) return;
  heartbeatTimer = setTimeout(() => {
    heartbeatTimer = null;
    sendWorkerHeartbeat();
  }, delayMs === undefined ? 2000 : delayMs);
}

let registryTurn = Promise.resolve();

function inRegistryTurn(work) {
  const next = registryTurn.then(work);
  registryTurn = next.catch(() => {});
  return next;
}

function notePageState(tabId, message) {
  return inRegistryTurn(async () => {
    const registry = (await sessionGet(TAB_REGISTRY_KEY)) || {};
    const before = registry[tabId] || null;
    const entry = {
      page_kind: PAGE_KIND.test(String(message.page_kind || "")) ? message.page_kind : "page",
      visible: message.visible === true,
      at: Date.now(),
      version: typeof message.extension_version === "string" ? message.extension_version.slice(0, 40) : null,
      network_reading: message.network_reading && typeof message.network_reading === "object" ? message.network_reading : null,
      voyager_calls: message.voyager_calls && typeof message.voyager_calls === "object" ? message.voyager_calls : null
    };
    registry[tabId] = entry;
    await sessionSet({ [TAB_REGISTRY_KEY]: registry });
    if (entry.version === chrome.runtime.getManifest().version) {
      const needs = (await sessionGet(NEEDS_RELOAD_KEY)) || {};
      if (needs[tabId]) {
        delete needs[tabId];
        await sessionSet({ [NEEDS_RELOAD_KEY]: needs });
      }
    }
    // A new tab, another kind of page, or network reading changing: the
    // studio hears soon rather than at the next minute.
    const changed = !before || before.page_kind !== entry.page_kind ||
      JSON.stringify(before.network_reading) !== JSON.stringify(entry.network_reading);
    if (changed) scheduleHeartbeat();
  });
}

function forgetTab(tabId) {
  return inRegistryTurn(async () => {
    const registry = (await sessionGet(TAB_REGISTRY_KEY)) || {};
    const needs = (await sessionGet(NEEDS_RELOAD_KEY)) || {};
    if (registry[tabId] !== undefined) {
      delete registry[tabId];
      await sessionSet({ [TAB_REGISTRY_KEY]: registry });
    }
    if (needs[tabId] !== undefined) {
      delete needs[tabId];
      await sessionSet({ [NEEDS_RELOAD_KEY]: needs });
    }
  });
}

async function openLinkedInTabs() {
  try {
    const tabs = await chrome.tabs.query({ url: "https://*.linkedin.com/*" });
    return Array.isArray(tabs) ? tabs.filter((tab) => tab && typeof tab.id === "number" && !tab.discarded) : [];
  } catch (err) {
    return [];
  }
}

async function sendWorkerHeartbeat() {
  const kept = await readKeptCaptures();
  const deliverable = kept.filter((item) => !item.heldFor);
  const registry = (await sessionGet(TAB_REGISTRY_KEY)) || {};
  const live = new Set((await openLinkedInTabs()).map((tab) => String(tab.id)));
  const openPages = {};
  let page = null;
  for (const [tabId, entry] of Object.entries(registry)) {
    if (!entry || !live.has(String(tabId))) continue;
    openPages[entry.page_kind] = (openPages[entry.page_kind] || 0) + 1;
    if (entry.network_reading && (!page || (entry.visible && !page.visible) ||
        (entry.visible === page.visible && entry.at > page.at))) {
      page = entry;
    }
  }
  const needs = (await sessionGet(NEEDS_RELOAD_KEY)) || {};
  // What this worker can see of network reading: the switch and whether the
  // browser holds the reader registered; what a page sees (whether it
  // carries the reader, the calls it counted) from the newest visible page.
  const reading = await workerNetworkReading();
  const filesCheck = await readLocal(FILES_CHECK_KEY);
  if (page) {
    for (const field of ["injected", "voyager_calls_seen", "matched", "captured"]) {
      if (reading[field] === null || reading[field] === undefined) {
        const value = page.network_reading[field];
        reading[field] = value === undefined ? null : value;
      }
    }
  }
  const body = {
    extension_version: chrome.runtime.getManifest().version,
    contract_version: INGEST_CONTRACT_VERSION,
    page_kind: "service_worker",
    waiting_captures: deliverable.length,
    oldest_waiting_at: deliverable.length ? deliverable[0].at : null,
    network_reading: reading,
    voyager_calls: page && page.voyager_calls ? page.voyager_calls : null,
    browser_instance_id: await browserInstanceId(),
    browser: browserName(),
    signed_in_vanity: await signedInAccount(),
    open_pages: openPages,
    held: heldCounts(kept),
    tabs_needing_reload: Object.keys(needs).filter((tabId) => live.has(String(tabId))).length,
    self_reload: true,
    files_version: (await readLocal(FILES_VERSION_KEY)) || null,
    files_readable: filesCheck && typeof filesCheck.readable === "boolean" ? filesCheck.readable : null,
    files_checked_at: filesCheck && typeof filesCheck.at === "string" ? filesCheck.at : null
  };
  let answer = null;
  await takeSlot();
  try {
    const response = await studioFetch("/api/v1/bridge/heartbeat", { method: "POST", body: JSON.stringify(body) });
    answer = await response.json().catch(() => ({}));
  } catch (err) {
    return;
  } finally {
    giveSlot();
  }
  const shake = answer && answer.handshake;
  if (shake && shake.reload_required) noteReloadNeeded(shake);
  // A studio of another version: an unpacked install whose files are newer
  // than it reloads now rather than at the next check, and one whose files
  // are not, or are gone, says so on the next beat.
  if (shake && (shake.reload_required ||
      (shake.studio_version && shake.studio_version !== chrome.runtime.getManifest().version))) {
    checkOwnFiles();
  }
  if (answer && Array.isArray(answer.profile_vanities)) {
    await storeLocal({ [PROFILE_VANITIES_KEY]: answer.profile_vanities.filter((v) => typeof v === "string") });
    if (kept.some((item) => item.heldFor && answer.profile_vanities.includes(item.heldFor))) {
      sendKeptCapturesLater();
    }
  }
}

function ensureAlarm(name, periodInMinutes) {
  try {
    chrome.alarms.get(name, (existing) => {
      if (!existing) chrome.alarms.create(name, { periodInMinutes });
    });
  } catch (err) {
    // Alarms are unavailable only if the permission was removed.
  }
}

// -------------------------------------------------------------
// Never reload by hand
// -------------------------------------------------------------
// The studio and the extension update together from the same folder, and a
// browser kept the extension it loaded at startup until someone pressed
// Reload: the studio last heard from 2.7.0 on an install whose files were
// 2.9.0. An unpacked install now notices its files changed, on start-up and
// every few minutes, by reading its own manifest.json from disk, and reloads
// itself when the version there differs from the one it runs. A store
// install's files only change by an update, which reloads it anyway, so
// there the two always agree and nothing happens.
const OWN_FILES_ALARM = "inox_own_files";
const OWN_FILES_EVERY_MINUTES = 5;

async function checkOwnFiles() {
  let response = null;
  try {
    response = await fetch(chrome.runtime.getURL("manifest.json"), { cache: "no-store" });
  } catch (err) {
    response = null;
  }
  // Its folder is gone: deleted, or replaced by an upgrade that extracts a
  // new folder somewhere else. It runs on from memory but cannot update
  // itself, and the browser will not load it at its next start; the
  // heartbeat says so, which is the one case the studio says to load it again.
  if (!response || !response.ok) {
    await storeLocal({ [FILES_VERSION_KEY]: null,
      [FILES_CHECK_KEY]: { at: new Date().toISOString(), readable: false } });
    return false;
  }
  try {
    const disk = await response.json();
    const onDisk = disk && typeof disk.version === "string" ? disk.version : null;
    await storeLocal({ [FILES_VERSION_KEY]: onDisk,
      [FILES_CHECK_KEY]: { at: new Date().toISOString(), readable: true } });
    if (onDisk && onDisk !== chrome.runtime.getManifest().version) {
      chrome.runtime.reload();
      return true;
    }
  } catch (err) {
    // A manifest caught half written reads as nothing; the next check sees it whole.
  }
  return false;
}

// On install and on update, the readers go into the LinkedIn tabs already
// open, so no tab needs a refresh: each tab is asked which version of the
// readers it carries (none, after an update: the readers of the version
// before are cut off from this one), and given this version's. A tab that
// cannot be reached is remembered as needing a reload, and the heartbeat
// says how many, which is the one case Setup should say "reload".
const READER_FILES = ["voyager_schema.js", "content.js", "own_pages.js", "own_insights.js"];

async function injectIntoOpenTabs() {
  const version = chrome.runtime.getManifest().version;
  for (const tab of await openLinkedInTabs()) {
    try {
      const probe = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => (typeof window.__inoxBridgeVersion === "string" ? window.__inoxBridgeVersion : null)
      });
      if (probe && probe[0] && probe[0].result === version) continue;
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["card_urns.js"], world: "MAIN" });
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: READER_FILES });
    } catch (err) {
      await inRegistryTurn(async () => {
        const needs = (await sessionGet(NEEDS_RELOAD_KEY)) || {};
        needs[tab.id] = String((err && err.message) || err).slice(0, 120);
        await sessionSet({ [NEEDS_RELOAD_KEY]: needs });
      });
    }
  }
  scheduleHeartbeat(0);
}

try {
  chrome.runtime.onInstalled.addListener((details) => {
    ensureAlarm(HEARTBEAT_ALARM, 1);
    ensureAlarm(OWN_FILES_ALARM, OWN_FILES_EVERY_MINUTES);
    if (details && (details.reason === "install" || details.reason === "update")) injectIntoOpenTabs();
  });
  chrome.runtime.onStartup.addListener(() => {
    ensureAlarm(HEARTBEAT_ALARM, 1);
    ensureAlarm(OWN_FILES_ALARM, OWN_FILES_EVERY_MINUTES);
    checkOwnFiles();
    scheduleHeartbeat(0);
  });
  ensureAlarm(HEARTBEAT_ALARM, 1);
  ensureAlarm(OWN_FILES_ALARM, OWN_FILES_EVERY_MINUTES);
} catch (err) {
  // No alarms or runtime events: the relays still work.
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

// Whether the studio stored anything, read from its own answer. The engagers
// route answers the ingest contract's outcome (ingest_contract.py: accepted
// or nothing_new); the creator's own pages answer the counts and words their
// routes have always answered: written, recorded, buckets_ingested,
// followers_saved, items_kept, or bound, updated, candidate; and since 2.8.0
// the counts of the readers track 5 added: readings_recorded and
// points_recorded from the account and content pages, reposts_recorded from
// the Activity page. A 200 that stored nothing is the usual answer on the
// feed, where most engagers are on other people's posts, and it is never
// counted as a capture: counting it would put a number on the badge that no
// row in the studio stands behind.
const STORED_COUNTS = ["written", "buckets_ingested", "followers_saved", "items_kept",
  "readings_recorded", "points_recorded", "reposts_recorded"];
const STORED_STATUSES = ["bound", "updated", "candidate"];

function storedSomething(data) {
  if (!data || typeof data !== "object") return false;
  if (data.outcome === "accepted") return true;
  if (data.outcome === "nothing_new" || data.status === "skipped") return false;
  if (STORED_COUNTS.some((field) => typeof data[field] === "number" && data[field] > 0)) return true;
  if (data.recorded === true) return true;
  return STORED_STATUSES.includes(data.status);
}

// One record per relay of the creator's data: which path, when, what the
// studio did with it, and from which tab. Never the capture itself: the panel
// names the kind of thing and when, not the person.
async function noteCapture(path, answer, tabId, kept) {
  const data = (answer && answer.data) || {};
  const ok = !!(answer && answer.ok);
  const stored = ok && storedSomething(data);
  await storeLocal({
    [LAST_CAPTURE_KEY]: {
      path,
      at: new Date().toISOString(),
      ok,
      kept: kept === true,
      stored,
      httpStatus: answer ? answer.httpStatus : 0,
      outcome: kept ? "kept" : (data.outcome || data.reason || data.status || null),
      tabId
    }
  });
  if (stored && path === "/api/v1/bridge/voyager-ingest") {
    await storeLocal({ [LAST_VOYAGER_CAPTURE_KEY]: new Date().toISOString() });
  }
  if (stored && tabId !== null && tabId !== undefined) {
    const counts = (await readLocal(BADGE_COUNTS_KEY)) || {};
    // A read of a post is one request now; the badge still counts each
    // person the studio took from it.
    const taken = typeof data.items_accepted === "number" && data.items_accepted > 0 ? data.items_accepted : 1;
    counts[tabId] = (counts[tabId] || 0) + taken;
    await storeLocal({ [BADGE_COUNTS_KEY]: counts });
    await actionCall("setBadgeText", { tabId, text: String(counts[tabId]) });
  }
  await paintBadge();
}

// null hands a tab back to the badge's own text, which is Chrome's documented
// reset; a browser that refuses null is given the empty text instead.
async function resetTabBadge(tabId) {
  if (!(await actionCall("setBadgeText", { tabId, text: null }))) {
    await actionCall("setBadgeText", { tabId, text: "" });
  }
}

async function clearBadgeCounts() {
  const counts = (await readLocal(BADGE_COUNTS_KEY)) || {};
  for (const tabId of Object.keys(counts)) {
    await resetTabBadge(Number(tabId));
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

// The drift notice lives in session storage, which the browser empties when
// it closes, so "once per page kind per session" holds by construction and a
// notice never outlives the session it was measured in. The side panel and
// the popup read it from there. A browser without session storage keeps no
// notice; every browser with a side panel has it.
function sessionArea() {
  try {
    return chrome.storage && chrome.storage.session ? chrome.storage.session : null;
  } catch (err) {
    return null;
  }
}

function sessionGet(key) {
  return new Promise((resolve) => {
    const area = sessionArea();
    if (!area) {
      resolve(null);
      return;
    }
    try {
      area.get(key, (items) => resolve((items && items[key]) || null));
    } catch (err) {
      resolve(null);
    }
  });
}

function sessionSet(values) {
  return new Promise((resolve) => {
    const area = sessionArea();
    if (!area) {
      resolve();
      return;
    }
    try {
      area.set(values, () => resolve());
    } catch (err) {
      resolve();
    }
  });
}

function sessionRemove(key) {
  return new Promise((resolve) => {
    const area = sessionArea();
    if (!area) {
      resolve();
      return;
    }
    try {
      area.remove(key, () => resolve());
    } catch (err) {
      resolve();
    }
  });
}

// A reader reported fields it could not read on a page that plainly had
// them. Said once per page kind per browser session, in the panel header
// and the badge colour, never in the page: it is a measurement the reader
// made, and the one failure a creator cannot see for themselves. A later
// clean run of the same reader on the same kind of page is a newer
// measurement, and takes the notice down.
async function noteDrift(body) {
  if (!body || typeof body !== "object") return;
  const pageKind = String(body.page_kind || "page").slice(0, 40);
  const extractor = String(body.extractor || "").slice(0, 40);
  const fields = Array.isArray(body.drift) ? body.drift.filter((d) => typeof d === "string").slice(0, 10) : [];
  if (!fields.length) {
    if (Number(body.items_seen) > 0) {
      const shown = await sessionGet(LAST_DRIFT_KEY);
      if (shown && shown.extractor === extractor && shown.page_kind === pageKind) {
        await sessionRemove(LAST_DRIFT_KEY);
        await paintBadge();
      }
    }
    return;
  }
  const key = DRIFT_NOTICED_PREFIX + pageKind;
  if (await sessionGet(key)) return;
  const at = new Date().toISOString();
  await sessionSet({ [key]: at, [LAST_DRIFT_KEY]: { extractor, page_kind: pageKind, fields, at } });
  await paintBadge();
}

// The newest notice a LinkedIn page had for the creator, kept in session
// storage beside the drift notice, so it never outlives the browser session
// it was said in. A warning puts "!" on the badge until the side panel
// opens, which is the creator seeing it, and the panel shows it at its top;
// a notice of captures kept for the studio is carried by the waiting count,
// which is already on the badge. A notice already seen is not raised again
// in the same session, so a studio that stays closed is said once.
const PAGE_NOTICE_KEY = "pageNotice";

async function notePageNotice(message) {
  const text = String((message && message.message) || "").replace(/\s+/g, " ").trim().slice(0, 400);
  if (!text) return;
  const shown = await sessionGet(PAGE_NOTICE_KEY);
  if (shown && shown.message === text && shown.seen) return;
  await sessionSet({
    [PAGE_NOTICE_KEY]: {
      message: text,
      kind: message.kind === "waiting" ? "waiting" : "warning",
      page_kind: String(message.page_kind || "page").slice(0, 40),
      at: new Date().toISOString(),
      seen: false
    }
  });
  await paintBadge();
}

async function markNoticeSeen() {
  const shown = await sessionGet(PAGE_NOTICE_KEY);
  if (!shown || shown.seen) return;
  await sessionSet({ [PAGE_NOTICE_KEY]: Object.assign({}, shown, { seen: true }) });
  await paintBadge();
}

async function paintBadge() {
  const waiting = (await readLocal(WAITING_KEY)) || {};
  const drift = await sessionGet(LAST_DRIFT_KEY);
  const notice = await sessionGet(PAGE_NOTICE_KEY);
  const warning = !!notice && !notice.seen && notice.kind === "warning";
  const waitingCount = typeof waiting.waiting === "number" ? waiting.waiting : 0;
  const attention = waitingCount > 0 || !!drift || warning;
  await actionCall("setBadgeBackgroundColor", { color: attention ? BADGE_ORANGE : BADGE_GREEN });
  await actionCall("setBadgeTextColor", { color: BADGE_TEXT });
  // What a tab with no count of its own shows: how many captures are
  // waiting, or a mark for a drift noticed this session. A badge with no
  // text is not drawn, so without this the orange could not be seen in a
  // tab where nothing had been captured yet. A tab's own count of captures
  // takes its place in that tab, on the same colour.
  await actionCall("setBadgeText", {
    text: waitingCount > 0 ? String(Math.min(waitingCount, 999)) : (drift || warning ? "!" : "")
  });
  let title = "Inox Hydra Bridge";
  if (waitingCount > 0) {
    title = "Inox Hydra: " + waitingCount + " capture(s) waiting for the studio";
  } else if (warning) {
    title = "Inox Hydra: " + notice.message.replace(/^Inox Hydra:\s{0,3}/, "") + " The side panel has it.";
  } else if (drift) {
    title = "Inox Hydra: cannot read " + drift.fields.join(", ").replace(/_/g, " ") +
      " on LinkedIn's " + drift.page_kind + " page. See Health in the studio.";
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
      await forgetTab(tabId);
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
// One listener for the worker's alarms: the drain, its own heartbeat (which
// also drains, so a held capture goes as soon as its account has a profile),
// and the check of its own files.
chrome.alarms.onAlarm.addListener((alarm) => {
  if (!alarm) return;
  if (alarm.name === DRAIN_ALARM) sendKeptCapturesLater();
  else if (alarm.name === HEARTBEAT_ALARM) {
    sendWorkerHeartbeat();
    sendKeptCapturesLater();
  } else if (alarm.name === OWN_FILES_ALARM) checkOwnFiles();
});

// Every write says which contract it speaks and which build sent it, so the
// studio knows what it is talking to without the page script having to
// remember to say, and where it was read (the stamp). A body that names
// them already keeps its own values.
function stamped(body, stamp) {
  const payload = sanitizeTelemetryPayload(body) || {};
  if (typeof payload !== "object" || Array.isArray(payload)) return payload;
  if (payload.contract_version === undefined) payload.contract_version = INGEST_CONTRACT_VERSION;
  if (payload.extension_version === undefined) {
    payload.extension_version = chrome.runtime.getManifest().version;
  }
  if (stamp && payload.stamp === undefined) payload.stamp = stamp;
  return payload;
}

// -------------------------------------------------------------
// The same capture from another tab is answered here
// -------------------------------------------------------------
// Ten tabs on one post each read every person on it and sent them all, so
// the studio wrote each engagement ten times. The worker keeps a key for
// each item it forwarded in the last ten seconds, in session storage (which
// survives the worker being stopped, is emptied when the browser closes, and
// no page can read); an identical item from any tab inside the window is
// answered already_seen here, without a request, and a new one always goes.
// The key is a hash of what the studio keeps one row for, never the words:
// for an engagement, the account, the post, the person, how they engaged and
// the comment; for anything else, the account and the item as read.
const COALESCE_WINDOW_MS = 10000;
const COALESCED_KEY = "coalescedCaptures";
const VOLATILE_FIELDS = new Set(["extension_version", "contract_version", "stamp", "idempotency_key", "timestamp",
  "capture_id"]);

function stableJson(value) {
  if (Array.isArray(value)) return "[" + value.map(stableJson).join(",") + "]";
  if (value && typeof value === "object") {
    return "{" + Object.keys(value).filter((k) => !VOLATILE_FIELDS.has(k)).sort()
      .map((k) => JSON.stringify(k) + ":" + stableJson(value[k])).join(",") + "}";
  }
  return JSON.stringify(value === undefined ? null : value);
}

async function hashOf(parts) {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(parts.join("|")));
  return Array.from(new Uint8Array(bytes)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function engagementKey(item, account) {
  const person = String(item.linkedin_urn || item.profile_url || "");
  // Someone with no profile link is never the same person as anyone else to
  // the studio, so nothing is answered for them here.
  if (!person) return contentKey("engagement")(item, account);
  const vanity = /linkedin\.com\/in\/([^/?#]+)/i.exec(person);
  const words = String(item.comment_text || "").split(/\s+/).filter(Boolean).join(" ").toLowerCase();
  return hashOf(["engagement", account || "", item.post_urn || item.capture_context || "",
    vanity ? vanity[1].toLowerCase() : person, String(item.interaction_type || "COMMENT").toUpperCase(), words]);
}

function contentKey(kind) {
  return (item, account) => hashOf([kind, account || "", stableJson(item)]);
}

// A reader's run, reported by every tab reading the same kind of page: the
// studio keeps one row per browser, reader and minute, so the same run
// shape from another tab in the same minute is not sent at all.
function runKey(body, account) {
  const drift = Array.isArray(body.drift) && body.drift.length ? "drift:" + body.drift.join(",") : "clean";
  return hashOf(["run", account || "", String(body.extractor || ""), String(body.page_kind || ""), drift,
    new Date().toISOString().slice(0, 16)]);
}

// The paths whose captures can be the same capture from another tab, and
// where a body lists its items.
const COALESCED_PATHS = {
  "/api/v1/bridge/capture": { keyOf: runKey },
  "/api/v1/crm/interactions/ingest": { list: "items", keyOf: engagementKey },
  "/api/v1/self/posts/ingest": { list: "posts", keyOf: contentKey("posts") },
  "/api/v1/self/outbound/ingest": { list: "items", keyOf: contentKey("outbound") },
  "/api/v1/self/posts/analytics": { keyOf: contentKey("post-analytics") },
  "/api/analytics/ingest": { keyOf: contentKey("analytics") },
  "/api/analytics/page-figures": { keyOf: contentKey("page-figures") },
  "/api/v1/identity/observe": { keyOf: contentKey("profile") }
};

let coalesceTurn = Promise.resolve();

// Splits a body into what is new and what another tab sent a moment ago.
function coalesce(path, body, account) {
  const rule = COALESCED_PATHS[path];
  const run = async () => {
    const listed = !!rule.list && Array.isArray(body[rule.list]);
    // An empty list is sent as it is: there is nothing in it to be the same.
    if (listed && body[rule.list].length === 0) return null;
    const items = listed ? body[rule.list] : [body];
    const keys = await Promise.all(items.map((item) => rule.keyOf(item || {}, account)));
    const now = Date.now();
    const seen = (await sessionGet(COALESCED_KEY)) || {};
    for (const key of Object.keys(seen)) {
      if (!(now - seen[key] < COALESCE_WINDOW_MS)) delete seen[key];
    }
    const fresh = [];
    const repeated = [];
    keys.forEach((key, index) => {
      if (seen[key] !== undefined) repeated.push(index);
      else {
        seen[key] = now;
        fresh.push(index);
      }
    });
    await sessionSet({ [COALESCED_KEY]: seen });
    return { listed, items, keys, fresh, repeated, list: rule.list };
  };
  const result = coalesceTurn.then(run);
  coalesceTurn = result.catch(() => {});
  return result;
}

function alreadySeen(key) {
  return { idempotency_key: key, status: "skipped", outcome: "nothing_new", reason: "already_seen", coalesced: true };
}

async function relayToStudio(message, path, sendResponse, sender) {
  const tabId = sender && sender.tab && typeof sender.tab.id === "number" ? sender.tab.id : null;
  const method = message.method || "POST";
  const stamp = await stampFor(sender);
  const account = stamp.signed_in_vanity || null;
  let outgoing = message.body;
  let split = null;
  if (COALESCED_PATHS[path] && outgoing && typeof outgoing === "object" && !Array.isArray(outgoing)) {
    // A key that cannot be made (no session storage, no digest) sends the
    // capture as it is: the studio's own already_seen still holds.
    try {
      split = await coalesce(path, outgoing, account);
    } catch (err) {
      split = null;
    }
  }
  if (split) {
    if (split.fresh.length === 0) {
      // Every item came from another tab a moment ago: answered here.
      const data = { status: "skipped", outcome: "nothing_new", reason: "already_seen", coalesced: true };
      if (split.listed && path === "/api/v1/crm/interactions/ingest") {
        data.items = split.keys.map(alreadySeen);
        data.items_accepted = 0;
      }
      sendResponse({ status: "success", httpStatus: 200, data });
      return;
    }
    if (split.listed) {
      outgoing = Object.assign({}, outgoing, {
        [split.list]: split.fresh.map((index) => (path === "/api/v1/crm/interactions/ingest"
          ? Object.assign({}, split.items[index], { idempotency_key: split.keys[index] })
          : split.items[index]))
      });
    }
  }
  const body = outgoing ? JSON.stringify(stamped(outgoing, stamp)) : undefined;
  let answer = { ok: false, httpStatus: 0, data: {}, busy: false, later: false, error: "not sent" };
  for (let attempt = 1; attempt <= BUSY_ATTEMPTS; attempt += 1) {
    answer = await askStudio(path, method, body, account);
    if (!answer.busy || attempt === BUSY_ATTEMPTS) break;
    await waitFor(busyWaitMs(answer.retryAfter, attempt));
  }
  // A read's answers come back in the order its people were read: the ones
  // another tab sent a moment ago answered here, the rest by the studio.
  if (split && split.listed && path === "/api/v1/crm/interactions/ingest" && answer.data &&
      Array.isArray(answer.data.items) && split.repeated.length) {
    const merged = split.keys.map(alreadySeen);
    split.fresh.forEach((index, n) => { merged[index] = answer.data.items[n] || merged[index]; });
    answer.data = Object.assign({}, answer.data, { items: merged });
  }
  // An account no creator profile holds: kept, and sent once one does.
  if (answer.held) {
    await keepCapture(path, body, account, answer.heldFor || account);
    await noteCapture(path, answer, tabId, true);
    sendResponse({
      status: "error", httpStatus: answer.httpStatus, data: answer.data, kept: true, held: true, waiting: 0,
      error: (answer.data && answer.data.message) || "No profile holds this LinkedIn account yet, so this capture is kept."
    });
    return;
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
    await keepCapture(path, body, account);
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
  if (KEEP_WHEN_BUSY.has(path)) await noteCapture(path, answer, tabId, false);
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
