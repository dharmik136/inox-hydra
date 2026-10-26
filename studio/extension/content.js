// -------------------------------------------------------------
// Inox Hydra Bridge - Content Script
// Interacts with LinkedIn DOM to auto-inject formatted posts
// -------------------------------------------------------------


/**
 * Sends a studio API call through the background service worker.
 *
 * This content script runs inside the LinkedIn page, so a fetch made from here
 * carries Origin: https://www.linkedin.com. The studio refuses that origin on
 * purpose, because trusting it would mean trusting every other script on the
 * page, including whatever LinkedIn's ad and analytics vendors inject. The
 * worker holds the token and speaks from the extension's own origin instead.
 *
 * Resolves to the parsed body, or null when the studio is offline. Callers
 * treat a failure as "not captured", never as an error worth interrupting for.
 * A studio that answered with an error status resolves to
 * {status: "refused", httpStatus, detail}: it is running and said no, which a
 * notice must not describe as either success or "could not reach".
 *
 * A capture the worker kept for a studio that was busy resolves to
 * {status: "kept", waiting}. That flag was dropped here, so the one thing the
 * creator most needed to know, that their work is waiting and not lost, could
 * not be said. The refusal's reason code and sentence come back with it, so a
 * caller can both count the reason and show the sentence.
 */
function studioApi(path, body, method) {
  return new Promise((resolve) => {
    try {
      chrome.runtime.sendMessage(
        { action: "STUDIO_API", path: path, method: method || "POST", body: body },
        (response) => {
          if (chrome.runtime.lastError || !response) {
            resolve(null);
            return;
          }
          if (response.status !== "success") {
            if (response.kept) {
              resolve({ status: "kept", waiting: response.waiting || 0, message: response.error || "" });
              return;
            }
            resolve(response.httpStatus
              ? {
                  status: "refused",
                  httpStatus: response.httpStatus,
                  detail: (response.data && response.data.detail) || "",
                  reason: response.reason || null,
                  message: response.message || (response.data && response.data.detail) || "",
                  show: response.show === true
                }
              : null);
            return;
          }
          resolve(response.data || {});
        }
      );
    } catch (err) {
      resolve(null);
    }
  });
}

// -------------------------------------------------------------
// Voyager API Network Capture (Phase 1: Self-Healing)
// -------------------------------------------------------------
// The MAIN-world interceptor (voyager_interceptor.js) patches fetch() on the
// LinkedIn page and posts structured JSON from Voyager responses via
// window.postMessage. This listener receives those messages in the extension's
// isolated world, where chrome.runtime is available.
//
// WHY DUAL-PATH:
// DOM scraping (the original approach) breaks when LinkedIn rehashes class
// names, loses precision with "1.2K" abbreviations, and misses data the user
// hasn't scrolled to. Network capture gives us exact numbers in structured
// JSON. But LinkedIn can also change their API response shapes, so we keep
// DOM as a fallback and report drift when network extraction fails.
//
// The schema registry (voyager_schema.js, loaded before this file) maps
// Voyager response structures to our internal data model. When fields move,
// updating the schema fixes extraction without touching this code.

// The interceptor runs only while the creator has network reading switched
// on (background.js registers it then). Messages claiming to come from it are
// ignored while it is off: any script on the page can post one.
//
// null until chrome.storage has answered. The interceptor runs at
// document_start and LinkedIn's first responses arrive before the storage
// read resolves, and every message that arrived in that gap used to be
// dropped without a trace: the first captures of every page were lost. They
// are held below and handled once the switch is known.
let networkReadingOn = null;
const EARLY_CAPTURES_LIMIT = 20;
const earlyCaptures = [];
// The schemas whose responses carry the creator's own data and nobody else's:
// their own posts' figures and their follower count. onboarding.VOYAGER_KEPT
// is the studio's list of the same, and a test holds the two equal.
const FORWARDED_SCHEMAS = new Set(["feed_updates", "creator_analytics"]);
// The LinkedIn account this browser is signed in to, as LinkedIn itself has
// shown it (own_pages.js notes it on the creator's own profile; the worker
// forgets it when the sign-in changes). Analytics carry it, because neither
// the analytics page nor LinkedIn's response names the account, and the
// studio refuses a reading that is not from the profile open in it.
let signedInVanity = null;
// own_pages.js runs in this same isolated world and is told by a function
// call when the state changes, not by an event on LinkedIn's window, which
// LinkedIn's own scripts can hear.
const networkReadingListeners = [];
window.__inoxOnNetworkReading = (fn) => {
  if (typeof fn === "function") networkReadingListeners.push(fn);
};
function announceNetworkReading() {
  networkReadingListeners.forEach((fn) => {
    try { fn(); } catch (err) {}
  });
}

// Whether this page carries the interceptor. It runs in LinkedIn's own
// world, out of this script's sight, so the page is asked over the window
// channel the interceptor already uses, and only while the switch is on:
// with network reading off the page is never asked. null until it
// has answered or the grace below has passed; a tab opened before the switch
// was turned on carries no interceptor and does not answer. It used to mark
// LinkedIn's root element with an attribute any script there could read.
const INTERCEPTOR_GRACE_MS = 1500;
let interceptorAnswered = null;
let interceptorAskTimer = null;

function askForInterceptor() {
  if (interceptorAskTimer) clearTimeout(interceptorAskTimer);
  interceptorAskTimer = null;
  if (!networkReadingOn) {
    interceptorAnswered = null;
    return;
  }
  if (interceptorAnswered === true) return;
  interceptorAnswered = null;
  interceptorAskTimer = setTimeout(() => {
    interceptorAskTimer = null;
    if (interceptorAnswered === null && networkReadingOn) {
      interceptorAnswered = false;
      announceNetworkReading();
    }
  }, INTERCEPTOR_GRACE_MS);
  try {
    window.postMessage({ type: "INOX_VOYAGER_PING", source: "inox-bridge" }, window.location.origin);
  } catch (err) {}
}

function noteInterceptor() {
  if (!networkReadingOn || interceptorAnswered === true) return;
  if (interceptorAskTimer) clearTimeout(interceptorAskTimer);
  interceptorAskTimer = null;
  interceptorAnswered = true;
  announceNetworkReading();
}

try {
  chrome.storage.local.get(["networkReading", "signedInVanity"], (items) => {
    networkReadingOn = !chrome.runtime.lastError && !!items && items.networkReading === true;
    signedInVanity = (!chrome.runtime.lastError && items && items.signedInVanity) || null;
    followNetworkReading();
    askForInterceptor();
    const held = earlyCaptures.splice(0, earlyCaptures.length);
    if (networkReadingOn) held.forEach(handleVoyagerCapture);
    // own_pages.js reports the state on its heartbeat; it is known now.
    announceNetworkReading();
  });
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && changes.networkReading) {
      networkReadingOn = changes.networkReading.newValue === true;
      followNetworkReading();
      askForInterceptor();
      announceNetworkReading();
    }
    if (area === "local" && changes.signedInVanity) {
      signedInVanity = changes.signedInVanity.newValue || null;
    }
  });
} catch (e) {}

const voyagerCaptureStats = {
  total: 0,
  matched: 0,
  successful: 0,
  drifted: 0,
  lastCaptureTime: 0
};

window.addEventListener("message", (event) => {
  // Only accept messages from the same page (our MAIN-world scripts).
  if (event.source !== window || !event.data) return;
  if (event.data.source === "inox-voyager-interceptor" && event.data.type === "INOX_VOYAGER_PRESENT") {
    noteInterceptor();
    return;
  }
  if (event.data.source === "inox-card-urns" && event.data.type === "INOX_CARD_URNS_REPORT") {
    forwardCardUrnsReport(event.data.report);
    return;
  }
  if (event.data.type !== "INOX_VOYAGER_CAPTURE") return;
  if (event.data.source !== "inox-voyager-interceptor") return;
  if (networkReadingOn === null) holdEarlyCapture(event.data);
  if (!networkReadingOn) return;
  handleVoyagerCapture(event.data);
});

function holdEarlyCapture(data) {
  if (earlyCaptures.length < EARLY_CAPTURES_LIMIT) earlyCaptures.push(data);
}

function handleVoyagerCapture(data) {
  const payload = data && data.payload;
  if (!payload || !payload.url || !payload.body) return;

  // The schema registry is loaded as voyager_schema.js before this file and
  // exposes its API on window.__InoxVoyagerSchema.
  const VSchema = window.__InoxVoyagerSchema;
  if (!VSchema) {
    console.debug("[Studio Bridge] Voyager schema registry not loaded, skipping capture.");
    return;
  }

  try {
    voyagerCaptureStats.total++;

    const schema = VSchema.resolveSchema(payload.url);
    if (!schema) {
      // URL doesn't match any known schema - ignore silently.
      // This is normal for Voyager endpoints we don't care about.
      return;
    }
    voyagerCaptureStats.matched++;
    // Own data only. The registry also knows profiles, reactions on posts
    // and comments, and those responses are about other members: they are
    // matched and counted here, and nothing of them, not their data and not
    // their drift, leaves the page. The studio refuses them too.
    const schemaName = Object.keys(VSchema.VOYAGER_SCHEMAS).find((k) => VSchema.VOYAGER_SCHEMAS[k] === schema);
    if (!FORWARDED_SCHEMAS.has(schemaName)) return;

    const result = VSchema.extractWithSchema(schema, payload.body);

    // The run's drift, named the way the DOM readers name theirs: a field
    // this reader cannot do without, missing from every entry of a response
    // that plainly matched its endpoint, or a response with no list of
    // entries at all. A missing optional figure is not drift for the reader
    // (most of a feed is other members' posts, which carry no view count);
    // it still goes to the drift log below. Every network run used to be
    // written with no drift, and one whose first entry lacked a required
    // field was not sent at all, so Setup could never say a network reader
    // had stopped reading.
    const entries = Array.isArray(result.data) ? result.data : (result.data ? [result.data] : []);
    const answered = payload.status >= 200 && payload.status < 300;
    const body = payload.body;
    const runDrift = !answered ? []
      : (body && typeof body === "object" && !Array.isArray(body.elements)) ? ["elements"]
      : schema.required.filter((field) => entries.length > 0 &&
          !entries.some((entry) => entry && entry[field] !== undefined && entry[field] !== null));

    if (result.success) {
      voyagerCaptureStats.successful++;
      voyagerCaptureStats.lastCaptureTime = Date.now();
    }
    if (result.success || runDrift.length || entries.length) {
      // Forward structured data to the backend.
      studioApi("/api/v1/bridge/voyager-ingest", {
        schema_name: schemaName,
        schema_version: result.schema_version,
        confidence: result.confidence,
        data: entries,
        drift: runDrift,
        // Whose figures these are; see signedInVanity.
        vanity: signedInVanity,
        source_url: payload.url,
        http_status: payload.status,
        capture_id: payload.captureId,
        timestamp: payload.timestamp,
        extension_version: chrome.runtime.getManifest().version
      });
    }

    // Report drift whenever extraction found missing fields, whether or not
    // the extraction itself "succeeded" (required fields present but optional
    // ones missing still counts as drift worth tracking).
    if (result.drift && result.drift.length > 0) {
      voyagerCaptureStats.drifted++;

      studioApi("/api/v1/bridge/schema-drift", {
        schema_name: schemaName,
        schema_version: result.schema_version,
        drift_fields: result.drift,
        confidence: result.confidence,
        success: result.success,
        source_url: payload.url,
        // Include the top-level keys from the response so the backend can
        // diagnose what LinkedIn changed. Only keys, never values, so no
        // private data leaks into drift telemetry.
        response_top_keys: Object.keys(payload.body || {}),
        timestamp: payload.timestamp,
        extension_version: chrome.runtime.getManifest().version
      });
    }

    console.debug(
      `[Studio Bridge] Voyager capture: ${result.success ? "OK" : "DRIFT"}`,
      `confidence=${result.confidence}`,
      `drift=[${(result.drift || []).join(", ")}]`
    );
  } catch (err) {
    // Never interrupt the user experience for a capture failure.
    console.debug("[Studio Bridge] Voyager capture error:", err.message);
  }
}

// -------------------------------------------------------------
// What LinkedIn calls, counted from the page's own timeline
// -------------------------------------------------------------
// The one question the studio could not answer about network reading was
// why it captured nothing: the switch, the registration, the page and the
// patterns all failed silently in the same direction. Resource Timing lists
// every request the page made, so while the switch is on the page counts
// its /voyager/api/ calls by path plus GraphQL query name (the part before
// the dot; the hash after it rotates), never a query string or a URN, and
// how many of them match the patterns the bridge reads. The heartbeat
// carries the counts, so the studio can say "LinkedIn made N data calls on
// this page, K matched" without anyone opening DevTools.
const voyagerCalls = {};
let voyagerCallsSeen = 0;
let voyagerCallsMatched = 0;
let coverageObserver = null;

// A path names the resource LinkedIn was asked for, and its REST paths put
// the thing asked about in the path itself: /identity/profiles/<vanity>/,
// /socialActions/<urn>/. That is another member, or a post, and is never
// kept. A segment is kept only if it is a word from this fixed list of the
// words LinkedIn's data API puts in its paths, compared without regard to
// case and written as listed; every other segment becomes "_id_", and so does
// the segment after a collection that takes an identifier. An unknown word
// costs a less specific key, never a person. The list used to be the other
// way round, the identifiers to blank, and a plain-word vanity after any
// collection it did not name went through. onboarding.VOYAGER_PATH_WORDS is
// the studio's copy, which refuses anything else; a test holds the two equal.
const VOYAGER_PATH_WORDS = [
  "voyager", "api", "graphql", "me", "identity", "dash", "profiles", "miniProfiles", "profileView",
  "profileContactInfo", "publicContactInfo", "networkinfo", "memberBadges", "memberIdentity",
  "profileActions", "feed", "updates", "updatesV2", "social", "socialActions", "socialDetails", "comments",
  "reactions", "likes", "followerInfo", "hashtags", "contentcreation", "normShares", "shares", "posts",
  "activities", "creatorAnalytics", "analytics", "messaging", "conversations", "events", "messages",
  "threads", "notifications", "badges", "relationships", "memberRelationships", "connections", "invitations",
  "invitationViews", "search", "clusters", "blended", "typeahead", "hitsV2", "hits", "organization",
  "organizations", "companies", "entities", "jobs", "jobPostings", "premium", "growth", "legoWidgets",
  "pageContent", "settings", "highlights", "recommendations", "skills", "positions", "educations",
  "featured", "followers", "following", "people", "members", "groups", "schools"
];
const VOYAGER_ID_AFTER = [
  "profiles", "miniProfiles", "profileContactInfo", "publicContactInfo", "networkinfo", "memberBadges",
  "profileActions", "updates", "updatesV2", "social", "socialActions", "socialDetails", "comments",
  "reactions", "likes", "followerInfo", "hashtags", "shares", "posts", "activities", "conversations",
  "events", "messages", "threads", "connections", "invitations", "organizations", "companies", "jobs",
  "jobPostings", "people", "members", "groups", "schools"
];
const PATH_WORD = new Map(VOYAGER_PATH_WORDS.map((word) => [word.toLowerCase(), word]));
const ID_AFTER = new Set(VOYAGER_ID_AFTER.map((word) => word.toLowerCase()));
// A GraphQL query name has one shape: "voyager" and a capitalised name.
// Anything else in that slot is "other".
const VOYAGER_QUERY_NAME = /^voyager[A-Z][A-Za-z0-9]{1,78}$/;

function cleanVoyagerPath(pathname) {
  const out = [];
  let previous = "";
  for (const segment of String(pathname).split("/").filter(Boolean).slice(0, 8)) {
    let word = ID_AFTER.has(previous) ? null : PATH_WORD.get(segment.toLowerCase()) || null;
    if (!word && previous === "api" && VOYAGER_QUERY_NAME.test(segment)) word = segment;
    out.push(word || "_id_");
    // What the segment was taken as, not the text it held: an identifier that
    // happens to spell a collection's name takes no identifier after it.
    previous = (word || "_id_").toLowerCase();
  }
  return "/" + out.join("/");
}

function voyagerCallKey(name) {
  let url;
  try {
    url = new URL(name);
  } catch (err) {
    return null;
  }
  if (!url.pathname.includes("/voyager/api/")) return null;
  const queryId = url.searchParams.get("queryId");
  const head = queryId ? String(queryId).split(".")[0] : "";
  const queryName = queryId ? (VOYAGER_QUERY_NAME.test(head) ? head : "other") : "";
  return { key: cleanVoyagerPath(url.pathname).slice(0, 160) + (queryName ? " " + queryName : ""),
           path: url.origin + url.pathname };
}

function noteVoyagerCall(entry) {
  const call = voyagerCallKey(entry && entry.name);
  if (!call) return;
  voyagerCallsSeen += 1;
  voyagerCalls[call.key] = (voyagerCalls[call.key] || 0) + 1;
  const VSchema = window.__InoxVoyagerSchema;
  if (VSchema && VSchema.resolveSchema(call.path)) voyagerCallsMatched += 1;
}

function followNetworkReading() {
  if (networkReadingOn && !coverageObserver && typeof PerformanceObserver !== "undefined") {
    // A new observer is handed the page's buffered entries again, so the
    // counts start again with it: switched off and on in one tab, the early
    // calls would otherwise be counted twice. The page's buffer holds its
    // first 250 entries, so on a heavy first load the count is of the calls
    // the bridge saw, which is how the studio words it.
    for (const key of Object.keys(voyagerCalls)) delete voyagerCalls[key];
    voyagerCallsSeen = 0;
    voyagerCallsMatched = 0;
    try {
      coverageObserver = new PerformanceObserver((list) => list.getEntries().forEach(noteVoyagerCall));
      coverageObserver.observe({ type: "resource", buffered: true });
    } catch (err) {
      coverageObserver = null;
    }
  } else if (!networkReadingOn && coverageObserver) {
    try { coverageObserver.disconnect(); } catch (err) {}
    coverageObserver = null;
  }
}

// The state of network reading as this page can see it, for the heartbeat
// own_pages.js sends. null while the switch has not been read: the studio
// shows that as not measured, never as off. `registered` is the worker's
// to know, so the page leaves it null and the worker's heartbeat says it.
window.__inoxNetworkReading = () => {
  if (networkReadingOn === null) return null;
  return {
    switch: networkReadingOn,
    registered: null,
    injected: networkReadingOn ? interceptorAnswered : null,
    voyager_calls_seen: networkReadingOn ? voyagerCallsSeen : null,
    matched: networkReadingOn ? voyagerCallsMatched : null,
    captured: networkReadingOn ? voyagerCaptureStats.total : null,
    last_capture_at: voyagerCaptureStats.lastCaptureTime ? new Date(voyagerCaptureStats.lastCaptureTime).toISOString() : null,
  };
};
window.__inoxVoyagerCalls = () => (networkReadingOn ? Object.assign({}, voyagerCalls) : null);

// -------------------------------------------------------------
// Reader self-timing
// -------------------------------------------------------------
// Nothing in the bridge was timed, so nothing could say whether capture was
// smooth or which read cost the most. Each reader marks the start and end
// of its read with performance.now(); the capture report carries this run's
// duration, the reads since the last report, how many of them took over
// 50 ms (Long Tasks' own threshold), and the long tasks the page's timeline
// showed during a read. Long task entries name the frame, not the script,
// and long animation frames carry no attribution for an isolated world, so
// the overlap is the closest this script can come to naming its own cost.
const SLOW_READ_MS = 50;
const READ_WINDOWS_KEPT = 200;
const readerTimings = {};
const openReads = {};
const readWindows = [];

function timingFor(extractor) {
  if (!readerTimings[extractor]) {
    readerTimings[extractor] = { reads: 0, slow_reads: 0, last_ms: null, long_tasks: 0, long_task_ms: 0 };
  }
  return readerTimings[extractor];
}

function beginRead(extractor) {
  openReads[extractor] = performance.now();
}

function endRead(extractor) {
  const started = openReads[extractor];
  if (started === undefined) return null;
  delete openReads[extractor];
  const end = performance.now();
  const ms = Math.max(0, end - started);
  const timing = timingFor(extractor);
  timing.reads += 1;
  if (ms > SLOW_READ_MS) timing.slow_reads += 1;
  timing.last_ms = ms;
  readWindows.push({ extractor, start: started, end });
  if (readWindows.length > READ_WINDOWS_KEPT) readWindows.splice(0, readWindows.length - READ_WINDOWS_KEPT);
  return ms;
}

// The figures since the last report, and this run's duration; the counters
// start again. A reader that never began a read has no duration: null, so
// the studio stores "not measured" rather than a zero.
function takeTiming(extractor) {
  const timing = timingFor(extractor);
  const out = {
    duration_ms: timing.last_ms === null ? null : Math.round(timing.last_ms * 10) / 10,
    reads: timing.reads,
    slow_reads: timing.slow_reads,
    long_tasks: timing.long_tasks,
    long_task_ms: Math.round(timing.long_task_ms * 10) / 10,
  };
  timing.reads = 0;
  timing.slow_reads = 0;
  timing.long_tasks = 0;
  timing.long_task_ms = 0;
  return out;
}

// A long frame's entry is delivered after the frame ends, so the frame that
// overlaps a read is counted against that reader's reads and rides with its
// next report: the figures on a capture row are the long frames delivered
// since the reader's previous report.
function noteLongTask(entry) {
  if (!entry || typeof entry.startTime !== "number" || typeof entry.duration !== "number") return;
  const start = entry.startTime;
  const end = start + entry.duration;
  for (const read of readWindows) {
    // A read that ran inside the frame overlapped it, however short the
    // read; the milliseconds counted are the part of the frame inside it.
    if (read.end < start || read.start > end) continue;
    const timing = timingFor(read.extractor);
    timing.long_tasks += 1;
    timing.long_task_ms += Math.max(0, Math.min(end, read.end) - Math.max(start, read.start));
  }
}

// One source of long frames, so one slow frame is not counted twice: a long
// animation frame (Chrome 123 and later) contains the long task inside it,
// so where the browser has both, the frame is observed and the task is not.
// LONG_FRAME_SOURCE says which, for the record of what a figure counts.
let LONG_FRAME_SOURCE = null;
try {
  if (typeof PerformanceObserver !== "undefined") {
    const supported = PerformanceObserver.supportedEntryTypes || [];
    LONG_FRAME_SOURCE = supported.includes("long-animation-frame") ? "long-animation-frame"
      : (supported.includes("longtask") ? "longtask" : null);
    if (LONG_FRAME_SOURCE) {
      new PerformanceObserver((list) => list.getEntries().forEach(noteLongTask))
        .observe({ type: LONG_FRAME_SOURCE, buffered: true });
    }
  }
} catch (err) {
  LONG_FRAME_SOURCE = null;
}

// own_pages.js reads the creator's pages in this same world and times its
// readers through this.
window.__inoxReaderTiming = Object.freeze({
  begin: beginRead, end: endRead, take: takeTiming, longFrameSource: () => LONG_FRAME_SOURCE
});

/**
 * Records one extractor run in the studio's capture log.
 *
 * When LinkedIn changes its markup, an extractor finds nothing and says
 * nothing, which from the creator's side looks exactly like nobody engaging.
 * drift names what could not be read on a page that plainly had it, so the
 * Setup screen can say "capture has stopped working" instead of silence.
 * Once per extractor per page per minute, so a busy feed is not a flood.
 */
const lastCaptureReport = {};
function reportCapture(extractor, itemsSeen, itemsKept, drift, timing) {
  // The read ends here whether or not the report gets through the throttle,
  // so every read is counted and a throttled report still stands for them.
  endRead(extractor);
  // Keyed on whether this run drifted, so a clean read always gets through
  // after a drifted one. Otherwise an early read that ran before the page
  // finished rendering logged drift, and the good read that followed was
  // throttled away, leaving a working reader marked broken for a minute.
  const key = extractor + "|" + window.location.pathname + "|" + (drift && drift.length ? "drift" : "ok");
  const now = Date.now();
  if (lastCaptureReport[key] && now - lastCaptureReport[key] < 60000) return;
  lastCaptureReport[key] = now;
  studioApi("/api/v1/bridge/capture", Object.assign({
    extractor,
    page_kind: window.location.pathname.split("/")[1] || "home",
    items_seen: itemsSeen,
    items_kept: itemsKept,
    drift: drift && drift.length ? drift : null,
    extension_version: chrome.runtime.getManifest().version
  }, timing || takeTiming(extractor)));
}

// The card stamper runs in the page's own world (card_urns.js) and cannot
// reach the worker, so it posts its run on the window channel the
// interceptor uses: how many feed cards were on screen, how many carry a
// post id, and its own timing. Cards on screen with not one id among them is
// the React properties changing shape, which is the drift that leaves every
// feed engager without a post. It used to write the run onto LinkedIn's root
// element, a mark any script on the page could read.
function forwardCardUrnsReport(report) {
  if (!report || typeof report !== "object") return;
  const seen = Number(report.seen) || 0;
  const stamped = Number(report.stamped) || 0;
  reportCapture("card_urns", seen, stamped, seen >= 3 && stamped === 0 ? ["card_urn"] : [], {
    duration_ms: typeof report.duration_ms === "number" ? Math.round(report.duration_ms * 10) / 10 : null,
    reads: Number(report.reads) || 0,
    slow_reads: Number(report.slow_reads) || 0,
    long_tasks: 0,
    long_task_ms: 0,
  });
}

console.log("[Inox Hydra Bridge] Content script active on linkedin.com");

// Listen for messages from Side Panel or Background
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "INJECT_POST") {
    injectIntoLinkedInComposer(message.content)
      .then(success => sendResponse({ status: success ? "success" : "failed" }))
      .catch(err => sendResponse({ status: "error", error: err.message }));
    return true; // Keep channel open for async response
  }
});

/**
 * The editor of LinkedIn's post composer, or null.
 *
 * The first matching editor in the page used to be taken. LinkedIn's comment
 * boxes and message boxes are the same kind of editor, and the composer
 * renders last, in a modal, so a draft went into an open comment box behind
 * the composer, or into a message to a contact, and the page said it was in
 * the composer. The composer always opens as a dialog; an editor inside a
 * comment or messaging block, or labelled for a comment, message or reply,
 * is never it.
 */
function composerEditor() {
  const editors = document.querySelectorAll(
    '.share-creation-state__text-editor div[contenteditable="true"], div.ql-editor[contenteditable="true"], div[role="textbox"][contenteditable="true"]'
  );
  for (const editor of editors) {
    if (!editor.closest('[role="dialog"], .artdeco-modal, dialog')) continue;
    if (editor.closest('.comments-comment-box, .comments-comment-texteditor, [class*="comments-comment"], [class*="msg-"], [data-view-name*="comment"], [data-testid*="comment" i]')) continue;
    const label = ["aria-label", "aria-placeholder", "data-placeholder"].map((a) => editor.getAttribute(a) || "").join(" ");
    const dialog = editor.closest('[role="dialog"], .artdeco-modal, dialog');
    if (/comment|message|reply/i.test(label + " " + (dialog.getAttribute("aria-label") || ""))) continue;
    return editor;
  }
  return null;
}

async function injectIntoLinkedInComposer(text) {
  // 1. Check if composer modal is already open
  let editor = composerEditor();

  // 2. If not open, try to click the "Start a post" button on feed
  if (!editor) {
    const startPostBtn = document.querySelector('button.share-box-feed-entry__trigger') ||
                         document.querySelector('button[aria-label*="Start a post"]') ||
                         document.querySelector('.share-box-feed-entry__trigger');
    if (startPostBtn) {
      startPostBtn.click();
      // Wait up to 1.5s for modal to render
      for (let i = 0; i < 15; i++) {
        await new Promise(r => setTimeout(r, 100));
        editor = composerEditor();
        if (editor) break;
      }
    }
  }

  // The answer is the side panel's to say, which asked: nothing is drawn
  // into LinkedIn's page.
  if (!editor) return false;

  // 3. Focus editor and insert text cleanly
  editor.focus();

  // Clear placeholder text if needed
  if (editor.innerText.trim() === "") {
    editor.innerHTML = "";
  }

  // Execute native insert command to preserve undo stack and trigger React listeners
  const success = document.execCommand('insertText', false, text);
  if (!success) {
    // Fallback: direct innerText + input event dispatch
    editor.innerText = text;
  }

  // Dispatch events to notify LinkedIn's React / Quill state
  editor.dispatchEvent(new Event('input', { bubbles: true }));
  editor.dispatchEvent(new Event('change', { bubbles: true }));
  return true;
}

// What the creator must act on, or must know was not saved, is said in the
// side panel and never drawn into LinkedIn's page (decision D3; the last of
// the in-page notices moved in cycle 4, the review's S7). The worker keeps
// the sentence for this browser session, the action badge carries it ("!"
// for a warning, orange while captures wait) until the panel opens, and the
// panel shows it at its top the next time it opens, as text: a notice can
// carry a studio reason or a name, never markup.
function noticeToPanel(message, kind) {
  try {
    chrome.runtime.sendMessage({
      action: "PAGE_NOTICE",
      message: String(message || ""),
      kind: kind === "waiting" ? "waiting" : "warning",
      page_kind: window.location.pathname.split("/")[1] || "home"
    }, () => { void chrome.runtime.lastError; });
  } catch (err) {}
}

// -------------------------------------------------------------
// Passive Creator Analytics Sync (100% Safe Local Extraction)
// -------------------------------------------------------------
// LinkedIn is a single page application. A listener registered inside a URL
// guard that is evaluated once, at injection time, never fires for a creator who
// navigates to analytics from the feed, which is how everyone reaches it. Watch
// the path instead.
let lastAnalyticsPath = null;
let analyticsReadTimer = null;

function maybeExtractAnalytics(force) {
  const path = window.location.pathname;
  // The account's own creator analytics only. Any path containing "/analytics"
  // used to qualify, which includes one post's summary page
  // (/analytics/post-summary/...), and that post's figures were then written
  // as the whole account's numbers for the day.
  if (!path.startsWith("/analytics/creator")) {
    // Leaving the page clears the latch, so returning to it reads again.
    lastAnalyticsPath = null;
    return;
  }
  if (!force && path === lastAnalyticsPath) return;
  lastAnalyticsPath = path;

  // Collapse bursts: a route change plus a re-render should read once.
  if (analyticsReadTimer) clearTimeout(analyticsReadTimer);
  analyticsReadTimer = setTimeout(extractAndSyncAnalytics, 2000);
}

// Announces in-app navigation from the Navigation API, with the URL as a net.
//
// popstate covers back and forward only, and LinkedIn navigates with
// pushState, which emits no event. The previous fix wrapped history.pushState
// and replaceState, which looked right and did nothing: a content script runs
// in an isolated world with its own copy of the page's JavaScript globals, so
// the wrapper replaced this script's history methods while LinkedIn went on
// calling its own. The fix after that compared location.href on every DOM
// mutation batch and on a 1 s poll, which saw the route late and cost a
// whole-document observer in every LinkedIn tab.
//
// The browser dispatches the Navigation API's events on the shared
// window.navigation object, as it does popstate, so the isolated world
// receives them without any code in the page's world: currententrychange
// fires once the new entry is current, in the same task as the pushState
// (checked in headless Chromium 153 with an isolated-world script; the
// record for cycle 4, track 1, item 7 holds the result). The URL is compared
// in the handler, so a replaceState to the same address announces nothing.
// The 5 s poll is a net for a browser without the API, and does nothing
// while the tab is hidden.
let lastSeenHref = window.location.href;

function checkForNavigation() {
  const href = window.location.href;
  if (href === lastSeenHref) return;
  lastSeenHref = href;
  window.dispatchEvent(new Event("studio:locationchange"));
}

if ("navigation" in window && window.navigation && typeof window.navigation.addEventListener === "function") {
  window.navigation.addEventListener("currententrychange", checkForNavigation);
}
setInterval(() => {
  if (document.visibilityState === "visible") checkForNavigation();
}, 5000);

maybeExtractAnalytics();
window.addEventListener("load", () => maybeExtractAnalytics());
window.addEventListener("popstate", () => maybeExtractAnalytics());
window.addEventListener("studio:locationchange", () => maybeExtractAnalytics());

// Changing the range selector rewrites the figures without changing the URL.
// The studio asks the creator to do exactly that when it refuses a multi-day
// window, so it has to notice when they do.
document.addEventListener("click", (e) => {
  if (!window.location.pathname.includes("/analytics")) return;
  const trigger = e.target && e.target.closest
    ? e.target.closest('.artdeco-dropdown__item, [role="option"], .artdeco-dropdown__trigger')
    : null;
  if (trigger) setTimeout(() => maybeExtractAnalytics(true), 1200);
}, true);

/**
 * Reads a LinkedIn metric figure.
 *
 * LinkedIn abbreviates: "1.2K", "13K", "1.5M". The old implementation called
 * parseInt on that text, so "1.2K" became 1 and "1.5M" became 1. Only creators
 * under a thousand impressions were ever recorded correctly, and the engagement
 * rate then divided by the truncated figure.
 *
 * Returns {value, precision} or null when the text is not a number at all.
 * precision is "exact" for a fully written figure and "rounded" for an
 * abbreviated one, because "1.2K" means somewhere in [1150, 1250) and the studio
 * should not later present it as though it meant exactly 1200.
 *
 * The page's language decides what a separator means. On a German or Italian
 * page "8.210" is eight thousand two hundred and ten and "1,2K" is 1.2K; read
 * as English the first became 8, marked exact. So the decimal mark is the
 * page's (document.documentElement.lang, or `lang` when given), thousands are
 * grouped in threes by the other mark or a space, and a figure with no certain
 * reading is refused rather than stored: a dotted "8.210" on a page that names
 * no language, a comma with three digits after it on a German page, or a
 * fraction with no K or M after it. A page with no language is read as English,
 * LinkedIn's default.
 */
function parseMetricValue(raw, lang) {
  if (!raw) return null;
  const text = String(raw).replace(/[   ]/g, " ").trim();
  const match = text.match(/^(\d[\d.,' ]*?)\s*([A-Za-z]+\.?)?$/);
  if (!match) return null;

  // Languages LinkedIn serves whose decimal mark is a comma.
  const COMMA_DECIMAL = ["cs", "da", "de", "el", "es", "fi", "fr", "hu", "id", "it", "nl", "no", "nb",
    "pl", "pt", "ro", "ru", "sv", "tr", "uk"];
  const pageLang = lang !== undefined ? lang
    : (typeof document !== "undefined" && document.documentElement && document.documentElement.lang) || "";
  const decimalMark = COMMA_DECIMAL.includes(String(pageLang).toLowerCase().slice(0, 2)) ? "," : ".";
  const groupMark = decimalMark === "," ? "." : ",";

  // K, M and B, and the words LinkedIn uses for them in other languages.
  const MULTIPLIERS = { k: 1e3, tsd: 1e3, mil: 1e3, m: 1e6, mio: 1e6, mln: 1e6, mn: 1e6, b: 1e9, mrd: 1e9, md: 1e9 };
  const suffix = (match[2] || "").toLowerCase().replace(/\.$/, "");
  if (suffix && !(suffix in MULTIPLIERS)) return null;

  const parts = match[1].split(decimalMark);
  if (parts.length > 2) return null;
  const whole = parts[0].trim();
  const fraction = parts.length === 2 ? parts[1].trim() : "";
  if (parts.length === 2 && !/^\d+$/.test(fraction)) return null;
  if (!/^\d+$/.test(whole)) {
    // Grouped thousands: one mark, used throughout, with three digits after it.
    const grouped = new RegExp("^\\d{1,3}(?:[" + groupMark + " ']\\d{3})+$");
    // Indian lakh and crore grouping, "12,34,567", wherever the comma groups.
    const lakh = groupMark === "," && /^\d{1,2}(?:,\d{2})+,\d{3}$/.test(whole);
    if (!(grouped.test(whole) || lakh) || new Set(whole.replace(/\d/g, "")).size > 1) return null;
  }
  // A count has no fraction unless it is abbreviated.
  if (fraction && !suffix) return null;

  const base = parseFloat(whole.replace(/\D/g, "") + (fraction ? "." + fraction : ""));
  if (!isFinite(base)) return null;
  return {
    value: Math.round(base * (suffix ? MULTIPLIERS[suffix] : 1)),
    precision: suffix ? "rounded" : "exact"
  };
}

/**
 * Finds which period the metric cards are reporting.
 *
 * This matters more than it looks. The figure on a creator analytics card is an
 * aggregate over a selected window, most often 7 or 28 days. Writing it into a
 * row keyed by today's date turned a 28 day total into today's impressions, and
 * the dashboard then summed overlapping windows. Returning null is honest, and
 * the backend refuses the write, which is better than silently recording a
 * number that means something other than what the column says.
 *
 * Any "N days" is read, in English and the other languages LinkedIn serves,
 * so "Past 365 days" is no longer a window nobody recognised. A range control
 * whose words are not understood (a custom range prints dates) answers
 * "unrecognised", which the studio refuses as a daily figure. null is kept for
 * a page with no range control at all.
 */
function analyticsPeriodOf(text) {
  const t = (text || "").toLowerCase();
  if (/\b24\s*(hours?|stunden|ore|heures|horas|uur|timmar|timer|godzin)(?![a-z])|\b(past|last) day\b/.test(t)) return "1d";
  if (/\b12\s*(months?|monate[n]?|mesi|mois|meses|maanden|månader|miesięcy)(?![a-z])|\b(past|last) year\b/.test(t)) return "365d";
  // An adjective may sit between the figure and the word: "365 derniers jours".
  const days = /\b(\d{1,3})\s*(?:[a-zà-ÿ]+\s+)?(days?|tage[n]?|giorni|jours|días|dias|dagen|dagar|dage|dni|dní|gün)(?![a-z])/.exec(t);
  if (days) return Number(days[1]) === 1 ? "1d" : Number(days[1]) + "d";
  return null;
}

function detectAnalyticsPeriod() {
  const candidates = document.querySelectorAll(
    '.artdeco-dropdown__trigger, [data-test-analytics-time-range], .analytics-time-range-selector, button[aria-label*="time range" i]'
  );
  let unread = false;
  for (const el of candidates) {
    const text = el.innerText || "";
    const period = analyticsPeriodOf(text);
    if (period) return period;
    // A generic dropdown without a figure in it is some other control.
    if (/\d/.test(text) || !el.matches(".artdeco-dropdown__trigger")) unread = unread || !!text.trim();
  }
  return unread ? "unrecognised" : null;
}

function extractAndSyncAnalytics() {
  try {
    beginRead("analytics");
    const metricElements = document.querySelectorAll('[data-test-metric-value], .member-analytics-addon__metric-value, .creator-analytics-metric__value, .analytics-metric-summary');
    let impressions = null;
    let engagements = null;
    let followers = null;
    // Precision belongs to a reading, not to the page. A single payload-wide
    // flag was escalated by any abbreviated card on screen, including ones whose
    // values are then discarded, so an exact impressions figure of 412 was
    // marked rounded because "Profile viewers 1.3K" sat beside it.
    const seen = {};

    metricElements.forEach(el => {
      const parent = el.closest('[data-test-metric-card], .creator-analytics-metric') || el.parentElement;
      const text = parent ? parent.innerText.toLowerCase() : "";
      const parsed = parseMetricValue(el.innerText);
      if (!parsed) return;
      if (text.includes("impression")) { impressions = parsed.value; seen.impressions = parsed.precision; }
      else if (text.includes("engagement") || text.includes("reaction")) { engagements = parsed.value; seen.reactions = parsed.precision; }
      else if (text.includes("follower")) { followers = parsed.value; seen.followers = parsed.precision; }
    });

    // Cards on the page but no label recognised, or an analytics page with no
    // cards at all: either way the reader no longer matches LinkedIn's markup.
    const analyticsDrift = [];
    if (!metricElements.length) analyticsDrift.push("metric_cards");
    else if (impressions === null && followers === null) analyticsDrift.push("metric_labels");
    reportCapture("analytics", metricElements.length,
      [impressions, engagements, followers].filter(v => v !== null).length, analyticsDrift);
    endRead("analytics");

    if (impressions === null && followers === null) return;

    // One row carries one precision, so report the least precise reading that
    // actually contributed a stored value.
    const contributing = Object.values(seen);
    const precision = contributing.includes("rounded") ? "rounded" : "exact";

    const period = detectAnalyticsPeriod();
    const today = new Date().toISOString().slice(0, 10);

    studioApi("/api/analytics/ingest", {
        // The LinkedIn account signed in here, which the studio checks
        // against the profile open in it.
        author: signedInVanity,
        period_label: period,
        precision: precision,
        series: [{
          date: today,
          period_label: period,
          precision: precision,
          impressions: impressions,
          reactions: engagements,
          followers: followers
        }]
      })
      // Says what the studio did. "Synced" used to follow any answer at all,
      // including none, so a creator whose studio was closed or unpaired was
      // told their figures were saved.
      .then(result => {
        if (!result) {
          noticeToPanel("Inox Hydra: could not reach your studio, so these analytics were not saved.", "warning");
          return;
        }
        if (result.status === "refused") {
          noticeToPanel(
            result.httpStatus === 401 || result.httpStatus === 403
              ? "Inox Hydra: the studio refused this browser, so these analytics were not saved. Open the studio once in this browser, then reload this page."
              : "Inox Hydra: the studio did not save these analytics" + (result.detail ? ": " + result.detail + "." : "."),
            "warning"
          );
          return;
        }
        if (result.status === "window_mismatch") {
          const cover = period === "unrecognised"
            ? "Inox Hydra: could not tell which period these figures cover"
            : "Inox Hydra: these figures cover " + (period || "an unknown period");
          const kept = result.followers_saved > 0 ? " Your follower count was saved." : "";
          noticeToPanel(
            cover + ", so they were not saved as today's numbers." + kept +
            " Set the range to 24 hours to sync a daily figure.",
            "warning"
          );
          return;
        }
        // A saved day is confirmed on the action badge and in the side
        // panel, from the worker's own record of the relay (decision D3):
        // nothing is drawn into LinkedIn's page for a capture that worked.
        if (result.status === "success" && result.buckets_ingested > 0) return;
        noticeToPanel("Inox Hydra: the studio saved nothing from this page.", "warning");
      })
      .catch(() => {});
  } catch (e) {
    endRead("analytics");
    console.debug("[Studio Bridge] Passive analytics parse:", e);
  }
}

// -------------------------------------------------------------
// Post Identity: binding what the creator wrote to what LinkedIn published
// -------------------------------------------------------------

/**
 * Pull a LinkedIn activity URN out of a URL or a DOM attribute.
 *
 * Three shapes appear in the wild:
 *   /feed/update/urn:li:activity:7390000000000000103/
 *   /feed/update/urn:li:share:7390000000000000103/
 *   /posts/someone_slug-activity-7390000000000000103-AbCd
 */
function extractActivityUrn(text) {
  if (!text) return null;
  const direct = text.match(/urn:li:(?:activity|share|ugcPost):\d+/);
  if (direct) return direct[0];
  const slug = text.match(/-activity-(\d{6,})/);
  if (slug) return `urn:li:activity:${slug[1]}`;
  return null;
}

const POST_CARD_SELECTOR =
  '[data-urn^="urn:li:activity:"], [data-id^="urn:li:activity:"], [data-urn*="ugcPost"], [data-urn*="share"]';
const POST_ACTOR_SELECTOR =
  ".update-components-actor__meta-link, a.update-components-actor__image, .update-components-actor a[href*='/in/']";

/**
 * The post whose list LinkedIn opened in a modal, or null.
 *
 * LinkedIn renders a post's reactions list in a modal in a body-level outlet,
 * outside every feed card, so nothing in the modal says whose post it is. The
 * reader used to take the first post in the feed instead, and when that was
 * the creator's (normal right after posting) every reactor of every stranger's
 * post the creator opened became the creator's lead.
 *
 * The click that opened the list does know: it landed inside that post's
 * card. Clicks inside a dialog (scrolling the list, "Show more") leave the
 * remembered post as it is; any other click replaces it, with null when it
 * landed outside every card we can read, so a list opened from such a card is
 * never filed under the post clicked before it.
 */
let postOpenedFromClick = null;

document.addEventListener("click", (e) => {
  const target = e.target && e.target.closest ? e.target : null;
  if (!target || target.closest('.artdeco-modal, [role="dialog"], dialog')) return;
  const card = target.closest(POST_CARD_SELECTOR);
  postOpenedFromClick = card ? { urn: postUrnFor(card), author: postAuthorFor(card) } : null;
}, true);

function postOpenedFor(element) {
  if (!element.closest('.artdeco-modal, [role="dialog"], dialog')) return null;
  return postOpenedFromClick;
}

/**
 * The vanity of whoever wrote the post an element belongs to, or "".
 *
 * The studio stores an engager as a lead only when the post is the creator's,
 * and this is how it knows: the actor link on the update card that contains
 * the element. A comment card has its own author link, so the search starts at
 * the containing update rather than at the element. A list in a modal belongs
 * to the post whose card was clicked to open it. Only on a permalink, where
 * the page shows one post, is the page's first actor the post's; in the feed
 * the first actor is merely the first post's, and "" is the honest answer. A
 * company page's post links to /company/, which yields "" and is correctly not
 * the creator's.
 */
function postAuthorFor(element) {
  const card = element.closest(POST_CARD_SELECTOR);
  let link = card && card.querySelector(POST_ACTOR_SELECTOR);
  if (!card) {
    const opened = postOpenedFor(element);
    if (opened) return opened.author;
  }
  if (!link && extractActivityUrn(window.location.pathname)) {
    link = document.querySelector("main " + POST_ACTOR_SELECTOR);
  }
  if (!link) return "";
  const match = /\/in\/([^/?#]+)/.exec(link.getAttribute("href") || "");
  return match ? decodeURIComponent(match[1]).toLowerCase() : "";
}

/**
 * The URN of the post a given element belongs to.
 *
 * On a permalink the URL is authoritative and needs no markup at all. In the
 * feed, where several posts share a page, the containing update card carries
 * the URN in a data attribute. Reading the URL first means the common case
 * never depends on a class name LinkedIn can rename. A list in a modal sits
 * outside every card and belongs to the post whose card opened it.
 */
function postUrnFor(element) {
  const fromUrl = extractActivityUrn(window.location.pathname);
  if (fromUrl) return fromUrl;

  let node = element;
  while (node && node !== document.body) {
    for (const attr of ["data-urn", "data-id", "data-activity-urn"]) {
      const value = node.getAttribute && node.getAttribute(attr);
      const urn = extractActivityUrn(value);
      if (urn) return urn;
    }
    node = node.parentElement;
  }
  const opened = postOpenedFor(element);
  return opened ? opened.urn : null;
}

/**
 * The text of the post currently on screen, used to recognise which of the
 * creator's drafts this is.
 */
function readPostBodyText() {
  const selectors = [
    ".feed-shared-update-v2__description",
    ".update-components-text",
    ".feed-shared-inline-show-more-text",
    '[data-test-id="main-feed-activity-card__commentary"]',
  ];
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el && el.innerText && el.innerText.trim().length > 20) {
      return el.innerText.trim();
    }
  }
  return "";
}

let lastBoundUrn = null;

/**
 * Offer the studio the URN of the post the creator is looking at.
 *
 * The studio decides whether it matches something it is waiting for. Matching
 * lives there rather than here so the rule is testable and so this script never
 * has to track which post is armed. A refusal is the normal case: most posts
 * the creator opens are not their own.
 */
function maybeBindPostUrn() {
  const urn = extractActivityUrn(window.location.pathname);
  if (!urn || urn === lastBoundUrn) return;

  const body = readPostBodyText();
  if (!body) return;
  lastBoundUrn = urn;

  // A plain repost's permalink shows the creator's words under the repost's
  // own id, and binding it left the creator's real post unbindable. So a
  // repost is never offered, and the post's author goes with the rest, for the
  // studio to refuse a post that is not the creator's.
  const header = document.querySelector(
    ".update-components-header__text-view, .update-components-header, .feed-shared-header, [data-view-name='feed-full-update-header']"
  );
  const opening = (document.querySelector("main") || document.body).innerText.split("\n").slice(0, 6).join(" ");
  if (/\breposted\b/i.test((header && header.innerText) || "") || /\breposted this\b/i.test(opening)) return;

  studioApi("/api/v1/posts/bind-urn", { activity_urn: urn, post_text: body, post_author: postAuthorFor(document.body) })
    .then(result => {
      if (!result) return;
      // A post linked to its draft is confirmed on the badge and in the
      // side panel, from the worker's record of the relay (decision D3).
      if (result.status === "bound") return;
      // "ambiguous" means the studio holds more than one draft whose opening
      // matches this post and will not guess. Only the creator can settle it,
      // and nothing said so: this answer was read for "bound" and discarded.
      if (result.status === "ambiguous" && !shownRefusals.ambiguous_bind) {
        shownRefusals.ambiguous_bind = true;
        noticeToPanel(
          "Inox Hydra: more than one of your drafts opens like this post, so it was not linked. " +
          "Open the studio's Posts screen to say which one it is.",
          "warning"
        );
        return;
      }
      if (result.status === "kept") {
        noticeToPanel(
          "Inox Hydra: your studio was busy, so linking this post is waiting and will be sent again.",
          "waiting"
        );
      }
    })
    .catch(() => {});
}

// Binding is cheap and idempotent, so run it on the same signals as everything
// else rather than inventing a separate schedule for it.
window.addEventListener("load", maybeBindPostUrn);
window.addEventListener("popstate", maybeBindPostUrn);
window.addEventListener("studio:locationchange", () => {
  lastBoundUrn = null;
  setTimeout(maybeBindPostUrn, 1500);
});
setTimeout(maybeBindPostUrn, 2500);

// -------------------------------------------------------------
// Auto-Capture Engagers (Commenters & Reactors) into Local CRM
// -------------------------------------------------------------
let lastCommentScrapeTime = 0;
const knownEngagersSet = new Set();
// Shown once per page, per reason, so a creator browsing the feed before
// Setup is told once why nothing is captured, not on every post. Keyed on the
// reason code, because there is more than one refusal worth saying and saying
// only the first of them is how "import your posts first" stayed invisible.
const shownRefusals = {};

/**
 * Identifies an engagement, not a person.
 *
 * The key used to be identity alone, and the set that holds it is module level
 * and never clears across LinkedIn's in-app navigation. So the first post a
 * creator opened claimed every commenter on it, and the same people were
 * silently filtered out of every later post in that session. They were counted
 * as already known rather than as skipped, so no toast fired and nothing said
 * a capture had been dropped. Per-post attribution is the feature this
 * extension exists to feed, and it was losing exactly the rows that feed it.
 *
 * Scoping by post fixes that. When the URN cannot be read from the card, the
 * page path stands in, which still separates one post's page from another's.
 * The path is used for scoping ONLY and is never stored as a post_urn: a value
 * this extension invented must not end up in LinkedIn's namespace.
 */
/**
 * Returns the first element matching the HIGHEST PRIORITY selector that finds
 * usable text, trying the selectors in the order given.
 *
 * This exists because querySelector with a comma separated list does NOT do
 * that. It returns the first element in DOCUMENT order matching any of them,
 * so the order a developer writes the selectors in carries no weight at all.
 *
 * The commenter name selector ended with a bare [aria-hidden="true"], and
 * LinkedIn puts that attribute on avatar wrappers, bullet separators and
 * relative timestamps, all of which sit before the name in the card. Verified
 * against a card shaped like LinkedIn's: the old list returned the avatar's
 * empty string, so the name failed the length guard and the whole commenter
 * was dropped. Where a timestamp came first it returned "2h", which passes the
 * guard, and a lead named "2h" entered the CRM with a real profile URL.
 *
 * Trying one selector at a time makes the priority order mean what it looks
 * like it means.
 */
function firstNamedElement(root, selectors) {
  if (!root) return null;
  for (const selector of selectors) {
    let candidate = null;
    try {
      candidate = root.querySelector(selector);
    } catch (err) {
      continue;
    }
    if (candidate && (candidate.innerText || candidate.textContent || "").trim().length >= 2) {
      return candidate;
    }
  }
  return null;
}

function engagerDedupeKey(profileUrl, name, headline, postUrn) {
  const identity = profileUrl || `${name}_${headline}`;
  const scope = postUrn || window.location.pathname || "unknown-surface";
  return `${identity}|${scope}`;
}


/**
 * True only on a page that shows engagement with a specific post.
 *
 * The reactor scraper used to run on every linkedin.com page and match a bare
 * `li` inside any `.artdeco-modal` or `div[role="dialog"]`. A messaging overlay,
 * a notifications panel, a connection request modal or a search filter dropdown
 * all satisfied that, so anyone whose name sat in a list item next to an /in/
 * link was stored as having reacted to a post. The creator would then open the
 * CRM and send a stranger a message referencing an engagement that never
 * happened, and once written the fabricated row was indistinguishable from a
 * real one.
 */
function isPostEngagementSurface() {
  const path = window.location.pathname;
  return (
    path === "/feed/" ||
    path.startsWith("/feed/") ||
    path.startsWith("/posts/") ||
    // "/in/" is deliberately absent.
    //
    // A profile page renders that person's comments on OTHER people's posts.
    // postUrnFor then walks up to a stranger's data-urn, and those commenters
    // were written to lead_interactions carrying a post_urn the creator never
    // authored. Every one of those rows is an engagement with somebody else's
    // content, recorded as if it were engagement with theirs.
    //
    // The reactions path is gated by looksLikeReactionsList; the commenter
    // path had no equivalent, so this is the gate.
    /\/activity-\d+/.test(path)
  );
}

/**
 * True when this container is a list of people who reacted to a post.
 *
 * Scoping by page path is not enough, because a messaging overlay or a
 * notifications panel can be open on any page. What separates a reactions modal
 * from those is the reactions markup itself, so that is what gets checked:
 * either a reactor-specific class, or a heading that names reactions. Anything
 * else is not a reactions list and contributes no leads.
 */
function looksLikeReactionsList(container) {
  if (!container) return false;
  if (container.querySelector('li.social-details-reactors-tab__item, .reactions-menu__item, .social-details-reactors-tab')) {
    return true;
  }
  const heading = container.querySelector('h2, h1, [role="heading"], .artdeco-modal__header');
  const title = heading ? (heading.innerText || "").toLowerCase() : "";
  return /reaction|reacted|likes\b/.test(title);
}

/**
 * Commenters in LinkedIn's rebuilt post layout.
 *
 * Measured on a live post page, 27 Sep 2026: none of the comment classes the
 * reader above looks for exist any more; class names are hashed per build.
 * The comment list keeps a data-testid containing "commentList", and each
 * comment is a block holding one person's profile link, then their name,
 * connection degree, headline, age and words. A reply nests inside the
 * comment it answers, so a comment's block is the largest ancestor of its
 * profile link that still contains links to that person only.
 */
function vanityFromHref(href) {
  const match = /\/in\/([^/?#]+)/i.exec(href || "");
  return match ? decodeURIComponent(match[1]).toLowerCase() : "";
}

function readNewLayoutComments() {
  const found = [];
  const lists = document.querySelectorAll('[data-testid*="commentList"]');
  for (const list of lists) {
    const seen = new Set();
    // Each list is one post's. It opens with the post header, so its first
    // profile link outside the reactor faces is that post's author, and the
    // post's URN is on the card around it. Both were read once, from the
    // first list on the page, and applied to every commenter in every list.
    const authorLink = Array.from(list.querySelectorAll('a[href*="/in/"]'))
      .find((a) => !a.closest('[data-testid^="ReactionFacepile"]'));
    const postAuthor = authorLink ? vanityFromHref(authorLink.getAttribute("href")) : "";
    const postUrn = postUrnFor(list);
    for (const link of list.querySelectorAll('a[href*="/in/"]')) {
      const vanity = vanityFromHref(link.getAttribute("href"));
      if (!vanity || seen.has(vanity)) continue;
      // The list also holds the post's reactor faces, and a commenter who also
      // reacted appears there first, as an avatar with no words beside it.
      if (link.closest('[data-testid^="ReactionFacepile"]')) continue;

      let block = link;
      while (block.parentElement && block.parentElement !== list) {
        const people = new Set(Array.from(block.parentElement.querySelectorAll('a[href*="/in/"]'))
          .map((a) => vanityFromHref(a.getAttribute("href"))).filter(Boolean));
        if (people.size > 1) break;
        block = block.parentElement;
      }

      const lines = (block.innerText || "").split("\n").map((l) => l.trim()).filter(Boolean);
      // Marked as read only once a block with words is found, so an earlier
      // bare avatar link cannot hide the comment that follows it.
      if (lines.length < 3) continue;
      seen.add(vanity);
      const degreeAt = lines.findIndex((l) => /^•\s*(1st|2nd|3rd\+?|author|you)/i.test(l) || /^author$/i.test(l));
      const name = degreeAt > 0 ? lines[degreeAt - 1] : lines.find((l) => !/premium|profile|•/i.test(l));
      const timeAt = lines.findIndex((l, i) => i > degreeAt && /^\d+\s*(s|m|h|d|w|mo|yr)s?$/i.test(l));
      const headline = degreeAt >= 0 && lines[degreeAt + 1] && degreeAt + 1 !== timeAt ? lines[degreeAt + 1] : "";
      const text = timeAt >= 0 ? (lines[timeAt + 1] || "") : "";
      if (!name) continue;
      found.push({
        name,
        headline,
        profileUrl: `https://www.linkedin.com/in/${encodeURIComponent(vanity)}/`,
        vanity,
        commentText: /^\d+$/.test(text) ? "" : text,
        postAuthor,
        postUrn,
      });
    }
  }
  return found;
}

/**
 * Runs the engager read at most every 4 s, and always once more after the
 * last change.
 *
 * The read used to run on the first mutation and drop every call inside the
 * next 4 s. A reactions list that arrived just after its modal shell fell into
 * that window and was not read until some unrelated change happened later, if
 * it ever did. One pending read is kept instead: it runs 600 ms after the
 * change that scheduled it, or when the 4 s since the last read are up.
 */
let engagerReadTimer = null;

function scheduleEngagerRead() {
  if (engagerReadTimer || !isPostEngagementSurface()) return;
  const wait = Math.max(600, 4000 - (Date.now() - lastCommentScrapeTime));
  engagerReadTimer = setTimeout(() => {
    engagerReadTimer = null;
    observeAndCaptureEngagers();
  }, wait);
}

function observeAndCaptureEngagers() {
  if (!isPostEngagementSurface()) return;

  lastCommentScrapeTime = Date.now();
  beginRead("engagers");

  const leads = [];

  // 1. Capture Commenters from Feed and Post detail pages
  const commentSelectors = [
    'article.comments-comment-item',
    '.comments-comments-list__comment-item',
    '.comments-comment-item',
    '.comments-comment-entity',
    '[data-view-name="feed-full-update-comment"]',
    'div[data-id^="urn:li:comment:"]'
  ].join(', ');

  const commentCards = document.querySelectorAll(commentSelectors);
  const leadsBeforeComments = leads.length;
  commentCards.forEach(card => {
    try {
      const nameEl = firstNamedElement(card, [
        '.comments-post-meta__name-text',
        '[data-anonymize="person-name"]',
        '.comments-comment-item__profile-link span[aria-hidden="true"]',
        '.comments-comment-item__profile-link span',
        '.update-components-actor__name',
        'a[href*="/in/"] span[aria-hidden="true"]'
      ]);
      const headlineEl = card.querySelector('.comments-post-meta__headline, .comments-comment-item__headline, .update-components-actor__description');
      const linkEl = card.querySelector('a.comments-post-meta__profile-link, a[href*="/in/"]');
      const bodyEl = card.querySelector('.comments-comment-item__main-content, .feed-shared-main-content--comment, .update-components-text');

      const rawName = nameEl ? nameEl.innerText.trim() : "";
      const name = rawName.replace(/[\n\r]+/g, " ").replace(/\s+/g, " ").trim();
      if (!name || name.length < 2) return;

      const headline = headlineEl ? headlineEl.innerText.replace(/[\n\r]+/g, " ").trim() : "";
      const profileUrl = linkEl ? linkEl.href.split("?")[0] : "";
      const commentText = bodyEl ? Array.from(bodyEl.innerText.trim()).slice(0, 140).join("") : "";
      // Whose post this is cannot be told: not filed, rather than guessed.
      if (!postUrnFor(card) && !postAuthorFor(card)) return;

      const dedupeKey = engagerDedupeKey(profileUrl, name, headline, postUrnFor(card));
      const isNew = !knownEngagersSet.has(dedupeKey);
      knownEngagersSet.add(dedupeKey);

      leads.push({
        _key: dedupeKey,
        name,
        headline,
        company: headline.includes(" at ") ? headline.split(" at ")[1].split("|")[0].trim() : (headline.includes(" @ ") ? headline.split(" @ ")[1].split("|")[0].trim() : ""),
        profile_url: profileUrl,
        engagement_type: "Commented",
        notes: commentText ? `Commented: "${commentText}"` : "Commented on post",
        // Which post this happened on. Without it the studio stores an
        // engagement with no subject, which is why three complete attribution
        // surfaces have returned zero for this product's entire existence.
        post_urn: postUrnFor(card),
        post_author: postAuthorFor(card),
        _isNew: isNew
      });
    } catch (e) {}
  });

  // 1b. The rebuilt layout, where none of the selectors above match. Tried
  // only when they found nothing, so a page in the older layout is read once.
  let newLayoutCommenters = [];
  if (!commentCards.length) {
    newLayoutCommenters = readNewLayoutComments();
    newLayoutCommenters.forEach((c) => {
      // Each commenter carries its own list's post and author.
      const postUrn = c.postUrn;
      if (!postUrn && !c.postAuthor) return;
      const dedupeKey = engagerDedupeKey(c.profileUrl, c.name, c.headline, postUrn);
      const isNew = !knownEngagersSet.has(dedupeKey);
      knownEngagersSet.add(dedupeKey);
      leads.push({
        _key: dedupeKey,
        name: c.name,
        headline: c.headline,
        company: c.headline.includes(" at ") ? c.headline.split(" at ")[1].split("|")[0].trim() : "",
        profile_url: c.profileUrl,
        engagement_type: "Commented",
        notes: c.commentText ? `Commented: "${Array.from(c.commentText).slice(0, 140).join("")}"` : "Commented on post",
        post_urn: postUrn,
        post_author: c.postAuthor,
        _isNew: isNew
      });
    });
  }

  // 2. Capture Reactors from LinkedIn Reactions Modal Dialog
  // Scoped to the reactions surface itself. The bare `li` fallback that used to
  // sit at the end of this selector list is what turned every dialog on the site
  // into a source of leads.
  // The containers are the real ones LinkedIn uses. What changed is that each
  // must prove it is a reactions list before its contents count as engagers,
  // and that the item selector no longer falls through to a bare `li`, which is
  // what turned every dialog on the site into a source of leads.
  const reactorModals = Array.from(
    document.querySelectorAll('.artdeco-modal, div[role="dialog"], .social-details-reactors-tab')
  ).filter(looksLikeReactionsList);
  // The reactors tab sits inside the dialog, and both match, so each list was
  // read twice and every reactor counted twice. An item is read once.
  const reactorsRead = new Set();
  reactorModals.forEach(modal => {
    try {
      const reactorItems = modal.querySelectorAll(
        'li.social-details-reactors-tab__item, .reactions-menu__item'
      );
      reactorItems.forEach(item => {
        if (reactorsRead.has(item)) return;
        reactorsRead.add(item);
        const linkEl = item.querySelector('a[href*="/in/"]');
        if (!linkEl) return;

        const nameEl = firstNamedElement(item, [
          '.artdeco-entity-lockup__title',
          '.actor-name',
          '[data-anonymize="person-name"]',
          'a[href*="/in/"] span[aria-hidden="true"]'
        ]);
        const headlineEl = item.querySelector('.artdeco-entity-lockup__subtitle, .actor-description, .artdeco-entity-lockup__caption');

        const rawName = nameEl ? nameEl.innerText.trim() : "";
        const name = rawName.replace(/[\n\r]+/g, " ").replace(/\s+/g, " ").trim();
        if (!name || name.length < 2) return;

        const headline = headlineEl ? headlineEl.innerText.replace(/[\n\r]+/g, " ").trim() : "";
        const profileUrl = linkEl.href.split("?")[0];
        // A list whose post is unknown (opened from no card we can read, off
        // a permalink) is not filed, rather than filed under a guessed post.
        if (!postUrnFor(item) && !postAuthorFor(item)) return;

        const dedupeKey = engagerDedupeKey(profileUrl, name, headline, postUrnFor(item));
        const isNew = !knownEngagersSet.has(dedupeKey);
        knownEngagersSet.add(dedupeKey);

        leads.push({
          _key: dedupeKey,
          name,
          headline,
          company: headline.includes(" at ") ? headline.split(" at ")[1].split("|")[0].trim() : (headline.includes(" @ ") ? headline.split(" @ ")[1].split("|")[0].trim() : ""),
          profile_url: profileUrl,
          engagement_type: "Liked",
          notes: "Reacted to post on LinkedIn",
          post_urn: postUrnFor(item),
          post_author: postAuthorFor(item),
          _isNew: isNew
        });
      });
    } catch (e) {}
  });

  // Comment cards on screen but not one readable name among them is the
  // markup changing, not an empty thread.
  const commentersRead = leads.length - leadsBeforeComments;
  const newLayoutList = !commentCards.length && document.querySelector('[data-testid*="commentList"]');
  // What the reader saw is the comments and the reactors both: counting only
  // comments made a reactions list read on its own a run that saw nothing.
  if (commentCards.length || reactorModals.length || newLayoutList) {
    reportCapture("engagers", (commentCards.length || newLayoutCommenters.length) + reactorsRead.size, leads.length,
      commentCards.length > 0 && commentersRead === 0 ? ["commenter_name"] : []);
  }
  // The read is the DOM work above; what follows is sending.
  endRead("engagers");

  // Only POST if we have valid leads
  if (leads.length) {
    const newLeads = leads.filter(l => l._isNew);

    // A person with no profile URL cannot be opened, messaged, or told apart
    // from anyone else with the same display name. They are filtered out of
    // BOTH writes: filtering only the CRM call left them in the leads table via
    // the batch endpoint below, while the toast claimed they had been skipped.
    const identified = newLeads.filter(l => l.profile_url);
    const skipped = newLeads.length - identified.length;

    if (!identified.length) {
      if (skipped > 0) {
        noticeToPanel(
          `Inox Hydra: ${skipped} engager(s) had no profile link and were not saved.`,
          "warning"
        );
      }
      return;
    }

    // One write per person, to the one route that decides whether they are a
    // lead at all.
    //
    // There used to be two: a batch into /api/analytics/ingest and this one.
    // They matched people by different keys (profile URL there, name plus
    // headline here), so one person could become two leads and two namesakes
    // one. And only this route now carries the rule that a lead engaged with
    // the creator's own post, so the batch write would have stored every
    // stranger this one refuses.
    const writes = [];
    identified.forEach(lead => {
      let commentOnly = "";
      if (lead.notes && lead.notes.startsWith('Commented: "')) {
        commentOnly = lead.notes.replace(/^Commented:\s*"/, "").replace(/"$/, "");
      }
      writes.push(
        studioApi("/api/v1/crm/interactions/ingest", {
            full_name: lead.name || "Unknown",
            // Only a real profile URL identifies a person. This used to fall
            // back to a urn:li:person: minted from a hash of their display
            // name, which put a forged key into LinkedIn's own namespace.
            linkedin_urn: lead.profile_url,
            headline: lead.headline || "",
            company: lead.company || "",
            interaction_type: (lead.engagement_type || "COMMENT").toUpperCase(),
            // Only words the person wrote. A reaction sent lead.notes here,
            // "Reacted to post on LinkedIn", which was stored and shown as
            // their comment.
            comment_text: commentOnly || "",
            // Where this row was read from, so a bad selector can be found and
            // its rows removed rather than left to look like observations.
            capture_context: window.location.pathname,
            post_urn: lead.post_urn || null,
            // Whose post this is. The studio keeps the engager only when it is
            // the creator's.
            post_author: lead.post_author || null,
            // The post this happened on is not known yet. A fixed string here
            // ended up quoted in every generated message.
            post_topic: null
          })
      );
    });

    // Report what was actually stored. This used to run synchronously, outside
    // the promise chain, so with the studio not running every request failed
    // and the creator was still told their engagers had been captured.
    //
    // Three outcomes now, not two. A refusal because the post is someone
    // else's is the rule working, and is silent: the feed is full of other
    // people's posts, and announcing each one would turn the notice into noise
    // the creator learns to ignore.
    Promise.allSettled(writes).then(results => {
      const answers = results.map(r => (r.status === "fulfilled" ? r.value : null));
      // A person counts as seen on this post only once the studio has decided
      // about them: kept, or deliberately skipped by its rule. Marking them
      // seen before the write meant that everyone read while the studio was
      // down or restarting was skipped on every later read of the page. They
      // are offered again after 30 s, not on the next read, so a studio that
      // is down is not asked every 4 s.
      // A capture kept for a busy studio is decided: it will be sent again by
      // the worker, so offering the person once more would queue them twice.
      const decided = ["success", "skipped", "kept"];
      const undecided = identified
        .filter((lead, i) => !answers[i] || decided.indexOf(answers[i].status) < 0)
        .map((lead) => lead._key);
      if (undecided.length) {
        setTimeout(() => undecided.forEach((key) => knownEngagersSet.delete(key)), 30000);
      }
      const stored = answers.filter(a => a && a.status === "success").length;
      const kept = answers.filter(a => a && a.status === "kept").length;
      const waiting = answers.reduce((most, a) => (a && a.status === "kept" ? Math.max(most, a.waiting || 0) : most), 0);
      // Not running, or running and refusing this unpaired browser: either
      // way nothing was saved, which is what the notice below says.
      const unreachable = answers.filter(a => a === null ||
        (a.status === "refused" && (a.httpStatus === 401 || a.httpStatus === 403))).length;
      // Every refusal the studio asked to be shown, in its own words. This
      // used to look for the word "Setup" in a reason the studio no longer
      // worded that way, so the refusal a creator meets most, "import your
      // posts first", fired no notice at all.
      const toShow = answers.find(a => a && a.status === "refused" && a.show && a.message);

      // Stored engagers are confirmed on the action badge and in the side
      // panel, from the worker's own record of each relay (decision D3), so
      // nothing is drawn into LinkedIn's page for a capture that worked.
      // What the creator must act on, or must know was not saved, is said in
      // the side panel (noticeToPanel).
      if (stored > 0) {
        if (skipped > 0) {
          noticeToPanel(`Inox Hydra: ${skipped} engager(s) had no profile link and were not saved.`, "warning");
        }
      } else if (kept > 0) {
        noticeToPanel(
          `Inox Hydra: your studio was busy, so ${kept} capture(s) are kept and will be sent again. ` +
          `${waiting} waiting in all.`,
          "waiting"
        );
      } else if (toShow && !shownRefusals[toShow.reason || toShow.message]) {
        shownRefusals[toShow.reason || toShow.message] = true;
        noticeToPanel("Inox Hydra: " + toShow.message, "warning");
      } else if (unreachable === answers.length) {
        noticeToPanel("Inox Hydra: could not reach your studio, so nothing was saved.", "warning");
      }
    });
  }
}

// Observe DOM mutations for opened comments sections and reaction modals
const commentObserver = new MutationObserver(() => {
  scheduleEngagerRead();
});
commentObserver.observe(document.body, { childList: true, subtree: true });

