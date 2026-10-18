/**
 * Inox Hydra - Voyager Network Interceptor
 * 
 * PURPOSE:
 * Runs in the MAIN world (LinkedIn's own page context), and only while the
 * creator has switched network reading on in the extension popup; it is off
 * by default. It copies the JSON of responses from LinkedIn's internal Voyager
 * API that LinkedIn's app already fetched for the page the creator has open:
 * feed updates, profiles, creator analytics, social actions and comments.
 * It never makes a request of its own.
 *
 * POSTURE:
 * - Runs in an IIFE to prevent global namespace pollution.
 * - Wraps `window.fetch` in a Proxy, so LinkedIn's code sees fetch behave
 *   exactly as the original does. The wrapping is disclosed in the popup and
 *   the README; it is not hidden from the creator.
 * - Entirely read-only: NEVER modifies requests or responses.
 * - Highly defensive: Wraps capture logic in try-catch to ensure LinkedIn never breaks
 *   even if our parsing logic fails.
 * - Communicates with the extension isolated world via window.postMessage.
 */
(() => {
    'use strict';

    // Avoid multiple injections in case of script re-evaluation
    if (window.__inox_voyager_intercepted__) return;
    Object.defineProperty(window, '__inox_voyager_intercepted__', { value: true, enumerable: false, writable: false });

    // Rate limiting: max 30 requests per minute to avoid memory pressure
    // Past bug: Capturing too many large Voyager responses quickly caused OOM crashes
    // in the background worker. A simple sliding window fixes this.
    const MAX_REQUESTS_PER_MIN = 30;
    const requestTimestamps = [];

    // Size limit: 2MB limit for response body
    // Voyager API responses for feed scrolling can sometimes be enormous
    const MAX_BODY_SIZE = 2 * 1024 * 1024;

    function isRateLimited() {
        const now = Date.now();
        // Prune timestamps older than 60 seconds
        while (requestTimestamps.length > 0 && requestTimestamps[0] < now - 60000) {
            requestTimestamps.shift();
        }
        if (requestTimestamps.length >= MAX_REQUESTS_PER_MIN) {
            return true;
        }
        requestTimestamps.push(now);
        return false;
    }

    const originalFetch = window.fetch;

    // A Proxy rather than a wrapper function, so calls and properties behave as
    // the original fetch does and LinkedIn's app is unaffected by the wrapping.
    // It is not invisible: fetch.toString() no longer names the original, and
    // the popup says the page's fetch is wrapped.
    const fetchProxy = new Proxy(originalFetch, {
        apply: function(target, thisArg, argumentsList) {
            // Immediately execute the original fetch to ensure zero blocking/delay
            const fetchPromise = Reflect.apply(target, thisArg, argumentsList);

            // Handle the interception asynchronously
            fetchPromise.then(response => {
                try {
                    if (!response || !response.url) return;
                    
                    // Filter: Only intercept Voyager API calls to minimize overhead
                    if (!response.url.includes('/voyager/api/')) return;

                    // Apply rate limit guard
                    if (isRateLimited()) return;

                    // Extract URL without query parameters for cleaner telemetry
                    let pathOnly = response.url;
                    try {
                        const urlObj = new URL(response.url);
                        pathOnly = urlObj.origin + urlObj.pathname;
                    } catch (e) {
                        // fallback to raw URL if parsing fails
                    }

                    // Pre-check size guard via Content-Length header if available
                    const contentLength = response.headers.get('content-length');
                    if (contentLength && parseInt(contentLength, 10) > MAX_BODY_SIZE) {
                        return;
                    }

                    // Clone the response so we can read the body without consuming
                    // the original stream that the LinkedIn app needs.
                    const responseClone = response.clone();

                    responseClone.text().then(text => {
                        try {
                            // Secondary size check in case Content-Length was missing or inaccurate
                            if (text.length > MAX_BODY_SIZE) return;

                            const body = JSON.parse(text);

                            // Determine HTTP method
                            const reqOpts = argumentsList[1];
                            const method = (reqOpts && reqOpts.method) ? reqOpts.method.toUpperCase() : 'GET';
                            
                            // Generate unique capture ID
                            const captureId = 'capture_' + Date.now() + '_' + Math.random().toString(36).substring(2, 9);

                            const message = {
                                type: 'INOX_VOYAGER_CAPTURE',
                                source: 'inox-voyager-interceptor',
                                payload: {
                                    url: pathOnly,
                                    method: method,
                                    status: response.status,
                                    timestamp: new Date().toISOString(),
                                    body: body,
                                    captureId: captureId
                                }
                            };

                            // Transmit to isolated world content script
                            window.postMessage(message, window.location.origin);
                        } catch (parseError) {
                            // Silently ignore JSON parse errors (e.g. 204 No Content)
                        }
                    }).catch(() => {
                        // Silently ignore text() read errors
                    });

                } catch (err) {
                    // Maximum defense: catch all synchronous errors in the interception flow
                    // to guarantee LinkedIn functionality is never interrupted
                }
            }).catch(() => {
                // Ignore network errors or user-aborted fetches
            });

            // Return the unadulterated original promise chain
            return fetchPromise;
        }
    });

    try {
        Object.defineProperty(window, 'fetch', {
            value: fetchProxy,
            configurable: true,
            enumerable: false,
            writable: true
        });
    } catch (e) {
        // Fallback
        window.fetch = fetchProxy;
    }

})();

