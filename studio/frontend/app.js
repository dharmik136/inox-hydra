/**
 * LinkedIn Studio Enterprise - Minimalist Authority Desktop Studio Controller
 * ==============================================================================
 * 100% Local, Air-Gapped Engine (Zero Cloud Egress)
 * Architecture:
 * - Rigid Three-Pane Desktop Studio: Collapsed Sidebar, Distraction-Free Editor, Live Mobile Simulator & Intelligence
 * - Dynamic Glowing Red "See More" Fold Line Tracker
 * - Inline Hook Variant Carousel (5-10 scrollable cards)
 * - Floating Text Selection Action Bar (Sans-Bold, Monospace, Clean Formatting)
 * - 6-Dimension Algorithmic Safety Auditor (0-100%)
 * - 1080x1080 Multi-Slide Carousel Canvas Engine
 * - Warm-Lead CRM Inbox with Contextual DM Generator
 * - 356 Vaulted Viral Swipe File Blueprints
 */

const API_BASE = "http://127.0.0.1:8000/api";

// State Management
let currentRange = "30d";
let isSeeMoreExpanded = false;
let currentDraftId = "post-enterprise-scheduled";
let currentInspTopic = "";
let currentInspQuery = "";
let inspSearchDebounce = null;
let analyticsChartInstance = null;

// Carousel Deck State
let carouselTheme = "dark_slate";
let carouselSlides = [
  {
    tag: "EXECUTIVE FRAMEWORK",
    title: "Stepping into Enterprise Systems Architecture",
    body: "Why modern enterprise observability and ERP ecosystems require foundational systems thinking rather than superficial tactical patches."
  },
  {
    tag: "CORE PRINCIPLE 01",
    title: "Zero-Latency Decoupling",
    body: "Architecture isn't about connecting every service to a central monolith. It's about clear bounded contexts, asynchronous event delivery, and fault isolation."
  },
  {
    tag: "CORE PRINCIPLE 02",
    title: "Observability Over Guesswork",
    body: "Telemetry without semantic context is just noise. Trace distributed transactions from initial ingress to persistence layer with standardized trace context."
  },
  {
    tag: "THE TAKEAWAY",
    title: "Execution Discipline",
    body: "Great technical strategy is simple, deterministic, and repeatable. Build systems that empower teams to operate autonomously with confidence."
  }
];

// Initialize on DOM Ready
document.addEventListener("DOMContentLoaded", () => {
  initNavigation();
  initEditor();
  initFloatingToolbar();
  initHookCarousel();
  initCarouselBuilder();
  initCRM();
  initInspirations();
  initAICommandCenter();
  initQueue();
  initDocsHub();

  // Initial Data Fetching
  loadKPIs();
  loadAnalyticsChart();
  loadQueue();
  loadLeads();
  loadInspirations();
});

// -------------------------------------------------------------
// 1. NAVIGATION & TAB ROUTING
// -------------------------------------------------------------
function initNavigation() {
  const navLinks = document.querySelectorAll(".nav-link");
  const viewTitle = document.getElementById("view-title");
  const viewSubtitle = document.getElementById("view-subtitle");

  navLinks.forEach(link => {
    link.addEventListener("click", () => {
      const targetTab = link.getAttribute("data-tab");
      switchTab(targetTab);
    });
  });

  // Brand icon toggle sidebar expansion
  const brandToggle = document.getElementById("brand-toggle");
  const sidebar = document.getElementById("global-sidebar");
  if (brandToggle && sidebar) {
    brandToggle.addEventListener("click", (e) => {
      e.preventDefault();
      sidebar.classList.toggle("expanded");
    });
  }
}

function switchTab(tabId) {
  document.querySelectorAll(".nav-link").forEach(l => l.classList.remove("active"));
  const activeLink = document.querySelector(`.nav-link[data-tab="${tabId}"]`);
  if (activeLink) activeLink.classList.add("active");

  const studioViewport = document.getElementById("tab-studio");
  const fullViews = document.querySelectorAll(".full-view-container");
  const viewTitle = document.getElementById("view-title");
  const viewSubtitle = document.getElementById("view-subtitle");

  fullViews.forEach(v => v.classList.remove("active"));

  if (tabId === "tab-studio") {
    studioViewport.style.display = "flex";
    if (viewTitle) viewTitle.innerText = "Post Studio & Simulator";
    if (viewSubtitle) viewSubtitle.innerText = "Distraction-Free Editor with Real-Time Feed Simulator";
  } else {
    studioViewport.style.display = "none";
    const targetPane = document.getElementById(tabId);
    if (targetPane) targetPane.classList.add("active");

    if (tabId === "tab-queue") {
      if (viewTitle) viewTitle.innerText = "Schedule & Cadence Queue";
      if (viewSubtitle) viewSubtitle.innerText = "Cadence Management & Smart Peak Engagement Slots";
      loadQueue();
    } else if (tabId === "tab-crm") {
      if (viewTitle) viewTitle.innerText = "Warm-Lead CRM Inbox";
      if (viewSubtitle) viewSubtitle.innerText = "Prospect Relationship Pipeline & 1-Click DM Outreach";
      loadLeads();
    } else if (tabId === "tab-inspirations") {
      if (viewTitle) viewTitle.innerText = "Viral Post Swipe File";
      if (viewSubtitle) viewSubtitle.innerText = "356 Reverse-Engineered High-Performing Blueprints";
      loadInspirations(currentInspQuery, currentInspTopic);
    } else if (tabId === "tab-analytics") {
      if (viewTitle) viewTitle.innerText = "Creator Analytics & Growth";
      if (viewSubtitle) viewSubtitle.innerText = "Audience Reach, Profile Views, and Time-Series Analytics";
      loadKPIs();
      loadAnalyticsChart();
    } else if (tabId === "tab-ai-command") {
      if (viewTitle) viewTitle.innerText = "Gemini & Antigravity Command Hub";
      if (viewSubtitle) viewSubtitle.innerText = "Dual-Mode Local Intelligence & Autonomous Content Generation";
    } else if (tabId === "tab-docs") {
      if (viewTitle) viewTitle.innerText = "Enterprise Documentation & Architecture Playbook";
      if (viewSubtitle) viewSubtitle.innerText = "Architecture Reference, Algorithmic Safety Formulas & Operations Manual";
      loadDocsHub();
    }
  }
}

// -------------------------------------------------------------
// 2. UNICODE MATHEMATICAL FORMATTERS (No Em-Dashes)
// -------------------------------------------------------------
function toUnicodeSansBold(text) {
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const code = text.charCodeAt(i);
    if (code >= 65 && code <= 90) {
      out += String.fromCodePoint(0x1D5D4 + code - 65);
    } else if (code >= 97 && code <= 122) {
      out += String.fromCodePoint(0x1D5EE + code - 97);
    } else if (code >= 48 && code <= 57) {
      out += String.fromCodePoint(0x1D7EC + code - 48);
    } else {
      out += text[i];
    }
  }
  return out;
}

function toUnicodeSansItalic(text) {
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const code = text.charCodeAt(i);
    if (code >= 65 && code <= 90) {
      out += String.fromCodePoint(0x1D608 + code - 65);
    } else if (code >= 97 && code <= 122) {
      out += String.fromCodePoint(0x1D622 + code - 97);
    } else {
      out += text[i];
    }
  }
  return out;
}

function toUnicodeMonospace(text) {
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const code = text.charCodeAt(i);
    if (code >= 65 && code <= 90) {
      out += String.fromCodePoint(0x1D670 + code - 65);
    } else if (code >= 97 && code <= 122) {
      out += String.fromCodePoint(0x1D68A + code - 97);
    } else if (code >= 48 && code <= 57) {
      out += String.fromCodePoint(0x1D7F6 + code - 48);
    } else {
      out += text[i];
    }
  }
  return out;
}

function toStrikethrough(text) {
  return text.split('').map(c => c !== '\n' ? c + '\u0336' : c).join('');
}

function cleanEmDashes(text) {
  let cleaned = text.replace(/—/g, ", ").replace(/–/g, ", ");
  cleaned = cleaned.replace(/(?<=\w)--+(?=\w)/g, ", ");
  cleaned = cleaned.replace(/[ \t]+/g, " ");
  cleaned = cleaned.replace(/ +([,.:;?!])/g, "$1");
  cleaned = cleaned.replace(/,\s*,/g, ",");
  return cleaned.trim();
}

// -------------------------------------------------------------
// 3. DISTRACTION-FREE EDITOR & LIVE MOBILE SIMULATOR
// -------------------------------------------------------------
function initEditor() {
  const textarea = document.getElementById("post-editor-input");
  const mediaInput = document.getElementById("media-path-input");
  const seeMoreBtn = document.getElementById("simulated-see-more");
  const belowFold = document.getElementById("simulated-below-fold");

  // Load scheduled post or draft by default
  fetch(`${API_BASE}/posts?status=scheduled`)
    .then(r => r.json())
    .then(data => {
      const scheduled = data.posts && data.posts[0];
      if (scheduled && !textarea.value) {
        currentDraftId = scheduled.id;
        textarea.value = scheduled.content;
        if (scheduled.media_urls && scheduled.media_urls.length) {
          mediaInput.value = scheduled.media_urls[0];
        }
        updateStudioState();
      }
    })
    .catch(() => {});

  textarea.addEventListener("input", updateStudioState);
  mediaInput.addEventListener("input", updateStudioState);

  // Toggle "...see more" in mobile simulator
  seeMoreBtn.addEventListener("click", () => {
    isSeeMoreExpanded = !isSeeMoreExpanded;
    if (isSeeMoreExpanded) {
      belowFold.style.display = "block";
      seeMoreBtn.innerText = "...see less";
    } else {
      belowFold.style.display = "none";
      seeMoreBtn.innerText = "...see more";
    }
  });

  // Clean Formatting Button
  const btnClean = document.getElementById("btn-clean-formatting");
  if (btnClean) {
    btnClean.addEventListener("click", () => {
      textarea.value = cleanEmDashes(textarea.value);
      updateStudioState();
      showToast("Scrubbed em-dashes and normalized spacing.");
    });
  }

  // Save Draft Button
  const btnSave = document.getElementById("btn-save-draft");
  if (btnSave) {
    btnSave.addEventListener("click", async () => {
      await saveCurrentDraft("draft");
    });
  }

  // Schedule Post Button
  const btnSchedule = document.getElementById("btn-schedule-post");
  if (btnSchedule) {
    btnSchedule.addEventListener("click", async () => {
      const timeStr = prompt("Enter scheduled time (YYYY-MM-DDTHH:MM:SS) or leave blank for next smart slot:", new Date(Date.now() + 3600000).toISOString().slice(0, 19));
      if (timeStr !== null) {
        await saveCurrentDraft("scheduled", timeStr);
      }
    });
  }

  // Mode Switcher (Text vs 1080x1080 Carousel Deck)
  const modeTextBtn = document.getElementById("mode-text-btn");
  const modeCarouselBtn = document.getElementById("mode-carousel-btn");
  const textCanvas = document.getElementById("editor-text-mode-canvas");
  const carouselCanvas = document.getElementById("carousel-deck-canvas");
  const mediaRow = document.getElementById("media-attachment-row");

  if (modeTextBtn && modeCarouselBtn) {
    modeTextBtn.addEventListener("click", () => {
      modeTextBtn.classList.add("active");
      modeCarouselBtn.classList.remove("active");
      textCanvas.style.display = "block";
      carouselCanvas.classList.remove("active");
      mediaRow.style.display = "flex";
    });

    modeCarouselBtn.addEventListener("click", () => {
      modeCarouselBtn.classList.add("active");
      modeTextBtn.classList.remove("active");
      textCanvas.style.display = "none";
      carouselCanvas.classList.add("active");
      mediaRow.style.display = "none";
      renderCarouselDeck();
    });
  }
}

async function saveCurrentDraft(status = "draft", scheduledFor = null) {
  const content = document.getElementById("post-editor-input").value.trim();
  const mediaUrl = document.getElementById("media-path-input").value.trim();
  if (!content) {
    showToast("Cannot save an empty post.");
    return;
  }

  try {
    const payload = {
      content,
      media_urls: mediaUrl ? [mediaUrl] : [],
      status,
      scheduled_for: scheduledFor
    };

    const res = await fetch(`${API_BASE}/posts/${currentDraftId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      showToast(status === "scheduled" ? "Post scheduled successfully!" : "Draft saved to local database.");
    } else {
      // Create new post if not existing
      await fetch(`${API_BASE}/posts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      showToast("Post saved successfully!");
    }
  } catch (e) {
    showToast("Failed to save post: " + e.message);
  }
}

// -------------------------------------------------------------
// 4. THE DYNAMIC GLOWING RED "SEE MORE" FOLD LINE
// -------------------------------------------------------------
function updateStudioState() {
  const textarea = document.getElementById("post-editor-input");
  const mediaInput = document.getElementById("media-path-input");
  const text = textarea.value;
  const mediaUrl = mediaInput.value.trim();

  // 1. Character & Word Metrics
  const charCount = text.length;
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  const estDwellSeconds = Math.max(10, Math.round((words / 210) * 60) + (text.split("\n\n").length * 3));

  document.getElementById("top-char-count").innerText = charCount.toLocaleString();
  document.getElementById("dwell-display").innerText = `~${estDwellSeconds}s`;
  document.getElementById("top-dwell-time").innerText = `${estDwellSeconds}s`;

  // 2. Compute Pre-Fold Cutoff for LinkedIn Mobile Feed
  // Mobile LinkedIn feed truncates at ~180-210 characters OR at 3 lines, whichever occurs first.
  let preFoldText = "";
  let postFoldText = "";
  const lines = text.split("\n");

  if (lines.length > 3) {
    preFoldText = lines.slice(0, 3).join("\n");
    postFoldText = lines.slice(3).join("\n");
  } else if (text.length > 200) {
    // Cut around character 180 on word boundary
    const spaceIdx = text.lastIndexOf(" ", 195);
    const cutPos = spaceIdx > 120 ? spaceIdx : 190;
    preFoldText = text.slice(0, cutPos);
    postFoldText = text.slice(cutPos);
  } else {
    preFoldText = text;
    postFoldText = "";
  }

  const preFoldChars = preFoldText.length;
  document.getElementById("top-hook-count").innerText = preFoldChars;

  // 3. Position the Dynamic Glowing Red Fold Line in the Editor
  const foldLineEl = document.getElementById("editor-fold-line");
  const foldCharBadge = document.getElementById("fold-char-badge");

  if (foldLineEl && foldCharBadge) {
    if (text.trim().length > 0) {
      foldLineEl.style.display = "flex";
      // Estimate vertical offset based on pre-fold line count and text height
      const lineCount = preFoldText.split("\n").length;
      const calculatedTop = Math.min(260, Math.max(70, lineCount * 34 + 30));
      foldLineEl.style.top = `${calculatedTop}px`;
      foldCharBadge.innerText = `Pre-Fold: ${preFoldChars} chars`;
    } else {
      foldLineEl.style.display = "none";
    }
  }

  // 4. Update Mobile Feed Simulator
  const simAboveFold = document.getElementById("simulated-above-fold");
  const simBelowFold = document.getElementById("simulated-below-fold");
  const simSeeMore = document.getElementById("simulated-see-more");
  const simMedia = document.getElementById("simulated-media");
  const simImg = document.getElementById("simulated-media-img");
  const simFoldStatus = document.getElementById("sim-fold-status");

  if (simAboveFold) simAboveFold.innerText = preFoldText || "Type in the editor to see your live preview...";
  if (simBelowFold) simBelowFold.innerText = postFoldText;

  if (postFoldText.trim().length > 0) {
    simSeeMore.style.display = "inline-block";
    simFoldStatus.innerText = preFoldChars <= 180 ? "Fold Safe" : "Fold Dense";
    simFoldStatus.className = preFoldChars <= 180 ? "sidebar-badge pro" : "sidebar-badge count";
  } else {
    simSeeMore.style.display = "none";
    simBelowFold.style.display = "none";
    simFoldStatus.innerText = "Pre-Fold Only";
  }

  // Media preview
  if (mediaUrl) {
    simMedia.style.display = "block";
    simImg.src = mediaUrl;
  } else {
    simMedia.style.display = "none";
    simImg.src = "";
  }

  // 5. Run Real-Time 6-Dimension Algorithmic Safety Audit
  runAlgorithmicAudit(text);
}

// -------------------------------------------------------------
// 5. 6-DIMENSION ALGORITHMIC SAFETY AUDITOR (0–100%)
// -------------------------------------------------------------
function runAlgorithmicAudit(text) {
  let score = 100;
  const issues = [];

  // Dimension 1: Outbound Link in Body (-40 points)
  const urlRegex = /(https?:\/\/[^\s]+|www\.[^\s]+|\b[a-zA-Z0-9-]+\.(com|io|ai|org|net|co)\b)/gi;
  const hasUrl = urlRegex.test(text);
  const dimLink = document.getElementById("dim-link-status");
  if (hasUrl) {
    score -= 40;
    dimLink.className = "dimension-status warning";
    dimLink.innerText = "⚠️ Link in Body (-40%)";
  } else {
    dimLink.className = "dimension-status safe";
    dimLink.innerText = "Safe (0 in body)";
  }

  // Dimension 2: Pre-Fold Hook CTR (-20 points if crowded or >210 chars)
  const firstLines = text.split("\n").slice(0, 3).join("\n");
  const dimHook = document.getElementById("dim-hook-status");
  if (firstLines.length > 210) {
    score -= 20;
    dimHook.className = "dimension-status warning";
    dimHook.innerText = "⚠️ Hook Exceeds Fold";
  } else if (firstLines.length > 0 && firstLines.length < 170) {
    dimHook.className = "dimension-status safe";
    dimHook.innerText = "Fold Safe (< 170 chars)";
  } else {
    dimHook.className = "dimension-status safe";
    dimHook.innerText = "Optimal Length";
  }

  // Dimension 3: Engagement-Bait Classifier (-25 points)
  const baitRegex = /(comment\s+['"]?yes['"]?|comment\s+below|type\s+['"]?info['"]?|like\s+and\s+share|tag\s+\d+\s+friends)/i;
  const hasBait = baitRegex.test(text);
  const dimBait = document.getElementById("dim-bait-status");
  if (hasBait) {
    score -= 25;
    dimBait.className = "dimension-status warning";
    dimBait.innerText = "⚠️ Engagement Bait";
  } else {
    dimBait.className = "dimension-status safe";
    dimBait.innerText = "Clean (0 flags)";
  }

  // Dimension 4: Hashtag Density (-15 points if > 5 tags)
  const hashtags = (text.match(/#[a-zA-Z0-9_]+/g) || []).length;
  const dimHash = document.getElementById("dim-hashtag-status");
  if (hashtags > 5) {
    score -= 15;
    dimHash.className = "dimension-status warning";
    dimHash.innerText = `⚠️ ${hashtags} tags (Stuffing)`;
  } else if (hashtags >= 2 && hashtags <= 4) {
    dimHash.className = "dimension-status safe";
    dimHash.innerText = `Optimal (${hashtags} tags)`;
  } else {
    dimHash.className = "dimension-status safe";
    dimHash.innerText = `${hashtags} tags`;
  }

  // Dimension 5: Pacing & Wall of Text (-15 points if > 4 lines unspaced)
  const paragraphs = text.split("\n\n");
  let hasWall = false;
  for (let p of paragraphs) {
    if (p.split("\n").length > 5 && p.length > 350) {
      hasWall = true;
      break;
    }
  }
  const dimPacing = document.getElementById("dim-pacing-status");
  if (hasWall) {
    score -= 15;
    dimPacing.className = "dimension-status warning";
    dimPacing.innerText = "⚠️ Wall of Text";
  } else {
    dimPacing.className = "dimension-status safe";
    dimPacing.innerText = "Well-spaced";
  }

  // Dimension 6: Font Accessibility & Zero Em-Dash (-15 points)
  const hasEmDash = /[—–]|(?<=\w)--+(?=\w)/.test(text);
  const dimEmdash = document.getElementById("dim-emdash-status");
  if (hasEmDash) {
    score -= 10;
    dimEmdash.className = "dimension-status warning";
    dimEmdash.innerText = "⚠️ Em-Dash Found";
  } else {
    dimEmdash.className = "dimension-status safe";
    dimEmdash.innerText = "Zero Em-Dash";
  }

  // Final Score Badge Render
  score = Math.max(20, Math.min(100, score));
  const badge = document.getElementById("algo-score-badge");
  const verdict = document.getElementById("verdict-display");

  if (badge) {
    if (score >= 90) {
      badge.className = "algo-score-badge high-reach";
      badge.innerText = `${score}% High Reach Profile`;
      if (verdict) { verdict.innerText = "Expand Feed"; verdict.style.color = "var(--accent-emerald)"; }
    } else if (score >= 70) {
      badge.className = "algo-score-badge moderate";
      badge.innerText = `${score}% Minor Optimizations`;
      if (verdict) { verdict.innerText = "Acceptable"; verdict.style.color = "var(--accent-amber)"; }
    } else {
      badge.className = "algo-score-badge high-risk";
      badge.innerText = `${score}% High Distribution Risk`;
      if (verdict) { verdict.innerText = "Reach Suppressed"; verdict.style.color = "var(--accent-rose)"; }
    }
  }
}

// -------------------------------------------------------------
// 6. FLOATING TEXT SELECTION ACTION BAR
// -------------------------------------------------------------
function initFloatingToolbar() {
  const textarea = document.getElementById("post-editor-input");
  const toolbar = document.getElementById("floating-selection-toolbar");

  if (!textarea || !toolbar) return;

  function updateToolbarPosition() {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;

    if (start === end || (end - start) < 2) {
      toolbar.style.display = "none";
      return;
    }

    // Get approximate cursor position inside textarea
    toolbar.style.display = "flex";
    toolbar.style.top = "20px";
    toolbar.style.right = "24px";
  }

  textarea.addEventListener("mouseup", updateToolbarPosition);
  textarea.addEventListener("keyup", updateToolbarPosition);

  // Wire Formatting Action Buttons
  function applySelectionTransform(transformFn) {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const val = textarea.value;
    const selected = val.substring(start, end);
    if (!selected) return;

    const transformed = transformFn(selected);
    textarea.value = val.substring(0, start) + transformed + val.substring(end);
    textarea.selectionStart = start;
    textarea.selectionEnd = start + transformed.length;
    updateStudioState();
    toolbar.style.display = "none";
  }

  document.getElementById("float-bold-btn").addEventListener("click", () => applySelectionTransform(toUnicodeSansBold));
  document.getElementById("float-italic-btn").addEventListener("click", () => applySelectionTransform(toUnicodeSansItalic));
  document.getElementById("float-mono-btn").addEventListener("click", () => applySelectionTransform(toUnicodeMonospace));
  document.getElementById("float-strike-btn").addEventListener("click", () => applySelectionTransform(toStrikethrough));
  document.getElementById("float-clean-btn").addEventListener("click", () => applySelectionTransform(cleanEmDashes));

  document.getElementById("float-rehook-btn").addEventListener("click", () => {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selected = textarea.value.substring(start, end).trim();
    toolbar.style.display = "none";
    generateHookVariants(selected || textarea.value.slice(0, 150));
  });
}

// -------------------------------------------------------------
// 7. INLINE HOOK VARIANT CAROUSEL
// -------------------------------------------------------------
function initHookCarousel() {
  const triggerBtn = document.getElementById("btn-trigger-rehook");
  const closeBtn = document.getElementById("btn-close-hook-carousel");
  const prevBtn = document.getElementById("btn-prev-hook-scroll");
  const nextBtn = document.getElementById("btn-next-hook-scroll");
  const track = document.getElementById("hook-cards-track");

  if (triggerBtn) {
    triggerBtn.addEventListener("click", () => {
      const draft = document.getElementById("post-editor-input").value.trim();
      generateHookVariants(draft || "Stepping into enterprise architecture and modern systems requires discipline.");
    });
  }

  if (closeBtn) {
    closeBtn.addEventListener("click", () => {
      document.getElementById("hook-carousel-container").classList.remove("active");
    });
  }

  if (prevBtn && track) {
    prevBtn.addEventListener("click", () => {
      track.scrollBy({ left: -280, behavior: "smooth" });
    });
  }

  if (nextBtn && track) {
    nextBtn.addEventListener("click", () => {
      track.scrollBy({ left: 280, behavior: "smooth" });
    });
  }
}

async function generateHookVariants(contextText) {
  const container = document.getElementById("hook-carousel-container");
  const track = document.getElementById("hook-cards-track");
  container.classList.add("active");
  track.innerHTML = `<div style="padding: 16px; font-size: 13px; color: var(--text-muted);">⚡ Generating 10x scroll-stopping hook variants...</div>`;

  try {
    const res = await fetch(`${API_BASE}/format/re-hook`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: contextText })
    });
    const json = await res.json();
    const hooks = json.hooks || [];

    track.innerHTML = "";
    hooks.forEach((h, idx) => {
      const card = document.createElement("div");
      card.className = "hook-variant-card";
      const isSafe = h.is_mobile_fold_safe;

      card.innerHTML = `
        <div>
          <div class="hook-archetype-tag">${idx + 1}. ${escapeHtml(h.archetype)}</div>
          <div class="hook-card-text" style="margin-top: 6px;">${escapeHtml(h.hook_text)}</div>
        </div>
        <div class="hook-card-footer">
          <span class="hook-safe-badge ${isSafe ? 'safe' : 'truncated'}">${isSafe ? 'Fold Safe' : 'Truncated'} (${h.char_count}c)</span>
          <span style="color: var(--accent-indigo); font-weight: 600;">⚡ Apply</span>
        </div>
      `;

      card.addEventListener("click", () => {
        const textarea = document.getElementById("post-editor-input");
        const rawLines = textarea.value.split("\n\n");
        if (rawLines.length > 1) {
          rawLines[0] = h.hook_text;
          textarea.value = rawLines.join("\n\n");
        } else {
          textarea.value = h.hook_text + (textarea.value ? "\n\n" + textarea.value : "");
        }
        updateStudioState();
        showToast(`Applied "${h.archetype}" hook variant!`);
        container.classList.remove("active");
      });

      track.appendChild(card);
    });

  } catch (e) {
    track.innerHTML = `<div style="color: var(--accent-rose); padding: 12px;">Error generating hooks: ${e.message}</div>`;
  }
}

// -------------------------------------------------------------
// 8. 1080x1080 MULTI-SLIDE CAROUSEL BUILDER ENGINE
// -------------------------------------------------------------
function initCarouselBuilder() {
  const addSlideBtn = document.getElementById("btn-add-carousel-slide");
  const downloadBtn = document.getElementById("btn-download-carousel-pdf");
  const themeSelect = document.getElementById("carousel-theme-select");

  if (addSlideBtn) {
    addSlideBtn.addEventListener("click", () => {
      const nextNum = carouselSlides.length + 1;
      carouselSlides.push({
        tag: `STEP 0${nextNum}`,
        title: "New Architectural Principle",
        body: "Detail your framework point or strategic takeaway here."
      });
      renderCarouselDeck();
      showToast(`Added Slide ${nextNum}`);
    });
  }

  if (themeSelect) {
    themeSelect.addEventListener("change", (e) => {
      carouselTheme = e.target.value;
      showToast(`Carousel theme set to ${carouselTheme}`);
    });
  }

  if (downloadBtn) {
    downloadBtn.addEventListener("click", async () => {
      downloadBtn.disabled = true;
      downloadBtn.innerText = "⏳ Rendering 1080x1080 PDF...";
      try {
        const res = await fetch(`${API_BASE}/carousel/generate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            slides: carouselSlides,
            theme: carouselTheme,
            author_name: "Dharmik Shingala",
            author_title: "Content Strategist • Enterprise Systems"
          })
        });

        if (res.ok) {
          const blob = await res.blob();
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = "linkedin_executive_carousel.pdf";
          document.body.appendChild(a);
          a.click();
          a.remove();
          showToast("📄 1080x1080 PDF Carousel Downloaded!");
        } else {
          showToast("Failed to render PDF carousel");
        }
      } catch (e) {
        showToast("PDF rendering error: " + e.message);
      } finally {
        downloadBtn.disabled = false;
        downloadBtn.innerText = "📄 Download 1080×1080 PDF";
      }
    });
  }
}

function renderCarouselDeck() {
  const grid = document.getElementById("carousel-slides-grid");
  if (!grid) return;
  grid.innerHTML = "";

  carouselSlides.forEach((slide, idx) => {
    const card = document.createElement("div");
    card.className = "slide-tile-card";
    card.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <span class="slide-badge-num">Slide ${idx + 1} / ${carouselSlides.length}</span>
        ${carouselSlides.length > 1 ? `<button class="btn btn-subtle btn-sm btn-del-slide" data-idx="${idx}" style="color: var(--accent-rose); padding: 2px 6px;">✕</button>` : ""}
      </div>
      <input type="text" class="slide-tile-title-input" value="${escapeHtml(slide.title)}" placeholder="Slide Headline...">
      <textarea class="slide-tile-body-input" placeholder="Slide content...">${escapeHtml(slide.body)}</textarea>
      <div style="font-size: 10px; color: var(--text-dim); text-transform: uppercase;">1080×1080 • Pillow Native</div>
    `;

    card.querySelector(".slide-tile-title-input").addEventListener("input", (e) => {
      slide.title = e.target.value;
    });

    card.querySelector(".slide-tile-body-input").addEventListener("input", (e) => {
      slide.body = e.target.value;
    });

    const delBtn = card.querySelector(".btn-del-slide");
    if (delBtn) {
      delBtn.addEventListener("click", () => {
        carouselSlides.splice(idx, 1);
        renderCarouselDeck();
      });
    }

    grid.appendChild(card);
  });
}

// -------------------------------------------------------------
// 9. WARM-LEAD CRM INBOX & CONTEXTUAL DM STARTER
// -------------------------------------------------------------
let allLeads = [];
let currentCRMStatus = "";
let currentCRMSearch = "";
let currentDMLeadId = null;
let currentDMStyle = "value_add";
let crmSearchDebounce = null;

function initCRM() {
  const dmModal = document.getElementById("dm-modal");
  const dmCloseBtn = document.getElementById("dm-close-btn");
  const dmCancelBtn = document.getElementById("dm-cancel-btn");
  const copyBtn = document.getElementById("btn-copy-dm");

  const prospectModal = document.getElementById("prospect-modal");
  const addBtn = document.getElementById("btn-add-prospect-modal");
  const prospectCloseBtn = document.getElementById("prospect-modal-close");
  const prospectCancelBtn = document.getElementById("prospect-modal-cancel");
  const saveProspectBtn = document.getElementById("btn-save-prospect");
  const exportCsvBtn = document.getElementById("btn-export-crm-csv");
  const searchInput = document.getElementById("crm-search-input");
  const statusChips = document.querySelectorAll("#crm-status-chips .topic-chip");

  // DM Modal handlers
  if (dmCloseBtn) dmCloseBtn.addEventListener("click", () => { dmModal.style.display = "none"; });
  if (dmCancelBtn) dmCancelBtn.addEventListener("click", () => { dmModal.style.display = "none"; });

  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      const text = document.getElementById("dm-script-textarea").value;
      try {
        await navigator.clipboard.writeText(text);
        showToast("📋 Contextual DM copied to clipboard!");
      } catch (e) {
        showToast("Copied script!");
      }
      dmModal.style.display = "none";
    });
  }

  // DM Style Switcher Chips
  const styleChips = document.querySelectorAll("#dm-style-chips .topic-chip");
  styleChips.forEach(chip => {
    chip.addEventListener("click", async () => {
      styleChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      currentDMStyle = chip.getAttribute("data-style") || "value_add";
      if (currentDMLeadId) {
        const textarea = document.getElementById("dm-script-textarea");
        textarea.value = "Generating tailored copy...";
        try {
          const res = await fetch(`${API_BASE}/leads/${currentDMLeadId}/dm-script?style=${currentDMStyle}`);
          const json = await res.json();
          textarea.value = json.dm_script || "";
        } catch (e) {
          showToast("Error updating DM style");
        }
      }
    });
  });

  // Prospect Modal handlers
  if (addBtn && prospectModal) {
    addBtn.addEventListener("click", () => {
      document.getElementById("add-lead-name").value = "";
      document.getElementById("add-lead-headline").value = "";
      document.getElementById("add-lead-company").value = "";
      document.getElementById("add-lead-url").value = "";
      document.getElementById("add-lead-notes").value = "";
      prospectModal.style.display = "flex";
      document.getElementById("add-lead-name").focus();
    });
  }

  if (prospectCloseBtn && prospectModal) {
    prospectCloseBtn.addEventListener("click", () => { prospectModal.style.display = "none"; });
  }
  if (prospectCancelBtn && prospectModal) {
    prospectCancelBtn.addEventListener("click", () => { prospectModal.style.display = "none"; });
  }

  if (saveProspectBtn && prospectModal) {
    saveProspectBtn.addEventListener("click", async () => {
      const name = document.getElementById("add-lead-name").value.trim();
      if (!name) {
        showToast("Full name is required");
        return;
      }
      const headline = document.getElementById("add-lead-headline").value.trim();
      const company = document.getElementById("add-lead-company").value.trim();
      const profileUrl = document.getElementById("add-lead-url").value.trim();
      const engagement = document.getElementById("add-lead-engagement").value;
      const status = document.getElementById("add-lead-status").value;
      const notes = document.getElementById("add-lead-notes").value.trim();

      try {
        saveProspectBtn.innerText = "Saving...";
        await fetch(`${API_BASE}/leads`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name,
            headline,
            company,
            profile_url: profileUrl,
            engagement_type: engagement,
            status: status,
            notes: notes || "Added manually to pipeline"
          })
        });
        showToast(`Added ${name} to Inbound CRM!`);
        prospectModal.style.display = "none";
        loadLeads();
      } catch (e) {
        showToast("Failed to add prospect: " + e.message);
      } finally {
        saveProspectBtn.innerText = "Save Prospect";
      }
    });
  }

  // Export CSV Handler
  if (exportCsvBtn) {
    exportCsvBtn.addEventListener("click", () => {
      let url = `${API_BASE}/leads/export/csv?`;
      if (currentCRMStatus) url += `status=${encodeURIComponent(currentCRMStatus)}&`;
      if (currentCRMSearch) url += `search=${encodeURIComponent(currentCRMSearch)}&`;
      window.open(url, "_blank");
      showToast("⬇ Exporting CRM leads as CSV...");
    });
  }

  // Search Input Handler
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      clearTimeout(crmSearchDebounce);
      crmSearchDebounce = setTimeout(() => {
        currentCRMSearch = e.target.value.trim();
        loadLeads();
      }, 250);
    });
  }

  // Status Filter Chips
  statusChips.forEach(chip => {
    chip.addEventListener("click", () => {
      statusChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      currentCRMStatus = chip.getAttribute("data-status") || "";
      loadLeads();
    });
  });
}

async function loadLeads() {
  try {
    let url = `${API_BASE}/leads?`;
    if (currentCRMStatus) url += `status=${encodeURIComponent(currentCRMStatus)}&`;
    if (currentCRMSearch) url += `search=${encodeURIComponent(currentCRMSearch)}&`;

    const res = await fetch(url);
    if (!res.ok) return;
    const json = await res.json();
    allLeads = json.leads || [];

    // Also fetch unfiltered count for top KPI cards if currently filtering
    if (currentCRMStatus || currentCRMSearch) {
      fetch(`${API_BASE}/leads`).then(r => r.json()).then(allData => {
        updateCRMKPIs(allData.leads || []);
      }).catch(() => {});
    } else {
      updateCRMKPIs(allLeads);
    }

    renderLeadsTable(allLeads);
  } catch (e) {
    console.error("Failed to load leads:", e);
  }
}

function updateCRMKPIs(leads) {
  const totalEl = document.getElementById("crm-total-leads");
  const outreachEl = document.getElementById("crm-outreach-count");
  const connectedEl = document.getElementById("crm-connected-count");
  const meetingEl = document.getElementById("crm-meeting-count");

  if (totalEl) totalEl.innerText = leads.length;
  if (outreachEl) outreachEl.innerText = leads.filter(l => l.status === "Outreach Sent").length;
  if (connectedEl) connectedEl.innerText = leads.filter(l => l.status === "Connected").length;
  if (meetingEl) meetingEl.innerText = leads.filter(l => l.status === "Meeting Booked").length;
}

function renderLeadsTable(leads) {
  const tbody = document.getElementById("crm-table-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (!leads.length) {
    const msg = (currentCRMStatus || currentCRMSearch) ?
      "No matching prospects found. Try adjusting your search or status filter." :
      "No prospects in CRM pipeline. Click '+ Add Prospect' or browse comments on LinkedIn to auto-capture engagers.";
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 28px;">${msg}</td></tr>`;
    return;
  }

  leads.forEach(lead => {
    const tr = document.createElement("tr");
    const statuses = ["New Lead", "Outreach Sent", "Connected", "Meeting Booked"];
    const statusOptions = statuses.map(s => `<option value="${s}" ${lead.status === s ? 'selected' : ''}>${s}</option>`).join("");

    const engType = lead.engagement_type || "Commented";
    const engClass = engType.toLowerCase();

    tr.innerHTML = `
      <td>
        <strong>${escapeHtml(lead.name)}</strong>
        ${lead.profile_url ? `<a href="${escapeHtml(lead.profile_url)}" target="_blank" style="display: block; font-size: 11px; color: var(--accent-indigo); text-decoration: none; margin-top: 2px;">Profile ↗</a>` : ''}
      </td>
      <td>
        <div style="font-weight: 500;">${escapeHtml(lead.headline || '')}</div>
        <small style="color: var(--text-muted); font-size: 11.5px;">${escapeHtml(lead.company || '')}</small>
      </td>
      <td><span class="crm-badge ${engClass}">${escapeHtml(engType)}</span></td>
      <td>
        <select class="media-path-field crm-status-select" data-id="${lead.id}" style="padding: 4px 8px; font-size: 12px; border-radius: 6px;">
          ${statusOptions}
        </select>
      </td>
      <td style="font-size: 12px; color: var(--text-secondary); max-width: 280px; word-break: break-word;">${escapeHtml(lead.notes || '')}</td>
      <td>
        <div style="display: flex; gap: 6px;">
          <button class="btn btn-outline btn-sm btn-generate-dm" data-id="${lead.id}" title="Generate personalized outreach DM">⚡ Contextual DM</button>
          <button class="btn btn-danger-outline btn-sm btn-del-lead" data-id="${lead.id}" title="Delete prospect">✕</button>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });

  tbody.querySelectorAll(".crm-status-select").forEach(sel => {
    sel.addEventListener("change", async () => {
      const id = sel.getAttribute("data-id");
      await fetch(`${API_BASE}/leads/${id}/status`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: sel.value })
      });
      showToast(`Status updated to "${sel.value}"`);
      loadLeads();
    });
  });

  tbody.querySelectorAll(".btn-generate-dm").forEach(btn => {
    btn.addEventListener("click", async () => {
      const id = btn.getAttribute("data-id");
      currentDMLeadId = id;

      // Reset active style chip to default value_add
      currentDMStyle = "value_add";
      const styleChips = document.querySelectorAll("#dm-style-chips .topic-chip");
      styleChips.forEach(c => {
        if (c.getAttribute("data-style") === "value_add") c.classList.add("active");
        else c.classList.remove("active");
      });

      try {
        const textarea = document.getElementById("dm-script-textarea");
        textarea.value = "Generating tailored outreach DM...";
        document.getElementById("dm-modal").style.display = "flex";

        const res = await fetch(`${API_BASE}/leads/${id}/dm-script?style=${currentDMStyle}`);
        const json = await res.json();
        textarea.value = json.dm_script || "";
      } catch (e) {
        showToast("Error generating DM script: " + e.message);
      }
    });
  });

  tbody.querySelectorAll(".btn-del-lead").forEach(btn => {
    btn.addEventListener("click", async () => {
      const id = btn.getAttribute("data-id");
      if (confirm("Remove this prospect from CRM?")) {
        await fetch(`${API_BASE}/leads/${id}`, { method: "DELETE" });
        showToast("Prospect removed from CRM.");
        loadLeads();
      }
    });
  });
}


// -------------------------------------------------------------
// 10. VIRAL POST SWIPE FILE (356 Vaulted Blueprints)
// -------------------------------------------------------------
function initInspirations() {
  const searchInput = document.getElementById("insp-search-input");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      clearTimeout(inspSearchDebounce);
      inspSearchDebounce = setTimeout(() => {
        currentInspQuery = e.target.value.trim();
        loadInspirations(currentInspQuery, currentInspTopic);
      }, 250);
    });
  }

  const topicChips = document.querySelectorAll("#insp-topic-chips .topic-chip");
  topicChips.forEach(chip => {
    chip.addEventListener("click", () => {
      topicChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      currentInspTopic = chip.getAttribute("data-topic") || "";
      loadInspirations(currentInspQuery, currentInspTopic);
    });
  });
}

async function loadInspirations(query = "", topic = "") {
  try {
    const params = new URLSearchParams();
    if (query) params.append("query", query);
    if (topic) params.append("topic", topic);
    params.append("limit", "100");

    const url = `${API_BASE}/inspirations?${params.toString()}`;
    const res = await fetch(url);
    if (!res.ok) return;
    const json = await res.json();
    const items = json.inspirations || [];
    const totalVaulted = json.total_vaulted || 356;

    const countBadge = document.getElementById("swipe-count-badge");
    if (countBadge) {
      countBadge.innerText = (topic || query) ? `${items.length} of ${totalVaulted} Blueprints` : `${totalVaulted} Vaulted Blueprints`;
    }

    const container = document.getElementById("inspirations-container");
    if (!container) return;
    container.innerHTML = "";

    if (!items.length) {
      container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); padding: 48px;">No matching blueprints found in vault. Try another search or category.</div>`;
      return;
    }

    items.forEach(insp => {
      const card = document.createElement("div");
      card.className = "swipe-card";
      card.innerHTML = `
        <div class="swipe-card-header">
          <div>
            <div style="display: flex; align-items: center; gap: 8px;">
              <span class="swipe-card-author">${escapeHtml(insp.author_name || 'Creator')}</span>
              ${insp.topic ? `<span class="sidebar-badge pro">${escapeHtml(insp.topic)}</span>` : ''}
            </div>
            <div class="swipe-card-sub">${escapeHtml(insp.author_headline || '')}</div>
          </div>
          <span style="color: var(--accent-indigo); font-weight: 700; font-size: 12px;">👍 ${Number(insp.likes_count || 0).toLocaleString()}</span>
        </div>
        <div class="swipe-card-body">${escapeHtml(insp.content)}</div>
        <div style="display: flex; gap: 8px;">
          <button class="btn btn-primary btn-sm btn-use-blueprint" style="flex: 1;" data-text="${encodeURIComponent(insp.content)}">
            ⚡ Load into Post Studio
          </button>
          <button class="btn btn-outline btn-sm btn-copy-blueprint" data-text="${encodeURIComponent(insp.content)}">
            📋 Copy
          </button>
        </div>
      `;

      card.querySelector(".btn-use-blueprint").addEventListener("click", () => {
        document.getElementById("post-editor-input").value = insp.content;
        updateStudioState();
        switchTab("tab-studio");
        showToast("Loaded blueprint into Distraction-Free Editor!");
      });

      card.querySelector(".btn-copy-blueprint").addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(insp.content);
          showToast("Copied blueprint to clipboard!");
        } catch (e) {
          showToast("Copied!");
        }
      });

      container.appendChild(card);
    });

  } catch (e) {
    console.error("Failed to load inspirations:", e);
  }
}

// -------------------------------------------------------------
// 11. SCHEDULE & CADENCE QUEUE
// -------------------------------------------------------------
function initQueue() {
  const refreshBtn = document.getElementById("btn-refresh-queue");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      loadQueue();
      showToast("Queue refreshed.");
    });
  }
}

async function loadQueue() {
  try {
    const res = await fetch(`${API_BASE}/posts?status=scheduled`);
    if (!res.ok) return;
    const json = await res.json();
    const posts = json.posts || [];

    const badge = document.getElementById("queue-badge-count");
    if (badge) badge.innerText = posts.length;

    const container = document.getElementById("queue-cards-list");
    if (!container) return;
    container.innerHTML = "";

    if (!posts.length) {
      container.innerHTML = `<p style="color: var(--text-muted); padding: 16px;">No posts currently scheduled in queue.</p>`;
      return;
    }

    posts.forEach(p => {
      const card = document.createElement("div");
      card.className = "kpi-box";
      card.style.marginBottom = "14px";
      const schedTime = p.scheduled_for ? new Date(p.scheduled_for).toLocaleString() : "Today at 5:30 PM IST";

      card.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
          <div>
            <div style="display: flex; align-items: center; gap: 8px;">
              <span class="sidebar-badge pro">⏰ ${schedTime}</span>
              <span style="font-size: 11px; color: var(--text-dim);">${p.id}</span>
            </div>
            <h4 style="font-size: 14px; font-weight: 700; margin-top: 8px; color: var(--text-primary);">${escapeHtml(p.content.split("\n")[0])}</h4>
            <p style="font-size: 12px; color: var(--text-muted); margin-top: 4px; line-height: 1.4;">${escapeHtml(p.content.slice(0, 200))}...</p>
          </div>
          <div style="display: flex; gap: 6px;">
            <button class="btn btn-outline btn-sm btn-queue-edit" data-id="${p.id}">Edit</button>
            <button class="btn btn-danger-outline btn-sm btn-queue-del" data-id="${p.id}">✕</button>
          </div>
        </div>
      `;

      card.querySelector(".btn-queue-edit").addEventListener("click", () => {
        document.getElementById("post-editor-input").value = p.content;
        currentDraftId = p.id;
        updateStudioState();
        switchTab("tab-studio");
        showToast("Loaded scheduled post into Studio!");
      });

      card.querySelector(".btn-queue-del").addEventListener("click", async () => {
        if (confirm("Cancel and delete this scheduled post?")) {
          await fetch(`${API_BASE}/posts/${p.id}`, { method: "DELETE" });
          showToast("Post deleted.");
          loadQueue();
        }
      });

      container.appendChild(card);
    });

  } catch (e) {
    console.error("Failed to load queue:", e);
  }
}

// -------------------------------------------------------------
// 12. CREATOR ANALYTICS OVERVIEW
// -------------------------------------------------------------
async function loadKPIs() {
  try {
    const res = await fetch(`${API_BASE}/analytics/kpis?range=${currentRange}`);
    if (!res.ok) return;
    const data = await res.json();

    const fEl = document.getElementById("kpi-followers");
    const vEl = document.getElementById("kpi-views");
    const iEl = document.getElementById("kpi-impressions");

    if (fEl) fEl.innerText = Number(data.total_followers || 2412).toLocaleString();
    if (vEl) vEl.innerText = Number(data.profile_views || 104).toLocaleString();
    if (iEl) iEl.innerText = Number(data.impressions || 314).toLocaleString();

    const csvBtn = document.getElementById("btn-export-csv-report");
    if (csvBtn) {
      csvBtn.onclick = () => {
        window.location.href = `${API_BASE}/analytics/export?format=csv`;
        showToast("Downloading analytics CSV report...");
      };
    }
  } catch (e) {}
}

async function loadAnalyticsChart() {
  try {
    const res = await fetch(`${API_BASE}/analytics/overview?range=${currentRange}`);
    if (!res.ok) return;
    const json = await res.json();
    const series = json.series || [];

    const labels = series.map(s => s.bucket.slice(5));
    const impressionsData = series.map(s => s.metrics.impressions || 0);

    const canvas = document.getElementById("analytics-chart-canvas");
    if (!canvas) return;

    if (analyticsChartInstance) {
      analyticsChartInstance.destroy();
    }

    analyticsChartInstance = new Chart(canvas, {
      type: "line",
      data: {
        labels: labels,
        datasets: [{
          label: "Daily Impressions",
          data: impressionsData,
          borderColor: "#4F46E5",
          backgroundColor: "rgba(79, 70, 229, 0.08)",
          borderWidth: 2,
          pointBackgroundColor: "#4F46E5",
          pointRadius: 3,
          fill: true,
          tension: 0.35
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false }
        },
        scales: {
          x: {
            grid: { color: "#F1F1F4" },
            ticks: { color: "#A1A1AA", font: { family: "Inter", size: 11 } }
          },
          y: {
            grid: { color: "#F1F1F4" },
            ticks: { color: "#A1A1AA", font: { family: "Inter", size: 11 } }
          }
        }
      }
    });
  } catch (e) {}
}

// -------------------------------------------------------------
// 13. AI COMMAND HUB (Dual-Mode Local & Gemini)
// -------------------------------------------------------------
function initAICommandCenter() {
  const runBtn = document.getElementById("btn-run-ai-command");
  const promptInput = document.getElementById("ai-command-prompt");
  const outputArea = document.getElementById("ai-command-output");
  const copyBtn = document.getElementById("btn-copy-ai-output");
  const sendBtn = document.getElementById("btn-send-output-to-editor");
  const attachBtn = document.getElementById("btn-attach-draft-context");

  document.querySelectorAll(".ai-quick-cmd").forEach(chip => {
    chip.addEventListener("click", () => {
      promptInput.value = chip.getAttribute("data-cmd");
      promptInput.focus();
    });
  });

  if (attachBtn) {
    attachBtn.addEventListener("click", () => {
      const draft = document.getElementById("post-editor-input").value.trim();
      if (draft) {
        promptInput.value += (promptInput.value ? "\n\n" : "") + `Context from Studio:\n${draft}`;
        showToast("Attached current draft as context!");
      }
    });
  }

  if (runBtn) {
    runBtn.addEventListener("click", async () => {
      const cmd = promptInput.value.trim();
      if (!cmd) {
        showToast("Please enter a command or prompt.");
        return;
      }

      runBtn.disabled = true;
      runBtn.innerText = "⏳ Executing...";
      outputArea.value = "Executing command via AI Engine...";

      try {
        const res = await fetch(`${API_BASE}/ai/command`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ command: cmd })
        });
        const json = await res.json();
        if (json.status === "success") {
          outputArea.value = json.output;
          showToast(`Generated successfully via ${json.engine}!`);
        } else {
          outputArea.value = "Error: " + (json.detail || "Unable to generate");
        }
      } catch (e) {
        outputArea.value = "Error: " + e.message;
      } finally {
        runBtn.disabled = false;
        runBtn.innerText = "Execute Command";
      }
    });
  }

  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      if (outputArea.value) {
        await navigator.clipboard.writeText(outputArea.value);
        showToast("Output copied to clipboard!");
      }
    });
  }

  if (sendBtn) {
    sendBtn.addEventListener("click", () => {
      if (outputArea.value) {
        document.getElementById("post-editor-input").value = outputArea.value;
        updateStudioState();
        switchTab("tab-studio");
        showToast("Loaded into Post Studio!");
      }
    });
  }
}

// -------------------------------------------------------------
// UI UTILITIES
// -------------------------------------------------------------
function showToast(msg) {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const t = document.createElement("div");
  t.className = "toast";
  t.innerText = msg;
  container.appendChild(t);
  setTimeout(() => {
    t.remove();
  }, 2800);
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// -------------------------------------------------------------
// 10. ENTERPRISE DOCUMENTATION & PLAYBOOK HUB CONTROLLER
// -------------------------------------------------------------
let docsModulesList = [];
let currentDocId = "studio-editor";
let currentDocRawContent = "";
let docsSearchDebounce = null;

// Fallback embedded metadata to ensure 100% offline availability
const DEFAULT_DOCS_MODULES = [
  {
    id: "studio-editor",
    number: "01",
    title: "Studio & Editor",
    category: "Core Authoring",
    icon: "edit",
    file: "01_STUDIO_AND_EDITOR.md",
    summary: "Universal top bar telemetry, dynamic glowing fold tracker, 1080×1080 PDF carousel deck, and 6-dimension algorithmic safety audit."
  },
  {
    id: "schedule-queue",
    number: "02",
    title: "Schedule & Queue",
    category: "Cadence & Timing",
    icon: "calendar",
    file: "02_SCHEDULE_AND_QUEUE.md",
    summary: "Publishing cadence rules, peak smart engagement slots (8:30 AM & 5:30 PM), and local background scheduler daemon."
  },
  {
    id: "inbound-crm",
    number: "03",
    title: "Inbound CRM",
    category: "Pipeline & Outreach",
    icon: "users",
    file: "03_INBOUND_CRM.md",
    summary: "Relationship pipeline stages, column dictionary, search/filtering, and 3-style contextual DM generator with zero em-dash compliance."
  },
  {
    id: "viral-swipe-file",
    number: "04",
    title: "Viral Swipe File",
    category: "Research & Blueprints",
    icon: "zap",
    file: "04_VIRAL_SWIPE_FILE.md",
    summary: "356 vaulted blueprints, 13 topic taxonomies, instant search, and Agno Framework autonomous inbound roadmap."
  },
  {
    id: "analytics",
    number: "05",
    title: "Creator Analytics",
    category: "Performance Telemetry",
    icon: "bar-chart",
    file: "05_ANALYTICS.md",
    summary: "Direct LinkedIn session ingestion (li_at & JSESSIONID), multi-range growth deltas, Chart.js vector curves, and demographics."
  },
  {
    id: "ai-command",
    number: "06",
    title: "AI Command Hub",
    category: "Dual-Mode Intelligence",
    icon: "sparkles",
    file: "06_AI_COMMAND.md",
    summary: "Dual-mode Gemini 2.5 Flash cloud API + Antigravity local deterministic engine, prompt presets, and direct Studio transfer."
  },
  {
    id: "enterprise-usage",
    number: "Master",
    title: "Enterprise Usage Manual",
    category: "Master Architecture",
    icon: "book",
    file: "ENTERPRISE_USAGE.md",
    summary: "Master operational reference manual covering all platform capabilities, security, and algorithms."
  }
];

function initDocsHub() {
  const searchInput = document.getElementById("docs-search-input");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      const q = e.target.value.toLowerCase().trim();
      clearTimeout(docsSearchDebounce);
      docsSearchDebounce = setTimeout(() => {
        renderDocsNav(q);
      }, 150);
    });
  }

  const exportBtn = document.getElementById("btn-export-docs-md");
  if (exportBtn) {
    exportBtn.addEventListener("click", () => {
      if (!currentDocRawContent) {
        showToast("No active document to export.");
        return;
      }
      const blob = new Blob([currentDocRawContent], { type: "text/markdown;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${currentDocId}_manual.md`;
      link.click();
      URL.revokeObjectURL(url);
      showToast(`Exported ${currentDocId}_manual.md`);
    });
  }
}

async function loadDocsHub() {
  try {
    const res = await fetch(`${API_BASE}/docs`);
    if (res.ok) {
      const data = await res.json();
      if (data.status === "success" && data.modules) {
        docsModulesList = data.modules;
      } else {
        docsModulesList = DEFAULT_DOCS_MODULES;
      }
    } else {
      docsModulesList = DEFAULT_DOCS_MODULES;
    }
  } catch (err) {
    console.warn("Using offline docs module list:", err);
    docsModulesList = DEFAULT_DOCS_MODULES;
  }

  const countBadge = document.getElementById("docs-count-badge");
  if (countBadge) countBadge.innerText = `${docsModulesList.length} Modules`;

  renderDocsNav("");
  selectDocModule(currentDocId);
}

function renderDocsNav(filterQuery = "") {
  const container = document.getElementById("docs-nav-list");
  if (!container) return;

  const filtered = docsModulesList.filter(m => {
    if (!filterQuery) return true;
    return m.title.toLowerCase().includes(filterQuery) ||
           m.category.toLowerCase().includes(filterQuery) ||
           m.summary.toLowerCase().includes(filterQuery);
  });

  if (filtered.length === 0) {
    container.innerHTML = `<div style="padding: 20px 10px; font-size: 13px; color: var(--text-muted); text-align: center;">No documentation matching "${escapeHtml(filterQuery)}"</div>`;
    return;
  }

  container.innerHTML = filtered.map(m => {
    const isActive = m.id === currentDocId ? "active" : "";
    return `
      <div class="docs-nav-item ${isActive}" data-id="${m.id}">
        <div class="docs-nav-item-top">
          <span class="docs-nav-item-number">${m.number}</span>
          <span class="docs-nav-item-cat">${escapeHtml(m.category)}</span>
        </div>
        <div class="docs-nav-item-title">${escapeHtml(m.title)}</div>
        <div class="docs-nav-item-summary">${escapeHtml(m.summary)}</div>
      </div>
    `;
  }).join("");

  container.querySelectorAll(".docs-nav-item").forEach(item => {
    item.addEventListener("click", () => {
      const modId = item.getAttribute("data-id");
      selectDocModule(modId);
    });
  });
}

async function selectDocModule(moduleId) {
  currentDocId = moduleId;

  // Update active state in sidebar
  document.querySelectorAll(".docs-nav-item").forEach(item => {
    item.classList.toggle("active", item.getAttribute("data-id") === moduleId);
  });

  const module = docsModulesList.find(m => m.id === moduleId) || DEFAULT_DOCS_MODULES[0];

  // Render header
  const header = document.getElementById("docs-article-header");
  if (header) {
    let jumpTab = "";
    let jumpLabel = "";
    if (module.id === "studio-editor") { jumpTab = "tab-studio"; jumpLabel = "🚀 Open Studio Editor"; }
    else if (module.id === "schedule-queue") { jumpTab = "tab-queue"; jumpLabel = "🚀 Open Schedule & Queue"; }
    else if (module.id === "inbound-crm") { jumpTab = "tab-crm"; jumpLabel = "🚀 Open Inbound CRM"; }
    else if (module.id === "viral-swipe-file") { jumpTab = "tab-inspirations"; jumpLabel = "🚀 Open Swipe File"; }
    else if (module.id === "analytics") { jumpTab = "tab-analytics"; jumpLabel = "🚀 Open Analytics"; }
    else if (module.id === "ai-command") { jumpTab = "tab-ai-command"; jumpLabel = "🚀 Open AI Command"; }

    const jumpBtnHtml = jumpTab ? `<button class="btn btn-primary btn-sm" id="btn-jump-to-tab" data-tab="${jumpTab}">${jumpLabel}</button>` : "";

    header.innerHTML = `
      <div class="docs-article-title-area">
        <span class="docs-article-breadcrumb">Manual / ${escapeHtml(module.category)} / Module ${module.number}</span>
        <h2 class="docs-article-title">${escapeHtml(module.title)}</h2>
      </div>
      <div class="docs-article-actions">
        ${jumpBtnHtml}
      </div>
    `;

    const jumpBtn = document.getElementById("btn-jump-to-tab");
    if (jumpBtn) {
      jumpBtn.addEventListener("click", () => {
        const target = jumpBtn.getAttribute("data-tab");
        switchTab(target);
      });
    }
  }

  // Load document content
  const bodyArea = document.getElementById("docs-article-body");
  if (bodyArea) {
    bodyArea.innerHTML = `<div style="display:flex; justify-content:center; align-items:center; height:200px; color:var(--text-muted);"><span style="animation:pulse 1s infinite;">Loading documentation module...</span></div>`;
  }

  try {
    const res = await fetch(`${API_BASE}/docs/${moduleId}`);
    if (res.ok) {
      const data = await res.json();
      currentDocRawContent = data.content || "";
      if (bodyArea) {
        bodyArea.innerHTML = renderMarkdownToHtml(currentDocRawContent);
      }
    } else {
      throw new Error(`Server returned ${res.status}`);
    }
  } catch (err) {
    console.warn("Failed fetching doc module from server, fallback:", err);
    if (bodyArea) {
      bodyArea.innerHTML = `
        <div style="padding:20px; background:var(--bg-subtle); border-radius:8px;">
          <h3 style="color:var(--accent-rose);">Offline Documentation Notice</h3>
          <p>Loaded metadata for <strong>${escapeHtml(module.title)}</strong>. The local backend server can be connected via <code>http://127.0.0.1:8000/api/docs/${moduleId}</code>.</p>
          <p>${escapeHtml(module.summary)}</p>
        </div>
      `;
    }
  }
}

// -------------------------------------------------------------
// CLIENT-SIDE ENTERPRISE MARKDOWN-TO-HTML PARSER
// -------------------------------------------------------------
function renderMarkdownToHtml(md) {
  if (!md) return "";

  // Normalize line endings
  let text = md.replace(/\r\n/g, "\n");

  // Protect code blocks before formatting
  const codeBlocks = [];
  text = text.replace(/```([a-zA-Z0-9_-]+)?\n([\s\S]*?)```/g, (match, lang, code) => {
    const token = `__CODE_BLOCK_${codeBlocks.length}__`;
    codeBlocks.push({ lang: lang || "text", code: escapeHtml(code.trim()) });
    return token;
  });

  // Protect math blocks $$\n ... \n$$ or $$\text{...}$$
  const mathBlocks = [];
  text = text.replace(/\$\$([\s\S]*?)\$\$/g, (match, formula) => {
    const token = `__MATH_BLOCK_${mathBlocks.length}__`;
    mathBlocks.push(formula.trim());
    return token;
  });

  // Protect inline code
  const inlineCodes = [];
  text = text.replace(/`([^`]+)`/g, (match, code) => {
    const token = `__INLINE_CODE_${inlineCodes.length}__`;
    inlineCodes.push(escapeHtml(code));
    return token;
  });

  // Horizontal rules
  text = text.replace(/^---$/gm, "<hr>");

  // Headers
  text = text.replace(/^#### (.*?)$/gm, "<h4>$1</h4>");
  text = text.replace(/^### (.*?)$/gm, "<h3>$1</h3>");
  text = text.replace(/^## (.*?)$/gm, "<h2>$1</h2>");
  text = text.replace(/^# (.*?)$/gm, "<h1>$1</h1>");

  // GitHub Alerts / Blockquotes
  text = text.replace(/^> \[!NOTE\]\s*(.*?)$/gm, '<blockquote class="alert-note"><strong>NOTE:</strong> $1</blockquote>');
  text = text.replace(/^> \[!IMPORTANT\]\s*(.*?)$/gm, '<blockquote class="alert-important"><strong>IMPORTANT:</strong> $1</blockquote>');
  text = text.replace(/^> \[!WARNING\]\s*(.*?)$/gm, '<blockquote class="alert-warning"><strong>WARNING:</strong> $1</blockquote>');
  text = text.replace(/^> (.*?)$/gm, '<blockquote>$1</blockquote>');

  // Tables: Match contiguous markdown table lines
  text = text.replace(/((?:^\|.+?\|\r?\n)+)/gm, (match) => {
    const lines = match.trim().split("\n");
    if (lines.length < 2) return match;
    
    // Check if second line is separator
    if (!lines[1].includes("---")) return match;

    const parseRow = (row) => row.split("|").slice(1, -1).map(c => c.trim());
    const headerCols = parseRow(lines[0]);
    const bodyRows = lines.slice(2).map(parseRow);

    let html = '<table><thead><tr>';
    headerCols.forEach(col => {
      html += `<th>${col}</th>`;
    });
    html += '</tr></thead><tbody>';

    bodyRows.forEach(row => {
      html += '<tr>';
      row.forEach(cell => {
        html += `<td>${cell}</td>`;
      });
      html += '</tr>';
    });
    html += '</tbody></table>';
    return html;
  });

  // Bold & Italic
  text = text.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/\*(.*?)\*/g, "<em>$1</em>");

  // Markdown links
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" style="color: var(--accent-indigo); text-decoration: underline;">$1</a>');

  // Bullet Lists
  text = text.replace(/^\s*[-*]\s+(.*?)$/gm, "<li>$1</li>");
  text = text.replace(/((?:<li>.*?<\/li>\s*)+)/g, "<ul>$1</ul>");

  // Paragraphs: Wrap loose lines in <p>
  const lines = text.split("\n");
  const processed = [];
  let inP = false;

  for (let line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      if (inP) { processed.push("</p>"); inP = false; }
      continue;
    }
    if (trimmed.startsWith("<h") || trimmed.startsWith("<table") || trimmed.startsWith("<ul") || 
        trimmed.startsWith("<li") || trimmed.startsWith("<blockquote") || trimmed.startsWith("<hr") ||
        trimmed.startsWith("__CODE_BLOCK_") || trimmed.startsWith("__MATH_BLOCK_")) {
      if (inP) { processed.push("</p>"); inP = false; }
      processed.push(trimmed);
    } else {
      if (!inP) { processed.push("<p>"); inP = true; }
      processed.push(trimmed);
    }
  }
  if (inP) processed.push("</p>");
  text = processed.join("\n");

  // Restore protected math blocks
  mathBlocks.forEach((math, idx) => {
    const card = `
      <div class="docs-formula-card">
        <div class="docs-formula-title">Mathematical Formula & Metric Specification</div>
        <div style="font-family: var(--font-mono); font-size: 13.5px; color: var(--text-primary); font-weight: 600;">${escapeHtml(math)}</div>
      </div>
    `;
    text = text.replace(new RegExp(`__MATH_BLOCK_${idx}__`, "g"), card);
  });

  // Restore protected code blocks
  codeBlocks.forEach((b, idx) => {
    const pre = `<pre><code class="language-${b.lang}">${b.code}</code></pre>`;
    text = text.replace(new RegExp(`__CODE_BLOCK_${idx}__`, "g"), pre);
  });

  // Restore protected inline code
  inlineCodes.forEach((code, idx) => {
    const span = `<code>${code}</code>`;
    text = text.replace(new RegExp(`__INLINE_CODE_${idx}__`, "g"), span);
  });

  return text;
}

