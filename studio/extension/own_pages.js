// -------------------------------------------------------------
// Inox Hydra Bridge: the creator's own pages
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

  // One extractor run, for the studio's capture log (see content.js
  // reportCapture for why). Throttled per extractor per page.
  const lastReport = {};
  function reportCapture(extractor, itemsSeen, itemsKept, drift) {
    // Keyed on whether this run drifted, so a clean read always gets through
    // after a drifted one. Otherwise an early read that ran before the page
    // finished rendering logged drift, and the good read that followed was
    // throttled away, leaving a working reader marked broken for a minute.
    const key = extractor + "|" + window.location.pathname + "|" + (drift && drift.length ? "drift" : "ok");
    const now = Date.now();
    if (lastReport[key] && now - lastReport[key] < 60000) return;
    lastReport[key] = now;
    studio("/api/v1/bridge/capture", {
      extractor,
      page_kind: pageKind(),
      items_seen: itemsSeen,
      items_kept: itemsKept,
      drift: drift && drift.length ? drift : null,
      extension_version: EXTENSION_VERSION,
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
    if (/^\/analytics\/post-summary\//.test(path)) return "post_analytics";
    if (!/^\/in\/[^/]+/.test(path)) return path.startsWith("/feed") ? "feed" : "other";
    if (/\/(?:detail\/)?recent-activity\/comments\/?/.test(path)) return "activity_comments";
    if (/\/(?:detail\/)?recent-activity\/reactions\/?/.test(path)) return "activity_reactions";
    if (/\/(?:detail\/)?recent-activity(?:\/(?:all|shares|posts))?\/?(?:$|\?)/.test(path)) return "activity_posts";
    if (/\/overlay\/contact-info\/?/.test(path)) return "contact";
    if (/\/details\/skills\/?/.test(path)) return "skills";
    if (/\/details\/experience\/?/.test(path)) return "details_experience";
    if (/\/details\/education\/?/.test(path)) return "details_education";
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

  // The first figure in a line of text, read with the page's own separators,
  // or null when it has no certain reading. "." was always a decimal point
  // here, so a German profile's "8.210 Follower" was stored as 8. The rules
  // are content.js parseMetricValue's: the page language's decimal mark,
  // thousands grouped in threes by the other mark or a space, no fraction
  // without K or M, and English when the page names no language.
  const COMMA_DECIMAL = ["cs", "da", "de", "el", "es", "fi", "fr", "hu", "id", "it", "nl", "no", "nb",
    "pl", "pt", "ro", "ru", "sv", "tr", "uk"];
  const MULTIPLIERS = { k: 1e3, tsd: 1e3, mil: 1e3, m: 1e6, mio: 1e6, mln: 1e6, mn: 1e6, b: 1e9, mrd: 1e9, md: 1e9 };

  function parseCount(text) {
    if (!text) return null;
    const normal = String(text).replace(/[   ]/g, " ");
    const match = /(\d(?:[\d.,']|\s(?=\d{3}(?!\d)))*)(?:\s*(k|tsd|mil|mio|mln|mn|mrd|md|m|b)\.?(?![a-z]))?/i.exec(normal);
    if (!match) return null;
    const lang = (document.documentElement && document.documentElement.lang) || "";
    const decimalMark = COMMA_DECIMAL.includes(lang.toLowerCase().slice(0, 2)) ? "," : ".";
    const groupMark = decimalMark === "," ? "." : ",";
    const figure = match[1].replace(/[.,]$/, "");
    const suffix = (match[2] || "").toLowerCase();

    const parts = figure.split(decimalMark);
    if (parts.length > 2) return null;
    const whole = parts[0];
    const fraction = parts.length === 2 ? parts[1] : "";
    if (parts.length === 2 && !/^\d+$/.test(fraction)) return null;
    if (!/^\d+$/.test(whole)) {
      const grouped = new RegExp("^\\d{1,3}(?:[" + groupMark + " ']\\d{3})+$");
      // Indian lakh and crore grouping, "12,34,567", wherever the comma groups.
      const lakh = groupMark === "," && /^\d{1,2}(?:,\d{2})+,\d{3}$/.test(whole);
      if (!(grouped.test(whole) || lakh) || new Set(whole.replace(/\d/g, "")).size > 1) return null;
    }
    if (fraction && !suffix) return null;
    const value = parseFloat(whole.replace(/\D/g, "") + (fraction ? "." + fraction : ""));
    if (Number.isNaN(value)) return null;
    return Math.round(value * (suffix ? MULTIPLIERS[suffix] : 1));
  }

  // ---------------------------------------------------------------
  // Finding things on a page LinkedIn rebuilds without notice
  // ---------------------------------------------------------------
  //
  // Measured against a live profile, 27 Sep 2026: class names are hashed and
  // change per build, the old section anchors (<div id="experience">) and the
  // duplicated screen-reader spans are gone, and the name is an h2, not an h1.
  // What survived is what a reader sees: each section's visible heading
  // ("About", "Experience"), the page title, and the lines of text in order.
  // So these readers find sections by heading and read lines, and keep the old
  // anchors only as a fallback for accounts still served the previous markup.

  function lines(el) {
    return el ? el.innerText.split("\n").map((l) => l.trim()).filter(Boolean) : [];
  }

  function mainElement() {
    return document.querySelector("main") || document.body;
  }

  // The section whose own heading reads `heading`, or the old anchored one.
  function sectionFor(heading) {
    for (const section of mainElement().querySelectorAll("section")) {
      const h = section.querySelector(":scope h2, :scope h3, :scope > div h2");
      if (h && clean(h.innerText).toLowerCase() === heading.toLowerCase()) return section;
    }
    const anchor = document.getElementById(heading.toLowerCase());
    return anchor ? anchor.closest("section") : null;
  }

  // The top card: the first section inside the page's primary content.
  function topCard() {
    const primary = mainElement().querySelector('section[aria-label="Primary content"]');
    return (primary && primary.querySelector("section")) || mainElement().querySelector("section");
  }

  function topLevelItems(root) {
    return root ? Array.from(root.querySelectorAll("li")).filter((li) => !li.parentElement.closest("li")) : [];
  }

  // The display name, from the page title: "(3) Dharmik Shingala | LinkedIn".
  function nameFromTitle() {
    const name = clean(document.title.split("|")[0].replace(/^\(\d+\)\s*/, ""));
    return name && !/^linkedin$/i.test(name) ? name : null;
  }

  // ---------------------------------------------------------------
  // Is this profile the viewer's own?
  // ---------------------------------------------------------------

  const OWNER_CONTROL = /^(edit profile|edit intro|edit about|add profile section|add section|enhance profile|open to\b|add experience|edit experience)/i;
  const VISITOR_CONTROL = /^(connect|message|follow|pending|invite .* to connect)$/i;

  function selfEvidence() {
    const evidence = [];

    // LinkedIn's own marker. /in/me/ redirects to /in/<you>/?isSelfProfile=true.
    try {
      if (new URLSearchParams(window.location.search).get("isSelfProfile") === "true") {
        evidence.push("self_profile_flag");
      }
    } catch (err) {
      // URLSearchParams is always present; this guards an odd embedding.
    }

    // Owner-only controls anywhere in the profile, vetoed only by visitor
    // controls in the top card. The veto used to look at the whole page, and
    // "People you may know" puts "Invite X to connect" on every profile,
    // including your own, so a real owner page was always rejected.
    const labels = (root) => Array.from(root.querySelectorAll("button, a")).slice(0, 400)
      .map((el) => clean(el.getAttribute("aria-label") || el.innerText || ""));
    // The owner's own edit links ("/in/<you>/edit/intro/", "/add-edit/...")
    // count in every language. The labels above are English only, so a
    // German creator's "Profil bearbeiten" was no evidence at all, and their
    // own profile, opened from a link, taught the bridge nothing.
    // So do the links only an owner's profile carries: its private
    // analytics and dashboard (profile views, search appearances, creator
    // analytics), which no visitor is shown.
    const pageVanity = vanityOf(window.location.href);
    const ownerLink = !!pageVanity && (
      Array.from(mainElement().querySelectorAll("a[href*='/edit/'], a[href*='/add-edit/']"))
        .some((a) => vanityOf(a.getAttribute("href")) === pageVanity) ||
      !!mainElement().querySelector(
        "a[href*='/me/profile-views'], a[href*='/analytics/search-appearances'], a[href*='/analytics/creator'], a[href*='/dashboard/']"
      ));
    const ownerSeen = ownerLink || labels(mainElement()).some((label) => OWNER_CONTROL.test(label));
    const card = topCard();
    const visitorInCard = card ? labels(card).some((label) => VISITOR_CONTROL.test(label)) : false;
    if (ownerSeen && !visitorInCard) evidence.push("owner_edit_controls");

    try {
      const cameFrom = sessionStorage.getItem("studio_me_redirect");
      if (cameFrom && cameFrom === vanityOf(window.location.href)) evidence.push("me_redirect");
    } catch (err) {
      // sessionStorage can be unavailable; the other signals still stand.
    }
    return evidence;
  }

  // /in/me/ is LinkedIn's alias for the viewer's own profile. When the
  // redirect happens in the page rather than on the server, arriving at
  // /in/me/ and then at a real vanity is LinkedIn saying which profile is ours.
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
      // Ignored; this is one of several signals.
    }
  }

  // Which LinkedIn account this browser is signed in to, kept for the
  // analytics readers in content.js: LinkedIn's analytics pages and responses
  // do not name the account, and the studio refuses analytics that do not
  // come from the profile open in it. Learnt only where LinkedIn shows it:
  // a profile shown with its owner's controls, flagged as the viewer's own,
  // or reached through /in/me/. The worker forgets it when the LinkedIn
  // sign-in cookie changes.
  function noteSignedInMember() {
    const vanity = vanityOf(window.location.href);
    if (!vanity || vanity === "me" || pageKind() !== "profile" || !selfEvidence().length) return;
    try {
      chrome.storage.local.set({ signedInVanity: vanity });
    } catch (err) {
      // The extension was reloaded under this page; the next load notes it.
    }
  }

  // An activity page is read only when it is the confirmed creator's. /in/me/
  // is LinkedIn's alias for whoever is signed in to this browser, which is the
  // creator only while nothing says otherwise: an in-page /in/me/ redirect that
  // landed on a different vanity means this browser is signed in as someone
  // else, and their posts would be filed under the creator.
  function isOwnActivityPage(me) {
    if (!me) return false;
    const vanity = vanityOf(window.location.href);
    if (vanity === me) return true;
    if (vanity !== "me") return false;
    try {
      const resolved = sessionStorage.getItem("studio_me_redirect");
      return !resolved || resolved === me;
    } catch (err) {
      return true; // no sessionStorage, so nothing contradicts the alias
    }
  }

  // ---------------------------------------------------------------
  // The profile
  // ---------------------------------------------------------------

  const PRONOUNS = /^(he|she|they|ze|xe)\/\w+/i;

  // The top card reads, in order: name, pronouns, headline, location, a
  // separator, "Contact info", followers, connections, then the controls.
  function readTopCard() {
    const text = lines(topCard());
    const name = nameFromTitle() || text[0] || null;
    let index = name ? text.indexOf(name) : 0;
    if (index < 0) index = 0;
    let cursor = index + 1;
    while (cursor < text.length && (PRONOUNS.test(text[cursor]) || text[cursor] === "·")) cursor += 1;
    const headline = text[cursor] && !/^contact info$/i.test(text[cursor]) ? text[cursor] : null;

    const contactAt = text.findIndex((line) => /^contact info$/i.test(line));
    let location = null;
    for (let i = contactAt - 1; i > cursor && contactAt > 0; i -= 1) {
      if (text[i] !== "·") {
        location = text[i];
        break;
      }
    }

    const followersLine = text.find((line) => /\bfollowers?$/i.test(line));
    const connectionsLine = text.find((line) => /\bconnections?$/i.test(line));
    return {
      display_name: name,
      headline,
      location,
      follower_count: followersLine ? parseCount(followersLine) : null,
      connection_count: connectionsLine ? parseCount(connectionsLine) : null,
    };
  }

  const MORE_LINE = /^(…|\.\.\.)?\s*(see )?more$|^show (all|more)/i;

  function readAbout() {
    const section = sectionFor("About");
    if (!section) return null;
    const text = lines(section).filter((line) => !/^about$/i.test(line) && !MORE_LINE.test(line));
    return text.length ? text.join("\n") : null;
  }

  const EMPLOYMENT = /^(full-time|part-time|internship|contract|freelance|self-employed|apprenticeship|seasonal|temporary)$/i;
  const DATE_LINE = /\b(19|20)\d{2}\b.*(-|\u2013|present)|\bpresent\b/i;
  const DURATION_ONLY = /^(\d+\s+yrs?)?\s*(\d+\s+mos?)?$/i;

  // The experience section as a stream: each top-level list item is one role,
  // and the text between list items is either a company header or a whole
  // single-role entry. Measured on a live profile, 27 Sep 2026:
  //
  //   Acme Inc / 9 mos / Riverside            <- company header, outside any li
  //     li: Associate Product Designer / Full-time / Jun 2024 - Aug 2024 ...
  //     li: Junior Product Designer / Internship / Dec 2023 - May 2024 ...
  //   Globex Industries / 2 mos               <- header with no logo at all
  //     li: Hardware Engineering Intern / ...
  //   Volunteer Tutor / Initech Academy · Part-time / Aug 2021 - Dec 2021
  //                                           <- one role, company inline, no li
  //
  // Taking the company from the nearest logo above got Globex Industries wrong,
  // because a company with no LinkedIn page has no logo, and missed the
  // single-role entries entirely because they are not list items.
  function experienceStream(section) {
    const stream = [];
    let run = null;
    const walker = document.createTreeWalker(section, NodeFilter.SHOW_TEXT);
    let node;
    const seenItems = new Set();
    while ((node = walker.nextNode())) {
      const text = clean(node.textContent);
      if (!text) continue;
      const parent = node.parentElement;
      let item = parent ? parent.closest("li") : null;
      while (item && item.parentElement && item.parentElement.closest("li") && section.contains(item.parentElement.closest("li"))) {
        item = item.parentElement.closest("li");
      }
      if (item && section.contains(item)) {
        if (!seenItems.has(item)) {
          seenItems.add(item);
          stream.push({ kind: "item", element: item });
        }
        run = null;
        continue;
      }
      if (!run) {
        run = { kind: "text", lines: [] };
        stream.push(run);
      }
      run.lines.push(text);
    }
    return stream;
  }

  function roleFrom(text, company) {
    const dateAt = text.findIndex((line) => DATE_LINE.test(line));
    const after = dateAt >= 0 ? text.slice(dateAt + 1) : text.slice(1);
    const location = after[0] && after[0].length < 80 && !/[.!?:]$/.test(after[0]) && !/skills?$/i.test(after[0])
      ? after[0] : null;
    const description = after.slice(location ? 1 : 0)
      .filter((line) => !MORE_LINE.test(line) && !/^skills:?$/i.test(line) && !/\bskills?$/i.test(line)
        && !/\.(png|jpe?g|pdf)$/i.test(line) && !/certificate$/i.test(line))
      .join("\n");
    return {
      title: text[0],
      company,
      date_range: dateAt >= 0 ? text[dateAt] : null,
      location,
      description: description || null,
    };
  }

  function readPositions(root) {
    const section = root || sectionFor("Experience");
    if (!section) return null;
    const positions = [];
    let company = null;

    for (const entry of experienceStream(section)) {
      if (positions.length >= 40) break;
      if (entry.kind === "item") {
        const text = lines(entry.element).filter((line) => !MORE_LINE.test(line));
        if (text.length && DATE_LINE.test(text.join("\n"))) positions.push(roleFrom(text, company));
        continue;
      }

      const text = entry.lines.filter((line) => !MORE_LINE.test(line) && !/^experience$/i.test(line));
      // A company header: the company's name followed by its total duration.
      const durationAt = text.findIndex((line, i) => i > 0 && DURATION_ONLY.test(line) && /\d/.test(line));
      const dateAt = text.findIndex((line) => DATE_LINE.test(line));
      if (durationAt > 0 && (dateAt < 0 || durationAt < dateAt)) {
        company = text[durationAt - 1];
        continue;
      }
      // A single-role entry: title, then "Company · Employment type", then dates.
      if (dateAt >= 1) {
        const title = dateAt >= 2 ? text[dateAt - 2] : text[0];
        const companyLine = dateAt >= 2 ? text[dateAt - 1] : null;
        const parts = companyLine ? companyLine.split(" · ") : [];
        const single = parts.length && !EMPLOYMENT.test(parts[0]) ? parts[0] : null;
        positions.push(roleFrom([title, ...text.slice(dateAt)], single));
        company = null;
      }
    }
    return positions.length ? positions : null;
  }

  function readEducation(root) {
    const section = root || sectionFor("Education");
    if (!section) return null;
    const entries = topLevelItems(section).map((li) => lines(li)).filter((text) => text.length);
    if (!entries.length) return null;
    return entries.slice(0, 20).map((text) => ({
      school: text[0] || null,
      degree: text[1] && !DATE_LINE.test(text[1]) ? text[1] : null,
      date_range: text.find((line) => /\b(19|20)\d{2}\b/.test(line)) || null,
    }));
  }

  function readSkills(root) {
    const section = root || sectionFor("Skills");
    if (!section) return null;
    const skills = topLevelItems(section)
      .map((li) => lines(li)[0])
      .filter((skill) => skill && skill.length < 120 && !MORE_LINE.test(skill) && !/^endorse/i.test(skill));
    return skills.length ? Array.from(new Set(skills)) : null;
  }

  // The contact panel is the dialog whose text begins "Contact info". A profile
  // page carries several other dialogs (a video player's "This is a modal
  // window", caption settings, ad options), and taking the first one read the
  // video player and stored an empty contact card as though it had been read.
  function readContact() {
    const dialog = Array.from(document.querySelectorAll('dialog, [role="dialog"], .pv-contact-info'))
      .find((d) => /^contact info/i.test(clean(d.innerText)));
    if (!dialog) return null;
    const contact = { email: null, phone: null, birthday: null, websites: [] };
    const mail = dialog.querySelector('a[href^="mailto:"]');
    if (mail) contact.email = mail.getAttribute("href").slice(7);
    const text = lines(dialog);
    const after = (label) => {
      const at = text.findIndex((line) => new RegExp("^" + label, "i").test(line));
      return at >= 0 && text[at + 1] ? text[at + 1] : null;
    };
    if (!contact.email) contact.email = after("email");
    contact.phone = after("phone");
    contact.birthday = after("birthday");
    dialog.querySelectorAll("a[href]").forEach((a) => {
      const href = a.getAttribute("href");
      if (href && /^https?:/i.test(href) && !/linkedin\.com\//i.test(href)) contact.websites.push(href);
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
      // Education and skills load only as the profile is scrolled, so they are
      // read from their own details pages; these catch them if already shown.
      const education = readEducation();
      if (education) payload.education = education;
      const skills = readSkills();
      if (skills) payload.skills = skills;
    } else if (kind === "details_experience") {
      const positions = readPositions(mainElement());
      if (positions) {
        payload.positions = positions;
        if (positions[0] && positions[0].company) payload.current_company = positions[0].company;
      }
    } else if (kind === "details_education") {
      const education = readEducation(mainElement());
      if (education) payload.education = education;
    } else if (kind === "skills") {
      const skills = readSkills(mainElement());
      if (skills) payload.skills = skills;
    } else if (kind === "contact") {
      payload.contact = readContact();
    }

    if (kind === "profile") {
      // A profile page always has a name. Not finding one on the creator's own
      // profile means the reader no longer matches the page.
      const read = ["display_name", "headline", "location", "about"].filter((k) => payload[k]);
      reportCapture("profile", read.length + (payload.positions ? payload.positions.length : 0),
        read.length, payload.display_name ? [] : ["name"]);
    }

    const result = await studio("/api/v1/identity/observe", payload);
    if (result && result.status === "candidate") {
      toast("The studio found your profile. Confirm it's you in the studio's Setup screen.");
    }
  }

  // ---------------------------------------------------------------
  // Activity: posts, comments, reactions
  // ---------------------------------------------------------------

  // The post's id as LinkedIn names it. A share or ugcPost id is a different
  // number from the post's activity id (card_urns.js says the same), and it
  // was relabelled urn:li:activity:<same digits>, an id LinkedIn never issued,
  // which the post's analytics page, the network readings and the studio's
  // binding then looked for in vain. An activity id wins when a text has both.
  function extractActivityUrn(text) {
    if (!text) return null;
    const activity = /urn:li:activity:(\d+)/.exec(text);
    if (activity) return `urn:li:activity:${activity[1]}`;
    const other = /urn:li:(share|ugcPost):(\d+)/.exec(text);
    if (other) return `urn:li:${other[1]}:${other[2]}`;
    const slug = /-activity-(\d{6,})/.exec(text);
    if (slug) return `urn:li:activity:${slug[1]}`;
    const bareUrn = /urn:li:activity:\d+/.exec(text);
    if (bareUrn) return bareUrn[0];
    const digits = /^\d{10,25}$/.exec(text.trim());
    if (digits) return `urn:li:activity:${digits[0]}`;
    return null;
  }

  // A card's activity id wherever it carries one, before a share or ugcPost
  // id it may carry elsewhere: a document card can name its ugcPost on the
  // card and its activity id only in a link.
  function cardUrn(card) {
    if (!card) return null;
    let other = null;
    const take = (value) => {
      const urn = extractActivityUrn(value);
      if (urn && urn.startsWith("urn:li:activity:")) return urn;
      if (urn && !other) other = urn;
      return null;
    };
    for (const attr of ["data-urn", "data-id", "data-activity-urn", "data-chameleon-urn"]) {
      const urn = take(card.getAttribute && card.getAttribute(attr));
      if (urn) return urn;
    }
    const inners = card.querySelectorAll("[data-urn], [data-id], [data-activity-urn], [data-chameleon-urn]");
    for (const inner of inners) {
      for (const attr of ["data-urn", "data-id", "data-activity-urn", "data-chameleon-urn"]) {
        const urn = take(inner.getAttribute(attr));
        if (urn) return urn;
      }
    }
    const links = card.querySelectorAll("a[href*='/feed/update/urn:li:'], a[href*='-activity-'], a[href*='urn:li:activity:'], a[href*='urn:li:share:'], a[href*='urn:li:ugcPost:']");
    for (const link of links) {
      const urn = take(link.getAttribute("href"));
      if (urn) return urn;
    }
    const els = [card, ...Array.from(card.querySelectorAll("*"))];
    for (let i = 0; i < els.length; i++) {
      const el = els[i];
      for (const k in el) {
        if (k.startsWith("__reactProps")) {
          try {
            const urn = take(JSON.stringify(el[k]));
            if (urn) return urn;
          } catch (e) {}
        }
      }
    }
    return other;
  }

  const CARD_CONTAINERS = [
    'div[id^="expanded"][id*="FeedType_"]',
    "li.profile-creator-shared-feed-update__container",
    ".profile-creator-shared-feed-update__container",
    '[data-view-name="feed-full-update"]',
    ".feed-shared-update-v2",
    ".occludable-update",
    '[data-urn*="activity:"]',
    '[data-urn*="ugcPost"]',
    '[data-urn*="share"]',
    '[data-id*="activity:"]',
    '[data-id*="ugcPost"]',
    '[data-id*="share"]',
    "div[data-activity-urn]",
    "div[data-chameleon-urn]",
    '[data-test-id="main-feed-activity-card"]',
    ".main-feed-activity-card",
  ];

  function activityCards() {
    const selector = CARD_CONTAINERS.join(", ");
    let list = Array.from(document.querySelectorAll(selector));

    if (!list.length) {
      const links = Array.from(document.querySelectorAll(
        "a[href*='/feed/update/urn:li:'], a[href*='-activity-'], a[href*='urn:li:activity:']"
      ));
      const seenContainers = new Set();
      for (const link of links) {
        const c = link.closest("article, li, [data-view-name], div[class*='update'], div[class*='feed'], div[class*='activity'], div[class*='card']") || link.parentElement;
        if (c && !seenContainers.has(c)) {
          seenContainers.add(c);
          list.push(c);
        }
      }
    }

    const topCards = list.filter((card) => {
      let parent = card.parentElement;
      while (parent && parent !== document.body) {
        if (parent.matches && parent.matches(selector)) return false;
        parent = parent.parentElement;
      }
      return true;
    });

    const seenUrns = new Set();
    const result = [];
    for (const card of topCards) {
      const urn = cardUrn(card);
      if (urn && !seenUrns.has(urn)) {
        seenUrns.add(urn);
        result.push(card);
      }
    }
    return result;
  }

  function cardActor(card) {
    const link = card.querySelector(
      ".update-components-actor__meta-link, a.update-components-actor__image, .update-components-actor a[href*='/in/'], .feed-shared-actor a[href*='/in/'], a[data-field='actor_name'], a.app-aware-link[href*='/in/']"
    );
    return link ? vanityOf(link.getAttribute("href")) : "";
  }

  // The author's display name: the first line of the actor title, without
  // the connection degree LinkedIn appends ("Ada Lovelace • 1st"). The
  // aria-hidden span this used to read no longer exists, so every one of 302
  // imported reactions and comments came back with no author.
  function cardActorName(card) {
    const title = card.querySelector(
      ".update-components-actor__title, .update-components-actor__name, .feed-shared-actor__title, .feed-shared-actor__name, a[data-field='actor_name'], [data-anonymize='person-name'], .update-components-actor__meta a, .feed-shared-actor a"
    );
    if (title) {
      const firstLine = (title.innerText || "").split("\n").map((l) => l.trim()).find(Boolean) || "";
      const name = firstLine.replace(/\s*•\s*(1st|2nd|3rd\+?|following|you)\s*$/i, "").replace(/\s*(Verified|Premium)\s*$/i, "").trim();
      if (name) return name;
    }
    const lineList = lines(card);
    const actionIdx = lineList.findIndex((l) => /(commented|likes\b|liked\b|supports\b|supported\b|celebrates\b|celebrated\b|loves\b|loved\b|finds\b|job update)/i.test(l));
    if (actionIdx !== -1 && actionIdx + 1 < lineList.length) {
      const candidate = lineList[actionIdx + 1];
      if (candidate && candidate.length < 60 && !candidate.startsWith("http")) {
        return candidate.replace(/\s*•.*$/, "").trim();
      }
    }
    return null;
  }

  // The post's text with its line breaks kept. It went through clean(), which
  // collapses every run of whitespace, newlines included, so the stored text
  // of every post was one long line and its opening line could not be told
  // from the rest: measured on a live import, 18 of 18 posts. The opening
  // line is what a reader sees before "see more", so it is the one line the
  // studio most needs to have as written.
  function cardTextElement(card) {
    return first(card, [
      ".update-components-text",
      ".feed-shared-inline-show-more-text",
      ".feed-shared-update-v2__description",
      '[data-view-name="feed-full-update-description"]',
      ".feed-shared-text",
      ".feed-shared-text-view",
      '[data-test-id="main-feed-activity-card__commentary"]',
      ".attributed-text-segment-list__container",
      '[data-testid="expandable-text-box"]',
      '[data-test-id="expandable-text-box"]',
    ]);
  }

  function cardText(card) {
    const el = cardTextElement(card);
    if (!el) return null;
    const text = (el.innerText || "")
      .split("\n")
      .map((line) => line.replace(/[ \t]+/g, " ").trim())
      .join("\n")
      .replace(/\n{3,}/g, "\n\n")
      .replace(/\n?…\s*more$/i, "")
      .trim();
    return text || null;
  }

  function cardHeader(card) {
    const direct = textOf(card, [
      ".update-components-header__text-view",
      ".update-components-header",
      ".feed-shared-header",
      ".feed-shared-update-v2__header",
      '[data-view-name="feed-full-update-header"]',
    ]);
    if (direct) return direct;
    const lineList = lines(card);
    // "reposted" too: on the rebuilt cards "Ada Lovelace reposted this" is a
    // plain line, and without it a repost was read as the creator's own post.
    const actionLine = lineList.find((l) => /(commented|reposted\b|likes\b|liked\b|supports\b|supported\b|celebrates\b|celebrated\b|loves\b|loved\b|finds\b)/i.test(l));
    return actionLine || "";
  }

  // The author's profile link on a card whose actor classes are gone (the
  // rebuilt layout): the first /in/ link above the post's text, other than
  // one in a "reposted this" line, which names the reposter.
  function cardHeaderAuthor(card) {
    const textEl = cardTextElement(card);
    for (const link of card.querySelectorAll("a[href*='/in/']")) {
      if (textEl && (textEl.contains(link) ||
          !(link.compareDocumentPosition(textEl) & Node.DOCUMENT_POSITION_FOLLOWING))) break;
      if (/\breposted\b/i.test(clean((link.parentElement || link).innerText || ""))) continue;
      const vanity = vanityOf(link.getAttribute("href"));
      if (vanity) return vanity;
    }
    return "";
  }

  function cardCounts(card) {
    const counts = { reactions: null, comments: null, reposts: null, impressions: null };
    // LinkedIn shows the bare count only when nobody you know reacted. When it
    // names someone ("Grace Hopper and 5 others") the number moves to the
    // social-proof element, and reading only the first element left most of
    // a creator's posts with no reaction count at all (measured: four of five).
    counts.reactions = parseCount(textOf(card, [
      ".social-details-social-counts__reactions-count",
      ".social-details-social-counts__social-proof-fallback-number",
      ".social-details-social-counts__count",
      "[data-test-id='social-actions__reactions-count']",
      "[data-testid='social-actions__reactions-count']",
      "button[aria-label*='reaction']",
    ]));
    if (counts.reactions === null) {
      const named = card.querySelector("button[aria-label$=' others' i], button[aria-label$=' other' i]");
      const match = named ? / and (\d[\d,]*) others?$/i.exec(named.getAttribute("aria-label") || "") : null;
      if (match) counts.reactions = parseCount(match[1]) + 1;
    }
    // The post's own words are not its figures. A short post such as "We just
    // crossed 10,000 impressions!" sits before the real counts, and the first
    // element naming impressions was taken, so 10,000 was stored as measured.
    // So the post's text is skipped, and a count is a figure directly followed
    // by its word ("9 comments"), never a figure somewhere in a sentence.
    const textEl = cardTextElement(card);
    const counted = (text, word) => new RegExp("^\\d[\\d.,'\\s]*[km]?\\s*(?:" + word + ")\\b", "i").test(text);
    card.querySelectorAll("button, span, a").forEach((el) => {
      if (textEl && textEl.contains(el)) return;
      const text = clean(el.getAttribute("aria-label") || el.innerText || "");
      if (text.length > 60) return;
      if (counts.reactions === null && counted(text, "reactions?|likes?")) counts.reactions = parseCount(text);
      if (counts.comments === null && counted(text, "comments?")) counts.comments = parseCount(text);
      if (counts.reposts === null && counted(text, "reposts?")) counts.reposts = parseCount(text);
      if (counts.impressions === null && counted(text, "impressions?")) counts.impressions = parseCount(text);
    });
    return counts;
  }

  const REACTION_WORDS = [
    ["celebrates", "celebrate"], ["celebrated", "celebrate"],
    ["supports", "support"], ["supported", "support"],
    ["loves", "love"], ["loved", "love"],
    ["finds this insightful", "insightful"], ["insightful", "insightful"],
    ["finds this funny", "funny"], ["funny", "funny"],
    ["likes", "like"], ["liked", "like"],
  ];

  const TIME_BADGE = /^(?:\(edited\)\s*)?\d+\s*(?:s|m|h|d|w|mo|yr|y)$/i;

  // A comment's text without the replies nested inside it.
  function ownText(commentEl, replies) {
    return (replies || []).reduce((text, reply) => text.replace(reply.innerText || "", ""), commentEl.innerText || "");
  }

  function extractCommentText(commentEl, replies) {
    const outside = (el) => !(replies || []).some((reply) => reply.contains(el));
    let direct = null;
    for (const selector of [
      ".comments-comment-item__main-content",
      ".update-components-text",
      ".comments-comment-item-content-body",
      ".comments-comment-item__text",
      ".feed-shared-inline-show-more-text",
      ".comments-comment-item__highlighted-text",
      ".comments-highlighted-comment",
      ".comment-body",
    ]) {
      const found = Array.from(commentEl.querySelectorAll(selector))
        .find((el) => outside(el) && clean(el.innerText || el.textContent));
      if (found) {
        direct = clean(found.innerText || found.textContent);
        break;
      }
    }
    if (direct) return direct;

    const paragraphs = Array.from(commentEl.querySelectorAll("p")).filter(outside);
    let seenTime = false;
    const bodyPs = [];
    for (const p of paragraphs) {
      const text = clean(p.innerText || p.textContent);
      if (!text) continue;
      if (!seenTime) {
        if (TIME_BADGE.test(text)) seenTime = true;
        continue;
      }
      if (/^[\d\s]+$/.test(text) || /\bimpressions?\b/i.test(text) || /\breactions?\b/i.test(text) || text === "Like" || text === "Reply") break;
      bodyPs.push(text);
    }
    if (bodyPs.length) return bodyPs.join("\n").replace(/\n?…\s*more$/i, "").trim();

    const lineList = ownText(commentEl, replies).split("\n").map((l) => l.trim()).filter(Boolean);
    let started = false;
    const bodyLines = [];
    for (const l of lineList) {
      if (!started) {
        if (TIME_BADGE.test(l)) started = true;
        continue;
      }
      if (/^[\d\s]+$/.test(l) || /\bimpressions?\b/i.test(l) || /\breactions?\b/i.test(l) || l === "Author" || l === "Like" || l === "Reply") break;
      bodyLines.push(l);
    }
    return bodyLines.join("\n").replace(/\n?…\s*more$/i, "").trim() || null;
  }

  function readActivity(kind, me) {
    const items = [];
    items.unreadActors = 0;
    for (const card of activityCards()) {
      const urn = cardUrn(card);
      if (!urn) continue;
      let actor = cardActor(card) || (kind === "activity_posts" ? cardHeaderAuthor(card) : "");
      const isRepostCard = cardHeader(card).toLowerCase().includes("repost");

      if (kind === "activity_posts") {
        // A repost is somebody else's writing, whoever its header names. An
        // author read from the card who is not the creator is not the creator.
        // Only a card with no author to read at all, and no repost header, on
        // the creator's own activity page is taken to be theirs; that is
        // counted, so a page where no author can be read reports drift.
        if (!actor) items.unreadActors += 1;
        if (isRepostCard) {
          actor = actor && actor !== me && actor !== "me" ? actor : "repost";
        } else if (!actor || actor === "me" || actor === me) {
          actor = me;
        }
        items.push({ activity_urn: urn, actor, text: cardText(card), ...cardCounts(card) });
      } else if (kind === "activity_comments") {
        const commentEls = Array.from(card.querySelectorAll(
          "article, .comments-comment-item, [data-view-name='feed-full-update-comment'], .feed-shared-main-content--comment, div[data-id^='urn:li:comment:'], .comments-comments-list__comment-item, div[id^='replaceableComment_urn:li:comment:']"
        ));
        // A reply nests inside the comment it answers, so whose comment this
        // is, and what it says, are read from its own part only. "• You" was
        // looked for anywhere inside, the creator's nested reply included, so
        // the stranger's comment they answered was saved as their own words.
        const repliesIn = (c) => commentEls.filter((other) => other !== c && c.contains(other) &&
          other.querySelector("a[href*='/in/']"));
        let mine = commentEls.filter((c) => {
          const replies = repliesIn(c);
          const outside = (el) => !replies.some((r) => r.contains(el));
          const firstLink = Array.from(c.querySelectorAll("a[href*='/in/']")).find(outside);
          const v = firstLink ? vanityOf(firstLink.getAttribute("href")) : "";
          if (v === me || v === "me") return true;
          const t = ownText(c, replies);
          if (t.includes("• You")) return true;
          return false;
        });
        for (const comment of mine) {
          const text = extractCommentText(comment, repliesIn(comment));
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
          target_activity_urn: urn, kind: "reaction", reaction_kind: match ? match[1] : "like",
          target_author: cardActorName(card), target_excerpt: (cardText(card) || "").slice(0, 300),
        });
      }
    }
    return items;
  }

  const sentKeys = new Set();

  async function sendActivity(kind, me) {
    const cards = activityCards();
    const items = readActivity(kind, me);
    // Post cards on the page none of whose authors could be read are the
    // markup changing. They are taken to be the creator's (see readActivity),
    // so this is the only place the change shows. It was tested after the
    // unread author had already been replaced by the creator, so never fired.
    const drift = [];
    if (kind === "activity_posts" && items.length && items.unreadActors === items.length) drift.push("post_author");
    reportCapture(kind, cards.length, items.length, drift);

    const fresh = items.filter((item) => {
      const key = JSON.stringify([
        item.activity_urn || item.target_activity_urn,
        item.kind,
        item.my_text,
        item.text ? item.text.length : 0,
        item.reactions
      ]);
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
  // One post's analytics page: /analytics/post-summary/<urn>/
  // ---------------------------------------------------------------
  //
  // Shown only to the post's author, and fuller than the feed: members
  // reached, saves and sends appear nowhere else. Read by label rather than
  // by class name: each figure sits near the words LinkedIn prints for it, and
  // those words change far less often than the markup around them.

  const POST_METRIC_LABELS = [
    ["members reached", "members_reached"],
    ["impressions", "impressions"],
    ["reactions", "reactions"],
    ["comments", "comments"],
    ["reposts", "reposts"],
    ["saves", "saves"],
    ["sends", "sends"],
  ];
  const NUMBER_ONLY = /^[\d.,]+\s*[KkMm]?$/;

  function postAnalyticsUrn() {
    let path = window.location.pathname;
    try {
      path = decodeURIComponent(path);
    } catch (err) {
      // Leave it encoded; the pattern below still fails cleanly.
    }
    const match = /urn:li:activity:(\d+)/.exec(path);
    return match ? `urn:li:activity:${match[1]}` : null;
  }

  function readPostAnalytics() {
    const main = document.querySelector("main") || document.body;
    const leaves = Array.from(main.querySelectorAll("*")).filter(
      (el) => el.children.length === 0 && clean(el.textContent).length > 0 && clean(el.textContent).length < 40
    );
    const metrics = {};
    for (const el of leaves) {
      const text = clean(el.textContent).toLowerCase();
      const hit = POST_METRIC_LABELS.find(([label, key]) => metrics[key] === undefined && text.startsWith(label));
      if (!hit) continue;
      // The figure is a sibling leaf within a few levels of the label.
      let box = el.parentElement;
      for (let depth = 0; depth < 3 && box && metrics[hit[1]] === undefined; depth += 1, box = box.parentElement) {
        const figure = Array.from(box.querySelectorAll("*")).find(
          (node) => node !== el && node.children.length === 0 && NUMBER_ONLY.test(clean(node.textContent))
        );
        if (figure) metrics[hit[1]] = parseCount(clean(figure.textContent));
      }
    }
    return metrics;
  }

  async function capturePostAnalytics() {
    const urn = postAnalyticsUrn();
    const me = await getConfirmedVanity();
    if (!urn || !me) return;
    const metrics = readPostAnalytics();
    const found = Object.keys(metrics).length;
    reportCapture("post_analytics", found, found, found ? [] : ["metric_labels"]);
    if (!found) return;
    await studio("/api/v1/self/posts/analytics", { author: me, activity_urn: urn, metrics });
  }

  // ---------------------------------------------------------------
  // The scroll, which happens only because the creator asked
  // ---------------------------------------------------------------

  const IMPORT_KIND = { activity_posts: "posts", activity_comments: "comments", activity_reactions: "reactions" };
  const MAX_ROUNDS = 250;
  const STALL_ROUNDS = 8;

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
      /^(show more results|see more|load more|show more)/i.test(clean(b.innerText || b.getAttribute("aria-label") || "")) ||
      (b.classList && b.classList.contains("scaffold-finite-scroll__load-button"))
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
    sentKeys.clear();
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

      if (!clickShowMore()) {
        const cards = activityCards();
        if (cards.length > 0) {
          try { cards[cards.length - 1].scrollIntoView({ behavior: "smooth", block: "end" }); } catch (err) {}
        }
        window.scrollTo({ top: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight), behavior: "smooth" });
      }
      await humanPause();
    }

    const finishRes = await studio("/api/v1/self/imports/event", { id: request.id, event: "finished", items_seen: total, outcome });
    importRunning = false;

    if (outcome === "stopped") {
      banner(`Stopped. ${total} ${noun} imported.`, false);
      clearBanner(6000);
      return;
    }

    if (finishRes && finishRes.next_url) {
      banner(`Done importing ${noun} (${total} imported). Advancing to ${finishRes.next_kind}...`, false);
      await pause(1800);
      window.location.href = finishRes.next_url;
      return;
    }

    if (finishRes && finishRes.all_completed) {
      banner("All activity streams synced successfully!", false);
      clearBanner(8000);
      return;
    }

    banner(outcome === "stopped" ? `Stopped. ${total} ${noun} imported.` : `Done. ${total} ${noun} imported.`, false);
    clearBanner(6000);
  }

  async function onActivityPage(kind) {
    const me = await getConfirmedVanity();
    if (!isOwnActivityPage(me)) return; // someone else's activity: not read

    // Whatever is on screen is read either way. Scrolling needs a request.
    await sendActivity(kind, me);

    const pending = await studio("/api/v1/self/imports/pending", { kind: IMPORT_KIND[kind] });
    if (pending && pending.request) runImport(kind, me, pending.request);
  }

  // ---------------------------------------------------------------
  // Heartbeat, so the studio can say the bridge is running
  // ---------------------------------------------------------------

  // From a hidden tab too. The launcher opens LinkedIn with the studio in a
  // second tab, so while the creator reads Setup the LinkedIn tab is hidden,
  // and a heartbeat sent only from a visible tab made Setup say the bridge was
  // gone while its tab sat open.
  function heartbeat() {
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
      if (["profile", "contact", "skills", "details_experience", "details_education"].includes(kind)) {
        captureProfile();
        noteSignedInMember();
        // Experience, education and skills render lazily below the top card,
        // so a second read picks up what the first arrived too early for. The
        // studio keeps any section a read did not see.
        if (kind === "profile") {
          setTimeout(() => { if (pageKind() === kind) { captureProfile(); noteSignedInMember(); } }, 6000);
        }
      } else if (IMPORT_KIND[kind]) {
        onActivityPage(kind);
      } else if (kind === "post_analytics") {
        capturePostAnalytics();
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
  document.addEventListener("visibilitychange", () => {
    heartbeat();
    if (document.visibilityState === "visible") onRoute();
  });

  let scrollDebounce = null;
  window.addEventListener("scroll", () => {
    const kind = pageKind();
    if (!IMPORT_KIND[kind]) return;
    if (scrollDebounce) clearTimeout(scrollDebounce);
    scrollDebounce = setTimeout(async () => {
      const me = await getConfirmedVanity();
      if (!isOwnActivityPage(me)) return;
      await sendActivity(kind, me);
    }, 1200);
  }, { passive: true });
})();
