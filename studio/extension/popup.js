const STUDIO_URL = "http://127.0.0.1:8000";

document.addEventListener("DOMContentLoaded", async () => {
  checkServerAndSession();

  document.getElementById("btn-open-studio").addEventListener("click", () => {
    chrome.tabs.create({ url: STUDIO_URL });
  });

  // Open Side Panel
  document.getElementById("btn-open-sidepanel").addEventListener("click", async () => {
    try {
      const window = await chrome.windows.getCurrent();
      await chrome.sidePanel.open({ windowId: window.id });
      window.close(); // close popup once side panel opens
    } catch (err) {
      console.error(err);
      document.getElementById("status-text").innerText = "Side panel opened in active tab!";
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

  const li_at = await getCookie("li_at");
  if (li_at) {
    sessionEl.innerText = "Active";
    sessionEl.style.color = "#34d399";
  } else {
    sessionEl.innerText = "Log into LinkedIn";
    sessionEl.style.color = "#94a3b8";
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
