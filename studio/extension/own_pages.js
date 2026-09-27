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
    if (/\/recent-activity\/(all|shares)\/?/.test(path)) return "activity_posts";
    if (/\/recent-activity\/comments\/?/.test(path)) return "activity_comments";
    if (/\/recent-activity\/reactions\/?/.test(path)) return "activity_reactions";
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
    const ownerSeen = labels(mainElement()).some((label) => OWNER_CONTROL.test(label));
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
  const DATE_LINE = /\b(19|20)\d{2}\b.*(-|–|present)|\bpresent\b/i;
  const DURATION_ONLY = /^(\d+\s+yrs?)?\s*(\d+\s+mos?)?$/i;

  // The experience section as a stream: each top-level list item is one role,
  // and the text between list items is either a company header or a whole
  // single-role entry. Measured on a live profile, 27 Sep 2026:
  //
  //   Motadata / 9 mos / Ahmedabad            <- company header, outside any li
  //     li: Product Content Strategist / Full-time / Jun 2026 - Aug 2026 ...
  //     li: Trainee Content Strategist / Internship / Dec 2025 - May 2026 ...
  //   HARMONY PowerTech / 2 mos               <- header with no logo at all
  //     li: Electronics Engineering Intern / ...
  //   Special Teacher / Teach For India · Part-time / Aug 2023 - Dec 2023
  //                                           <- one role, company inline, no li
  //
  // Taking the company from the nearest logo above got HARMONY PowerTech wrong,
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

  // The author's display name: the first line of the actor title, without
  // the connection degree LinkedIn appends ("Jaivik Gajjar • 1st"). The
  // aria-hidden span this used to read no longer exists, so every one of 302
  // imported reactions and comments came back with no author.
  function cardActorName(card) {
    const title = card.querySelector(".update-components-actor__title, .update-components-actor__name");
    if (!title) return null;
    const firstLine = (title.innerText || "").split("\n").map((l) => l.trim()).find(Boolean) || "";
    const name = firstLine.replace(/\s*•\s*(1st|2nd|3rd\+?|following|you)\s*$/i, "").replace(/\s*(Verified|Premium)\s*$/i, "").trim();
    return name || null;
  }

  // The post's text with its line breaks kept. It went through clean(), which
  // collapses every run of whitespace, newlines included, so the stored text
  // of every post was one long line and its opening line could not be told
  // from the rest: measured on a live import, 18 of 18 posts. The opening
  // line is what a reader sees before "see more", so it is the one line the
  // studio most needs to have as written.
  function cardText(card) {
    const el = first(card, [".update-components-text", ".feed-shared-inline-show-more-text", ".feed-shared-update-v2__description"]);
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
    return textOf(card, [".update-components-header__text-view", ".update-components-header"]) || "";
  }

  function cardCounts(card) {
    const counts = { reactions: null, comments: null, reposts: null, impressions: null };
    // LinkedIn shows the bare count only when nobody you know reacted. When it
    // names someone ("Kunjan Solanki and 5 others") the number moves to the
    // social-proof element, and reading only the first element left most of
    // a creator's posts with no reaction count at all (measured: four of five).
    counts.reactions = parseCount(textOf(card, [
      ".social-details-social-counts__reactions-count",
      ".social-details-social-counts__social-proof-fallback-number",
    ]));
    if (counts.reactions === null) {
      const named = card.querySelector("button[aria-label$=' others' i], button[aria-label$=' other' i]");
      const match = named ? / and (\d[\d,]*) others?$/i.exec(named.getAttribute("aria-label") || "") : null;
      if (match) counts.reactions = parseCount(match[1]) + 1;
    }
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
    const cards = activityCards();
    const items = readActivity(kind, me);
    // Post cards on the page whose author link could not be read are the
    // markup changing: every post would then be skipped as not the creator's.
    const drift = [];
    if (kind === "activity_posts" && cards.length && items.every((i) => !i.actor)) drift.push("post_author");
    reportCapture(kind, cards.length, items.length, drift);

    const fresh = items.filter((item) => {
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
      if (["profile", "contact", "skills", "details_experience", "details_education"].includes(kind)) {
        captureProfile();
        // Experience, education and skills render lazily below the top card,
        // so a second read picks up what the first arrived too early for. The
        // studio keeps any section a read did not see.
        if (kind === "profile") setTimeout(() => { if (pageKind() === kind) captureProfile(); }, 6000);
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
  document.addEventListener("visibilitychange", heartbeat);
})();
