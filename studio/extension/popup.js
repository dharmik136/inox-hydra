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

  try {
    const res = await fetch("http://127.0.0.1:8000/api/analytics/kpis?range=7d");
    if (res.ok) {
      serverEl.innerText = "Online";
      serverEl.style.color = "#34d399";
      bridgeBadge.innerText = "Ready";
    }

    const leadsRes = await fetch("http://127.0.0.1:8000/api/leads");
    if (leadsRes.ok) {
      const leadsJson = await leadsRes.json();
      if (crmEl) {
        crmEl.innerText = `${leadsJson.leads ? leadsJson.leads.length : 0} Active`;
        crmEl.style.color = "#34d399";
      }
    }
  } catch {
    serverEl.innerText = "Offline";
    serverEl.style.color = "#ef4444";
    bridgeBadge.innerText = "Server Offline";
    if (crmEl) {
      crmEl.innerText = "Offline";
      crmEl.style.color = "#94a3b8";
    }
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
