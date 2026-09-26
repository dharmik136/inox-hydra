# Install the browser extension that captures leads and analytics

Load the studio's browser extension in Edge or Brave so it can record the people and figures on LinkedIn pages you open yourself.

By default the studio makes no requests to LinkedIn itself. Apart from optional demo data, leads and daily figures arrive only through this extension, which reads LinkedIn pages while you browse them and passes what it reads to the studio on this machine. On your browser's extensions page it is listed as **LinkedIn Studio Bridge (LocalTaplio)**.

## Which browser to use

| Browser | Result |
| --- | --- |
| Microsoft Edge | Loads the extension from the studio's launcher |
| Brave | Loads the extension from the studio's launcher |
| Google Chrome | Ignores the launcher's extension flag, so the extension is not attached. The studio's check covers only that flag, not loading it by hand. |
| Opera, Vivaldi | Detected if installed, but not checked |

## Option A: launch from the Leads page

While your lead list is empty, **Leads** shows the launcher.

1. Open **Leads** in the rail.
2. Under **OPEN LINKEDIN WITH THE BRIDGE**, click your browser, for example **Microsoft Edge** or **Brave Browser**.
3. The browser opens at your LinkedIn feed and the studio shows a message such as "Launched Microsoft Edge with the bridge loaded."

Other installed browsers are named underneath in a single line. It ends "IGNORES THE EXTENSION FLAG, SO THE BRIDGE WOULD NOT ATTACH." when Chrome is among them, and "HAS NOT BEEN CHECKED ON THIS MACHINE." otherwise. If you see "NO CHROMIUM BROWSER FOUND ON THIS MACHINE. INSTALL EDGE OR BRAVE TO RUN THE BRIDGE.", install one of them first.

## Option B: load it by hand

This section of the empty **Leads** page appears only when the studio found at least one browser.

1. Under **OR LOAD IT BY HAND**, click **Copy the folder path**. The path is also printed under the button.
2. Open your browser's extensions page (`edge://extensions` in Edge, `brave://extensions` in Brave).
3. Turn on developer mode.
4. Choose **Load unpacked** and select that folder, which is the `extension` folder inside the studio's `studio` folder.

The studio shows "Copied to the clipboard:" followed by the path even when the clipboard could not be reached. If pasting gives you something else, type or copy the printed path instead.

## Pair it with the studio

In the same browser, open `http://127.0.0.1:8000` once. That page load gives the browser the studio's access token as a cookie, and the extension's background worker sends it with every request it makes. Opening the studio only in another browser, or only in the tray icon's app window (which opens in Google Chrome when Chrome is installed), does not count. Without the token the studio refuses every capture.

## What it captures, and when

| Where you are | What is read | Where it goes |
| --- | --- | --- |
| Feed, post pages and activity pages | Name, headline, profile link and the first 140 characters of comment text of commenters; people in an open reactions list | **Leads** |
| A post's own page | The post's ID and text | Offered to the studio to link to a post you wrote. In this build that link does not complete; see [Read your analytics](read-your-analytics.md). |
| Any LinkedIn page with `/analytics` in its address | Impressions, engagements and followers from the figure cards, about 2 seconds after load | **Analytics** |
| In the background, every 15 minutes | Your LinkedIn session cookies, if both exist | The studio's saved LinkedIn session |
| Some LinkedIn data requests the page makes (feed updates, profiles, creator analytics) | The address (without its query) and status code | The studio's local telemetry store |

Everything goes only to the studio at `127.0.0.1:8000`. Lead capture skips profile pages. On the feed, it captures commenters and reactors on any post you can see, not only your own. The first session copy can take up to 15 minutes after install; see [Connect your LinkedIn session](connect-your-linkedin-session.md).

## What it never does

It does not post, comment, react, message or follow on your behalf, and it does not load LinkedIn pages. Apart from the session cookies and request addresses above, it reads only what your browser is already showing. The one thing it can do on a LinkedIn page is the side panel's insert button: it opens LinkedIn's post box if needed and types your text into it, but it does not press Post.

The part of the extension that runs inside LinkedIn pages relays to just three studio functions: saving analytics, linking a post, and saving an engagement. Fields named after LinkedIn session credentials are stripped out first.

> [!NOTE]
> Do not rely on the extension's toolbar popup or side panel for status. They call the studio without the studio token, so the popup's sync button reports the studio as not reachable and their lists stay empty or stuck on loading, even when it is running.

## Check it works

Open one of your posts with comments. A small notice appears on the LinkedIn page for people it has not already seen on that post since the page loaded:

- "LinkedIn Studio: N engager(s) captured from this post." The people are now in **Leads**. Reopen **Leads** to see them.
- "LinkedIn Studio: N engager(s) had no profile link and were not saved."
- "LinkedIn Studio: could not reach your studio, so nothing was saved." The studio is not running, or this browser was never paired.

## If it does not work

See [Why is my lead list empty?](why-is-my-lead-list-empty.md). For analytics, see [Read your analytics](read-your-analytics.md).
