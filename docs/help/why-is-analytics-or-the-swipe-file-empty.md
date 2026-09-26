# Why is my analytics chart or Swipe File empty?
Match what Analytics or the Swipe File shows to its cause, and get figures or specimens back on screen.

## Analytics: how figures arrive

The studio never fetches your analytics. The browser extension reads the impressions, engagements and followers cards on LinkedIn's own analytics page while you have it open, and sends them to the studio on this machine. How capture works and what each measure means is in [Read your analytics](read-your-analytics.md).

## Analytics: what you see, and what to do

| What you see | Why | What to do |
| --- | --- | --- |
| NOTHING MEASURED IN THIS RANGE on every measure | The studio holds no days at all. The range counts back from the latest stored day, so once one day exists, every range has something | Work through the checklist below |
| Only **Profile views** shows NOTHING MEASURED IN THIS RANGE | Profile views are never captured | Nothing to fix. This is expected |
| **Comments** is a flat line at 0 | Comments are never captured; captured days store 0 | Nothing to fix. This is expected |
| You just visited LinkedIn, but the page has not changed | Analytics reads once when you open it and again only when you change the range. It does not refresh on its own | Switch to another surface in the rail and back to **Analytics** |
| LinkedIn showed a notice ending "Set the range to 24 hours to sync a daily figure." | The page showed a multi-day total, which the studio refuses | Set LinkedIn's range selector to the past 24 hours. The extension reads again |
| No LinkedIn Studio notice at all on the analytics page | The extension is not loaded in that browser, or it found neither an impressions nor a followers card, so it sent nothing | Check the extension is loaded, then reload the LinkedIn analytics page |
| ANALYTICS UNAVAILABLE | The studio did not answer or refused the request | Check the studio is running, then reload the page |
| LOADING ANALYTICS that never ends | The server has not answered | Treat it like ANALYTICS UNAVAILABLE |
| NO PUBLISHED POSTS TO COMPARE | No post has the published status | Mark a post as published; see [Publish, queue or send a post to LinkedIn](publish-queue-or-send-to-linkedin.md) |
| Post rows all read 0 | The extension does not capture per-post figures | Nothing to fix. This is expected |

> [!NOTE]
> The notice "LinkedIn Studio: creator analytics synced to your local studio." also appears when the studio could not be reached or refused the figures. Always confirm on **Analytics**.

## Analytics checklist

1. Make sure the studio is running: `http://127.0.0.1:8000` opens in your browser.
2. Make sure the extension is loaded and paired in Edge or Brave. See [Install the browser extension that captures leads and analytics](install-the-browser-extension.md).
3. Open `http://127.0.0.1:8000` once in that same browser, so the extension can pick up the studio token. If leads are missing too, fix the token first, as [Why is my lead list empty?](why-is-my-lead-list-empty.md) describes.
4. Open your LinkedIn analytics page and set its range selector to the past 24 hours. Wait a couple of seconds.
5. Open **Analytics** in the studio, or switch away and back if it was already open.

If you see a banner reading "*n* of *m* days are seeded sample data, not measurements.", those days are generated samples, not your figures. [Read your analytics](read-your-analytics.md) explains it.

## Swipe File: what you see, and what to do

The Swipe File reads its specimens once when you open it. They are hook forms stored on this machine, starting with a set that ships with the studio. Nothing is fetched from LinkedIn.

| What you see | Why | What to do |
| --- | --- | --- |
| SWIPE FILE UNAVAILABLE | The request to the studio failed | Check the studio is running, then reopen **Swipe File** |
| LOADING SPECIMENS that never ends | The server has not answered | Treat it like SWIPE FILE UNAVAILABLE |
| NOTHING MATCHES THAT | Your text in **Search specimens**, or the type chip you chose, matches nothing. Search looks at the post text, the hook and the topic, and it combines with the chip | Clear the search box and choose **All** |
| NO SPECIMENS SAVED YET | The library came back empty. The studio refills it with its shipped forms whenever it is empty, so this should be rare | Switch to another surface and back to **Swipe File**. If it persists, run the doctor command below |

## Still stuck

Run `python -m studio.cli doctor` in a terminal opened in the checkout folder (portable build: `InoxHydra-CLI.bat doctor`). It lists content row counts and any problems it found. Then see [The studio will not open](the-studio-will-not-open.md).
