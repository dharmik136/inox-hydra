// -------------------------------------------------------------
// LinkedIn Studio - Side Panel Controller
// -------------------------------------------------------------
const LOCAL_API = "http://127.0.0.1:8000/api";

document.addEventListener("DOMContentLoaded", () => {
  const textarea = document.getElementById("sp-text");
  const charCount = document.getElementById("sp-char-count");
  const foldStatus = document.getElementById("sp-fold-status");
  const toast = document.getElementById("sp-toast");

  // Load scheduled post by default
  fetch(`${LOCAL_API}/posts?status=scheduled`)
    .then(r => r.json())
    .then(data => {
      if (data.posts && data.posts.length && !textarea.value) {
        textarea.value = data.posts[0].content;
        updateStats();
      }
    })
    .catch(() => {});

  textarea.addEventListener("input", updateStats);

  function updateStats() {
    const val = textarea.value;
    charCount.innerText = val.length;
    const lines = val.split("\n");
    if (val.length > 210 || (lines.length >= 3 && lines[0].length > 140)) {
      foldStatus.innerText = "Truncated by fold";
      foldStatus.style.color = "#f59e0b";
    } else {
      foldStatus.innerText = "Fold Safe";
      foldStatus.style.color = "#10b981";
    }
  }

  // Formatting tools
  document.getElementById("sp-bold").addEventListener("click", () => {
    applyFormat(toUnicodeSansBold);
  });

  document.getElementById("sp-italic").addEventListener("click", () => {
    applyFormat(toUnicodeSansItalic);
  });

  document.getElementById("sp-clean").addEventListener("click", () => {
    textarea.value = cleanDashes(textarea.value);
    updateStats();
    showToast("Em-dashes cleaned!");
  });

  document.getElementById("sp-bullet").addEventListener("click", () => {
    insertAtCursor("• ");
  });

  document.getElementById("sp-arrow").addEventListener("click", () => {
    insertAtCursor("→ ");
  });

  function applyFormat(fn) {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selected = textarea.value.substring(start, end);
    if (!selected) return;
    const transformed = fn(selected);
    textarea.value = textarea.value.substring(0, start) + transformed + textarea.value.substring(end);
    textarea.selectionStart = start;
    textarea.selectionEnd = start + transformed.length;
    textarea.focus();
    updateStats();
  }

  function insertAtCursor(txt) {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    textarea.value = textarea.value.substring(0, start) + txt + textarea.value.substring(end);
    textarea.selectionStart = textarea.selectionEnd = start + txt.length;
    textarea.focus();
    updateStats();
  }

  // 1-Click "Insert into LinkedIn Composer" via Content Script
  document.getElementById("btn-inject-composer").addEventListener("click", async () => {
    const content = textarea.value.trim();
    if (!content) {
      showToast("Textarea is empty!");
      return;
    }

    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab || !tab.url || !tab.url.includes("linkedin.com")) {
        showToast("⚠️ Open LinkedIn in your active browser tab first!");
        return;
      }

      showToast("Injecting post into LinkedIn...");
      chrome.tabs.sendMessage(tab.id, { action: "INJECT_POST", content: content }, (response) => {
        if (chrome.runtime.lastError) {
          console.warn(chrome.runtime.lastError);
          showToast("⚠️ Please refresh your LinkedIn tab to activate bridge!");
        } else if (response && response.status === "success") {
          showToast("✅ Successfully inserted into LinkedIn composer!");
        } else {
          showToast("⚠️ Click 'Start a post' on LinkedIn first!");
        }
      });
    } catch (err) {
      console.error(err);
      showToast("Injection error: " + err.message);
    }
  });

  // Copy to Clipboard
  document.getElementById("btn-copy-clipboard").addEventListener("click", async () => {
    await navigator.clipboard.writeText(textarea.value);
    showToast("Copied to clipboard!");
  });

  // Open Full Dashboard
  document.getElementById("btn-open-full-studio").addEventListener("click", () => {
    chrome.tabs.create({ url: "http://127.0.0.1:8000" });
  });

  // Tabs Toggle
  const tabComposer = document.getElementById("tab-composer-btn");
  const tabQueue = document.getElementById("tab-queue-btn");
  const tabCrm = document.getElementById("tab-crm-btn");
  const panelComposer = document.getElementById("panel-composer");
  const panelQueue = document.getElementById("panel-queue");
  const panelCrm = document.getElementById("panel-crm");

  tabComposer.addEventListener("click", () => {
    tabComposer.classList.add("active");
    tabQueue.classList.remove("active");
    tabCrm.classList.remove("active");
    panelComposer.style.display = "block";
    panelQueue.style.display = "none";
    panelCrm.style.display = "none";
  });

  tabQueue.addEventListener("click", () => {
    tabQueue.classList.add("active");
    tabComposer.classList.remove("active");
    tabCrm.classList.remove("active");
    panelComposer.style.display = "none";
    panelQueue.style.display = "block";
    panelCrm.style.display = "none";
    loadSideQueue();
  });

  tabCrm.addEventListener("click", () => {
    tabCrm.classList.add("active");
    tabComposer.classList.remove("active");
    tabQueue.classList.remove("active");
    panelComposer.style.display = "none";
    panelQueue.style.display = "none";
    panelCrm.style.display = "block";
    loadSideCRM();
  });

  function showToast(msg) {
    toast.innerText = msg;
    setTimeout(() => {
      if (toast.innerText === msg) toast.innerText = "";
    }, 3500);
  }
});

// Fast Unicode transformers
function toUnicodeSansBold(text) {
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const code = text.charCodeAt(i);
    if (code >= 65 && code <= 90) out += String.fromCodePoint(0x1D5D4 + code - 65);
    else if (code >= 97 && code <= 122) out += String.fromCodePoint(0x1D5EE + code - 97);
    else if (code >= 48 && code <= 57) out += String.fromCodePoint(0x1D7EC + code - 48);
    else out += text[i];
  }
  return out;
}

function toUnicodeSansItalic(text) {
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const code = text.charCodeAt(i);
    if (code >= 65 && code <= 90) out += String.fromCodePoint(0x1D608 + code - 65);
    else if (code >= 97 && code <= 122) out += String.fromCodePoint(0x1D622 + code - 97);
    else out += text[i];
  }
  return out;
}

function cleanDashes(text) {
  return text.replace(/\u2014/g, ", ").replace(/\u2013/g, ", ").replace(/(?<=\w)--+(?=\w)/g, ", ").replace(/[ \t]+/g, " ");
}

async function loadSideQueue() {
  const container = document.getElementById("queue-mini-list");
  container.innerHTML = "<p style='color: var(--text-dim);'>Loading queue...</p>";
  try {
    const res = await fetch(`${LOCAL_API}/posts?status=scheduled`);
    const json = await res.json();
    const posts = json.posts || [];
    container.innerHTML = "";

    if (!posts.length) {
      container.innerHTML = "<p style='color: var(--text-dim);'>No scheduled posts.</p>";
      return;
    }

    posts.forEach(p => {
      const item = document.createElement("div");
      item.className = "queue-item-mini";
      const schedTime = p.scheduled_for ? new Date(p.scheduled_for).toLocaleString() : "Today at 5:30 PM";
      item.innerHTML = `
        <div class="queue-item-time">⏰ ${schedTime}</div>
        <div class="queue-item-text">${p.content.split("\n")[0]}</div>
      `;
      item.addEventListener("click", () => {
        document.getElementById("sp-text").value = p.content;
        document.getElementById("tab-composer-btn").click();
      });
      container.appendChild(item);
    });
  } catch (err) {
    container.innerHTML = "<p style='color: var(--text-dim);'>Failed to load queue.</p>";
  }
}

async function loadSideCRM() {
  const container = document.getElementById("crm-mini-list");
  const countBadge = document.getElementById("sp-crm-count");
  container.innerHTML = "<p style='color: var(--text-dim);'>Loading prospects...</p>";
  try {
    const res = await fetch(`${LOCAL_API}/leads`);
    const json = await res.json();
    const leads = json.leads || [];
    container.innerHTML = "";
    if (countBadge) countBadge.innerText = `${leads.length} Leads`;

    if (!leads.length) {
      container.innerHTML = "<p style='color: var(--text-dim);'>No prospects yet. Browse comments on LinkedIn to auto-capture engagers.</p>";
      return;
    }

    leads.forEach(l => {
      const card = document.createElement("div");
      card.className = "queue-item-mini";
      card.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 4px;">
          <strong style="color: var(--text); font-size: 12.5px;">${escapeHtml(l.name)}</strong>
          <span style="font-size: 10px; padding: 2px 6px; border-radius: 4px; background: rgba(99, 102, 241, 0.2); color: #a5b4fc;">${escapeHtml(l.status)}</span>
        </div>
        <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 6px;">${escapeHtml(l.headline || l.company || '')}</div>
        <div id="agno-dossier-${l.id}" style="display: none; font-size: 11px; background: rgba(15, 23, 42, 0.8); border-radius: 6px; padding: 8px; margin-bottom: 8px; border: 1px solid rgba(99, 102, 241, 0.35); color: var(--text-secondary);"></div>
        <div style="display: flex; gap: 6px; justify-content: flex-end;">
          ${l.profile_url ? `<a href="${escapeHtml(l.profile_url)}" target="_blank" style="font-size: 11px; color: var(--accent); text-decoration: none; padding: 3px 6px;">Profile ↗</a>` : ''}
          <button class="tool-btn btn-side-enrich" data-id="${l.id}" style="font-size: 11px; padding: 3px 8px; background: rgba(99, 102, 241, 0.2); border-color: #6366f1; color: #a5b4fc;">✨ Enrich</button>
          <button class="tool-btn btn-side-copy-dm" data-id="${l.id}" style="font-size: 11px; padding: 3px 8px;">⚡ Copy DM</button>
        </div>
      `;
      container.appendChild(card);
    });

    container.querySelectorAll(".btn-side-enrich").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const id = btn.getAttribute("data-id");
        const dossierBox = document.getElementById(`agno-dossier-${id}`);
        if (dossierBox.style.display === "block") {
          dossierBox.style.display = "none";
          btn.innerText = "✨ Enrich";
          return;
        }
        btn.innerText = "Enriching...";
        try {
          const enrichRes = await fetch(`${LOCAL_API}/leads/${id}/enrich`, { method: "POST" });
          const enrichJson = await enrichRes.json();
          if (enrichJson.status === "success" && enrichJson.enrichment) {
            const en = enrichJson.enrichment;
            dossierBox.innerHTML = `
              <div style="font-weight: 600; color: #a5b4fc; margin-bottom: 4px;">⚡ Agno Intelligence Dossier:</div>
              <div style="margin-bottom: 3px;"><strong>Stack:</strong> ${escapeHtml(en.estimated_tech_stack || "Enterprise")}</div>
              <div style="margin-bottom: 4px;"><strong>Friction:</strong> ${escapeHtml(en.friction_points || "")}</div>
              <div style="font-weight: 600; color: #38bdf8; margin-top: 4px;">Top Hook:</div>
              <div style="font-style: italic; color: #e2e8f0;">"${escapeHtml(en.icebreakers ? en.icebreakers[0] : "")}"</div>
            `;
            dossierBox.style.display = "block";
            btn.innerText = "Hide Dossier";
          } else {
            btn.innerText = "Failed";
            setTimeout(() => { btn.innerText = "✨ Enrich"; }, 2000);
          }
        } catch {
          btn.innerText = "Error";
          setTimeout(() => { btn.innerText = "✨ Enrich"; }, 2000);
        }
      });
    });

    container.querySelectorAll(".btn-side-copy-dm").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const id = btn.getAttribute("data-id");
        btn.innerText = "Fetching...";
        try {
          const dmRes = await fetch(`${LOCAL_API}/leads/${id}/dm-script`);
          const dmJson = await dmRes.json();
          if (dmJson.dm_script) {
            await navigator.clipboard.writeText(dmJson.dm_script);
            btn.innerText = "✓ Copied!";
            const toast = document.getElementById("sp-toast");
            if (toast) {
              toast.innerText = `Copied DM for ${dmJson.lead_name}!`;
              setTimeout(() => { toast.innerText = ""; }, 3000);
            }
          }
        } catch {
          btn.innerText = "Failed";
        }
        setTimeout(() => { btn.innerText = "⚡ Copy DM"; }, 2500);
      });
    });
  } catch (err) {
    container.innerHTML = "<p style='color: #ef4444;'>Local server offline.</p>";
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
