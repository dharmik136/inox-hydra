# First Run

> **Status:** specification, 2026-09-21. Item 1 of section 9 is DONE (commit
> `b2c8579`). Everything else is unimplemented.

## Why this document exists

The studio used to open onto fabricated data, so nobody ever had to look at what
a new person actually sees. Removing that data made the empty state visible for
the first time, and it is not designed.

Four audits of a genuinely fresh install produced this. Claims about current
behaviour carry a file and line.

## Verified by execution, not by reading

- **`--load-extension` no longer works on Chrome.** Tested directly against
  Chrome 153 with a temporary profile, headless and headful, looking for the
  bridge's `background.js` service worker in the debugging targets. It never
  appears; only Chrome's own component extensions load. Under an identical
  probe, **Edge 153 and Brave 153 both load it**. So the desktop shortcuts from
  `browser_launcher.py` open Chrome with no bridge attached and report success
  anyway (`browser_launcher.py:271-278`). Onboarding has to branch by browser.

- **Two database backups holding 225 real people were committed.**
  `.gitignore:69` covers `studio/data/*.db`, one level deep, so backups written
  to `studio/data/backups/` fell outside it. 166 real profile URLs, 662 comment
  texts, and the session vault. Removed from history, ignore rule fixed, nothing
  had been pushed. Fixed in `b2c8579`.

- **The live database is still in pushed history.** Commit `2cc6582`, the
  initial release, carries `studio/data/linkedin_studio.db` with 17 real profile
  URLs. It was untracked later in `60b5144`, but the blob remains reachable.
  This one is already on the remote, so removing it means rewriting published
  history and is a decision for the repository owner, not a routine fix.

- **Five fabricated posts are attributed to real, identifiable people.**
  `database.py:1908-1956` puts invented engagement counts against Dan Koe
  (4,200), Sahil Bloom (8,500), Garry Tan (12,400), Shreyas Doshi (9,400) and
  Alex Hormozi (15,300). This is a different and worse category than the
  analytics that were purged: those invented the user's own numbers, these
  invent other people's.

- **"air-gapped ... zero cloud data egress"** (`README.md:3`) while
  `index.html:7-9` and `styles.css:9` fetch three font families from Google on
  every launch, carrying the user's IP.

- **Nothing publishes.** `scheduler.py:374` flips a database row and
  `app.js:4222` toasts "Post published immediately!". The only real publish path
  is refused by `egress_guard`. A user schedules for 5:30pm, is told it went
  live, and it did not.

---

# Inox Hydra: First-Run Specification

Status: design spec, ready for implementation. Every claim about current behaviour is cited to a file and line I read. No file was modified.

---

## 1. The problem in one paragraph

A new person double-clicks `InoxHydra.bat`, which probes port 8000 with a bare TCP connect and treats any listener as its own backend (`launch_studio.bat:26-28`, `tools/build_portable.py:67-71`), waits three or four seconds, opens Chrome, prints `[*] Desktop session established.` and exits 0 whether or not uvicorn ever started (`launch_studio.bat:31-48`). If it did start, the studio opens on the Composer tab, hardcoded active in markup (`studio/frontend/index.html:227`), and the person meets another creator's product. The sidebar says `37` swipe items and `WARM` leads (`index.html:247`, `index.html:241`), the topbar says `POST / DRAFT 07` and `Pipeline: 23 Leads` (`index.html:288`, `index.html:321`), and an empty text box scores `94` on an "Algorithm Reach Score" gauge because no initial render pass ever runs (`index.html:1571`, `app.js:48-77`). The settings form is pre-filled with `Dharmik Shingala`, `AI Systems Engineer & Full-Stack Architect`, `Enterprise Labs` (`index.html:1022,1027,1032`), the API returns the same as defaults (`app.py:1554-1566`), `saveCreatorProfile` writes them back if the user clears the fields (`app.js:5485-5488`), and `carousel_generator.py:262` draws `"Dharmik Shingala - Personal LinkedIn Studio"` into every exported slide with no parameter to override it. Sixteen of the author's launch drafts seed unconditionally from two call sites (`database.py:361-367` inside `init_db`, `database.py:1689-1704` inside `seed_initial_data`, both invoked at `app.py:174-175`), each writing a draft and a `status='scheduled'` post (`database.py:420-436`), and the extension side panel loads the first of them into the textarea one click from the real LinkedIn composer (`sidepanel.js:13-21`, ordering from `app.py:576`). Four sample leads including one at `Meeting Booked` seed from two places (`database.py:1708-1719` and `database.py:1966-1978`), five fabricated posts are attributed to five real named people with invented engagement counts (`database.py:1908-1956`), and two 3.3MB pre-purge databases holding 225 real people ship in every `git clone` because `.gitignore:69` covers `studio/data/*.db` but not `studio/data/backups/`. Nothing in the codebase knows a first run from a thousandth: `DOMContentLoaded` fires twenty init and load calls with no branch (`app.js:48-77`), and the lifespan computes nothing about install state (`app.py:173-182`). The extension is never mentioned in either README install path (`README.md:87-110`) and appears exactly once in the entire UI, inside a table placeholder (`app.js:4712`), while four working browser-bridge endpoints that would install it sit unreachable (`app.py:1278-1311`).

---

## 2. The setup ladder

The ordering below is the real dependency chain. Rungs 1 to 4 are required. Everything from rung 5 down is optional, and the product must say so out loud rather than presenting an unfinished chain as a broken one.

| # | Rung | Required? | What it is | Why it is needed | What the product shows when missing | How the product helps |
|---|------|-----------|------------|------------------|-------------------------------------|-----------------------|
| 1 | Runtime | Yes | CPython, embedded in the ZIP or installed by the user | Nothing runs without it | Launcher window stays open and prints: `Python was not found. Use the no-Python download instead: <releases URL>` | Launcher checks `python -V` before starting uvicorn and refuses to open a browser on failure |
| 2 | Backend answering on 127.0.0.1:8000 | Yes | uvicorn serving `studio.backend.app:app` | Every screen and every extension call targets this one origin | Launcher prints the uvicorn tail it captured and does not open a browser | Launcher probes `GET /api/v1/schema/status` (`app.py:2421`) and checks `app_version`, not a TCP connect |
| 3 | The studio page loaded | Yes | `http://127.0.0.1:8000` in any browser | The UI | n/a | Launcher opens it only after rung 2 verified |
| 4 | Identity | Yes | Display name and handle | Watermarks, carousel footers and both feed simulators render a name. Today that name is the author's | Watermark and simulator render the literal text `Your name` until set. Carousel export is blocked with: `Add your name in Settings before exporting. Slides carry a footer.` | A single Settings field pair, reachable from the connection panel row |
| 5 | Extension loaded in a browser profile | No | The MV3 bridge (`studio/extension/manifest.json`) | Gates every capture path: engagers, analytics, injection, URN binding | Connection panel: `Browser add-on: never seen.` with an `Install it` action | `/api/v1/browser/copy-path` (`app.py:1309`) plus a four-step walkthrough. See section 9 item 5 on why `--load-extension` is not the headline |
| 6 | Signed into LinkedIn in that same profile | No | A live LinkedIn web session in the profile that holds the extension | Capture reads pages the creator opens. If they are signed out, the pages have nothing on them | `Browser add-on is loaded, but that browser is not signed into LinkedIn.` | Explains the most silent failure in the product: extension loaded on profile A, LinkedIn open on profile B |
| 7 | A draft injected into the composer | No | `Insert into LinkedIn Composer` (`sidepanel.js:82-100`), which fingerprints the text (`app.py:2098-2110`) | The fingerprint is the only thing a later URN can bind to. `bind-urn` matches `WHERE activity_urn IS NULL AND content_fingerprint IS NOT NULL` (`app.py:2155-2157`) | `No post is waiting to be linked.` | The side panel |
| 8 | The user actually posts it | No | A human clicking Post on LinkedIn | Nothing in this product can post. `scheduler.py:374` only flips a database row, and the real path is refused by `egress_guard` | Post sits as `Ready to post`, not `Published`. See section 7 item 9 | Reminder opens the composer with the text on the clipboard |
| 9 | The permalink opened once | No | Visiting the published post's own URL | `maybeBindPostUrn` runs there and attaches the URN (`content.js:354-376`) | `Posted, not yet linked. Open it on LinkedIn once.` | A row action that opens the URL. Note `lastBoundUrn` latches per URN (`content.js:344,360`), so a retry needs a real navigation |
| 10 | Engagers captured | No | Opening the reactor or commenter list on that post | Fills the CRM (`content.js:548-600`) | CRM empty state, section 5 | The panel names the exact page to open |
| 11 | Analytics captured | No | Opening the creator's own LinkedIn analytics page | The only source of impressions (`content.js:131-146`) | Analytics deferred, section 8 | Stated with the no-backfill fact |
| 12 | AI provider key | No | BYO key via CLI | Better hooks and rewrites | `Using local rules. Connect your own AI key for model-written variants.` | Link to the CLI command |
| 13 | Telegram ingress | No | `TELEGRAM_BOT_TOKEN` **and** `TELEGRAM_CHAT_ID` in the environment | Starts the ingress worker, which accepts messages only from that chat id | `Telegram ingress off. Both variables are read once at launch, so set them and restart.` | Stated explicitly, because `app.py` reads them only at process start. The chat id is not optional: without it the daemon refuses every message, because a bot username is not a secret and Telegram lists bots in search, so any stranger who found the bot could otherwise put text into your drafts |

Dependency notes an implementer must not get wrong:

- 5 does not depend on 4, and 4 does not depend on 5. They are independent and can be satisfied in either order.
- 6 depends on 5 only in the sense that the evidence for 6 comes from the extension. A user can be signed into LinkedIn with no extension; the product simply cannot know it, and must not claim to.
- 9 depends on 7 for a match, and on 8 for the URN to exist at all. Opening a permalink with nothing armed is a no-op, not an error.
- 10 and 11 both depend on 5 and 6, not on 7, 8 or 9. Engagers scraped without a bound URN still land, they just carry no attribution.
- A stored `li_at` gates nothing in a default install. `save_tokens` no longer contacts LinkedIn (`app.py:1477-1489`), and outbound calls are refused by `egress_guard`. Say so: the token's presence is used as evidence of rung 6, not as a capability.

---

## 3. The connection panel

One surface, always visible, docked under the topbar on every tab. Not a modal, not a wizard, not dismissible on day 1. Collapsible to a single summary line once rungs 1 to 4 are green, and it stays collapsible forever after.

Rules:
- Every row states a fact with an age, never a colour alone. `Last heard from 40 seconds ago` is a fact; a green dot is a claim.
- Rows 3 through 5 are labelled `Optional` in the markup, and the panel header carries one line: `The studio works fully without the rows marked optional. They add capture from LinkedIn.`
- No row is ever green before it has been checked. `popup.html:127` currently ships `<strong id="server-status" style="color: #34d399;">Online</strong>` as static markup, and `checkServerAndSession` only overwrites it inside `if (res.ok)` or the catch (`popup.js:70-94`). Both the popup and the panel must ship the word `Checking` and nothing else.

### Rows

| Row | States | How checked | Action button |
|---|---|---|---|
| **Studio** | `Running, version 2.5.2, schema v<n> current` / `Schema behind, migration pending` / `Schema newer than this build` | `GET /api/v1/schema/status` (`app.py:2421-2440`), on load and every 60s | `Run migration` when pending |
| **Your name** | `Set to <name>` / `Not set yet` | `GET /api/settings/profile` returning an explicit `is_set` boolean, not a default-filled object | `Set it` opens Settings, focuses the name field |
| **Browser add-on** (optional) | `Last heard from 40 seconds ago, version 2.5.2` / `Last heard from 3 days ago` / `Never seen` / `Version 2.5.1 does not match studio 2.5.2` | `GET /api/v1/bridge/status`, polled every 30s | `Install it` opens the install walkthrough |
| **LinkedIn tabs** (optional) | `Content script last reported from a LinkedIn tab 6 minutes ago, signed in` / `...signed out` / `Add-on is loaded but has not been on a LinkedIn page yet` | Same endpoint, separate timestamp and `li_at_present` flag | `Open LinkedIn` |
| **Posts linked** (optional) | `2 of 3 posts linked to LinkedIn activity` / `Nothing waiting to be linked` | `SELECT COUNT(*) FROM posts WHERE content_fingerprint IS NOT NULL` and `... AND activity_urn IS NOT NULL` | `Show unlinked` filters the queue |

Two optional rows behind a `More` disclosure, because they are per-user and not part of the chain: AI provider (`Using local rules` / `<provider> configured`) and Telegram ingress (`Off. Read once at launch, so set the variable and restart.`).

### The extension heartbeat, minimum version

None exists today. I read every extension file and grepped the backend: all traffic is one-way work product (`background.js:71` cookies, `background.js:106` telemetry, `content.js:565` leads, `content.js:362` URN binds), nothing carries a version or an identity, and nothing is stored as a last-seen. `TelemetryEngine.get_status()` returns only totals and file size (`studio/core/telemetry_shard.py:201-208`), so even the inference "a browser contacted us recently" cannot be made.

Minimum implementation, roughly forty lines, needing no new permissions. `alarms`, `storage` and `http://127.0.0.1:8000/*` are already granted (`manifest.json:11-25`).

**`POST /api/v1/bridge/hello`**

| Field | Type | Source | Notes |
|---|---|---|---|
| `role` | `"worker"` or `"content"` | caller | The two links are proved separately. A worker can be alive while no content script has ever run |
| `extension_version` | string | `chrome.runtime.getManifest().version` | Compared to `studio.__version__` |
| `extension_id` | string | `chrome.runtime.id` | Distinguishes two profiles both running the bridge |
| `li_at_present` | boolean | worker only, from the existing `getCookie("li_at")` call | **Never the value.** Presence only |
| `on_linkedin` | boolean | content only, `location.hostname` check | |

Called from: `chrome.runtime.onInstalled`, `chrome.runtime.onStartup`, and the existing `studio_periodic_sync` alarm (`background.js:51-62`), plus once from `content.js` at `document_idle`.

Backend stores five settings keys: `bridge_last_seen_worker`, `bridge_last_seen_content`, `bridge_extension_version`, `bridge_extension_id`, `bridge_li_at_present`. Nothing else. No new table.

**`GET /api/v1/bridge/status`** returns `seconds_since_worker`, `seconds_since_content`, `extension_version`, `studio_version`, `version_match`, `li_at_present`, and `ever_seen`. Null timestamps mean never seen, which is the honest representation of an extension Chrome quietly disabled. A boolean cannot express that.

Reduce the alarm from 15 minutes to 5 (`background.js:54`). A 15-minute silence window means a user who loads the extension before starting the backend waits a quarter hour for a signal no surface currently shows at all.

---

## 4. The first session, minute by minute

**The first win: the user pastes a draft they already had, watches the mobile fold line move as they edit, takes a stronger opening line, and exports a clean image. No login, no extension, no key, no permission prompt.**

That win is achievable on an empty database because nothing in it reads a row. `formatters.py` imports `re` and `math` and nothing else. The hook rewriter and the five-style repurposer have documented deterministic fallbacks (`repurposer.py:235-238,464-468`). The feed simulator is in-memory. The carousel and quote renderers are local PIL. The only inputs are the user's text and their name, which is rung 4.

| Time | What happens |
|---|---|
| 0:00 | Double-click. Launcher prints what it is doing. It probes `GET /api/v1/schema/status` and checks `app_version`, so a foreign process on 8000 produces `Something else is using port 8000. Close it and run this again.` rather than opening a stranger's web page |
| 0:05 | Backend up. Launcher confirms the version it got back matches the build, then opens the browser. If uvicorn failed, the console stays open with the captured tail and no browser opens |
| 0:10 | Studio loads on Composer. Connection panel shows `Studio: running` and `Your name: not set yet`. Sidebar badges are empty, not `37` and `WARM`. Topbar slug is empty, not `DRAFT 07`. The gauge shows an em dash under `Not scored yet` |
| 0:20 | One line above the editor: `Paste something you were going to post. Nothing leaves this computer.` The cursor is in the editor. Nothing else asks for anything |
| 0:40 | They paste. Six local checks run for the first time. The simulator draws the ~140 character mobile cut line. The gauge now shows a real number against real text |
| 2:00 | They move a sentence above the fold and watch the cut line move. This is the moment the product earns the session |
| 3:00 | They click `Rewrite the opener`. Ten deterministic archetypes, no key needed. They take one |
| 5:00 | They export a carousel or quote image. Because rung 4 is not satisfied, export asks once: `Add your name. Slides carry a footer with it.` One field, one save, export proceeds with their name, not the author's |
| 6:00 | Session can end here and the product was useful. The connection panel is still sitting there stating that three optional rows exist. It has not nagged once |
| Later, after they mark a post as posted | One sentence appears on that post's row: `Want to see who engaged with this? That needs a browser add-on that reads your post page while you look at it. It never posts, follows or messages, and it only reads pages you open yourself.` That is the first and only mention of the extension in the flow |

The extension request is deliberately placed after a payoff. `GETTING_STARTED.md:42-49` currently makes it step 2, before any value has been delivered, and the manifest asks for `cookies`, `webRequest`, `scripting` and `tabs` (`manifest.json:11-19`), which produces Chrome's maximally alarming warning. Nobody grants that to a tool that has not done anything for them yet.

---

## 5. Empty state copy

Real copy. Short lines. The vocabulary already exists in two places and is correct there: `app.js:3087` and `app.js:4618`, on a `.table-empty` class whose CSS comment states the rule, "an absence should read as an absence, not as an error the creator caused" (`styles.css:5705-5722`).

| Screen | What it shows at zero | The one action that fills it |
|---|---|---|
| Composer gauge (`index.html:1569-1571`) | Gauge number is an em dash, arc at zero. Label: `Not scored yet` | Type something |
| Composer checks (six badges) | One line replaces all six: `Six formatting checks run as you type. Nothing to check yet.` | Type something |
| Composer dwell (`index.html:514,1695`) | `–` in place of `0.0s [OPTIMAL]` and `~26 sec` | Type something |
| Carousel stage (`app.js:526-549`) | One blank slide: `Your slides build themselves from the paragraphs in your draft.` / `Write two or more paragraphs to see the deck.` | Write two paragraphs |
| Queue slot matrix (`app.js:4290`) | Slot cards with day, time and label. No multiplier badge at all | n/a, these are default times, not measurements |
| Queue, nothing scheduled | `Nothing scheduled. Your first draft can go in any of these windows.` | Schedule a draft |
| Queue cadence health (`app.js:4118-4131`) | `–` with subline `Health appears once you have two or more posts scheduled.` | Schedule two posts |
| CRM funnel bar (`index.html:677-681`) | Bar hidden entirely. In its place: `No pipeline yet. People appear here when the studio reads the comments or reactions on one of your posts.` | Open your own post's commenter list with the add-on running |
| CRM stream (`app.js:3087`) | Keep as is. It already reads correctly | |
| Analytics chart (`app.js:4345`) | Draw the frame and axes, then centre: `No impressions recorded yet.` / `The studio charts a day once it has captured metrics for it.` Never return before painting | Open your own LinkedIn analytics page with the add-on running |
| Analytics KPI strip (`app.js:4321-4329`) | Keep the dash. It is already right | |
| Analytics observation cards (`index.html:872,878`; `app.js:4580-4594`) | All three collapse to one line: `Nothing measured yet. Observations appear when there are at least two days to compare.` | Capture two days |
| Analytics posts table (`app.js:4618`) | Keep as is. It already reads correctly | |
| Swipe file cards (`app.js:3634-3635`) | Archetype label only. No `9.0 Vel`, no `2.5x` | n/a, these are hand-written starters |
| Image studio watermark field (`index.html:2378`) | Placeholder `@yourhandle`, empty value | Set your handle in Settings |
| Sidebar badges (`index.html:235,241,247`) | Empty. A zero count renders nothing, not `0` | Data arrives |
| Topbar slug (`index.html:288`) | Empty until a draft has a title | Name a draft |
| Topbar CRM pill (`index.html:321`) | `Pipeline: –` | Capture a lead |
| Live Stream beacon (`index.html:289`, `app.js:5565,5628-5632`) | Retitled `Add-on`. Reads `Not connected` until `/api/v1/bridge/status` reports a worker. It must stop turning green on a localhost SSE open | Install the add-on |

---

## 6. The identity problem

The product must learn a display name, a headline, a company and a watermark handle. It currently ships the author's in eleven places, and fixing `app.py:1554-1566` alone fixes none of the visible ones, because the static `value=` attributes win before any fetch resolves (`index.html:1022,1027,1032,1066`).

**Default: manual, one field pair, asked at the moment it is needed.**

Why manual is the default:
1. It is available at minute zero. Passive read requires rungs 5 and 6, which the first session deliberately does not ask for.
2. The identity is needed for the very first export, which is minute five of the writing-only session.
3. A name is two seconds of typing. Nothing about it justifies a permission grant.
4. Passive read gives a name and headline from the DOM of a page the creator opened. It cannot give a watermark handle, which is a brand choice, not a fact about their profile.

The ask is not a form up front. It is a blocking prompt on the first operation that renders a name: carousel export, quote export, image studio watermark, or the feed simulator's author row. One prompt, two fields (`Your name`, `Your handle`), a Save, and the operation continues. Headline and company are optional and live in Settings only.

**Passive option: offer, never adopt.** When the extension is present and the creator opens their own LinkedIn profile or feed, the content script may read the display name and headline from the page already on screen and POST them to a new `POST /api/v1/identity/suggest`. The studio stores them under `creator_profile_suggested`, never under `creator_profile`. The connection panel's identity row then reads:

> `LinkedIn shows your name as "<name>". Use it?` with `Use this` and `No, I will type it`.

Adopting a scraped identity silently would be the same class of move as the seeded data: a row that asserts something about a person which the person never entered.

**Rules for the implementation:**

| Rule | Why |
|---|---|
| `GET /api/settings/profile` returns `{"is_set": false, "profile": null}` when the settings row is absent. No default identity object | `app.py:1554-1566` currently synthesises a person |
| `index.html` ships empty `value=""` with placeholders at 1022, 1027, 1032, 1066, 1108, 1365, 1368, 1449, 1456, 1459, 1509, 1783-1785, 2378 | Static markup renders first |
| `saveCreatorProfile` sends empty strings, never `\|\| "Dharmik Shingala"` (`app.js:5485-5488`) | A cleared field currently writes the author's name into the user's database |
| `carousel_generator.py:262` takes the footer from the profile and renders nothing when unset | The one place a correct settings form still produces a wrong file |
| `image_studio.py:343`, `carousel_engine.py` and `quote_renderer.py` default arguments become `None`, not a handle | Same |
| Watermark rendering is skipped, not defaulted, when the handle is empty | An unset watermark is no watermark |

---

## 7. What to remove before shipping to anyone else

This is a correctness list. Every item is something a second user inherits that asserts something false about a person.

| # | Item | Location | Why it must go | Verify |
|---|---|---|---|---|
| 1 | Two tracked pre-purge databases, 3.3MB each, holding 225 real leads, 240 posts, 43 settings including DPAPI-wrapped `li_at` and `JSESSIONID`, and `user_vanity='dharmik-shingala'` | `studio/data/backups/linkedin_studio_before_full_purge_20260921_184823.db`, `..._before_seed_purge_20260921_184438.db`. `.gitignore:69` covers `studio/data/*.db` but not `studio/data/backups/` | A `git clone` per `README.md:103` delivers 225 real people's names and profile URLs in plaintext. They are also valid inputs to `python -m studio.cli restore` (`cli.py:119-145`), so a user following the support docs can load the author's CRM into their own | `git ls-files studio/data` returns only `.gitkeep`. Add `studio/data/backups/` to `.gitignore`. Purge from history, not just from HEAD |
| 2 | Sixteen launch drafts, each writing one `drafts` row and one `posts` row with `status='scheduled'` | `database.py:361-367` (days 02-08, inside `init_db`) **and** `database.py:1689-1704` (days 02-17, inside `seed_initial_data`). Both run at `app.py:174-175`. Body text at `database.py:398-436` | A fresh install opens with 16 drafts and 16 scheduled posts in the author's first person about a campaign the user is not running. Both call sites must be removed; deleting one leaves the other | Fresh DB: `SELECT COUNT(*) FROM drafts` and `FROM posts` both return 0 |
| 3 | Per-seed existence guards | e.g. `database.py:394-396`, `SELECT id FROM drafts WHERE title LIKE '%The Fallacy of Heavy Web Scraping%'` | Guarding on "does this row exist" means a user who deletes it gets it back on next launch | Delete a row, restart, it stays deleted |
| 4 | Four sample leads, including Elena Rostova at `Meeting Booked` | `database.py:1708-1719` **and** `database.py:1966-1978`. Both guarded only by `SELECT COUNT(*) FROM leads == 0` | `Meeting Booked` now registers as a real conversion since the funnel was repaired. The `COUNT == 0` guard also means a user who empties their CRM gets four strangers back | Empty the leads table, restart, it stays empty |
| 5 | Sample lead enrichment tied to those leads | `database.py:1981-1990` | Orphan rows describing invented people | |
| 6 | Five fabricated posts attributed to Dan Koe, Sahil Bloom, Garry Tan, Shreyas Doshi and Alex Hormozi, with invented engagement counts including 12,400 likes on a Garry Tan post that does not exist | `database.py:1908-1956` | Worse than the analytics that were purged. Those invented the user's own numbers. These put words in identifiable third parties' mouths and attach fake metrics. Delete, do not re-attribute | `SELECT COUNT(*) FROM inspirations` returns 0 on a fresh DB |
| 7 | Hardcoded identity in markup and in the save path | `index.html:353,1022,1027,1032,1066,1108,1365,1368,1449,1456,1459,1509,1783-1785,2378`; `app.js:489-492,5485-5488`; `app.py:1554-1566`; `carousel_generator.py:262`; `image_studio.py:343` | Section 6 | Fresh install, grep the rendered DOM for `Dharmik` and `dharmik136`, expect zero hits |
| 8 | Fabricated numbers in static markup and unconditional JS | Gauge `94` and arc `stroke-dashoffset="7.16"` (`index.html:1569-1571`); `0.0s [OPTIMAL]` (`index.html:514`); `~26 sec` (`index.html:1695`); `+18%` and `74%` (`index.html:872,878`); unconditional observation text (`app.js:4580-4594`); `${slot.multiplier \|\| "2.2x"}` against a table with four columns and no multiplier (`app.js:4290`, `database.py:150-156`); `velocity_score ? ... : "9.0"` and `\|\| "2.5x"` (`app.js:3634-3635`); `23 Leads` (`index.html:321`); `POST / DRAFT 07` (`index.html:288`); `WARM` (`index.html:241`); `37` (`index.html:247`); `1` (`index.html:235`) | These are the same fabrication the database purge removed, one layer up. None of them is backed by a row | Load a fresh install, screenshot every tab, no number appears that no row produced |
| 9 | The word "publish" | `scheduler.py:374`, `app.py:704-744` | Neither touches LinkedIn. The real path is refused by `egress_guard`. A user schedules for 5:30 PM, sees `Published`, sees a toast, and nothing was posted. This is the highest-stakes untruth in the product because the user acts on it. Rename the state to `Ready to post` and the action to `Mark as posted` | No user-facing string says a post was published unless a URN was bound |
| 10 | The side panel pre-loading a scheduled post | `sidepanel.js:13-21` with ordering from `app.py:576` | Once item 2 lands there is nothing to load, but the behaviour itself is wrong: a pre-filled composer one click from `Insert into LinkedIn Composer` (`sidepanel.js:82-100`) risks publishing content the user did not write. The panel opens empty | Open the side panel on a fresh install, textarea is empty |
| 11 | Recording a post as published at injection time | `app.py:2098-2110` writes `status='published'` and `published_at=now` the moment text lands in the composer, called unconditionally from `sidepanel.js:108-114` | The user may read it back, dislike it, and close the tab. The studio then holds a published post that does not exist, counting toward totals and feeding cadence collision warnings (`scheduler.py:167-175`) against a phantom. Record it as `injected`, and promote to posted only when the user confirms or a URN binds | Inject, close the tab, the post shows as `Injected, not posted` |
| 12 | The Chrome Web Store instruction in the shipped portable README | `tools/build_portable.py:206-211` | There is no such listing. The project's own plan lists P7, the store submission, as the one unlanded phase (`docs/PACKAGING_AND_MAINTENANCE_MASTER_PLAN.md:5,193`). A buyer of the no-Python bundle follows the instructions in the box and arrives at nothing | The string is gone or the listing exists |
| 13 | `"air-gapped"` and `"zero cloud data egress"` while the page fetches Google Fonts | `README.md:3`, `index.html:7-9`, `styles.css:9` | Three connections to Google on every launch, carrying the user's IP. Self-host the three OFL families and delete the preconnects, or delete the claim. `app.py:187` repeats the claim in the OpenAPI description | Launch offline, no external request in the network tab, type renders correctly |
| 14 | `"Encrypted local SQLite"` and `"Encrypted Local Storage"` | `README.md:31,210` | No SQLCipher, no `PRAGMA key` anywhere in `database.py`. `vault.py` DPAPI-wraps exactly two values. Every draft and every lead name is readable in any SQLite viewer. The honest sentence is stronger: "your data sits in one file on your disk, protected by your operating system account, and your LinkedIn session cookie is additionally encrypted with Windows DPAPI" | |
| 15 | Five product names | `inox-hydra` / `README.md:1` / `LinkedIn Studio Enterprise \| Editorial Motion OS` (`index.html:6`) / `LinkedIn Studio` (`index.html:223`) / `LinkedIn Studio Bridge (LocalTaplio)` (`manifest.json:3-4`) | The user downloads one thing, opens another, and is asked to trust an extension named after a competitor. Pick `Inox Hydra`, put it in all four, delete the rest | |
| 16 | Launcher success on failure | `launch_studio.bat:26-48`, `tools/build_portable.py:65-89` | Section 2 rungs 1 and 2 | Rename the uvicorn entry point temporarily, run the launcher, no browser opens and the error is on screen |
| 17 | `"Successfully launched ... with LinkedIn Studio Bridge loaded"` | `browser_launcher.py:271-278` | Returned unconditionally on `Popen` success. Chrome branded builds removed `--load-extension` at 137, and the args carry no `--user-data-dir` (`browser_launcher.py:253-257`), so an already-running browser discards the switch entirely. The message is false in the majority case | The function reports what it did, not what it hopes happened |

---

## 8. Progressive disclosure

The unit is content, not time. "Day 7" means "after roughly a week of use", and the gate is a count.

| | Visible | Hidden or deferred | What unlocks the next step |
|---|---|---|---|
| **Day 1** (0 posts, 0 leads, 0 analytics rows) | Composer with the fold simulator, hook rewriter, repurposer, carousel and quote export. Queue showing the slot matrix with no multipliers. CRM with an `Add lead` button (`index.html:706`) and the funnel bar hidden. Swipe file, the one genuinely full screen. Settings. Docs. Connection panel | Analytics: shown in the rail, disabled, labelled `Analytics · after your first post` | Injecting and marking a first post as posted |
| **Day 7** (1+ posts, 1+ bound URN, 1 to 6 days of analytics) | Analytics unlocks. Chart frame drawn with axes and one to six points. KPI strip shows real captured values with dashes for what was not captured. CRM funnel bar appears once `total_leads > 0`. Queue cadence health appears at two or more scheduled | Observation cards stay collapsed to `Nothing measured yet. Observations appear when there are at least two days to compare.` Trend deltas stay hidden | A second day of captured analytics |
| **Day 30** (7+ days captured, 10+ leads) | Everything. Deltas computed against real prior periods. Observations rendered only where a delta actually exists. Funnel widths from real statuses | Nothing | |

Do not hide Queue or CRM on day 1. Both have a real day-one action, and a hidden tab teaches the user the product is smaller than it is. Analytics is the only tab where every element is a measurement, which is why it is the only one deferred.

State the no-backfill fact once, on the Analytics unlock screen: `The studio only records what it sees. Anything before you installed it is not available, so these charts start from today.` A user who sees an empty 90-day chart and is not told this will assume it is broken.

---

## 9. The sequence

Ordered by dependency. Items 1 through 4 are the correctness gate and must land before anyone else installs this.

| # | Item | Depends on | Files | How you know it worked |
|---|---|---|---|---|
| 1 | Remove the tracked backup databases and history | none | `.gitignore`, `studio/data/backups/` | `git ls-files studio/data` returns `.gitkeep` only. Fresh clone contains no `.db` |
| 2 | Remove all seeding that asserts something about a person | none | `database.py:361-367`, `1689-1704`, `1708-1719`, `1966-1978`, `1981-1990`, `1908-1956`, and the sixteen `seed_dayNN_draft` functions at `386-1400` | Fresh DB: drafts 0, posts 0, leads 0, lead_enrichments 0, inspirations 0, queue_slots 11, hook templates 36. Delete a lead, restart, it stays deleted |
| 3 | Identity: unset by default everywhere | 2 | `app.py:1554-1566`, `index.html` (13 sites listed in section 7 item 7), `app.js:489-492,5485-5488`, `carousel_generator.py:262`, `image_studio.py:343`, `carousel_engine.py`, `quote_renderer.py` | Fresh install, grep the live DOM and an exported carousel PNG for `Dharmik` and `dharmik136`. Zero hits. Clear the name field, save, reopen, still empty |
| 4 | Stop fabricating in the UI layer | 2 | `index.html:235,241,247,288,321,353,514,872,878,1569-1571,1695`; `app.js:3011,3634-3635,4118-4131,4290,4345,4580-4594` | Fresh install, walk every tab, no number on screen that no row produced. Analytics chart paints a frame with a sentence in it, not a blank rectangle |
| 5 | Launcher honesty | none | `launch_studio.bat:26-48`, `tools/build_portable.py:65-89` | Break uvicorn, run the launcher: error visible, no browser. Start a Django server on 8000, run the launcher: `Something else is using port 8000`, no browser |
| 6 | Extension heartbeat | none | New `POST /api/v1/bridge/hello` and `GET /api/v1/bridge/status` in `app.py`; `background.js:51-62`; `content.js` at `document_idle` | Load the extension, `GET /api/v1/bridge/status` reports a worker within 5s. Disable the extension, the timestamp ages. Open a LinkedIn tab, the content timestamp appears separately |
| 7 | Connection panel | 3, 6 | New markup in `index.html` under the topbar, new module in `app.js`, retire `updateLiveStreamBadge` SSE wiring (`app.js:5565,5628-5632`) | Every row reads `Checking` before its first result. Kill the extension, row 3 ages instead of flipping to red. Sign out of LinkedIn, row 4 changes |
| 8 | Extension install walkthrough | 6, 7 | New view in `index.html`/`app.js` calling the existing `/api/v1/browser/status`, `/copy-path`, `/create-shortcuts` (`app.py:1278-1311`) | Clicking `Install it` puts the extension path on the clipboard and shows four steps. Completing them makes row 3 report within 5s |
| 9 | Retire `--load-extension` as the headline | 8 | `browser_launcher.py:242,253-278` | `/api/v1/browser/status` reports per browser whether the switch is still honoured. Branded Chrome 137+ reports `no` and the UI routes to copy-path. `launch_browser_with_extension` no longer claims the extension loaded when it cannot verify it |
| 10 | Injection records `injected`, not `published` | none | `app.py:2098-2110`, `sidepanel.js:100-118`, `scheduler.py:374`, `app.py:704-744`, queue rendering in `app.js` | Inject and close the tab: the post reads `Injected, not posted`. Schedule a post and let the scheduler run: it reads `Ready to post`, never `Published` |
| 11 | Side panel opens empty | 2, 10 | `sidepanel.js:13-21` | Fresh install, side panel textarea is empty |
| 12 | Progressive disclosure gates | 4, 7 | `app.js:48-77` gains one `GET /api/v1/install/state` call and branches on it; new endpoint in `app.py` returning counts | Fresh install: Analytics disabled with its label. Bind one URN: Analytics unlocks with one point and a collapsed observation line |
| 13 | `doctor` learns the six live checks | 6 | `studio/backend/support.py:107-174`, `studio/cli.py:50-101` | `doctor` reports: is anything listening on 8000, is it us (version match), extension last seen, `li_at` present and its age, AI provider reachable if configured, `TELEGRAM_BOT_TOKEN` present at process start. The existing disk-state half is already correct and stays |
| 14 | Documentation | 8, 9 | `README.md:3,31,87-110,210`, `docs/GETTING_STARTED.md:42-49`, `tools/build_portable.py:206-211` | Both install paths mention the add-on and link to the in-app walkthrough. The Chrome Web Store sentence is gone. `air-gapped` and `encrypted SQLite` are either true or deleted |
| 15 | Self-host fonts | none | `index.html:7-9`, `styles.css:9` | Launch with the network disabled: type renders correctly, no outbound request |
| 16 | One name | none | `README.md:1`, `index.html:6,223`, `manifest.json:3-4` | The word `Taplio` appears nowhere in a user-facing string |

---

## 10. What not to build

| Pattern | Why it is wrong here |
|---|---|
| **A modal welcome tour** | It arrives before any value and blocks the one thing that works on an empty database, which is the editor. The first session's job is to get a cursor into a text box in under twenty seconds |
| **A step-by-step wizard that enforces order** | The ladder in section 2 is entered out of order constantly: extension before backend, permalink before injection, extension on the wrong profile. A wizard has to model every one of those as an error. A panel that states five independent facts degrades correctly and needs no state machine |
| **A checklist that nags, badges, or reappears** | Rows 3 to 5 are genuinely optional. A tool that keeps reminding you about optional steps is asserting they are not optional. State them once, let the user collapse the panel, do not resurface it |
| **A progress bar or percent-complete over setup** | `3 of 7 steps complete` fabricates a sense of incompleteness for a user who is done. Someone who only ever writes drafts locally is at 100 percent of what they want |
| **Confetti, celebration states, or gamified streaks** | The product just finished deleting fabricated engagement. Manufacturing a sense of achievement from a configuration step is the same instinct in a friendlier outfit |
| **Sample or demo data of any kind, including opt-in** | The four leads and sixteen drafts are the whole reason this document exists. A toggle does not help: the seeds run unconditionally at `app.py:174-175` before any guard, and their existence guards mean a deleted row returns. An empty product is a truthful product |
| **The existing "Guided Studio Flows" drawer as the onboarding surface** | It is hidden behind a Z-tab and `display:none`, and its header shows six green `PASS` gates before the user has typed a character (`index.html:2496-2545`). It would need to be rebuilt to be honest, at which point it is the connection panel |
| **A green connected/disconnected light** | Nothing in this system can currently justify a green light. The popup turns green because `/api/analytics/kpis` answered (`popup.js:71-76`), which tests the backend, not the bridge. `/api/auth/status` reports connected whenever two strings exist in SQLite (`linkedin_client.py:195-197`), which survives session expiry forever. Ages, not colours |
| **Auto-adopting a scraped identity** | Section 6. Offer it, never write it |
| **Any copy containing "sovereign", "air-gapped", "Editorial Motion OS", "Enterprise Reverse CRM", "asymmetric intelligence", "anti-detection shield" or "Antigravity Deterministic Local Engine" before minute ten** | These describe the implementation, not the user's outcome. Plain replacements: "runs on your computer, nothing is uploaded", "people who engaged", "openers that worked", "works without an AI key", "pre-post check", "gets cut off on mobile", "link this draft to the post you published" |