# Changelog

What changed for someone running the studio, newest first. The master plan
asks for an entry per release (`docs/PACKAGING_AND_MAINTENANCE_MASTER_PLAN.md`
section 5.5); this file starts with the work since v2.5.2, which was never
released. Version numbers follow `studio/__version__.py`.

## 2.13.0

The Telegram bot does more from your phone: it lists its commands, sends you a
whole post to copy into the LinkedIn app, rewrites a draft the way you set it,
follows your replies and edits, keeps files and albums, and tells you when it
could not check Telegram for a day.

### Before you use 2.13.0

- **Your database is upgraded** the first time you start it, from schema 40 to
  42, after the usual automatic backup: each message from your phone is linked
  to the item it made, and the collection can hold documents, videos and
  albums. Everything already in your collection keeps its number.
- **No hand reload.** An extension loaded from the studio's folder reloads
  itself when the studio is updated.

### Added

- **The / menu.** Typing / in your chat with the bot lists its commands, each
  with one line on what it does. They are registered for your paired chat
  only.
- **Send me the whole post.** Under "Draft ready" and under a due post's
  reminder, while the bot may send you what it writes: the post alone, to
  long-press, copy and paste into the LinkedIn app. A long post comes in parts.
  You post it yourself; nothing is posted for you.
- **Shape a draft from your phone.** Buttons under a draft the bot wrote
  rewrite it through your own AI provider and your writing settings: Shorter,
  New opening and Another angle to start with, each with an instruction you can
  change, up to six or none, in Brand, Writing. The text a rewrite replaced is
  kept on the draft, with Put it back in the editor in the Composer and Undo on
  the bot.
- **Build an idea up over the day.** Reply in Telegram to an earlier message,
  or to the bot's answer about it, and your words are added to that item
  instead of starting a new one, with Undo. You can switch this off in the
  Telegram panel.
- **Edits follow.** Editing a message on your phone updates its item in your
  collection. Once an item became a draft, the draft is left as it is and the
  bot says so.
- **Remember this** under "Saved to your collection." keeps a note as a thing
  to remember, with Undo.
- **/write and a word or a #tag** writes one draft from the unused items that
  match. How many items one draft may use (10 to start with, from 2 to 20) is a
  setting, for Combine and /write alike.
- **Everything in one box.** Photos sent together arrive as one item. PDFs,
  other files and videos are kept as they are, up to Telegram's 20 MB limit for
  bots, and never read; a file the studio cannot safely show is offered as a
  download only.
- **Text kept whole.** A link behind words is kept, a link to one of your posts
  behind words is handled like a pasted one, #hashtags become the item's tags,
  and /recall #tag finds them.
- **Nothing lost quietly.** Telegram keeps a bot's messages for one day. If
  your studio could not check Telegram for longer than that, it says so once,
  on the bot and in the Telegram panel, so you can send again what is missing.
  The panel shows when it last checked Telegram, and /status says it too.

### Fixed

- The Telegram panel said "Not yet seen working" on a studio that already held
  messages from your chat.
- One log line per failed check instead of two, and a check that times out
  while your network reconnects is a warning, not an error.

## 2.12.0

Everything you send the bot lands in one collection, the studio makes posts
from it the way you set it to write, and it remembers what you tell it.

### Before you use 2.12.0

- **Your database is upgraded** the first time you start it, from schema 37 to
  40, after the usual automatic backup: your collection, the things to
  remember, and the photos and voice notes from your phone. What your phone
  already sent appears in the collection.
- **No hand reload.** An extension loaded from the studio's folder reloads
  itself when the studio is updated.

### Added

- **Your collection**, in From your record: every idea, note, link, forwarded
  text, photo and voice note you send the bot, as it arrives, without a
  reload. Each item shows its kind, its tags, whether you used it and what it
  became. A link to someone else's post is kept only as a plain link rebuilt
  from the post's id, with your own words; a forward keeps its text, never
  who it came from.
- **Make something out of it.** On any item, Make a post writes a draft in
  your voice through your own AI provider; Combine makes one draft from
  several; Angles offers hooks to choose from. On the bot, Write it up and the
  angles button sit under "Saved to your collection". The bot sends back what
  it wrote only if you tick "The bot may send me what it writes from my
  collection" (off by default); otherwise it says the draft is ready in your
  studio.
- **How the studio writes is yours to set**, in Brand, Writing: draft length,
  tone, language, opening line, emojis, hashtags, line breaks, ending, words to
  avoid, how many angles, and which things to remember go with a request. What
  ideas draw on (your collection, your posts, your asks) and how many daily
  ideas are asked for are settings too. None of it is fixed in code.
- **Things to remember.** Tell the studio about you, your audience, your offers
  and your dates in Brand, Writing, or with /remember from your phone (with
  Undo); /forget removes one. They go with every writing request you allow,
  and a draft written from your collection shows what it was written from and
  which of them went with it.
- **What you collected comes back.** From your collection in the Composer
  offers related items to add to the draft you are writing; unused ideas
  return in your daily cards and your weekly summary; /recall says what you
  saved on a word.
- **A morning idea**, off by default, on the days and at the hour you choose:
  one unused item with an angle drawn from what worked in your own posts, with
  Write it up and Not today.
- **Photos and voice notes** you send the bot are kept as they are, shown or
  playable in your collection, never read or transcribed. Add to your media
  library copies a photo there. A file over 20 MB is refused before it is
  downloaded.

## 2.11.0

The Telegram bot answers you. Until now it saved what your phone sent without
a word back; it now confirms each message, answers commands, can remind you
and report your own figures if you ask it to, and puts buttons on what it
sends.

### Before you use 2.11.0

- **No database upgrade.** The schema stays at 37: the bot's new settings are
  rows in your settings.
- **No hand reload.** An extension loaded from the studio's folder reloads
  itself when the studio is updated.
- **Try it on your phone** with the help page "Test your Telegram bot", five
  steps that take about five minutes.

### Added

- **The bot replies to every message**, in fixed sentences that never repeat
  your words: saved as a draft; Today will ask you to open this post or link;
  not one of your posts; could not save; paired; not paired yet, with how to
  pair. On by default ("The bot confirms each message"). A chat that is not
  yours is answered at most once in ten minutes.
- **Commands:** /start and /help; /idea, a draft tagged as an idea; /ask, a
  question for From your record; /status, the studio and the bridge, without
  figures; /today; and /drafts, how many drafts came from your phone in the
  last seven days.
- **Your figures, only if you allow them** ("The bot may answer with your
  figures", off by default): /today answers with your latest post's figures,
  each with where and when it was read, the replies waiting as a count, and
  your next scheduled post's time. A figure nobody read is left out. Once
  allowed, those figures sit on Telegram's servers, and the panel says so.
- **Notifications, each off until you turn it on:** a post in your queue is
  due; your latest post's figures at about 24 hours. Each is sent once,
  unless you ask to be reminded.
- **Buttons.** Undo under a saved draft removes it while it is untouched in
  the studio. Remind me in an hour and Done under a due post: Done only clears
  the reminder, and nothing ever acts on LinkedIn. A button works once, and
  only from your paired chat.
- **Quiet hours.** Notifications wait from 23:00 to 07:00 (change the hours
  or turn this off in the Telegram panel) and go when quiet hours end.
  Answers to your own messages and commands are never held.
- **A weekly summary**, off by default, on the day and hour you pick: the
  posts the studio recorded as published, drafts from your phone, replies
  waiting and your next scheduled post; figures only if you allow them.
- **Send a test message** from the Telegram panel, and the last problem
  reaching Telegram said in plain words: a token Telegram does not know,
  another program asking for the same bot, Telegram's own trouble, no
  connection, or a rate limit with how long the studio waits.

### Fixed

- The store disclosures now say that the extension checks once a minute which
  LinkedIn tabs are still open, and tells the studio only how many pages of
  each kind are open.

## 2.10.2

Network reading is retired, and the Telegram bot's token no longer shows on
Local security.

### Before you use 2.10.2

- **No database upgrade.** The schema stays at 37, and what network reading
  captured before stays in your database.
- **No hand reload.** An extension loaded from the studio's folder reloads
  itself when the studio is updated, and asks for one permission fewer
  (`webRequest`). A LinkedIn tab that was open with network reading on keeps an
  inert copy of it until you reload that tab.
- **If you shared a screenshot of Local security** after setting up the
  Telegram bot, revoke the bot's token with @BotFather (/revoke) and save the
  new one in the Telegram panel.

### Removed

- **Network reading.** LinkedIn's 2026 site no longer makes the requests it
  read: its data now arrives in an internal streaming format. The popup's
  switch, the coverage meter and the side panel's network reading lines are
  gone, and nothing in the extension wraps LinkedIn's own requests any more.
  The page readers, rebuilt in 2.10.1, and LinkedIn's analytics export cover
  what it was meant to add. Where it had run, Health and Setup say once that it
  was retired.

### Fixed

- **The Telegram bot's token is no longer shown** on Local security after the
  first poll. The poll is counted under Telegram's address with the token
  masked. It was held in memory only, never written to disk or to a
  diagnostics bundle.
- **A Telegram error answer is waited out.** A token Telegram does not know, a
  second program asking for the same bot, or Telegram's own trouble used to
  make the studio ask again every two seconds; it now waits longer after each
  failure, up to a minute.
- A message from your phone that could not be saved is logged by its kind of
  failure only, never by words that could quote it.
- The Storage and privacy panel calls the separate readings file the
  **extension readings log**: it now holds a copy of each analytics reading the
  extension sends.

## 2.10.1

From the first tests on your own live LinkedIn pages and a real analytics
export: LinkedIn rebuilt several of its pages in 2026, and three readers and
parts of the export import did not yet know them.

### Before you use 2.10.1

- **Your database is upgraded** the first time you start it, from schema 35 to
  37, after the usual automatic backup: the analytics page's members reached,
  saves, sends and network split by day and by window, and short links sent
  from your phone.
- **No hand reload.** An extension loaded from the studio's folder reloads
  itself when the studio is updated.

### Fixed

- **Your posts list is read again** on LinkedIn's rebuilt Activity page. The
  reader waits for your posts to load, keeps reading as more appear, and now
  keeps each post's impressions.
- **Your analytics page is read again**, by its own section names: impressions,
  members reached, reactions, comments, reposts, saves, sends and the share of
  impressions inside and outside your network, each with the range LinkedIn
  names. A 24-hour reading is kept as that day's figure; a range the page does
  not name is kept as unnamed, never as a day.
- **Search appearances are read** from the page LinkedIn now sends you to.
- **LinkedIn's analytics export** now also imports its Most recent posts sheet
  and both demographics sheets, and is verified against a real export.
- **Telegram is paired with one press.** Save the bot's token, send the bot one
  message, and press This is me; there is no chat number to find.
- **A post link shared from the LinkedIn app** (a short lnkd.in link) becomes
  a request on Today with an Open button; opening it in your browser tells the
  studio which post it is.

## 2.10.0

The bridge now behaves as one per browser however many LinkedIn tabs you have
open, keeps itself up to date when you update the studio, and the studio shows
more of what it keeps.

### Before you use 2.10.0

- **Your database is upgraded** the first time you start it, from schema 33 to
  35, after the usual automatic backup. A lead's stage change keeps the post it
  came from, the Queue keeps what it dispatched and missed, and the bridge's
  heartbeats and capture rows are kept per browser and minute.
- **Reload the extension by hand one last time** if it was loaded before
  2.10.0. From 2.10.0 on, an extension loaded from the studio's folder reloads
  itself when you update the studio and re-reads the LinkedIn tabs you have
  open. If an upgrade replaced that folder, Health tells you to load it again
  from the studio's folder.

### New

- **One bridge per browser.** Ten LinkedIn tabs open on one post now send the
  studio 3 requests instead of 620, write each engagement once instead of ten
  times, and keep one heartbeat per browser. A tab you are not looking at reads
  once when you come back to it.
- **Each capture lands in the right creator profile**, the one whose LinkedIn
  account read it; a capture for an account no profile holds waits in Health
  instead of landing in whichever profile is open. Only one tab runs a history
  import.
- **From your record** now builds cards from what you follow, voted on and
  wrote when it matches your topics, keeps one topic per card where it can,
  shows the day's cards as a strip on Today, has its own block in Health, and
  adds a Monday line of how last week's cards were used.
- **Brand and Settings.** Brand opens on your profile as LinkedIn last showed
  it, each part with the day it was read. Settings opens on an overview (last
  backup, next cleanup, what left this machine, your licence, the update check
  and autostart), and your LinkedIn session has one control there.
- **Posts** show a post's readings as a series for each page they came from,
  its two-day reading, and who each post brought.
- **The Queue** has a month calendar, keeps every dispatch decision including
  missed posts, says how late a due post is and why, and names the post a
  queued one collides with.
- **The Composer's "What the model is told"** shows, from the code that builds
  each request, what your AI provider is sent.
- **Outbound and Leads** show when you first engaged with an account, your last
  reaction, the days between your engagement and theirs, and the post a lead's
  stage change came from.

### Changed

- Today's What worked no longer counts "qualified leads".
- The demo shows a sample creator's own drafts and queue.
- The bridge's heartbeat carries fingerprints of your profiles' accounts, never
  their names.

## 2.9.0

The studio now shows what the bridge reads the moment it arrives, gives each
question its own section, and keeps only what is yours: the extension reads
more smoothly, draws nothing into LinkedIn's pages but its own mark on your
cards, and network reading keeps only your own posts.

### Before you use 2.9.0

- **Your database is upgraded** the first time you start it, from schema 31 to
  33, after the usual automatic backup. It gains the Answered mark on replies,
  a daily summary per reader, how long each reader took, and the network
  reading state. If network reading was ever on, figures it kept for posts in
  your feed that were not yours are removed, and a post the bridge first saw
  after the 2.7.0 upgrade gets back its studio record.
- **Reload the extension** once in the browser you capture with. Its notices
  now appear in its side panel and on its badge rather than on LinkedIn's
  page.

### New

- **Health**: whether each reader is reading, what it read in the last seven
  days, what it could not read, and which new figures LinkedIn has not shown
  on your recent pages. Setup is back to a first-run flow.
- **Replies**: everyone who commented on your posts in the last two weeks,
  grouped by post, with an Answered mark you set yourself. The studio only
  knows when it saw a comment, so it says "seen by the studio", never when it
  was written.
- **Audience**: who keeps coming back across your posts, who has gone quiet,
  and who is already a connection, ordered by what they did, never by a score.
- **The rail** is grouped into Now, Make, Learn, Bridge and Studio, with labels
  on a wide screen.
- **Profile views and search appearances** on Analytics, each over the window
  LinkedIn names; on Posts, a post's edited mark and watch time, and your own
  reposts, articles and newsletters with their figures.
- **What arrives shows at once.** A capture appears on Setup, Activity and
  Health within about a second and on Today within fifteen seconds, instead
  of on the next poll; idle Setup costs about a sixth of the database work it
  did.

### Changed

- **The extension draws nothing into LinkedIn's pages** except its mark on your
  feed cards and the import banner, which carries Stop. Captures are
  confirmed on its badge and in its side panel.
- **Network reading tells you its state** in Health: off, on and seeing
  LinkedIn's data calls, or on and matching nothing, with the counts kept as
  plain path words, never an address that names anyone. It keeps only your
  own posts' figures and your analytics.
- **No capture is lost** when the studio restarts during a history import, and
  the new readings are kept when the studio is busy.
- **Today asks for a post's week-old reading**, and for a weekly look at your
  Activity tab when it is due.
- A reader that read nothing, or was refused, no longer shows WORKING, and
  network reading reports drift like every other reader.

### Fixed from 2.8.0's known list

- Network reading no longer keeps figures for other people's posts.
- A post first seen after the 2.7.0 upgrade has its studio record again.

## 2.8.0

The studio now works from your own record every day, reads more of what
LinkedIn shows you about your own posts, and draws a firmer line around whose
data it keeps and what leaves your computer.

### Before you use 2.8.0

- **Your database is upgraded** the first time you start it, from schema 27 to
  31, after the usual automatic backup. It gains a precision mark on post
  readings, dated audience demographics, a format per post, the tables of the
  new From your record section, a place for links you send from your
  phone, and the new readings below. Nothing you wrote is changed.
- **Reload the extension** once in the browser you capture with: it reads
  more of your own pages.
- **One creator profile keeps a LinkedIn session.** Session sync and Send to
  LinkedIn now work for the first creator profile only, because each
  profile's session must come from that creator's own browser. A session an
  earlier version kept in a later profile is deleted the first time 2.8.0
  starts, and that profile tells you so once.

### New

- **From your record**, a section that builds a few cards a day from your own
  history: what worked for you (only once enough settled posts support it,
  and it says so until then), a post from this day in an earlier year, posts
  you engaged with in your own words, and what you asked the studio to keep in
  mind. Keep, skip and hide what you see; Kept holds what you keep. With your
  own AI key, a once-a-day pass on your first visit suggests angles from your
  own best posts under a daily spending ceiling (10 cents by default). It is
  sent your own text and the studio's own words for how each post did, never a
  figure, another person's name or a comment, and nothing it returns with a
  number in it is shown.
- **More of the post analytics page:** followers gained and profile viewers
  from a post, link visits, article and video views, the share of impressions
  inside and outside your network, and viewer demographics kept by day. A
  figure LinkedIn does not show you is recorded as not read, never as 0.
- **More of your own pages are read**, each figure kept as a count over the
  window the page names: profile views, search appearances and new
  followers per day from your analytics dashboard, your articles' and
  newsletters' figures, watch time on your video posts, and your own reposts
  and edited posts. Nothing about who viewed or searched is read. The
  studio keeps these from now on; the screens that draw them come in 2.9.0.
- **A rounded figure is marked as rounded.** "12K" read twice is no longer
  growth, and figures LinkedIn rounded read "about".
- **Today says whether your latest post is still moving**, from the readings
  the studio has, with how many there are and how old the latest is.
- **Followers are kept as a series**, and a weekly analytics card is kept as
  weekly rather than as one day.
- **LinkedIn's analytics export** (the .xlsx from the Export button on your
  analytics page) imports in Setup with a preview; anything the studio does
  not recognise is shown and left out.
- **Your phone can tell the desk what to read.** Share one of your post links
  to your own Telegram bot, set up in Local security, and Today asks you to
  open that post's analytics next. A link to someone else's post is refused.
- **The help quotes LinkedIn's own terms** beside each feature, so you decide
  with the words in front of you.

### Changed

- People are ordered by when they engaged, never by a score.
- Posts lists every published post, including ones published here that
  LinkedIn has not shown the bridge yet; Analytics no longer repeats the list,
  and search opens a published post on Posts.
- Patterns shows each comparison with both sides' counts and the engine's own
  abstentions; your posting rhythm moved to the Queue, and the "qualified
  pipeline" table is gone.
- The Queue shows waiting drafts as a count with one action, and queueing the
  newest draft refuses a post that is no longer a draft.
- The Evidence panel says what reaches your AI provider when you use Re-Hook
  or Command.
- The studio no longer sends MCP server settings to the browser.
- People who engaged with a post first captured after the 2.7.0 upgrade are
  listed on that post again.

### Known, and fixed in 2.9.0

- With network reading switched on (it is off by default), the feed reader
  keeps figures for posts in your feed that are not yours. 2.9.0 keeps only
  your own and removes the rest on upgrade.
- A post the bridge first sees after the 2.7.0 upgrade may lack its studio
  record until 2.9.0 restores it; its people are already listed (above).

## 2.7.0

The studio used to disagree with itself. Ask which post did best and four
screens gave four answers; ask how one post did and Today, Posts and
Analytics gave three different numbers. Underneath, four tables each held
"something you wrote", and a third of your captured engagement could not be
reached from the post it happened on.

This release gives the studio one idea of a post, one idea of what worked,
and one way in. Then every section was rebuilt on top of that, measured
rather than judged by eye: how much of the screen carries something, how
much it downloads before it can show you anything, and how long its own
questions take on three years of posts.

### Before you use 2.7.0

- **Your database is upgraded** the first time you start it, to hold one
  record per post. A backup is taken first, as always. Nothing you wrote is
  removed: on a three year install the upgrade moved 1,567 pieces of writing
  and left 1,567, and the engagement that could not reach its post went from
  182,054 stranded to none.
- **Two sections are gone.** The Swipe File drew the same hook forms as the
  rail under the Composer's editor through a second screen, and nothing could
  be saved into it. Command was the Prompt panel with its own icon; its
  instruction box is now in the Prompt panel, with a Copy control it never
  had.
- **Before the first Send to LinkedIn**, the studio asks you to acknowledge
  what it does: it posts through an interface LinkedIn has not published, and
  LinkedIn could treat that as automation. The per-send confirmation still
  asks every time on top of that.

#### What the studio knows about your posts
- Every post can tell you who engaged with it, including the posts the studio
  only knows from LinkedIn.
- A post you publish from the studio appears everywhere at once, instead of
  waiting for the extension to find it on LinkedIn.
- The drafts list shows the drafts that used to be held where no screen could
  show them.
- The studio stopped carrying a second, empty queue in every backup, export
  and cleanup.
- Posts, Analytics and the Composer's Evidence panel now name the same best
  post, measured the same way, from your whole history rather than from the
  page on screen.
- An engagement rate above 100% is no longer shown as a fact: where the
  figures came from two different readings the studio says so instead of
  printing a rate.
- Lead scores are recomputed when the headline, company or engagements they
  are derived from change, so every screen shows the same current number.
- One post now shows one set of figures on Today, Posts and Analytics, and
  says which page they were read from and when.
- Posts now reads each post as a pair, how far it reached and how strongly
  people responded, against your own posts at the same age, and the studio
  measures when a post has settled from your own readings instead of assuming
  a week.
- Patterns now says plainly when a difference is too small for your own posts
  to separate, instead of printing it as a finding.

#### What reaches the studio, and how fast
- A capture that carries the studio's own post key is kept instead of being
  rejected, and an extension older than the studio is told once to reload
  rather than failing quietly.
- When the studio turns a capture away it now says why, on the page and in the
  side panel, instead of nothing happening: most often "import your posts
  first".
- A capture your studio was busy or closed for is now kept on every path that
  carries your own data, sent again on its own, and counted where you can see
  it.
- Capturing a busy post's engagers is four times faster and no longer leaves
  the slowest capture waiting six seconds.
- Posts and Analytics read the people a post brought for the posts on screen,
  not for every post you have ever written.
- The Posts and Analytics screens load a page of posts instead of your whole
  history: 2,207 KB to 84 KB and 2,447 KB to 108 KB on a three year account.
- A post's engagers open faster, from the index rather than a scan of every
  person you have captured.
- Capturing the people who engaged with a post no longer reads your whole
  posting history for each one.
- Your hourly backup and cleanup now run when the laptop wakes, instead of
  being skipped for the hour, and the studio says when the newest backup is
  out of date.

#### Today, the Queue and writing
- Today shows the whole day at once: what to fix, who to reply to in their own
  words, how your latest post did against your own history, what worked and
  what did not, what goes out next, your last thirty days and your posting
  rhythm, without scrolling.
- The Queue opens on your week: each day with its slots and what sits in them,
  what is due, what was missed and why, and how the queue's pace compares with
  how steadily you have actually posted.
- The Composer now opens on your own strongest openings, with what each post
  drew and the shape it was in, and one click puts one at the top of your
  draft.
- Adding the engineering hook pack now adds to the Composer's hook rail
  instead of replacing your own starter forms, each pack form is marked, and
  the Composer says that those forms make first-person claims you would have
  to make true.
- The Composer's hook rail now says these are hook forms rather than posts
  anyone measured, and the rating on a pack form was typed in rather than
  measured. If you had added the engineering pack, you can take it back out
  from the rail.
- The studio no longer reads every draft you have written each time it opens.

#### Posts, Analytics and Patterns
- Posts is a table you can sort, filter, search and page, and it says how many
  posts it is showing of how many you have.
- Opening a post from Posts shows the whole post, its one reading with the
  page it came from named, where it sat for reach and response, and everyone
  the studio captured on it.
- Analytics shows your impressions, engagements, rate, followers and profile
  views with each one's change beside it, and its post comparison is a page
  you can turn.
- Patterns shows how your own posts settle, measured from your readings rather
  than assumed, and lets you order the findings, open each one and sort the
  topic table.

#### Leads, Outbound and the rest
- The lead dossier fits a phone, and at a wide window what is known about a
  person sits beside what you can do about it, so drafting a message no longer
  starts below the fold.
- A lead's dossier now shows which of your posts that person engaged with, how
  often, and when they last did.
- Outbound now shows whose posts you spend your attention on, what you last
  said to them, who has engaged back, who has gone quiet and where it goes one
  way, instead of a notice about an import.
- Activity is one log of what the bridge read, newest first and grouped by
  day, instead of five tabs of cards six screens long.
- The Swipe File is gone. It showed the same hook forms as the Composer's
  rail, which is where they can actually be used; Ctrl+K now opens one there.
- The Command section is gone. Its instruction box is in the Composer's Prompt
  panel, next to the draft it works on, and an answer can be copied.
- Backing up and exporting your work is now at the top of Brand Studio's
  Storage and privacy tab, not at the foot of Local security.

#### Saying what the studio actually does
- The extension document and help now say what a history import does: it
  clicks LinkedIn's load-more control and scrolls your own activity page, up
  to 250 rounds, only after you press Import your history.
- The architecture document no longer claims zero automated activity: it names
  Send to LinkedIn and the history import, and the risk register now names the
  Send to LinkedIn path and what it could cost an account.
- Before the first time a studio sends a post to LinkedIn, it now asks you
  once to acknowledge that this writes to LinkedIn's private scheduling API,
  outside LinkedIn's published terms, and records your answer. Each send still
  asks you to confirm the account and the time.

## 2.6.1

Three faults that needed Windows, or a slow machine, to show themselves. If
you run 2.6.0 on Windows, this one replaces it.

- **A capture the studio was busy with is saved instead of lost.** When the
  bridge sent a page's engagers together, some were refused with "database is
  locked" and dropped without a word. The studio now waits its turn and tries
  again, and if it is still busy it answers so plainly; the extension keeps
  that capture and sends it the next time it gets through, up to 200 of them,
  and the same capture sent twice is still one engagement.
- **A restore is no longer refused.** On Windows, restoring a backup could
  stop with "Access is denied", because a background job that keeps each
  post's figures up to date still had the database open. Every part of the
  studio that opens the database now waits while a restore swaps the files,
  that job is stopped and resumed around it, and each file move is retried
  briefly in case something else is reading it. A half-applied restore was
  never possible and still is not.
- **Reset forgets whose LinkedIn session it was.** It cleared the session
  cookies and kept the row naming the account they belonged to, so the studio
  still said who had used this computer.
- **A day's "members reached" is no longer shown as 0.** That figure has never
  been read from LinkedIn, and an old database default stored a 0 on every
  row, which Analytics read as measured. Your existing rows are cleared when
  the studio next starts.

## 2.6.0

### Before you use 2.6.0: four things to do once

- **Reload the extension** on your browser's extensions page
  (brave://extensions, edge://extensions or chrome://extensions). A browser
  keeps running the old extension until then, and the old one reports some
  things the studio now refuses (it may still say "synced").
- **Open your own profile once** at `https://www.linkedin.com/in/me/` in the
  bridge browser. Analytics are now kept only when the browser is signed in to
  the LinkedIn account you confirmed in Setup, and this is how the extension
  learns which account that is.
- **Run one posts import** from Setup with the reloaded extension. Imports the
  old extension called complete can no longer be shown to have reached the end,
  so Today and the Leads review wait for one that does. Nothing is deleted.
- **Sample drafts from 2.5.1 are removed.** The 16 Launch Kit drafts an earlier
  version put into every install are removed on the first start, but only those
  you never edited, queued or published, and only after a backup of your
  database. Today tells you once what was removed and where the copy is.

- **A daily backup now runs on its own**, keeps about 14 copies, and checks
  each one as it is made. Brand Studio has a new **Storage and privacy** tab
  that shows what the studio holds, its retention rules, and its backups.
  Folding reactions older than two years into counts, and listing leads silent
  for two years, both ask you first; nothing of yours is removed without that.

### One name
- **The product is Inox Hydra**, and the extension is **Inox Hydra Bridge**.
  Before, it went by five names, one borrowing a competitor's mark.
  Shortcuts and the extension take the new name; a Startup shortcut made
  under the old one still works and is replaced the next time autostart is
  switched on. Your data stays where it was.

### Creator profiles
- **Each creator profile is its own database.** Profiles used to share one,
  so switching changed the avatar and nothing else. Now each profile has its
  own posts, drafts, leads, analytics, media, backups and exports, and
  nothing one holds appears in another. Your first profile is your studio as
  it was. Scheduled posts in every profile fall due on time, whichever one is
  open.
- Deleting a profile asks you to type its name, and removes its folder.

### Licence and prices
- **An offline licence.** Brand Studio, Licence: paste the key from your
  purchase, and it is checked on this machine with nothing sent anywhere.
  Free; Creator at $12 a month billed yearly, or $249 once with a year of
  updates; Agency at $39 a month for up to 5 creator profiles. During the
  beta every Creator feature stays open to everyone; a licence changes the
  number of profiles you can keep.

### Setup
- **Your LinkedIn archive is a Setup step.** The studio opens LinkedIn's
  "Get a copy of your data" page, finds the export in your Downloads folder
  once you say you asked for it, shows what it holds, and imports only what
  you keep ticked: your posts with their dates, your comments and reactions,
  your profile, roles, education and skills, and your connections (never
  their email addresses). Messages are never imported. Nothing the bridge
  captured is overwritten.

### The extension
- **Network reading is off unless you switch it on.** The part of the
  extension that wraps LinkedIn's page `fetch` to copy exact figures now
  runs only after you turn on "Read LinkedIn's network responses" in its
  popup, where what it does is written beside the switch.

### Your data
- **Export to Obsidian.** Brand Studio, Local security, Your data. Writes your
  posts, the people who engaged with them, your topics, the people whose posts
  you engage with, and your drafts as a folder of linked notes. Export again
  into the same folder to refresh it: notes you add, and anything under a
  "Your notes" heading, are kept. Also `python -m studio.cli export --format obsidian`.
- **The JSON and CSV exports carry your own LinkedIn record**: your profile,
  roles, education and skills, your posts with every reading of their figures,
  your comments and reactions elsewhere, and each lead's stage history. Before,
  none of it could be exported. Credentials are still never included.

### Writing
- **Drafts in your own voice.** When a model is configured, the copilot's hooks
  are now written from who you are and how you write: your headline, roles,
  skills and about, measured habits from your own posts (length, paragraphs,
  how often you open with a question), and the openers of yours that drew the
  most reactions. Each part is sent only when there is real data for it, and
  the response records which parts went.

### Fixed
- An installed copy of the studio starts again. The package left out the
  folder that holds most of its API routes, so a fresh install failed at its
  first import; CI now finds every package on disk instead of trusting a list.
- Carousel slides are signed with your own name and headline from Brand Studio
  (or your confirmed LinkedIn profile), or left unsigned. They used to fall back
  to the original author's job title, which every new user's slides carried.
- The command engine, the hook rail and the repurposer write for you, using the
  same voice pack as the copilot, instead of a system prompt describing one
  particular author.
- A first-message draft no longer tells someone who only reacted to your post
  that they commented on it. Every lead the bridge captured was labelled
  "Commented"; the label now follows how they actually engaged, and leads
  captured before this are corrected from their own records when the studio
  upgrades its database (a backup is taken first, as always).
- A captured lead's LinkedIn profile link is stored where the dossier reads it.
- Follower counts read from LinkedIn's network responses were never saved: the
  write named a column that does not exist, and failed every time without a
  trace. They are saved now. The impressions figure beside them is not, because
  it covers a period the response does not name.
- A post placed in LinkedIn's composer from the side panel is recorded again,
  so it can be linked to its LinkedIn post once published.
- An activity page reached through LinkedIn's `/in/me/` address is read as
  yours only when nothing in the browser says it belongs to another account.
- The Composer works in a narrow window: below 1024 pixels the inspector opens
  as a drawer over the editor instead of squeezing it out, and its close
  control can no longer be pushed out of reach by its own tab labels.
- The Activity screen follows the light theme and meets contrast, and no
  longer names a browser that has not reported in.
- Posts, Patterns and Outbound keep their heading before anything is imported,
  and every screen has one level-one heading for screen readers.
- Rail labels no longer stay over the page after you click a section.
- Reload on brave://extensions no longer fails with "Cannot load extension
  with file or directory name __pycache__". The packaging script lived in the
  extension folder, and running the tests left a Python cache beside the
  manifest; it now lives in `tools/`.

### Ready for a normal creator, and for years of data

A second cycle: four research reports (install, backend, frontend, data at
scale), owner decisions, seven parallel batches, an independent review of each
and a re-check of every fix sent back. The plan is
docs/quality/CYCLE2_2026-10_PRD.md.

#### Installing and updating
- The release smoke test passes the studio's own security gate, so a 2.6.0
  release can actually publish its portable ZIP and update manifest.
- The desktop app installer includes the studio interface instead of opening
  on an error page.
- macOS and Linux builds carry their own pinned, checksum-verified Python, and
  a build that would depend on the build machine's Python now fails instead of
  shipping.
- A release is published only when the portable ZIP, the update manifest and
  the Windows installer are all on it; until then it stays a draft nobody
  sees.
- The portable launcher opens the studio only once it is really running, says
  when another program holds port 8000, and shows the engine's error instead
  of a page that cannot connect.
- When another program uses port 8000, the portable launcher starts the studio
  on the next free port and says that the browser extension needs 8000.
- Double-clicking create_desktop_shortcut.vbs in the portable folder now makes
  a working desktop shortcut.
- The README inside the download no longer points at a store listing that does
  not exist.
- The studio's Docs screen in a downloaded copy shows the help articles only,
  not the project's internal engineering documents.
- The install, upgrade and removal instructions match what the Windows
  download does today, and macOS and Linux users are told to run from source
  for now.
- Hindi and Gujarati quote overlays appear on generated images in the Windows
  download and desktop app, which now include the text layout library Pillow
  needs.

#### Writing, drafts and publishing
- A queued post missed while the computer slept now waits as due at its own
  time, and Today says it was missed, with Post now and Move to next slot; it
  is never moved without asking.
- Your weekly posting slots can now be added, retimed, renamed and removed on
  the Queue, and start with plain names such as Monday morning.
- New studios start with neutral fill-in hook forms; the engineering creator
  pack of 36 forms is now an opt-in from the Swipe File.
- The Composer now has Drafts and New post: see every draft, open, find or
  delete one, and clearing the editor never saves over an earlier draft.
- Publish's main action is now Copy and mark posted: it copies the exact text
  and records it as posted by you, with Queue it beside it and a Copy button
  in the Composer.
- Send to LinkedIn now names you as the author, sends only as the account you
  confirmed after asking with that account and the time, refuses times
  LinkedIn will not hold, and keeps a record of each send and LinkedIn's
  answer.
- Removed POST /api/v1/scheduler/native/stage, an unguarded duplicate of Send
  to LinkedIn.

#### Images
- Images: a generation that fails or is blocked now says so and why, and
  nothing is added to your library; choose who makes your images (the free
  public generator, your OpenAI, Google Imagen, Stability AI, Replicate,
  fal.ai or Together account, or AUTOMATIC1111, Forge or ComfyUI on your own
  machine, or Off) in the Prompt tab, with what leaves your computer shown for
  each. Image providers never follow a redirect to another address, and if you
  already made images with an OpenAI or Gemini key, the studio keeps using the
  model you had until you choose another.
- Images: quotes and your watermark are drawn at full size on Windows, macOS
  and Linux, and Hindi and Gujarati quotes and names are drawn in their own
  letters instead of boxes.

#### Everyday screens, help and restore
- Reply to their comment drafts straight away from the post the person
  commented on, without asking you to type it.
- Screens that could not load while the studio was stopped recover by
  themselves when it is back, and Queue, Leads and Posts stay current while
  open.
- Activity and Setup stop asking the studio for updates while their window is
  hidden.
- Help and search show creators the help articles only; maintainer and retired
  documents no longer appear unless developer mode is on.
- Docs lists the help articles only; the studio's engineering documents and
  retired manuals are no longer part of the customer's library.
- Brand Studio can now restore a backup: Local security, Your data, Restore. A
  safety backup is taken first, and people you forgot after the backup was
  made stay forgotten.
- The import of your LinkedIn history has one name, Import your history, on
  Setup, Today and Activity.
- Setup says when it is done and takes you to Today.
- Times on a screen use one clock format, a queued post shows its date, and an
  unread figure on Activity reads not measured instead of 0.
- Patterns compares each form once, in plain words, and no longer says Other
  posts posts.
- The help on saving a post no longer tells you to reload before starting the
  next post.
- The studio opens straight on Setup or Today without flashing the Composer
  first.
- The bridge mark beside Activity always agrees with the screen under it.
- Demo mode now includes a sample creator with posts and people who engaged,
  so Today, Posts, Patterns and Outbound show data.
- After you mark a post as published, Today names it until the bridge sees it
  on LinkedIn.
- Today's status line no longer says nothing was captured when your posts are
  already imported.
- Search names a lead's stage as Leads does.
- In the Composer, Ctrl+S saves and Ctrl+B, Ctrl+I and Ctrl+U format the
  selection.
- Empty Posts, Patterns and Outbound screens have a Go to Setup button.
- After copying a message on Leads you can mark the person as Outreach Sent in
  one click.
- Forgetting a lead says that older backups keep them until rotation, and
  where to remove them from backups too.

#### Speed with years of data
- Posts, Analytics, Patterns, Outbound, Today, Activity and the Leads review
  open in under a tenth of a second on years of data, where they took up to
  two seconds.
- Search answers as you type, in milliseconds, on years of data; it matches
  words from their start, so 'pric' finds pricing, and finds words you wrote
  in bold or italic.
- Exporting your data needs about 20 MB of memory however much you have, where
  three years took over a gigabyte.
- The database keeps its query statistics current, after updates and while the
  studio runs.
- The Leads screen opens at once however many leads you have, and searches on
  the server.

#### Storage, retention and privacy
- Forgetting someone now overwrites their words in the database file on every
  system, and Storage and privacy says how long they stay in older backups and
  can remove them from backups too.
- The studio now backs itself up once a day, checks every backup as it is
  made, stores photos without recompressing them, and keeps about 14 automatic
  backups and the last 2 pre-upgrade copies instead of every one ever made.
- New Storage and privacy tab in Brand Studio: see what each kind of data
  takes, choose how long readings and logs are kept, preview every cleanup
  before it runs, fold two-year-old reactions into counts without changing any
  number on screen, and review people who have been silent for two years.

#### Reliability and privacy under the hood
- A comment cut through an emoji is now captured as a lead, and any failure
  inside the studio answers a readable sentence instead of 'Internal Server
  Error'.
- When the database is busy or the disk is full, the studio says so and asks
  you to try again, and the rest of the studio keeps answering meanwhile.
- The diagnostics file and the studio's log no longer contain searches,
  message topics, names or profile addresses.
- Starting the studio keeps the previous session's log as engine.log.1 instead
  of deleting it.
- A grounding source that hangs no longer freezes the preview or leaves
  programs running.
- Grounding sources started with npx now work on Windows.
- Grounding sources no longer receive the studio's API keys.
- A grounding source that fails now says why.
- If the studio's database is damaged, the studio still opens and offers to
  restore your newest backup.
- Telemetry no longer grows with oversized payloads and loses nothing when the
  studio stops.
- Telemetry no longer keeps text or names, and forgetting your identity clears
  it.
- Deleting a media file now removes it, or says it could not and keeps it in
  the library.
- A very short image concept gets a clear message instead of an error.
- Removed about thirty unused API routes (listed in the commit); anyone
  scripting against them should use the studio's own routes. Telegram ingress
  is now a maintainer feature that needs INOX_DEV_MODE=1.

### Fixed before release

A quality cycle before the first paid release: six audits used the studio the
way a new customer would, 160 findings were triaged to 142 real defects
(26 very high, 50 high, 66 medium), and every fix was independently reviewed
and carries a test. The register is in docs/quality/BUG_REGISTER_2026-10.md.

#### Setup and your LinkedIn history
- The archive preview says whose archive it is, and an archive in someone
  else's name, or imported before you confirm your profile, is imported only
  when you tick a box naming you both.
- Importing LinkedIn's first, basic archive no longer ends the archive step:
  Setup keeps looking for the complete archive with your posts, and an account
  with no posts can say so.
- Importing a large LinkedIn archive takes seconds rather than a minute,
  drafts and bridge captures keep saving while it runs, and an import cut off
  part way can be removed.
- Posts with the same words on different days import as separate posts, and
  image, video or document posts without a caption are imported instead of
  dropped.
- An archive Safari unpacked into a folder is found in your Downloads folder,
  and Setup's archive step can be pointed at a folder with Choose the folder.
- What an archive import added can be removed from the archive step, even
  before you confirm your profile, and what the bridge has read since is kept.
- On Windows, Setup looks for the archive in your Downloads folder even after
  you moved it to another drive or into OneDrive, and says which folder it is
  watching.
- A LinkedIn archive still downloading is shown as STILL DOWNLOADING instead
  of being offered and then refused as a broken file.
- The archive import result names what it filled in plain words and says why
  rows were skipped.
- Setup now recognises your profile when your LinkedIn address contains
  accented or non-Latin letters (for example josé, müller, 王伟, राहुल).
- Leads who commented on posts brought in from your LinkedIn archive are
  recognised as yours and are no longer offered for removal as 'engaged only
  with other people's posts'.
- A history import that stalls, hits its limit or reads nothing is recorded as
  partial, and Setup says so; only an import that reaches the end of your
  posts lets Leads call anyone 'not on your posts'. If your browser still runs
  the extension from before the update, Setup and Today say to reload it on
  the browser's extensions page before importing again.
- Deleting everything the studio holds about you now shows what will be
  deleted, says whether a backup exists, offers one, and asks you to type
  'delete' first.
- Removing the wrong account in Setup now also clears the name, headline and
  company it filled in Brand Studio, unless you changed them.
- Opening your own profile no longer cuts the skills and roles read from your
  archive or the full lists down to the few the profile page shows.
- Import all three now says what actually happened: which browser opened, in
  what order the imports run, or why nothing could start.
- Setup's 'Your history' step now ticks only once your posts have been read to
  the end of the list, so Today never sends you to a Setup that looks
  finished.
- In Setup and Today, the result of a click, including errors, now appears
  next to the button you pressed.
- An import you asked for more than 30 minutes ago now reads 'Expired, click
  Import again' instead of waiting forever.
- Import all three carries on through comments and reactions even if the
  studio restarts mid-import, and Setup shows which import is running.
- Capture health no longer lists two network-reading rows that stay 'not seen
  yet' unless you turned network reading on.
- Setup's 'Sync All Activity' is now 'Import all three', with a plain
  description, and the help explains it.
- With only Chrome installed, Setup's first step shows the extension folder
  and how to load it by hand; with no suitable browser it says to install Edge
  or Brave.
- A history import no longer turns a new draft that reuses an old post's
  opening into that old published post.
- The Activity screen's Leads list now shows the people just captured first.
- Today's Reply to shows when someone commented rather than when the comment
  was last re-read, and leaves out people who only reacted.

#### The browser extension
- Opening the reactions list of someone else's post in your feed no longer
  files its reactors as your leads; a list whose post the bridge cannot tell
  is not saved.
- In LinkedIn's rebuilt comment layout, commenters on other people's posts are
  no longer filed under your post.
- On a German, Italian, French or other non-English LinkedIn, followers and
  impressions are read correctly (8.210 is 8210), and a figure the bridge
  cannot read with certainty is no longer saved.
- Analytics read with LinkedIn's 'Past 365 days' (or a range in another
  language) are no longer saved and charted as today's figure.
- Analytics and follower counts are saved only when the browser is signed in
  to the LinkedIn account confirmed in Setup; open
  `https://www.linkedin.com/in/me/` once in the bridge browser so it knows which
  account that is.
- Insert into LinkedIn Composer no longer types your draft into an open
  comment box or a message.
- A stranger's comment you replied to is no longer saved as your own comment.
- A post you reposted is no longer imported as one you wrote.
- Setup's 'Connect the browser' step no longer unticks while you read Setup
  with LinkedIn in the tab beside it.
- A post that mentions a number of impressions or comments no longer has that
  number stored as its own figures.
- Your follower count is saved whatever range LinkedIn's analytics page shows.
- The extension help no longer says leads are captured on your activity pages.
- The analytics notice on LinkedIn no longer says 'synced' when the studio was
  closed, unpaired or refused the figures.
- With network reading on, the exact analytics figures are no longer dropped
  on a busy LinkedIn page.
- The extension popup's LinkedIn Session line shows whether the studio holds a
  session, and its side panel button says when the panel could not open.
- A short reactions list that finishes loading just after it opens is now
  captured.
- Engagers seen while the studio was not running are captured once it is back,
  without reloading the page.
- A post whose LinkedIn card shows only a document or share id is no longer
  saved under an id LinkedIn never issued.
- Opening a repost of your post no longer links the repost to your studio post
  in place of the real one.
- The bridge's notices on LinkedIn are announced to screen readers and stay on
  screen longer.
- Captured analytics days no longer report a members reached of 0 that was
  never read.

#### Writing and publishing
- Reloading or closing the studio with unsaved writing in the Composer now
  asks before the text is lost.
- Applying a hook no longer replaces the whole post when blank lines hold a
  space or LinkedIn's blank spacer, and a new Undo button puts your opening
  back.
- Typing a Windows Alt code such as Alt+0149, or Alt and a number in another
  field, no longer applies a hook over your opening.
- Saving a draft that was changed in another window since you opened it is now
  refused with an explanation, and Keep this version lets you replace it on
  purpose.
- Double-clicking Save on a new post no longer creates duplicate drafts.
- Words typed while Bold, Italic or Clean is still working are no longer
  thrown away.
- Clean formatting no longer turns ranges like Mon-Fri into lists, flattens
  indentation, or glues '.env' to the word before it.
- The Composer's character count now shows LinkedIn's 3,000 limit and agrees
  with the Audit for Hindi, Gujarati and emoji.
- When a save fails, the Composer now says why on screen instead of in a hover
  tooltip.
- Every studio screen now has its own address, so reloading keeps your place,
  links open the right screen, and Back moves between screens.
- The studio now follows your computer's light or dark setting, remembers your
  choice, and has a theme button in the top bar.
- The header no longer shows a fixed DRAFT 01 or a green 'live' dot when the
  bridge has not been seen.
- At phone width the header's Search button and the Composer's fold label stay
  on screen.
- Deleting a media file now asks first and reports a failure, and the Composer
  no longer suggests it can attach files or show carousel slides.
- A queued post's text can be corrected from the Queue with Edit text, and a
  save over a queued or published post now asks before changing it or saves
  your text as a new draft, instead of overwriting it by accident.
- With the studio open in two windows, switching profile in one now tells the
  other, and the other's saves are refused instead of landing in the wrong
  creator's profile.
- After Publish the Composer clears for the next post; writing the next post
  no longer overwrites the one you just published or queued.
- Publish saves what is on screen first, so Queue it and Send to LinkedIn act
  on the text you see, and the dialog shows which post it is acting on.
- Publish on an empty or unsavable draft explains why in the status strip
  instead of opening a dialog with no way out.
- The Queue no longer records a post as published when its time comes: it
  moves to Due on the Queue for you to post, and counts as published once you
  press I posted it or the bridge sees it on LinkedIn.
- Inserting a post from the side panel no longer records it as published
  before you post it, and no longer makes a second copy of a queued post.
- A post you marked as published, queued or sent to LinkedIn from the studio
  is now linked to its LinkedIn post when you open it, so its engagers are
  attributed.
- Posts written in Hindi, Gujarati, Chinese, Arabic, Russian or any other
  script can now be linked to their LinkedIn post, and the side panel says
  when a post cannot be identified.
- The Queue lists posts at your local time, matching the Composer and Today.
- Errors such as a wrong AI key or a refused Send to LinkedIn now show the
  reason instead of a bare '400' or '502'.
- When the studio stops answering, every screen says so in one line instead of
  'Failed to fetch', and the line goes away when it is back.
- The side panel's queue no longer invents a time for an unscheduled post, and
  shows text in angle brackets as written.
- The side panel's Fold Safe verdict and character count now agree with the
  studio's.
- If LinkedIn does not answer a Send to LinkedIn, the studio says the post may
  already be scheduled and holds back a second send until you have checked.
- The Publish dialog keeps keyboard focus while open and returns it to Publish
  when closed.
- The Publish dialog says plainly that Send to LinkedIn sends the post's text
  and uses your saved LinkedIn session.

#### Your own AI provider
- Your AI provider key no longer appears in the Local security data, the
  server log, error messages or the diagnostics bundle; Gemini's key is sent
  in a header instead of the address.
- With no AI provider set up, nothing is written for you that you did not say:
  Re-Hook offers fill-in templates with a [bracket] for each fact of yours,
  and Command says a model is needed.
- The Prompt tab now lists exactly what goes to your AI provider, including
  the parts of your profile and posts sent to match your voice, and each
  Command answer says what was sent with it.
- When your AI provider refuses your key, runs out of credit or fails, Re-Hook
  and Command now tell you why instead of quietly showing templates, and the
  Prompt tab shows the last failure.
- A stalled AI provider can no longer freeze the studio: requests stop after
  40 seconds, Re-Hook shows that it is working, and pressing it again while it
  runs does nothing.
- Claude can be connected from the Prompt tab again, with current models, and
  you can now choose the model there for any provider.
- The Command console shows the model's answer as text, not JSON, and can
  include your Composer draft when you tick the box.
- Carousel slide titles and text now show in the theme's colours instead of
  black.
- Carousel slides are no longer headed ARCHITECTURE or signed 'Creator' when
  you have not given a tag or a name.
- Generated images no longer put stock quotes under famous names or sign
  quotes 'Leadership'; only words you typed are drawn.
- The Audit tab no longer scores an empty draft, and its checks read as advice
  (WORTH A LOOK) without team-role jargon.
- The Linux and macOS source launcher now keeps its log in the app's logs
  folder, where the diagnostics bundle finds it, and tells you if the server
  did not start.
- The Prompt tab says plainly when no AI model is set up, instead of showing
  an internal engine name.

#### Leads, messages and your Obsidian vault
- Lead drafts no longer claim an architecture blueprint, an engineering
  background or a tech stack: they use only the person's record and what you
  type, and Offer something offers only what you name.
- Forgetting a lead now removes their stage history too, from the studio and
  every export, and it no longer comes back if the same person engages again.
- Exporting to Obsidian again never overwrites a note you wrote or edited: a
  generated note that would take its name is written under another name, and
  the export says so.
- In an Obsidian vault, each note stays with the same person or post across
  exports, so your notes no longer move to someone else when a namesake is
  added or removed, and a renamed person or draft moves to the new name with
  your notes.
- The Leads CSV shows a commenter's name or headline that starts with = or @
  as text instead of running it as a spreadsheet formula, and its Status
  column matches the screen.
- In a lead's dossier you can now edit your notes and forget the person, which
  removes them and everything the studio recorded about them.
- Demo data no longer stays once the studio starts without INOX_DEMO_DATA:
  untouched sample people, drafts, posts and figures are removed after a copy
  of the database is saved to the backups folder, and anything you queued,
  published or edited is kept.
- Export to Obsidian in Brand Studio now refreshes the same vault each time,
  keeping what you wrote in it, and says what it kept.
- The lead dossier shows times and dates in your own time zone.
- A lead scored 0 now shows 0 and its tier instead of 'Not scored'.
- A post's VIP lead count uses the same 80-point rule as the rest of the
  studio.
- The lead stream can be searched by name, company, headline or notes and
  filtered by stage, and long lists load 200 at a time.
- On a phone-sized window, choosing a lead opens their dossier full width,
  with a way back to the list.

#### Analytics, patterns and search
- Analytics no longer reports a rise such as +650% when the previous period
  was barely captured: a change is shown only when both periods have at least
  80% of their days, compared per captured day, and the screen says how many
  days each has.
- Figures LinkedIn rounded (1.2K) are marked approximate on Analytics, and a
  change smaller than that rounding is not reported.
- Analytics' Post comparison now lists your posts imported from LinkedIn, and
  a figure nobody read shows 'not measured' instead of 0 or 0%.
- Analytics opens quickly with thousands of posts and no longer goes blank
  when you change the range.
- Search finds people whose names have accents or umlauts however you type
  them, ignores quotes around a word, and no longer offers unrelated help for
  such names.
- Search now finds words in your posts imported from LinkedIn.
- Patterns counts each person once per topic, and its qualified share can no
  longer read above 100%; Outbound's 'On your posts' counts posts, not
  interactions.
- Patterns no longer calls a comparison conclusive, or passes it to the
  copilot, when its two sides come from different years.
- Patterns' topics are now the words and hashtags your own posts share, not a
  fixed software vocabulary, and the screen says they are a keyword grouping.
- The Patterns page can be scrolled with the keyboard.
- After an archive import, Outbound says how many reactions and comments were
  imported and how to add their authors, instead of saying none were imported.
- After an archive import, Posts and Patterns say your imported posts have no
  figures yet and how to read them, instead of saying they are too new.

#### Profiles, licence, backups and installing
- Restore works when the studio's database is damaged: the damaged file is
  kept in the safety backup and the good backup goes in.
- When an Agency licence ends, profiles beyond the free tier stay on disk and
  listed but closed until it is renewed; they can still be backed up, exported
  or deleted, and your first profile always works.
- Deleting a creator profile while an image generation or other work for it is
  running no longer leaves its folder behind.
- The automatic database copy taken before an upgrade can now be restored with
  the restore command.
- A restore that fails part way now changes nothing and tells you where the
  safety backup is.
- Restoring a backup made by a newer version is refused with a message to
  update the studio first, instead of leaving a studio that will not start.
- Large media uploads no longer load the whole file into memory, and files
  over the size limit are refused with a clear message.
- On Linux, autostart and the desktop shortcut now work when the studio is
  installed in a folder whose path has a space.
- The update command no longer tells a portable-mode user to delete the folder
  that holds their data.
- `reset` now clears only the AI setup and the LinkedIn session; a paused
  queue stays paused and the Brand Studio profile is kept.
- Switching to a profile written by a newer version now says why it cannot
  open, instead of a server error.
- Brand Studio's backups list now shows your newest backups first.
- Update checks now report only versions that have actually been released.
- A creator profile can no longer be given an id Windows cannot use as a
  folder name, such as 'con' or 'aux'.
- The diagnostics bundle no longer contains your computer account's folder
  name, or a copy of the previous bundle.
- The command-line backup, export, restore and doctor now say which creator
  profile they used, and take --profile, with --all for backup and export.
- Setting the computer's clock back no longer brings an ended licence back,
  and a clock that was once set far ahead no longer locks out a valid licence.
- Command-line commands run before the studio's first start now explain that
  there is no data yet, instead of crashing or writing an empty backup.
- In the Windows tray, Exit now also stops the studio server the tray started.
- The packaged studio now ships its help articles; every help section in Docs
  is filled.
- The profile switcher now shows the right number of drafts for each profile.

#### Across the studio
- Copy the folder path on an empty Leads screen no longer says 'Copied' when
  the clipboard was unreachable; it shows why and selects the path. The lead
  dossier's COPY and Activity's copy URN confirm only once the copy happened.
- Open the post on Posts and Open in Bridge Browser on Activity now show that
  they are working and then say which browser opened, or why none could.
- The profile switcher opened from the navigation tray now opens below the
  profile card instead of above the top of the window.
- The navigation tray scrolls on short laptop screens, so Docs and Brand
  Studio are reachable, and Brand Studio's tabs wrap on a phone instead of
  running off screen.
- The command palette, navigation tray and profile switcher now keep keyboard
  focus while open, close with Escape one layer at a time, and give focus back
  to what opened them.
- On a licence with no room for another creator profile, the profile switcher
  explains the limit instead of offering a form that is refused after you fill
  it in.
- Brand Studio's Local security no longer says drafts and the LinkedIn session
  never leave this machine; it lists what stays and exactly which actions send
  what, and where.
- The inspector no longer says Brand Studio is not built, the Command screen
  no longer opens with an internal engine codename, and the Activity screen is
  called Activity everywhere it is linked.
- Switching profile with unsaved Brand Studio edits now asks first, and says
  which unsaved work would be lost.
- Help articles in Docs are readable on a phone-width window; before, opening
  one changed nothing on screen.
- Typing a search on the Docs home screen keeps every letter; it used to keep
  only the first.
- The LOCAL shield on the rail no longer says all processing is local: it says
  your work is kept on this machine and where to see what leaves it.
- Activity's Imports tab says how each import ended in words, and shows only
  an import read to the end as complete.
- Activity says when the studio last answered instead of "Live updates on",
  says so when the studio stops answering, and the header button is called
  Activity.
- With an AI provider connected, hooks are no longer written for "Engineering
  & Product Leaders" unless you asked for that audience.
- The Distribution audit no longer quotes reach penalties nobody measured,
  such as "-40% algorithmic reach penalty"; it says what it found in your
  draft.
- The command-line reference describes what reset clears today: the AI
  provider settings and the LinkedIn session, nothing else.
- The release notes no longer tell a portable-mode user to delete the folder
  that holds their data.
- The README, the docs and the command-line help name only Claude models
  Anthropic still serves.
- An import that pauses because its LinkedIn tab is hidden now says so in
  Setup, and that the tab must be in front, instead of SCROLLING NOW.
- Today shows posts that are due to post now, with Copy text and I posted it.
- After the studio removes sample content an earlier version added, Today says
  once what it removed and where the copy of your database from before is.
- In a lead's dossier, a copy the browser refuses now points to the text above
  it, and the message goes once a copy works.

### For developers
- The repository no longer holds the owner's own posts, figures, post
  graphics or Taplio scripts, or real members' names; demo seeds use
  labelled samples.
- The desktop shell's installer now carries the name Inox Hydra. A
  development install made under the old name is not upgraded in place;
  uninstall it first. No release ever shipped the desktop shell.
- CSV exports prefix a cell that begins with =, +, - or @ with an
  apostrophe, so a name or comment someone else wrote cannot run as a
  spreadsheet formula.
- `tools/licence_keys.py` makes the licence signing key outside the
  repository and issues licences. Ed25519 is the RFC 8032 reference code,
  checked against the RFC's vectors.
- `tools/ui_audit.py` drives every screen in both themes at desktop and phone
  width and reports console errors, egress, failed API calls, accessibility
  violations and overflow, with screenshots. CI runs it on Linux.
- Playwright is installed in CI, so the browser suite runs instead of skipping.
- No test starts a real browser. Setup's sync test launched Brave on every
  run on a machine that had it, pointed at the live studio, and left the
  window open; the launcher's process calls are now recorded instead.
- Agentation, a dev-only review toolbar, sends element-anchored notes to an
  agent through `agentation-mcp` (`.mcp.json`). It never enters a build.
- `npm run dev` works against any backend (`INOX_API_TARGET`) and receives the
  studio token before its first request.
- `planning/` is an Obsidian vault mapping what the bridge reads to what the
  product does with it, the open gaps, and the commercial roadmap.
- The README no longer claims an encrypted database, an air-gapped install, or
  an extension that does not wrap `fetch`. It describes what the code does.

### Since v2.5.2, before this entry
About 140 commits landed between v2.5.2 and the work above. The larger pieces:

- A React interface replaced the vanilla page, with self-hosted fonts.
- Setup: the studio learns who you are from your own LinkedIn profile and
  imports your history, with capture health showing what each reader saw.
- Today, Posts, Patterns and Outbound: what to do in the next hour, which posts
  worked against your own usual and who they brought, and whose content you
  engage with.
- Lead dossiers with a drafted first message that says nothing the record
  cannot support, and a history of every lead's stage.
- Universal search, a help centre, and the playbook in Docs.
- One egress chokepoint with a ledger, and the AI key sealed at rest.
- Grounding drafts in your own material through MCP servers.
- A native desktop shell for Windows, macOS and Linux, with signed updates wired
  but off until keys exist.
- Creator profiles in the rail (their data is not yet separated; see
  `planning/6 Gaps/Gap - Account scoping is cosmetic.md`).
- Live activity stream, router split, terminal monitor and streaming AI.
