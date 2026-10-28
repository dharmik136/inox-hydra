# Install the browser extension that captures leads and analytics

Load the studio's browser extension in Edge or Brave so it can record the people and figures on LinkedIn pages you open yourself.

By default the studio makes no requests to LinkedIn itself. Apart from optional demo data, leads and daily figures arrive only through this extension, which reads LinkedIn pages while you browse them and passes what it reads to the studio on this machine. On your browser's extensions page it is listed as **Inox Hydra Bridge**.

## Network reading is off unless you switch it on

The extension's popup has a switch, **Read LinkedIn's network responses**. Off, which is how it starts, the bridge reads only what is on the pages you open. On, it also copies the figures LinkedIn's own app has already downloaded for those pages, which are exact rather than rounded: those of your own posts, and your follower count. The other posts in your feed, and the profiles, reactions and comments LinkedIn's page downloads, are not kept. It also notes which of LinkedIn's data requests the pages made (the address and status, not the contents). It does this by wrapping the page's `fetch` function. LinkedIn's page code can see that wrapping and may treat it as automation, so leave it off unless you want the exact figures.

Switching it on applies to LinkedIn pages you open or reload afterwards. Switching it off stops the copying at once; a LinkedIn tab that was already open keeps the wrapper in place, doing nothing, until you reload it.

The studio says which of three states it is in, in **Setup** step 1 and in the side panel's **Health** tab: "Network reading is off.", "Network reading is on and seeing N LinkedIn data calls, K matched." or "Network reading is on and matching nothing", with the number of data calls the LinkedIn tab that last reported saw. While it is on, each LinkedIn page also counts the data calls it makes and hands the counts to the extension, which sends those of the page you looked at last with its check-in once a minute. An address is counted only as the words of LinkedIn's own API, from a fixed list (such as `identity`, `profiles`, `feed`), with every other part written `_id_`, and a GraphQL call by its query name, or as `other` when the name is not one of LinkedIn's; nothing else of an address is kept, so the studio can name what LinkedIn calls without you opening the browser's developer tools. The sentence adds "reload that tab" when the page was opened before the switch, and "turn the switch off and on" when the browser did not register the reader.

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
3. The browser opens at your LinkedIn feed, with the studio in a second tab, and the studio shows a message such as "Launched Microsoft Edge with the bridge loaded."

The browser opens in its own profile, separate from your usual one, so the bridge attaches even when that browser is already open. The first time, sign in to LinkedIn in that window. Your usual browser windows are not touched. The profile is kept in your user data folder, never in the studio's own folder, because it holds your LinkedIn sign-in.

Other installed browsers are named underneath in a single line. It ends "IGNORES THE EXTENSION FLAG, SO THE BRIDGE WOULD NOT ATTACH." when Chrome is among them, and "HAS NOT BEEN CHECKED ON THIS MACHINE." otherwise. If you see "NO CHROMIUM BROWSER FOUND ON THIS MACHINE. INSTALL EDGE OR BRAVE TO RUN THE BRIDGE.", install one of them first.

## Option B: load it by hand

This section of the empty **Leads** page appears only when the studio found at least one browser.

1. Under **OR LOAD IT BY HAND**, click **Copy the folder path**. The path is also printed under the button.
2. Open your browser's extensions page (`edge://extensions` in Edge, `brave://extensions` in Brave).
3. Turn on developer mode.
4. Choose **Load unpacked** and select that folder, which is the `extension` folder inside the studio's `studio` folder.

The studio shows "Copied to the clipboard:" followed by the path even when the clipboard could not be reached. If pasting gives you something else, type or copy the printed path instead.

## Pair it with the studio

If you used option A, this is already done: the studio tab that opened beside LinkedIn paired it. If you loaded the extension by hand, open `http://127.0.0.1:8000` once in the same browser. That page load gives the browser the studio's access token as a cookie, and the extension's background worker sends it with every request it makes. Opening the studio only in another browser, or only in the tray icon's app window (which opens in Google Chrome when Chrome is installed), does not count. Without the token the studio refuses every capture.

## What it captures, and when

| Where you are | What is read | Where it goes |
| --- | --- | --- |
| Feed and post pages | Name, headline, profile link and the first 140 characters of comment text of commenters; people in an open reactions list | **Leads** |
| A post's own page | The post's ID, text and author; nothing on a page that shows someone's repost | Offered to the studio to link to a post you wrote, which it refuses when the author is someone else. In this build that link does not complete; see [Read your analytics](read-your-analytics.md). |
| Your creator analytics page, any address starting `/analytics/creator` | Impressions, engagements and followers from the figure cards, about 2 seconds after the page loads or after you click through to it from elsewhere on LinkedIn, with the LinkedIn account this browser is signed in to | **Analytics**, only when that account is the profile confirmed in **Setup** |
| Your own profile | Which LinkedIn account this browser is signed in to, forgotten when you sign out of LinkedIn | Kept in the extension, to name the account analytics came from |
| When you press **Sync LinkedIn Session** in the popup | Your LinkedIn session cookies, if both exist | The studio's saved LinkedIn session |
| Some LinkedIn data requests the page makes (feed updates, profiles, creator analytics) | The address (without its query) and status code | The studio's local telemetry store |

Everything goes only to the studio at `127.0.0.1:8000`. Lead capture skips profile pages, and your activity pages (`linkedin.com/in/you/recent-activity/...`) are not read for leads: open the post itself, or find it in your feed, to capture the people who engaged with it. On the feed, the extension reads commenters and reactors on any post you can see, but the studio keeps only people who engaged with your own posts, and only after you have confirmed your profile in **Setup**. A reactions list opens outside the post it belongs to, so the extension files it under the post whose reaction count you clicked, or the post page you are on, and sends nothing from a list whose post it cannot tell. See [Why is my lead list empty?](why-is-my-lead-list-empty.md) Nothing copies your session on a timer; see [Connect your LinkedIn session](connect-your-linkedin-session.md).

## What it never does

It does not post, comment, react, message or follow on your behalf. Apart from the session cookies and request addresses above, it reads what your browser is already showing.

Two things it does act on a page, and both happen only when you press something:

- **The side panel's insert button.** It opens LinkedIn's post box if needed and types your text into it, but it does not press Post.
- **A history import, after you press Import in Setup.** It clicks LinkedIn's own "Show more results" control and scrolls your own activity page so it can read further back, at a randomised pace, for up to 250 rounds, and when it has finished one kind it loads the next activity page itself. A **Stop** control sits on the page throughout, it pauses while the tab is not in front, and however many tabs show the page, only one of them scrolls. See [Set up the studio from your LinkedIn](set-up-the-studio-from-your-linkedin.md).

The part of the extension that runs inside LinkedIn pages can reach only a fixed list of studio functions: saving analytics, linking a post, saving an engagement, the bridge's heartbeat and capture log, recognising your own profile, saving your own posts, comments and reactions and the history imports that read them, and, only while network reading is on, the network readings. Fields named after LinkedIn session credentials are stripped out first.

> [!NOTE]
> The toolbar popup and side panel ask the studio through the extension's background worker, which carries the studio token. The popup's server line reads Online, Not paired or Offline, and a side panel list that cannot load names the reason: the studio is not running, has not paired with this browser, or answered with an error status.

## Check it works

Open one of your posts with comments. A capture that worked is confirmed outside LinkedIn's page, from the extension's own record of it, with no call to the studio:

- The extension's toolbar icon shows a count on a green badge: how many captures from this tab the studio stored this session. Only what the studio stored is counted, so the engagers of other people's posts, which the studio deliberately does not keep, never add to it. The count clears when you open the side panel.
- The badge turns orange while captures are waiting for a studio that was busy or closed, and in a tab with no count of its own it then shows how many are waiting. It also turns orange, with a `!` in such a tab, after a part of the capture reported this session that it could not read a page. The icon's tooltip says which.
- The side panel's header reads, for example, "Captured an engager on your post just now." It names the kind of thing and when, never the person, and it updates the moment the next capture lands. When the last page read gave the studio nothing new, it reads "Read LinkedIn just now; nothing new to keep." The popup shows the same line.
- The people are now in **Leads**. Reopen **Leads** to see them.

Nothing the extension says is drawn into LinkedIn's page. What you can act on, or must know was not saved, appears at the top of the side panel the next time you open it, and until then the badge shows a `!` and its tooltip gives the sentence. For example:

- "Inox Hydra: N engager(s) had no profile link and were not saved."
- "Inox Hydra: could not reach your studio, so nothing was saved." The studio is not running, or this browser was never paired.

The one exception is a history import: its banner, with its **Stop** control, stays on the page while it runs, and a warning during the import is a sentence in that banner.

When a part of the capture cannot read a page LinkedIn has rebuilt, the side panel's header says so once per kind of page per browser session, for example "LinkedIn's feed page: cannot read commenter name, noticed 2 min ago. See Health in the studio.", and the badge turns orange. The notice goes when that part next reads the same kind of page cleanly, and when you close the browser. Nothing about it is drawn into LinkedIn's page.

The side panel's **Health** tab also lists the data calls seen in the LinkedIn tab that last reported while network reading was on, by query name and how many times, for example `voyagerFeedDashMainFeed (9)`, so you can see what LinkedIn calls without opening the browser's developer tools.

## If it does not work

See [Why is my lead list empty?](why-is-my-lead-list-empty.md). For analytics, see [Read your analytics](read-your-analytics.md).
