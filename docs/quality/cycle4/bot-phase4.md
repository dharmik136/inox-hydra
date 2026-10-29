# The Telegram bot, phase 4: nothing lost quietly, the / menu, and posts shaped from the phone

Written before any of its code (2026-10-30). Branch `qc4/bot-phase4`, from `8962bce` (2.12.0, schema 40). It says, for each item, how it will be built, where it lives in the interface, what is stored, what may go to Telegram or the AI provider and under which switch, which preferences it adds with their defaults, and what was decided against. The record of what was built is a "Phase 4" section of [the bot's record](telegram-bot.md), written as each item is committed.

## The owner's words, and the reading built here

Asked on 2026-10-30: "see what more can be done in it". Standing since phase 3:

- "no as this will be used by single person they can have this one of this colloectioc box having everything here in one bot also that is way much more real time ideas and efeatures are needed here on the bot and on our product to make soething out of thiose things and remember thme for some things"
- "do not hardcode tings are they will be users prefernce in AI work"
- For the interface: "things in sections only, but each section properly optimised".

Read as:

1. The bot stays one person's one collection box, and it must never mislead: what the panel says about it, and what the creator believes reached the studio, have to be true.
2. More of what is sent is kept as it was sent (edits, replies, albums, files, links behind words), and more can be made from it on the phone (the whole post to copy, a rewrite, a draft from a word).
3. Every AI choice has a visible default the creator can change (Brand, Writing, or the Telegram panel), explained in plain words. A rule that keeps writing honest (only what was sent, no invented figure or person, no em dash) is a guarantee, not a preference.
4. No new section: the Telegram panel (Settings, Local security), Brand's Writing view, Your collection (From your record) and the Composer's note "What this draft was written from" are extended.

## What phase 4 starts from (evidence)

- `ingress.py` decides "seen working" from one settings marker (`telegram_chat_heard_at`) set when a message from the saved chat is saved. A studio that saved phone messages before the marker existed never had it set, so the owner's panel says "Not yet seen working on this computer: no message from your own chat has been saved here" beside a collection of messages from that chat. False on screen.
- The poll asks for `message` and `callback_query` only: an edit, an album's grouping, a reply's target and a message's entities (a link behind words) are not read, and setMyCommands is never called. A sticker, a file or a video is answered "That message had no text, so nothing was saved."
- Nothing tells the creator that Telegram keeps a bot's incoming messages for at most a day, so a message sent while the computer is off for longer is gone without a word.
- A failed check is logged twice ("Polling error", then "Worker loop error"), and a long poll that times out while Wi-Fi reconnects (hourly on the owner's machine) is logged as an error.

## Telegram's rules this phase relies on

Each quoted from the Bot API page (https://core.telegram.org/bots/api), checked on 2026-10-30. The suite's fake Bot API (`tests/telegram_fake.py`) holds the same rules; nothing in the suite reaches Telegram.

- getUpdates: "Incoming updates are stored on the server until the bot receives them either way, but they will not be kept longer than 24 hours." An offset confirms every update below it. allowed_updates is remembered: it does not affect updates created before the call.
- An edit arrives as `edited_message`, "New version of a message that is known to the bot and was edited", only if the poll asks for it.
- Photos sent together arrive as separate messages sharing a `media_group_id`.
- A reply carries `reply_to_message`, which "will not contain further reply_to_message fields".
- A link behind words is a `text_link` entity with its `url`; entity offsets and lengths are in UTF-16 code units.
- A bot can download files of up to 20 MB (getFile); the link is valid for at least an hour.
- A GIF arrives as an `animation`, and "for backward compatibility, when this field is set, the document field will also be set"; a round video message (`video_note`) carries no file name and no type. A `message_id` of 0 is an ephemeral message, which cannot be linked to.
- One message is 1 to 4096 characters after entities parsing; a caption is 0 to 1024.
- An inline button's callback_data is 1 to 64 bytes.
- setMyCommands takes up to 100 BotCommand (command: 1 to 32 characters, lowercase English letters, digits and underscores; description: 1 to 256 characters) and a scope; BotCommandScopeChat names one chat, and a chat's own list wins over the default one. deleteMyCommands takes the same scope.

## The items

Twelve, in the owner's order, one commit each, each with a failing test first and one guard falsified.

### 1. Seen working, truthfully

- **Built:** the panel's answer comes from what this profile holds. "Seen working" is the marker as before, or else anything saved here from Telegram since the chat was paired: an item in the collection, a thing to remember, an ask. Only the paired chat's messages are ever saved, so each of these came from it. Found once, the marker is set to that thing's time, so the answer stays when the item is later removed. From now on the moment a chat is paired is kept (`telegram_chat_paired_at`), so after a change of chat only what came after it counts, as the marker's own rule says ("a message from one chat says nothing about another"). A chat paired before this build has no such moment, and then anything saved from Telegram counts.
- **Interface:** the panel's orange sentence goes away; no new control.
- **Stored:** one settings row, the pairing moment (a time), removed with the bot.
- **Leaves the machine:** nothing.
- **Preferences:** none.
- **Decided against:** reading the log for evidence (it keeps refused chats, never saved ones); counting a message refused before pairing.

### 2. Nothing lost silently while the computer is off

- **Built:** the worker keeps the time of the last successful check (a getUpdates Telegram answered), in memory and in the bot's profile (`telegram_checked_at`), written at most once a minute and when the worker stops, so it survives a restart; the write wakes no window (it is announced as derived, not as a change to read). When a successful check comes more than 24 hours after the one before, whether the computer was off, asleep or offline, the studio keeps one notice (`telegram_gap`: the last check before, this check, and the moment 24 hours before this check) and tells it once on the bot and in the panel:
  > Your studio did not check Telegram for your messages from Thu 29 Oct, 18:02 until Sat 31 Oct, 09:15, on your computer's clock. Telegram keeps a bot's messages for one day, so anything you sent before Fri 30 Oct, 09:15 may not have arrived. Send again whatever is missing from Your collection.

  It never says a message was lost, and never gives a count: the studio cannot know either. A bot whose token changed starts with no last check, since another bot's history says nothing about this one.
- **Quiet hours, decided:** the bot's message waits for quiet hours, like the notifications: it is something the bot says unasked, and the panel shows it at once, so nothing is hidden meanwhile. It does not wait for any notification switch (it carries only times, and a creator who ticked nothing needs it most), and it goes only to a paired chat.
- **/status** adds when the studio last checked before that message, as a time and how long ago, so a /status sent while the computer was off is answered with the gap.
- **/help** and the help pages say the studio must run at least once a day.
- **Interface:** in the Telegram panel, a row "Last checked Telegram" and, while there is a notice, the notice with **Got it** (`POST /api/v1/ingress/gap/seen`, one new path, reached by the panel).
- **Stored:** two settings rows, a time and the notice (times only), both removed with the bot.
- **Leaves the machine:** one fixed message to the paired chat carrying three times, under no switch beyond pairing.
- **Preferences:** none. The day is Telegram's rule, not a choice.
- **Decided against:** a count or a list of what may be missing; saying anything when the gap is under a day (Telegram still holds it all); a webhook (it needs an open port, which the studio never opens).

### 3. The "/" menu

- **Built:** one list of the bot's commands, each with a description in plain words (`telegram_bot.BOT_COMMANDS`), from which /help's lines about commands are written, so the two cannot differ. After a successful check, with a chat paired, the worker compares a fingerprint of the chat and the list with the one kept (`telegram_menu`), and only when they differ calls setMyCommands with the scope of the paired chat (BotCommandScopeChat), through `telegram_bot.call`: the egress check under `ingress`, counted as `.../bot<token>/setMyCommands`. Kept only when Telegram answers ok; a refusal is tried again after ten minutes, never at every poll. So it registers when pairing completes and when a new build changes the list, and is not re-sent at every start. When another chat is paired, the earlier chat's menu is taken away (deleteMyCommands, its scope); when the bot is removed or replaced in the panel, its menu is taken away, best effort.
- **Interface:** a row in the Telegram panel, "The / menu in your chat": SET once Telegram took it.
- **Stored:** one settings row: the fingerprint, the chat and when.
- **Leaves the machine:** the command names and their descriptions, the product's own words, for the paired chat only. No switch: the owner asked for the menu, and it carries nothing of the creator's.
- **Preferences:** none.
- **Decided against:** the default scope (anyone who finds the bot would see its menu); a list per language; registering at every start.

### 4. Post from the phone: copy and post

- **Built:** while "The bot may send me what it writes from my collection" is on, "Draft ready in your studio. It begins:" carries **Send me the whole post**, and so do "A post in your queue is due now." and its reminder (**Send me the posts** when several are due). A press sends the post's text as the studio holds it now (an edit at the desk included) as a message of its own with nothing of the bot's around it, so long-press, Copy gives exactly the post to paste into the LinkedIn app. Longer than Telegram takes in one message (4096 characters, counted as Telegram counts them), it is split on paragraph boundaries (then lines, then spaces), each part beginning "Part 1 of 2". The press keeps the message's other buttons. With the switch off the button is not offered, and a press on an older message says why. Nothing is posted and nothing reaches LinkedIn.
- **Interface:** the words switch's description says it now carries the whole post on request.
- **Stored:** nothing new: the button's record names the post by its id, never its words.
- **Leaves the machine:** the post's whole text, under the words switch, on the creator's press.
- **Preferences:** none.
- **Decided against:** a link that opens LinkedIn with the text filled in (LinkedIn's share address and its parameters are not documented for this, and the rule is copy and post); sending the post's image.

### 5. Shape a draft from the phone

- **Built:** under a draft the bot wrote (words switch on), one button per rewrite the creator keeps: by default **Shorter**, **New opening** and **Another angle**. A press is answered at once ("Rewriting it in your studio.") and the rewrite runs beside the bot's loop, never in it, as Write it up does. It sends the creator's own provider (the `model` category) the draft as it is now, the notes it was written from, the things to remember as chosen, the voice block, the writing preferences and the button's own instruction; the answer is kept only if it passes the grounding check every draft passes (no figure, and no person the studio knows of, that is not in what was sent), and is refused, never repaired, otherwise. The draft changes in place only while it is still a draft and unchanged since the rewrite read it (one conditional update); a draft changed at the desk, queued or published is left as it is, and the bot says so.
- **The earlier text:** the Composer keeps no versions, so each rewrite keeps the text it replaced on the draft (`posts.made_with`, its "earlier" list, the ten newest). The Composer's "What this draft was written from" lists them, each with **Put it back in the editor**, which the creator then saves as usual; the bot's answer carries **Undo**, which puts the earlier text back while the draft is as the rewrite left it. An open Composer with no unsaved change shows the new text; with unsaved changes its next save is refused as changed elsewhere, as today, with Keep this version.
- **Answers:** "Rewritten in your studio (Shorter). It begins:" and the new first line, with Send me the whole post, the rewrite buttons and Undo. No provider: the existing `no_provider` answer, and nothing is asked.
- **Preferences:** `reshapes`, the rewrite buttons: each a label (at most 24 characters, to fit a button) and what it asks for (at most 200 characters), at most six, none allowed. Defaults: Shorter, "Make it about a third shorter. Keep its point, its first line and its voice."; New opening, "Write a new first line for it, as the opening line preference says. Keep the rest as it is."; Another angle, "Rewrite it from another angle on the same notes, at about the same length." Set in Brand, Writing, each with its default shown; named on the Telegram panel beside the words switch.
- **Stored:** the earlier texts on the draft (the creator's own words), counted, exported, forgotten and backed up with the draft.
- **Decided against:** rewriting with the words switch off (the creator could not see the result); a new draft for each rewrite (it fills the drafts list, which phase 3 stopped); version history for every save in the Composer, which is another feature.

### 6. Build an idea up over the day

- **Built:** each message saved from the phone is linked to the item it made, by its chat and message id, and so is each of the bot's answers about an item, once Telegram says it took it (the morning idea included). A Telegram reply from the paired chat, to one of the creator's earlier messages or to the bot's answer about one, adds its words to that item, as a part of its own, instead of making a new item; the item's words are its parts joined by a blank line, and the box shows the change at once. The bot answers "Added to the item in your collection." (with the words switch on, "Added to:" and the item's first line), with **Undo**, which takes the added words back off while the item has not been used since. If the item already became a draft, the words still go on the item, and the bot adds "The draft made from it was not changed." A command in a reply is a command; a photo or a file in a reply is an item of its own; a reply to something no longer in the collection makes a new item.
- **Interface:** an item built from several messages says so in the box ("From 3 of your messages").
- **Preferences:** "A reply adds to what it replies to", on by default, in the Telegram panel. Off, a reply is an item of its own.
- **Stored:** migration 41, a table linking messages to items (below).
- **Leaves the machine:** nothing new; the first line only under the words switch.
- **Decided against:** matching a reply by its date or its words; adding a photo to an item by replying with it.

### 7. Edits follow

- **Built:** the poll asks for `edited_message` too. An edit from the paired chat of a message that made an item, while the item has not been used, becomes its words (read as the message was: a prefix such as Idea: or a command such as /idea taken off), live in the studio. Once the item has been used, the draft is kept as it is, the item takes the edit and says it was edited after it was used, and the bot says the draft was not changed. An edit from any other chat is refused like a stranger's message. An edit of a message that made nothing (a command, a refused message) changes nothing, and the bot says so. An edited link makes no new request.
- **Answers:** "Updated in your collection." and, once used, "Updated in your collection. The draft made from it was not changed.", under the confirmations switch, as any answer to a message.
- **Interface:** an edited item says "Edited on your phone" in the box.
- **Stored:** the edited words and when, in migration 41's table, and the item's words.
- **Decided against:** following an edit into a draft.

### 8. Remember this

- **Built:** under "Saved to your collection.", for a note or an idea whose words fit a thing to remember (300 characters), **Remember this** keeps its words as a thing to remember (about you, or what a prefix such as `offer:` says, as /remember reads it), sets the item used ("Kept in your things to remember"), and answers with **Undo**, which removes the fact and puts the item back to new. The fact names the item it came from (`origin_ref`), so no table changes.
- **Leaves the machine:** nothing; the fact goes with writing as the memory preference says, as every fact does.
- **Decided against:** Remember this on a forward (someone else's words), a link or a file.

### 9. `/write <word or #tag>`

- **Built:** one draft from the unused items (new, with words) that hold the word, or carry the tag, newest first, through the existing Combine path (one item: Make a post), beside the loop. "Writing one post from 3 items in your collection.", then "Draft ready" as Write it up answers, with its buttons. Nothing matches: "Nothing new in your collection holds that word, so nothing was written." No provider: `no_provider`. Answered whatever the confirmations switch says, as a question is.
- **Preferences:** `combine_at_most`, "Most items in one draft": today's fixed ten (`COMBINE_AT_MOST` in `writing.py` and in `CollectionPanel.tsx`) becomes a preference, default 10, from 2 to 20, set in Brand, Writing, read by Combine in the box and by /write.
- **Decided against:** writing from used items; asking on the phone which items to use.

### 10. Everything in one box, kept as it is, never read

- **Built:** photos sent together (one `media_group_id`) arrive as one item: the first makes it, the rest join it, and the caption, from whichever carries it, is its words. Documents (a PDF or any other file, a music file among them) and videos (a video, a round video message, a GIF Telegram sends as a video) are kept as photos and voice notes are: getFile, then the file, each through the egress check under `ingress` and counted without the token, under `assets/phone` by a random name. The file's own name is kept, to show and to download under. Over Telegram's 20 MB: "That file is larger than your studio keeps from the phone (20 MB), so nothing was saved." Never read: no text taken from a PDF or a picture, nothing transcribed. Stickers, locations and contacts keep today's plain answer.
- **Shown safely:** the stored name's extension comes from a short list (a PDF, an image other than SVG, an MP4, WebM or QuickTime video, a sound file, plain text); anything else is kept as a download only, served as bytes, never opened in the studio's own window.
- **Interface:** Your collection's kind filter gains Documents and Videos; a document shows its name and size with View (a PDF) or Download, a video plays. **Add to your media library** is offered only for what the library takes, by its own upload rules: a photo or an image file (PNG, JPEG, WebP), a PDF (as a document carousel), an MP4 or WebM video.
- **Stored:** migration 42 (below); the files in the profile's media folder, counted, backed up, and deleted with everything else as photos are.
- **Leaves the machine:** nothing is sent; the files come in from Telegram.
- **Decided against:** a local Bot API server for files over 20 MB; reading any file; keeping a sticker, a location or a contact.

### 11. Text kept whole

- **What `collection.py` already derives:** a message's hashtags as its tags (lower case, each once, up to 30), a topic from them or the creator's own topics, and every LinkedIn post link rebuilt from its id. Hashtags already become tags; this item does not add them again.
- **Built:** a link hidden behind words (a `text_link` entity, offsets in UTF-16) is written into the item's words right after the words it hides behind, so it is kept, shown, found and written from; a LinkedIn post link behind words is treated as a visible one (one of the creator's posts: Today; anyone else's: a bookmark without its slug). A caption's entities likewise. `/recall #tag` matches the item's tags, as well as its words.
- **Stored:** nothing new.
- **Decided against:** keeping bold, italic and other formatting; a separate column of links.

### 12. One line per failed check

- **Built:** a failed check is logged once, by the check itself; the loop no longer logs it again. A long poll that timed out, or a connection that dropped, is a warning (it happens whenever Wi-Fi reconnects); anything else is an error. The token is never in a line.

## Migrations, and why

- **Migration 41, with item 6:** `collection_messages`. Replies and edits name a message by its chat and message id, and nothing kept today holds that id: an item's `origin_ref` keys the update (its id and date) so it is kept once, and changing that key would let a message handled again across the upgrade be kept twice. One row per message: the item, the chat, the message id, whose it is (the creator's or the bot's), the words a message of the creator's gave the item, when, and when it was edited. The creator's own words and ids only. Counted in Storage with the collection, exported, deleted with everything else, kept in backups with the database.
- **Migration 42, with item 10:** `collection_items` rebuilt to take two more kinds, `document` and `video` (the kind is a CHECK constraint, which SQLite changes only by rebuilding the table: create, copy every row, drop, rename, indexes again, in one transaction), with `media_group` (an album's id, so its photos join one item).

Both appended to `MIGRATIONS`, forward only, re-runnable (each checks what is there first), each with a test that an older database gains it and a second run adds nothing, behind the automatic backup taken before any migration. Neither is named with a word an earlier migration's test finds it by.

## Preferences added

| Preference | Default | Set in | Read by |
| --- | --- | --- | --- |
| Rewrite buttons (`reshapes`): which appear, what each asks | Shorter, New opening, Another angle, each with its instruction (item 5) | Brand, Writing; named on the Telegram panel | the bot's rewrite buttons |
| Most items in one draft (`combine_at_most`) | 10 (today's fixed limit), from 2 to 20 | Brand, Writing | Combine in Your collection, /write |
| A reply adds to what it replies to | on | the Telegram panel | the bot |

Each is tested: changing it changes what the bot offers or what the fake provider receives, and a fresh profile gets the default.

## What may go where

| What | To Telegram | To the AI provider | Kept |
| --- | --- | --- | --- |
| The gap notice | three times, once per gap, to the paired chat; waits for quiet hours | never | settings, removed with the bot |
| The / menu | the command names and descriptions, the product's own words, for the paired chat | never | a fingerprint in settings |
| A post's whole text | on a press, under the words switch | never | as before |
| A draft's rewrite | its first line, under the words switch; the whole post on a press | the draft, its notes, things to remember as chosen, preferences, the button's instruction, on a press | the draft, and its earlier texts on it |
| A reply's words, an edit | the item's first line only under the words switch | only when something is written from the item | the item, and migration 41's table |
| Albums, documents, videos | never sent back | never | the media folder, the item |
| Another person's name or words, a forward's origin, a post's slug | never | never | never |

## Sections

No new section, per the owner's rule. The Telegram panel (Settings, Local security) gains the last check, the gap notice, the menu's row and one switch; Brand's Writing view gains two preferences; Your collection gains two kinds, an edited mark and a built-up mark; the Composer's "What this draft was written from" gains the earlier texts. One new API path (`/api/v1/ingress/gap/seen`); the census in `tests/test_endpoint_reachability.py` is re-measured in that commit.

## Tests

`tests/telegram_fake.py` gains what this phase meets: setMyCommands, getMyCommands and deleteMyCommands with Telegram's limits and scopes; edited messages; albums; documents and videos with getFile; replies; the message id each sendMessage answers with. The studio's own worker runs against it over loopback, and the writing against the fake provider (`tests/ai_fake.py`). Each item: a failing test first, the code, one guard falsified, one commit. A browser test with axe in both themes for each new control (the gap notice, the switch, the rewrite buttons, the most items, the earlier texts, the documents and videos), `tools/ui_audit.py` at 0 blocking. One full suite as CI runs it at the end, with flake8.
