/**
 * Inox Hydra Bridge - Post IDs on Feed Cards
 *
 * Runs in the MAIN world (LinkedIn's own page context), always, because it is
 * page reading: LinkedIn's newer feed cards carry their post's id only in
 * React's properties, which the extension's own scripts cannot see from their
 * isolated world. This copies each card's id onto the card as a data-urn
 * attribute, so content.js knows which post a commenter or reactor belongs to.
 *
 * It reads the page and adds one attribute. It does not wrap fetch, read
 * network responses, or send anything anywhere. It used to live inside
 * voyager_interceptor.js, so switching network reading off (the default) also
 * left feed engagers without a post.
 */
(() => {
    'use strict';

    if (window.__inox_card_urns__) return;
    Object.defineProperty(window, '__inox_card_urns__', { value: true, enumerable: false, writable: false });

    const CARDS = 'div[id^="expanded"][id*="FeedType_"], div[id*="FeedType_"], [data-view-name="feed-full-update"], .feed-shared-update-v2, .occludable-update';
    const ACTIVITY = /urn:li:activity:(\d+)/;
    const OTHER = /urn:li:(share|ugcPost):(\d+)/;

    // The id as LinkedIn names it. A share or ugcPost id is a different number
    // from the post's activity id, so it is never relabelled as one.
    function urnIn(props) {
        try {
            const str = JSON.stringify(props);
            const activity = ACTIVITY.exec(str);
            if (activity) return 'urn:li:activity:' + activity[1];
            const other = OTHER.exec(str);
            if (other) return 'urn:li:' + other[1] + ':' + other[2];
        } catch (e) {}
        return null;
    }

    function urnOf(el) {
        for (const k in el) {
            if (k.startsWith('__reactProps')) {
                const found = urnIn(el[k]);
                if (found) return found;
            }
        }
        return null;
    }

    // This runs in the page's own world, where the extension's worker is out
    // of reach, so it reports the way it works: by marking the page. One
    // attribute on the root element carries how many feed cards are on
    // screen, how many carry a post id, and its own timing (each run is timed
    // with performance.now(); runs over 50 ms are counted), written once
    // after the first tick and then at most once a minute while there is
    // something on screen. content.js watches that attribute and forwards it
    // to the capture log as the "card_urns" reader. It sends nothing and
    // posts nothing.
    const REPORT_ATTRIBUTE = 'data-inox-card-urns';
    const SLOW_RUN_MS = 50;
    const REPORT_EVERY_MS = 60000;
    let runs = 0;
    let slowRuns = 0;
    let lastRunMs = null;
    let reportedAt = 0;
    let firstRun = true;

    function now() {
        try { return performance.now(); } catch (e) { return Date.now(); }
    }

    function report(seen, stamped) {
        try {
            document.documentElement.setAttribute(REPORT_ATTRIBUTE, JSON.stringify({
                seen: seen, stamped: stamped, duration_ms: lastRunMs, reads: runs, slow_reads: slowRuns, at: Date.now()
            }));
        } catch (e) {}
        runs = 0;
        slowRuns = 0;
        reportedAt = Date.now();
    }

    function stampCardUrns() {
        const started = now();
        let seen = 0;
        let carrying = 0;
        try {
            const cards = document.querySelectorAll(CARDS);
            seen = cards.length;
            for (let c = 0; c < cards.length; c++) {
                const card = cards[c];
                if (card.getAttribute('data-urn')) { carrying += 1; continue; }
                let found = urnOf(card);
                if (!found) {
                    const inners = card.querySelectorAll('*');
                    for (let i = 0; i < Math.min(inners.length, 50) && !found; i++) {
                        found = urnOf(inners[i]);
                    }
                }
                if (found) { card.setAttribute('data-urn', found); carrying += 1; }
            }
        } catch (err) {}
        const ms = Math.max(0, now() - started);
        runs += 1;
        if (ms > SLOW_RUN_MS) slowRuns += 1;
        lastRunMs = Math.round(ms * 10) / 10;
        // The first run can precede the isolated world's listener; the first
        // report waits for the first tick.
        if (firstRun) { firstRun = false; return; }
        if (seen > 0 && Date.now() - reportedAt >= REPORT_EVERY_MS) report(seen, carrying);
    }

    stampCardUrns();
    setInterval(stampCardUrns, 1500);
    document.addEventListener('DOMContentLoaded', stampCardUrns);
})();
