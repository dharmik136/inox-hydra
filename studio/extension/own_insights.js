/*
 * The creator's own surfaces nothing read before (cycle 4, track 5, phase 2).
 *
 * The creator opens these pages and the bridge walked past them: the
 * analytics dashboard's profile views, search appearances and new followers
 * graph; "Who viewed your profile" and the search appearances page; an
 * article's and a newsletter's own analytics pages. And on their own
 * Activity tab, their reposts and the "edited" mark on their posts, which
 * own_pages.js's activity reader asks this file about (ownCardFacts).
 *
 * Every page's markup and labels are unverified against 2026 pages, so:
 * a figure is sent only when its label and its number can be read; a count
 * over a window only with the window its own card, label or page names; a
 * page read as nothing sends nothing. Counts and windows only: no viewer's or
 * searcher's name, headline, company or profile link is ever read, and no
 * list of them is looked at. An absent label is not read, never drift (the
 * owner's decision of 2026-10-26), so this file reports no capture runs; the
 * studio derives how long each figure has gone unread from what it was sent.
 *
 * It reuses content.js's globals, loaded before it in the same world:
 * parseMetricValue (a figure and its precision, in the page's language),
 * analyticsPeriodOf (the window a phrase names), detectAnalyticsPeriod (the
 * page's range control), studioApi, and signedInVanity (whose figures).
 */
(function ownInsights() {
  "use strict";

  const FIGURES_PATH = "/api/analytics/page-figures";
  const clean = (text) => (text || "").replace(/\s+/g, " ").trim();

  // The pages this file reads, by path, and the labels on each: the Help's
  // wording, unverified. A label may be spelt two ways; the first wins.
  function insightPage() {
    const path = window.location.pathname;
    if (/^\/(?:me|analytics)\/profile-views\/?/.test(path)) return "profile_views";
    if (/^\/(?:me|analytics)\/search-appearances\/?/.test(path)) return "search_appearances";
    if (/^\/analytics\/(?:creator\/)?article\//.test(path)) return "article_analytics";
    if (/^\/analytics\/(?:creator\/)?newsletter\//.test(path)) return "newsletter_analytics";
    if (/^\/analytics\/creator\//.test(path) || /^\/dashboard\/?$/.test(path)) return "account_analytics";
    return null;
  }

  const LABELS = {
    account_analytics: [["profile viewers", "profile_views"], ["profile views", "profile_views"],
      ["search appearances", "search_appearances"]],
    profile_views: [["profile viewers", "profile_views"], ["profile views", "profile_views"]],
    search_appearances: [["search appearances", "search_appearances"]],
    article_analytics: [["article views", "views"], ["views", "views"], ["impressions", "impressions"],
      ["members reached", "members_reached"], ["reactions", "reactions"], ["comments", "comments"],
      ["reposts", "reposts"]],
    newsletter_analytics: [["subscribers", "subscribers"], ["article views", "views"],
      ["impressions", "impressions"], ["email sends", "email_sends"], ["emails sent", "email_sends"],
      ["email open rate", "email_open_rate_pct"], ["open rate", "email_open_rate_pct"]],
  };
  const SHARES = new Set(["email_open_rate_pct"]);
  const CONTENT_PAGES = new Set(["article_analytics", "newsletter_analytics"]);
  const PERCENT_ONLY = /^(\d{1,3}(?:[.,]\d+)?)\s*%$/;

  function windowOf(text) {
    const said = clean(text);
    if (!said) return null;
    const period = typeof analyticsPeriodOf === "function" ? analyticsPeriodOf(said) : null;
    if (period) return period;
    // LinkedIn names search appearances by the week.
    return /\b(?:past|last|previous) week\b/i.test(said) ? "7d" : null;
  }

  function figureOf(text, share) {
    const said = clean(text);
    if (share) {
      const match = PERCENT_ONLY.exec(said);
      if (!match) return null;
      const value = parseFloat(match[1].replace(",", "."));
      return Number.isNaN(value) || value > 100 ? null : { value, precision: "exact" };
    }
    return typeof parseMetricValue === "function" ? parseMetricValue(said) : null;
  }

  function leavesOf(root) {
    return Array.from(root.querySelectorAll("*")).filter(
      (el) => el.children.length === 0 && clean(el.textContent).length > 0 && clean(el.textContent).length < 80);
  }

  // The card a label sits in: its list item, as LinkedIn's summary cards
  // are ("li" around "15 Search appearances 0% past 7 days"), else the box
  // its figure was found in.
  function cardOf(el, box) {
    const item = el.closest("li");
    return item && item.contains(box) ? item : box;
  }

  // The words of a card after its label, the label's own words excluded.
  function wordsAfter(el, card) {
    if (!card || !card.contains(el) || card === el) return "";
    const range = document.createRange();
    range.setStartAfter(el);
    range.setEnd(card, card.childNodes.length);
    return clean(range.toString());
  }

  // The figure printed right before a label in its card's words, as the
  // 2026 summary cards print it ("15 Search appearances"): the last word
  // before the label, and only when it is a count. A percentage is never a
  // count, so the change printed beside it ("0%") is never the figure.
  function figureBefore(label, text, share) {
    const said = clean(text).toLowerCase();
    const at = said.indexOf(label);
    if (at <= 0) return null;
    const before = said.slice(0, at).trim().split(/\s+/);
    return figureOf(before[before.length - 1], share);
  }

  // A labelled figure: the number in a leaf beside the label, within a few
  // levels, or leading the label's own line ("412 profile viewers ..."), or
  // the word right before the label in its card. The window is the one the
  // label's line, its card or the page names; on its card, after the label
  // too, where the 2026 cards print it after the change ("0% past 7 days")
  // in a line that is not a leaf of its own.
  function readLabels(page, leaves) {
    const found = [];
    const taken = new Set();
    for (const el of leaves) {
      const text = clean(el.textContent).toLowerCase();
      const hit = LABELS[page].find(([label, key]) => !taken.has(key) &&
        (text.startsWith(label) || new RegExp("^\\S+\\s+" + label + "\\b").test(text)));
      if (!hit) continue;
      const [label, key] = hit;
      const share = SHARES.has(key);
      let figure = null;
      let box = el;
      if (!text.startsWith(label)) figure = figureOf(text.split(/\s+/)[0], share);
      for (let depth = 0; depth < 3 && !figure && box.parentElement; depth += 1) {
        box = box.parentElement;
        const near = leavesOf(box).find((leaf) => leaf !== el && figureOf(leaf.textContent, share));
        if (near) figure = figureOf(near.textContent, share);
      }
      const card = cardOf(el, box);
      if (!figure) figure = figureBefore(label, card.textContent, share);
      if (!figure) continue;
      // Its own line's window, else its own card's: never a neighbouring
      // card's, which may name another range.
      const period = windowOf(el.textContent) ||
        leavesOf(box).map((leaf) => windowOf(leaf.textContent)).find(Boolean) ||
        windowOf(wordsAfter(el, card)) || null;
      taken.add(key);
      found.push({ key, figure, period });
    }
    return found.concat(readLines(page, taken));
  }

  // A label that is no element of its own: one line carries the figure, the
  // label and the window ("15 Search appearances 0% past 7 days"). The
  // figure is the count right before the label; the window is named after
  // it. The smallest element holding such a line is read, once per label.
  function readLines(page, taken) {
    const found = [];
    const root = document.querySelector("main") || document.body;
    for (const [label, key] of LABELS[page]) {
      if (taken.has(key)) continue;
      const share = SHARES.has(key);
      const lines = Array.from(root.querySelectorAll("p, span, li, div, a, h1, h2, h3, h4, h5, h6")).filter((el) => {
        const raw = el.textContent || "";
        if (raw.length > 400) return false;
        const text = clean(raw);
        return text.length > 0 && text.length < 120 && text.toLowerCase().includes(label) &&
          figureBefore(label, text, share);
      });
      const line = lines.find((el) => !lines.some((other) => other !== el && el.contains(other)));
      if (!line) continue;
      const text = clean(line.textContent).toLowerCase();
      const card = line.closest("li") || line;
      const period = windowOf(text.slice(text.indexOf(label) + label.length)) ||
        windowOf(wordsAfter(line, card)) || null;
      taken.add(key);
      found.push({ key, figure: figureBefore(label, text, share), period });
    }
    return found;
  }

  // The page's own range, for a figure whose card names none: on a content
  // page, which has one range, any window the page names; on an account
  // page, whose cards name different ranges, only its range control.
  function pageWindow(leaves, anyPhrase) {
    if (anyPhrase) {
      const named = leaves.map((leaf) => windowOf(leaf.textContent)).find(Boolean);
      if (named) return named;
    }
    const control = typeof detectAnalyticsPeriod === "function" ? detectAnalyticsPeriod() : null;
    return control && control !== "unrecognised" ? control : null;
  }

  // Readings grouped by window, each with its precision: rounded when any
  // figure under it was abbreviated.
  function grouped(found) {
    const by = new Map();
    for (const { key, figure, period } of found) {
      const reading = by.get(period) || { period_label: period, precision: "exact", figures: {} };
      reading.figures[key] = figure.value;
      if (figure.precision === "rounded") reading.precision = "rounded";
      by.set(period, reading);
    }
    return Array.from(by.values());
  }

  // New followers by day, from the chart's own labels: a day and a count
  // beside the word followers, in one element's accessible name. A label
  // with no readable day, or no count, is not a point.
  const MONTHS = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };

  function dayOf(text) {
    const iso = /(\d{4})-(\d{2})-(\d{2})/.exec(text);
    if (iso) return { day: iso[0], said: iso[0] };
    const pad = (n) => String(n).padStart(2, "0");
    const monthFirst = /\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b/.exec(text);
    const dayFirst = /\b(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b/.exec(text);
    const hit = monthFirst ? { month: monthFirst[1], day: monthFirst[2], year: monthFirst[3], said: monthFirst[0] }
      : dayFirst ? { month: dayFirst[2], day: dayFirst[1], year: dayFirst[3], said: dayFirst[0] } : null;
    const month = hit ? MONTHS[hit.month.slice(0, 3).toLowerCase()] : null;
    if (!hit || !month || Number(hit.day) < 1 || Number(hit.day) > 31) return null;
    return { day: `${hit.year}-${pad(month)}-${pad(hit.day)}`, said: hit.said };
  }

  function followerPoints(root) {
    const points = new Map();
    for (const el of root.querySelectorAll("[aria-label], [title]")) {
      const text = clean(el.getAttribute("aria-label") || el.getAttribute("title"));
      if (!/followers?\b/i.test(text)) continue;
      const day = dayOf(text);
      if (!day) continue;
      const rest = text.replace(day.said, " ");
      const count = /(\d[\d.,']*\s*[KkMm]?)\s+(?:new\s+)?followers?\b/i.exec(rest);
      const figure = count ? figureOf(count[1], false) : null;
      if (figure) points.set(day.day, { date: day.day, figure: "new_followers", value: figure.value, precision: figure.precision });
    }
    return Array.from(points.values()).sort((a, b) => (a.date < b.date ? -1 : 1));
  }

  function contentUrn() {
    let path = window.location.pathname;
    try {
      path = decodeURIComponent(path);
    } catch (err) {
      // Leave it encoded; the pattern below then finds nothing.
    }
    const match = /urn:li:[A-Za-z_]+:[A-Za-z0-9_-]{3,80}/.exec(path);
    return match ? match[0] : null;
  }

  const lastSent = {};

  function readPage() {
    const page = insightPage();
    if (!page) return;
    const root = document.querySelector("main") || document.body;
    const leaves = leavesOf(root);
    const found = readLabels(page, leaves);
    const body = { author: typeof signedInVanity !== "undefined" ? signedInVanity : null, page, readings: [] };
    if (CONTENT_PAGES.has(page)) {
      const urn = contentUrn();
      if (!urn) return;
      body.content_urn = urn;
      const period = pageWindow(leaves, true) || "";
      body.readings = grouped(found.map((f) => ({ ...f, period: f.period || period })));
    } else {
      const period = pageWindow(leaves, false);
      // An account count is kept only with a window: its own, or the page's.
      body.readings = grouped(found.map((f) => ({ ...f, period: f.period || period })).filter((f) => f.period));
    }
    if (page === "account_analytics") body.points = followerPoints(root);
    if (!body.readings.length && !(body.points && body.points.length)) return;
    const signature = window.location.pathname + JSON.stringify(body);
    if (lastSent[window.location.pathname] === signature) return;
    lastSent[window.location.pathname] = signature;
    if (typeof studioApi === "function") studioApi(FIGURES_PATH, body);
  }

  // ---------------------------------------------------------------
  // The creator's own Activity tab, for own_pages.js's activity reader
  // ---------------------------------------------------------------
  //
  // Called once per card on the creator's own activity page (own_pages.js
  // readActivity). A repost is the creator's own there: it is marked, and
  // its own figures are read from the card with the embedded original taken
  // out, only when an embedded original can be found to take out; otherwise
  // the counts may be the original's and none are given. A post of theirs is
  // marked edited when the mark sits before the post's own words, never from
  // the words themselves.
  const EMBEDDED = "[data-urn], [data-id^='urn:li:activity'], [data-activity-urn]";

  function ownCardFacts(card, helpers) {
    const facts = {};
    if (helpers && helpers.isRepost) {
      facts.own_repost = true;
      if (typeof helpers.counts === "function" && card.querySelector(EMBEDDED)) {
        const own = card.cloneNode(true);
        own.querySelectorAll(EMBEDDED).forEach((el) => el.remove());
        const counts = helpers.counts(own);
        if (counts && Object.values(counts).some((value) => value !== null && value !== undefined)) {
          facts.own_figures = counts;
        }
      }
      return facts;
    }
    const words = helpers && helpers.textElement;
    if (!words) return facts;
    for (const el of card.querySelectorAll("*")) {
      if (el.children.length || words.contains(el)) continue;
      if (!(el.compareDocumentPosition(words) & Node.DOCUMENT_POSITION_FOLLOWING)) continue;
      const text = clean(el.textContent);
      if (text.length <= 40 && /(^|[\s•·(])edited([\s•·)]|$)/i.test(text)) {
        facts.edited = true;
        break;
      }
    }
    return facts;
  }

  globalThis.inoxOwnCardFacts = ownCardFacts;

  // ---------------------------------------------------------------
  // Wiring: as own_pages.js does, after LinkedIn has rendered the page.
  // ---------------------------------------------------------------
  let settle = null;
  function onRoute() {
    if (!insightPage()) return;
    if (settle) clearTimeout(settle);
    settle = setTimeout(() => {
      readPage();
      // Charts and late cards render after the first read; once more.
      setTimeout(() => { if (insightPage()) readPage(); }, 6000);
    }, 2500);
  }

  window.addEventListener("studio:locationchange", onRoute);
  window.addEventListener("popstate", onRoute);
  onRoute();
})();
