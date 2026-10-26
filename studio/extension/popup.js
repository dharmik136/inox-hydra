const STUDIO_URL = "http://127.0.0.1:8000";

const NETWORK_READING_NOTE_OFF =
  "Off. The bridge reads only what is on the LinkedIn pages you open. " +
  "Switched on, it also copies the figures LinkedIn's own app has already downloaded " +
  "for those pages, which are exact rather than rounded, and notes which of LinkedIn's data " +
  "requests they made. It does this by wrapping the page's fetch function, which LinkedIn " +
  "may treat as automation. It never sends a request of its own.";
const NETWORK_READING_NOTE_ON =
  "On. The bridge copies the figures LinkedIn's own app has already downloaded, by wrapping " +
  "the page's fetch function, which LinkedIn may treat as automation. It applies to LinkedIn " +
  "pages you open or reload from now; switching it off stops the copying at once, and a tab " +
  "already open keeps the wrapper until you reload it.";

function paintNetworkReading(enabled) {
  const box = document.getElementById("network-reading");
  const note = document.getElementById("network-reading-note");
  if (box) box.checked = enabled;
  if (note) note.innerText = enabled ? NETWORK_READING_NOTE_ON : NETWORK_READING_NOTE_OFF;
}

document.addEventListener("DOMContentLoaded", async () => {
  checkServerAndSession();
  // The last capture and the last drift noticed, from the worker's storage.
  try {
    followStorage("popup-last-capture", "popup-drift-notice");
  } catch (err) {}

  // Off unless set. background.js registers or removes the interceptor when
  // this value changes, and refuses its captures while it is off.
  chrome.storage.local.get("networkReading", (items) => {
    paintNetworkReading(!chrome.runtime.lastError && !!items && items.networkReading === true);
  });
  document.getElementById("network-reading").addEventListener("change", (event) => {
    const enabled = !!event.target.checked;
    chrome.storage.local.set({ networkReading: enabled }, () => paintNetworkReading(enabled));
  });

  document.getElementById("btn-open-studio").addEventListener("click", () => {
    chrome.tabs.create({ url: STUDIO_URL });
  });

  // Open Side Panel
  //
  // The browser window is `win`: naming it `window` hid the popup's own
  // window, so closing the popup threw, and the catch then reported the side
  // panel as opened, which it also did when the side panel failed to open.
  document.getElementById("btn-open-sidepanel").addEventListener("click", async () => {
    let opened = false;
    try {
      const win = await chrome.windows.getCurrent();
      await chrome.sidePanel.open({ windowId: win.id });
      opened = true;
      window.close(); // close popup once side panel opens
    } catch (err) {
      if (!opened) {
        document.getElementById("status-text").innerText =
          "Could not open the side panel: " + ((err && err.message) || "the browser refused.");
      }
    }
  });

  // Sync Session Cookies
  document.getElementById("btn-sync").addEventListener("click", async () => {
    const statusEl = document.getElementById("status-text");
    statusEl.innerText = "Reading session cookies...";

    // Through the service worker, which carries the studio token. This used
    // to be a bare fetch from the popup, which carries none, so every press
    // was refused with a 401 and reported as the server being unreachable.
    // It is now the only way the session reaches the studio, so the worker's
    // own words are shown rather than a guess at what went wrong.
    chrome.runtime.sendMessage({ action: "SYNC_NOW" }, (result) => {
      const sessionEl = document.getElementById("session-status");
      if (chrome.runtime.lastError || !result) {
        statusEl.innerText = "The extension could not run the sync. Reload it and try again.";
        return;
      }
      statusEl.innerText = result.message || result.status;
      if (result.status === "synced") {
        sessionEl.innerText = "Saved to the studio";
        sessionEl.style.color = "#34d399";
      } else if (result.status === "not_signed_in") {
        sessionEl.innerText = "Not signed in";
        sessionEl.style.color = "#f59e0b";
      }
    });
  });
});

async function checkServerAndSession() {
  const serverEl = document.getElementById("server-status");
  const sessionEl = document.getElementById("session-status");
  const bridgeBadge = document.getElementById("bridge-status");
  const crmEl = document.getElementById("crm-leads-status");

  // Through the worker, which carries the studio token. Three outcomes, and
  // each says what it is: the studio answered, the studio is not running, or
  // the studio refused this browser because it was never paired.
  const state = await panelApi("/api/v1/onboarding/state");
  const paint = (el, text, color) => { if (el) { el.innerText = text; el.style.color = color; } };

  if (state.ok) {
    paint(serverEl, "Online", "#34d399");
    bridgeBadge.innerText = state.data.identity ? "Ready" : "Finish Setup in the studio";
    const leads = await panelApi("/api/leads");
    paint(crmEl, leads.ok ? `${(leads.data.leads || []).length} Active` : "Unavailable",
          leads.ok ? "#34d399" : "#94a3b8");
  } else if (state.httpStatus === 401 || state.httpStatus === 403) {
    paint(serverEl, "Not paired", "#f59e0b");
    bridgeBadge.innerText = "Open 127.0.0.1:8000 in this browser once";
    paint(crmEl, "Not paired", "#94a3b8");
  } else {
    paint(serverEl, "Offline", "#ef4444");
    bridgeBadge.innerText = "Studio not running";
    paint(crmEl, "Offline", "#94a3b8");
  }

  // Whether the studio holds a session, which is what the live send needs,
  // from the studio itself. The browser's own li_at cookie only says this
  // browser is signed in to LinkedIn; it was shown as "Active" while the
  // studio held nothing and the live send refused.
  const li_at = await getCookie("li_at");
  const session = state.ok ? state.data.session : null;
  if (session && session.stored) {
    paint(sessionEl, "Saved in the studio" + (session.saved_at ? " " + String(session.saved_at).slice(0, 10) : ""), "#34d399");
  } else if (session) {
    paint(sessionEl, li_at ? "Not saved in the studio. Press Sync." : "Not saved in the studio. Sign in to LinkedIn.", "#f59e0b");
  } else {
    paint(sessionEl, li_at ? "Signed in to LinkedIn" : "Log into LinkedIn", "#94a3b8");
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
 * A GET against the studio, made by the service worker so it carries the
 * studio token. Resolves to { ok, httpStatus, data }; httpStatus 0 means the
 * studio could not be reached at all.
 */
function panelApi(path) {
  return new Promise((resolve) => {
    try {
      chrome.runtime.sendMessage({ action: "PANEL_API", path }, (result) => {
        if (chrome.runtime.lastError || !result) {
          resolve({ ok: false, httpStatus: 0, data: {} });
          return;
        }
        resolve({ ok: !!result.ok, httpStatus: result.httpStatus || 0, data: result.data || {} });
      });
    } catch (err) {
      resolve({ ok: false, httpStatus: 0, data: {} });
    }
  });
}

// -------------------------------------------------------------
// What the worker last did, from the extension's own storage
// -------------------------------------------------------------
// The worker writes the last capture to chrome.storage.local and the drift
// notice to chrome.storage.session the moment each happens, so these lines
// are drawn from storage and follow storage.onChanged: no studio call, and
// nothing drawn into LinkedIn's page (decision D3). A capture names the kind
// of thing and when, never the person, and "captured" is said only of what
// the studio stored. The popup closes when it loses focus, so it carries the
// last capture and the drift notice only; counts belong to the side panel
// and the badge, which stay in view.
const CAPTURE_WORDS = {
  "/api/v1/crm/interactions/ingest": "an engager on your post",
  "/api/v1/self/posts/ingest": "your posts",
  "/api/v1/self/posts/analytics": "a post's analytics figures",
  "/api/v1/self/outbound/ingest": "your comments and reactions",
  "/api/v1/identity/observe": "your profile",
  "/api/v1/posts/bind-urn": "a post linked to your draft",
  "/api/v1/bridge/voyager-ingest": "a network reading",
  "/api/analytics/ingest": "creator analytics",
  "/api/analytics/page-figures": "figures from your own analytics pages"
};

function agoWords(iso) {
  const then = Date.parse(iso || "");
  if (!then) return "";
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 10) return "just now";
  if (seconds < 60) return seconds + " s ago";
  if (seconds < 3600) return Math.round(seconds / 60) + " min ago";
  const when = new Date(then);
  if (when.toDateString() === new Date().toDateString()) {
    return "at " + when.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  return "on " + when.toLocaleDateString();
}

function captureLine(last) {
  if (!last || !last.path) return "No capture yet.";
  const what = CAPTURE_WORDS[last.path] || "a capture";
  const first = what.charAt(0).toUpperCase() + what.slice(1);
  const when = agoWords(last.at);
  if (last.kept) return first + " was kept for the studio " + when + ", and is sent again on its own.";
  if (!last.ok) return "The studio refused " + what + " " + when + ". The side panel's Health tab says why.";
  if (last.stored) return "Captured " + what + " " + when + ".";
  return "Read LinkedIn " + when + "; nothing new to keep.";
}

function driftLine(drift) {
  if (!drift || !Array.isArray(drift.fields) || !drift.fields.length) return "";
  return "LinkedIn's " + (drift.page_kind || "page") + " page: cannot read " +
    drift.fields.join(", ").replace(/_/g, " ") + ", noticed " + agoWords(drift.at) +
    ". See Health in the studio.";
}

function readArea(area, keys) {
  return new Promise((resolve) => {
    if (!area) {
      resolve({});
      return;
    }
    try {
      area.get(keys, (items) => resolve(chrome.runtime.lastError ? {} : (items || {})));
    } catch (err) {
      resolve({});
    }
  });
}

// Either area, or null when this page has no storage API (a test page, or
// an extension being reloaded). A status line must never stop the popup.
function storageArea(name) {
  try {
    return (chrome.storage && chrome.storage[name]) || null;
  } catch (err) {
    return null;
  }
}

function paintFromStorage(captureId, driftId) {
  Promise.all([
    readArea(storageArea("local"), ["lastCapture"]),
    readArea(storageArea("session"), ["lastDrift"])
  ]).then(([found, noticed]) => {
    const capture = document.getElementById(captureId);
    if (capture) capture.textContent = captureLine(found.lastCapture);
    const drift = document.getElementById(driftId);
    if (drift) {
      const line = driftLine(noticed.lastDrift);
      drift.textContent = line;
      drift.hidden = !line;
    }
  });
}

function followStorage(captureId, driftId) {
  paintFromStorage(captureId, driftId);
  try {
    chrome.storage.onChanged.addListener((changes, area) => {
      if ((area === "local" && changes.lastCapture) || (area === "session" && changes.lastDrift)) {
        paintFromStorage(captureId, driftId);
      }
    });
  } catch (err) {}
}
