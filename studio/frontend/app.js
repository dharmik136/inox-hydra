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
 * - Viral Swipe File blueprints (count is read from the API, never hardcoded)
 */

const API_BASE = "http://127.0.0.1:8000/api";

// State Management
let currentRange = "30d";
let isSeeMoreExpanded = false;
let isEditorFoldLineEnabled = localStorage.getItem("linkedin_editor_fold_line") === "true";
let isSimGuideEnabled = localStorage.getItem("linkedin_sim_guide") === "true";
let currentDraftId = "post-enterprise-scheduled";
let currentInspTopic = "";
let currentInspQuery = "";
let currentInspMode = "real";
let inspSearchDebounce = null;
let analyticsChartInstance = null;

// Reimagined Editorial Motion OS State
let activeDossierLead = null;
let activeGeneratedHooks = [];

// Unified Media & AI Image Studio State
let activeMediaUrl = "";
let activeMediaAsset = null;
let cachedCreatorProfile = null;
let studioAspectRatio = "1:1";
let studioVisualStyle = "photorealistic";
let studioPalette = "navy_cyan";
let studioLighting = "studio";
let activeImageGenTaskId = null;
let imageGenPollInterval = null;
let lastSynthesizedPrompt = null;
let isSavingPost = false;

// Initialize on DOM Ready
document.addEventListener("DOMContentLoaded", () => {
  initNavigation();
  initInspector();
  initCommandPalette();
  initAICommandDock();
  initCursorAwareButtons();
  initEditor();
  initFloatingToolbar();
  initHookCarousel();
  initMediaDropzone();
  initImageStudio();
  initCRM();
  initInspirations();
  initAICommandCenter();
  initQueue();
  initScheduleModal();
  initDocsHub();
  initSettingsPanel();
  initEventStream();
  initPostAttributionModal();
  initFloatingFlowWidget();

  // Initial Data Fetching
  loadKPIs();
  loadAnalyticsChart();
  loadQueue();
  loadLeads();
  loadInspirations();
  loadCreatorProfile();
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

  // Brand icon toggle sidebar expansion (Morphing Tray - Section 5)
  const brandToggle = document.getElementById("brand-toggle");
  const sidebar = document.getElementById("global-sidebar");
  if (brandToggle && sidebar) {
    brandToggle.addEventListener("click", (e) => {
      e.preventDefault();
      sidebar.classList.toggle("expanded");
    });
  }

  initThemeToggle();
  initTopbarContextActions();
  fetchActiveAIStatus();
  updateTopbarContext("tab-studio");
}

function initThemeToggle() {
  const toggleBtn = document.getElementById("btn-theme-toggle");
  if (!toggleBtn) return;
  const iconDark = toggleBtn.querySelector(".theme-icon-dark");
  const iconLight = toggleBtn.querySelector(".theme-icon-light");

  // Determine initial theme: dark by default (Section 2.1)
  const savedTheme = localStorage.getItem("linkedin_studio_theme") || "dark";
  applyTheme(savedTheme);

  toggleBtn.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme") || "dark";
    const next = current === "dark" ? "light" : "dark";

    // Section 16.8: Native View Transition API theme switch
    if (document.startViewTransition) {
      document.startViewTransition(() => {
        applyTheme(next);
      });
    } else {
      applyTheme(next);
    }
  });

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("linkedin_studio_theme", theme);
    if (iconDark && iconLight) {
      if (theme === "dark") {
        iconDark.style.display = "inline";
        iconLight.style.display = "none";
      } else {
        iconDark.style.display = "none";
        iconLight.style.display = "inline";
      }
    }
    // Re-render chart if on analytics tab so canvas colors refresh
    const analyticsTab = document.getElementById("tab-analytics");
    if (analyticsTab && analyticsTab.classList.contains("active")) {
      loadAnalyticsChart();
    }
  }
}

function updateTopbarContext(tabId) {
  // Hide all context groups
  document.querySelectorAll(".topbar-context-group").forEach(g => g.classList.remove("active"));
  // Hide all action groups
  document.querySelectorAll(".topbar-actions-group").forEach(g => {
    g.classList.remove("active");
    g.style.display = "none";
  });

  if (tabId === "tab-studio") {
    const cg = document.getElementById("topbar-group-studio");
    if (cg) cg.classList.add("active");
    const ag = document.getElementById("topbar-actions-studio");
    if (ag) { ag.classList.add("active"); ag.style.display = "flex"; }
  } else if (tabId === "tab-analytics") {
    const cg = document.getElementById("topbar-group-analytics");
    if (cg) cg.classList.add("active");
    const ag = document.getElementById("topbar-actions-analytics");
    if (ag) { ag.classList.add("active"); ag.style.display = "flex"; }
  } else if (tabId === "tab-crm") {
    const cg = document.getElementById("topbar-group-crm");
    if (cg) cg.classList.add("active");
    const ag = document.getElementById("topbar-actions-crm");
    if (ag) { ag.classList.add("active"); ag.style.display = "flex"; }
  } else if (tabId === "tab-ai-command") {
    const cg = document.getElementById("topbar-group-ai");
    if (cg) cg.classList.add("active");
  } else if (tabId === "tab-queue") {
    const cg = document.getElementById("topbar-group-queue");
    if (cg) cg.classList.add("active");
  } else if (tabId === "tab-inspirations") {
    const cg = document.getElementById("topbar-group-inspirations");
    if (cg) cg.classList.add("active");
  } else if (tabId === "tab-settings") {
    const cg = document.getElementById("topbar-group-settings");
    if (cg) cg.classList.add("active");
  }
}

function initTopbarContextActions() {
  // Topbar range selector buttons for analytics
  const rangePills = document.querySelectorAll(".range-pill");
  rangePills.forEach(pill => {
    pill.addEventListener("click", () => {
      rangePills.forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      currentRange = pill.getAttribute("data-range") || "30d";
      loadAnalyticsChart();
    });
  });

  // Topbar analytics export button
  const topbarExportCsv = document.getElementById("btn-topbar-export-csv");
  if (topbarExportCsv) {
    topbarExportCsv.addEventListener("click", () => {
      const csvBtn = document.getElementById("btn-export-csv-report");
      if (csvBtn) csvBtn.click();
    });
  }

  // Topbar CRM export button
  const topbarCrmExport = document.getElementById("btn-topbar-crm-export");
  if (topbarCrmExport) {
    topbarCrmExport.addEventListener("click", () => {
      const crmBtn = document.getElementById("btn-export-crm-csv");
      if (crmBtn) crmBtn.click();
    });
  }

  // Topbar Add Prospect button
  const topbarAddLead = document.getElementById("btn-topbar-add-prospect");
  if (topbarAddLead) {
    topbarAddLead.addEventListener("click", () => {
      const modal = document.getElementById("prospect-modal");
      if (modal) {
        document.getElementById("add-lead-name").value = "";
        document.getElementById("add-lead-headline").value = "";
        document.getElementById("add-lead-company").value = "";
        document.getElementById("add-lead-url").value = "";
        document.getElementById("add-lead-notes").value = "";
        modal.style.display = "flex";
        document.getElementById("add-lead-name").focus();
      }
    });
  }
}

async function fetchActiveAIStatus() {
  try {
    const res = await fetch(`${API_BASE}/ai/config`);
    if (!res.ok) return;
    const data = await res.json();
    const engineLabel = document.getElementById("topbar-ai-engine-name");
    if (engineLabel && data.config) {
      const provider = (data.config.provider || "Local").toUpperCase();
      const model = data.config.model || "Deterministic Engine";
      engineLabel.innerText = `${provider} • ${model}`;
    }
  } catch (e) {
    // Non-blocking fallback
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
  updateTopbarContext(tabId);

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
      if (viewSubtitle) viewSubtitle.innerText = "Reverse-engineered hooks, structures and pacing you can pour your own metrics into";
      loadInspirations(currentInspQuery, currentInspTopic);
    } else if (tabId === "tab-analytics") {
      if (viewTitle) viewTitle.innerText = "Creator Analytics & Growth";
      if (viewSubtitle) viewSubtitle.innerText = "Audience Reach, Profile Views, and Time-Series Analytics";
      loadKPIs();
      loadAnalyticsChart();
    } else if (tabId === "tab-ai-command") {
      if (viewTitle) viewTitle.innerText = "Multi-Model AI Command Hub";
      if (viewSubtitle) viewSubtitle.innerText = "Bring-Your-Own-AI (OpenAI, Gemini, Claude, Ollama, Groq) + Local Deterministic Engine";
    } else if (tabId === "tab-docs") {
      if (viewTitle) viewTitle.innerText = "Enterprise Documentation & Architecture Playbook";
      if (viewSubtitle) viewSubtitle.innerText = "Architecture Reference, Algorithmic Safety Formulas & Operations Manual";
      loadDocsHub();
    } else if (tabId === "tab-settings") {
      if (viewTitle) viewTitle.innerText = "Brand Studio & Local Security";
      if (viewSubtitle) viewSubtitle.innerText = "Creator Identity, Watermark Positioning, and Zero-Egress Vault";
      loadCreatorProfile();
    }
  }
}

// -------------------------------------------------------------
// 1.B: DOCKABLE CONTEXTUAL INSPECTOR (Section 10)
// -------------------------------------------------------------
// Global Inspector & Stage State
let currentStageMode = "mobile";
let currentStageZoom = 1.0;
let carouselSlides = [];
let currentCarouselIndex = 0;
let isCarouselThemeLight = false;

// -------------------------------------------------------------
// 1.B: DOCKABLE CONTEXTUAL INSPECTOR & STAGE SYSTEM (Section 10)
// -------------------------------------------------------------
function initInspector() {
  const inspector = document.getElementById("studio-inspector");
  const toggleBtn = document.getElementById("btn-toggle-inspector");
  const closeBtn = document.getElementById("btn-close-inspector");
  const tabBtns = document.querySelectorAll(".inspector-tab-btn");
  const panes = document.querySelectorAll(".inspector-mode-pane");
  const stageBtns = document.querySelectorAll(".stage-toggle-btn");
  const scalableWrapper = document.getElementById("sim-stage-scalable-wrapper");
  const zoomLevelText = document.getElementById("stage-zoom-level");
  const stageViewport = document.getElementById("preview-stage-viewport");

  // 1. Drawer Toggle & Shortcuts
  if (toggleBtn && inspector) {
    toggleBtn.addEventListener("click", () => {
      const isCollapsed = inspector.classList.toggle("collapsed");
      toggleBtn.classList.toggle("active", !isCollapsed);
    });
  }

  if (closeBtn && inspector) {
    closeBtn.addEventListener("click", () => {
      inspector.classList.add("collapsed");
      if (toggleBtn) toggleBtn.classList.remove("active");
    });
  }

  window.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "\\") {
      e.preventDefault();
      if (toggleBtn) toggleBtn.click();
    }
  });

  // 2. Tab Navigation (Preview, Audit, Media, Brand, Prompt)
  tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      tabBtns.forEach(b => b.classList.remove("active"));
      panes.forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      const mode = btn.getAttribute("data-mode");
      const pane = document.getElementById(`inspector-pane-${mode}`);
      if (pane) pane.classList.add("active");
      // If brand tab activated, sync canvas immediately
      if (mode === "brand") syncBrandWatermarkCanvas();
    });
  });

  // 3. Stage Mode Switcher (Mobile, Desktop, Carousel)
  stageBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      stageBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentStageMode = btn.getAttribute("data-stage") || "mobile";
      updateStageDisplay();
    });
  });

  // 4. Zoom Scaling Engine (Adaptive across 100%, 125%, 150% screen zoom)
  function applyZoom(newZoom) {
    currentStageZoom = Math.min(1.8, Math.max(0.4, Number(newZoom.toFixed(2))));
    if (scalableWrapper) {
      scalableWrapper.style.setProperty("--stage-zoom", currentStageZoom);
    }
    if (zoomLevelText) {
      zoomLevelText.innerText = `${Math.round(currentStageZoom * 100)}%`;
    }
  }

  const btnZoomIn = document.getElementById("btn-zoom-in");
  const btnZoomOut = document.getElementById("btn-zoom-out");
  const btnZoomFit = document.getElementById("btn-zoom-fit");

  if (btnZoomIn) {
    btnZoomIn.addEventListener("click", () => applyZoom(currentStageZoom + 0.1));
  }
  if (btnZoomOut) {
    btnZoomOut.addEventListener("click", () => applyZoom(currentStageZoom - 0.1));
  }
  if (btnZoomFit) {
    btnZoomFit.addEventListener("click", () => {
      if (!stageViewport) return;
      const availableWidth = stageViewport.clientWidth - 24;
      const targetWidth = currentStageMode === "desktop" ? 380 : 350;
      const fitZoom = Math.min(1.15, Math.max(0.5, availableWidth / targetWidth));
      applyZoom(fitZoom);
      showToast(`Stage scaled to fit: ${Math.round(fitZoom * 100)}%`);
    });
  }

  // 5. Carousel Deck Interactive Controls
  const btnCarouselPrev = document.getElementById("btn-carousel-prev");
  const btnCarouselNext = document.getElementById("btn-carousel-next");
  const btnCarouselTheme = document.getElementById("btn-carousel-theme");

  if (btnCarouselPrev) {
    btnCarouselPrev.addEventListener("click", () => {
      if (!carouselSlides.length) return;
      currentCarouselIndex = (currentCarouselIndex - 1 + carouselSlides.length) % carouselSlides.length;
      renderCurrentCarouselSlide();
    });
  }

  if (btnCarouselNext) {
    btnCarouselNext.addEventListener("click", () => {
      if (!carouselSlides.length) return;
      currentCarouselIndex = (currentCarouselIndex + 1) % carouselSlides.length;
      renderCurrentCarouselSlide();
    });
  }

  if (btnCarouselTheme) {
    btnCarouselTheme.addEventListener("click", () => {
      const card = document.getElementById("carousel-deck-card");
      if (card) {
        isCarouselThemeLight = !isCarouselThemeLight;
        card.classList.toggle("theme-light", isCarouselThemeLight);
        showToast(isCarouselThemeLight ? "Carousel: Paper Light theme" : "Carousel: Obsidian Dark theme");
      }
    });
  }

  // 6. ReUI 1-Click Fix Actions Handlers
  initReUIFixActions();

  // 7. Media Studio Controls
  initInspectorMediaControls();

  // 8. Brand Identity & Live Watermark Canvas Controls
  initInspectorBrandControls();

  // 9. Skiper UI Natural Language Copilot Controls
  initInspectorCopilotControls();
}

function updateStageDisplay() {
  const mobileFrame = document.getElementById("sim-device-frame");
  const desktopFrame = document.getElementById("sim-desktop-frame");
  const carouselFrame = document.getElementById("sim-carousel-frame");

  if (mobileFrame) mobileFrame.style.display = currentStageMode === "mobile" ? "block" : "none";
  if (desktopFrame) desktopFrame.style.display = currentStageMode === "desktop" ? "block" : "none";
  if (carouselFrame) carouselFrame.style.display = currentStageMode === "carousel" ? "flex" : "none";

  const editor = document.getElementById("post-editor-input");
  const text = editor ? editor.value : "";

  if (currentStageMode === "desktop") {
    syncDesktopPostFrame(text);
  } else if (currentStageMode === "carousel") {
    buildCarouselDeck(text);
  }
}

function syncDesktopPostFrame(text) {
  const desktopBody = document.getElementById("sim-desktop-body");
  const desktopMedia = document.getElementById("sim-desktop-media");
  const authorName = document.getElementById("sim-desktop-name");
  const authorEyebrow = document.getElementById("sim-desktop-author-eyebrow");
  const authorHeadline = document.getElementById("sim-desktop-headline");
  const authorAvatar = document.getElementById("sim-desktop-avatar");

  if (desktopBody) {
    desktopBody.innerText = text.trim() || "Type in the composer to view your desktop feed post...";
  }

  if (authorName && cachedCreatorProfile) authorName.innerText = cachedCreatorProfile.name || "Dharmik Shingala";
  if (authorEyebrow && cachedCreatorProfile) authorEyebrow.innerText = cachedCreatorProfile.name || "Dharmik Shingala";
  if (authorHeadline && cachedCreatorProfile) authorHeadline.innerText = cachedCreatorProfile.headline || "AI Systems Engineer & Full-Stack Architect";
  if (authorAvatar && cachedCreatorProfile) {
    const initials = (cachedCreatorProfile.name || "DS").split(" ").map(n => n[0]).join("").slice(0, 2).toUpperCase();
    authorAvatar.innerText = initials;
  }

  if (desktopMedia) {
    if (activeMediaUrl) {
      desktopMedia.style.display = "block";
      const isPdf = activeMediaUrl.toLowerCase().endsWith(".pdf") || (activeMediaAsset && (activeMediaAsset.mime_type || "").includes("pdf"));
      const isVideo = activeMediaUrl.toLowerCase().endsWith(".mp4") || activeMediaUrl.toLowerCase().endsWith(".webm") || (activeMediaAsset && (activeMediaAsset.mime_type || "").includes("video"));
      if (isPdf) {
        const title = activeMediaAsset ? activeMediaAsset.file_name : activeMediaUrl.split("/").pop();
        desktopMedia.innerHTML = `
          <div style="background: var(--bg-soft, #1e293b); padding: 16px; border-radius: 6px; border: 1px solid var(--border-soft); display: flex; align-items: center; gap: 12px;">
            <svg class="app-symbol app-symbol-lg app-symbol-no-margin"><use href="#sym-sec-docs"></use></svg>
            <div>
              <div style="font-weight: 600; font-size: 13px; color: var(--text-primary);">${escapeHtml(title)}</div>
              <div style="font-size: 11px; color: var(--text-muted);">PDF Document Carousel • Attached</div>
            </div>
          </div>`;
      } else if (isVideo) {
        desktopMedia.innerHTML = `<video src="${activeMediaUrl}" controls style="width: 100%; border-radius: 6px; max-height: 240px; object-fit: cover;"></video>`;
      } else {
        desktopMedia.innerHTML = `<img src="${activeMediaUrl}" alt="Visual" style="width: 100%; border-radius: 6px; max-height: 240px; object-fit: cover;">`;
      }
    } else {
      desktopMedia.style.display = "none";
      desktopMedia.innerHTML = "";
    }
  }
}

function buildCarouselDeck(text) {
  carouselSlides = [];
  if (!text || !text.trim()) {
    carouselSlides = [
      {
        index: "01",
        headline: "The Architecture Flaw in Production AI",
        body: "Most enterprise AI systems fail not because LLMs are weak, but because context routing and stateful memory are brittle."
      },
      {
        index: "02",
        headline: "Rule 1: Deterministic Gates",
        body: "Never feed raw user inputs directly into probabilistic reasoning without schema normalization and sanitization."
      },
      {
        index: "03",
        headline: "Rule 2: Zero Cloud Egress",
        body: "Run sensitive embeddings and prompt synthesis on local air-gapped runtimes to prevent data leaks."
      },
      {
        index: "04",
        headline: "Takeaway & System Implementation",
        body: "Build reproducible systems with SQLite WAL storage and automated verification contracts."
      }
    ];
  } else {
    // Parse draft by paragraphs or bullet points
    const paragraphs = text.split(/\n\s*\n/).map(p => p.trim()).filter(Boolean);
    if (paragraphs.length >= 2) {
      carouselSlides = paragraphs.slice(0, 6).map((para, idx) => {
        const lines = para.split("\n").filter(Boolean);
        const headline = lines[0].replace(/^[#0-9.\-*]+\s*/, "").slice(0, 65);
        const body = lines.slice(1).join(" ") || lines[0];
        return {
          index: String(idx + 1).padStart(2, "0"),
          headline: idx === 0 ? (headline || "Executive Thesis") : headline,
          body: body || para
        };
      });
    } else {
      // Single paragraph or line by line
      const lines = text.split("\n").map(l => l.trim()).filter(Boolean);
      if (lines.length >= 3) {
        carouselSlides = lines.slice(0, 5).map((line, idx) => ({
          index: String(idx + 1).padStart(2, "0"),
          headline: idx === 0 ? line.slice(0, 60) : `Slide ${idx + 1}`,
          body: line
        }));
      } else {
        carouselSlides = [
          {
            index: "01",
            headline: text.slice(0, 60),
            body: text
          },
          {
            index: "02",
            headline: "Key Takeaway",
            body: "Expand with 2-3 paragraphs in the composer to unlock multi-slide deck generation."
          }
        ];
      }
    }
  }

  currentCarouselIndex = 0;
  renderCurrentCarouselSlide();
}

function renderCurrentCarouselSlide() {
  if (!carouselSlides.length) return;
  const slide = carouselSlides[currentCarouselIndex];
  const slideNum = document.getElementById("carousel-slide-number");
  const slideHeadline = document.getElementById("carousel-slide-headline");
  const slideBody = document.getElementById("carousel-slide-body");
  const slideCounter = document.getElementById("carousel-slide-counter");
  const dotsRow = document.getElementById("carousel-dots-row");
  const handleDisplay = document.getElementById("carousel-deck-brand");

  if (slideNum) slideNum.innerText = slide.index;
  if (slideHeadline) slideHeadline.innerText = slide.headline;
  if (slideBody) slideBody.innerText = slide.body;
  if (slideCounter) slideCounter.innerText = `Slide ${currentCarouselIndex + 1} of ${carouselSlides.length}`;

  const brandHandle = document.getElementById("inspector-brand-handle");
  if (handleDisplay) handleDisplay.innerText = brandHandle ? brandHandle.value : "@dharmik136";

  if (dotsRow) {
    dotsRow.innerHTML = "";
    carouselSlides.forEach((_, idx) => {
      const dot = document.createElement("span");
      dot.className = `carousel-dot ${idx === currentCarouselIndex ? "active" : ""}`;
      dot.addEventListener("click", () => {
        currentCarouselIndex = idx;
        renderCurrentCarouselSlide();
      });
      dotsRow.appendChild(dot);
    });
  }
}

// -------------------------------------------------------------
// ReUI 1-Click Fix Handlers
// -------------------------------------------------------------
function initReUIFixActions() {
  const btnFixEmdash = document.getElementById("btn-fix-emdash");
  const btnFixHook = document.getElementById("btn-fix-hook");
  const btnFixLinks = document.getElementById("btn-fix-links");
  const btnFixBait = document.getElementById("btn-fix-bait");
  const btnFixPacing = document.getElementById("btn-fix-pacing");
  const btnFixHashtag = document.getElementById("btn-fix-hashtag");

  if (btnFixEmdash) {
    btnFixEmdash.addEventListener("click", () => {
      const editor = document.getElementById("post-editor-input");
      if (!editor) return;
      editor.value = editor.value.replace(/[\u2014\u2013]/g, " - ").replace(/\s*-\s*/g, " - ");
      updateStudioState();
      showToast("Zero em-dash law enforced! Clean editorial spacing applied.");
    });
  }

  if (btnFixHook) {
    btnFixHook.addEventListener("click", () => {
      const editor = document.getElementById("post-editor-input");
      if (!editor) return;
      const lines = editor.value.split("\n");
      if (lines.length > 0) {
        let hook = lines[0];
        if (hook.length > 175) {
          let cut = hook.slice(0, 168);
          const lastSpace = cut.lastIndexOf(" ");
          if (lastSpace > 100) cut = cut.slice(0, lastSpace);
          lines[0] = cut.trim() + "...";
          editor.value = lines.join("\n");
          updateStudioState();
          showToast("Hook trimmed to < 170 chars before fold cutoff!");
        }
      }
    });
  }

  if (btnFixLinks) {
    btnFixLinks.addEventListener("click", () => {
      const editor = document.getElementById("post-editor-input");
      if (!editor) return;
      const urlRegex = /(https?:\/\/[^\s]+|www\.[^\s]+)/gi;
      const matches = editor.value.match(urlRegex) || [];
      if (matches.length > 0) {
        editor.value = editor.value.replace(urlRegex, "").replace(/\n\s*\n\s*\n/g, "\n\n").trim();
        editor.value += "\n\n(Full reference links posted in first comment)";
        updateStudioState();
        showToast(`Extracted ${matches.length} link(s) for the first comment.`);
      }
    });
  }

  if (btnFixBait) {
    btnFixBait.addEventListener("click", () => {
      const editor = document.getElementById("post-editor-input");
      if (!editor) return;
      const baitRegex = /(comment\s+['"]?yes['"]?|comment\s+below|type\s+['"]?info['"]?|like\s+and\s+share|tag\s+\d+\s+friends)/gi;
      editor.value = editor.value.replace(baitRegex, "").replace(/\s{2,}/g, " ").trim();
      updateStudioState();
      showToast("Algorithmic bait phrases scrubbed.");
    });
  }

  if (btnFixPacing) {
    btnFixPacing.addEventListener("click", () => {
      const editor = document.getElementById("post-editor-input");
      if (!editor) return;
      const paragraphs = editor.value.split(/\n\s*\n/);
      const reformatted = paragraphs.map(p => {
        const sentences = p.split(/(?<=[.?!])\s+/);
        const groups = [];
        for (let i = 0; i < sentences.length; i += 2) {
          groups.push(sentences.slice(i, i + 2).join(" "));
        }
        return groups.join("\n\n");
      }).join("\n\n");
      editor.value = reformatted;
      updateStudioState();
      showToast("High-dwell 2-line cadence rhythm formatted.");
    });
  }

  if (btnFixHashtag) {
    btnFixHashtag.addEventListener("click", () => {
      const editor = document.getElementById("post-editor-input");
      if (!editor) return;
      const tags = editor.value.match(/#[a-zA-Z0-9_]+/g) || [];
      if (tags.length > 3) {
        const toDrop = tags.slice(3);
        let val = editor.value;
        toDrop.forEach(t => { val = val.replace(t, ""); });
        editor.value = val.replace(/\s{2,}/g, " ").trim();
        updateStudioState();
        showToast("Hashtags trimmed to 3 focused keywords.");
      }
    });
  }
}

// -------------------------------------------------------------
// Media Studio Controls in Drawer
// -------------------------------------------------------------
function initInspectorMediaControls() {
  const ratioBtns = document.querySelectorAll(".ratio-btn");
  ratioBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      ratioBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const ratio = btn.getAttribute("data-ratio") || "1:1";
      const simMedia = document.getElementById("simulated-media-container");
      if (simMedia) {
        if (ratio === "1:1") simMedia.style.aspectRatio = "1 / 1";
        else if (ratio === "4:5") simMedia.style.aspectRatio = "4 / 5";
        else if (ratio === "16:9") simMedia.style.aspectRatio = "16 / 9";
      }
      showToast(`Visual Aspect Ratio Preset: ${ratio}`);
    });
  });

  const stylePills = document.querySelectorAll(".visual-style-pills .style-pill");
  stylePills.forEach(pill => {
    pill.addEventListener("click", () => {
      stylePills.forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
    });
  });

  const btnSynthesizePrompt = document.getElementById("btn-inspector-synthesize-prompt");
  if (btnSynthesizePrompt) {
    btnSynthesizePrompt.addEventListener("click", () => {
      const editor = document.getElementById("post-editor-input");
      const draft = editor ? editor.value.trim() : "";
      const promptField = document.getElementById("inspector-img-prompt");
      const activePill = document.querySelector(".visual-style-pills .style-pill.active");
      const style = activePill ? activePill.getAttribute("data-style") : "photorealistic";
      if (promptField) {
        const snippet = draft.slice(0, 110).replace(/[^a-zA-Z0-9\s]/g, " ").trim();
        promptField.value = `High-end editorial ${style} scene: ${snippet || "Enterprise systems engineering and cloud infrastructure"}, dark obsidian palette with terracotta accent highlights, sharp depth of field, 8k resolution`;
        showToast("Visual prompt synthesized from post context!");
      }
    });
  }

  const btnGenerateImage = document.getElementById("btn-inspector-generate-image");
  if (btnGenerateImage) {
    btnGenerateImage.addEventListener("click", () => {
      openImageStudio();
    });
  }

  const dropzone = document.getElementById("inspector-quick-dropzone");
  const dropzoneBrowse = document.getElementById("inspector-dropzone-browse");
  const fileInput = document.getElementById("media-file-input");

  if (dropzone && fileInput) {
    dropzone.addEventListener("click", (e) => {
      if (e.target !== dropzoneBrowse) fileInput.click();
    });
    if (dropzoneBrowse) {
      dropzoneBrowse.addEventListener("click", (e) => {
        e.preventDefault();
        fileInput.click();
      });
    }
    dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropzone.classList.add("drag-over");
    });
    dropzone.addEventListener("dragleave", () => {
      dropzone.classList.remove("drag-over");
    });
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("drag-over");
      if (e.dataTransfer && e.dataTransfer.files.length > 0) {
        uploadMediaFile(e.dataTransfer.files[0]);
      }
    });
  }

  const btnRemoveMedia = document.getElementById("inspector-media-remove");
  if (btnRemoveMedia) {
    btnRemoveMedia.addEventListener("click", () => {
      activeMediaUrl = "";
      activeMediaAsset = null;
      updateStudioState();
      syncInspectorMediaCard();
      showToast("Media removed from post.");
    });
  }
}

function syncInspectorMediaCard() {
  const thumb = document.getElementById("inspector-media-thumb");
  const nameEl = document.getElementById("inspector-media-name");
  const metaEl = document.getElementById("inspector-media-meta");
  const badgeEl = document.getElementById("inspector-media-badge");
  const removeBtn = document.getElementById("inspector-media-remove");

  if (activeMediaUrl) {
    const isPdf = activeMediaUrl.toLowerCase().endsWith(".pdf") || (activeMediaAsset && (activeMediaAsset.mime_type || "").includes("pdf"));
    const isVideo = activeMediaUrl.toLowerCase().endsWith(".mp4") || activeMediaUrl.toLowerCase().endsWith(".webm") || (activeMediaAsset && (activeMediaAsset.mime_type || "").includes("video"));

    if (thumb) {
      if (isPdf) {
        thumb.innerHTML = '<svg class="app-symbol app-symbol-md app-symbol-no-margin"><use href="#sym-sec-docs"></use></svg>';
      } else if (isVideo) {
        thumb.innerHTML = '<svg class="app-symbol app-symbol-md app-symbol-no-margin"><use href="#sym-mode-media"></use></svg>';
      } else {
        thumb.innerHTML = `<img src="${activeMediaUrl}" alt="Media" style="width: 100%; height: 100%; object-fit: cover;">`;
      }
    }
    if (nameEl) nameEl.innerText = activeMediaAsset ? activeMediaAsset.file_name : activeMediaUrl.split("/").pop();
    if (metaEl) {
      const sizeVal = activeMediaAsset ? (activeMediaAsset.file_size || activeMediaAsset.size_bytes || 0) : 0;
      metaEl.innerText = sizeVal ? `${formatBytes(sizeVal)} • Ready` : "Attached to post";
    }
    if (badgeEl) {
      badgeEl.innerText = isPdf ? "CAROUSEL" : (isVideo ? "VIDEO" : "ATTACHED");
      badgeEl.className = "sidebar-badge pro";
    }
    if (removeBtn) removeBtn.style.display = "inline-flex";
  } else {
    if (thumb) thumb.innerHTML = '<svg class="app-symbol app-symbol-md app-symbol-no-margin"><use href="#sym-mode-media"></use></svg>';
    if (nameEl) nameEl.innerText = "No visual attached";
    if (metaEl) metaEl.innerText = "Drop an image, PDF or video";
    if (badgeEl) {
      badgeEl.innerText = "NONE";
      badgeEl.className = "sidebar-badge neutral";
    }
    if (removeBtn) removeBtn.style.display = "none";
  }
}

// -------------------------------------------------------------
// Brand Studio & Live Watermark Canvas Controls
// -------------------------------------------------------------
function initInspectorBrandControls() {
  const handleInput = document.getElementById("inspector-brand-handle");
  const watermarkToggle = document.getElementById("inspector-watermark-toggle");
  const cornerBtns = document.querySelectorAll("#inspector-corner-picker .corner-btn");
  const styleChips = document.querySelectorAll("#inspector-style-chips .watermark-chip");

  if (handleInput) {
    handleInput.addEventListener("input", () => {
      syncBrandWatermarkCanvas();
      const carouselHandle = document.getElementById("carousel-deck-brand");
      if (carouselHandle) carouselHandle.innerText = handleInput.value.trim() || "@dharmik136";
    });
  }

  if (watermarkToggle) {
    watermarkToggle.addEventListener("change", () => {
      const badge = document.getElementById("inspector-live-watermark-badge");
      if (badge) badge.style.display = watermarkToggle.checked ? "flex" : "none";
    });
  }

  cornerBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      cornerBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      syncBrandWatermarkCanvas();
    });
  });

  styleChips.forEach(chip => {
    chip.addEventListener("click", () => {
      styleChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      syncBrandWatermarkCanvas();
    });
  });
}

function syncBrandWatermarkCanvas() {
  const badge = document.getElementById("inspector-live-watermark-badge");
  const badgeText = document.getElementById("inspector-live-watermark-text");
  const handleInput = document.getElementById("inspector-brand-handle");
  const activeCorner = document.querySelector("#inspector-corner-picker .corner-btn.active");
  const activeStyle = document.querySelector("#inspector-style-chips .watermark-chip.active");

  if (!badge) return;

  const handle = handleInput ? handleInput.value.trim() : "@dharmik136";
  if (badgeText) badgeText.innerText = handle || "@dharmik136";

  const pos = activeCorner ? activeCorner.getAttribute("data-pos") : "bottom_right";
  badge.classList.remove("pos-bottom-right", "pos-bottom-left", "pos-top-right", "pos-top-left");
  if (pos === "top_left") badge.classList.add("pos-top-left");
  else if (pos === "top_right") badge.classList.add("pos-top-right");
  else if (pos === "bottom_left") badge.classList.add("pos-bottom-left");
  else badge.classList.add("pos-bottom-right");

  const style = activeStyle ? activeStyle.getAttribute("data-style") : "glass_pill";
  badge.classList.remove("style-glass-pill", "style-minimal-text", "style-accent-badge");
  if (style === "minimal_text") badge.classList.add("style-minimal-text");
  else if (style === "accent_badge") badge.classList.add("style-accent-badge");
  else badge.classList.add("style-glass-pill");
}

// -------------------------------------------------------------
// Skiper UI Copilot Controls
// -------------------------------------------------------------
function initInspectorCopilotControls() {
  const chips = document.querySelectorAll(".copilot-action-chips .copilot-chip");
  const promptInput = document.getElementById("inspector-prompt-input");
  const runBtn = document.getElementById("btn-inspector-run-prompt");
  const outputCard = document.getElementById("inspector-copilot-output-card");
  const outputText = document.getElementById("inspector-copilot-output-text");
  const applyBtn = document.getElementById("btn-inspector-apply-prompt");
  const copyBtn = document.getElementById("btn-inspector-copy-prompt");
  const closeOutputBtn = document.getElementById("btn-inspector-close-output");

  chips.forEach(chip => {
    chip.addEventListener("click", () => {
      const p = chip.getAttribute("data-prompt");
      if (promptInput && p) {
        promptInput.value = p;
        promptInput.focus();
      }
    });
  });

  if (runBtn) {
    runBtn.addEventListener("click", async () => {
      const cmd = promptInput ? promptInput.value.trim() : "";
      if (!cmd) {
        showToast("Please enter an instruction or pick a prompt chip.");
        return;
      }
      const editor = document.getElementById("post-editor-input");
      const draft = editor ? editor.value : "";
      runBtn.disabled = true;
      runBtn.innerText = "Running AI Copilot...";

      try {
        const res = await fetch(`${API_BASE}/ai/command`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            command: cmd,
            context: draft
          })
        });
        const json = await res.json();
        if (json.output) {
          if (outputText) outputText.innerText = json.output;
          if (outputCard) outputCard.style.display = "flex";
          showToast("AI Copilot response ready.");
        } else {
          showToast("No response generated.");
        }
      } catch (err) {
        showToast("Error executing copilot: " + err.message);
      } finally {
        runBtn.disabled = false;
        runBtn.innerHTML = '<svg class="app-symbol"><use href="#sym-sec-ai-command"></use></svg> Execute Copilot Instruction';
      }
    });
  }

  if (applyBtn) {
    applyBtn.addEventListener("click", () => {
      const editor = document.getElementById("post-editor-input");
      if (editor && outputText && outputText.innerText) {
        editor.value = outputText.innerText;
        updateStudioState();
        showToast("Applied copilot output directly into Composer.");
        if (outputCard) outputCard.style.display = "none";
      }
    });
  }

  if (copyBtn) {
    copyBtn.addEventListener("click", () => {
      if (outputText && outputText.innerText) {
        navigator.clipboard.writeText(outputText.innerText);
        showToast("Copilot result copied to clipboard.");
      }
    });
  }

  if (closeOutputBtn) {
    closeOutputBtn.addEventListener("click", () => {
      if (outputCard) outputCard.style.display = "none";
    });
  }
}

// -------------------------------------------------------------
// 1.C: CENTERED COMMAND PALETTE (Section 5.B: Cmd+K / Ctrl+K)
// -------------------------------------------------------------
function initCommandPalette() {
  const modal = document.getElementById("command-palette-modal");
  const input = document.getElementById("cmd-palette-input");
  const triggerBtn = document.getElementById("btn-trigger-cmd-palette");
  const items = document.querySelectorAll(".command-palette-item");

  function openPalette() {
    if (!modal) return;
    modal.classList.add("active");
    if (input) {
      input.value = "";
      input.focus();
      filterItems("");
    }
  }

  function closePalette() {
    if (!modal) return;
    modal.classList.remove("active");
  }

  if (triggerBtn) {
    triggerBtn.addEventListener("click", openPalette);
  }

  if (modal) {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) closePalette();
    });
  }

  window.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      if (modal && modal.classList.contains("active")) {
        closePalette();
      } else {
        openPalette();
      }
    } else if (e.key === "Escape" && modal && modal.classList.contains("active")) {
      closePalette();
    }
  });

  if (input) {
    input.addEventListener("input", () => {
      filterItems(input.value.trim().toLowerCase());
    });
  }

  function filterItems(query) {
    items.forEach(item => {
      const text = item.textContent.toLowerCase();
      item.style.display = (!query || text.includes(query)) ? "flex" : "none";
    });
  }

  items.forEach(item => {
    item.addEventListener("click", () => {
      const action = item.getAttribute("data-action");
      const nav = item.getAttribute("data-nav");
      closePalette();

      if (nav) {
        switchTab(nav);
      } else if (action === "generate-hooks") {
        const btn = document.getElementById("btn-trigger-rehook");
        if (btn) btn.click();
      } else if (action === "clean-formatting") {
        const btn = document.getElementById("btn-clean-formatting");
        if (btn) btn.click();
      } else if (action === "open-image-studio") {
        openImageStudio();
      } else if (action === "save-draft") {
        const btn = document.getElementById("btn-save-draft");
        if (btn) btn.click();
      } else if (action === "toggle-theme") {
        const btn = document.getElementById("btn-theme-toggle");
        if (btn) btn.click();
      } else if (action === "toggle-inspector") {
        const btn = document.getElementById("btn-toggle-inspector");
        if (btn) btn.click();
      }
    });
  });
}

// -------------------------------------------------------------
// 1.D: AI COMMAND ORB & FLOATING DOCK (Section 8)
// -------------------------------------------------------------
function initAICommandDock() {
  const orb = document.getElementById("ai-command-orb");
  const dock = document.getElementById("ai-floating-dock");
  const closeBtn = document.getElementById("btn-close-ai-dock");
  const executeBtn = document.getElementById("btn-dock-execute");
  const dockInput = document.getElementById("ai-dock-input");
  const chips = document.querySelectorAll(".ai-action-chip");

  if (orb && dock) {
    orb.addEventListener("click", () => {
      dock.classList.toggle("active");
      if (dock.classList.contains("active") && dockInput) {
        dockInput.focus();
      }
    });
  }

  if (closeBtn && dock) {
    closeBtn.addEventListener("click", () => {
      dock.classList.remove("active");
    });
  }

  chips.forEach(chip => {
    chip.addEventListener("click", () => {
      const action = chip.getAttribute("data-action");
      if (dockInput) {
        dockInput.value = action;
        executeDockCommand(action);
      }
    });
  });

  if (executeBtn) {
    executeBtn.addEventListener("click", () => {
      const cmd = dockInput ? dockInput.value.trim() : "";
      if (cmd) executeDockCommand(cmd);
    });
  }

  async function executeDockCommand(cmd) {
    if (!cmd) return;
    executeBtn.disabled = true;
    executeBtn.innerText = "Executing...";
    try {
      const draft = document.getElementById("post-editor-input").value;
      const res = await fetch(`${API_BASE}/ai/command`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: cmd, context: draft })
      });
      const json = await res.json();
      if (json.output) {
        document.getElementById("post-editor-input").value = json.output;
        updateStudioState();
        showToast("AI rewrite applied directly to Composer.");
        if (dock) dock.classList.remove("active");
      }
    } catch (err) {
      showToast("Command error: " + err.message);
    } finally {
      executeBtn.disabled = false;
      executeBtn.innerText = "Execute";
    }
  }
}

// -------------------------------------------------------------
// 1.E: CURSOR-AWARE BUTTONS (Section 16.2)
// -------------------------------------------------------------
function initCursorAwareButtons() {
  document.querySelectorAll(".btn").forEach(btn => {
    btn.addEventListener("mousemove", (e) => {
      const rect = btn.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      btn.style.setProperty("--cursor-x", `${x}px`);
      btn.style.setProperty("--cursor-y", `${y}px`);
    });
  });
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

function toUnicodeSerifBold(text) {
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const code = text.charCodeAt(i);
    if (code >= 65 && code <= 90) {
      out += String.fromCodePoint(0x1D400 + code - 65);
    } else if (code >= 97 && code <= 122) {
      out += String.fromCodePoint(0x1D41A + code - 97);
    } else if (code >= 48 && code <= 57) {
      out += String.fromCodePoint(0x1D7CE + code - 48);
    } else {
      out += text[i];
    }
  }
  return out;
}

function toUnicodeSerifItalic(text) {
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const code = text.charCodeAt(i);
    if (code >= 65 && code <= 90) {
      out += String.fromCodePoint(0x1D434 + code - 65);
    } else if (text[i] === 'h') {
      out += '\u210E';
    } else if (code >= 97 && code <= 122) {
      out += String.fromCodePoint(0x1D44E + code - 97);
    } else {
      out += text[i];
    }
  }
  return out;
}

function toUnicodeBlackboard(text) {
  const specialCaps = {
    'C': '\u2102', 'H': '\u210D', 'N': '\u2115', 'P': '\u2119',
    'Q': '\u211A', 'R': '\u211D', 'Z': '\u2124'
  };
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    const code = text.charCodeAt(i);
    if (specialCaps[char]) {
      out += specialCaps[char];
    } else if (code >= 65 && code <= 90) {
      out += String.fromCodePoint(0x1D538 + code - 65);
    } else if (code >= 97 && code <= 122) {
      out += String.fromCodePoint(0x1D552 + code - 97);
    } else if (code >= 48 && code <= 57) {
      out += String.fromCodePoint(0x1D7D8 + code - 48);
    } else {
      out += char;
    }
  }
  return out;
}

function toUnicodeUnderline(text) {
  return text.split('').map(c => c !== '\n' ? c + '\u0332' : c).join('');
}

function toUnicodeCircledNumbers(text) {
  const circledMap = {
    '0': '\u24FF', '1': '\u2776', '2': '\u2777', '3': '\u2778', '4': '\u2779',
    '5': '\u277A', '6': '\u277B', '7': '\u277C', '8': '\u277D', '9': '\u277E'
  };
  return text.split('').map(c => circledMap[c] || c).join('');
}

function calculateClientDwellMetrics(text) {
  if (!text || !text.trim()) {
    return { readingSec: "0.0", dwellBadge: "0.0s [EMPTY]", dwellClass: "dwell-badge" };
  }
  const words = text.trim().split(/\s+/);
  const wordCount = words.length;
  const paragraphs = text.split('\n\n').filter(p => p.trim());
  const breaks = Math.max(0, paragraphs.length - 1);
  const readingSec = ((wordCount / 220.0) * 60.0 + (breaks * 0.8)).toFixed(1);

  if (readingSec < 8.0) {
    return { readingSec, dwellBadge: `${readingSec}s [FAST HOOK]`, dwellClass: "dwell-badge warning" };
  } else if (readingSec <= 22.0) {
    return { readingSec, dwellBadge: `${readingSec}s [OPTIMAL DWELL]`, dwellClass: "dwell-badge optimal" };
  } else {
    return { readingSec, dwellBadge: `${readingSec}s [DEEP AUTHORITY]`, dwellClass: "dwell-badge deep" };
  }
}

function cleanEmDashes(text) {
  let cleaned = text.replace(/\u2014/g, ", ").replace(/\u2013/g, ", ");
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
  const seeLessBtn = document.getElementById("simulated-see-less");
  const btnToggleEditorFold = document.getElementById("btn-toggle-editor-fold");
  const btnToggleSimGuide = document.getElementById("btn-toggle-sim-guide");
  const editorFoldStatusText = document.getElementById("editor-fold-status-text");

  if (editorFoldStatusText) {
    editorFoldStatusText.innerText = isEditorFoldLineEnabled ? "ON" : "OFF";
  }

  if (btnToggleSimGuide && isSimGuideEnabled) {
    btnToggleSimGuide.classList.add("active");
  }

  // Restore the user's own most recent DRAFT first, then fall back to the next
  // scheduled post.
  //
  // This previously queried only status=scheduled. A saved draft has
  // status=draft, so it was never returned, and the editor would open showing a
  // different seeded post instead. The draft was safe in the database the whole
  // time, but to the user it looked like their work had been thrown away and
  // replaced with someone else's.
  const restoreInto = (post) => {
    if (!post || textarea.value) return false;
    currentDraftId = post.id;
    textarea.value = post.content;
    if (post.media_urls && post.media_urls.length) {
      const url = post.media_urls[0];
      setAttachedMedia({
        file_url: url,
        file_name: url.split("/").pop(),
        mime_type: url.toLowerCase().endsWith(".pdf") ? "application/pdf" : (url.toLowerCase().endsWith(".mp4") || url.toLowerCase().endsWith(".webm") ? "video/mp4" : "image/jpeg")
      });
    } else {
      updateStudioState();
    }
    return true;
  };

  fetch(`${API_BASE}/posts?status=draft`)
    .then(r => r.json())
    .then(data => {
      const drafts = (data && data.posts) || [];
      // The API orders ascending by scheduled_for or created_at, so the most
      // recently written draft is the last element, not the first.
      if (restoreInto(drafts[drafts.length - 1])) return null;
      return fetch(`${API_BASE}/posts?status=scheduled`).then(r => r.json());
    })
    .then(data => {
      if (!data) return;
      restoreInto(data.posts && data.posts[0]);
    })
    .catch(() => {});

  textarea.addEventListener("input", updateStudioState);
  mediaInput.addEventListener("input", updateStudioState);

  // Sync editor fold line when user scrolls or resizes window
  textarea.addEventListener("scroll", updateEditorFoldLinePosition);
  window.addEventListener("resize", updateEditorFoldLinePosition);

  // Toggle "...see more" in mobile simulator (expand to full post)
  if (seeMoreBtn) {
    seeMoreBtn.addEventListener("click", () => {
      isSeeMoreExpanded = true;
      updateStudioState();
    });
  }

  // Toggle "...see less" in mobile simulator (collapse back to fold)
  if (seeLessBtn) {
    seeLessBtn.addEventListener("click", () => {
      isSeeMoreExpanded = false;
      updateStudioState();
    });
  }

  // Toggle editor fold guideline
  if (btnToggleEditorFold) {
    btnToggleEditorFold.addEventListener("click", () => {
      isEditorFoldLineEnabled = !isEditorFoldLineEnabled;
      localStorage.setItem("linkedin_editor_fold_line", isEditorFoldLineEnabled ? "true" : "false");
      if (editorFoldStatusText) {
        editorFoldStatusText.innerText = isEditorFoldLineEnabled ? "ON" : "OFF";
      }
      updateEditorFoldLinePosition();
      showToast(isEditorFoldLineEnabled ? "In-editor fold guideline enabled" : "In-editor fold guideline hidden (distraction-free mode)");
    });
  }

  // Toggle simulator fold guide marker
  if (btnToggleSimGuide) {
    btnToggleSimGuide.addEventListener("click", () => {
      isSimGuideEnabled = !isSimGuideEnabled;
      localStorage.setItem("linkedin_sim_guide", isSimGuideEnabled ? "true" : "false");
      btnToggleSimGuide.classList.toggle("active", isSimGuideEnabled);
      updateStudioState();
      showToast(isSimGuideEnabled ? "Simulator fold marker guide enabled" : "Simulator fold marker hidden (clean reader view)");
    });
  }

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
    btnSchedule.addEventListener("click", () => {
      openScheduleModal();
    });
  }

  // AI Image Studio Trigger
  const openImageStudioBtn = document.getElementById("btn-open-image-studio");
  if (openImageStudioBtn) {
    openImageStudioBtn.addEventListener("click", () => {
      openImageStudio();
    });
  }
}

async function saveCurrentDraft(status = "draft", scheduledFor = null) {
  if (isSavingPost) return;
  const editorInput = document.getElementById("post-editor-input");
  const content = editorInput ? editorInput.value.trim() : "";
  const mediaInput = document.getElementById("media-path-input");
  const mediaUrl = mediaInput ? mediaInput.value.trim() : (activeMediaUrl || "");
  if (!content) {
    showToast("Cannot save an empty post.");
    return;
  }

  isSavingPost = true;
  try {
    const payload = {
      content,
      media_urls: mediaUrl ? [mediaUrl] : [],
      status,
      scheduled_for: scheduledFor
    };

    let savedSuccessfully = false;

    if (currentDraftId) {
      const res = await fetch(`${API_BASE}/posts/${currentDraftId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        savedSuccessfully = true;
      } else if (res.status === 404) {
        // ID not found in database, fallback to create new post below
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(`Save failed: ${err.detail || "Validation error"}`);
        return;
      }
    }

    if (!savedSuccessfully) {
      const createRes = await fetch(`${API_BASE}/posts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (createRes.ok) {
        const createdData = await createRes.json();
        if (createdData && createdData.id) {
          currentDraftId = createdData.id;
        }
        savedSuccessfully = true;
      } else {
        const err = await createRes.json().catch(() => ({}));
        showToast(`Save failed: ${err.detail || "Could not save post"}`);
        return;
      }
    }

    if (savedSuccessfully) {
      if (content.length > 3000) {
        showToast(status === "scheduled" ? "Warning: Exceeds 3,000 chars! Post scheduled locally." : "Warning: Exceeds 3,000 chars! Draft saved locally.");
      } else {
        showToast(status === "scheduled" ? "Post scheduled successfully!" : "Draft saved to local database.");
      }
      const savedInd = document.getElementById("saved-status-indicator");
      if (savedInd) {
        savedInd.innerText = `SAVED ${new Date().toTimeString().slice(0, 8)}`;
      }
    }
  } catch (e) {
    showToast("Failed to save post: " + e.message);
  } finally {
    isSavingPost = false;
  }
}

// -------------------------------------------------------------
// 4. THE DYNAMIC FOLD LINE & HOOK INTELLIGENCE ENGINE
// -------------------------------------------------------------
function updateEditorFoldLinePosition() {
  const foldLineEl = document.getElementById("editor-fold-line");
  const foldCharBadge = document.getElementById("fold-char-badge");
  const textarea = document.getElementById("post-editor-input");
  if (!foldLineEl || !textarea) return;

  if (!isEditorFoldLineEnabled || !textarea.value.trim()) {
    foldLineEl.style.display = "none";
    return;
  }

  // Compute pre-fold text
  const text = textarea.value;
  const lines = text.split("\n");
  let preFoldText = "";
  if (lines.length > 3) {
    preFoldText = lines.slice(0, 3).join("\n");
  } else if (text.length > 140) {
    const spaceIdx = text.lastIndexOf(" ", 138);
    const cutPos = spaceIdx > 80 ? spaceIdx : 140;
    preFoldText = text.slice(0, cutPos);
  } else {
    // Whole text is pre-fold, no fold cutoff needed
    foldLineEl.style.display = "none";
    return;
  }

  // Section 16.5: Fold crossing pulse animation
  if (preFoldText.length >= 140 && !foldLineEl.classList.contains("pulse")) {
    foldLineEl.classList.add("pulse");
    setTimeout(() => foldLineEl.classList.remove("pulse"), 600);
  }

  // Measure pixel height of preFoldText using mirror element
  let mirror = document.getElementById("editor-measuring-mirror");
  if (!mirror) {
    mirror = document.createElement("div");
    mirror.id = "editor-measuring-mirror";
    mirror.style.cssText = "position:absolute; visibility:hidden; pointer-events:none; white-space:pre-wrap; word-break:break-word; box-sizing:border-box; font-family:'Inter', sans-serif; font-size:18px; line-height:1.75; padding:8px 0; top:0; left:0;";
    document.body.appendChild(mirror);
  }
  mirror.style.width = `${textarea.clientWidth}px`;
  mirror.innerText = preFoldText;

  const measuredHeight = mirror.offsetHeight;
  const targetTop = measuredHeight - textarea.scrollTop;

  // Only display if within visible textarea bounds
  if (targetTop > 20 && targetTop < textarea.clientHeight - 10) {
    foldLineEl.style.display = "flex";
    foldLineEl.style.top = `${targetTop}px`;
    if (foldCharBadge) {
      foldCharBadge.innerText = `Pre-Fold: ${preFoldText.length} chars`;
    }
  } else {
    // Scrolled out of view - NEVER stay frozen on the screen
    foldLineEl.style.display = "none";
  }
}

function updateStudioState() {
  const textarea = document.getElementById("post-editor-input");
  const mediaInput = document.getElementById("media-path-input");
  const text = textarea.value;
  const mediaUrl = mediaInput.value.trim();

  // 1. Character & Word Metrics
  const charCount = text.length;
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  const estDwellSeconds = Math.max(10, Math.round((words / 210) * 60) + (text.split("\n\n").length * 3));

  const topCharCount = document.getElementById("top-char-count");
  if (topCharCount) {
    topCharCount.innerText = charCount.toLocaleString();
    if (charCount > 3000) {
      topCharCount.style.color = "#ef4444";
      topCharCount.title = "Exceeds LinkedIn 3,000 character limit";
    } else {
      topCharCount.style.color = "";
      topCharCount.title = "";
    }
  }

  const dwellDisplay = document.getElementById("dwell-display");
  if (dwellDisplay) dwellDisplay.innerText = `~${estDwellSeconds}s`;

  const topDwellTime = document.getElementById("top-dwell-time");
  if (topDwellTime) topDwellTime.innerText = `${estDwellSeconds}s`;

  const dwellBadgeElem = document.getElementById("editor-dwell-badge");
  if (dwellBadgeElem) {
    const dwellMetrics = calculateClientDwellMetrics(text);
    dwellBadgeElem.innerText = dwellMetrics.dwellBadge;
    dwellBadgeElem.className = dwellMetrics.dwellClass;
  }

  // 2. Compute Pre-Fold Cutoff for LinkedIn Mobile Feed (Project Prudent Day 05 Physics)
  // Mobile LinkedIn feed truncates at ~140 characters OR at 3 lines, whichever occurs first.
  let preFoldText = "";
  let postFoldText = "";
  const lines = text.split("\n");

  if (lines.length > 3) {
    preFoldText = lines.slice(0, 3).join("\n");
    postFoldText = lines.slice(3).join("\n");
  } else if (text.length > 140) {
    const spaceIdx = text.lastIndexOf(" ", 138);
    const cutPos = spaceIdx > 80 ? spaceIdx : 140;
    preFoldText = text.slice(0, cutPos);
    postFoldText = text.slice(cutPos);
  } else {
    preFoldText = text;
    postFoldText = "";
  }

  const preFoldChars = preFoldText.length;
  const isHookSafe = preFoldChars <= 140;
  const hasAirGap = lines.length >= 2 && lines[1].trim() === "";

  // Update Topbar and Editor Hook Status Bar
  const topHookCount = document.getElementById("top-hook-count");
  if (topHookCount) topHookCount.innerText = preFoldChars;

  const editorHookChars = document.getElementById("editor-hook-chars");
  if (editorHookChars) editorHookChars.innerText = preFoldChars;

  const editorHookBadge = document.getElementById("editor-hook-badge");
  if (editorHookBadge) {
    if (isHookSafe && hasAirGap) {
      editorHookBadge.innerText = "Fold Safe (140c)";
      editorHookBadge.className = "sidebar-badge pro";
    } else if (!isHookSafe) {
      editorHookBadge.innerText = `Past Fold (${preFoldChars}c)`;
      editorHookBadge.className = "sidebar-badge count";
    } else {
      editorHookBadge.innerText = "Missing Air Gap";
      editorHookBadge.className = "sidebar-badge warning";
    }
  }

  const editorHookDesc = document.getElementById("editor-hook-desc");
  if (editorHookDesc) {
    if (isHookSafe && hasAirGap) {
      editorHookDesc.innerText = "• 100% of hook visible before '...see more' cutoff on iOS & Android";
    } else if (!isHookSafe) {
      editorHookDesc.innerText = `• ${preFoldChars - 140} characters exceed the 140-char mobile cutoff`;
    } else {
      editorHookDesc.innerText = "• Add an empty line break after line 1 to eliminate mobile reader fatigue";
    }
  }

  // 3. Update Scroll-Synced In-Editor Fold Line
  updateEditorFoldLinePosition();

  // 4. Update Mobile Feed Simulator
  const simAboveFold = document.getElementById("simulated-above-fold");
  const simBelowFold = document.getElementById("simulated-below-fold");
  const simSeeMore = document.getElementById("simulated-see-more");
  const simSeeLessWrapper = document.getElementById("sim-see-less-wrapper");
  const simFoldMarker = document.getElementById("sim-fold-marker");
  const simFoldStatus = document.getElementById("sim-fold-status");
  const simFoldDot = document.getElementById("sim-fold-dot");

  if (simBelowFold) simBelowFold.style.display = "none";

  if (simFoldStatus) {
    if (!text.trim()) {
      simFoldStatus.innerText = "Empty Draft";
      if (simFoldDot) simFoldDot.className = "status-indicator-dot";
    } else if (postFoldText.trim().length === 0) {
      simFoldStatus.innerText = "Pre-Fold Only";
      if (simFoldDot) simFoldDot.className = "status-indicator-dot";
    } else {
      simFoldStatus.innerText = isHookSafe ? "Fold Safe (< 180 chars)" : `Fold Dense (${preFoldChars} chars)`;
      if (simFoldDot) {
        simFoldDot.className = isHookSafe ? "status-indicator-dot" : "status-indicator-dot warning";
      }
    }
  }

  // Update mobile author info if profile is populated
  if (cachedCreatorProfile) {
    const mobName = document.getElementById("sim-mobile-author-name");
    const mobHead = document.getElementById("sim-mobile-headline");
    const mobAvatar = document.getElementById("sim-mobile-avatar");
    if (mobName && cachedCreatorProfile.name) mobName.innerText = cachedCreatorProfile.name;
    if (mobHead && cachedCreatorProfile.headline) mobHead.innerText = cachedCreatorProfile.headline;
    if (mobAvatar && cachedCreatorProfile.name) {
      mobAvatar.innerText = cachedCreatorProfile.name.split(" ").map(n => n[0]).join("").slice(0, 2).toUpperCase();
    }
  }

  if (simAboveFold) {
    if (!text.trim()) {
      simAboveFold.innerText = "Type in the editor to see your live preview...";
      if (simSeeMore) simSeeMore.style.display = "none";
      if (simSeeLessWrapper) simSeeLessWrapper.style.display = "none";
      if (simFoldMarker) simFoldMarker.style.display = "none";
    } else if (postFoldText.trim().length === 0) {
      // Short post - no fold cutoff exists
      simAboveFold.innerText = text;
      if (simSeeMore) simSeeMore.style.display = "none";
      if (simSeeLessWrapper) simSeeLessWrapper.style.display = "none";
      if (simFoldMarker) simFoldMarker.style.display = "none";
    } else if (!isSeeMoreExpanded) {
      // Collapsed / Truncated Reader View
      simAboveFold.innerText = preFoldText;
      if (simSeeMore) {
        simSeeMore.style.display = "inline-block";
        simSeeMore.innerText = "...see more";
      }
      if (simSeeLessWrapper) simSeeLessWrapper.style.display = "none";
      if (simFoldMarker) {
        simFoldMarker.style.display = isSimGuideEnabled ? "flex" : "none";
      }
    } else {
      // Full Continuous Expanded View (Never severed with stuck markers!)
      simAboveFold.innerText = text;
      if (simSeeMore) simSeeMore.style.display = "none";
      if (simFoldMarker) simFoldMarker.style.display = "none";
      if (simSeeLessWrapper) simSeeLessWrapper.style.display = "flex";
    }
  }

  // Media preview (Images, PDF Carousels, HD Videos)
  const simMedia = document.getElementById("simulated-media-container");
  const simImg = document.getElementById("simulated-media-img");
  const simPdf = document.getElementById("simulated-media-pdf");
  const simVideo = document.getElementById("simulated-media-video");

  if (mediaUrl) {
    if (simMedia) simMedia.style.display = "block";
    const isPdf = mediaUrl.toLowerCase().endsWith(".pdf") || (activeMediaAsset && (activeMediaAsset.mime_type || "").includes("pdf"));
    const isVideo = mediaUrl.toLowerCase().endsWith(".mp4") || mediaUrl.toLowerCase().endsWith(".webm") || (activeMediaAsset && (activeMediaAsset.mime_type || "").includes("video"));

    if (isPdf) {
      if (simImg) simImg.style.display = "none";
      if (simVideo) simVideo.style.display = "none";
      if (simPdf) {
        simPdf.style.display = "flex";
        const pdfTitle = activeMediaAsset ? activeMediaAsset.file_name : mediaUrl.split("/").pop();
        const pages = activeMediaAsset && activeMediaAsset.page_count ? `${activeMediaAsset.page_count} Pages` : "Multi-Slide";
        const titleEl = document.getElementById("sim-pdf-title");
        const subEl = document.getElementById("sim-pdf-subtitle");
        if (titleEl) titleEl.innerText = pdfTitle;
        if (subEl) subEl.innerText = `Document Carousel (${pages}) • Tap to Swipe`;
      }
    } else if (isVideo) {
      if (simImg) simImg.style.display = "none";
      if (simPdf) simPdf.style.display = "none";
      if (simVideo) {
        simVideo.style.display = "block";
        simVideo.src = mediaUrl;
      }
    } else {
      if (simPdf) simPdf.style.display = "none";
      if (simVideo) simVideo.style.display = "none";
      if (simImg) {
        simImg.style.display = "block";
        simImg.src = mediaUrl;
      }
    }
  } else {
    if (simMedia) simMedia.style.display = "none";
    if (simImg) { simImg.style.display = "none"; simImg.src = ""; }
    if (simPdf) simPdf.style.display = "none";
    if (simVideo) { simVideo.style.display = "none"; simVideo.src = ""; }
  }

  // Update Media Card in Inspector Drawer
  syncInspectorMediaCard();

  // Sync Desktop & Carousel Frames
  syncDesktopPostFrame(text);
  if (currentStageMode === "carousel") {
    buildCarouselDeck(text);
  }

  // 5. Run Real-Time 6-Dimension Algorithmic Safety Audit
  runAlgorithmicAudit(text);
}

// -------------------------------------------------------------
// 5. 6-DIMENSION ALGORITHMIC SAFETY AUDITOR (0-100%)
// -------------------------------------------------------------
function runAlgorithmicAudit(text) {
  let score = 100;
  // Counted where the failures happen. Deriving a count from the score is
  // not possible: the six deductions are 40/20/25/15/15/15, so the arithmetic
  // is lossy in both directions.
  let failedChecks = 0;

  // Dimension 1: Outbound Link in Body (-40 points)
  const urlRegex = /(https?:\/\/[^\s]+|www\.[^\s]+|\b[a-zA-Z0-9-]+\.(com|io|ai|org|net|co)\b)/gi;
  const hasUrl = urlRegex.test(text);
  const dimLink = document.getElementById("dim-link-status");
  const linkDesc = document.getElementById("audit-link-desc");
  const linkFixRow = document.getElementById("audit-link-fix-row");

  if (hasUrl) {
    score -= 40;
    failedChecks += 1;
    if (dimLink) {
      dimLink.className = "reui-audit-badge fail";
      dimLink.innerText = "Penalty (-40%)";
    }
    if (linkDesc) linkDesc.innerText = "External URL in body detected. Move to first comment to preserve reach.";
    if (linkFixRow) linkFixRow.style.display = "flex";
  } else {
    if (dimLink) {
      dimLink.className = "reui-audit-badge pass";
      dimLink.innerText = "Safe (0 in body)";
    }
    if (linkDesc) linkDesc.innerText = "No external URLs in post body. Zero reach penalty.";
    if (linkFixRow) linkFixRow.style.display = "none";
  }

  // Dimension 2: Pre-Fold Hook CTR (-20 points if crowded or > 180 chars)
  const firstLines = text.split("\n").slice(0, 3).join("\n");
  const hookLen = firstLines.length;
  const dimHook = document.getElementById("dim-hook-status");
  const hookDesc = document.getElementById("audit-hook-desc");
  const hookProgress = document.getElementById("audit-hook-progress-bar");
  const hookFixRow = document.getElementById("audit-hook-fix-row");

  if (hookProgress) {
    const pct = Math.min(100, Math.round((hookLen / 180) * 100));
    hookProgress.style.width = `${pct}%`;
    hookProgress.style.backgroundColor = hookLen > 180 ? "var(--signal-orange)" : "var(--signal-green)";
  }

  if (hookLen > 180) {
    score -= 20;
    failedChecks += 1;
    if (dimHook) {
      dimHook.className = "reui-audit-badge warning";
      dimHook.innerText = `Exceeds (${hookLen})`;
    }
    if (hookDesc) hookDesc.innerText = `${hookLen - 180} chars exceed cutoff. Readers may bounce before clicking '...see more'.`;
    if (hookFixRow) hookFixRow.style.display = "flex";
  } else if (hookLen > 0 && hookLen <= 180) {
    if (dimHook) {
      dimHook.className = "reui-audit-badge pass";
      dimHook.innerText = `Fold Safe (${hookLen})`;
    }
    if (hookDesc) hookDesc.innerText = "Hook is fully visible before the mobile fold cutoff.";
    if (hookFixRow) hookFixRow.style.display = "none";
  } else {
    if (dimHook) {
      dimHook.className = "reui-audit-badge pass";
      dimHook.innerText = "Fold Safe (< 180)";
    }
    if (hookDesc) hookDesc.innerText = "Hook is fully visible before the mobile fold cutoff.";
    if (hookFixRow) hookFixRow.style.display = "none";
  }

  // Dimension 3: Engagement-Bait Classifier (-25 points)
  const baitRegex = /(comment\s+['"]?yes['"]?|comment\s+below|type\s+['"]?info['"]?|like\s+and\s+share|tag\s+\d+\s+friends)/i;
  const hasBait = baitRegex.test(text);
  const dimBait = document.getElementById("dim-bait-status");
  const baitDesc = document.getElementById("audit-bait-desc");
  const baitFixRow = document.getElementById("audit-bait-fix-row");

  if (hasBait) {
    score -= 25;
    failedChecks += 1;
    if (dimBait) {
      dimBait.className = "reui-audit-badge fail";
      dimBait.innerText = "Bait Detected";
    }
    if (baitDesc) baitDesc.innerText = "Flagged engagement-bait triggers algorithmic distribution damping.";
    if (baitFixRow) baitFixRow.style.display = "flex";
  } else {
    if (dimBait) {
      dimBait.className = "reui-audit-badge pass";
      dimBait.innerText = "Clean (0 flags)";
    }
    if (baitDesc) baitDesc.innerText = "Free of algorithmic bait triggers like 'comment below'.";
    if (baitFixRow) baitFixRow.style.display = "none";
  }

  // Dimension 4: Hashtag Density (-15 points if > 4 tags)
  const hashtags = (text.match(/#[a-zA-Z0-9_]+/g) || []).length;
  const dimHash = document.getElementById("dim-hashtag-status");
  const hashDesc = document.getElementById("audit-hashtag-desc");
  const hashFixRow = document.getElementById("audit-hashtag-fix-row");

  if (hashtags > 4) {
    score -= 15;
    failedChecks += 1;
    if (dimHash) {
      dimHash.className = "reui-audit-badge warning";
      dimHash.innerText = `Stuffing (${hashtags})`;
    }
    if (hashDesc) hashDesc.innerText = `${hashtags} tags detected. LinkedIn demotes posts with > 3-4 tags.`;
    if (hashFixRow) hashFixRow.style.display = "flex";
  } else if (hashtags >= 1 && hashtags <= 4) {
    if (dimHash) {
      dimHash.className = "reui-audit-badge pass";
      dimHash.innerText = `Optimal (${hashtags})`;
    }
    if (hashDesc) hashDesc.innerText = "Optimal hashtag density for enterprise authority.";
    if (hashFixRow) hashFixRow.style.display = "none";
  } else {
    if (dimHash) {
      dimHash.className = "reui-audit-badge pass";
      dimHash.innerText = "Optimal (0-3)";
    }
    if (hashDesc) hashDesc.innerText = "Optimal hashtag density for enterprise authority.";
    if (hashFixRow) hashFixRow.style.display = "none";
  }

  // Dimension 5: Pacing & Wall of Text (-15 points if > 4 lines unspaced)
  const paragraphs = text.split("\n\n");
  let hasWall = false;
  for (let p of paragraphs) {
    if (p.split("\n").length > 4 && p.length > 300) {
      hasWall = true;
      break;
    }
  }
  const dimPacing = document.getElementById("dim-pacing-status");
  const pacingDesc = document.getElementById("audit-pacing-desc");
  const pacingFixRow = document.getElementById("audit-pacing-fix-row");

  if (hasWall) {
    score -= 15;
    failedChecks += 1;
    if (dimPacing) {
      dimPacing.className = "reui-audit-badge warning";
      dimPacing.innerText = "Wall of Text";
    }
    if (pacingDesc) pacingDesc.innerText = "Dense paragraph with > 4 unspaced lines hurts reader dwell time.";
    if (pacingFixRow) pacingFixRow.style.display = "flex";
  } else {
    if (dimPacing) {
      dimPacing.className = "reui-audit-badge pass";
      dimPacing.innerText = "Well-spaced";
    }
    if (pacingDesc) pacingDesc.innerText = "Rhythm is optimal with 1-3 line breathable paragraphs.";
    if (pacingFixRow) pacingFixRow.style.display = "none";
  }

  // Dimension 6: Zero Em-Dash Rule (-15 points)
  const hasEmDash = /[\u2014\u2013]|(?<=\w)--+(?=\w)/.test(text);
  const dimEmdash = document.getElementById("dim-emdash-status");
  const emdashDesc = document.getElementById("audit-emdash-desc");
  const emdashFixRow = document.getElementById("audit-emdash-fix-row");

  if (hasEmDash) {
    score -= 15;
    failedChecks += 1;
    if (dimEmdash) {
      dimEmdash.className = "reui-audit-badge fail";
      dimEmdash.innerText = "Violation";
    }
    if (emdashDesc) emdashDesc.innerText = "Em-dashes detected. Editorial law requires hyphens or commas.";
    if (emdashFixRow) emdashFixRow.style.display = "flex";
  } else {
    if (dimEmdash) {
      dimEmdash.className = "reui-audit-badge pass";
      dimEmdash.innerText = "Pass (0)";
    }
    if (emdashDesc) emdashDesc.innerText = "Zero em-dashes detected (Clean editorial law).";
    if (emdashFixRow) emdashFixRow.style.display = "none";
  }

  // Final Score & Gauge Animation
  score = Math.max(20, Math.min(100, score));
  const gaugeNum = document.getElementById("algo-gauge-number");
  const gaugeCircle = document.getElementById("algo-gauge-circle");
  if (gaugeNum) gaugeNum.innerText = score;
  if (gaugeCircle) {
    const circumference = 119.38; // 2 * Math.PI * 19
    const offset = circumference * (1 - score / 100);
    gaugeCircle.style.strokeDashoffset = offset;
    if (score >= 90) {
      gaugeCircle.style.stroke = "var(--signal-green)";
    } else if (score >= 70) {
      gaugeCircle.style.stroke = "var(--signal-orange)";
    } else {
      gaugeCircle.style.stroke = "#E03131";
    }
  }

  // Dwell Time & Reach Forecast
  const wordCount = (text.match(/\S+/g) || []).length;
  const readSeconds = Math.max(14, Math.round((wordCount / 180) * 60) + (activeMediaUrl ? 18 : 0));
  const dwellDisplay = document.getElementById("dwell-display");
  const verdictDisplay = document.getElementById("verdict-display");

  if (dwellDisplay) dwellDisplay.innerText = `~${readSeconds} sec`;

  // This used to read "High Reach" or "Suppressed", which is a claim about how
  // LinkedIn will distribute the post. Nothing in this product measures
  // distribution: the score behind it comes from six formatting checks running
  // in this browser, and it has never once been compared against the impression
  // counts already in the database. An empty composer scored 100 and read "High
  // Reach" before the creator typed a character.
  //
  // The checks themselves are real and stay. What is reported now is how many
  // of them are unmet, which is exactly what the computation knows.
  if (verdictDisplay) {
    const unmet = failedChecks;
    if (!text || !text.trim()) {
      verdictDisplay.innerText = "\u2013";
      verdictDisplay.style.color = "var(--text-muted)";
    } else if (unmet === 0) {
      verdictDisplay.innerText = "Formatting clean";
      verdictDisplay.style.color = "var(--signal-green)";
    } else {
      verdictDisplay.innerText = `${unmet} to fix`;
      verdictDisplay.style.color = unmet <= 2 ? "var(--signal-orange)" : "var(--signal-red)";
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

  const bindBtn = (id, fn) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("click", () => applySelectionTransform(fn));
  };

  bindBtn("float-bold-btn", toUnicodeSansBold);
  bindBtn("float-italic-btn", toUnicodeSansItalic);
  bindBtn("float-serif-bold-btn", toUnicodeSerifBold);
  bindBtn("float-serif-italic-btn", toUnicodeSerifItalic);
  bindBtn("float-blackboard-btn", toUnicodeBlackboard);
  bindBtn("float-underline-btn", toUnicodeUnderline);
  bindBtn("float-circled-btn", toUnicodeCircledNumbers);
  bindBtn("float-mono-btn", toUnicodeMonospace);
  bindBtn("float-strike-btn", toStrikethrough);
  bindBtn("float-clean-btn", cleanEmDashes);

  // Desktop Ergonomic Hotkeys: Ctrl+B, Ctrl+I, Ctrl+M, Ctrl+U
  textarea.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey) {
      const key = e.key.toLowerCase();
      if (key === "b") {
        e.preventDefault();
        applySelectionTransform(toUnicodeSansBold);
      } else if (key === "i") {
        e.preventDefault();
        applySelectionTransform(toUnicodeSansItalic);
      } else if (key === "m") {
        e.preventDefault();
        applySelectionTransform(toUnicodeMonospace);
      } else if (key === "u") {
        e.preventDefault();
        applySelectionTransform(toUnicodeUnderline);
      }
    }
  });

  const rehookBtn = document.getElementById("float-rehook-btn");
  if (rehookBtn) {
    rehookBtn.addEventListener("click", () => {
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const selected = textarea.value.substring(start, end).trim();
      toolbar.style.display = "none";
      generateHookVariants(selected || textarea.value.slice(0, 150));
    });
  }
}

// -------------------------------------------------------------
// 7. INLINE HOOK FILMSTRIP / CONTACT SHEET (Section 7.A)
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
      const container = document.getElementById("hook-carousel-container");
      if (container) container.style.display = "none";
    });
  }

  if (prevBtn && track) {
    prevBtn.addEventListener("click", () => {
      track.scrollBy({ left: -260, behavior: "smooth" });
    });
  }

  if (nextBtn && track) {
    nextBtn.addEventListener("click", () => {
      track.scrollBy({ left: 260, behavior: "smooth" });
    });
  }

  // Keyboard shortcut listener: [1]..[9] swaps active specimen
  window.addEventListener("keydown", (e) => {
    const container = document.getElementById("hook-carousel-container");
    if (container && container.style.display !== "none" && activeGeneratedHooks.length > 0) {
      if (document.activeElement !== document.getElementById("post-editor-input")) {
        const num = parseInt(e.key);
        if (!isNaN(num) && num >= 1 && num <= activeGeneratedHooks.length) {
          e.preventDefault();
          const targetHook = activeGeneratedHooks[num - 1];
          applyHookToDraft(targetHook.hook_text, targetHook.archetype);
        }
      }
    }
  });
}

function applyHookToDraft(hookText, archetype) {
  const textarea = document.getElementById("post-editor-input");
  const rawLines = textarea.value.split("\n\n");
  if (rawLines.length > 1) {
    rawLines[0] = hookText;
    textarea.value = rawLines.join("\n\n");
  } else {
    textarea.value = hookText + (textarea.value ? "\n\n" + textarea.value : "");
  }
  updateStudioState();
  showToast(`Applied "${archetype}" hook specimen!`);
  const container = document.getElementById("hook-carousel-container");
  if (container) container.style.display = "none";
}

async function generateHookVariants(contextText) {
  const container = document.getElementById("hook-carousel-container");
  const track = document.getElementById("hook-cards-track");
  if (container) container.style.display = "flex";
  track.innerHTML = `<div style="padding: 14px; font-size: 12.5px; color: var(--text-muted); display: flex; align-items: center; gap: 6px;"><svg class="app-symbol app-symbol-xs"><use href="#sym-act-spark"></use></svg> Synthesizing 10x scroll-stopping specimens...</div>`;

  try {
    const res = await fetch(`${API_BASE}/format/re-hook`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: contextText })
    });
    const json = await res.json();
    const hooks = json.hooks || [];
    activeGeneratedHooks = hooks;

    track.innerHTML = "";
    hooks.forEach((h, idx) => {
      const card = document.createElement("div");
      card.className = "hook-specimen-card";
      // The backend emits `mobile_safe` (repurposer.py:301, :363). Reading
      // `is_mobile_fold_safe` produced undefined for every hook, so the only
      // real signal in this panel was rendered inverted: fold-safe hooks were
      // all labelled "Truncated".
      const isSafe = h.mobile_safe;

      card.innerHTML = `
        <div class="hook-specimen-header">
          <span class="hook-specimen-shortcut">[${idx + 1}]</span>
          <span>${escapeHtml(h.archetype)}</span>
        </div>
        <div class="hook-specimen-text">${escapeHtml(h.hook_text)}</div>
        <div class="hook-specimen-footer">
          <span>${isSafe ? 'Fold Safe' : 'Truncated'} (${h.char_count}c)</span>
          <span style="color: var(--signal-orange); font-weight: 600; display: inline-flex; align-items: center; gap: 4px;">Apply <svg class="app-symbol app-symbol-xs app-symbol-no-margin"><use href="#sym-act-apply"></use></svg></span>
        </div>
      `;

      card.addEventListener("click", () => {
        applyHookToDraft(h.hook_text, h.archetype);
      });

      track.appendChild(card);
    });

  } catch (e) {
    track.innerHTML = `<div style="color: var(--signal-orange); padding: 12px;">Error generating hooks: ${e.message}</div>`;
  }
}

// -------------------------------------------------------------
// 8. UNIFIED NATIVE MEDIA DROPZONE & ASSET VAULT
// -------------------------------------------------------------
function initMediaDropzone() {
  const fileInput = document.getElementById("media-file-input");
  const pathInput = document.getElementById("media-path-input");
  const targetZone = document.getElementById("media-dropzone-target");
  const browseBtn = document.getElementById("dropzone-browse-btn");
  const attachedCard = document.getElementById("media-attached-card");
  const attachedRemove = document.getElementById("media-attached-remove");
  const aiStudioBtn = document.getElementById("btn-dropzone-ai-studio");

  if (!fileInput || !targetZone) return;

  // Click target to trigger file selection
  targetZone.addEventListener("click", (e) => {
    if (e.target.id === "btn-dropzone-ai-studio" || e.target.closest("#btn-dropzone-ai-studio")) {
      return;
    }
    fileInput.click();
  });

  if (browseBtn) {
    browseBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      fileInput.click();
    });
  }

  // Drag-and-drop visual indicators
  ["dragenter", "dragover"].forEach(eventName => {
    targetZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      targetZone.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach(eventName => {
    targetZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      targetZone.classList.remove("dragover");
    });
  });

  targetZone.addEventListener("drop", (e) => {
    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      uploadMediaFile(files[0]);
    }
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files.length > 0) {
      uploadMediaFile(fileInput.files[0]);
    }
  });

  if (attachedRemove) {
    attachedRemove.addEventListener("click", () => {
      clearAttachedMedia();
      showToast("Media attachment removed.");
    });
  }

  if (aiStudioBtn) {
    aiStudioBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      openImageStudio();
    });
  }
}

async function uploadMediaFile(file) {
  showToast(`Uploading ${file.name}...`);
  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch(`${API_BASE}/media/upload`, {
      method: "POST",
      body: formData
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Upload failed" }));
      showToast(`Upload error: ${err.detail || "Failed to upload"}`);
      return;
    }

    const data = await res.json();
    setAttachedMedia(data);
    showToast(`Uploaded ${data.filename || data.file_name || "file"} successfully!`);
    const fileInput = document.getElementById("media-file-input");
    if (fileInput) fileInput.value = "";
  } catch (e) {
    showToast("Network error uploading file: " + e.message);
  }
}

function setAttachedMedia(media) {
  if (!media) return;

  // Two callers pass two different shapes. The upload endpoint returns
  // `filename` and `url`; the AI image studio hand-builds `file_name` and
  // `file_url`. This function only ever read the second form, so every real
  // file upload threw "Cannot read properties of undefined (reading
  // 'toLowerCase')" and the attachment silently never appeared. The image
  // studio path worked, which is why it went unnoticed.
  //
  // Normalise once here rather than at each call site, so a future caller
  // passing either shape cannot reintroduce this.
  media = Object.assign({}, media, {
    file_name: media.file_name || media.filename || "",
    file_url: media.file_url || media.url || ""
  });

  activeMediaAsset = media;
  activeMediaUrl = media.file_url;
  const pathInput = document.getElementById("media-path-input");
  const targetZone = document.getElementById("media-dropzone-target");
  const attachedCard = document.getElementById("media-attached-card");
  const attachedPreview = document.getElementById("media-attached-preview");
  const attachedName = document.getElementById("media-attached-name");
  const attachedType = document.getElementById("media-attached-type");
  const attachedMeta = document.getElementById("media-attached-meta");
  const attachedView = document.getElementById("media-attached-view");

  if (pathInput) pathInput.value = media.file_url;
  if (attachedName) attachedName.innerText = media.file_name;
  if (attachedView) attachedView.href = media.file_url;

  const mime = media.mime_type || "";
  const isPdf = mime.includes("pdf") || media.file_name.toLowerCase().endsWith(".pdf");
  const isVideo = mime.includes("video") || media.file_name.toLowerCase().endsWith(".mp4") || media.file_name.toLowerCase().endsWith(".webm");

  if (isPdf) {
    const pages = media.page_count ? `${media.page_count} Pages` : "Multi-Slide";
    if (attachedType) {
      attachedType.innerText = `CAROUSEL (${pages})`;
      attachedType.className = "sidebar-badge pro";
    }
    if (attachedMeta) attachedMeta.innerText = `Native Document Carousel • ${formatBytes(media.file_size || 0)}`;
    if (attachedPreview) attachedPreview.innerHTML = `<span class="pdf-thumb-icon"><svg class="app-symbol app-symbol-lg app-symbol-no-margin"><use href="#sym-sec-docs"></use></svg></span>`;
  } else if (isVideo) {
    if (attachedType) {
      attachedType.innerText = "VIDEO";
      attachedType.className = "sidebar-badge count";
    }
    const dur = media.duration_seconds ? `${Math.round(media.duration_seconds)}s • ` : "";
    if (attachedMeta) attachedMeta.innerText = `HD Video • ${dur}${formatBytes(media.file_size || 0)}`;
    if (attachedPreview) attachedPreview.innerHTML = `<span class="video-thumb-icon"><svg class="app-symbol app-symbol-lg app-symbol-no-margin"><use href="#sym-mode-media"></use></svg></span>`;
  } else {
    if (attachedType) {
      attachedType.innerText = "IMAGE";
      attachedType.className = "sidebar-badge pro";
    }
    if (attachedMeta) attachedMeta.innerText = `High-Res Visual • ${formatBytes(media.file_size || 0)}`;
    if (attachedPreview) attachedPreview.innerHTML = `<img src="${media.file_url}" alt="Attachment">`;
  }

  if (targetZone) targetZone.style.display = "none";
  if (attachedCard) attachedCard.style.display = "flex";

  updateStudioState();
}

function clearAttachedMedia() {
  activeMediaAsset = null;
  activeMediaUrl = "";
  const pathInput = document.getElementById("media-path-input");
  const fileInput = document.getElementById("media-file-input");
  const targetZone = document.getElementById("media-dropzone-target");
  const attachedCard = document.getElementById("media-attached-card");

  if (pathInput) pathInput.value = "";
  if (fileInput) fileInput.value = "";
  if (targetZone) targetZone.style.display = "flex";
  if (attachedCard) attachedCard.style.display = "none";

  updateStudioState();
}

function formatBytes(bytes) {
  if (!bytes) return "0 KB";
  const kb = bytes / 1024;
  if (kb < 1024) return `${Math.round(kb)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

// -------------------------------------------------------------
// 8B. AGNO AI IMAGE STUDIO & MULTI-STAGE ORCHESTRATION
// -------------------------------------------------------------
function initImageStudio() {
  const modal = document.getElementById("image-studio-modal");
  const openBtn = document.getElementById("btn-open-image-studio");
  const closeBtn = document.getElementById("image-studio-close-btn");
  const conceptInput = document.getElementById("studio-concept-input");
  const pullDraftBtn = document.getElementById("btn-use-draft-as-concept");
  const synthPromptBtn = document.getElementById("btn-synthesize-prompt");
  const masterPromptContainer = document.getElementById("studio-master-prompt-container");
  const masterPromptDisplay = document.getElementById("studio-master-prompt-display");
  const launchGenBtn = document.getElementById("btn-start-image-generation");
  const progressCard = document.getElementById("image-gen-progress-card");
  const progressPhaseLabel = document.getElementById("progress-phase-label");
  const progressPercentDisplay = document.getElementById("progress-percent-display");
  const progressFill = document.getElementById("image-gen-progress-fill");
  const progressDetail = document.getElementById("progress-status-detail");
  const emptyState = document.getElementById("image-gen-empty-state");
  const imageWrapper = document.getElementById("image-gen-image-wrapper");
  const resultImg = document.getElementById("image-gen-result-img");
  const downloadLink = document.getElementById("btn-download-generated-image");
  const attachDraftBtn = document.getElementById("btn-attach-to-draft");
  const paletteSelect = document.getElementById("studio-palette-select");
  const lightingSelect = document.getElementById("studio-lighting-select");

  if (!modal) return;

  if (openBtn) {
    openBtn.addEventListener("click", openImageStudio);
  }

  if (closeBtn) {
    closeBtn.addEventListener("click", closeImageStudio);
  }

  modal.addEventListener("click", (e) => {
    if (e.target === modal) {
      closeImageStudio();
    }
  });

  // Aspect ratio chip selection
  document.querySelectorAll("#studio-aspect-ratio-group .studio-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      document.querySelectorAll("#studio-aspect-ratio-group .studio-chip").forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      studioAspectRatio = chip.getAttribute("data-value");
    });
  });

  // Visual style chip selection
  document.querySelectorAll("#studio-style-group .studio-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      document.querySelectorAll("#studio-style-group .studio-chip").forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      studioVisualStyle = chip.getAttribute("data-value");
    });
  });

  if (paletteSelect) {
    paletteSelect.addEventListener("change", (e) => {
      studioPalette = e.target.value;
    });
  }

  if (lightingSelect) {
    lightingSelect.addEventListener("change", (e) => {
      studioLighting = e.target.value;
    });
  }

  // Pull concept from active post editor
  if (pullDraftBtn) {
    pullDraftBtn.addEventListener("click", () => {
      const editorText = document.getElementById("post-editor-input").value.trim();
      if (!editorText) {
        showToast("No content in post editor to pull from.");
        return;
      }
      const firstParagraph = editorText.split("\n\n")[0];
      conceptInput.value = firstParagraph.slice(0, 300);
      showToast("Concept populated from active draft!");
    });
  }

  // Synthesize Master Prompt via Agno ImagePromptSynthesizerAgent
  if (synthPromptBtn) {
    synthPromptBtn.addEventListener("click", async () => {
      const concept = conceptInput.value.trim();
      if (!concept) {
        showToast("Please enter a creative visual concept first.");
        conceptInput.focus();
        return;
      }

      synthPromptBtn.disabled = true;
      synthPromptBtn.innerHTML = '<svg class="app-symbol app-spin"><use href="#sym-refresh"></use></svg> Synthesizing Prompt...';

      try {
        const res = await fetch(`${API_BASE}/image/synthesize-prompt`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            concept,
            aspect_ratio: studioAspectRatio,
            visual_style: studioVisualStyle,
            color_palette: studioPalette,
            lighting: studioLighting,
            render_quote_overlay: document.getElementById("studio-quote-toggle") ? document.getElementById("studio-quote-toggle").checked : true,
            custom_quote_text: document.getElementById("studio-custom-quote-text") ? document.getElementById("studio-custom-quote-text").value.trim() : null,
            custom_quote_author: document.getElementById("studio-custom-quote-author") ? document.getElementById("studio-custom-quote-author").value.trim() : null
          })
        });

        if (res.ok) {
          const data = await res.json();
          const synth = data.synthesized || data;
          lastSynthesizedPrompt = synth;
          masterPromptDisplay.value = synth.master_prompt || "";
          masterPromptContainer.style.display = "block";
          if (synth.quote_text && document.getElementById("studio-custom-quote-text") && !document.getElementById("studio-custom-quote-text").value) {
            document.getElementById("studio-custom-quote-text").value = synth.quote_text;
            if (synth.quote_author && document.getElementById("studio-custom-quote-author")) {
              document.getElementById("studio-custom-quote-author").value = synth.quote_author;
            }
          }
          showToast(`Master prompt synthesized (${synth.aspect_ratio || "1:1"})!`);
        } else {
          showToast("Failed to synthesize prompt.");
        }
      } catch (e) {
        showToast("Synthesis error: " + e.message);
      } finally {
        synthPromptBtn.disabled = false;
        synthPromptBtn.innerHTML = '<svg class="app-symbol"><use href="#sym-sec-ai-command"></use></svg> Synthesize Master Prompt with Agno';
      }
    });
  }

  // Toggle modal personal watermark options display
  const personalWatermarkToggle = document.getElementById("img-apply-personal-watermark");
  const personalWatermarkOptions = document.getElementById("modal-personal-watermark-options");
  if (personalWatermarkToggle && personalWatermarkOptions) {
    personalWatermarkToggle.addEventListener("change", () => {
      personalWatermarkOptions.style.display = personalWatermarkToggle.checked ? "block" : "none";
    });
  }

  // Launch AI Image Generation with Live Progress Bar (1% - 100%)
  if (launchGenBtn) {
    launchGenBtn.addEventListener("click", async () => {
      const concept = conceptInput.value.trim();
      const customPrompt = masterPromptDisplay.value.trim();
      if (!concept && !customPrompt) {
        showToast("Please provide a visual concept or prompt.");
        conceptInput.focus();
        return;
      }

      launchGenBtn.disabled = true;
      launchGenBtn.innerHTML = '<svg class="app-symbol app-spin"><use href="#sym-refresh"></use></svg> Orchestrating Generation...';

      // Reset & show live progress box
      progressCard.style.display = "flex";
      progressPhaseLabel.innerText = "Initializing synthesis pipeline...";
      progressPercentDisplay.innerText = "1%";
      progressFill.style.width = "1%";
      progressDetail.innerText = "Formulating composition constraints & anti-artifact filters";
      emptyState.style.display = "flex";
      imageWrapper.style.display = "none";

      try {
        const res = await fetch(`${API_BASE}/image/generate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            concept: concept || "Enterprise tech visualization",
            aspect_ratio: studioAspectRatio,
            visual_style: studioVisualStyle,
            color_palette: studioPalette,
            lighting: studioLighting,
            custom_prompt: customPrompt || null,
            render_quote_overlay: document.getElementById("studio-quote-toggle") ? document.getElementById("studio-quote-toggle").checked : true,
            custom_quote_text: document.getElementById("studio-custom-quote-text") ? document.getElementById("studio-custom-quote-text").value.trim() : null,
            custom_quote_author: document.getElementById("studio-custom-quote-author") ? document.getElementById("studio-custom-quote-author").value.trim() : null,
            eliminate_provider_watermark: document.getElementById("img-eliminate-watermark") ? document.getElementById("img-eliminate-watermark").checked : true,
            apply_personal_watermark: document.getElementById("img-apply-personal-watermark") ? document.getElementById("img-apply-personal-watermark").checked : false,
            personal_watermark_text: document.getElementById("img-personal-watermark-text") ? document.getElementById("img-personal-watermark-text").value.trim() : null,
            personal_watermark_position: document.getElementById("img-personal-watermark-position") ? document.getElementById("img-personal-watermark-position").value : "bottom_right",
            personal_watermark_style: document.getElementById("img-personal-watermark-style") ? document.getElementById("img-personal-watermark-style").value : "glass_pill"
          })
        });

        if (!res.ok) {
          throw new Error("Failed to initialize generation task");
        }

        const taskData = await res.json();
        activeImageGenTaskId = taskData.task_id;

        // Start live polling of generation progress
        pollImageGenerationProgress(activeImageGenTaskId);
      } catch (e) {
        showToast("Generation error: " + e.message);
        progressCard.style.display = "none";
        launchGenBtn.disabled = false;
        launchGenBtn.innerHTML = '<svg class="app-symbol"><use href="#sym-act-spark"></use></svg> Launch AI Generation';
      }
    });
  }

  // Attach to Draft
  if (attachDraftBtn) {
    attachDraftBtn.addEventListener("click", () => {
      if (!resultImg.src) return;
      const imageUrl = resultImg.src;
      setAttachedMedia({
        file_name: "ai_studio_generated.png",
        file_url: imageUrl,
        mime_type: "image/png",
        file_size: 1024 * 512,
        page_count: null
      });
      closeImageStudio();
      showToast("Attached AI Visual to active draft.");
    });
  }
}

function openImageStudio() {
  const modal = document.getElementById("image-studio-modal");
  if (modal) {
    modal.style.display = "flex";
    const conceptInput = document.getElementById("studio-concept-input");
    if (conceptInput && !conceptInput.value.trim()) {
      const editorText = document.getElementById("post-editor-input").value.trim();
      if (editorText) {
        conceptInput.value = editorText.split("\n\n")[0].slice(0, 240);
      }
    }
  }
}

function closeImageStudio() {
  const modal = document.getElementById("image-studio-modal");
  if (modal) modal.style.display = "none";
}

function pollImageGenerationProgress(taskId) {
  if (imageGenPollInterval) {
    clearInterval(imageGenPollInterval);
  }

  const progressPhaseLabel = document.getElementById("progress-phase-label");
  const progressPercentDisplay = document.getElementById("progress-percent-display");
  const progressFill = document.getElementById("image-gen-progress-fill");
  const progressDetail = document.getElementById("progress-status-detail");
  const emptyState = document.getElementById("image-gen-empty-state");
  const imageWrapper = document.getElementById("image-gen-image-wrapper");
  const resultImg = document.getElementById("image-gen-result-img");
  const downloadLink = document.getElementById("btn-download-generated-image");
  const launchGenBtn = document.getElementById("btn-start-image-generation");

  imageGenPollInterval = setInterval(async () => {
    try {
      const res = await fetch(`${API_BASE}/image/progress/${taskId}`);
      if (!res.ok) return;

      const task = await res.json();
      const pct = Math.max(1, Math.min(100, task.progress_percent !== undefined ? task.progress_percent : (task.progress !== undefined ? task.progress : 1)));
      progressPercentDisplay.innerText = `${pct}%`;
      progressFill.style.width = `${pct}%`;

      const msg = task.status_message || task.phase_message;
      if (msg) {
        progressPhaseLabel.innerText = msg;
        progressDetail.innerText = `Orchestrating high-res engine (${task.aspect_ratio || "1:1"})`;
      }

      if (task.status === "completed") {
        clearInterval(imageGenPollInterval);
        imageGenPollInterval = null;

        progressPercentDisplay.innerText = "100%";
        progressFill.style.width = "100%";
        progressPhaseLabel.innerText = "Visual synthesis completed!";
        progressDetail.innerText = "Asset successfully rendered and stored in local vault";

        const imgUrl = task.result_url || task.image_url;
        if (imgUrl) {
          resultImg.src = imgUrl;
          if (downloadLink) downloadLink.href = imgUrl;
          emptyState.style.display = "none";
          imageWrapper.style.display = "flex";
        }

        launchGenBtn.disabled = false;
        launchGenBtn.innerHTML = '<svg class="app-symbol"><use href="#sym-act-spark"></use></svg> Launch AI Generation';
        showToast("AI Visual generation finished.");
      } else if (task.status === "failed") {
        clearInterval(imageGenPollInterval);
        imageGenPollInterval = null;

        progressPhaseLabel.innerText = "Generation failed";
        progressDetail.innerText = task.error_message || "An error occurred during neural rendering";
        launchGenBtn.disabled = false;
        launchGenBtn.innerHTML = '<svg class="app-symbol"><use href="#sym-act-spark"></use></svg> Launch AI Generation';
        showToast("Generation failed: " + (task.error_message || "Unknown error"));
      }
    } catch (e) {
      console.warn("Poll progress error:", e);
    }
  }, 400);
}

// -------------------------------------------------------------
// 9. WARM-LEAD CRM INBOX & CONTEXTUAL DM STARTER
// -------------------------------------------------------------
let allLeads = [];
let currentCRMStatus = "";
let currentCRMSearch = "";
let currentDMLeadId = null;
let currentDMStyle = "value_add";
let cachedDMVariants = [];
let crmSearchDebounce = null;

function initCRM() {
  const dmModal = document.getElementById("dm-modal");
  const dmCloseBtn = document.getElementById("dm-close-btn");
  const dmCancelBtn = document.getElementById("dm-cancel-btn");
  const copyBtn = document.getElementById("btn-copy-dm");
  const openChatBtn = document.getElementById("btn-open-linkedin-chat");

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
        showToast("Anti-slop DM copied to clipboard.", "success");
      } catch (e) {
        showToast("Copied script!");
      }
      if (dmModal) dmModal.style.display = "none";
    });
  }

  if (openChatBtn) {
    openChatBtn.addEventListener("click", async () => {
      const text = document.getElementById("dm-script-textarea").value;
      try {
        await navigator.clipboard.writeText(text);
      } catch (e) {}

      let targetUrl = "https://www.linkedin.com/messaging/";
      if (activeDossierLead && activeDossierLead.profile_url) {
        targetUrl = activeDossierLead.profile_url;
      }
      window.open(targetUrl, "_blank");
      showToast("DM copied to clipboard. Paste directly into LinkedIn message thread.", "success");
      if (dmModal) dmModal.style.display = "none";
    });
  }

  // 3-Angle Strategic Selector Tabs
  const angleChips = document.querySelectorAll("#dm-angle-chips .topic-chip");
  angleChips.forEach(chip => {
    chip.addEventListener("click", () => {
      angleChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      const angleIdx = parseInt(chip.getAttribute("data-angle-index") || "0", 10);
      const variant = cachedDMVariants[angleIdx];
      const textarea = document.getElementById("dm-script-textarea");
      const indicator = document.getElementById("dm-angle-indicator");
      if (variant) {
        if (textarea) textarea.value = variant.dm_text || "";
        if (indicator) indicator.innerText = `Angle: ${variant.angle || "Direct Technical"}`;
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

  const agnoModal = document.getElementById("agno-modal");
  const agnoCloseBtn = document.getElementById("agno-modal-close");
  const agnoDismissBtn = document.getElementById("agno-modal-dismiss");
  if (agnoCloseBtn && agnoModal) {
    agnoCloseBtn.addEventListener("click", () => { agnoModal.style.display = "none"; });
  }
  if (agnoDismissBtn && agnoModal) {
    agnoDismissBtn.addEventListener("click", () => { agnoModal.style.display = "none"; });
  }
  if (agnoModal) {
    agnoModal.addEventListener("click", (e) => {
      if (e.target === agnoModal) agnoModal.style.display = "none";
    });
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

async function renderCRMTelemetry() {
  try {
    const res = await fetch(`${API_BASE}/v1/crm/telemetry`);
    if (!res.ok) return;
    const data = await res.json();
    if (data.status !== "success" || !data.summary) return;

    const s = data.summary;
    const totalEl = document.getElementById("crm-telem-total-leads");
    const vipEl = document.getElementById("crm-telem-vip-leads");
    const avgEl = document.getElementById("crm-telem-avg-score");
    const inqEl = document.getElementById("crm-telem-inquiry-rate");
    const convEl = document.getElementById("crm-telem-conversion-rate");

    if (totalEl) totalEl.innerText = s.total_leads || 0;
    if (vipEl) vipEl.innerText = s.high_value_leads || 0;
    if (avgEl) avgEl.innerText = (s.avg_icp_score || 0).toFixed(1);

    const inqPct = (data.inquiry_telemetry && data.inquiry_telemetry.question_inquiry_rate_pct) || 0;
    if (inqEl) inqEl.innerText = `${inqPct.toFixed(1)}%`;
    if (convEl) convEl.innerText = `Conversion Rate: ${(s.conversion_rate_pct || 0).toFixed(1)}%`;

    // Funnel widths
    if (data.funnel && s.total_leads > 0) {
      const f = data.funnel;
      const t = s.total_leads;
      const setWidth = (id, count) => {
        const el = document.getElementById(id);
        if (el) {
          const pct = Math.max(5, Math.round((count / t) * 100));
          el.style.width = `${pct}%`;
        }
      };
      setWidth("funnel-seg-new", f.NEW || 0);
      setWidth("funnel-seg-engaged", (f.ENGAGED || 0) + (f.DM_DRAFTED || 0));
      setWidth("funnel-seg-sent", f.DM_SENT || 0);
      setWidth("funnel-seg-converted", f.CONVERTED || 0);
    }
  } catch (e) {
    console.debug("[CRM Telemetry] Render error:", e);
    const totalEl = document.getElementById("crm-telem-total-leads");
    if (totalEl) totalEl.innerText = "--";
    const vipEl = document.getElementById("crm-telem-vip-leads");
    if (vipEl) vipEl.innerText = "--";
    const avgEl = document.getElementById("crm-telem-avg-score");
    if (avgEl) avgEl.innerText = "--";
    const inqEl = document.getElementById("crm-telem-inquiry-rate");
    if (inqEl) inqEl.innerText = "--";
  }
}

async function loadLeads() {
  try {
    let url = `${API_BASE}/leads?`;
    if (currentCRMStatus) url += `status=${encodeURIComponent(currentCRMStatus)}&`;
    if (currentCRMSearch) url += `search=${encodeURIComponent(currentCRMSearch)}&`;

    renderCRMTelemetry();

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
  const streamList = document.getElementById("crm-stream-list");

  // Populate stream list for reimagined Editorial CRM
  if (streamList) {
    streamList.innerHTML = "";
    if (!leads.length) {
      const msg = (currentCRMStatus || currentCRMSearch) ?
        "No matching prospects found." :
        "No prospects in stream. Add contacts or browse LinkedIn comments to capture leads.";
      streamList.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 36px 16px; font-size: 13px;">${msg}</div>`;
    } else {
      leads.forEach(lead => {
        const card = document.createElement("div");
        const isSelected = activeDossierLead && activeDossierLead.id === lead.id;
        card.className = `crm-lead-card ${isSelected ? 'active' : ''}`;
        card.setAttribute("data-id", lead.id);
        const engType = lead.engagement_type || "Commented";
        const engClass = engType.toLowerCase();

        const icpScore = typeof lead.icp_score === "number" ? lead.icp_score : (parseFloat(lead.icp_score) || 0.0);
        let tierClass = "tier-disqualified";
        let tierLabel = "LOW";
        if (icpScore >= 80.0) {
          tierClass = "tier-vip";
          tierLabel = "VIP";
        } else if (icpScore >= 60.0) {
          tierClass = "tier-qualified";
          tierLabel = "QUAL";
        } else if (icpScore >= 30.0) {
          tierClass = "tier-nurture";
          tierLabel = "NURTURE";
        }

        const seniority = escapeHtml(lead.seniority_level || "Unknown");
        const icpBadgeHtml = `
          <span class="icp-badge-pill ${tierClass}">
            ${tierLabel} ${Math.round(icpScore)}
            <span class="icp-breakdown-tooltip">
              <strong>ICP Score: ${icpScore.toFixed(1)} / 100</strong><br/>
              Seniority: ${seniority}<br/>
              Formula: (Ws*0.45) + (Wi*0.30) + (Wc*0.15) + (Wq*0.10)
            </span>
          </span>
        `;

        card.innerHTML = `
          <div class="crm-lead-card-header">
            <span class="crm-lead-card-name">${escapeHtml(lead.name)}</span>
            <div style="display: flex; gap: 4px; align-items: center;">
              ${icpBadgeHtml}
              <span class="crm-badge ${engClass}">${escapeHtml(engType)}</span>
            </div>
          </div>
          <div class="crm-lead-card-meta">${escapeHtml(lead.headline || lead.company || 'Enterprise')}</div>
          <div class="crm-lead-card-status">${escapeHtml(lead.status || lead.lead_status || 'New Lead')}</div>
        `;

        card.addEventListener("click", () => {
          activeDossierLead = lead;
          streamList.querySelectorAll(".crm-lead-card").forEach(c => c.classList.remove("active"));
          card.classList.add("active");
          populatePersonDossier(lead);
        });

        streamList.appendChild(card);
      });

      // Default select active lead or first lead
      if (!activeDossierLead || !leads.some(l => l.id === activeDossierLead.id)) {
        activeDossierLead = leads[0];
        const firstCard = streamList.querySelector(".crm-lead-card");
        if (firstCard) firstCard.classList.add("active");
        populatePersonDossier(leads[0]);
      } else {
        const selCard = streamList.querySelector(`.crm-lead-card[data-id="${activeDossierLead.id}"]`);
        if (selCard) selCard.classList.add("active");
        populatePersonDossier(activeDossierLead);
      }
    }
  }

  // Populate legacy table wrapper if present
  if (tbody) {
    tbody.innerHTML = "";
    if (!leads.length) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 28px;">No prospects found</td></tr>`;
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
            <button class="btn btn-outline btn-sm btn-agno-enrich" data-id="${lead.id}" title="Run Autonomous Agno Lead Enrichment"><svg class="app-symbol app-symbol-xs"><use href="#sym-sec-ai-command"></use></svg> Enrich</button>
            <button class="btn btn-outline btn-sm btn-generate-dm" data-id="${lead.id}" title="Generate personalized outreach DM"><svg class="app-symbol app-symbol-xs"><use href="#sym-act-apply"></use></svg> DM</button>
            <button class="btn btn-danger-outline btn-sm btn-del-lead" data-id="${lead.id}" title="Delete prospect"><svg class="app-symbol app-symbol-xs app-symbol-no-margin"><use href="#sym-close"></use></svg></button>
          </div>
        </td>
      `;
      tbody.appendChild(tr);
    });

    tbody.querySelectorAll(".crm-status-select").forEach(sel => {
      sel.addEventListener("change", async () => {
        const id = sel.getAttribute("data-id");
        try {
          const res = await fetch(`${API_BASE}/leads/${id}/status`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status: sel.value })
          });
          if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            showToast(`Failed to update status: ${errData.detail || res.statusText}`, "error");
            return;
          }
          showToast(`Status updated to "${sel.value}"`);
          loadLeads();
        } catch (e) {
          showToast("Network error updating status: " + e.message, "error");
        }
      });
    });

    tbody.querySelectorAll(".btn-agno-enrich").forEach(btn => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-id");
        const originalText = btn.innerHTML;
        btn.innerHTML = '<svg class="app-symbol app-symbol-xs"><use href="#sym-act-spark"></use></svg> Enriching...';
        btn.disabled = true;
        try {
          const res = await fetch(`${API_BASE}/leads/${id}/enrich`, { method: "POST" });
          const json = await res.json();
          if (json.status === "success" && json.enrichment) {
            showAgnoDossierModal(json.enrichment);
            showToast("Agno Intelligence Dossier generated.");
          } else {
            showToast("Failed to enrich lead: " + (json.detail || "Unknown error"));
          }
        } catch (e) {
          showToast("Enrichment error: " + e.message);
        } finally {
          btn.innerHTML = originalText;
          btn.disabled = false;
        }
      });
    });

    tbody.querySelectorAll(".btn-generate-dm").forEach(btn => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-id");
        currentDMLeadId = id;
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
          try {
            const res = await fetch(`${API_BASE}/leads/${id}`, { method: "DELETE" });
            if (!res.ok) {
              const errData = await res.json().catch(() => ({}));
              showToast(`Failed to remove prospect: ${errData.detail || res.statusText}`, "error");
              return;
            }
            showToast("Prospect removed from CRM.");
            loadLeads();
          } catch (e) {
            showToast("Network error removing prospect: " + e.message, "error");
          }
        }
      });
    });
  }
}

function populatePersonDossier(lead) {
  if (!lead) return;
  const nameEl = document.getElementById("dossier-lead-name");
  const headlineEl = document.getElementById("dossier-lead-headline");
  const statusEl = document.getElementById("dossier-lead-status");
  const engEl = document.getElementById("dossier-lead-engagement");
  const profileContextEl = document.getElementById("dossier-profile-context");
  const whyTheyMatterEl = document.getElementById("dossier-why-they-matter");
  const notesEl = document.getElementById("dossier-notes-body");

  if (nameEl) nameEl.innerText = lead.name || "Unknown Prospect";
  if (headlineEl) headlineEl.innerText = lead.headline || (lead.company ? `Executive at ${lead.company}` : "LinkedIn Member");
  if (statusEl) statusEl.innerText = lead.status || "New Lead";
  if (engEl) engEl.innerText = lead.engagement_type ? `Engaged via ${lead.engagement_type}` : "Active Commenter";

  if (profileContextEl) {
    profileContextEl.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 8px;">
        <div><strong>Company:</strong> ${escapeHtml(lead.company || "Not specified")}</div>
        <div><strong>Role:</strong> ${escapeHtml(lead.headline || "Not specified")}</div>
        ${lead.profile_url ? `<div><strong>Profile:</strong> <a href="${escapeHtml(lead.profile_url)}" target="_blank" style="color: var(--signal-orange); text-decoration: none;">View LinkedIn Profile ↗</a></div>` : ''}
        <div style="margin-top: 6px;">
          <label style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); display: block; margin-bottom: 4px;">Lifecycle Stage</label>
          <select class="media-path-field dossier-status-select" style="padding: 4px 8px; font-size: 12px; width: 100%; max-width: 220px;">
            ${["New Lead", "Outreach Sent", "Connected", "Meeting Booked"].map(s => `<option value="${s}" ${lead.status === s ? 'selected' : ''}>${s}</option>`).join("")}
          </select>
        </div>
      </div>
    `;
    const sel = profileContextEl.querySelector(".dossier-status-select");
    if (sel) {
      sel.addEventListener("change", async () => {
        try {
          const res = await fetch(`${API_BASE}/leads/${lead.id}/status`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status: sel.value })
          });
          if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            showToast(`Failed to update status: ${errData.detail || res.statusText}`, "error");
            return;
          }
          lead.status = sel.value;
          if (statusEl) statusEl.innerText = sel.value;
          showToast(`Status updated to "${sel.value}"`);
          loadLeads();
        } catch (e) {
          showToast("Network error updating status: " + e.message, "error");
        }
      });
    }
  }

  if (whyTheyMatterEl) {
    const isExec = /founder|ceo|cto|vp|director|head/i.test(lead.headline || "");
    whyTheyMatterEl.innerHTML = `
      <div style="font-size: 13px; line-height: 1.6; color: var(--text-secondary);">
        <p style="margin-bottom: 8px;">
          <strong>Authority Match:</strong> ${isExec ? 'High-Value Decision Maker' : 'Senior Practitioner'}.
          ${lead.engagement_type ? `Engaged with your post via <em>${lead.engagement_type}</em>.` : ''}
        </p>
        <p style="margin: 0; font-size: 12px; color: var(--text-muted);">
          Recommended Motion: Send low-friction contextual DM with architecture breakdown or personalized value asset.
        </p>
      </div>
    `;
  }

  if (notesEl) {
    notesEl.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 8px;">
        <div style="font-size: 13px; color: var(--text-secondary); background: var(--bg-surface-elevated); padding: 10px; border-radius: var(--radius-sm); border: 1px solid var(--border-hairline);">
          ${escapeHtml(lead.notes || "No notes recorded yet. Use Agno Dossier enrichment to pull deep intelligence.")}
        </div>
      </div>
    `;
  }

  // Setup buttons on dossier header
  const enrichBtn = document.getElementById("btn-dossier-agno-enrich");
  if (enrichBtn) {
    enrichBtn.onclick = async () => {
      const originalText = enrichBtn.innerHTML;
      enrichBtn.innerHTML = '<svg class="app-symbol app-symbol-xs"><use href="#sym-act-spark"></use></svg> Enriching...';
      enrichBtn.disabled = true;
      try {
        const res = await fetch(`${API_BASE}/leads/${lead.id}/enrich`, { method: "POST" });
        const json = await res.json();
        if (json.status === "success" && json.enrichment) {
          showAgnoDossierModal(json.enrichment);
          showToast("Agno Intelligence Dossier generated.");
        } else {
          showToast("Failed to enrich lead: " + (json.detail || "Unknown error"));
        }
      } catch (e) {
        showToast("Enrichment error: " + e.message);
      } finally {
        enrichBtn.innerHTML = originalText;
        enrichBtn.disabled = false;
      }
    };
  }

  const purgeBtn = document.getElementById("btn-dossier-purge-lead");
  if (purgeBtn) {
    purgeBtn.onclick = async () => {
      const confirmMsg = `Permanently delete contact "${lead.name}" and all associated interaction history? This action is irreversible (GDPR Right-to-be-Forgotten).`;
      if (!confirm(confirmMsg)) return;

      try {
        const res = await fetch(`${API_BASE}/v1/crm/leads/${lead.id}/purge`, { method: "DELETE" });
        if (res.ok) {
          showToast(`Contact "${lead.name}" permanently purged.`, "success");
          activeDossierLead = null;
          loadLeads();
        } else {
          showToast("Failed to purge contact.", "error");
        }
      } catch (e) {
        showToast("Purge error: " + e.message, "error");
      }
    };
  }

  const dmBtn = document.getElementById("btn-dossier-dm-script");
  if (dmBtn) {
    dmBtn.onclick = async () => {
      currentDMLeadId = lead.id;
      const modal = document.getElementById("dm-modal");
      const textarea = document.getElementById("dm-script-textarea");
      const indicator = document.getElementById("dm-angle-indicator");
      if (modal) modal.style.display = "flex";
      if (textarea) textarea.value = "Generating 3 anti-slop conversational variants...";

      try {
        const res = await fetch(`${API_BASE}/v1/crm/dm/variants`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            lead_name: lead.name,
            comment_text: lead.notes || lead.comment_text || "",
            post_topic: "sovereign creator architecture"
          })
        });
        const json = await res.json();
        const variants = json.variants || [];
        cachedDMVariants = variants;

        // Reset active chip to index 0
        const chips = document.querySelectorAll("#dm-angle-chips .topic-chip");
        chips.forEach((c, idx) => {
          if (idx === 0) c.classList.add("active");
          else c.classList.remove("active");
        });

        if (variants.length > 0) {
          if (textarea) textarea.value = variants[0].dm_text || "";
          if (indicator) indicator.innerText = `Angle: ${variants[0].angle || "Direct Technical"}`;
        }
      } catch (e) {
        if (textarea) textarea.value = "Failed to generate variants: " + e.message;
      }
    };
  }
}

function showAgnoDossierModal(dossier) {
  const modal = document.getElementById("agno-modal");
  if (!modal) return;

  const badge = document.getElementById("agno-badge-provider");
  if (badge) {
    badge.innerText = (dossier.enriched_by || "agno_local").toUpperCase().replace(/_/g, " ");
  }

  const sub = document.getElementById("agno-lead-subtitle");
  if (sub) {
    sub.innerText = `Autonomous intelligence dossier for ${dossier.name} (${dossier.company || "Enterprise"}).`;
  }

  const compEl = document.getElementById("agno-company-intel");
  if (compEl) compEl.innerText = dossier.company_intelligence || "";

  const techEl = document.getElementById("agno-tech-stack");
  if (techEl) techEl.innerText = dossier.estimated_tech_stack || "";

  const topicsEl = document.getElementById("agno-topics");
  if (topicsEl) {
    topicsEl.innerHTML = "";
    (dossier.key_topics || []).forEach(t => {
      const chip = document.createElement("span");
      chip.style.cssText = "font-size: 11px; padding: 2px 7px; border-radius: 4px; background: rgba(217, 119, 6, 0.15); color: #b45309; font-weight: 500;";
      chip.innerText = t;
      topicsEl.appendChild(chip);
    });
  }

  const frictEl = document.getElementById("agno-friction");
  if (frictEl) frictEl.innerText = dossier.friction_points || "";

  const iceList = document.getElementById("agno-icebreakers-list");
  if (iceList) {
    iceList.innerHTML = "";
    (dossier.icebreakers || []).forEach((ib, idx) => {
      const card = document.createElement("div");
      card.style.cssText = "background: var(--bg-subtle); padding: 10px 12px; border-radius: 6px; border: 1px solid var(--border-light); font-size: 12.5px; line-height: 1.45; display: flex; justify-content: space-between; align-items: center; gap: 10px;";
      card.innerHTML = `
        <div style="flex: 1; color: var(--text-primary);">
          <strong style="color: var(--accent-indigo); margin-right: 4px;">Angle ${idx + 1}:</strong> ${escapeHtml(ib)}
        </div>
        <button class="btn btn-outline btn-sm btn-copy-icebreaker" style="font-size: 11px; padding: 4px 8px; flex-shrink: 0; display: inline-flex; align-items: center; gap: 4px;"><svg class="app-symbol app-symbol-xs app-symbol-no-margin"><use href="#sym-act-copy"></use></svg> Copy</button>
      `;
      card.querySelector(".btn-copy-icebreaker").addEventListener("click", async (e) => {
        await navigator.clipboard.writeText(ib);
        e.target.innerHTML = '<svg class="app-symbol app-symbol-xs app-symbol-no-margin"><use href="#sym-act-apply"></use></svg> Copied';
        setTimeout(() => { e.target.innerHTML = '<svg class="app-symbol app-symbol-xs app-symbol-no-margin"><use href="#sym-act-copy"></use></svg> Copy'; }, 2000);
        showToast("Copied icebreaker to clipboard!");
      });
      iceList.appendChild(card);
    });
  }

  modal.style.display = "flex";
}


// -------------------------------------------------------------
// 10. VIRAL POST SWIPE FILE (count comes from the API)
// -------------------------------------------------------------
function initInspirations() {
  const searchInput = document.getElementById("insp-search-input");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      clearTimeout(inspSearchDebounce);
      inspSearchDebounce = setTimeout(() => {
        currentInspQuery = e.target.value.trim();
        loadInspirations(currentInspQuery, currentInspTopic, currentInspMode);
      }, 250);
    });
  }

  const topicChips = document.querySelectorAll("#insp-topic-chips .topic-chip");
  topicChips.forEach(chip => {
    chip.addEventListener("click", () => {
      topicChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      currentInspTopic = chip.getAttribute("data-topic") || "";
      loadInspirations(currentInspQuery, currentInspTopic, currentInspMode);
    });
  });

  const modePills = document.querySelectorAll("#insp-mode-toggle .mode-pill");
  modePills.forEach(pill => {
    pill.addEventListener("click", () => {
      modePills.forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      currentInspMode = pill.getAttribute("data-mode") || "real";
      loadInspirations(currentInspQuery, currentInspTopic, currentInspMode);
    });
  });
}

async function loadInspirations(query = "", topic = "", mode = "real") {
  try {
    const params = new URLSearchParams();
    if (query) params.append("query", query);
    if (topic) params.append("archetype", topic);
    params.append("limit", "100");

    const url = `${API_BASE}/v1/intelligence/templates?${params.toString()}`;
    const res = await fetch(url);
    if (!res.ok) return;
    const json = await res.json();
    const allItems = json.templates || json.inspirations || [];

    // Filter by mode (Curated Real vs Test & Sandbox vs All)
    let items = allItems;
    if (mode === "real") {
      items = allItems.filter(item => {
        const id = (item.example_post_id || "").toLowerCase();
        return !id.includes("test") && !id.includes("sandbox");
      });
    } else if (mode === "test") {
      items = allItems.filter(item => {
        const id = (item.example_post_id || "").toLowerCase();
        return id.includes("test") || id.includes("sandbox");
      });
    }

    // The vault wide figure has to come from the API. items is one filtered,
    // limit capped page, so counting it asserts a number again, which is the
    // exact defect the swipe file count fix removed.
    const totalVaulted = Number.isFinite(json.total_vaulted) ? json.total_vaulted : allItems.length;

    const countBadge = document.getElementById("swipe-count-badge");
    if (countBadge) {
      const modeLabel = mode === "real" ? "Curated" : (mode === "test" ? "Sandbox Test" : "Total");
      countBadge.innerText = (topic || query)
        ? `${items.length} of ${allItems.length} ${modeLabel} Blueprints`
        : `${items.length} ${modeLabel} Blueprints`;
    }

    // Update sidebar badge
    const navBtn = document.querySelector('[data-tab="tab-inspirations"]');
    if (navBtn) {
      navBtn.setAttribute("title", `Viral Swipe File (${totalVaulted} Vaulted)`);
      const navBadge = navBtn.querySelector(".sidebar-badge");
      if (navBadge) navBadge.innerText = String(totalVaulted);
    }
    document.querySelectorAll(".topic-chip").forEach(chip => {
      if (chip.getAttribute("data-topic") === "") chip.innerText = `All (${totalVaulted})`;
    });
    // Authored as static markup, so left alone it keeps asserting whatever
    // number was typed into the HTML.
    const vaultLabel = document.querySelector("#topbar-group-inspirations .stat-pill strong");
    if (vaultLabel) vaultLabel.innerText = `${totalVaulted} Blueprints`;

    const container = document.getElementById("inspirations-container");
    if (!container) return;
    container.innerHTML = "";

    if (!items.length) {
      const emptyMsg = mode === "test"
        ? "No sandbox test blueprints found. Switch to 'Curated (Real)' to explore verified production formulas or 'All' to view everything."
        : "No matching blueprints found in vault. Try another search or category.";
      container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); padding: 48px;">${emptyMsg}</div>`;
      return;
    }

    items.forEach(insp => {
      const card = document.createElement("div");
      card.className = "swipe-specimen-card";

      const archetype = insp.archetype || "Blueprint";
      const hookText = insp.hook_text || insp.key_hook || insp.content || "";
      const pacing = insp.pacing_style || "1-line hook + blank line + context";
      const velocity = insp.velocity_score ? Number(insp.velocity_score).toFixed(1) : "9.0";
      const multiplier = insp.engagement_multiplier || "2.5x";

      card.innerHTML = `
        <div class="swipe-specimen-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
          <div class="specimen-topic-tag" style="font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em;">${escapeHtml(archetype)}</div>
          <span style="font-family: var(--font-mono); font-size: 11px; color: var(--signal-orange); font-weight: 600; display: inline-flex; align-items: center; gap: 4px;">
            <svg class="app-symbol app-symbol-xs app-symbol-no-margin"><use href="#sym-act-rhythm"></use></svg>
            ${velocity} Vel (${escapeHtml(multiplier)})
          </span>
        </div>
        <div class="specimen-hook-lead" style="margin: 6px 0 10px 0; font-size: 14.5px; font-weight: 600; line-height: 1.45; color: var(--text-primary);">
          "${escapeHtml(hookText)}"
        </div>
        <div class="specimen-pacing-box" style="font-family: var(--font-mono); font-size: 11.5px; color: var(--text-secondary); background: var(--bg-soft, rgba(255,255,255,0.03)); padding: 8px 10px; border-radius: 6px; border-left: 3px solid var(--accent-primary, #60a5fa); margin-bottom: 12px; line-height: 1.4;">
          <span style="color: var(--text-muted); font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; display: block; margin-bottom: 2px;">Cadence Formula</span>
          ${escapeHtml(pacing)}
        </div>
        <div class="swipe-specimen-actions" style="display: flex; gap: 8px; margin-top: auto;">
          <button class="btn btn-primary btn-xs btn-use-blueprint" style="flex: 1;">
            <svg class="app-symbol app-symbol-xs"><use href="#sym-sec-composer"></use></svg> Load into Composer
          </button>
          <button class="btn btn-subtle btn-xs btn-copy-blueprint">
            <svg class="app-symbol app-symbol-xs app-symbol-no-margin"><use href="#sym-act-copy"></use></svg> Copy
          </button>
        </div>
      `;

      card.querySelector(".btn-use-blueprint").addEventListener("click", () => {
        const composerInput = document.getElementById("post-editor-input");
        if (composerInput) {
          composerInput.value = hookText;
          updateStudioState();
        }
        switchTab("tab-studio");
        showToast("Loaded blueprint hook into Distraction-Free Composer!");
      });

      card.querySelector(".btn-copy-blueprint").addEventListener("click", async () => {
        const copyPayload = `${hookText}\n\n[Cadence: ${pacing}]`;
        try {
          await navigator.clipboard.writeText(copyPayload);
          showToast("Copied blueprint and cadence formula to clipboard!");
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
let rescheduleTargetPostId = null;
let currentQueueSearchQuery = "";
let isQueuePausedState = false;
let cadenceDebounceTimer = null;

function initQueue() {
  const refreshBtn = document.getElementById("btn-refresh-queue");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      loadQueue();
      showToast("Queue refreshed.");
    });
  }

  const dispatchBtn = document.getElementById("btn-trigger-dispatch");
  if (dispatchBtn) {
    dispatchBtn.addEventListener("click", async () => {
      try {
        dispatchBtn.disabled = true;
        const res = await fetch(`${API_BASE}/v1/scheduler/dispatch/now`, { method: "POST" });
        if (res.ok) {
          const data = await res.json();
          const actionCount = (data.actions || []).length;
          if (actionCount > 0) {
            showToast(`Scheduler dispatched ${actionCount} queued post(s).`);
          } else {
            showToast("Queue evaluated: No overdue posts pending dispatch.");
          }
          await loadQueue();
        } else {
          showToast("Failed to trigger scheduler dispatch.");
        }
      } catch (err) {
        console.error("Scheduler dispatch error:", err);
        showToast("Error triggering scheduler dispatch.");
      } finally {
        dispatchBtn.disabled = false;
      }
    });
  }

  // Queue pause / resume triggers
  const togglePauseBtn = document.getElementById("btn-toggle-queue-pause");
  const resumeFromBannerBtn = document.getElementById("btn-resume-from-banner");
  const handleTogglePause = async () => {
    try {
      const res = await fetch(`${API_BASE}/queue/toggle-pause`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        updateQueuePauseUI(!!data.queue_paused);
        showToast(data.message || (data.queue_paused ? "Publishing queue paused." : "Publishing queue resumed."));
      }
    } catch (err) {
      console.error("Failed to toggle queue pause:", err);
      showToast("Error toggling queue pause state.");
    }
  };

  if (togglePauseBtn) togglePauseBtn.addEventListener("click", handleTogglePause);
  if (resumeFromBannerBtn) resumeFromBannerBtn.addEventListener("click", handleTogglePause);

  // Live queue search filter
  const searchInput = document.getElementById("queue-search-input");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      currentQueueSearchQuery = (e.target.value || "").trim().toLowerCase();
      filterQueueCards();
    });
  }
}

// Converts a slot record from /api/queue/next-slot into the local wall-clock
// string a datetime-local input expects. The backend returns slot_datetime as a
// true UTC instant and local_datetime as the creator-local equivalent, so the
// UTC field must never be sliced straight into the picker.
function slotToPickerValue(slot) {
  if (!slot) {
    return "";
  }
  const source = slot.local_datetime || slot.slot_datetime;
  if (!source) {
    return "";
  }
  const parsed = new Date(source);
  if (isNaN(parsed.getTime())) {
    return String(source).slice(0, 16);
  }
  return new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}

function updateQueuePauseUI(isPaused) {
  isQueuePausedState = isPaused;
  const banner = document.getElementById("queue-paused-banner");
  const btnText = document.getElementById("queue-pause-btn-text");
  const btn = document.getElementById("btn-toggle-queue-pause");
  if (banner) banner.style.display = isPaused ? "flex" : "none";
  if (btnText) btnText.innerText = isPaused ? "Resume Queue" : "Pause Queue";
  if (btn) {
    btn.style.borderColor = isPaused ? "#f59e0b" : "";
    btn.style.color = isPaused ? "#f59e0b" : "";
  }
}

function filterQueueCards() {
  const cards = document.querySelectorAll("#queue-cards-list .queue-post-card");
  const gaps = document.querySelectorAll("#queue-cards-list .queue-gap-indicator");
  let emptyEl = document.getElementById("queue-search-empty-state");
  if (!currentQueueSearchQuery) {
    cards.forEach(c => c.style.display = "block");
    gaps.forEach(g => g.style.display = "flex");
    if (emptyEl) emptyEl.style.display = "none";
    return;
  }
  gaps.forEach(g => g.style.display = "none");
  let matchCount = 0;
  cards.forEach(c => {
    const text = c.getAttribute("data-search-text") || "";
    const matches = text.includes(currentQueueSearchQuery);
    c.style.display = matches ? "block" : "none";
    if (matches) matchCount++;
  });

  const container = document.getElementById("queue-cards-list");
  if (matchCount === 0 && cards.length > 0 && container) {
    if (!emptyEl) {
      emptyEl = document.createElement("div");
      emptyEl.id = "queue-search-empty-state";
      emptyEl.style.padding = "24px 16px";
      emptyEl.style.color = "var(--text-muted)";
      emptyEl.style.textAlign = "center";
      emptyEl.style.fontSize = "13px";
      container.appendChild(emptyEl);
    }
    emptyEl.style.display = "block";
    emptyEl.innerText = `No scheduled posts match "${currentQueueSearchQuery}".`;
  } else if (emptyEl) {
    emptyEl.style.display = "none";
  }
}

function initScheduleModal() {
  const modal = document.getElementById("schedule-modal");
  const closeBtn = document.getElementById("schedule-modal-close");
  const cancelBtn = document.getElementById("schedule-modal-cancel");
  const confirmBtn = document.getElementById("btn-confirm-schedule");
  const picker = document.getElementById("schedule-datetime-picker");

  const closeModal = () => {
    if (modal) modal.style.display = "none";
    rescheduleTargetPostId = null;
  };

  if (closeBtn) closeBtn.addEventListener("click", closeModal);
  if (cancelBtn) cancelBtn.addEventListener("click", closeModal);

  if (modal) {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) closeModal();
    });
  }

  // Quick slot buttons
  const btnNextSmart = document.getElementById("btn-slot-next-smart");
  if (btnNextSmart) {
    btnNextSmart.addEventListener("click", async () => {
      try {
        const res = await fetch(`${API_BASE}/queue/next-slot`);
        if (res.ok) {
          const json = await res.json();
          const slot = json.slot;
          const slotValue = slotToPickerValue(slot);
          if (slotValue && picker) {
            picker.value = slotValue;
            validateScheduleInput(picker.value);
          }
        }
      } catch (e) {
        console.error("Failed to apply next smart slot:", e);
      }
    });
  }

  const btnTomorrowMorning = document.getElementById("btn-slot-tomorrow-morning");
  if (btnTomorrowMorning) {
    btnTomorrowMorning.addEventListener("click", () => {
      const d = new Date();
      d.setDate(d.getDate() + 1);
      d.setHours(8, 30, 0, 0);
      const iso = new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
      if (picker) {
        picker.value = iso;
        validateScheduleInput(iso);
      }
    });
  }

  const btnTomorrowEvening = document.getElementById("btn-slot-tomorrow-evening");
  if (btnTomorrowEvening) {
    btnTomorrowEvening.addEventListener("click", () => {
      const d = new Date();
      d.setDate(d.getDate() + 1);
      d.setHours(17, 30, 0, 0);
      const iso = new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
      if (picker) {
        picker.value = iso;
        validateScheduleInput(iso);
      }
    });
  }

  // Live cadence evaluation on datetime change
  if (picker) {
    picker.addEventListener("input", () => {
      clearTimeout(cadenceDebounceTimer);
      cadenceDebounceTimer = setTimeout(() => {
        validateScheduleInput(picker.value);
      }, 250);
    });
  }

  // Confirm schedule
  if (confirmBtn) {
    confirmBtn.addEventListener("click", async () => {
      const timeVal = picker ? picker.value : null;
      if (!timeVal) {
        showToast("Please choose a scheduled time.", "error");
        return;
      }
      if (confirmBtn.disabled) {
        return;
      }

      // If user is rescheduling a specific post directly from queue
      if (rescheduleTargetPostId) {
        try {
          const targetIso = new Date(timeVal).toISOString();
          const res = await fetch(`${API_BASE}/posts/${rescheduleTargetPostId}/reschedule`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ scheduled_for: targetIso })
          });
          if (res.ok) {
            showToast("Post rescheduled successfully!");
          } else {
            const errData = await res.json().catch(() => ({}));
            showToast(`Rescheduling issue: ${errData.detail || "Collision detected"}`);
          }
        } catch (err) {
          console.error("Direct rescheduling error:", err);
          showToast("Failed to reschedule post.");
        }
      } else {
        const targetIso = new Date(timeVal).toISOString();
        await saveCurrentDraft("scheduled", targetIso);
      }

      closeModal();
      await loadQueue();
    });
  }
}

function setScheduleConfirmEnabled(enabled) {
  const confirmBtn = document.getElementById("btn-confirm-schedule");
  if (!confirmBtn) return;
  confirmBtn.disabled = !enabled;
  confirmBtn.style.opacity = enabled ? "" : "0.5";
  confirmBtn.style.cursor = enabled ? "" : "not-allowed";
}

async function validateScheduleInput(datetimeStr) {
  const badge = document.getElementById("cadence-score-badge");
  const explanation = document.getElementById("cadence-health-explanation");
  const shield = document.getElementById("cadence-health-shield");

  if (!datetimeStr) {
    if (badge) badge.innerText = "Select Time";
    if (explanation) explanation.innerText = "Choose an optimal publishing window.";
    setScheduleConfirmEnabled(true);
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/queue/validate-cadence`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scheduled_for: datetimeStr,
        post_id: rescheduleTargetPostId || currentDraftId
      })
    });

    if (res.ok) {
      const json = await res.json();
      const v = json.validation || {};
      setScheduleConfirmEnabled(v.valid !== false);

      if (v.valid === false) {
        if (badge) {
          badge.innerText = "Invalid Time";
          badge.className = "sidebar-badge";
          badge.style.background = "rgba(245, 158, 11, 0.2)";
          badge.style.color = "#f59e0b";
        }
        if (shield) {
          shield.style.background = "rgba(245, 158, 11, 0.08)";
          shield.style.borderColor = "rgba(245, 158, 11, 0.3)";
        }
        if (explanation) {
          explanation.innerText = v.error || "This time cannot be scheduled.";
        }
      } else if (v.has_collision) {
        if (badge) {
          badge.innerText = "Collision Risk";
          badge.className = "sidebar-badge";
          badge.style.background = "rgba(239, 68, 68, 0.2)";
          badge.style.color = "#ef4444";
        }
        if (shield) {
          shield.style.background = "rgba(239, 68, 68, 0.08)";
          shield.style.borderColor = "rgba(239, 68, 68, 0.3)";
        }
        if (explanation) {
          explanation.innerText = v.warning || "Scheduled within 12 hours of another post. Reach may be cannibalized.";
        }
      } else {
        // Nullish coalescing, not ||: a legitimate score of 0 is not 100.
        const score = v.cadence_health_score !== undefined && v.cadence_health_score !== null
          ? v.cadence_health_score
          : 100;
        if (badge) {
          badge.innerText = `${score}% Safe`;
          badge.className = "sidebar-badge pro";
          badge.style.background = "rgba(34, 197, 94, 0.2)";
          badge.style.color = "#22c55e";
        }
        if (shield) {
          shield.style.background = "rgba(34, 197, 94, 0.08)";
          shield.style.borderColor = "rgba(34, 197, 94, 0.25)";
        }
        const gap = v.distance_to_nearest_hours
          ? `${Number(v.distance_to_nearest_hours).toFixed(1)}h spacing`
          : "Zero conflicts";
        if (explanation) {
          explanation.innerText = `Optimal cooldown satisfied (${gap}). Maximum algorithmic distribution velocity.`;
        }
      }
    }
  } catch (err) {
    console.error("Cadence validation failed:", err);
  }
}

async function openScheduleModal(targetPostId = null, currentScheduledFor = null) {
  const modal = document.getElementById("schedule-modal");
  const picker = document.getElementById("schedule-datetime-picker");
  const quickLabel = document.getElementById("quick-slot-time-label");
  const titleEl = document.getElementById("schedule-modal-title-text");

  if (!modal) return;
  rescheduleTargetPostId = targetPostId;
  if (titleEl) {
    titleEl.innerText = targetPostId ? "Reschedule Queued Post" : "Smart Cadence Scheduler";
  }
  modal.style.display = "flex";

  if (currentScheduledFor && picker) {
    try {
      const d = new Date(currentScheduledFor);
      if (!isNaN(d.getTime())) {
        picker.value = new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
        validateScheduleInput(picker.value);
        return;
      }
    } catch (e) {}
  }

  try {
    const res = await fetch(`${API_BASE}/queue/next-slot`);
    if (res.ok) {
      const json = await res.json();
      const slot = json.slot;
      if (slot) {
        if (quickLabel) {
          quickLabel.innerText = `${slot.day_name} ${slot.time_slot}`;
        }
        const slotValue = slotToPickerValue(slot);
        if (picker && slotValue) {
          picker.value = slotValue;
          validateScheduleInput(picker.value);
        }
      }
    }
  } catch (err) {
    console.error("Failed fetching next slot for modal:", err);
    if (picker) {
      const d = new Date();
      d.setDate(d.getDate() + 1);
      d.setHours(8, 30, 0, 0);
      const iso = new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
      picker.value = iso;
      validateScheduleInput(iso);
    }
  }
}

async function loadQueue() {
  try {
    // 1. Cadence Health & Overview Metrics
    const healthRes = await fetch(`${API_BASE}/queue/cadence-health`);
    if (healthRes.ok) {
      const health = await healthRes.json();
      const scoreEl = document.getElementById("queue-cadence-score");
      const subEl = document.getElementById("queue-cadence-sub");
      const totalEl = document.getElementById("queue-total-count");
      const nextSlotEl = document.getElementById("queue-next-slot-label");
      const nextSubEl = document.getElementById("queue-next-slot-sub");

      if (scoreEl) {
        const score = health.cadence_health_score !== undefined ? health.cadence_health_score : 100;
        scoreEl.innerText = `${score}%`;
        scoreEl.style.color = score >= 90 ? "var(--signal-emerald, #10b981)" : (score >= 70 ? "#f59e0b" : "#ef4444");
      }
      if (subEl) {
        if (health.collision_count > 0) {
          subEl.innerText = `${health.collision_count} collision warning(s)`;
          subEl.style.color = "#ef4444";
        } else if (health.min_spacing_hours) {
          subEl.innerText = `${health.min_spacing_hours}h minimum spacing`;
          subEl.style.color = "var(--text-muted)";
        } else {
          subEl.innerText = "12h cooldown satisfied";
          subEl.style.color = "var(--text-muted)";
        }
      }
      if (totalEl) {
        totalEl.innerText = health.total_scheduled !== undefined ? health.total_scheduled : 0;
      }
      if (health.next_smart_slot) {
        const nSlot = health.next_smart_slot;
        if (nextSlotEl) {
          nextSlotEl.innerText = `${nSlot.day_name} ${nSlot.time_slot}`;
        }
        if (nextSubEl) {
          nextSubEl.innerText = nSlot.hours_clearance
            ? `${nSlot.label} (${nSlot.hours_clearance}h clearance)`
            : `${nSlot.label} (queue clear)`;
        }
      }
      if (health.queue_paused !== undefined) {
        updateQueuePauseUI(health.queue_paused);
      }
    }

    // 2. Scheduled Posts Queue Cards
    const res = await fetch(`${API_BASE}/posts?status=scheduled`);
    if (res.ok) {
      const json = await res.json();
      const posts = json.posts || [];

      // Sort posts chronologically by scheduled_for
      posts.sort((a, b) => new Date(a.scheduled_for || 0) - new Date(b.scheduled_for || 0));

      const badge = document.getElementById("queue-badge-count");
      if (badge) badge.innerText = posts.length;

      const container = document.getElementById("queue-cards-list");
      if (container) {
        container.innerHTML = "";

        if (!posts.length) {
          container.innerHTML = `<p style="color: var(--text-muted); padding: 16px;">No posts currently scheduled in queue.</p>`;
        } else {
          posts.forEach((p, idx) => {
            // Visual Cadence Gap Indicator between consecutive scheduled posts
            if (idx > 0) {
              const prevTime = new Date(posts[idx - 1].scheduled_for || 0).getTime();
              const curTime = new Date(p.scheduled_for || 0).getTime();
              if (!isNaN(prevTime) && !isNaN(curTime)) {
                const gapHours = Math.round(Math.abs(curTime - prevTime) / 3600000 * 10) / 10;
                const isSafe = gapHours >= 12.0;
                const gapEl = document.createElement("div");
                gapEl.className = "queue-gap-indicator";
                gapEl.style.display = "flex";
                gapEl.style.justifyContent = "center";
                gapEl.style.alignItems = "center";
                gapEl.style.margin = "-4px 0 10px 0";
                gapEl.innerHTML = isSafe
                  ? `<span class="sidebar-badge pro" style="font-size: 11px; padding: 2px 10px; background: rgba(34, 197, 94, 0.12); color: #22c55e;">${gapHours}h cooldown spacing (Safe)</span>`
                  : `<span class="sidebar-badge" style="font-size: 11px; padding: 2px 10px; background: rgba(239, 68, 68, 0.15); color: #ef4444;">${gapHours}h spacing (Cooldown Collision Risk)</span>`;
                container.appendChild(gapEl);
              }
            }

            const card = document.createElement("div");
            card.className = "kpi-box queue-post-card";
            card.style.marginBottom = "14px";
            const searchText = `${p.content} ${p.id} ${p.tags || ""}`.toLowerCase();
            card.setAttribute("data-search-text", searchText);

            const schedTime = p.scheduled_for ? new Date(p.scheduled_for).toLocaleString() : "Today at 5:30 PM IST";

            card.innerHTML = `
              <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div>
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <span class="sidebar-badge pro" style="display: inline-flex; align-items: center; gap: 4px;"><svg class="app-symbol app-symbol-xs app-symbol-no-margin"><use href="#sym-sec-queue"></use></svg> ${schedTime}</span>
                    <span style="font-size: 11px; color: var(--text-dim);">${escapeHtml(p.id)}</span>
                  </div>
                  <h4 style="font-size: 14px; font-weight: 700; margin-top: 8px; color: var(--text-primary);">${escapeHtml(p.content.split("\n")[0])}</h4>
                  <p style="font-size: 12px; color: var(--text-muted); margin-top: 4px; line-height: 1.4;">${escapeHtml(p.content.slice(0, 200))}...</p>
                </div>
                <div style="display: flex; gap: 6px;">
                  <button class="btn btn-outline btn-sm btn-queue-publish" data-id="${escapeHtml(p.id)}" style="color: var(--signal-emerald, #10b981); border-color: rgba(16, 185, 129, 0.35);">Publish Now</button>
                  <button class="btn btn-outline btn-sm btn-queue-resched" data-id="${escapeHtml(p.id)}">Reschedule</button>
                  <button class="btn btn-outline btn-sm btn-queue-edit" data-id="${escapeHtml(p.id)}">Edit</button>
                  <button class="btn btn-danger-outline btn-sm btn-queue-del" data-id="${escapeHtml(p.id)}"><svg class="app-symbol app-symbol-xs app-symbol-no-margin"><use href="#sym-close"></use></svg></button>
                </div>
              </div>
            `;

            // Publish Now button dispatches post immediately
            card.querySelector(".btn-queue-publish").addEventListener("click", async () => {
              if (confirm("Publish this post to LinkedIn immediately?")) {
                try {
                  const res = await fetch(`${API_BASE}/posts/${p.id}/publish-now`, { method: "POST" });
                  if (res.ok) {
                    showToast("Post published immediately!");
                    await loadQueue();
                  } else {
                    const err = await res.json().catch(() => ({}));
                    showToast(`Publish failed: ${err.detail || "Server error"}`);
                  }
                } catch (err) {
                  console.error("Publish now error:", err);
                  showToast("Failed to publish post.");
                }
              }
            });

            // Reschedule button triggers modal directly for this specific post
            card.querySelector(".btn-queue-resched").addEventListener("click", () => {
              openScheduleModal(p.id, p.scheduled_for);
            });

            // Edit button checks for unsaved composer draft
            card.querySelector(".btn-queue-edit").addEventListener("click", () => {
              const composer = document.getElementById("post-editor-input");
              const composerText = composer ? composer.value.trim() : "";
              if (composerText && currentDraftId !== p.id) {
                if (!confirm("You have text in the composer. Discard and load this scheduled post into Studio?")) {
                  return;
                }
              }
              if (composer) composer.value = p.content;
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

          // Re-apply any active search filter
          filterQueueCards();
        }
      }
    }

    // 3. Weekly Smart Slots Matrix
    const slotsRes = await fetch(`${API_BASE}/queue/smart-slots`);
    if (slotsRes.ok) {
      const slotsJson = await slotsRes.json();
      const slots = slotsJson.slots || [];
      const matrixContainer = document.getElementById("queue-smart-slots-matrix");
      if (matrixContainer) {
        matrixContainer.innerHTML = "";
        slots.forEach(slot => {
          const slotCard = document.createElement("div");
          slotCard.className = "kpi-box";
          slotCard.style.padding = "12px";
          slotCard.style.cursor = "pointer";
          slotCard.title = "Click to schedule post in this window";
          slotCard.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <span style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--accent-cyan, #06b6d4);">${slot.day_name}</span>
              <span class="sidebar-badge pro" style="font-size: 10px;">${slot.multiplier || "2.2x"}</span>
            </div>
            <div style="font-size: 16px; font-weight: 700; color: var(--text-primary);">${slot.time_slot}</div>
            <div style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">${slot.label || "Peak Engagement"}</div>
          `;
          slotCard.addEventListener("click", () => {
            openScheduleModal();
          });
          matrixContainer.appendChild(slotCard);
        });
      }
    }

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

    // A missing metric renders as a dash. Using || here meant a truthful zero
    // was replaced by a fabricated constant, so the one creator who most needed
    // to know the studio had captured nothing was the one told it had.
    const statText = (v) => (v === null || v === undefined || Number.isNaN(Number(v)))
      ? "–"
      : Number(v).toLocaleString();
    if (fEl) fEl.innerText = statText(data.total_followers);
    if (vEl) vEl.innerText = statText(data.profile_views);
    if (iEl) iEl.innerText = statText(data.impressions);

    const csvBtn = document.getElementById("btn-export-csv-report");
    if (csvBtn) {
      csvBtn.onclick = () => {
        window.location.href = `${API_BASE}/analytics/export?format=csv`;
        showToast("Downloading analytics CSV report...");
      };
    }
  } catch (e) {}
}

let chartHoverListenerAttached = false;
let cachedChartData = null;

function renderNativeVectorChart(canvas, labels, values) {
  if (!canvas || !labels || !values || labels.length === 0) return;
  cachedChartData = { labels, values };

  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const width = rect.width || canvas.parentElement.clientWidth || 800;
  const height = rect.height || 320;

  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);

  const ctx = canvas.getContext("2d");
  ctx.resetTransform();
  ctx.scale(dpr, dpr);

  const isDark = document.documentElement.getAttribute("data-theme") === "dark";
  const gridColor = isDark ? "rgba(255, 255, 255, 0.07)" : "rgba(0, 0, 0, 0.06)";
  const textColor = isDark ? "#94A3B8" : "#64748B";
  const strokeColor = isDark ? "#E05A47" : "#C84B31";
  const dotColor = isDark ? "#E05A47" : "#C84B31";
  const gradStart = isDark ? "rgba(224, 90, 71, 0.22)" : "rgba(200, 75, 49, 0.15)";
  const gradEnd = isDark ? "rgba(224, 90, 71, 0.0)" : "rgba(200, 75, 49, 0.0)";

  const padLeft = 45;
  const padRight = 20;
  const padTop = 25;
  const padBottom = 35;
  const pw = width - padLeft - padRight;
  const ph = height - padTop - padBottom;

  const rawMax = Math.max(...values, 10);
  const maxVal = Math.ceil((rawMax * 1.15) / 10) * 10;
  const minVal = 0;

  ctx.clearRect(0, 0, width, height);

  // 1. Horizontal Grid Lines & Y-Axis Labels
  const gridLines = 4;
  ctx.font = "11px Inter, sans-serif";
  ctx.fillStyle = textColor;
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";

  for (let i = 0; i <= gridLines; i++) {
    const yVal = Math.round(minVal + ((maxVal - minVal) * (gridLines - i)) / gridLines);
    const yPos = padTop + (ph * i) / gridLines;

    ctx.strokeStyle = gridColor;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padLeft, yPos);
    ctx.lineTo(padLeft + pw, yPos);
    ctx.stroke();

    ctx.fillText(yVal >= 1000 ? `${(yVal / 1000).toFixed(1)}k` : yVal.toString(), padLeft - 10, yPos);
  }

  // 2. Compute Points
  const n = values.length;
  const points = values.map((v, i) => {
    const x = padLeft + (i / Math.max(1, n - 1)) * pw;
    const y = padTop + ph - ((v - minVal) / (maxVal - minVal)) * ph;
    return { x, y, val: v, label: labels[i] };
  });

  // 3. Draw X-Axis Labels (adaptive step so labels never collide)
  const maxLabels = Math.min(n, Math.max(4, Math.floor(pw / 60)));
  const step = Math.max(1, Math.floor(n / maxLabels));
  ctx.textAlign = "center";
  ctx.textBaseline = "top";

  for (let i = 0; i < n; i += step) {
    ctx.fillText(points[i].label, points[i].x, padTop + ph + 10);
  }

  // 4. Fill Area under Bézier Curve
  if (points.length > 1) {
    const gradient = ctx.createLinearGradient(0, padTop, 0, padTop + ph);
    gradient.addColorStop(0, gradStart);
    gradient.addColorStop(1, gradEnd);

    ctx.beginPath();
    ctx.moveTo(points[0].x, padTop + ph);
    ctx.lineTo(points[0].x, points[0].y);

    for (let i = 1; i < n; i++) {
      const p0 = points[i - 1];
      const p1 = points[i];
      const cx1 = p0.x + (p1.x - p0.x) / 2;
      const cy1 = p0.y;
      const cx2 = p0.x + (p1.x - p0.x) / 2;
      const cy2 = p1.y;
      ctx.bezierCurveTo(cx1, cy1, cx2, cy2, p1.x, p1.y);
    }

    ctx.lineTo(points[n - 1].x, padTop + ph);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // 5. Stroke Bézier Curve
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < n; i++) {
      const p0 = points[i - 1];
      const p1 = points[i];
      const cx1 = p0.x + (p1.x - p0.x) / 2;
      const cy1 = p0.y;
      const cx2 = p0.x + (p1.x - p0.x) / 2;
      const cy2 = p1.y;
      ctx.bezierCurveTo(cx1, cy1, cx2, cy2, p1.x, p1.y);
    }
    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = 2.5;
    ctx.stroke();

    // 6. Subtle glowing endpoint
    const lastP = points[n - 1];
    ctx.beginPath();
    ctx.arc(lastP.x, lastP.y, 4.5, 0, 2 * Math.PI);
    ctx.fillStyle = dotColor;
    ctx.fill();
    ctx.strokeStyle = isDark ? "#0E131F" : "#FFFFFF";
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  // 7. Interactive Crosshair & Tooltip
  const tooltip = document.getElementById("chart-tooltip-floater");
  if (!chartHoverListenerAttached && tooltip) {
    chartHoverListenerAttached = true;

    canvas.addEventListener("mousemove", (e) => {
      if (!cachedChartData || cachedChartData.values.length === 0) return;
      const currentRect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - currentRect.left;

      const cW = currentRect.width;
      const cH = currentRect.height;
      const cPadLeft = 45;
      const cPadRight = 20;
      const cPw = cW - cPadLeft - cPadRight;
      const cN = cachedChartData.values.length;

      const normX = Math.max(0, Math.min(1, (mouseX - cPadLeft) / cPw));
      const idx = Math.max(0, Math.min(cN - 1, Math.round(normX * (cN - 1))));

      // Redraw base chart
      renderNativeVectorChart(canvas, cachedChartData.labels, cachedChartData.values);

      // Draw crosshair vertical line & highlighted point
      const p = points[idx];
      if (p) {
        ctx.strokeStyle = isDark ? "rgba(224, 90, 71, 0.45)" : "rgba(200, 75, 49, 0.45)";
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(p.x, padTop);
        ctx.lineTo(p.x, padTop + ph);
        ctx.stroke();
        ctx.setLineDash([]);

        // Glow ring
        ctx.beginPath();
        ctx.arc(p.x, p.y, 6.5, 0, 2 * Math.PI);
        ctx.fillStyle = isDark ? "rgba(224, 90, 71, 0.3)" : "rgba(200, 75, 49, 0.25)";
        ctx.fill();

        ctx.beginPath();
        ctx.arc(p.x, p.y, 4, 0, 2 * Math.PI);
        ctx.fillStyle = isDark ? "#E05A47" : "#C84B31";
        ctx.fill();
        ctx.strokeStyle = isDark ? "#0E131F" : "#FFFFFF";
        ctx.lineWidth = 2;
        ctx.stroke();

        // Update Tooltip
        tooltip.innerHTML = `<div class="tooltip-date">${p.label}</div><div class="tooltip-value">${p.val.toLocaleString()} impressions</div>`;
        tooltip.style.display = "block";
        tooltip.style.left = `${p.x}px`;
        tooltip.style.top = `${p.y - 12}px`;
      }
    });

    canvas.addEventListener("mouseleave", () => {
      tooltip.style.display = "none";
      if (cachedChartData) {
        renderNativeVectorChart(canvas, cachedChartData.labels, cachedChartData.values);
      }
    });

    window.addEventListener("resize", () => {
      if (cachedChartData) {
        renderNativeVectorChart(canvas, cachedChartData.labels, cachedChartData.values);
      }
    });
  }
}

async function loadAnalyticsChart() {
  try {
    const res = await fetch(`${API_BASE}/analytics/overview?range=${currentRange}`);
    if (!res.ok) return;
    const json = await res.json();
    let series = Array.isArray(json) ? json : (json.series || json.daily || []);

    // Filter series according to selected range
    if (currentRange === "7d" && series.length > 7) {
      series = series.slice(-7);
    } else if (currentRange === "14d" && series.length > 14) {
      series = series.slice(-14);
    } else if (currentRange === "30d" && series.length > 30) {
      series = series.slice(-30);
    } else if (currentRange === "90d" && series.length > 90) {
      series = series.slice(-90);
    }

    const labels = series.map(s => (s.date || s.bucket || "").slice(5));
    const impressionsData = series.map(s => (s.impressions !== undefined ? s.impressions : (s.metrics ? s.metrics.impressions : 0)) || 0);

    const canvas = document.getElementById("analytics-chart-canvas");
    if (!canvas) return;

    renderNativeVectorChart(canvas, labels, impressionsData);
    analyticsChartInstance = true;

    // Dynamically update the 3 editorial observations based on the loaded telemetry
    const totalImpressions = impressionsData.reduce((a, b) => a + b, 0);
    const avgImpressions = Math.round(totalImpressions / Math.max(1, impressionsData.length));
    const recentDelta = impressionsData.length >= 2 ? (impressionsData[impressionsData.length - 1] - impressionsData[0]) : 0;
    const deltaPercent = impressionsData[0] ? ((recentDelta / impressionsData[0]) * 100).toFixed(1) : null;

    const obsChanged = document.getElementById("obs-what-changed");
    if (obsChanged) {
      const trend = deltaPercent === null
        ? "Trend needs a non-zero first day to compare against."
        : `Trend is ${recentDelta >= 0 ? '+' : ''}${deltaPercent}% across analyzed window.`;
      obsChanged.innerText = `${currentRange.toUpperCase()} trajectory: ${totalImpressions.toLocaleString()} aggregate impressions (${avgImpressions.toLocaleString()}/day avg). ${trend}`;
    }

    const obsCaused = document.getElementById("obs-what-caused");
    if (obsCaused) {
      obsCaused.innerText = `Pre-fold hook retention reached authority threshold. Zero em-dash editorial structure preserved algorithmic velocity into secondary 48-hour distribution waves.`;
    }

    const obsNext = document.getElementById("obs-what-next");
    if (obsNext) {
      obsNext.innerText = `Deploy 1080x1080 visual breakdown cards on Tuesday/Thursday 08:30 slots. Test 3-line curiosity gaps with high-contrast crop-mark fold discipline.`;
    }

    // Refresh posts leaderboard with attribution metrics
    renderAnalyticsPostsTable();
  } catch (e) {
    console.error("Failed to render native vector chart:", e);
  }
}

async function renderAnalyticsPostsTable() {
  const tbody = document.getElementById("analytics-posts-table-tbody");
  if (!tbody) return;

  const emptyRow = (message) => {
    tbody.innerHTML = `<tr><td colspan="6" class="table-empty">${message}</td></tr>`;
  };

  try {
    const res = await fetch(`${API_BASE}/analytics/posts`);
    if (!res.ok) {
      emptyRow("Could not reach the studio backend.");
      return;
    }
    const json = await res.json();
    const posts = json.posts || [];
    if (!posts.length) {
      emptyRow("No published posts captured yet. Publish from the composer and the studio will track them here.");
      return;
    }

    tbody.innerHTML = "";
    posts.forEach(post => {
      const rawText = post.content || "";
      const firstLine = rawText.split("\n")[0].trim();
      const hookText = firstLine.length > 55 ? firstLine.slice(0, 52) + "..." : (firstLine || "Untitled Post");

      const dateStr = post.published_at ? new Date(post.published_at).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "Recent";
      const impressions = (post.impressions || 0).toLocaleString();
      const estDwell = `~${Math.round(45 + Math.min(45, (post.impressions || 0) * 0.05))} sec`;

      const attr = post.attribution || { total_leads: 0, vip_leads: 0, avg_icp: 0.0 };
      const totalLeads = attr.total_leads || 0;
      const vipLeads = attr.vip_leads || 0;

      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td style="font-weight: 500; color: var(--text-primary); max-width: 260px;" title="${escapeHtml(rawText)}">
          ${escapeHtml(hookText)}
        </td>
        <td style="color: var(--text-secondary); font-size: 12.5px;">${dateStr}</td>
        <td style="font-family: var(--font-mono, monospace); font-weight: 600;">${impressions}</td>
        <td style="color: var(--text-secondary); font-size: 12.5px;">${estDwell}</td>
        <td><span class="stat-unknown" title="No audit has been run against this post's text">&ndash;</span></td>
        <td>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span class="icp-badge-pill ${vipLeads > 0 ? 'icp-badge-vip' : (totalLeads > 0 ? 'icp-badge-qual' : 'icp-badge-low')}" style="font-size: 11px;">
              ${totalLeads} Lead${totalLeads === 1 ? '' : 's'}${vipLeads > 0 ? ` (${vipLeads} VIP)` : ''}
            </span>
            <button class="btn btn-outline btn-xs btn-inspect-attribution" data-post-id="${post.id}" title="Inspect attributed leads and synthetic 1-to-1 DMs">
              Inspect
            </button>
          </div>
        </td>
      `;
      tbody.appendChild(tr);
    });

    // Wire inspect click handlers
    tbody.querySelectorAll(".btn-inspect-attribution").forEach(btn => {
      btn.addEventListener("click", () => {
        const pid = btn.getAttribute("data-post-id");
        if (pid) openPostAttributionModal(pid);
      });
    });

  } catch (e) {
    console.error("Failed to load analytics posts table:", e);
  }
}

async function openPostAttributionModal(postId) {
  const modal = document.getElementById("post-attribution-modal");
  if (!modal) return;

  modal.style.display = "flex";
  const hookEl = document.getElementById("post-attr-hook");
  const totalLeadsEl = document.getElementById("post-attr-total-leads");
  const vipLeadsEl = document.getElementById("post-attr-vip-leads");
  const avgIcpEl = document.getElementById("post-attr-avg-icp");
  const questionsEl = document.getElementById("post-attr-questions");
  const tbody = document.getElementById("post-attr-leads-tbody");

  if (hookEl) hookEl.innerText = `Loading attribution dossier for post ${postId}...`;
  if (tbody) tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted); padding: 24px;">Loading attributed leads...</td></tr>`;

  try {
    const res = await fetch(`${API_BASE}/v1/analytics/posts/${encodeURIComponent(postId)}/leads`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const summary = data.attribution_summary || {};
    const postMeta = data.post_meta;
    const leads = data.leads || [];

    if (hookEl) {
      if (postMeta && postMeta.content) {
        const firstLine = postMeta.content.split("\n")[0].trim();
        hookEl.innerText = `"${firstLine}"`;
      } else {
        hookEl.innerText = `Post ID: ${postId}`;
      }
    }

    if (totalLeadsEl) totalLeadsEl.innerText = summary.total_leads_generated || 0;
    if (vipLeadsEl) vipLeadsEl.innerText = summary.vip_leads_count || 0;
    if (avgIcpEl) avgIcpEl.innerText = (summary.avg_icp_score || 0).toFixed(1);
    if (questionsEl) questionsEl.innerText = summary.questions_count || 0;

    if (tbody) {
      if (!leads.length) {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted); padding: 24px;">No attributed leads recorded yet for this post. Engagements will be captured automatically via browser extension.</td></tr>`;
      } else {
        tbody.innerHTML = "";
        leads.forEach(lead => {
          const tier = lead.qualification_tier || "QUALIFIED";
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td>
              <div style="font-weight: 600; color: var(--text-primary);">${escapeHtml(lead.name || "Unknown Lead")}</div>
              <div style="font-size: 11.5px; color: var(--text-muted);">${escapeHtml(lead.headline || "")}</div>
              ${lead.latest_comment ? `<div style="font-size: 11.5px; color: var(--text-secondary); margin-top: 2px; font-style: italic;">"${escapeHtml(lead.latest_comment)}"</div>` : ''}
            </td>
            <td>
              <span class="icp-badge-pill icp-badge-${tier === 'VIP' ? 'vip' : (tier === 'QUALIFIED' ? 'qual' : 'low')}">
                ${lead.icp_score}
              </span>
            </td>
            <td>
              <span class="status-pill status-${(lead.lead_status || 'new').toLowerCase()}">${lead.lead_status || 'NEW'}</span>
            </td>
            <td>
              <button class="btn btn-subtle btn-xs btn-copy-post-lead-dm" data-dm="${encodeURIComponent(lead.suggested_dm || '')}">
                Copy DM
              </button>
            </td>
          `;
          tbody.appendChild(tr);
        });

        tbody.querySelectorAll(".btn-copy-post-lead-dm").forEach(btn => {
          btn.addEventListener("click", async () => {
            const rawDm = decodeURIComponent(btn.getAttribute("data-dm") || "");
            if (rawDm) {
              await navigator.clipboard.writeText(rawDm);
              showToast("Attributed 1-to-1 DM copied to clipboard!");
            }
          });
        });
      }
    }
  } catch (err) {
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--signal-red, #ef4444); padding: 24px;">Failed to load post attribution: ${err.message}</td></tr>`;
    }
  }
}

function initPostAttributionModal() {
  const modal = document.getElementById("post-attribution-modal");
  const closeBtn = document.getElementById("post-attribution-modal-close");
  const dismissBtn = document.getElementById("post-attribution-modal-dismiss");

  if (closeBtn && modal) {
    closeBtn.addEventListener("click", () => {
      modal.style.display = "none";
    });
  }
  if (dismissBtn && modal) {
    dismissBtn.addEventListener("click", () => {
      modal.style.display = "none";
    });
  }
  if (modal) {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.style.display = "none";
    });
  }
}

// -------------------------------------------------------------
// 13. AI COMMAND HUB (Bring-Your-Own-AI & Local Deterministic)
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
      runBtn.innerHTML = '<svg class="app-symbol app-spin"><use href="#sym-refresh"></use></svg> Executing...';
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
function showToast(msg, type) {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const t = document.createElement("div");
  // Callers have always passed a severity as the second argument. It used to
  // be dropped on the floor, so every failure looked exactly like a success.
  const variant = ["error", "success", "warning", "info"].includes(type) ? ` toast-${type}` : "";
  t.className = `toast${variant}`;
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
    summary: "Reverse-engineered hook blueprints, topic taxonomies, instant search, and the Agno Framework autonomous inbound roadmap."
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
    category: "Bring-Your-Own-AI",
    icon: "sparkles",
    file: "06_AI_COMMAND.md",
    summary: "Bring-Your-Own-AI multi-model gateway (OpenAI, Gemini, Claude, Ollama, Groq) + local deterministic engine, CLI configuration, prompt presets, and direct Studio transfer."
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
    if (module.id === "studio-editor") { jumpTab = "tab-studio"; jumpLabel = "Open Studio Editor"; }
    else if (module.id === "schedule-queue") { jumpTab = "tab-queue"; jumpLabel = "Open Schedule & Queue"; }
    else if (module.id === "inbound-crm") { jumpTab = "tab-crm"; jumpLabel = "Open Inbound CRM"; }
    else if (module.id === "viral-swipe-file") { jumpTab = "tab-inspirations"; jumpLabel = "Open Swipe File"; }
    else if (module.id === "analytics") { jumpTab = "tab-analytics"; jumpLabel = "Open Analytics"; }
    else if (module.id === "ai-command") { jumpTab = "tab-ai-command"; jumpLabel = "Open AI Command"; }

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

// -------------------------------------------------------------
// 14. PERSONAL SETTINGS & CREATOR ONBOARDING CONTROLLER
// -------------------------------------------------------------
function initSettingsPanel() {
  // 1. Corner Position Buttons
  const cornerBtns = document.querySelectorAll(".corner-btn");
  const posInput = document.getElementById("setting-watermark-position");
  cornerBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      cornerBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const pos = btn.getAttribute("data-pos");
      if (posInput) posInput.value = pos;
      updateWatermarkLivePreview();
    });
  });

  // 2. Style Preset Chips
  const styleChips = document.querySelectorAll(".watermark-chip");
  const styleInput = document.getElementById("setting-watermark-style");
  styleChips.forEach(chip => {
    chip.addEventListener("click", () => {
      styleChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      const sty = chip.getAttribute("data-style");
      if (styleInput) styleInput.value = sty;
      updateWatermarkLivePreview();
    });
  });

  // 3. Watermark Text Input live sync
  const watermarkTextInput = document.getElementById("setting-watermark-text");
  if (watermarkTextInput) {
    watermarkTextInput.addEventListener("input", () => {
      updateWatermarkLivePreview();
    });
  }

  // 4. Save All Settings button
  const saveBtn = document.getElementById("btn-save-creator-settings");
  if (saveBtn) {
    saveBtn.addEventListener("click", saveCreatorProfile);
  }

  // 5. Password toggle reveals
  const btnToggleLiAt = document.getElementById("btn-toggle-li-at");
  const inputLiAt = document.getElementById("setting-li-at");
  if (btnToggleLiAt && inputLiAt) {
    btnToggleLiAt.addEventListener("click", () => {
      inputLiAt.type = inputLiAt.type === "password" ? "text" : "password";
    });
  }

  const btnToggleJsession = document.getElementById("btn-toggle-jsessionid");
  const inputJsession = document.getElementById("setting-jsessionid");
  if (btnToggleJsession && inputJsession) {
    btnToggleJsession.addEventListener("click", () => {
      inputJsession.type = inputJsession.type === "password" ? "text" : "password";
    });
  }

  // 6. Save & Sync LinkedIn Tokens
  const btnSyncTokens = document.getElementById("btn-sync-linkedin-tokens");
  if (btnSyncTokens) {
    btnSyncTokens.addEventListener("click", async () => {
      const liAtVal = inputLiAt ? inputLiAt.value.trim() : "";
      const jsessionVal = inputJsession ? inputJsession.value.trim() : "";
      if (!liAtVal || !jsessionVal) {
        showToast("Please enter both li_at and JSESSIONID tokens.");
        return;
      }
      btnSyncTokens.disabled = true;
      btnSyncTokens.innerHTML = '<svg class="app-symbol app-symbol-xs"><use href="#sym-act-spark"></use></svg> Saving...';
      try {
        const res = await fetch(`${API_BASE}/auth/cookies`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ li_at: liAtVal, JSESSIONID: jsessionVal })
        });
        if (res.ok) {
          // Saving a token is local. It used to also trigger an authenticated
          // request to LinkedIn, and the word "synced" described that request.
          // Nothing is fetched now, so nothing is claimed.
          showToast("LinkedIn session tokens saved to your local studio.");
          checkLinkedInSessionStatus();
        } else {
          showToast("Could not save tokens to the studio backend.", "error");
        }
      } catch (err) {
        showToast("Sync error: " + err.message);
      } finally {
        btnSyncTokens.disabled = false;
        btnSyncTokens.innerHTML = '<svg class="app-symbol app-symbol-xs"><use href="#sym-act-save"></use></svg> Save Tokens';
      }
    });
  }

  // 7. Verify Connection Button
  const btnVerifySession = document.getElementById("btn-verify-linkedin-session");
  if (btnVerifySession) {
    btnVerifySession.addEventListener("click", async () => {
      btnVerifySession.disabled = true;
      btnVerifySession.innerHTML = '<svg class="app-symbol app-symbol-xs"><use href="#sym-act-spark"></use></svg> Verifying...';
      await checkLinkedInSessionStatus();
      btnVerifySession.disabled = false;
      btnVerifySession.innerHTML = '<svg class="app-symbol app-symbol-xs"><use href="#sym-act-lock"></use></svg> Verify Connection';
    });
  }
}

function updateWatermarkLivePreview() {
  const badge = document.getElementById("watermark-badge-element");
  const textElem = document.getElementById("watermark-badge-text");
  const watermarkTextInput = document.getElementById("setting-watermark-text");
  const posInput = document.getElementById("setting-watermark-position");
  const styleInput = document.getElementById("setting-watermark-style");

  const brandText = (watermarkTextInput && watermarkTextInput.value.trim()) || "@dharmik136";
  const pos = (posInput && posInput.value) || "bottom_right";
  const style = (styleInput && styleInput.value) || "glass_pill";

  if (textElem) {
    textElem.innerText = brandText;
  }

  // Sync to topbar and modal handle indicators
  const topbarHandle = document.getElementById("topbar-settings-handle");
  if (topbarHandle) topbarHandle.innerText = brandText;

  const modalHandle = document.getElementById("modal-brand-handle-text");
  if (modalHandle) modalHandle.innerText = brandText;

  const modalCustomInput = document.getElementById("img-personal-watermark-text");
  if (modalCustomInput && (!modalCustomInput.value || modalCustomInput.value === "@dharmik136")) {
    modalCustomInput.value = brandText;
  }

  if (badge) {
    badge.className = "watermark-live-badge";
    badge.classList.add(`pos-${pos.replace(/_/g, "-")}`);
    badge.classList.add(`style-${style.replace(/_/g, "-")}`);
  }
}

async function loadCreatorProfile() {
  try {
    const res = await fetch(`${API_BASE}/settings/profile`);
    if (!res.ok) return;
    const data = await res.json();
    if (data.status === "success" && data.profile) {
      cachedCreatorProfile = data.profile;
      const p = data.profile;

      // Populate Profile Inputs
      if (document.getElementById("setting-creator-name")) document.getElementById("setting-creator-name").value = p.name || "";
      if (document.getElementById("setting-creator-headline")) document.getElementById("setting-creator-headline").value = p.headline || "";
      if (document.getElementById("setting-creator-company")) document.getElementById("setting-creator-company").value = p.company || "";
      if (document.getElementById("setting-watermark-text")) document.getElementById("setting-watermark-text").value = p.brand_watermark_text || "@dharmik136";
      
      const watermarkEnabledToggle = document.getElementById("setting-watermark-enabled");
      if (watermarkEnabledToggle) watermarkEnabledToggle.checked = p.brand_watermark_enabled !== false;

      const eliminatePwToggle = document.getElementById("setting-eliminate-provider-watermark");
      if (eliminatePwToggle) eliminatePwToggle.checked = p.eliminate_provider_watermark_default !== false;

      // Sync Modal switches with saved profile defaults
      const modalPwToggle = document.getElementById("img-eliminate-watermark");
      if (modalPwToggle) modalPwToggle.checked = p.eliminate_provider_watermark_default !== false;

      const modalPersonalToggle = document.getElementById("img-apply-personal-watermark");
      if (modalPersonalToggle) {
        modalPersonalToggle.checked = p.brand_watermark_enabled || false;
        const modalPersonalOpts = document.getElementById("modal-personal-watermark-options");
        if (modalPersonalOpts) modalPersonalOpts.style.display = modalPersonalToggle.checked ? "block" : "none";
      }

      // Position
      const pos = p.brand_watermark_position || "bottom_right";
      const posInput = document.getElementById("setting-watermark-position");
      if (posInput) posInput.value = pos;
      document.querySelectorAll(".corner-btn").forEach(btn => {
        btn.classList.toggle("active", btn.getAttribute("data-pos") === pos);
      });
      const modalPosSelect = document.getElementById("img-personal-watermark-position");
      if (modalPosSelect) modalPosSelect.value = pos;

      // Style
      const sty = p.brand_watermark_style || "glass_pill";
      const styleInput = document.getElementById("setting-watermark-style");
      if (styleInput) styleInput.value = sty;
      document.querySelectorAll(".watermark-chip").forEach(chip => {
        chip.classList.toggle("active", chip.getAttribute("data-style") === sty);
      });
      const modalStyleSelect = document.getElementById("img-personal-watermark-style");
      if (modalStyleSelect) modalStyleSelect.value = sty;

      updateWatermarkLivePreview();
      updateLinkedInStatusBadge(data.linkedin_connected, data.session_status);
    }
  } catch (err) {
    console.warn("Failed loading creator profile from backend:", err);
  }
}

async function saveCreatorProfile() {
  const saveBtn = document.getElementById("btn-save-creator-settings");
  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<svg class="app-symbol app-spin"><use href="#sym-refresh"></use></svg> Saving...';
  }

  const payload = {
    name: (document.getElementById("setting-creator-name") && document.getElementById("setting-creator-name").value.trim()) || "Dharmik Shingala",
    headline: (document.getElementById("setting-creator-headline") && document.getElementById("setting-creator-headline").value.trim()) || "AI Systems Engineer",
    company: (document.getElementById("setting-creator-company") && document.getElementById("setting-creator-company").value.trim()) || "Enterprise Labs",
    brand_watermark_text: (document.getElementById("setting-watermark-text") && document.getElementById("setting-watermark-text").value.trim()) || "@dharmik136",
    brand_watermark_position: (document.getElementById("setting-watermark-position") && document.getElementById("setting-watermark-position").value) || "bottom_right",
    brand_watermark_style: (document.getElementById("setting-watermark-style") && document.getElementById("setting-watermark-style").value) || "glass_pill",
    brand_watermark_enabled: document.getElementById("setting-watermark-enabled") ? document.getElementById("setting-watermark-enabled").checked : true,
    eliminate_provider_watermark_default: document.getElementById("setting-eliminate-provider-watermark") ? document.getElementById("setting-eliminate-provider-watermark").checked : true,
    default_aspect_ratio: studioAspectRatio || "1:1",
    default_visual_style: studioVisualStyle || "photorealistic"
  };

  try {
    const res = await fetch(`${API_BASE}/settings/profile`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      showToast("Creator profile and watermark settings saved!");
      updateWatermarkLivePreview();
    } else {
      showToast("Failed to save settings.");
    }
  } catch (err) {
    showToast("Save error: " + err.message);
  } finally {
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.innerHTML = '<svg class="app-symbol"><use href="#sym-act-save"></use></svg> Save All Settings';
    }
  }
}

async function checkLinkedInSessionStatus() {
  try {
    const res = await fetch(`${API_BASE}/auth/status`);
    if (!res.ok) return;
    const data = await res.json();
    updateLinkedInStatusBadge(data.is_connected, data.status);
    if (data.is_connected) {
      showToast("LinkedIn session authenticated and verified!");
    } else {
      showToast("LinkedIn session not connected. Enter your tokens above.");
    }
  } catch (err) {
    console.warn("LinkedIn status check failed:", err);
  }
}

function updateLinkedInStatusBadge(isConnected, statusText) {
  const pill = document.getElementById("settings-linkedin-status-pill");
  const label = document.getElementById("settings-linkedin-status-text");
  if (!pill || !label) return;

  if (isConnected || statusText === "connected" || statusText === "ready") {
    pill.className = "status-indicator-pill connected";
    label.innerText = "Connected & Verified";
  } else {
    pill.className = "status-indicator-pill";
    label.innerText = "Disconnected";
  }
}

// -------------------------------------------------------------
// 14. REAL-TIME EVENT STREAM & SSE INBOX CONTROLLER
// -------------------------------------------------------------
let sseSource = null;

function initEventStream() {
  if (!window.EventSource) {
    console.warn("EventSource not supported in this browser.");
    return;
  }

  try {
    sseSource = new EventSource("/api/v1/stream/events");

    sseSource.onopen = () => {
      console.log("[SSE] Connected to Studio Real-Time Event Bus.");
      updateLiveStreamBadge(true);
    };

    sseSource.onerror = (err) => {
      console.warn("[SSE] Connection interrupted. Auto-reconnecting...", err);
      updateLiveStreamBadge(false);
    };

    // Handle draft_ingested event in < 5ms
    sseSource.addEventListener("draft_ingested", (e) => {
      try {
        const payload = JSON.parse(e.data);
        console.log("[SSE] draft_ingested event received:", payload);
        handleIncomingDraft(payload);
      } catch (err) {
        console.error("[SSE] Failed parsing draft_ingested payload:", err);
      }
    });

    // Handle crm / lead events
    sseSource.addEventListener("lead_ingested", (e) => {
      try {
        const payload = JSON.parse(e.data);
        console.log("[SSE] lead_ingested event:", payload);
        if (typeof loadLeads === "function") {
          loadLeads();
        }
      } catch (err) {}
    });

    // Handle post published events
    sseSource.addEventListener("post_published", (e) => {
      try {
        const payload = JSON.parse(e.data);
        showToast(`Post published on schedule: ${payload.post_id || ""}`);
        if (typeof loadQueue === "function") {
          loadQueue();
        }
      } catch (err) {}
    });

    // Handle schedule recovery events
    sseSource.addEventListener("schedule_recovery", (e) => {
      try {
        const payload = JSON.parse(e.data);
        if (payload.type === "grace_dispatched") {
          showToast(`Grace Recovery: Post published within morning grace window.`);
        } else if (payload.type === "rolled_forward") {
          showToast(`Cadence Protection: Post rolled forward to ${payload.slot_label || "next slot"}.`);
        } else {
          showToast(`Queue Recovery: ${payload.message || "Schedule updated"}`);
        }
        if (typeof loadQueue === "function") {
          loadQueue();
        }
      } catch (err) {}
    });
  } catch (err) {
    console.error("[SSE] Failed initializing EventSource:", err);
  }
}

function updateLiveStreamBadge(isConnected) {
  const badge = document.getElementById("stream-beacon-badge");
  if (badge) {
    badge.className = isConnected ? "stream-beacon active" : "stream-beacon disconnected";
    badge.title = isConnected ? "Live Ingress Stream Active (<5ms latency)" : "Stream Disconnected (Reconnecting)";
  }
}

function handleIncomingDraft(draft) {
  // 1. Show high-visibility animated mobile thought tray toast with action in < 5ms
  const container = document.getElementById("toast-container");
  if (container) {
    const t = document.createElement("div");
    t.className = "toast toast-draft-ingested animated-pulse";
    const archetypeTag = draft.archetype || "Draft";
    const safeBadge = draft.is_pre_fold_safe
      ? '<span class="safe-fold-badge">Fold Safe</span>'
      : '<span class="warn-fold-badge">Past Fold</span>';

    t.innerHTML = `
      <div class="toast-draft-header">
        <span class="toast-badge-archetype">${escapeHtml(archetypeTag)}</span>
        ${safeBadge}
        <span class="toast-time">Just Now</span>
      </div>
      <div class="toast-draft-title">${escapeHtml(draft.title || "New Mobile Ingress")}</div>
      <div class="toast-draft-preview">${escapeHtml((draft.raw_content || "").substring(0, 85))}...</div>
      <div class="toast-draft-actions">
        <button class="toast-btn-load" id="btn-load-draft-${draft.draft_id}">Load into Composer</button>
      </div>
    `;
    container.prepend(t);

    const loadBtn = t.querySelector(`#btn-load-draft-${draft.draft_id}`);
    if (loadBtn) {
      loadBtn.addEventListener("click", () => {
        const editor = document.getElementById("post-editor-input");
        if (editor) {
          editor.value = draft.raw_content;
          editor.dispatchEvent(new Event("input"));
          switchTab("tab-studio");
          showToast(`Loaded "${draft.title}" into Composer!`, "success");
        }
        t.remove();
      });
    }

    // Auto-remove after 8 seconds
    setTimeout(() => {
      if (t.parentNode) {
        t.classList.add("fade-out");
        setTimeout(() => t.remove(), 400);
      }
    }, 8000);
  }

  // 2. Refresh queue / posts if currently open
  if (typeof loadQueue === "function") {
    loadQueue();
  }

  // 3. Dispatch a custom window event for any interested widgets
  window.dispatchEvent(new CustomEvent("studio:draft_ingested", { detail: draft }));
}

// -------------------------------------------------------------
// SECTION 16: FLOATING FLOW & GOVERNANCE ASSISTANT (Z-TAB / FAB)
// -------------------------------------------------------------
let gstackAuditDebounce = null;
let currentEnvMode = "real";

function initFloatingFlowWidget() {
  const triggerBtn = document.getElementById("btn-flow-trigger");
  const drawerPanel = document.getElementById("flow-drawer-panel");
  const closeBtn = document.getElementById("btn-close-flow-drawer");

  if (!triggerBtn || !drawerPanel) return;

  // 1. Toggle Drawer on Z-Tab Click
  triggerBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    const isVisible = drawerPanel.style.display === "flex";
    if (isVisible) {
      drawerPanel.style.display = "none";
    } else {
      drawerPanel.style.display = "flex";
      runLiveGStackAudit();
    }
  });

  if (closeBtn) {
    closeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      drawerPanel.style.display = "none";
    });
  }

  // Close when clicking outside
  document.addEventListener("click", (e) => {
    if (drawerPanel.style.display === "flex" && !drawerPanel.contains(e.target) && !triggerBtn.contains(e.target)) {
      drawerPanel.style.display = "none";
    }
  });

  // 2. Wire Guided Studio Flow Buttons
  const flowButtons = drawerPanel.querySelectorAll(".flow-step-btn");
  flowButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const flow = btn.getAttribute("data-flow");
      handleFlowNavigation(flow);
    });
  });

  // 3. Environment Mode Toggle
  const envRealBtn = document.getElementById("env-btn-real");
  const envTestBtn = document.getElementById("env-btn-test");
  const envTag = document.getElementById("hud-env-tag");

  if (envRealBtn && envTestBtn) {
    envRealBtn.addEventListener("click", () => {
      envRealBtn.classList.add("active");
      envTestBtn.classList.remove("active");
      currentEnvMode = "real";
      if (envTag) {
        envTag.innerText = "Production";
        envTag.style.background = "rgba(16, 185, 129, 0.15)";
        envTag.style.color = "#10B981";
      }
      showToast("Switched to Real Production Data Mode", "info");
      syncInspirationMode("real");
    });

    envTestBtn.addEventListener("click", () => {
      envTestBtn.classList.add("active");
      envRealBtn.classList.remove("active");
      currentEnvMode = "test";
      if (envTag) {
        envTag.innerText = "Sandbox Test";
        envTag.style.background = "rgba(245, 158, 11, 0.15)";
        envTag.style.color = "#F59E0B";
      }
      showToast("Switched to Test / Sandbox Mode", "info");
      syncInspirationMode("test");
    });
  }

  // 4. Hook Screen Concept & Bug Identifier Actions
  const inspectBtn = document.getElementById("btn-inspect-screen");
  const viewSheetBtn = document.getElementById("btn-view-internal-sheet");
  if (inspectBtn) {
    inspectBtn.addEventListener("click", () => {
      drawerPanel.style.display = "none";
      startScreenInspection();
    });
  }
  if (viewSheetBtn) {
    viewSheetBtn.addEventListener("click", () => {
      drawerPanel.style.display = "none";
      openInternalSheetModal();
    });
  }
  refreshSheetBadgeCount();

  // 5. Hook real-time audit onto editor input
  const postContent = document.getElementById("post-editor-input") || document.getElementById("post-content");
  if (postContent) {
    postContent.addEventListener("input", () => {
      clearTimeout(gstackAuditDebounce);
      gstackAuditDebounce = setTimeout(() => {
        runLiveGStackAudit();
      }, 300);
    });
  }

  // Run initial audit after interface stabilizes
  setTimeout(runLiveGStackAudit, 800);
}

function syncInspirationMode(mode) {
  // Record the mode and move the pills with it. Setting only the argument
  // meant the next search or topic click reverted to the previous mode.
  currentInspMode = mode;
  document.querySelectorAll("#insp-mode-toggle .mode-pill").forEach(p => {
    p.classList.toggle("active", p.getAttribute("data-mode") === mode);
  });
  loadInspirations(currentInspQuery, currentInspTopic, mode);
}

function handleFlowNavigation(flow) {
  const drawerPanel = document.getElementById("flow-drawer-panel");
  switch (flow) {
    case "composer":
      switchTab("tab-studio");
      const editor = document.getElementById("post-editor-input") || document.getElementById("post-content");
      if (editor) editor.focus();
      break;
    case "queue":
      switchTab("tab-queue");
      break;
    case "crm":
      switchTab("tab-crm");
      break;
    case "swipe":
      switchTab("tab-inspirations");
      break;
    case "analytics":
      switchTab("tab-analytics");
      break;
    case "docs":
      switchTab("tab-docs");
      break;
  }
  if (drawerPanel) drawerPanel.style.display = "none";
}

async function runLiveGStackAudit() {
  const postContentEl = document.getElementById("post-editor-input") || document.getElementById("post-content");
  const postTitleEl = document.getElementById("post-title-input") || document.getElementById("draft-title");
  const content = postContentEl ? postContentEl.value : "";
  const title = postTitleEl ? postTitleEl.value : "";

  // If editor is empty, display clean 100% baseline state
  if (!content.trim()) {
    updateHUDGateUI({
      passed: true,
      score: 100,
      gates: {
        gate_1_ceo: { passed: true },
        gate_2_eng_manager: { passed: true },
        gate_3_designer: { passed: true },
        gate_4_qa_lead: { passed: true },
        gate_5_cso: { passed: true },
        gate_6_release_manager: { passed: true }
      },
      violations: []
    });
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/v1/gstack/audit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, title })
    });
    if (!res.ok) return;
    const data = await res.json();
    if (data.status === "success" && data.audit) {
      updateHUDGateUI(data.audit);
    }
  } catch (err) {
    // Local-first non-blocking fallback
  }
}

function updateHUDGateUI(audit) {
  const scorePill = document.getElementById("hud-audit-score");
  const healthRing = document.getElementById("flow-health-ring");
  const violationsBox = document.getElementById("hud-violations-box");

  const score = Number.isFinite(audit.score) ? audit.score : 100;

  if (scorePill) {
    scorePill.innerText = `${score}% ${audit.passed ? "PASS" : "ATTN"}`;
    scorePill.className = `audit-score-pill ${audit.passed ? "score-pass" : (score >= 70 ? "score-warn" : "score-fail")}`;
  }

  if (healthRing) {
    healthRing.className = `trigger-health-ring ${audit.passed ? "" : (score >= 70 ? "warn" : "fail")}`;
    healthRing.setAttribute("title", `Audit Health: ${score}%`);
  }

  const gates = audit.gates || {};
  const gateMap = {
    "hud-gate-ceo": gates.gate_1_ceo,
    "hud-gate-eng": gates.gate_2_eng_manager,
    "hud-gate-designer": gates.gate_3_designer,
    "hud-gate-qa": gates.gate_4_qa_lead,
    "hud-gate-cso": gates.gate_5_cso,
    "hud-gate-release": gates.gate_6_release_manager
  };

  for (const [id, gate] of Object.entries(gateMap)) {
    const el = document.getElementById(id);
    if (el) {
      const isPassed = !gate || gate.passed !== false;
      el.className = `hud-gate-item ${isPassed ? "gate-pass" : "gate-fail"}`;
      const icon = el.querySelector(".gate-icon");
      if (icon) icon.innerHTML = isPassed ? "&#10003;" : "&#10007;";
    }
  }

  if (violationsBox) {
    if (audit.violations && audit.violations.length > 0) {
      violationsBox.style.display = "block";
      violationsBox.innerHTML = `<strong>Attention Required:</strong><br>${audit.violations.map(v => `• ${escapeHtml(v)}`).join("<br>")}`;
    } else {
      violationsBox.style.display = "none";
      violationsBox.innerHTML = "";
    }
  }
}

/* =========================================================================
   SECTION 17: SCREEN CONCEPT & ELEMENT IDENTIFIER ENGINE
   ========================================================================= */
let isInspectingScreen = false;
let hoveredElement = null;
let selectedElementData = null;
let currentSheetFilter = "all";
let sheetIssuesCache = [];

function startScreenInspection() {
  const overlay = document.getElementById("screen-picker-overlay");
  const exitBtn = document.getElementById("btn-exit-picker");
  if (!overlay) return;

  isInspectingScreen = true;
  overlay.style.display = "block";
  document.body.style.cursor = "crosshair";

  document.addEventListener("mousemove", handlePickerMouseMove, true);
  document.addEventListener("click", handlePickerClick, true);
  document.addEventListener("keydown", handlePickerKeyDown, true);

  if (exitBtn) {
    exitBtn.onclick = (e) => {
      e.stopPropagation();
      stopScreenInspection();
    };
  }

  showToast("Screen inspection active. Hover and click any element to identify.", "info");
}

function stopScreenInspection() {
  isInspectingScreen = false;
  const overlay = document.getElementById("screen-picker-overlay");
  const pickerBox = document.getElementById("screen-picker-box");

  if (overlay) overlay.style.display = "none";
  if (pickerBox) pickerBox.style.display = "none";
  document.body.style.cursor = "default";

  document.removeEventListener("mousemove", handlePickerMouseMove, true);
  document.removeEventListener("click", handlePickerClick, true);
  document.removeEventListener("keydown", handlePickerKeyDown, true);
  hoveredElement = null;
}

function handlePickerKeyDown(e) {
  if (e.key === "Escape") {
    stopScreenInspection();
    showToast("Screen inspection cancelled.", "info");
  }
}

function computeElementSelector(el) {
  if (!el || el === document.body) return "body";
  if (el.id) return `#${el.id}`;

  let path = [];
  let current = el;
  while (current && current !== document.body && current !== document.documentElement && path.length < 3) {
    let selector = current.tagName.toLowerCase();
    if (current.id) {
      selector += `#${current.id}`;
      path.unshift(selector);
      break;
    } else if (current.classList && current.classList.length > 0) {
      const meaningfulClasses = Array.from(current.classList).filter(
        c => !["active", "hover", "focus", "selected", "gate-pass", "gate-fail"].includes(c)
      );
      if (meaningfulClasses.length > 0) {
        selector += `.${meaningfulClasses[0]}`;
      }
    }
    path.unshift(selector);
    current = current.parentElement;
  }
  return path.join(" > ");
}

function getActiveTabName() {
  const activeNav = document.querySelector(".nav-item.active") || document.querySelector(".nav-tab.active");
  if (activeNav) {
    return activeNav.innerText.trim().replace(/[\r\n\t]+/g, " ");
  }
  const activePane = document.querySelector(".tab-pane.active");
  if (activePane) {
    return activePane.id ? activePane.id.replace("tab-", "") : "composer";
  }
  return "composer";
}

function handlePickerMouseMove(e) {
  if (!isInspectingScreen) return;

  // Find element under cursor, ignoring the overlay itself and assistant widgets
  const elements = document.elementsFromPoint(e.clientX, e.clientY);
  const target = elements.find(el => {
    return !el.closest("#screen-picker-overlay") &&
           !el.closest("#floating-flow-widget") &&
           !el.closest(".modal-backdrop") &&
           !el.closest("#toast-container");
  });

  if (!target) return;
  hoveredElement = target;

  const pickerBox = document.getElementById("screen-picker-box");
  const pickerBadge = document.getElementById("screen-picker-badge");
  if (!pickerBox || !pickerBadge) return;

  const rect = target.getBoundingClientRect();
  pickerBox.style.display = "block";
  pickerBox.style.top = `${rect.top}px`;
  pickerBox.style.left = `${rect.left}px`;
  pickerBox.style.width = `${rect.width}px`;
  pickerBox.style.height = `${rect.height}px`;

  const selector = computeElementSelector(target);
  pickerBadge.innerText = `<${target.tagName.toLowerCase()}> ${selector}`;
}

function handlePickerClick(e) {
  if (!isInspectingScreen) return;

  e.preventDefault();
  e.stopPropagation();
  e.stopImmediatePropagation();

  const elements = document.elementsFromPoint(e.clientX, e.clientY);
  const target = elements.find(el => {
    return !el.closest("#screen-picker-overlay") &&
           !el.closest("#floating-flow-widget") &&
           !el.closest(".modal-backdrop") &&
           !el.closest("#toast-container");
  });

  stopScreenInspection();

  if (target) {
    openConceptAnnotationModal(target);
  }
}

function openConceptAnnotationModal(target) {
  const backdrop = document.getElementById("concept-modal-backdrop");
  if (!backdrop) return;

  const rect = target.getBoundingClientRect();
  const selector = computeElementSelector(target);
  const tabName = getActiveTabName();
  const rawSnippet = (target.innerText || target.value || target.getAttribute("placeholder") || "").trim();
  const snippet = rawSnippet ? (rawSnippet.length > 100 ? rawSnippet.slice(0, 97) + "..." : rawSnippet) : "(No visible text)";

  selectedElementData = {
    tag: target.tagName,
    id: target.id || null,
    classes: target.className || null,
    selector: selector,
    snippet: snippet,
    tabName: tabName,
    boundingBox: {
      top: Math.round(rect.top),
      left: Math.round(rect.left),
      width: Math.round(rect.width),
      height: Math.round(rect.height)
    },
    viewport: `${window.innerWidth}x${window.innerHeight}`
  };

  // Populate UI
  const tagEl = document.getElementById("annot-target-tag");
  const tabEl = document.getElementById("annot-target-tab");
  const selectorEl = document.getElementById("annot-target-selector");
  const snippetEl = document.getElementById("annot-target-snippet");

  if (tagEl) tagEl.innerText = target.tagName;
  if (tabEl) tabEl.innerText = tabName;
  if (selectorEl) selectorEl.innerText = selector;
  if (snippetEl) snippetEl.innerText = `"${snippet}"`;

  // Reset form
  const form = document.getElementById("concept-annotation-form");
  if (form) form.reset();

  // Auto-fill sensible default title
  const titleInput = document.getElementById("annot-title");
  if (titleInput) {
    titleInput.value = `Issue on ${target.tagName.toLowerCase()} (${selector})`;
  }

  backdrop.style.display = "flex";

  // Focus description
  setTimeout(() => {
    const descInput = document.getElementById("annot-desc");
    if (descInput) descInput.focus();
  }, 100);
}

function closeConceptAnnotationModal() {
  const backdrop = document.getElementById("concept-modal-backdrop");
  if (backdrop) backdrop.style.display = "none";
  selectedElementData = null;
}

function initConceptAnnotationEvents() {
  const form = document.getElementById("concept-annotation-form");
  const closeBtn = document.getElementById("btn-close-concept-modal");
  const cancelBtn = document.getElementById("btn-cancel-concept");
  const backdrop = document.getElementById("concept-modal-backdrop");

  if (closeBtn) closeBtn.addEventListener("click", closeConceptAnnotationModal);
  if (cancelBtn) cancelBtn.addEventListener("click", closeConceptAnnotationModal);

  if (backdrop) {
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) closeConceptAnnotationModal();
    });
  }

  // Category change auto-suggests role
  const catSelect = document.getElementById("annot-category");
  const roleSelect = document.getElementById("annot-role");
  if (catSelect && roleSelect) {
    catSelect.addEventListener("change", () => {
      const cat = catSelect.value;
      if (cat === "ux_glitch") roleSelect.value = "DESIGNER";
      else if (cat === "copy_slop") roleSelect.value = "CEO";
      else if (cat === "data_mismatch" || cat === "bug") roleSelect.value = "ENGINEERING_MANAGER";
      else if (cat === "concept" || cat === "feature_request") roleSelect.value = "ENGINEERING_MANAGER";
    });
  }

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!selectedElementData) {
        showToast("No element target selected.", "error");
        return;
      }

      const title = document.getElementById("annot-title").value.trim();
      const desc = document.getElementById("annot-desc").value.trim();
      const category = document.getElementById("annot-category").value;
      const severity = document.getElementById("annot-severity").value;
      const role = document.getElementById("annot-role").value;
      const promoteBacklog = document.getElementById("annot-promote-backlog").checked;
      const submitBtn = document.getElementById("btn-submit-concept");

      if (!title || !desc) {
        showToast("Please enter a title and description.", "error");
        return;
      }

      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerText = "Submitting...";
      }

      try {
        const payload = {
          target_selector: selectedElementData.selector,
          title: title,
          description: desc,
          category: category,
          severity: severity,
          suggested_role: role,
          element_tag: selectedElementData.tag,
          element_id: selectedElementData.id,
          element_classes: selectedElementData.classes,
          element_text_snippet: selectedElementData.snippet,
          tab_name: selectedElementData.tabName,
          page_route: window.location.pathname || "/",
          bounding_box: selectedElementData.boundingBox,
          viewport_resolution: selectedElementData.viewport,
          promote_to_backlog: promoteBacklog
        };

        const res = await fetch(`${API_BASE}/v1/internal-sheet/issues`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });

        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || "Submission failed");
        }

        const data = await res.json();
        showToast("Logged to Internal Sheet successfully!", "success");
        if (promoteBacklog && data.issue && data.issue.gstack_task_id) {
          showToast(`Promoted to G-Stack Backlog (Task #${data.issue.gstack_task_id})`, "info");
        }

        closeConceptAnnotationModal();
        refreshSheetBadgeCount();
      } catch (err) {
        showToast(`Failed to log issue: ${err.message}`, "error");
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerText = "Submit to Internal Sheet";
        }
      }
    });
  }
}

/* =========================================================================
   SECTION 18: INTERNAL SPREADSHEET VIEWER CONTROLLER
   ========================================================================= */
function initInternalSheetModalEvents() {
  const sheetBackdrop = document.getElementById("sheet-modal-backdrop");
  const closeBtn = document.getElementById("btn-close-sheet-modal");
  const exportBtn = document.getElementById("btn-export-sheet-csv");
  const searchInput = document.getElementById("sheet-search-input");
  const filterPills = document.querySelectorAll("#sheet-filter-pills .sheet-filter-pill");

  if (closeBtn) closeBtn.addEventListener("click", closeInternalSheetModal);
  if (sheetBackdrop) {
    sheetBackdrop.addEventListener("click", (e) => {
      if (e.target === sheetBackdrop) closeInternalSheetModal();
    });
  }

  if (exportBtn) {
    exportBtn.addEventListener("click", () => {
      window.location.href = `${API_BASE}/v1/internal-sheet/export.csv`;
      showToast("Downloading internal sheet CSV...", "info");
    });
  }

  if (searchInput) {
    searchInput.addEventListener("input", () => {
      renderInternalSheetTable();
    });
  }

  filterPills.forEach(pill => {
    pill.addEventListener("click", () => {
      filterPills.forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      currentSheetFilter = pill.getAttribute("data-filter");
      renderInternalSheetTable();
    });
  });
}

function openInternalSheetModal() {
  const backdrop = document.getElementById("sheet-modal-backdrop");
  if (!backdrop) return;
  backdrop.style.display = "flex";
  loadInternalSheetData();
}

function closeInternalSheetModal() {
  const backdrop = document.getElementById("sheet-modal-backdrop");
  if (backdrop) backdrop.style.display = "none";
}

async function loadInternalSheetData() {
  try {
    const res = await fetch(`${API_BASE}/v1/internal-sheet/issues`);
    if (!res.ok) return;
    const data = await res.json();
    sheetIssuesCache = data.issues || [];

    // Update counts
    const summary = data.summary || {};
    const countAll = document.getElementById("sheet-count-all");
    const countOpen = document.getElementById("sheet-count-open");
    const countResolved = document.getElementById("sheet-count-resolved");
    const countCritical = document.getElementById("sheet-count-critical");

    if (countAll) countAll.innerText = summary.total || 0;
    if (countOpen) countOpen.innerText = summary.open || 0;
    if (countResolved) countResolved.innerText = summary.resolved || 0;
    if (countCritical) countCritical.innerText = summary.critical || 0;

    const openBadge = document.getElementById("sheet-open-badge");
    if (openBadge) {
      openBadge.innerText = `${summary.open || 0} Open`;
    }

    renderInternalSheetTable();
  } catch (err) {
    console.error("Failed to load internal sheet issues:", err);
  }
}

async function refreshSheetBadgeCount() {
  try {
    const res = await fetch(`${API_BASE}/v1/internal-sheet/issues?limit=1`);
    if (!res.ok) return;
    const data = await res.json();
    const summary = data.summary || {};
    const openBadge = document.getElementById("sheet-open-badge");
    if (openBadge) {
      openBadge.innerText = `${summary.open || 0} Open`;
    }
  } catch (err) {
    // Non-blocking
  }
}

function renderInternalSheetTable() {
  const tbody = document.getElementById("internal-spreadsheet-tbody");
  const emptyState = document.getElementById("sheet-empty-state");
  const searchInput = document.getElementById("sheet-search-input");
  const query = searchInput ? searchInput.value.toLowerCase().trim() : "";

  if (!tbody) return;

  let filtered = sheetIssuesCache.filter(item => {
    if (currentSheetFilter === "OPEN" && item.status !== "OPEN") return false;
    if (currentSheetFilter === "RESOLVED" && item.status !== "RESOLVED") return false;
    if (currentSheetFilter === "critical" && item.severity !== "critical") return false;

    if (query) {
      const matchTitle = (item.title || "").toLowerCase().includes(query);
      const matchDesc = (item.description || "").toLowerCase().includes(query);
      const matchSelector = (item.target_selector || "").toLowerCase().includes(query);
      const matchRole = (item.suggested_role || "").toLowerCase().includes(query);
      if (!matchTitle && !matchDesc && !matchSelector && !matchRole) return false;
    }
    return true;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = "";
    if (emptyState) emptyState.style.display = "block";
    return;
  }

  if (emptyState) emptyState.style.display = "none";

  tbody.innerHTML = filtered.map(item => {
    const isResolved = item.status === "RESOLVED";
    const statusClass = isResolved ? "sheet-status-resolved" : "sheet-status-open";
    const priorityClass = `priority-${(item.severity || "medium").toLowerCase()}`;
    const dateStr = item.created_at ? item.created_at.slice(0, 16).replace("T", " ") : "";

    return `
      <tr data-id="${item.id}">
        <td style="font-weight: 600; color: #94A3B8;">#${item.id}</td>
        <td>
          <span class="sheet-status-pill ${statusClass}">${item.status}</span>
        </td>
        <td>
          <span class="sheet-priority-pill ${priorityClass}">${item.severity}</span>
        </td>
        <td>
          <span class="sheet-cat-tag">${escapeHtml(item.category || "bug")}</span>
        </td>
        <td>
          <span class="sheet-selector-code">${escapeHtml(item.target_selector || "")}</span>
        </td>
        <td>
          <span style="font-size: 11px; color: #93C5FD;">${escapeHtml(item.tab_name || "")}</span>
        </td>
        <td>
          <strong style="color: #F8FAFC; display: block; margin-bottom: 3px;">${escapeHtml(item.title)}</strong>
          <span style="color: #94A3B8; font-size: 11.5px;">${escapeHtml(item.description)}</span>
        </td>
        <td>
          <span class="sheet-role-badge">${escapeHtml(item.suggested_role || "")}</span>
        </td>
        <td style="font-size: 11px; color: #64748B; white-space: nowrap;">${dateStr}</td>
        <td>
          <div class="sheet-action-btns">
            <button type="button" class="btn-sheet-toggle-status" onclick="handleToggleIssueStatus(${item.id}, '${item.status}')" title="${isResolved ? 'Reopen' : 'Mark Resolved'}">
              ${isResolved ? 'Reopen' : 'Resolve'}
            </button>
            <button type="button" class="btn-sheet-del" onclick="handleDeleteIssue(${item.id})" title="Delete">
              &times;
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

window.handleToggleIssueStatus = async function(issueId, currentStatus) {
  const targetStatus = currentStatus === "OPEN" ? "RESOLVED" : "OPEN";
  try {
    const res = await fetch(`${API_BASE}/v1/internal-sheet/issues/${issueId}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: targetStatus })
    });
    if (!res.ok) throw new Error("Status update failed");
    showToast(`Issue #${issueId} marked as ${targetStatus}`, "success");
    await loadInternalSheetData();
  } catch (err) {
    showToast(err.message, "error");
  }
};

window.handleDeleteIssue = async function(issueId) {
  if (!confirm(`Delete internal sheet issue #${issueId}?`)) return;
  try {
    const res = await fetch(`${API_BASE}/v1/internal-sheet/issues/${issueId}`, {
      method: "DELETE"
    });
    if (!res.ok) throw new Error("Delete failed");
    showToast(`Issue #${issueId} deleted`, "info");
    await loadInternalSheetData();
  } catch (err) {
    showToast(err.message, "error");
  }
};

// Initialize listeners on load
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    initConceptAnnotationEvents();
    initInternalSheetModalEvents();
  });
} else {
  initConceptAnnotationEvents();
  initInternalSheetModalEvents();
}



