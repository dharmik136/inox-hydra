# Privacy policy: Inox Hydra Bridge

**Last updated: 25 October 2026. Applies to Inox Hydra Bridge version 2.7.0.**

Inox Hydra Bridge is a browser extension that connects the LinkedIn pages you
open to Inox Hydra, a program that runs on your own computer. The extension has
no server. Neither does Inox Hydra. There is no account to create, no sign-in
to the developer, and no analytics or crash reporting of any kind.

The developer of this extension receives nothing from it. Not your posts, not
your leads, not usage statistics, not an installation count beyond what the
browser stores publish to every developer.

## In one paragraph

The extension reads the LinkedIn pages you have open in your own browser and
sends what it reads to Inox Hydra on your own computer, at
`http://127.0.0.1:8000`, which is an address that exists only inside your
machine. That is the only address the extension ever sends anything to. The
data stays in a database file on your disk, under your control, and you can
delete it by deleting the file.

## What the extension reads

### From the LinkedIn pages you open

The extension reads the LinkedIn pages you open. A history import is the one
place where it also acts on them, and it does that only after you press
"Import your history" in Setup, and only on your own posts, comments or
reactions. During that import it clicks LinkedIn's own "Show more results"
control and scrolls the page, so it can read further back than what was
already on screen, and when you asked for all three kinds it moves the tab
itself from one of your own activity pages to the next. So it does open a
page for you, during that import and nowhere else, and its click is what
makes LinkedIn's own page fetch more. The extension itself never fetches from
LinkedIn, during an import or at any other time.

It does one other thing to a LinkedIn page, in the other direction, and it is
described under LinkedIn's composer below: when you ask for a draft to be
placed in the composer, it opens the composer and types. It never posts,
comments, reacts, messages or connects.

From **other people's activity on your posts** (`content.js`): the names,
profile addresses, headlines and comment or reaction details of people who
commented on or reacted to a post, as those appear on the page, together with
which post they engaged on. This is how the leads list in Inox Hydra is built.

From **your post analytics pages** (`content.js`): the impression, reaction,
comment and repost figures LinkedIn shows you for your own posts.

From **your own profile and activity pages** (`own_pages.js`), and only yours:
your profile fields, experience, education and skills; the contact details on
your own contact-info overlay (email, phone, birthday, websites) if you open
it; the posts you wrote; the comments you left; the posts you reacted to. The
extension establishes that a profile is yours from signs only the owner of a
profile sees, or from LinkedIn itself resolving `/in/me/` to it, and then from
the profile name you confirmed in Inox Hydra. A profile that is not yours is
never read by this file.

From **LinkedIn's composer** (`content.js`): nothing is read. Text travels the
other way, when you ask Inox Hydra to place a draft you wrote into the
composer: if the composer is not already open, the extension clicks
LinkedIn's own "Start a post" control to open it, and then types your draft
into it. Nothing is posted for you; you still press LinkedIn's own Post
button.

### Only if you switch "Read LinkedIn's network responses" on

This setting is in the extension's popup and is **off when you install the
extension**. It stays off until you switch it on, and switching it off stops
the behaviour at once.

While it is on, two further things happen:

1. A script runs inside LinkedIn's own page context
   (`voyager_interceptor.js`) and wraps the page's `fetch` function so that it
   can copy the JSON of responses LinkedIn's own application has **already**
   downloaded for the page you are looking at: feed updates, profiles, creator
   analytics, social actions and comments. The figures in those responses are
   exact rather than rounded, which is the reason the option exists. The script
   never issues a request of its own and never modifies a request or a
   response.
2. The extension notes which of LinkedIn's internal data requests a page made
   (`background.js`, using `chrome.webRequest.onCompleted`): the address, the
   HTTP status and the method. **Not the contents.** This log is what Inox
   Hydra uses to tell you when LinkedIn has changed something and a reading has
   stopped working.

While the setting is off, the first script is not registered in your browser at
all, and Inox Hydra refuses the two data paths that feed from it.

Wrapping the page's `fetch` function is something LinkedIn may regard as
automation. That is written beside the switch in the extension, in those words,
before you turn it on.

### Cookies

The extension reads cookies through the browser's cookies API in exactly two
situations.

**The local token, every time it talks to Inox Hydra.** Inox Hydra issues an
`inox_studio_token` cookie to `127.0.0.1` and `localhost` so that only a
browser you have paired can reach your own data. The extension reads that
cookie and sends it back as a request header. It never leaves your machine.

**Your LinkedIn session, only when you press "Sync LinkedIn Session".** When
you press that button in the popup, and at no other time, the extension reads
your `li_at` and `JSESSIONID` cookies for linkedin.com and stores them in Inox
Hydra on your computer. They are used for one feature: handing a finished post
to LinkedIn's own scheduler ("Send to LinkedIn"). Nothing that reads LinkedIn
needs them, because reading is done on the pages you open. Inox Hydra's Setup
screen shows whether a session is held and has a control to delete it. There is
no timer: an earlier version copied the session every fifteen minutes, and that
was removed.

The extension also keeps a short one-way digest of your `li_at` cookie (a
truncated SHA-256 hash, never the cookie itself) so that it can notice when you
sign out or sign in as somebody else and stop filing readings under the
previous account.

## What is stored, and where

**In the browser**, under the extension's own storage: whether network reading
is on; the profile name of the LinkedIn account this browser is signed in to;
that member's LinkedIn id; the cookie digest described above; and the captures
Inox Hydra did not take, so that your own activity is not lost. A capture is
held when Inox Hydra is not running, when its database is busy and it asks to
be tried again, and when it refuses this browser because the browser has not
been paired with it yet. Those held captures contain the same engagement
details described above, including the name, profile address, headline and
comment of a person who engaged with your post. They are sent to Inox Hydra on
this computer at the next successful contact and then removed, at most 200 are
held, the oldest going first, and removing the extension removes all of it. Inox
Hydra's Today screen says how many are waiting, once the extension has
reported.

**On your computer**, in Inox Hydra's own folder (its location is shown in the
app, and is set by `INOX_HYDRA_HOME`): a SQLite database file holding
your posts, drafts, queue, post readings, leads and their engagement, your
comments and reactions, any connections you imported from your own LinkedIn
data archive, daily analytics, logs and settings; your media files; the network
readings log, as a separate file; and the daily backups folder.

If you import LinkedIn's analytics export, the .xlsx file LinkedIn writes when
you press Export on your analytics page, Inox Hydra reads it on your computer
and keeps the figures it recognises in that database, each marked as read from
LinkedIn's export. A copy you chose by hand is kept only until it is imported
or set aside, or for a day, and nothing in the file is sent anywhere.

If you keep more than one creator profile, each profile is a separate folder
with its own database, under `profiles/` inside that same folder, and nothing
of one profile's data is in another's. The vault key, the logs and the browser
profiles belong to the machine and are held once, outside them.

**These database files are not encrypted.** Keep your operating system's disk
encryption on. Anyone with access to your user account on this computer can
read them.

**How long it is kept, and how to remove it.** Inox Hydra's "Storage and
privacy" panel shows how much space each kind of data takes, lets you set
retention for post readings, reactions and the network readings log, lets you
review and forget people who have gone quiet, and lets you compact the database
so that removed rows no longer occupy the file. Forgetting a person removes
their lead record, every engagement of theirs the studio read, their stage
history and any enrichment. If you also imported your LinkedIn connections,
their row there is separate and stays until you remove it; so does a record of
your own commenting or reacting on their posts. Everything is on your disk, so
you can also simply delete the folder. There is nothing of yours anywhere else
to request or to delete.

## Third parties

In its default configuration, the extension contacts nobody. Every outbound
destination below is reached by Inox Hydra on your computer, not by the
extension, and only at the moment you use the feature that needs it.

| Destination | When it is reached |
| --- | --- |
| `www.linkedin.com` | Checking your stored session is still valid, syncing your profile, and "Send to LinkedIn", which hands a post you wrote to LinkedIn's own scheduler. Off by default, the same as update checking below: nothing reaches LinkedIn until you set `INOX_ALLOW_LINKEDIN_EGRESS=1`, and the first time you use Send to LinkedIn for a given creator profile, it also asks you to acknowledge, separately from the per-send confirmation, that this writes to LinkedIn's private scheduling API, outside its published terms. It is asked once for each creator profile rather than once for the machine, because each profile is a different LinkedIn account and the account that carries the risk is the one that answers for it. Send to LinkedIn, and the session sync it needs, are available for the first creator profile only: a second or later profile's session is refused and never stored, because each profile's session must come from that creator's own browser on that creator's own machine, and Inox Hydra cannot tell whose browser a session came from. |
| `api.openai.com`, `api.anthropic.com`, `api.groq.com`, `generativelanguage.googleapis.com` | Drafting and rewriting help, if you entered your own API key for that provider. Your prompt and the text you are working on go to the provider you chose, under your own account with them, governed by their terms, not ours. |
| `image.pollinations.ai` | Generating an image, if the image provider is left at its default. This is a free public service run by a third party, and it is the default, so the first time you press Generate without having chosen a provider, your image prompt goes there. Choose another provider, a local one, or Off in the Prompt tab if you would rather it did not. |
| `api.stability.ai`, `api.replicate.com`, `fal.run`, `api.together.xyz` | Generating an image, if you chose that provider and entered your own key. |
| A local image generator (AUTOMATIC1111, Forge or ComfyUI) or a local model through Ollama | If you chose it. These stay on your machine or your network. |
| A program you connected as a grounding source (MCP) | Only if you add one yourself in Brand Studio. The studio starts that program and reads what it hands back, which you can preview; no writing control in the studio draws on it yet. What that program itself does on the network is its own, outside the studio's view, and `INOX_NO_EGRESS` cannot stop it. |
| `github.com`, `raw.githubusercontent.com` | Checking whether a newer version has been released, and fetching the template bundle. Update checking is off by default, and nothing in the interface turns it on: you enable it yourself from the command line (`python -m studio.cli update enable`). |
| `api.telegram.org` | An optional inbound bridge, inactive unless you set up a bot of your own under Your phone, through Telegram in Brand Studio's Local security tab, or set a `TELEGRAM_BOT_TOKEN` yourself. While it is set up, Inox Hydra asks Telegram for the messages you sent your own bot and sends Telegram nothing but that request. Text you send becomes a draft; a LinkedIn post link becomes a reminder on Today to open that post's analytics at this computer, and the phone's message is never stored as a figure. Your messages pass through Telegram's servers. The bot token is sealed on your disk like an AI key. |

If you configure an AI or image provider, that provider's own privacy policy
governs what it does with what you send it. We do not see it, do not proxy it,
and hold no key of yours anywhere but on your own disk.

## What we do not do

- We do not sell or transfer your data to anyone. There is no recipient: the
  data does not reach us.
- We do not use or transfer your data for any purpose unrelated to the
  extension's single purpose.
- We do not use or transfer your data to determine creditworthiness or for
  lending purposes.
- We do not serve advertising, build advertising profiles, or include any
  third-party tracker, analytics library or tag.
- We do not load or execute any code fetched at runtime. Everything the
  extension runs is in the uploaded package.

## Children

Inox Hydra Bridge is a tool for people who use LinkedIn professionally and is
not directed at children.

## Changes to this policy

If what the extension reads or where anything is sent changes, this page is
updated and the "Last updated" date above changes with it. The version of the
extension a change applies to is named.

## Contact

Questions about this policy, or about anything described on this page, can be
sent to the address published on the extension's store listing.
