/**
 * Calls the studio through the service worker.
 *
 * The API requires a token the panel cannot read, and a direct fetch from here
 * carries no credential at all, so this used to 401 and the post attribution
 * chain never recorded its first row.
 */
function studioApiFromPanel(path, options) {
  return new Promise((resolve) => {
    let body = null;
    if (options && options.body) {
      try { body = JSON.parse(options.body); } catch (e) { body = null; }
    }
    // PANEL_WRITE, not STUDIO_API: that relay serves content scripts and its
    // allowlist rightly refuses this path, which is why the call used to fail
    // without a word.
    chrome.runtime.sendMessage(
      { action: "PANEL_WRITE", path: path, body: body },
      (response) => {
        const ok = !chrome.runtime.lastError && Boolean(response && response.ok);
        resolve({
          ok: ok,
          json: () => Promise.resolve(ok && response ? response.data : {})
        });
      }
    );
  });
}

// -------------------------------------------------------------
// Inox Hydra - Side Panel Controller
// -------------------------------------------------------------

/** The studio post whose text the panel was filled with, or null. */
let panelPostId = null;

// The studio's fold, the two numbers in studio/backend/fold.py. The panel used
// to carry its own rule (over 210 characters, or a first line over 140 only
// once there were three lines), so a 165 character one-line opening was "Fold
// Safe" here while the studio said it was cut off.
const MOBILE_FOLD_CHARS = 140;
const MOBILE_FOLD_LINES = 3;

/** The text as a reader counts it: decoration marks stripped, one per code point. */
function measurableText(text) {
  return Array.from(text || "").filter((ch) => !/\p{M}/u.test(ch)).join("");
}

/** The studio's verdict (formatters.analyze_hook): the first lines, and the first line alone, fit. */
function isFoldSafe(value) {
  const text = measurableText(value);
  // Python's splitlines, which drops the empty line after a final break.
  const lines = text.split(/\r\n|[\n\v\f\r\x1c-\x1e\x85\u2028\u2029]/);
  if (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
  const firstLine = (lines.find((line) => line.trim()) || "").trim();
  const preFold = Array.from(lines.slice(0, MOBILE_FOLD_LINES).join("\n")).length;
  return preFold <= MOBILE_FOLD_CHARS && Array.from(firstLine).length <= MOBILE_FOLD_CHARS;
}

/**
 * A GET against the studio, made by the service worker so it carries the
 * studio token. This page used to fetch the studio directly, which carries
 * none, so every call was refused and the panel showed "No prospects yet" and
 * "No scheduled posts" over a studio that was full of both.
 * Resolves to { ok, httpStatus, data }; httpStatus 0 means unreachable.
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

/** Why a panel read failed, in words the creator can act on. */
function failureText(result, what) {
  if (result.httpStatus === 401 || result.httpStatus === 403) {
    return `Could not load ${what}: the studio has not paired with this browser. Open http://127.0.0.1:8000 in this browser once.`;
  }
  if (result.httpStatus === 0) return `Could not load ${what}: the studio is not running.`;
  return `Could not load ${what} (the studio answered ${result.httpStatus}).`;
}

document.addEventListener("DOMContentLoaded", () => {
  const textarea = document.getElementById("sp-text");
  const charCount = document.getElementById("sp-char-count");
  const foldStatus = document.getElementById("sp-fold-status");
  const toast = document.getElementById("sp-toast");

  // Open on the post to make next: one that is due, else the next queued.
  loadQueuedPosts().then(result => {
    const posts = result.ok ? result.posts : [];
    if (posts.length && !textarea.value) {
      textarea.value = posts[0].content;
      panelPostId = posts[0].id || null;
      updateStats();
    }
  });

  textarea.addEventListener("input", updateStats);

  function updateStats() {
    const val = textarea.value;
    charCount.innerText = Array.from(measurableText(val)).length;
    if (!isFoldSafe(val)) {
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
          // Record the post at the moment the studio causes it to exist.
          //
          // This line is the difference between a CRM full of strangers and
          // one that can say which post brought each person in. Without a row
          // here, the activity URN seen later on the permalink has nothing to
          // attach to, and three complete attribution surfaces keep returning
          // zero. It is bookkeeping on an event the studio itself caused, so
          // it contacts nothing but the local backend.
          //
          // The toast waits for the studio's answer. It used to promise the
          // link whatever the studio said, including when it answered that
          // the text could not be identified again.
          studioApiFromPanel("/api/v1/posts/injected", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            // Which queued post this text came from, so the studio arms that
            // post rather than recording a second copy of it beside it.
            body: JSON.stringify({ content: content, post_id: panelPostId })
          }).then((res) => res.json()).then((data) => {
            if (data && data.status === "recorded") {
              showToast("✅ Inserted into the composer. Open the post once after publishing and the studio will link it.");
            } else if (data && data.message) {
              showToast("Inserted into the composer. " + data.message);
            } else {
              showToast("Inserted into the composer, but the studio did not record it, so it cannot link this post later.");
            }
          }).catch(() => {
            showToast("Inserted into the composer, but the studio did not record it, so it cannot link this post later.");
          });
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
  const tabHealth = document.getElementById("tab-health-btn");
  const panelComposer = document.getElementById("panel-composer");
  const panelQueue = document.getElementById("panel-queue");
  const panelCrm = document.getElementById("panel-crm");
  const panelHealth = document.getElementById("panel-health");

  tabComposer.addEventListener("click", () => {
    tabComposer.classList.add("active");
    tabQueue.classList.remove("active");
    tabCrm.classList.remove("active");
    tabHealth.classList.remove("active");
    panelComposer.style.display = "block";
    panelQueue.style.display = "none";
    panelCrm.style.display = "none";
    panelHealth.style.display = "none";
  });

  tabQueue.addEventListener("click", () => {
    tabQueue.classList.add("active");
    tabComposer.classList.remove("active");
    tabCrm.classList.remove("active");
    tabHealth.classList.remove("active");
    panelComposer.style.display = "none";
    panelQueue.style.display = "block";
    panelCrm.style.display = "none";
    panelHealth.style.display = "none";
    loadSideQueue();
  });

  tabCrm.addEventListener("click", () => {
    tabCrm.classList.add("active");
    tabComposer.classList.remove("active");
    tabQueue.classList.remove("active");
    tabHealth.classList.remove("active");
    panelComposer.style.display = "none";
    panelQueue.style.display = "none";
    panelCrm.style.display = "block";
    panelHealth.style.display = "none";
    loadSideCRM();
  });

  tabHealth.addEventListener("click", () => {
    tabHealth.classList.add("active");
    tabComposer.classList.remove("active");
    tabQueue.classList.remove("active");
    tabCrm.classList.remove("active");
    panelComposer.style.display = "none";
    panelQueue.style.display = "none";
    panelCrm.style.display = "none";
    panelHealth.style.display = "block";
    loadSideHealth();
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

/**
 * Due posts, then queued ones, earliest first.
 *
 * The studio's queue posts nothing: at a post's time it marks it due, for the
 * creator to post. Those are the posts this panel exists to insert, so they
 * come first.
 */
async function loadQueuedPosts() {
  const [due, queued] = await Promise.all([
    panelApi("/api/posts?status=due"),
    panelApi("/api/posts?status=scheduled"),
  ]);
  if (!queued.ok) return { ok: false, result: queued, posts: [] };
  return { ok: true, posts: [...(due.ok ? due.data.posts || [] : []), ...(queued.data.posts || [])] };
}

async function loadSideQueue() {
  const container = document.getElementById("queue-mini-list");
  container.innerHTML = "<p style='color: var(--text-dim);'>Loading queue...</p>";
  try {
    const loaded = await loadQueuedPosts();
    const result = loaded.ok ? loaded : loaded.result;
    if (!loaded.ok) {
      container.innerHTML = "";
      const p = document.createElement("p");
      p.style.color = "var(--text-dim)";
      p.textContent = failureText(result, "the queue");
      container.appendChild(p);
      return;
    }
    const posts = loaded.posts;
    container.innerHTML = "";

    if (!posts.length) {
      container.innerHTML = "<p style='color: var(--text-dim);'>No scheduled posts.</p>";
      return;
    }

    posts.forEach(p => {
      const item = document.createElement("div");
      item.className = "queue-item-mini";
      // A post queued without a time says so. This used to print "Today at
      // 5:30 PM", a time nobody set. Both lines are text, not markup, so a
      // post that mentions <Thinking in Systems> shows it.
      const schedTime = p.scheduled_for ? new Date(p.scheduled_for).toLocaleString() : "No time set";
      const time = document.createElement("div");
      time.className = "queue-item-time";
      time.textContent = p.status === "due" ? `Due now, post it: ${schedTime}` : `⏰ ${schedTime}`;
      const text = document.createElement("div");
      text.className = "queue-item-text";
      text.textContent = (p.content || "").split("\n")[0];
      item.append(time, text);
      item.addEventListener("click", () => {
        document.getElementById("sp-text").value = p.content;
        panelPostId = p.id || null;
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
    const result = await panelApi("/api/leads");
    if (!result.ok) {
      container.innerHTML = "";
      const p = document.createElement("p");
      p.style.color = "var(--text-dim)";
      p.textContent = failureText(result, "your leads");
      container.appendChild(p);
      if (countBadge) countBadge.innerText = "";
      return;
    }
    const leads = result.data.leads || [];
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
        <div style="display: flex; gap: 6px; justify-content: flex-end;">
          ${l.profile_url ? `<a href="${escapeHtml(l.profile_url)}" target="_blank" style="font-size: 11px; color: var(--accent); text-decoration: none; padding: 3px 6px;">Profile ↗</a>` : ''}
          <button class="tool-btn btn-side-copy-dm" data-id="${l.id}" style="font-size: 11px; padding: 3px 8px;">⚡ Copy DM</button>
        </div>
      `;
      container.appendChild(card);
    });

    // The Enrich button is gone. It showed a "dossier" of a company's stack
    // and problems guessed from the person's job title; the studio retired the
    // route that produced it (410) rather than keep presenting a guess as
    // research.

    container.querySelectorAll(".btn-side-copy-dm").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const id = btn.getAttribute("data-id");
        btn.innerText = "Fetching...";
        try {
          const result = await panelApi(`/api/leads/${encodeURIComponent(id)}/dm-script`);
          const dmJson = result.ok ? result.data : {};
          if (!dmJson.dm_script) {
            btn.innerText = "Failed";
          } else {
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

function panelStorage(keys) {
  return new Promise((resolve) => {
    try {
      chrome.storage.local.get(keys, (items) => resolve(items || {}));
    } catch (err) {
      resolve({});
    }
  });
}

/**
 * The three things the bridge decided and never said: how many captures are
 * waiting for a studio that was busy, what the studio last refused and why,
 * and whether this extension speaks the studio's ingest contract.
 *
 * The waiting count comes from the extension's own storage, which is where the
 * queue lives, so it is right even while the studio cannot be reached. A count
 * nobody has written yet is "not measured", never a zero.
 */
async function waitingAndRefusalPanel(health) {
  const kept = await panelStorage(["waitingCaptures", "lastRefusal"]);
  const waiting = kept.waitingCaptures || null;
  const refusal = kept.lastRefusal || null;
  const shake = (health && health.contract) || {};
  let html = "";

  if (shake.reload_required && shake.message) {
    html += `
      <div style="background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 6px; padding: 8px; margin-bottom: 8px;">
        <div style="color: #f87171; font-weight: 600; margin-bottom: 4px; font-size: 11px;">Reload this extension</div>
        <div style="font-size: 10.5px; color: var(--text-muted);">${escapeHtml(shake.message)}</div>
      </div>
    `;
  }

  const count = waiting && typeof waiting.waiting === "number" ? waiting.waiting : null;
  if (count === null) {
    html += `
      <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 6px; padding: 8px; margin-bottom: 8px; font-size: 11px; color: var(--text-muted);">
        Captures waiting for the studio: not measured yet.
      </div>
    `;
  } else if (count > 0) {
    html += `
      <div style="background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.2); border-radius: 6px; padding: 8px; margin-bottom: 8px;">
        <div style="color: #f59e0b; font-weight: 600; margin-bottom: 4px; font-size: 11px;">${count} capture(s) waiting</div>
        <div style="font-size: 10.5px; color: var(--text-muted);">
          Your studio was busy or closed. They are sent again on their own, oldest first.
        </div>
      </div>
    `;
  }

  if (refusal && refusal.message) {
    html += `
      <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 6px; padding: 8px; margin-bottom: 8px;">
        <div style="color: var(--text-muted); font-size: 11px; margin-bottom: 4px;">The studio last refused a capture</div>
        <div style="font-size: 10.5px; color: var(--text);">${escapeHtml(refusal.message)}</div>
      </div>
    `;
  }
  return html;
}

async function loadSideHealth() {
  const container = document.getElementById("health-mini-list");
  const badge = document.getElementById("sp-health-badge");
  container.innerHTML = "<p style='color: var(--text-dim);'>Checking telemetry health...</p>";

  try {
    const result = await panelApi("/api/v1/extension/health");
    if (!result.ok) {
      container.innerHTML = `<p style="color: #ef4444;">${escapeHtml(failureText(result, "health diagnostics"))}</p>`;
      badge.innerText = "Offline";
      badge.style.color = "#ef4444";
      return;
    }

    const health = result.data || {};
    const bridge = health.bridge || {};
    const extractors = health.extractors || [];
    const drift = health.recent_drift || [];
    const voyagerActive = health.voyager_active;

    if (bridge.connected) {
      badge.innerText = voyagerActive ? "Voyager Active" : "DOM Fallback";
      badge.style.color = voyagerActive ? "var(--success)" : "#f59e0b";
    } else {
      badge.innerText = "Bridge Idle";
      badge.style.color = "var(--text-dim)";
    }

    // What the creator could not see before: captures waiting because the
    // studio was busy, the last refusal in the studio's own words, and whether
    // this extension is older than the studio's ingest contract. Every one of
    // these was decided somewhere and shown nowhere.
    let html = await waitingAndRefusalPanel(health);

    html += `
      <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 6px; padding: 10px; margin-bottom: 8px;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
          <span style="color: var(--text-muted);">Network Interceptor</span>
          <span style="font-weight: 600; color: ${voyagerActive ? "var(--success)" : "#f59e0b"};">
            ${voyagerActive ? "🟢 Active (Exact JSON)" : "🟡 Standby"}
          </span>
        </div>
        <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
          <span style="color: var(--text-muted);">Schema Registry</span>
          <span style="color: var(--accent); font-family: monospace;">v${escapeHtml(health.schema_version || "2026.10.1")}</span>
        </div>
        <div style="display: flex; justify-content: space-between;">
          <span style="color: var(--text-muted);">24h Network Captures</span>
          <span style="font-weight: 600;">${health.voyager_24h_captures || 0}</span>
        </div>
      </div>
    `;

    if (drift.length > 0) {
      html += `
        <div style="background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 6px; padding: 8px; margin-bottom: 8px;">
          <div style="color: #f87171; font-weight: 600; margin-bottom: 4px; font-size: 11px;">⚠️ Detected API Drift (${drift.length})</div>
          <div style="font-size: 10.5px; color: var(--text-muted);">
            ${escapeHtml(drift[0].schema_name)}: missing ${escapeHtml((drift[0].drift_fields || []).join(", "))}
          </div>
        </div>
      `;
    } else {
      html += `
        <div style="background: rgba(16, 185, 129, 0.06); border: 1px solid rgba(16, 185, 129, 0.15); border-radius: 6px; padding: 8px; margin-bottom: 8px; text-align: center; color: var(--success); font-size: 11px;">
          ✓ Zero drift detected - 100% schema match
        </div>
      `;
    }

    html += `<div style="font-size: 11px; color: var(--text-muted); margin-bottom: 6px;">Observer Pipelines:</div>`;
    extractors.forEach(ext => {
      const isOk = ext.state === "working";
      const isDrift = ext.state === "drifting";
      const dot = isOk ? "🟢" : (isDrift ? "🔴" : "⚪");
      html += `
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.03); font-size: 11px;">
          <span style="color: var(--text);">${dot} ${escapeHtml(ext.label)}</span>
          <span style="color: var(--text-dim); font-size: 10px;">${ext.state}</span>
        </div>
      `;
    });

    container.innerHTML = html;
  } catch (err) {
    container.innerHTML = `<p style="color: #ef4444;">Could not load health metrics.</p>`;
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
