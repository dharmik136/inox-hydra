# Chrome Extension & Sync Bridge

The **Inox Hydra Bridge** extension connects the LinkedIn pages you open in your own browser to the studio running on `127.0.0.1:8000`. For everyday reading it never acts on LinkedIn for you. Two things it does do to the page, both covered below and both only when you press something: a history import, which clicks LinkedIn's own load-more control, scrolls, and moves the tab from one of your activity pages to the next; and placing a draft, which opens LinkedIn's composer and types your post into it. Neither posts: you press LinkedIn's own Post button yourself.

---

## 1. Extension Component Architecture

```mermaid
graph TD
    subgraph BrowserContext [Google Chrome Browser]
        Tab[Active LinkedIn Tab: linkedin.com]
        ContentScript[Content Script: content.js<br/>Passive DOM MutationObserver]
        BackgroundWorker[Service Worker: background.js<br/>Cookies API; drains kept captures every 1 min]
        SidePanel[Side Panel: sidepanel.html<br/>In-Feed Composer]
    end

    subgraph LocalhostEngine [Localhost Studio: 127.0.0.1:8000]
        AuthEndpoint[POST /api/auth/cookies]
        CaptureEndpoints[POST /api/v1/bridge/capture,<br/>/api/v1/crm/interactions/ingest]
        PanelEndpoints[GET through an allowlist,<br/>POST /api/v1/posts/injected]
        SQLite[(SQLite: leads & settings)]
    end

    BackgroundWorker -->|chrome.cookies.get| Tab
    BackgroundWorker -->|POST tokens| AuthEndpoint
    
    ContentScript -->|Observe Comments DOM| Tab
    ContentScript -->|Debounced POST, allowlisted paths only| CaptureEndpoints
    
    SidePanel <-->|Reads, and the one write for an injected draft| PanelEndpoints
    
    AuthEndpoint --> SQLite
    CaptureEndpoints --> SQLite
    PanelEndpoints --> SQLite
```

---

## 2. What the Bridge Does in LinkedIn's Page

LinkedIn's User Agreement restricts automated access. The bridge is built to stay a reader of pages you open yourself, with two named exceptions, and to say plainly what it does there:

| What | How |
| :--- | :--- |
| **Page reading** | Content scripts read the page you have open, as it renders, and follow your own scrolling. They never post, react, comment, message or connect, at all. They click and type in exactly two places, both named below, and each only when you press something yourself. |
| **History import (first exception)** | Only after you press **Import your history** in Setup, for your own posts, comments or reactions, `own_pages.js` clicks LinkedIn's "Show more results" control and scrolls the page itself, so it can read further than what was already on screen. It runs at a randomised pace, 1.6 to 3.2 seconds between rounds, for up to 250 rounds per kind: up to several minutes of unattended clicking and scrolling. When you asked for all three kinds, it also moves the tab itself from one of your activity pages to the next (`own_pages.js:1388` sets `window.location.href`), so the import opens a page as well as reading one. A **Stop** control sits on the page the whole time, and the import pauses itself while the tab is not visible. It runs only because you asked for that import, on your own activity, never on a timer and never on a page that is not yours. This is the exposure the risk register (`planning/7 Roadmap/Risk - LinkedIn terms and detection.md`) names as "the scrolled History Import". |
| **Placing a draft (second exception)** | Only when you press the side panel's insert control, `content.js` puts a draft you wrote into LinkedIn's composer: if the composer is not already open it clicks LinkedIn's **Start a post** control to open it (`content.js:275-279`), then types the text into the editor. It never presses **Post**, and if it cannot find the composer the side panel says so and nothing is typed. |
| **Network reading (off by default)** | Only when you switch on **Read LinkedIn's network responses** in the extension's popup: `voyager_interceptor.js` wraps `window.fetch` in LinkedIn's page and copies the JSON of responses LinkedIn's own app already fetched, for exact rather than rounded figures, and the worker notes which of LinkedIn's data requests a page made (address and status, never contents). It never sends a request of its own. Wrapping fetch is visible to LinkedIn's page code, which may treat it as automation. Switching it off stops the copying at once; an open tab keeps the inert wrapper until reloaded. |
| **Post ids on feed cards** | `card_urns.js` runs in the page, always, and copies each feed card's post id from LinkedIn's React properties onto the card as `data-urn`, so the readers know which post a commenter belongs to. That attribute and the history import's banner are the only marks the extension leaves in LinkedIn's page (decision D3); the stamper's own count and timing reach the extension as a window message. It does not touch fetch. |
| **Requests to LinkedIn** | None. No part of the extension fetches from LinkedIn, network reading included: that feature copies answers LinkedIn's own page already had. What a history import does instead is make LinkedIn's own page fetch: its click on the load-more control, and the activity page it opens, are requests LinkedIn's page issues because the extension acted on it. Separately from the extension, the studio itself contacts LinkedIn for features that are off by default, from your machine, never from a server. |
| **Session** | Copied into the studio only when you press **Sync LinkedIn Session** in the popup, read through `chrome.cookies`, and sealed at rest. |

---

## 3. Passive Commenter & Engager Capture Pipeline

When you browse LinkedIn and view comments or open the reaction modal (Likes/Celebrates) of any post, `content.js` passively observes DOM mutations:

* **Comment Extraction**: Observes comments in feed updates and permalink post views, parsing person names, headlines, profile URLs, and exact comment text.
* **Reaction Modal Extraction**: When you click the reaction count on a post to see who liked/celebrated it, the extension reads the listed reactors and files them under that post: LinkedIn renders the list outside the post's card, so the post is the one whose card was clicked, or the post page you are on. A list whose post cannot be told is not sent. The studio keeps only people who engaged with your own posts.
* **Smart Deduplication**: Re-engaging prospects have their latest context notes updated in SQLite rather than creating duplicate entries. Several tabs on one post send it once: a read of a post is one request with an item per person, the worker answers the same capture from another tab within ten seconds itself (from a SHA-256 key in `chrome.storage.session`, never the words), and the studio answers a replay `already_seen` before its single writer. Ten tabs reading one post with 30 commenters went from 620 requests to the studio to 3, and from writing each engagement ten times to once.
* **Feedback**: A capture the studio stored is confirmed on the extension's action badge (a per-tab count of stored captures for the session, green; orange while captures are waiting or after a reader reported drift this session) and in the side panel's header, from the worker's own `lastCapture` record in `chrome.storage.local` and its drift notice in `chrome.storage.session`, with no studio call and nothing drawn into LinkedIn's page (cycle 4, decision D3). An answer that stored nothing (`nothing_new`, `written: 0`) is never counted. What the creator must act on ("Inox Hydra: could not reach your studio, so nothing was saved.") goes to the worker as text, which keeps it in `chrome.storage.session`, shows `!` on the badge until the side panel opens, and is shown at the top of the panel in a status line; a warning while a history import runs is a sentence in the import's banner. Nothing else is drawn into LinkedIn's page. People read while the studio was unreachable are offered again 30 seconds later.

### Analytics, and whose they are

LinkedIn's analytics page and its network responses do not say whose figures they show. The extension learns which LinkedIn account the browser is signed in to from your own profile (shown with its owner's edit controls, or reached through `/in/me/`), forgets it when LinkedIn's sign-in cookie changes, and sends it with every analytics reading. The studio keeps a reading only when that account is the profile confirmed in Setup. Figures are read in the page's language, and a follower count is kept whatever range the page shows.

### Lead Extraction Fields:
* **Name**: Sanitized author name.
* **Headline**: Current professional designation (e.g. `VP of Engineering at CloudScale`).
* **Company**: Extracted from headline via regex parsing (`at X` / `@ X`).
* **Profile URL**: Cleaned LinkedIn vanity URL (tracking parameters stripped).
* **Engagement Type**: Categorized as `Commented`, `Liked`, or `Reposted`.
* **Notes**: Quoted comment text or reaction context for personalized 1-on-1 outreach.

---

## 4. Session Sync, When You Ask

Nothing about your session runs on a timer. Four other things do, and none touches LinkedIn: the worker retries captures the studio was too busy to take, every minute (`background.js`, `DRAIN_EVERY_MINUTES`); a page the bridge is reading tells the worker it is open every minute (`own_pages.js`, `HEARTBEAT_MS`); the worker tells the studio it is alive once a minute for the whole browser, with the pages open by kind (`background.js`, `HEARTBEAT_ALARM`); and an unpacked install reads its own `manifest.json` every five minutes and reloads itself when the version there differs from the one it runs (`OWN_FILES_EVERY_MINUTES`). The first three talk only to `127.0.0.1:8000`; the fourth reads a file in the extension's own folder.

When you press **Sync LinkedIn Session** in the popup, `studio/extension/background.js`:

1. Reads `li_at` and `JSESSIONID` from Chrome's cookie store.
2. Posts them to `http://127.0.0.1:8000/api/auth/cookies`, with the studio token.
3. The studio seals them at rest. They are used only by the features that need a session, such as staging a post into LinkedIn's scheduler, and the Setup screen shows whether one is held, with a Delete control.

An earlier version copied the session every 15 minutes. That alarm is cleared when the extension starts.

---

## 5. Sidepanel Composer & In-Feed Warm CRM

The extension embeds a lightweight workspace directly into Chrome's native **Side Panel**:
* **Composer Tab**: Draft and format posts with Unicode mathematical sans-bold and insert into the LinkedIn composer with 1 click. That insert is the second of the two exceptions in §2: it clicks LinkedIn's **Start a post** control if the composer is closed, and types. It does not press **Post**.
* **Queued Posts Tab**: Review your upcoming scheduled publishing queue.
* **Warm CRM Tab**: Browse your active prospect pipeline right alongside LinkedIn. Click **⚡ Copy DM** to generate a personalized outreach message tailored to the prospect's real comments and copy it to your clipboard with one click.

