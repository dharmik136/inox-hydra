// -------------------------------------------------------------
// LinkedIn Studio Bridge - Background Service Worker (Manifest V3)
// -------------------------------------------------------------
const LOCAL_API_AUTH = "http://127.0.0.1:8000/api/auth/cookies";
const LOCAL_INGEST_URL = "http://127.0.0.1:8000/api/analytics/ingest";

// Configure alarms on installation
chrome.runtime.onInstalled.addListener(() => {
  console.log("[Studio Bridge v2.5] Service worker installed.");
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

// Intercept LinkedIn Voyager Creator Analytics responses
chrome.webRequest.onCompleted.addListener(
  (details) => {
    if (details.url.includes("voyager/api/identity/dash/creatorAnalytics") || 
        (details.url.includes("voyager/api/graphql") && details.url.includes("creator"))) {
      console.log("[Studio Bridge] Intercepted Creator Analytics response:", details.url);
      syncActiveSessionToStudio();
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
});
