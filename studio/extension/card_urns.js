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

    function stampCardUrns() {
        try {
            const cards = document.querySelectorAll(CARDS);
            for (let c = 0; c < cards.length; c++) {
                const card = cards[c];
                if (card.getAttribute('data-urn')) continue;
                let found = urnOf(card);
                if (!found) {
                    const inners = card.querySelectorAll('*');
                    for (let i = 0; i < Math.min(inners.length, 50) && !found; i++) {
                        found = urnOf(inners[i]);
                    }
                }
                if (found) card.setAttribute('data-urn', found);
            }
        } catch (err) {}
    }

    stampCardUrns();
    setInterval(stampCardUrns, 1500);
    document.addEventListener('DOMContentLoaded', stampCardUrns);
})();
