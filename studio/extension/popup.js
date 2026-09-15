const LOCAL_API_URL = "http://127.0.0.1:8000/api/auth/cookies";
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

    try {
      const li_at = await getCookie("li_at");
      const jsessionid = await getCookie("JSESSIONID");

      if (!li_at || !jsessionid) {
        statusEl.innerText = "⚠️ Please log into LinkedIn in Chrome first!";
        document.getElementById("session-status").innerText = "Not Logged In";
        document.getElementById("session-status").style.color = "#f59e0b";
        return;
      }

      statusEl.innerText = "Pushing tokens to local Studio...";
      const response = await fetch(LOCAL_API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          li_at: li_at.value,
          JSESSIONID: jsessionid.value
        })
      });

      if (response.ok) {
        statusEl.innerText = "✅ Session synced to Local Studio!";
        document.getElementById("bridge-status").innerText = "Connected & Active";
        document.getElementById("session-status").innerText = "Authenticated";
        document.getElementById("session-status").style.color = "#34d399";
      } else {
        statusEl.innerText = "❌ Studio server not reachable on port 8000.";
      }
    } catch (err) {
      console.error(err);
      statusEl.innerText = "Error: Is local studio server running?";
    }
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
