// -------------------------------------------------------------
// LinkedIn Studio Bridge: the creator's own pages
// -------------------------------------------------------------
//
// content.js reads other people: engagers, analytics cards, the composer. This
// file reads the creator, and only the creator:
//
//   /in/<you>/                         profile, experience, education, skills
//   /in/<you>/overlay/contact-info/    email, phone, birthday, websites
//   /in/<you>/details/skills/          the full skills list
//   /in/<you>/recent-activity/all/     posts you wrote
//   /in/<you>/recent-activity/comments/   comments you left on other posts
//   /in/<you>/recent-activity/reactions/  posts you reacted to
//
// How it knows a page is yours. Before onboarding, from signs only the owner
// of a profile sees (the edit controls) or from LinkedIn itself sending
// /in/me/ to that profile. The studio then asks the creator to confirm. After
// that, from the confirmed vanity alone. A stranger's profile is never sent:
// without a sign of ownership, and once a creator is confirmed without a
// matching vanity, nothing leaves this page.
//
// Scrolling. The activity pages load more as you scroll. When the creator has
// clicked an import in the studio, and only then, this script scrolls the page
// itself: at a human pace, with a banner and a Stop button, pausing while the
// tab is hidden, and stopping when the list stops growing. The request lives
// in the studio and expires after 30 minutes, so a scroll always traces back
// to a recent click.
//
// Selectors. LinkedIn's markup is not documented and changes. Every reader
// here tries more than one route to the same field and returns null rather
// than a guess when none match. The onboarding screen shows what was read, so
// a gap is visible to the creator instead of silently absent.
//
// Strict Invariants:
// - Zero em-dashes.
// - No network request to LinkedIn. This reads the page the creator has open.
// - Nothing about another member is sent from here.

(function ownPages() {
  "use strict";

  const EXTENSION_VERSION = chrome.runtime.getManifest().version;
  const HEARTBEAT_MS = 60 * 1000;

  // ---------------------------------------------------------------
  // Talking to the studio, through the worker's allowlisted relay
  // ---------------------------------------------------------------

  function studio(path, body) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage(
          { action: "STUDIO_API", path, method: "POST", body: body || {} },
          (response) => {
            if (chrome.runtime.lastError || !response || response.status !== "success") {
              resolve(null);
              return;
            }
            resolve(response.data || {});
          }
        );
      } catch (err) {
        // The extension was reloaded under this page. Nothing to do until the
        // page is reloaded too.
        resolve(null);
      }
    });
  }

  let confirmedVanity; // undefined: not asked yet; null: nobody confirmed
  async function getConfirmedVanity(force) {
    if (confirmedVanity !== undefined && !force) return confirmedVanity;
    const data = await studio("/api/v1/identity/me");
    confirmedVanity = data ? data.vanity || null : null;
    return confirmedVanity;
  }

  // ---------------------------------------------------------------
  // Where we are
  // ---------------------------------------------------------------

  function vanityOf(href) {
    const match = /linkedin\.com\/in\/([^/?#]+)/i.exec(href || "") || /^\/in\/([^/?#]+)/i.exec(href || "");
    if (!match) return "";
    try {
      return decodeURIComponent(match[1]).toLowerCase();
    } catch (err) {
      return match[1].toLowerCase();
    }
  }

  function pageKind() {
    const path = window.location.pathname;
    if (!/^\/in\/[^/]+/.test(path)) return path.startsWith("/feed") ? "feed" : "other";
    if (/\/recent-activity\/(all|shares)\/?/.test(path)) return "activity_posts";
    if (/\/recent-activity\/comments\/?/.test(path)) return "activity_comments";
    if (/\/recent-activity\/reactions\/?/.test(path)) return "activity_reactions";
    if (/\/overlay\/contact-info\/?/.test(path)) return "contact";
    if (/\/details\/skills\/?/.test(path)) return "skills";
    if (/^\/in\/[^/]+\/?$/.test(path)) return "profile";
    return "profile_other";
  }

  // ---------------------------------------------------------------
  // Small readers
  // ---------------------------------------------------------------

  const clean = (text) => (text || "").replace(/\s+/g, " ").trim();

  function first(root, selectors) {
    for (const selector of selectors) {
      const found = (root || document).querySelector(selector);
      if (found && clean(found.innerText || found.textContent)) return found;
    }
    return null;
  }

  function textOf(root, selectors) {
    const el = first(root, selectors);
    return el ? clean(el.innerText || el.textContent) : null;
  }

  // LinkedIn renders visible text in aria-hidden spans and a screen-reader
  // copy beside it. Reading the aria-hidden ones gives each string once.
  function visibleStrings(root) {
    const out = [];
    const seen = new Set();
    root.querySelectorAll('span[aria-hidden="true"]').forEach((span) => {
      const value = clean(span.innerText || span.textContent);
      if (value && !seen.has(value)) {
        seen.add(value);
        out.push(value);
      }
    });
    return out;
  }

  function parseCount(text) {
    if (!text) return null;
    const match = /([\d.,]+)\s*([KkMm])?/.exec(text);
    if (!match) return null;
    let value = parseFloat(match[1].replace(/,/g, ""));
    if (Number.isNaN(value)) return null;
    if (/k/i.test(match[2] || "")) value *= 1000;
    if (/m/i.test(match[2] || "")) value *= 1000000;
    return Math.round(value);
  }

  // The section that follows an anchor like <div id="experience">.
  function sectionFor(anchorId) {
    const anchor = document.getElementById(anchorId);
    return anchor ? anchor.closest("section") : null;
  }

  // ---------------------------------------------------------------
  // Is this profile the viewer's own?
  // ---------------------------------------------------------------

  const OWNER_CONTROL = /^(edit intro|add profile section|open to|enhance profile|add section|edit about|add experience|edit experience)/i;
  const VISITOR_CONTROL = /^(invite .* to connect|connect|message|follow|pending)/i;

  function selfEvidence() {
    const evidence = [];
    const main = document.querySelector("main") || document.body;

    const labels = Array.from(main.querySelectorAll("button, a"))
      .slice(0, 400)
      .map((el) => clean(el.getAttribute("aria-label") || el.innerText || ""));
    const ownerSeen = labels.some((label) => OWNER_CONTROL.test(label)) ||
      !!main.querySelector('a[href*="/edit/intro/"], a[href*="/add-edit/"]');
    const visitorSeen = labels.some((label) => VISITOR_CONTROL.test(label));
    // Both present is a page we cannot read confidently, so it proves nothing.
    if (ownerSeen && !visitorSeen) evidence.push("owner_edit_controls");

    try {
      const cameFrom = sessionStorage.getItem("studio_me_redirect");
      if (cameFrom && cameFrom === vanityOf(window.location.href)) evidence.push("me_redirect");
    } catch (err) {
      // sessionStorage can be unavailable; the other signal still stands.
    }
    return evidence;
  }

  // /in/me/ is LinkedIn's alias for the viewer's own profile. Whether it
  // redirects on the server or in the page, arriving at /in/me/ and then at a
  // real vanity is LinkedIn telling us which profile is ours.
  function noteMeRedirect() {
    try {
      if (/^\/in\/me\/?/.test(window.location.pathname)) {
        sessionStorage.setItem("studio_me_pending", "1");
        return;
      }
      if (sessionStorage.getItem("studio_me_pending") === "1") {
        const vanity = vanityOf(window.location.href);
        if (vanity && vanity !== "me") {
          sessionStorage.setItem("studio_me_redirect", vanity);
          sessionStorage.removeItem("studio_me_pending");
        }
      }
    } catch (err) {
      // Ignored; this is one of two signals.
    }
  }

  // ---------------------------------------------------------------
  // The profile
  // ---------------------------------------------------------------

  function readTopCard() {
    const main = document.querySelector("main") || document.body;
    const card = main.querySelector("section.artdeco-card") || main;
    const name = textOf(card, ["h1", ".text-heading-xlarge"]);
    const headline = textOf(card, [".text-body-medium.break-words", ".text-body-medium"]);
    const location = textOf(card, [".text-body-small.inline.t-black--light.break-words", ".pv-text-details__left-panel .text-body-small"]);

    let followers = null;
    let connections = null;
    main.querySelectorAll("li, span, a").forEach((el) => {
      if (followers !== null && connections !== null) return;
      const text = clean(el.innerText || el.textContent);
      if (text.length > 40) return;
      if (followers === null && /\bfollowers?\b/i.test(text)) followers = parseCount(text);
      if (connections === null && /\bconnections?\b/i.test(text)) connections = parseCount(text);
    });

    return { display_name: name, headline, location, follower_count: followers, connection_count: connections };
  }

  function readAbout() {
    const section = sectionFor("about");
    if (!section) return null;
    const strings = visibleStrings(section).filter((s) => !/^about$/i.test(s));
    return strings.length ? strings.join("\n") : null;
  }

  // One entry per top-level list item in a section. Positional, because the
  // items carry no labels: title first, then organisation, then dates.
  function readEntries(anchorId) {
    const section = sectionFor(anchorId);
    if (!section) return null; // absent from the page: the studio keeps what it has
    const items = Array.from(section.querySelectorAll(":scope ul > li")).filter(
      (li) => !li.parentElement.closest("li")
    );
    return items.map((li) => visibleStrings(li)).filter((strings) => strings.length);
  }

  function readPositions() {
    const entries = readEntries("experience");
    if (!entries) return null;
    return entries.slice(0, 40).map((s) => ({
      title: s[0] || null,
      company: s[1] ? s[1].split(" · ")[0] : null,
      date_range: s.find((x) => /\b(19|20)\d{2}\b|present/i.test(x)) || null,
      location: s.find((x, i) => i > 1 && !/\b(19|20)\d{2}\b|present/i.test(x) && x.length < 80) || null,
      description: s.length > 4 ? s.slice(4).join("\n") : null,
    }));
  }

  function readEducation() {
    const entries = readEntries("education");
    if (!entries) return null;
    return entries.slice(0, 20).map((s) => ({
      school: s[0] || null,
      degree: s[1] || null,
      date_range: s.find((x) => /\b(19|20)\d{2}\b/.test(x)) || null,
    }));
  }

  function readSkills() {
    // The details page has the whole list; the profile shows only a few.
    const root = pageKind() === "skills" ? document.querySelector("main") : sectionFor("skills");
    if (!root) return null;
    const skills = Array.from(root.querySelectorAll(":scope ul > li"))
      .filter((li) => !li.parentElement.closest("li"))
      .map((li) => visibleStrings(li)[0])
      .filter((s) => s && s.length < 120 && !/^show all/i.test(s));
    return skills.length ? skills : null;
  }

  function readContact() {
    const dialog = document.querySelector('[role="dialog"]') ||
      document.querySelector(".pv-contact-info") || null;
    if (!dialog) return null;
    const contact = { email: null, phone: null, birthday: null, websites: [] };
    dialog.querySelectorAll("section, .pv-contact-info__contact-type").forEach((block) => {
      const heading = clean(textOf(block, ["h3", "header"]) || "");
      const body = clean(
        Array.from(block.querySelectorAll("a, span, li"))
          .map((el) => clean(el.innerText))
          .filter((t) => t && t !== heading)
          .join(" ")
      );
      if (/^email/i.test(heading)) {
        const mail = block.querySelector('a[href^="mailto:"]');
        contact.email = mail ? mail.getAttribute("href").slice(7) : body || null;
      } else if (/^phone/i.test(heading)) {
        contact.phone = body || null;
      } else if (/^birthday/i.test(heading)) {
        contact.birthday = body || null;
      } else if (/^websites?/i.test(heading)) {
        block.querySelectorAll("a[href]").forEach((a) => {
          const href = a.getAttribute("href");
          if (href && !/linkedin\.com\/in\//.test(href)) contact.websites.push(href);
        });
      }
    });
    return contact;
  }

  async function captureProfile() {
    const kind = pageKind();
    const vanity = vanityOf(window.location.href);
    if (!vanity || vanity === "me") return;

    const mine = await getConfirmedVanity();
    const evidence = mine ? [] : selfEvidence();
    if (mine ? mine !== vanity : evidence.length === 0) return; // not ours: nothing leaves

    const payload = { vanity, self_evidence: evidence };
    if (kind === "profile") {
      Object.assign(payload, readTopCard());
      payload.about = readAbout();
      const positions = readPositions();
      if (positions) {
        payload.positions = positions;
        if (positions[0] && positions[0].company) payload.current_company = positions[0].company;
      }
      const education = readEducation();
      if (education) payload.education = education;
    }
    const skills = readSkills();
    if (skills && kind === "skills") payload.skills = skills;
    if (kind === "contact") payload.contact = readContact();

    const result = await studio("/api/v1/identity/observe", payload);
    if (result && result.status === "candidate") {
      toast("The studio found your profile. Confirm it's you in the studio's Setup screen.");
    }
  }

  // ---------------------------------------------------------------
  // Activity: posts, comments, reactions
  // ---------------------------------------------------------------

  function cardUrn(card) {
    const attr = card.getAttribute("data-urn") || card.getAttribute("data-id") || "";
    const match = /urn:li:activity:\d+/.exec(attr);
    return match ? match[0] : null;
  }

  function activityCards() {
    return Array.from(document.querySelectorAll('[data-urn^="urn:li:activity:"], [data-id^="urn:li:activity:"]'))
      .filter((card) => !card.parentElement.closest('[data-urn^="urn:li:activity:"], [data-id^="urn:li:activity:"]'));
  }

  function cardActor(card) {
    const link = card.querySelector(
      ".update-components-actor__meta-link, a.update-components-actor__image, .update-components-actor a[href*='/in/']"
    );
    return link ? vanityOf(link.getAttribute("href")) : "";
  }

  function cardActorName(card) {
    return textOf(card, [".update-components-actor__title span[aria-hidden='true']", ".update-components-actor__name"]);
  }

  function cardText(card) {
    return textOf(card, [".update-components-text", ".feed-shared-inline-show-more-text", ".feed-shared-update-v2__description"]);
  }

  function cardHeader(card) {
    return textOf(card, [".update-components-header__text-view", ".update-components-header"]) || "";
  }

  function cardCounts(card) {
    const counts = { reactions: null, comments: null, reposts: null, impressions: null };
    counts.reactions = parseCount(textOf(card, [".social-details-social-counts__reactions-count"]));
    card.querySelectorAll("button, span, a").forEach((el) => {
      const text = clean(el.getAttribute("aria-label") || el.innerText || "");
      if (text.length > 60) return;
      if (counts.comments === null && /\bcomments?\b/i.test(text)) counts.comments = parseCount(text);
      if (counts.reposts === null && /\breposts?\b/i.test(text)) counts.reposts = parseCount(text);
      if (counts.impressions === null && /\bimpressions?\b/i.test(text)) counts.impressions = parseCount(text);
    });
    return counts;
  }

  const REACTION_WORDS = [
    ["celebrates", "celebrate"], ["supports", "support"], ["loves", "love"],
    ["finds this insightful", "insightful"], ["finds this funny", "funny"], ["likes", "like"],
  ];

  function readActivity(kind, me) {
    const items = [];
    for (const card of activityCards()) {
      const urn = cardUrn(card);
      if (!urn) continue;
      const actor = cardActor(card);

      if (kind === "activity_posts") {
        // A repost's header names you and its actor is the original author.
        // The backend skips it by actor; it is sent with the true actor.
        items.push({ activity_urn: urn, actor, text: cardText(card), ...cardCounts(card) });
      } else if (kind === "activity_comments") {
        const mine = Array.from(card.querySelectorAll("article, .comments-comment-item")).filter((c) => {
          const link = c.querySelector("a[href*='/in/']");
          return link && vanityOf(link.getAttribute("href")) === me;
        });
        for (const comment of mine) {
          const text = textOf(comment, [".comments-comment-item__main-content", ".update-components-text", ".comments-comment-item-content-body"]);
          if (!text) continue;
          items.push({
            target_activity_urn: urn, kind: "comment", my_text: text,
            target_author: cardActorName(card), target_excerpt: (cardText(card) || "").slice(0, 300),
          });
        }
      } else if (kind === "activity_reactions") {
        const header = cardHeader(card).toLowerCase();
        const match = REACTION_WORDS.find(([word]) => header.includes(word));
        items.push({
          target_activity_urn: urn, kind: "reaction", reaction_kind: match ? match[1] : null,
          target_author: cardActorName(card), target_excerpt: (cardText(card) || "").slice(0, 300),
        });
      }
    }
    return items;
  }

  const sentKeys = new Set();

  async function sendActivity(kind, me) {
    const fresh = readActivity(kind, me).filter((item) => {
      const key = JSON.stringify([item.activity_urn || item.target_activity_urn, item.kind, item.my_text]);
      if (sentKeys.has(key)) return false;
      sentKeys.add(key);
      return true;
    });
    if (!fresh.length) return 0;
    if (kind === "activity_posts") {
      await studio("/api/v1/self/posts/ingest", { author: me, posts: fresh });
    } else {
      await studio("/api/v1/self/outbound/ingest", { actor: me, items: fresh });
    }
    return fresh.length;
  }

  // ---------------------------------------------------------------
  // The scroll, which happens only because the creator asked
  // ---------------------------------------------------------------

  const IMPORT_KIND = { activity_posts: "posts", activity_comments: "comments", activity_reactions: "reactions" };
  const MAX_ROUNDS = 250;
  const STALL_ROUNDS = 4;

  let importRunning = false;
  let stopRequested = false;

  function banner(text, withStop) {
    let el = document.getElementById("studio-import-banner");
    if (!el) {
      el = document.createElement("div");
      el.id = "studio-import-banner";
      el.setAttribute("role", "status");
      el.style.cssText = [
        "position:fixed", "bottom:16px", "left:50%", "transform:translateX(-50%)", "z-index:2147483647",
        "background:#1b1f24", "color:#f4f4f4", "font:13px/1.4 system-ui,sans-serif", "padding:10px 14px",
        "border-radius:8px", "box-shadow:0 6px 24px rgba(0,0,0,.3)", "display:flex", "gap:12px", "align-items:center",
      ].join(";");
      document.body.appendChild(el);
    }
    el.textContent = "";
    const label = document.createElement("span");
    label.textContent = text;
    el.appendChild(label);
    if (withStop) {
      const stop = document.createElement("button");
      stop.textContent = "Stop";
      stop.style.cssText = "background:#ff6b35;color:#111;border:0;border-radius:6px;padding:4px 10px;cursor:pointer;font:inherit";
      stop.addEventListener("click", () => { stopRequested = true; });
      el.appendChild(stop);
    }
    return el;
  }

  function clearBanner(afterMs) {
    setTimeout(() => {
      const el = document.getElementById("studio-import-banner");
      if (el) el.remove();
    }, afterMs || 0);
  }

  const pause = (ms) => new Promise((r) => setTimeout(r, ms));
  const humanPause = () => pause(1600 + Math.random() * 1600);

  async function whileHidden() {
    while (document.visibilityState !== "visible" && !stopRequested) await pause(1000);
  }

  function clickShowMore() {
    const button = Array.from(document.querySelectorAll("button")).find((b) =>
      /^(show more results|see more|load more)/i.test(clean(b.innerText))
    );
    if (button && !button.disabled) {
      button.click();
      return true;
    }
    return false;
  }

  async function runImport(kind, me, request) {
    if (importRunning) return;
    importRunning = true;
    stopRequested = false;
    await studio("/api/v1/self/imports/event", { id: request.id, event: "started" });

    const noun = { posts: "posts", comments: "comments", reactions: "reactions" }[IMPORT_KIND[kind]];
    let total = 0;
    let stalled = 0;
    let outcome = "completed";

    for (let round = 0; round < MAX_ROUNDS; round += 1) {
      if (stopRequested) { outcome = "stopped"; break; }
      if (pageKind() !== kind) { outcome = "left_page"; break; }
      await whileHidden();

      const added = await sendActivity(kind, me);
      total += added;
      banner(`Studio is importing your ${noun}: ${total} so far.`, true);

      stalled = added === 0 ? stalled + 1 : 0;
      if (stalled >= STALL_ROUNDS) break; // the list stopped growing: the end

      if (!clickShowMore()) window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
      await humanPause();
    }

    await studio("/api/v1/self/imports/event", { id: request.id, event: "finished", items_seen: total, outcome });
    banner(outcome === "stopped" ? `Stopped. ${total} ${noun} imported.` : `Done. ${total} ${noun} imported.`, false);
    clearBanner(6000);
    importRunning = false;
  }

  async function onActivityPage(kind) {
    const me = await getConfirmedVanity();
    if (!me || vanityOf(window.location.href) !== me) return; // someone else's activity: not read

    // Whatever is on screen is read either way. Scrolling needs a request.
    await sendActivity(kind, me);

    const pending = await studio("/api/v1/self/imports/pending", { kind: IMPORT_KIND[kind] });
    if (pending && pending.request) runImport(kind, me, pending.request);
  }

  // ---------------------------------------------------------------
  // Heartbeat, so the studio can say the bridge is running
  // ---------------------------------------------------------------

  function heartbeat() {
    if (document.visibilityState !== "visible") return;
    studio("/api/v1/bridge/heartbeat", { extension_version: EXTENSION_VERSION, page_kind: pageKind() });
  }

  function toast(message) {
    banner(message, false);
    clearBanner(7000);
  }

  // ---------------------------------------------------------------
  // Wiring
  // ---------------------------------------------------------------

  let settleTimer = null;
  function onRoute() {
    noteMeRedirect();
    if (settleTimer) clearTimeout(settleTimer);
    // LinkedIn renders sections after the route changes. Waiting lets them
    // arrive, and collapses a burst of route events into one read.
    settleTimer = setTimeout(() => {
      const kind = pageKind();
      if (kind === "profile" || kind === "contact" || kind === "skills") {
        captureProfile();
        // Experience, education and skills render lazily below the top card,
        // so a second read picks up what the first arrived too early for. The
        // studio keeps any section a read did not see.
        if (kind === "profile") setTimeout(() => { if (pageKind() === kind) captureProfile(); }, 6000);
      } else if (IMPORT_KIND[kind]) {
        onActivityPage(kind);
      }
    }, 2500);
  }

  // content.js announces in-app navigation with this event; it watches the URL
  // because a content script cannot see LinkedIn's history calls.
  window.addEventListener("studio:locationchange", () => {
    getConfirmedVanity(true);
    onRoute();
  });
  window.addEventListener("popstate", onRoute);
  onRoute();

  heartbeat();
  setInterval(heartbeat, HEARTBEAT_MS);
  document.addEventListener("visibilitychange", heartbeat);
})();
