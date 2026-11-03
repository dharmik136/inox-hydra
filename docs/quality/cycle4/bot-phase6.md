# The Telegram bot, phase 6: what connects, what comes back, what you have, and a reply that rewrites

Written before any of its code (2026-11-03). Branch `qc4/bot-phase6`, from `6c1bba2` (2.14.0, schema 43). It says, for each item, how it will be built, where it lives, what is stored, what may go to Telegram or the AI provider and under which switch, which preferences it adds with their defaults, and what was decided against. The record of what was built is a "Phase 6" section of [the bot's record](telegram-bot.md), written as each item is committed.

## The owner's words, and the reading built here

Asked on 2026-11-03: "continue", after phase 5 shipped. Standing since phase 3:

- "much more real time ideas and features are needed here on the bot and on our product to make something out of those things and remember them for some things" (one bot for one person, one collection box; no reading of photos and no transcription of voice notes, now or here)
- "do not hardcode things as they will be users preference in AI work"
- For the interface: "things in sections only, but each section properly optimised".

Read as:

1. "Real time" and "make something out of those things": what the creator sends is matched against what they already sent, at the moment it arrives, and the bot says so in the answer it already sends, with a way to write from the group. The studio shows the same groups on each item of Your collection.
2. "Remember them for some things": an idea the creator never used is brought back when they ask for it to be, and what the studio holds (the unused items, the things to remember) can be read and pruned from the phone.
3. "Make something out of those things", again: a reply under the bot's message about a draft is about that draft, and today it is filed as an unrelated note. It becomes the way to say what to change.
4. Every count, threshold, time, schedule and set of buttons these use is the creator's preference with a visible default, explained in plain words. The guarantees (nothing posted for the creator, nothing invented, nothing about another person stored or sent, traffic only through `egress.py`, the creator's words and anything the AI writes on Telegram only behind the words switch, AI only through the existing writing paths to the creator's own provider) are not preferences.
5. No new section: the Telegram panel (Settings, Local security), Your collection (From your record) and Brand, Writing are extended.

## What phase 6 starts from (evidence)

Each read in the code at `6c1bba2`, not taken from the brief.

- `collection.related(text, limit)` scores the new items with words (the kinds of `collection.MATERIAL`) by how many of the draft's meaningful words (four letters or more, not a common word, `_keywords`) their words or tags share, most shared first, then newest. Its one caller is `POST /api/v1/collection/related`, which only the Composer's From your collection reads, with a fixed three and any one shared word. Neither the bot nor Your collection uses it.
- "Saved to your collection." says nothing about the rest of the collection. Its buttons are Write it up, the angles, Remind me, Remember this (a note or an idea that fits) and Undo (`telegram_bot.item_rows`).
- The morning idea (phase 3) offers one unused item a day, only with the words switch on: the one offered least recently, never-offered items first (`collection.least_offered`). It never says how old an item is, takes no age, offers no Remind me, and an item offered once waits behind every item never offered, so an old idea once offered rarely comes back. Nothing else brings an old unused idea back unless the creator pressed Remind me on that one item. The tour (phase 5) has no step for the morning idea, so "offered in the tour like the morning idea" has nothing to copy: both are added.
- `/recall` alone answers "Send /recall with a word, for example /recall pricing." (`SENTENCES["empty_recall"]`). There is no way on the phone to see the newest unused items, or what the studio remembers: `/remember` and `/forget` exist, and no list.
- A plain reply to "Draft ready in your studio." is saved as a new note: `ingress._add_to_replied` finds the item a message is linked to through `collection_messages`, and a draft's message is linked to no item (`_start_job` puts it with its buttons only), so `item_for_message` finds nothing and `_store` keeps the words as an unrelated note. The bot already finds the draft such a message is about, by Telegram's id for it (`telegram_bot.post_of_message`, phase 5, for `/plan`), for the kinds `draft`, `reshaped`, `plan` and `planned`.
- A rewrite from the phone (`writing.reshape`, phase 4) refuses any post that is not a plain draft, so a draft planned from the phone (queued, `made_with.planned`) cannot be rewritten, though nothing has posted it.
- `BOT_COMMANDS` holds eleven commands; 2.14.0's menu record keeps their names (phase 5), and `EARLIER_COMMANDS` holds only `COMMANDS_2_13`.
- Found while reading, outside the bot: the Composer's note "What this draft was written from" (`MadeWithNote` in `ComposerCollection.tsx`) reads `made.items.length` and `made.remembered.length` for any post whose `made_with` is set. A draft saved and planned with `Schedule <when>:` (phase 5, item 6) has a `made_with` holding only `planned`, and one unplanned with Undo holds `{}`. The Queue's **Edit text** opens such a post in the Composer (`App.tsx`, `onEditText`), where those reads throw, and the interface has no error boundary. Fixed first, with a browser test (below).
- Found by the record of phase 4, still open: `tests/test_privacy_page_is_the_policy.py` puts `tools/` first on `sys.path`, and `tools/library_bundle.py` then shadows the backend's `library_bundle` for a run that imports `app` after it. Running `tests/test_privacy_page_is_the_policy.py tests/test_telegram_bot_commands.py` together errors with `module 'library_bundle' has no attribute 'MAX_BYTES'` (reproduced on `6c1bba2`). Other test files insert `tools/` first at import (`tests/test_licensing.py` among them), so the pair is one of several.

## Telegram's rules this phase relies on

Each quoted from the Bot API page (https://core.telegram.org/bots/api), checked again on 2026-11-03. The suite's fake Bot API (`tests/telegram_fake.py`) holds the same rules; nothing in the suite reaches Telegram.

- A reply carries `reply_to_message`: "For replies in the same chat and message thread, the original message." A `message_id` is "Unique message identifier inside this chat; 0 for ephemeral messages."
- An inline button's `callback_data` is "Data to be sent in a callback query to the bot when the button is pressed, 1-64 bytes". Each button's data here is a 12-character id, a dot and at most three characters.
- "After the user presses a callback button, Telegram clients will display a progress bar until you call answerCallbackQuery." Its `text` is "Text of the notification. If not specified, nothing will be shown to the user, 0-200 characters." Every notice is one of the bot's fixed sentences, each at most 200 characters (phase 1's rule).
- sendMessage's `text` is "Text of the message to be sent, 1-4096 characters after entities parsing". A list is cut to the creator's "The bot lists at most", each line to 300 characters, so it stays far under.
- A command is "Text of the command; 1-32 characters. Can contain only lowercase English letters, digits and underscores." Its description is "Description of the command; 1-256 characters".
- editMessageText's `reply_markup` is "A JSON-serialized object for an inline keyboard": a press replaces a message's words and buttons in place.
- Incoming updates "will not be kept longer than 24 hours" (phase 4's notice, unchanged).

## The items

A chore and five items in the brief's order, the fifth if budget allows. One commit each, each with a failing test first and one guard falsified; the Composer fix found while reading is a commit of its own before item 1.

### 0. Chore: any set of test files runs together

- **Built:** the backend's `library_bundle` is bound once, in `tests/conftest.py` at `pytest_configure` (after the session's sandbox home is set, so `database` binds no live path), so a test file that puts `tools/` first on the path can no longer shadow it. The vendor tool `tools/library_bundle.py` is never imported as a module (it is run as a command, and itself imports the backend's), so nothing loses its module. The privacy page test stops putting `tools/` on the path at all: it loads the renderer by its file.
- **Test first:** a test runs, in a fresh process with its own home, `tests/test_privacy_page_is_the_policy.py` and then one test of `tests/test_telegram_bot_commands.py`, and `tests/test_licensing.py` then the same test, and expects both to pass. Both fail on `6c1bba2`.
- **Decided against:** renaming `tools/library_bundle.py` (its command is in the vendor's own notes); changing every test that inserts `tools/` (the binding protects any future one too).

### Found while reading: the Composer opens a draft planned with `Schedule`

- **Built:** "What this draft was written from" reads a draft's record whatever it holds: the line "Written by ..., from N items" only for a draft the studio wrote (a provider, items or one of today's ideas recorded), the earlier texts a rewrite replaced for any draft that has them, the things to remember only when some went with it, and nothing at all for a record with none of these (a plan alone).
- **Test first:** in a browser, a draft saved by `Schedule tomorrow 09:00:` from the fake bot, opened from the Queue with **Edit text**, shows its words in the Composer; fails on `6c1bba2` with the page error the throw makes. Axe in both themes.

### 1. It connects to, in real time

- **Built:** one engine in `collection.py`, `connections(item)`, beside `related` and sharing its scoring: the other unused items with words (status new, a kind of `MATERIAL`, never the item itself) that share at least the creator's "Words two items share to be connected" of their meaningful words and tags with it, most shared first, then newest; with how many there are, the first "Connected items offered with one" of them, and the words they share most. Matched on the computer; nothing leaves it.
- **On the bot:** when something with words is saved, "Saved to your collection." (and the bookmark's answer) adds "It shares words with 3 other unused items in your collection." With the words switch on, their first lines follow, numbered, the offered ones only ("The 3 that share the most:" when more connect). The answer carries **Write one post from these**, /recall's button: pressed, it writes one draft from the item and the items it connects to, read again at the press (still unused, still sharing the words), at most "Connected items offered with one" of them and never more than "Most items in one draft" in all, through Combine, beside the loop, as /recall's press does, and says how many ("Writing one post from 4 items in your collection."). An item used, set aside or removed since, or with nothing unused left to connect to, is said, and nothing is written. The draft records `connected: true` with `via: telegram`.
- **In Your collection:** each new item with words that connects says "Shares words with 3 other unused items: pricing, page" with **Open the group**, which shows the item and the ones offered with it, with **Combine these 4 into one post** (Combine's own path) and **Back to your collection**. The group is `GET /api/v1/collection?around=<id>`, a parameter on the box's own path: no new path.
- **Preferences:** in Brand, Writing (the engine is the box's and the bot's): **Words two items share to be connected**, 2 (1 to 5), because one shared word ("today", "really") connects notes that have nothing else in common, while two ("pricing" and "page") rarely do; **Connected items offered with one**, 3 (1 to 9), what the bot lists and writes with an item, and what the box's group holds. In the Telegram panel: **Say what something new connects to**, on, because it adds a line and one button to an answer the bot already sends and never a message of its own, the line is a count, and first lines go only with the words switch on, as everything else the bot sends from the collection.
- **Stored:** nothing new: the groups are worked out when asked; the press's message keeps the item's id with its buttons, as every item's answer does.
- **Leaves the machine:** a count to Telegram; first lines only with the words switch on; on a press, the items' words to the creator's own provider, as Combine and /write send them.
- **Tour and seen working:** a step "Send an idea that shares words with others ..." in "make something of it"; the panel's line "A draft written from what an idea connects to", from a draft whose `made_with` records `connected` and `via: telegram`.
- **Decided against:** a message of its own when a later item connects to an earlier one (a new message the creator did not ask for); a connection to a used or set-aside item; numbered Write up buttons under the saved answer (Write it up is already there); changing the Composer's From your collection, which ranks by shared words and shows three, as phase 3 chose, and which these preferences do not govern (named in the record as a candidate for later).

### 2. Bring back an unused idea

- **Built:** off by default. On the days and at the hour the creator picks, between polls, the bot brings back one unused item with words older than the creator's age: oldest first; never one set aside, already used, or with a reminder waiting; never the one it brought back last time, nor the one the morning idea offered last, so neither repeats the other in a row. With the words switch on: "Back from your collection: an idea you saved 22 days ago, on Mon 12 Oct, and have not used yet." and its first line; off, that line alone, which says only its kind and its age. Under it, **Write it up**, **Remind me** and **Not now**, each acting as it does under a reminder (Remind me sends the moments, Not now sets it aside while it is new); a reply to it adds to the item.
- **Rules:** told once a day it is due (`telegram_told`, `back:<day>`, as the morning idea's day key), and a day with nothing to bring back is marked all the same; held by quiet hours, as every notification is (nothing is looked at while it is quiet, so it goes at the first check after); a moment before it was turned on or changed does not count (`since`, as the morning idea); told only to a paired chat, under the worker's check lock for the bot it was made with, so a bot removed meanwhile keeps nothing. The item brought back is marked offered (`offered_at`), so the morning idea's least-offered order passes over it.
- **Interface:** in the Telegram panel, under "WHAT THE BOT TELLS YOU, EACH ONLY IF TICKED": **Bring back an unused idea**, its days, its hour and "older than", and "NEXT ONE BROUGHT BACK:" with the moment, worked out as the weekly summary's is.
- **Stored:** the setting (`telegram_bring_back`: on, days, hour, older, since); which item was brought back last and when (`telegram_brought_back`), removed with the bot and by Delete everything.
- **Leaves the machine:** the kind and the age; the first line only with the words switch on.
- **Preferences:** **Bring back an unused idea**, off; **on these days**, Friday, and **at**, 16:00 on the computer's clock: once a week, near the end of the working week when next week is planned, and clear of the morning idea (08:00) and the weekly summary (Monday, 09:00); **older than**, 14 days (3, 7, 14, 21, 30, 60 or 90): two weeks is past the week an idea is fresh in, and short of the month after which it is forgotten.
- **Tour and seen working:** steps for this and for the morning idea in "plan it and come back to it", each saying where to turn it on; the panel's line "An unused item brought back to your phone", from `telegram_brought_back`. The morning idea's step is not listed in the panel: a day marked told does not prove an idea went.
- **Decided against:** more than one a day; bringing back an item without words (it has nothing for Write it up); its own quiet hours (the bot's are one setting); a count of how many are waiting in the message (the weekly summary says it).

### 3. See what you have from the phone

- **Built:** `/recall` alone lists the newest unused items, up to "The bot lists at most": with the words switch on, "23 unused items wait in your collection." then "The newest 5:" and their first lines, numbered, an item without words said as its kind ("a photo, with no words"), with **Write up 1** and so on for each with words, each acting once as under /recall's list; off, the count and "See them in your studio, under From your record, Your collection." with no button. `/recall pricing` is unchanged.
- **A new command, `/remembered`:** the things the studio remembers for its writing. With the words switch on, "Your studio remembers 4 things for its writing." and the newest of them, each with what it is about ("About you: I write for founders"), numbered, up to "The bot lists at most", with **Forget 1**, **Forget 2** and so on: a press removes that one, as `/forget` does, and its button goes while the others stay. One left out of writing by Brand's "Which go with writing" is said so. Off: the count and "See them in your studio, in Brand, under Writing, Things to remember." The name is 10 lowercase letters, within Telegram's 1 to 32.
- **The menu:** `/remembered` is added to `BOT_COMMANDS`, and `/recall`'s description now names both forms. 2.14.0's list is frozen word for word as `COMMANDS_2_14` and added to `EARLIER_COMMANDS`, so a menu record kept by 2.14.0 is recognised by its names or, failing those, its fingerprint, and the one-time notice after this upgrade names only `/remembered`.
- **Stored:** with the list's buttons, the ids of the items or things listed, as /recall's list keeps them.
- **Leaves the machine:** counts; first lines and the things' words only with the words switch on.
- **Preferences:** "The bot lists at most" (phase 5), now read by both lists too.
- **Tour:** a step in "build it up and keep it". Neither list leaves anything in the studio, so the panel does not list them (a Forget leaves an absence, never evidence).
- **Decided against:** Write one post from these under `/recall` alone (the newest items share nothing but their age); an Undo under Forget (the list showed its words, and `/remember` keeps it again); listing a thing's use counts.

### 4. Reply to a draft with what to change

- **Built:** a plain reply (text, not a command, a file or a forward) to one of the bot's messages about a draft ("Draft ready", a rewrite, the times Plan it offers, a plan) is no longer filed as a note. The bot answers "Press Rewrite it with what you said to have your AI provider rewrite the draft with your words, or Keep it as a note.", with **Rewrite it with what you said** and **Keep it as a note**, whatever the confirmations switch says (it is a question, as a command's answer is). The reply's words are kept with that message's buttons until one is pressed, then dropped from it.
- **Rewrite it with what you said:** rewrites that draft beside the loop through the creator's own provider, as a rewrite button does (`writing.reshape`'s path): the draft as it is now, the notes it was written from, the things to remember as chosen and the writing preferences, with the creator's words as the instruction in place of a button's. Kept only if it passes the check every draft passes (a figure or a name in the creator's own reply counts as theirs), and only while the draft is unchanged since it was read: one conditional update. The text it replaced is kept on the draft for Undo, as a rewrite's is, said in the Composer as "before your reply". With the words switch on: "Rewritten in your studio as you asked. It begins:" and the first line, with the draft's buttons and **Undo**; off, "Rewritten in your studio as you asked." with **Plan it** and **Undo**, which carry no words. With no provider, the offer says so first ("This needs an AI provider, and none is connected yet: connect yours on the Composer's Prompt tab in your studio, then press Rewrite it with what you said.") and a press says it again, its buttons staying, so it works once one is connected.
- **Keep it as a note:** the words saved as a note, as a reply was before, linked to the reply so a reply to it adds to it and an edit follows it; the message then says "Saved to your collection." with the item's buttons.
- **A planned draft:** a draft planned from the phone is still the creator's draft until it comes due, so it may be rewritten, by a reply or a rewrite button, while it is still queued at its planned time and no one handed it to LinkedIn; its plan is kept, and Undo puts the text back on the same terms. A post queued at the desk, due, published or held by LinkedIn is not rewritten, as now.
- **Preference:** **What a reply to a draft does**, in the Telegram panel: "Offer to rewrite the draft with it" (the default: a reply under a message about a draft is about that draft, as a reply under an item adds to that item, and nothing is rewritten until the press, while Keep it as a note keeps the old behaviour one press away), or "Keep it as a note", as until now.
- **Stored:** the reply's words with the offer's buttons until a press; the replaced text on the draft (`made_with.earlier`, the ten newest, as phase 4 keeps them).
- **Leaves the machine:** on the rewrite press, the draft, its notes, the things to remember as chosen, the preferences and the reply's words, to the creator's own provider; to Telegram, the result's first line only with the words switch on.
- **Tour and seen working:** a step in "make something of it"; the panel's line "A draft rewritten with your reply", from an earlier text kept "before your reply".
- **Decided against:** rewriting at the reply itself, without a press (a "thanks" under a draft would rewrite it); following an edit of the reply into the offer; a reply to a due post's message (its post is no longer a draft); a limit on the reply's length beyond Telegram's own.

### 5. If budget allows: a series from a group

- **Built:** **Write it as a series** under /recall's answer for a word (beside Write one post from these) and in Your collection's group: one request to the creator's provider for the creator's number of posts as a series from the group's unused items, each a post of its own that stands alone and leads to the next, each checked as a draft is and all kept or none; each saved as its own draft, recording its part (`made_with.series`: the series, its part, how many). The bot answers "A series of 3 drafts is ready in your studio." (with each part's first line only with the words switch on) and **Plan the series**, which puts the parts into the Queue's next open slots in order, each the Queue's cooldown from every other post and after the part before, through Plan it's own path (`phone_plans.plan`, never Send to LinkedIn; the scheduler only marks posts due), with **Undo**. Too few open slots in two weeks plans nothing and says so.
- **Preference:** **Drafts in a series**, 3 (2 to 5), in Brand, Writing: three is the shortest series with a beginning, a middle and an end.
- **Decided against:** a series from the saved answer itself (its buttons are already many); planning with the creator's own times (two of them on one day break the Queue's spacing rule); keeping the parts that pass when one fails the check (a series with a hole is not the series asked for).

## Migrations, and why

None. Every new preference is a settings row or a field of the writing preferences' row; which item was brought back last is a settings row; a group is worked out when asked; a reply's words wait with their message's buttons, as /recall's word does; a series is a key on each draft's `made_with`. The schema stays 43.

## Preferences added

| Preference | Default | Set in | Read by |
| --- | --- | --- | --- |
| Words two items share to be connected (`connect_shared`) | 2, from 1 to 5 | Brand, Writing | the bot's saved answer, Your collection |
| Connected items offered with one (`connect_offer`) | 3, from 1 to 9, and never more than Most items in one draft with the item | Brand, Writing | the bot's saved answer and its press, Your collection's group |
| Say what something new connects to (`telegram_connect`) | on | the Telegram panel | the bot's saved answer |
| Bring back an unused idea (`telegram_bring_back`) | off; Friday, 16:00; older than 14 days (3, 7, 14, 21, 30, 60 or 90) | the Telegram panel | the bot, between polls |
| What a reply to a draft does (`telegram_draft_reply`) | offer to rewrite the draft with it | the Telegram panel | a reply to the bot's message about a draft |
| Drafts in a series (`series_parts`), with item 5 | 3, from 2 to 5 | Brand, Writing | Write it as a series |

"The bot lists at most" (phase 5) is now read by `/recall` alone and `/remembered` too. Each control shows its default beside it; each is tested: changing it changes what the bot or the box does, a wrong value is refused with a sentence and nothing is saved, and a fresh profile gets the default.

## What may go where

| What | To Telegram | To the AI provider | Kept |
| --- | --- | --- | --- |
| A connection | a count; first lines only with the words switch | the group's words, on a press | nothing new |
| An idea brought back | its kind and age; its first line only with the words switch | its words, on Write it up | the setting, the last item brought back |
| `/recall` alone, `/remembered` | counts; first lines and the things' words only with the words switch | never | the ids listed, with the buttons |
| A reply to a draft | the offer, the product's words; the result's first line only with the words switch | the draft, its notes, the things to remember as chosen, the preferences, the reply's words, on a press | the reply's words until a press; the replaced text on the draft |
| A series | a count; first lines only with the words switch | the group's words, on a press | each part on its draft |
| Another person's name or words | never | never | never |

## Sections

No new section, per the owner's rule. The Telegram panel gains three switches or choices; Your collection gains the connection line, the group and its Combine; Brand, Writing gains two preferences (three with item 5); the Composer's note is made to read every record. No new API path: the group is a parameter of `GET /api/v1/collection`, and the census in `tests/test_endpoint_reachability.py` stays 242/194/48.

## Tests

The fake Bot API runs as phase 5 left it; the writing runs against the fake provider (`tests/ai_fake.py`). Each item: a failing test first, the code, one guard falsified, one commit; each new test file run three times in a row before its commit, with the Telegram, collection, phone, ingress and memory suites whole. Data is put in place before the switch that acts on it (a setting's `since` written on its row), the bot's clock is never moved while the worker runs, a button's answer is read only after waiting for it, and no small timing is compared. A browser test with axe in both themes (the shared helper, which stills transitions) for each new control, waiting for a settled page, and `tools/ui_audit.py` at 0 blocking on a fresh install. At the end, the interface built, then one full suite as CI runs it, with flake8 and `tools/sync_version.py --check`.
