# Store listing disclosures: Inox Hydra Bridge

Drafted for the coordinator to paste into the Chrome Web Store developer dashboard (and the Edge Add-ons listing, whose fields ask the same questions) at the 2.8.0 release. Written against the extension manifest at version 2.7.0 (`studio/extension/manifest.json`) on 26 October 2026, and revised for 2.10.2 on 28 October 2026, when network reading was retired and the extension stopped asking for `webRequest`; check it against the manifest that ships before pasting. If cycle 4's track 1, phase 3 moves `cookies` to an optional permission (decision D5), its justification moves to the optional permissions and the listing's permission warning changes with it.

A lawyer's read of the extension comes before the public listing (`planning/7 Roadmap/Risk - LinkedIn terms and detection.md`, mitigation 5). Nothing here is legal advice.

Why this file exists: a listing is reviewed against Chrome's Limited Use policy, which reads: "Collection and use of web browsing activity is prohibited, except to the extent required for a user-facing feature" that is "described prominently in the Product's Chrome Web Store page and in the Product's user interface" (Chrome Web Store program policies, Limited Use, "Last updated 2022-11-01", read 2026-10-26). The extension reads LinkedIn pages, which is browsing activity, so the listing has to say so prominently, and the dashboard's privacy fields have to match the privacy policy word for word in substance.

## Single purpose

> Inox Hydra Bridge brings what you see on your own LinkedIn pages into Inox Hydra, a program running on your own computer, and places drafts you wrote there into LinkedIn's composer when you press Insert. It sends nothing to anyone but that program, at 127.0.0.1:8000 on your machine.

## The prominent disclosure, for the top of the listing description

> **What this extension reads, and where it goes.** On the LinkedIn pages you open, the extension reads your own posts, profile and analytics, and the names, headlines and comments of people who engaged with your posts. It sends what it reads to Inox Hydra on your own computer, at 127.0.0.1:8000, and nowhere else: there is no server of ours and no account with us. It acts on a LinkedIn page only when you ask: during a history import you start, it presses LinkedIn's "Show more results" and scrolls your own activity pages; when you press Insert, it opens LinkedIn's composer and types your draft, and you press Post yourself. It does not wrap LinkedIn's page functions or watch LinkedIn's network requests. Your LinkedIn session is copied to Inox Hydra only when you press Sync LinkedIn Session, for one feature, Send to LinkedIn, which is off by default. LinkedIn's terms do not permit browser extensions that copy data from its pages; the studio's help quotes them, with where each feature stands.

## Where the interface says the same (Limited Use asks for both)

- The studio's Setup screen, before the first reading: "The studio reads your own LinkedIn in a browser it opens for you: your profile, your posts, and what you have liked and commented on. It all stays in the database on this machine." (`studio/ui/src/components/OnboardingSurface.tsx`)
- The studio's help article "Where each feature stands with LinkedIn's terms", which quotes LinkedIn's User Agreement and Help Center verbatim, dated, with each feature's standing beside them (`docs/help/where-each-feature-stands-with-linkedins-terms.md`).
- The privacy policy, shown in the studio's Docs and at the published address (`docs/PRIVACY_POLICY.md`).

## Permission justifications

| Permission | Justification to paste |
| --- | --- |
| `sidePanel` | The side panel shows, beside LinkedIn rather than inside its page, what the extension read from the page you are on and whether the studio on your computer took it, and lets you place a draft you wrote into LinkedIn's composer. |
| `cookies` | Every time it talks to Inox Hydra on your computer, it reads that program's own access cookie for 127.0.0.1 and localhost and sends it back as a header, so only a browser you paired can reach your data. It reads your LinkedIn li_at cookie in this browser to show in the popup whether you are signed in to LinkedIn, and watches it change so it notices a sign-out or a different account, keeping only a truncated one-way digest of it, never the cookie. Only when you press Sync LinkedIn Session does it give li_at and JSESSIONID to Inox Hydra on your computer, for the one feature Send to LinkedIn, which works in your first creator profile only. No cookie is sent anywhere but your own computer. |
| `storage` | Holds, in the extension's own storage: the LinkedIn account this browser is signed in to and its member id, the cookie digest above, a random identifier for this browser's copy of the extension, one-way digests of the accounts Inox Hydra's creator profiles have confirmed, and up to 200 captures Inox Hydra could not take yet, which are sent to it at the next contact and removed; and, until the browser closes, the LinkedIn tabs open with the kind of page each shows, and a one-way digest of each capture sent in the last ten seconds, so a capture read in two tabs is sent once. |
| `tabs` | Opens Inox Hydra's interface in a new tab from the popup and from the side panel; from the side panel, finds the LinkedIn tab you are looking at to place a draft into its composer when you press Insert; finds the LinkedIn tabs already open when the extension is installed or updated, to start its readers there; and once a minute checks which LinkedIn tabs are still open, so it can tell Inox Hydra on your computer how many LinkedIn pages of each kind are open (a count, never an address). |
| `scripting` | When the extension is installed or updated, starts its own readers in the LinkedIn tabs already open, as reloading each tab would, so no tab has to be reloaded by hand; and removes the network-reading script an earlier version registered, network reading having been retired in 2.10.2. |
| `alarms` | Three periodic alarms: one retries sending held captures to Inox Hydra on your computer, one checks in with it once a minute, and one reads the extension's own manifest every five minutes to notice an update. None contacts LinkedIn. |
| Host `https://*.linkedin.com/*` | To read the LinkedIn pages you open, and, when you press Sync LinkedIn Session, your LinkedIn session cookies. |
| Hosts `http://127.0.0.1:8000/*` and `http://localhost:8000/*` | Inox Hydra on your own computer, the only address the extension sends anything to. |

## Remote code

> No. Everything the extension runs is in the uploaded package; it loads and executes no code fetched at runtime.

## Data usage: the categories to tick

| Category | Tick | What, from the privacy policy |
| --- | --- | --- |
| Personally identifiable information | Yes | Names, profile addresses and headlines of people who engaged with your posts, as LinkedIn shows them; your own profile fields, and the contact details on your own contact-info overlay if you open it. |
| Authentication information | Yes | Inox Hydra's own access cookie, every time; your LinkedIn li_at cookie, read in the browser to show whether you are signed in and kept only as a one-way digest; your LinkedIn session cookies (li_at, JSESSIONID), given to Inox Hydra only when you press Sync LinkedIn Session. |
| Personal communications | No | Messages are never read. Comments on your posts are covered under website content. |
| Location | No | No device location. A location typed into a LinkedIn profile is profile text, under the first row. |
| Web history | Yes | Which of your own LinkedIn pages a reading came from, and which post a short link you sent from your phone landed on when you open it from Inox Hydra's Today. |
| User activity | No | No network monitoring: network reading, which noted LinkedIn's data requests, was retired in 2.10.2. No clicks, keystrokes or mouse movement are recorded. |
| Website content | Yes | Your posts, figures and analytics, and the comments and reactions on your posts, as they appear on the pages you open. |
| Health information, Financial and payment information | No | None. |

Every category above is sent only to Inox Hydra on your own computer. None reaches the developer.

## Certifications, all three ticked

- I do not sell or transfer user data to third parties, outside of the approved use cases.
- I do not use or transfer user data for purposes that are unrelated to my item's single purpose.
- I do not use or transfer user data to determine creditworthiness or for lending purposes.

The privacy policy's "What we do not do" section already makes each of these statements (`docs/PRIVACY_POLICY.md`).

## A sentence the coordinator may add to the privacy policy

The policy is the coordinator's and track 7's to edit, not this track's. A sentence many listings carry, which reviewers look for:

> The use of information received from this extension adheres to the Chrome Web Store User Data Policy, including the Limited Use requirements.

## The privacy policy address

The published page built from `docs/PRIVACY_POLICY.md` by `tools/build_privacy_page.py`, at the address the release publishes it to.
