# Privacy policy: Inox Hydra Bridge

**Last updated: 28 October 2026. Applies to Inox Hydra Bridge version 2.10.1.**

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

When the extension is installed or updated, it starts its readers in the
LinkedIn tabs you already have open, as a reload of each tab would, so that
no tab has to be reloaded by hand. They read what is described here and
nothing more, and nothing is added to the page.

From **other people's activity on your posts** (`content.js`): the names,
profile addresses, headlines and comment or reaction details of people who
commented on or reacted to a post, as those appear on the page, together with
which post they engaged on. This is how the leads list in Inox Hydra is built.

From **your post analytics pages** (`own_pages.js`), for your own recorded
posts only: the figures LinkedIn shows you there, which are impressions,
members reached, reactions, comments, reposts, saves and sends, and, where the
page shows them, followers gained from the post, profile viewers from the
post, link visits, article views, video views, the share of impressions from
inside and from outside your network, and the viewer demographics for the
post, which are LinkedIn's aggregate percentages (such as the share of viewers
with a job title or in a location), never names, and for a video post its
watch time and average watch time. Each reading is kept with the post's age and
the day it was read.

From **your creator analytics page** (`content.js`), for the account you
confirmed in Inox Hydra only: the figures LinkedIn shows you there over the
range the page is set to, which are impressions, members reached, reactions,
comments, reposts, saves and sends, the share of impressions from inside and
from outside your network, and on LinkedIn's earlier layout your follower
count. A reading over the past 24 hours is kept as that day; a reading over
any other range, or one whose range the page does not name, is kept as a
reading over that range on the day it was read, never as a day.

From **your own account and content analytics pages** (`own_insights.js`), and
only yours: on your analytics dashboard, your profile views and search
appearances, each with the window the page names (such as the past 90 days),
and your new followers by day from the followers graph; the profile viewer count
on "Who viewed your profile" and the count on your search appearances page,
with their windows, and never a viewer's or a searcher's name, headline or
company; and on your own articles' and newsletters' analytics pages, their
article views, impressions, members reached, reactions, comments, reposts,
subscribers, email sends and email open rate. From your own Activity tab it
also keeps that you reposted a post, when, and the repost's own figures where
they can be told apart, never the original's author, words or figures, and
when one of your posts was first seen marked edited.

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
   can copy the JSON of two kinds of response LinkedIn's own application has
   **already** downloaded for the page you are looking at: feed updates and
   your creator analytics. From a feed response Inox Hydra keeps the figures of
   your own posts only: every other post in it is dropped before anything is
   written, and only how many were dropped is recorded. From your creator
   analytics it keeps your follower count, for the account you confirmed in
   Inox Hydra. Responses about other members, such as profiles, reactions on
   posts and comments, are not copied, and Inox Hydra refuses them if they
   arrive. The figures are exact rather than rounded, which is the reason the
   option exists. The script never issues a request of its own and never
   modifies a request or a response.
2. The extension notes which of LinkedIn's internal data requests a page made
   (`background.js`, using `chrome.webRequest.onCompleted`): the address, cut
   before any part that would name a member and with any LinkedIn id in it
   blanked, the HTTP status and the method. **Not the contents.** Each LinkedIn page you
   open also counts the data requests it made, by address and query name,
   and hands the counts to the extension, which sends Inox Hydra those of the
   page you looked at last with its check-in once a minute: an address is kept
   only as words from a fixed list of the words LinkedIn's data addresses use,
   with every other part written as a blank, and a query name only in
   LinkedIn's own form, otherwise as "other". Never a query string. Inox Hydra
   keeps those counts for seven days. These records are what it uses to tell
   you when LinkedIn has changed something and a reading has stopped working.

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
that member's LinkedIn id; the cookie digest described above; a random
identifier the extension makes the first time it runs in this browser, which
says nothing about you or the browser and lets Inox Hydra tell two browsers
apart; a one-way digest (SHA-256) of each LinkedIn account your creator
profiles in Inox Hydra have confirmed, never the account's name, so that a
capture held for one of those accounts is sent as soon as it has a home; the
version number the extension found in its own files at its last look, whether
it could read them, and when; a record of the last capture, saying what kind of
thing it was, when, what Inox Hydra answered and which tab it came from, never
who; this session's count of captures per tab, for the toolbar badge; when
network reading last stored something; and, until the browser closes, the last
notice that a part of the capture could not read a page (naming the part, the
kind of page and the fields) and the last notice a LinkedIn page had for you,
in Inox Hydra's own words, which the side panel shows instead of drawing it
into LinkedIn's page; a list of the LinkedIn tabs open, each with the kind of
page it shows, whether it is in view, the version of the extension's readers it
carries and its network reading counts, and which tabs could not be given new
readers after an update; and a one-way digest (SHA-256) of each capture it
sent, never the capture itself, which it uses for ten seconds so that the same
capture read in two tabs is sent once; and the captures Inox Hydra did not take, so that
your own activity is not lost. A capture is held when Inox Hydra is
not running, when its database is busy and it asks to be tried again, and when it
refuses this browser because the browser has not been paired with it yet. A
capture is also held when it was read while this browser is signed in to a
LinkedIn account that none of your creator profiles has confirmed: Inox Hydra
writes it into no profile, and the extension keeps it, marked with that
account's profile name, until a profile confirms the account. Those held
captures contain the same engagement details described above, including the
name, profile address, headline and comment of a person who engaged with your
post. They are sent to Inox Hydra on this computer at the next successful
contact (one held for an account, once a profile has confirmed it) and then
removed, at most 200 are held, the oldest going first, and removing the
extension removes all of it. Inox Hydra's Today screen says how many are
waiting, once the extension has reported, and its Health screen says how many
are held for which account.

**On your computer**, in Inox Hydra's own folder (its location is shown in the
app, and is set by `INOX_HYDRA_HOME`): a SQLite database file holding
your posts, drafts, queue, post readings, leads and their engagement, your
comments and reactions, any connections you imported from your own LinkedIn
data archive, daily analytics, logs and settings; your media files; the network
readings log, as a separate file; and the daily backups folder.

**What you ask of it, and what it works out for you**, in that same database:
the text of the asks you make of the studio and choose to keep (the topics,
audience and things to avoid you type at Setup; an ask typed into the From
your record section; an instruction you tick "remember this ask" on in the
Composer, and only then; an idea sent from Telegram; a card you ask for more
of; and a search from your archive, only when you ticked that file at import
and it shares one of your recurring topics), nothing typed anywhere else;
the marks you put on the daily cards (keep, skip and hide, and the studio's
own used and posted marks when a draft comes from a card);
the daily batch of cards itself, one dated row per card with the rows it was
built from; a monthly note you may write about whether the cards helped; and,
only for the files you ticked at import, what your own LinkedIn archive says
you saved, followed, voted on, reposted and searched for, each row
with the file it came from and the date it was imported. Nothing removes an
ask or a mark on its own: an ask goes when you remove it on the section's
"What the studio knows" page, a keep or a hide when you take it back, and
all of them when you delete what the studio holds about you. Dated batches
are kept for the number of days you set on that page, 365 by
default, except a batch a mark or a draft still refers to. None of it is in
the diagnostics bundle or the access log, and none of it leaves this computer
unless you have entered an AI provider key and the section's model stage is
on, in which case the AI row below says exactly what goes.

If you import LinkedIn's analytics export, the .xlsx file LinkedIn writes when
you press Export on your analytics page, Inox Hydra reads it on your computer
and keeps the figures it recognises in that database, each marked as read from
LinkedIn's export: your figures by day, your recorded posts' figures, and the
demographics of your audience and of who engaged with your posts. Those
demographics are shares, such as the percentage of your audience with one job
title or in one location, kept with the last day the export covers; they name
no one, and nothing else in those sheets is kept. A copy you chose by hand is
kept only until it is imported or set aside, or for a day, and nothing in the
file is sent anywhere.

If you keep more than one creator profile, each profile is a separate folder
with its own database, under `profiles/` inside that same folder, and nothing
of one profile's data is in another's. The vault key, the logs and the browser
profiles belong to the machine and are held once, outside them. Each capture
the extension sends names the LinkedIn account its browser is signed in to,
which is your own, and Inox Hydra files it in the profile that confirmed that
account; a capture for an account no profile has confirmed is written into
none of them and stays held in the browser, as described above.

**The bridge's own record**, in the database of the creator profile that is
open, or, for a reader's run and a history import, of the profile that
confirmed the account the browser is signed in to: for each browser the extension runs in, at most one check-in a minute,
saying when, the extension's version and the version found in its files,
whether it could read them and when it looked, which browser it is (as the
browser names itself, such as Microsoft Edge or Brave), the random identifier
described above, the profile name of the LinkedIn account it is signed in to,
how many LinkedIn pages of each kind it had open, how many captures it held for
which account, how many tabs still carried an older copy of its readers, and
whether it reloads itself; with each run of a reader, which browser ran it; and
with a history import, which browser and tab ran it, so that two tabs never
both scroll. Every capture also says which tab, window and page it was read in,
and Inox Hydra keeps no more of that than is listed here. Check-ins and runs
are kept for seven days, except each reader's latest run and its latest run
that worked. Inox Hydra also
remembers, in memory only and for ten minutes, a one-way digest of each capture
it took, so that the same capture sent twice is answered "already seen" and not
written again; none of it is written to disk.

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
extension, and only at the moment you use the feature that needs it. The
daily section's model stage is such a moment: it runs when you open From your
record for the first time each day, never on a timer and never while you are
away, and only once you have entered a key.

| Destination | When it is reached |
| --- | --- |
| `www.linkedin.com` | Checking your stored session is still valid, syncing your profile, and "Send to LinkedIn", which hands a post you wrote to LinkedIn's own scheduler. Off by default, the same as update checking below: nothing reaches LinkedIn until you set `INOX_ALLOW_LINKEDIN_EGRESS=1`, and the first time you use Send to LinkedIn for a given creator profile, it also asks you to acknowledge, separately from the per-send confirmation, that this writes to LinkedIn's private scheduling API, outside its published terms. The acknowledgement is kept in that profile's own settings. Send to LinkedIn, and the session sync it needs, are available for the first creator profile only, so it is the first profile's account that answers for it: a second or later profile's session is refused and never stored, and a session an earlier version kept in one is deleted the first time this version starts, because each profile's session must come from that creator's own browser on that creator's own machine, and Inox Hydra cannot tell whose browser a session came from. |
| `api.openai.com`, `api.anthropic.com`, `api.groq.com`, `generativelanguage.googleapis.com` | Drafting and rewriting help, if you entered your own API key for that provider. Your prompt and the text you are working on go to the provider you chose, under your own account with them, governed by their terms, not ours. The From your record section's model stage, once a day when you open the section and only with a key entered, sends a redacted set of your own rows to the same provider: the first 300 characters of your own posts and their ids, the studio's own word for how each did (above usual, usual, below usual, not measured), your topic labels, the asks you kept (never a search from your archive) and your voice profile. It never sends figures, other people's names or comments, your connections or anybody's score, and a name, an address or a phone number inside your own text is replaced before it leaves. It spends at most the daily ceiling you set on the section, 10 cents by default, and the model may return only ids of rows it was sent, labels from a fixed list and short phrases; anything else, and any phrase carrying a number, is dropped before it is shown. |
| `image.pollinations.ai` | Generating an image, if the image provider is left at its default. This is a free public service run by a third party, and it is the default, so the first time you press Generate without having chosen a provider, your image prompt goes there. Choose another provider, a local one, or Off in the Prompt tab if you would rather it did not. |
| `api.stability.ai`, `api.replicate.com`, `fal.run`, `api.together.xyz` | Generating an image, if you chose that provider and entered your own key. |
| A local image generator (AUTOMATIC1111, Forge or ComfyUI) or a local model through Ollama | If you chose it. These stay on your machine or your network. |
| A program you connected as a grounding source (MCP) | Only if you add one yourself in Brand Studio. The studio starts that program and reads what it hands back, which you can preview; no writing control in the studio draws on it yet. What that program itself does on the network is its own, outside the studio's view, and `INOX_NO_EGRESS` cannot stop it. |
| `github.com`, `raw.githubusercontent.com` | Checking whether a newer version has been released, and fetching the Inox library when you press Fetch on From your record's What the studio knows page. Update checking is off by default, and nothing in the interface turns it on: you enable it yourself from the command line (`python -m studio.cli update enable`). The library is one file of forms, patterns and examples the Inox Hydra team wrote; the request for it carries nothing of yours, only its address, a name for the channel and the tag of the copy you already hold, and the file is kept only if its signature matches the key the studio ships. |
| `api.telegram.org` | An optional inbound bridge, inactive unless you set up a bot of your own under Your phone, through Telegram in Brand Studio's Local security tab, or set a `TELEGRAM_BOT_TOKEN` yourself. While it is set up, Inox Hydra asks Telegram for the messages you sent your own bot, and the bot answers each with one short fixed sentence that carries none of your words, your figures or anything about anyone else (such as "Saved as a draft in your studio."); a chat that is not paired is told how to pair, with that chat's own id. You can turn the answers off in the same panel, whose Send a test message sends one more fixed sentence to your chat. Your figures go to Telegram only if you turn on The bot may answer with your figures there: then /today answers with your latest post's figures, how many replies are waiting and when your next post is scheduled, and those figures sit on Telegram's servers like everything in the chat. Three notifications, each off until you turn it on there: that a queued post is due (a count, never its words); your latest post's figures at about 24 hours; and, with Send me a weekly summary, a weekly summary once a week at the day and hour you pick, of how many posts Inox Hydra recorded as published that week, how many drafts you saved from your phone, how many replies are waiting (a count) and when your next post is scheduled, with each of that week's posts' figures only if The bot may answer with your figures is on. They wait during quiet hours, 23:00 to 07:00 on your computer's clock unless you change or turn them off there, and go when they end. Never another person's name or comment text. Some of the bot's messages carry buttons you press in Telegram: Undo under a saved draft, which removes that draft from your studio while it is untouched there, and Remind me in an hour and Done under a due post, where Done only clears the reminder and marks nothing as posted. A press comes back to Inox Hydra through Telegram as a message does, carrying an id that names nothing and none of your words, and is answered with one more fixed sentence; the message is then edited to say what became of it. What each button does is kept in Inox Hydra's settings, for the newest 100 messages that carry buttons, and deleted with everything else. Text you send becomes a draft; a LinkedIn post link becomes a reminder on Today to open that post's analytics at this computer, and the phone's message is never stored as a figure. A short lnkd.in link, which the LinkedIn app's Copy link gives, is kept as it was sent and opened in your own browser when you press Open on Today; Inox Hydra never fetches it, and learns which post it was only from the extension, on the post's page. Until you say which chat is yours, every message is refused; Inox Hydra keeps the chats it refused in memory only, until it stops (each chat's id, how many messages, when, and the first 60 characters of the first), so that its panel can ask whether one is you, and writes only a refused chat's id to its log. Your messages pass through Telegram's servers. The bot token is sealed on your disk like an AI key. |

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
  extension runs is in the uploaded package. To notice an update, it reads its
  own manifest file from its own folder every five minutes, and when the
  version there differs from the one it runs, it reloads itself from that
  folder.

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
