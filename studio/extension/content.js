// -------------------------------------------------------------
// LinkedIn Studio Bridge - Content Script
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
 */
function studioApi(path, body, method) {
  return new Promise((resolve) => {
    try {
      chrome.runtime.sendMessage(
        { action: "STUDIO_API", path: path, method: method || "POST", body: body },
        (response) => {
          if (chrome.runtime.lastError || !response || response.status !== "success") {
            resolve(null);
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
// LinkedIn is a single page application. A listener registered inside a URL
// guard that is evaluated once, at injection time, never fires for a creator who
// navigates to analytics from the feed, which is how everyone reaches it. Watch
// the path instead.
let lastAnalyticsPath = null;
let analyticsReadTimer = null;

function maybeExtractAnalytics(force) {
  const path = window.location.pathname;
  if (!path.includes("/analytics")) {
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

// popstate covers back and forward only. LinkedIn navigates with pushState,
// which emits no event at all, so wrap the two history methods and announce
// them ourselves. Without this the extractor never runs for anyone who reaches
// analytics by clicking through the app rather than by loading the URL cold.
(function announceSpaNavigation() {
  const fire = () => window.dispatchEvent(new Event("studio:locationchange"));
  for (const method of ["pushState", "replaceState"]) {
    const original = history[method];
    if (typeof original !== "function" || original.__studioWrapped) continue;
    const wrapped = function () {
      const result = original.apply(this, arguments);
      fire();
      return result;
    };
    wrapped.__studioWrapped = true;
    history[method] = wrapped;
  }
})();

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
 */
function parseMetricValue(raw) {
  if (!raw) return null;
  const text = String(raw).trim();

  // A comma before one or two digits is a decimal comma, not a separator:
  // "1,2K" is 1.2K in de-DE and fr-FR, and stripping the comma made it 12000.
  // The metric classification in this file matches English words, so a page in
  // another locale cannot be read correctly regardless. Refuse rather than
  // return a number that is wrong by a factor of ten.
  if (/\d,\d{1,2}(\s*[KMB])?$/i.test(text)) return null;

  const normalized = text.replace(/,/g, "");
  const match = normalized.match(/^([0-9]*\.?[0-9]+)\s*([KMB]?)$/i);
  if (!match) return null;

  const base = parseFloat(match[1]);
  if (!isFinite(base)) return null;

  const suffix = (match[2] || "").toUpperCase();
  const multiplier = suffix === "K" ? 1e3 : suffix === "M" ? 1e6 : suffix === "B" ? 1e9 : 1;
  return {
    value: Math.round(base * multiplier),
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
 */
function detectAnalyticsPeriod() {
  const candidates = document.querySelectorAll(
    '.artdeco-dropdown__trigger, [data-test-analytics-time-range], .analytics-time-range-selector, button[aria-label*="time range" i]'
  );
  for (const el of candidates) {
    const t = (el.innerText || "").toLowerCase();
    if (/past 24 hours|last 24 hours|past day/.test(t)) return "1d";
    if (/past 7 days|last 7 days/.test(t)) return "7d";
    if (/past 14 days|last 14 days/.test(t)) return "14d";
    if (/past 28 days|last 28 days|past 30 days/.test(t)) return "28d";
    if (/past 90 days|last 90 days/.test(t)) return "90d";
    if (/past year|last 365/.test(t)) return "365d";
  }
  return null;
}

function extractAndSyncAnalytics() {
  try {
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

    if (impressions === null && followers === null) return;

    // One row carries one precision, so report the least precise reading that
    // actually contributed a stored value.
    const contributing = Object.values(seen);
    const precision = contributing.includes("rounded") ? "rounded" : "exact";

    const period = detectAnalyticsPeriod();
    const today = new Date().toISOString().slice(0, 10);

    studioApi("/api/analytics/ingest", {
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
      .then(result => {
        if (result && result.status === "window_mismatch") {
          showInPageToast(
            "LinkedIn Studio: these figures cover " + (period || "an unknown period") +
            ", so they were not saved as today's numbers. Set the range to 24 hours to sync a daily figure.",
            "warning"
          );
          return;
        }
        showInPageToast("LinkedIn Studio: creator analytics synced to your local studio.", "success");
      })
      .catch(() => {});
  } catch (e) {
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
 *   /feed/update/urn:li:activity:7504139397143883776/
 *   /feed/update/urn:li:share:7504139397143883776/
 *   /posts/someone_slug-activity-7504139397143883776-AbCd
 */
function extractActivityUrn(text) {
  if (!text) return null;
  const direct = text.match(/urn:li:(?:activity|share|ugcPost):\d+/);
  if (direct) return direct[0];
  const slug = text.match(/-activity-(\d{6,})/);
  if (slug) return `urn:li:activity:${slug[1]}`;
  return null;
}

/**
 * The URN of the post a given element belongs to.
 *
 * On a permalink the URL is authoritative and needs no markup at all. In the
 * feed, where several posts share a page, the containing update card carries
 * the URN in a data attribute. Reading the URL first means the common case
 * never depends on a class name LinkedIn can rename.
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
  return null;
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

  studioApi("/api/v1/posts/bind-urn", { activity_urn: urn, post_text: body })
    .then(result => {
      if (result && result.status === "bound") {
        showInPageToast(
          "LinkedIn Studio: this post is now linked to your draft. Engagement on it will be attributed.",
          "success"
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
    path.startsWith("/in/") ||
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

function observeAndCaptureEngagers() {
  if (!isPostEngagementSurface()) return;

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
      const commentText = bodyEl ? bodyEl.innerText.trim().slice(0, 140) : "";

      const dedupeKey = engagerDedupeKey(profileUrl, name, headline, postUrnFor(card));
      const isNew = !knownEngagersSet.has(dedupeKey);
      knownEngagersSet.add(dedupeKey);

      leads.push({
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
        _isNew: isNew
      });
    } catch (e) {}
  });

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
  reactorModals.forEach(modal => {
    try {
      const reactorItems = modal.querySelectorAll(
        'li.social-details-reactors-tab__item, .reactions-menu__item'
      );
      reactorItems.forEach(item => {
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

        const dedupeKey = engagerDedupeKey(profileUrl, name, headline, postUrnFor(item));
        const isNew = !knownEngagersSet.has(dedupeKey);
        knownEngagersSet.add(dedupeKey);

        leads.push({
          name,
          headline,
          company: headline.includes(" at ") ? headline.split(" at ")[1].split("|")[0].trim() : (headline.includes(" @ ") ? headline.split(" @ ")[1].split("|")[0].trim() : ""),
          profile_url: profileUrl,
          engagement_type: "Liked",
          notes: "Reacted to post on LinkedIn",
          post_urn: postUrnFor(item),
          _isNew: isNew
        });
      });
    } catch (e) {}
  });

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
        showInPageToast(
          `LinkedIn Studio: ${skipped} engager(s) had no profile link and were not saved.`,
          "warning"
        );
      }
      return;
    }

    const writes = [];

    // 1. Batch ingest into the leads store.
    writes.push(
      studioApi("/api/analytics/ingest", { leads: identified }).then(r => r !== null)
    );

    // 2. Per-person CRM ingest, which carries the interaction and its context.
    identified.forEach(lead => {
      let commentOnly = "";
      if (lead.notes && lead.notes.startsWith('Commented: "')) {
        commentOnly = lead.notes.replace(/^Commented:\s*"/, "").replace(/"$/, "");
      }
      writes.push(
        studioApi("/api/v1/crm/interactions/ingest", {
            full_name: lead.name,
            // Only a real profile URL identifies a person. This used to fall
            // back to a urn:li:person: minted from a hash of their display
            // name, which put a forged key into LinkedIn's own namespace.
            linkedin_urn: lead.profile_url,
            headline: lead.headline,
            company: lead.company,
            interaction_type: (lead.engagement_type || "COMMENT").toUpperCase(),
            comment_text: commentOnly || lead.notes || "",
            // Where this row was read from, so a bad selector can be found and
            // its rows removed rather than left to look like observations.
            capture_context: window.location.pathname,
            post_urn: lead.post_urn || null,
            // The post this happened on is not known yet. A fixed string here
            // ended up quoted in every generated message.
            post_topic: null
          }).then(r => r !== null)
      );
    });

    // Report what was actually stored. This used to run synchronously, outside
    // the promise chain, so with the studio not running every request failed
    // and the creator was still told their engagers had been captured.
    Promise.allSettled(writes).then(results => {
      const ok = results.filter(r => r.status === "fulfilled" && r.value).length;
      if (ok === 0) {
        showInPageToast(
          "LinkedIn Studio: could not reach your studio, so nothing was saved.",
          "warning"
        );
        return;
      }
      const note = skipped > 0 ? ` (${skipped} had no profile link)` : "";
      showInPageToast(
        `LinkedIn Studio: ${identified.length} engager(s) captured from this post${note}.`,
        "success"
      );
    });
  }
}

// Observe DOM mutations for opened comments sections and reaction modals
const commentObserver = new MutationObserver(() => {
  observeAndCaptureEngagers();
});
commentObserver.observe(document.body, { childList: true, subtree: true });

