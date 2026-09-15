// -------------------------------------------------------------
// LinkedIn Studio Bridge - Content Script
// Interacts with LinkedIn DOM to auto-inject formatted posts
// -------------------------------------------------------------

console.log("[LinkedIn Studio Bridge] Content script active on linkedin.com");

// Listen for messages from Side Panel or Background
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "INJECT_POST") {
    injectIntoLinkedInComposer(message.content)
      .then(success => sendResponse({ status: success ? "success" : "failed" }))
      .catch(err => sendResponse({ status: "error", error: err.message }));
    return true; // Keep channel open for async response
  }
});

async function injectIntoLinkedInComposer(text) {
  // 1. Check if composer modal is already open
  let editor = document.querySelector('div.ql-editor[contenteditable="true"]') ||
               document.querySelector('div[role="textbox"][contenteditable="true"]') ||
               document.querySelector('.share-creation-state__text-editor div[contenteditable="true"]');

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
        editor = document.querySelector('div.ql-editor[contenteditable="true"]') ||
                 document.querySelector('div[role="textbox"][contenteditable="true"]');
        if (editor) break;
      }
    }
  }

  if (!editor) {
    showInPageToast("⚠️ Please click 'Start a post' on LinkedIn first!", "warning");
    return false;
  }

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

  showInPageToast("✅ LinkedIn Studio: Formatted post injected into composer!", "success");
  return true;
}

function showInPageToast(message, type = "success") {
  const existing = document.getElementById("studio-bridge-inpage-toast");
  if (existing) existing.remove();

  const toast = document.createElement("div");
  toast.id = "studio-bridge-inpage-toast";
  toast.className = `studio-inpage-toast ${type}`;
  toast.innerHTML = `
    <div class="studio-toast-icon">LS</div>
    <div class="studio-toast-msg">${message}</div>
  `;

  document.body.appendChild(toast);
  setTimeout(() => {
    toast.classList.add("studio-toast-fade");
    setTimeout(() => toast.remove(), 400);
  }, 3500);
}

// -------------------------------------------------------------
// Passive Creator Analytics Sync (100% Safe Local Extraction)
// -------------------------------------------------------------
if (window.location.href.includes("/analytics/creator") || window.location.href.includes("/analytics/")) {
  window.addEventListener("load", () => {
    setTimeout(extractAndSyncAnalytics, 2000);
  });
}

function extractAndSyncAnalytics() {
  try {
    const metricElements = document.querySelectorAll('[data-test-metric-value], .member-analytics-addon__metric-value, .creator-analytics-metric__value, .analytics-metric-summary');
    let impressions = null;
    let engagements = null;
    let followers = null;

    metricElements.forEach(el => {
      const parent = el.closest('[data-test-metric-card], .creator-analytics-metric') || el.parentElement;
      const text = parent ? parent.innerText.toLowerCase() : "";
      const val = parseInt(el.innerText.replace(/,/g, "").trim(), 10);
      if (!isNaN(val)) {
        if (text.includes("impression")) impressions = val;
        else if (text.includes("engagement") || text.includes("reaction")) engagements = val;
        else if (text.includes("follower")) followers = val;
      }
    });

    if (impressions !== null || followers !== null) {
      const today = new Date().toISOString().slice(0, 10);
      fetch("http://127.0.0.1:8000/api/analytics/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          series: [{
            date: today,
            impressions: impressions || 0,
            reactions: engagements || 0,
            followers: followers || null
          }]
        })
      })
      .then(r => r.json())
      .then(() => {
        showInPageToast("⚡ LinkedIn Studio: Live Creator Analytics synced to local studio!", "success");
      })
      .catch(() => {});
    }
  } catch (e) {
    console.debug("[Studio Bridge] Passive analytics parse:", e);
  }
}

// -------------------------------------------------------------
// Auto-Capture Engagers (Commenters & Reactors) into Local CRM
// -------------------------------------------------------------
let lastCommentScrapeTime = 0;
const knownEngagersSet = new Set();

function observeAndCaptureEngagers() {
  const now = Date.now();
  if (now - lastCommentScrapeTime < 4000) return; // Debounce 4s
  lastCommentScrapeTime = now;

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
  commentCards.forEach(card => {
    try {
      const nameEl = card.querySelector('.comments-post-meta__name-text, [data-anonymize="person-name"], .comments-comment-item__profile-link span, .update-components-actor__name, [aria-hidden="true"]');
      const headlineEl = card.querySelector('.comments-post-meta__headline, .comments-comment-item__headline, .update-components-actor__description');
      const linkEl = card.querySelector('a.comments-post-meta__profile-link, a[href*="/in/"]');
      const bodyEl = card.querySelector('.comments-comment-item__main-content, .feed-shared-main-content--comment, .update-components-text');

      const rawName = nameEl ? nameEl.innerText.trim() : "";
      const name = rawName.replace(/[\n\r]+/g, " ").replace(/\s+/g, " ").trim();
      if (!name || name.length < 2) return;

      const headline = headlineEl ? headlineEl.innerText.replace(/[\n\r]+/g, " ").trim() : "";
      const profileUrl = linkEl ? linkEl.href.split("?")[0] : "";
      const commentText = bodyEl ? bodyEl.innerText.trim().slice(0, 140) : "";

      const dedupeKey = profileUrl || `${name}_${headline}`;
      const isNew = !knownEngagersSet.has(dedupeKey);
      knownEngagersSet.add(dedupeKey);

      leads.push({
        name,
        headline,
        company: headline.includes(" at ") ? headline.split(" at ")[1].split("|")[0].trim() : (headline.includes(" @ ") ? headline.split(" @ ")[1].split("|")[0].trim() : ""),
        profile_url: profileUrl,
        engagement_type: "Commented",
        notes: commentText ? `Commented: "${commentText}"` : "Commented on post",
        _isNew: isNew
      });
    } catch (e) {}
  });

  // 2. Capture Reactors from LinkedIn Reactions Modal Dialog
  const reactorModals = document.querySelectorAll('.artdeco-modal, div[role="dialog"]');
  reactorModals.forEach(modal => {
    try {
      const reactorItems = modal.querySelectorAll('li.social-details-reactors-tab__item, .reactions-menu__item, li');
      reactorItems.forEach(item => {
        const linkEl = item.querySelector('a[href*="/in/"]');
        if (!linkEl) return;

        const nameEl = item.querySelector('.artdeco-entity-lockup__title, .actor-name, a[href*="/in/"] span[aria-hidden="true"], [data-anonymize="person-name"]');
        const headlineEl = item.querySelector('.artdeco-entity-lockup__subtitle, .actor-description, .artdeco-entity-lockup__caption');

        const rawName = nameEl ? nameEl.innerText.trim() : "";
        const name = rawName.replace(/[\n\r]+/g, " ").replace(/\s+/g, " ").trim();
        if (!name || name.length < 2) return;

        const headline = headlineEl ? headlineEl.innerText.replace(/[\n\r]+/g, " ").trim() : "";
        const profileUrl = linkEl.href.split("?")[0];

        const dedupeKey = profileUrl || `${name}_${headline}`;
        const isNew = !knownEngagersSet.has(dedupeKey);
        knownEngagersSet.add(dedupeKey);

        leads.push({
          name,
          headline,
          company: headline.includes(" at ") ? headline.split(" at ")[1].split("|")[0].trim() : (headline.includes(" @ ") ? headline.split(" @ ")[1].split("|")[0].trim() : ""),
          profile_url: profileUrl,
          engagement_type: "Liked",
          notes: "Reacted to post on LinkedIn",
          _isNew: isNew
        });
      });
    } catch (e) {}
  });

  // Only POST if we have valid leads
  if (leads.length) {
    const newCount = leads.filter(l => l._isNew).length;
    fetch("http://127.0.0.1:8000/api/analytics/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ leads })
    })
    .then(r => r.json())
    .then(() => {
      if (newCount > 0) {
        showInPageToast(`⚡ LinkedIn Studio CRM: Ingested ${newCount} warm engager(s)!`, "success");
      }
    })
    .catch(() => {});
  }
}

// Observe DOM mutations for opened comments sections and reaction modals
const commentObserver = new MutationObserver(() => {
  observeAndCaptureEngagers();
});
commentObserver.observe(document.body, { childList: true, subtree: true });

