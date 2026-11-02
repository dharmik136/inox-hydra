# The Telegram bot, phase 5: a guided first run, plans and reminders from the phone, and acting on what comes back

Written before any of its code (2026-11-02). Branch `qc4/bot-phase5`, from `b2f1754` (2.13.0, schema 42). It says, for each item, how it will be built, where it lives, what is stored, what may go to Telegram or the AI provider and under which switch, which preferences it adds with their defaults, and what was decided against. The record of what was built is a "Phase 5" section of [the bot's record](telegram-bot.md), written as each item is committed.

## The owner's words, and the reading built here

Asked on 2026-11-02: "continue". Standing since phase 3:

- "much more real time ideas and features are needed here on the bot and on our product to make something out of those things and remember them for some things"
- "do not hardcode things as they will be users preference in AI work"
- For the interface: "things in sections only, but each section properly optimised".

Read as:

1. The bot already does a great deal (eleven commands, sixteen buttons), and the owner has not yet tried phases 3 and 4 on the phone. A creator who pairs a bot is told nothing about what to try. The first item is a tour on the phone, and a panel that says, from what the studio holds, what has been seen working.
2. "Make something out of those things" now ends at "Draft ready": to plan it the creator goes to the desk, and what /recall finds, an item worth coming back to, and today's idea cards cannot be acted on from the phone. Items 2 to 5 close those loops, each through what the studio already has (the Queue and its due reminder, Combine, the collection, From your record).
3. Every count, time and set of buttons a feature offers is the creator's preference with a visible default, explained in plain words. The rules that keep the product honest (nothing posted for you, nothing invented, nothing about anyone else, the Queue's own spacing rule) are guarantees, not preferences.
4. No new section: the Telegram panel (Settings, Local security), Your collection (From your record) and the Composer's note "What this draft was written from" are extended.

## What phase 5 starts from (evidence)

- `docs/help/test-your-telegram-bot.md` is the only guide to what the bot does, and it lives in the studio's help. Nothing on the phone says what to try; /help lists commands, not what each shows.
- Under "Draft ready in your studio." the bot offers Send me the whole post and the rewrite buttons (words switch on) or nothing at all (off). Planning a post means opening the Queue. The Queue's scheduler (`scheduler.check_scheduled_queue`) only ever marks a queued post due; it posts nothing. The one queued post LinkedIn publishes itself is one handed over with Send to LinkedIn (`app.py`, which records `linkedin_holds:<id>`), a route nothing here calls. The due reminder (`telegram_bot.notifications`) is told only with "Tell me when a queued post is due" ticked.
- /recall answers with a count, and first lines with the words switch on; nothing in its answer can be pressed. /write writes one draft from the unused items that match.
- "Remind me in an hour" exists for a due post only. Nothing brings an item of the collection back at a moment the creator picks.
- From your record's daily cards (`record_daily`, `record_cards`) exist only on screen. The batch is built once a day by the scheduler's hourly job; the model's card comes on the creator's first open of the section.
- A latent race of the kind phase 4 fixed (3622105): `telegram_bot.register_menu` keeps the menu's record after setMyCommands returns, without the check lock, so a registration still waiting on Telegram when the bot is removed writes its record back for a bot that is gone. Item 1 extends that record, so it fixes the write first.

## Telegram's rules this phase relies on

Each quoted from the Bot API page (https://core.telegram.org/bots/api), checked on 2026-11-02. The suite's fake Bot API (`tests/telegram_fake.py`) holds the same rules; nothing in the suite reaches Telegram.

- A reply carries `reply_to_message`: "For replies in the same chat and message thread, the original message." It "will not contain further reply_to_message fields even if it itself is a reply", and "If the message is a reply to an ephemeral message, then this field may be omitted." A `message_id` is "Unique message identifier inside this chat; 0 for ephemeral messages."
- An inline button's `callback_data` is "Data to be sent in a callback query to the bot when the button is pressed, 1-64 bytes". The page states no limit on how many buttons a keyboard holds; rows here hold at most five.
- "After the user presses a callback button, Telegram clients will display a progress bar until you call answerCallbackQuery", whose `text` is "Text of the notification. If not specified, nothing will be shown to the user, 0-200 characters." Every notice here is one of the bot's fixed sentences, each at most 200 characters (phase 1's rule).
- editMessageText's `reply_markup` is "A JSON-serialized object for an inline keyboard"; editMessageReplyMarkup is "Use this method to edit only the reply markup of messages." A tour part replaces the one before it in the same message.
- sendMessage's `text` is "1-4096 characters after entities parsing".
- Incoming updates "will not be kept longer than 24 hours" (phase 4's notice, unchanged).

## The items

Five, in the owner's order, and a sixth if budget allows. One commit each, each with a failing test first and one guard falsified.

### 1. A guided first run on the bot

- **Built:** `/tour` sends the tour's first part as one message with buttons; **Next** replaces it in the same message with the next part, **Stop the tour** ends it, and the last part offers **From the start**. The parts follow the checklist's own groups, so there is no count to choose: send things in (an idea, a link to one of your posts, a photo or a file, and Undo); make something of it (Write it up, then under "Draft ready" Send me the whole post or a rewrite, and /write); build it up and keep it (a reply, an edit, /remember or Remember this); plan it and come back to it (Plan it, Remind me, /ideas and /recall, from this phase). Each step says what to send and what the creator will see, in the bot's own fixed words. A step that writes says, while no AI provider is connected, "This needs an AI provider, and none is connected yet: connect yours on the Composer's Prompt tab in your studio."; a step whose words come only with the words switch says so. A step the studio has seen working says so, from the same evidence the panel reads.
- **Offered once after pairing:** the "Paired." message carries **Start the tour**, and says so. It is sent once per pairing, as now.
- **Offered once after an upgrade that adds commands:** when the worker registers the "/" menu again for the same chat because the list changed, and the list Telegram held lacked some of today's commands, it keeps one notice ("Your studio was updated: your bot now also takes /tour, /plan and /ideas. ...") with **Start the tour**, told once outside quiet hours, as phase 4's gap notice is. The menu's record keeps the command names from now on; a record kept by 2.13.0 holds only a fingerprint, which is matched against 2.13.0's own list (kept in the code as it was), so the owner's bot, paired under 2.13.0, is offered the tour once after this upgrade. A record nothing matches offers nothing: the studio cannot know what the creator was offered.
- **Seen working, derived:** the panel lists the steps that leave something in the studio, each SEEN WORKING or NOT YET, read from what the profile holds, never from a press: something saved from Telegram (a note, an idea or a forward; a link; a photo, voice note, document or video), a draft written from a press on the bot (from now on a draft records that it was asked for on the phone), a draft rewritten from the phone, one draft from several items asked for on the phone, an item built up by a reply (an album's photos excepted), an edit followed, a thing to remember from Telegram, a draft planned from the phone, a reminder asked for, and a draft written from one of today's ideas. Steps that leave nothing (/help, /status, Send me the whole post, /recall's list) are named as such.
- **The race fixed first:** the menu's record, and the tour's notice, are kept only for the bot they were made for, under the worker's check lock, as phase 4's last check is; removal stops the worker before deleting. The notice is removed with the bot and with Delete everything.
- **Interface:** in the Telegram panel, "WHAT YOU HAVE TRIED FROM YOUR PHONE", one line a step.
- **Stored:** the tour's notice in one settings row (`telegram_tour`: the chat, the new command names, whether it was told); the command names in the menu's record; `via: telegram` in a written draft's `made_with`.
- **Leaves the machine:** the tour's parts and the notice, the product's own words, and whether a step was seen working or needs a provider, to the paired chat. No word of the creator's, nothing about anyone else.
- **Preferences:** none. The offer comes once, /tour is there when wanted, and the parts are the checklist's.
- **Decided against:** a count of steps per message (the checklist's groups are the natural cut, and a number here is not a taste); marking a step seen from a press; sending the tour unasked more than once.

### 2. Plan it from the phone

- **Built:** "Draft ready in your studio." carries **Plan it**, with the words switch on or off: a time carries no words. A press sends a message of its own, "When should your studio bring this post back to you? It goes into your Queue at that time, and I send it here then. Nothing is posted.", with one button per offered time, labelled on the computer's clock ("Today 17:30", "Tomorrow 08:30", "Wed 4 Nov, 08:30"); Plan it stays on its message, so it can be pressed again. A time pressed puts the draft in the Queue at that time in one conditional update: still a draft, never queued, published or bound to a post, and never one LinkedIn holds; a draft planned from the phone may be planned again while it is still queued at its planned time. The message then says "Planned for Tue 3 Nov, 08:30, on your computer's clock. It is in your Queue, and I bring it back here then. Nothing is posted.", with **Undo**, which makes it a draft again while it is still queued at that time. It adds, when true, that another post is in the Queue within 12 hours of it (the Queue's own rule, `scheduler.MIN_COOLDOWN_HOURS`), and that the Queue is paused, so it will not come due until it is resumed.
- **At that time:** the scheduler marks it due, as for any queued post (its code is read, never changed or called here), and the existing due reminder brings it back, with Send me the whole post while the words switch is on, Remind me in an hour and Done. A draft planned from the phone is told when due even with "Tell me when a queued post is due" unticked: planning it was asking to be reminded. Quiet hours hold it like any notification.
- **Typed:** a reply to the bot's message about a draft (Draft ready, a rewrite, the times, the plan) with `/plan <day> <time>` plans that draft: today, tomorrow or a weekday (the next one; today while the time is ahead), then 9, 09:00, 9:30, 6pm or 18:30. A /plan with a time that is not a reply, a time not read, or a time past is answered with how to say it.
- **`/plan` alone** lists the next queued posts, as many as the creator's "The bot lists at most": their times always, their first lines only with the words switch on, a post LinkedIn holds marked "LinkedIn posts it", and how many are due now.
- **Never LinkedIn:** nothing here calls Send to LinkedIn, `linkedin_client`, or anything that posts; it writes `status` and `scheduled_for` on a draft and the plan on its `made_with`. A test counts the `linkedin` egress category before and after, checks no `linkedin_holds:` row is written, and runs the scheduler at the planned time to see the post due, not published.
- **Interface:** in the Telegram panel, under "PLANS, REMINDERS AND LISTS", **Plan it offers** (your Queue's next open slots, how many; or your own times) and **The bot lists at most**.
- **Stored:** the post's queue time, as the Queue keeps it, and `planned` (when it was planned for, when, from the phone) on the draft's `made_with`; the bot's record of a message about a draft keeps Telegram's id for that message, so a reply to it finds the draft.
- **Leaves the machine:** times; a post's first line only in /plan's list and only with the words switch on.
- **Preferences:** **Plan it offers**: "Your Queue's next open slots", 3 of them (1 to 4), each at least 15 minutes ahead and 12 hours from any other queued, due or published post, as the Queue finds its next open slot; or "These times", each a number of days from today and a time, by default tomorrow at 09:00 and at 18:00 (1 to 4 times). With the slots chosen and none open in the next two weeks (or no slot at all), the times are offered, and the message says so. **The bot lists at most**: 5 (1 to 10), read by /plan and, from item 3, /recall.
- **Decided against:** planning a due post from the phone (Remind me in an hour and Today's Move to next slot do that); moving a post the Composer queued; posting at the time (the product never posts for the creator); Plan it under "Saved as a draft" (a `Draft:` message is the creator's own words, planned at the desk).

### 3. Act on what /recall finds

- **Built:** with the words switch on, /recall lists the matching items' first lines, numbered, up to "The bot lists at most" (newest first; "The newest 5:" when more match), with **Write up 1**, **Write up 2** and so on for each listed item that has words, and **Write one post from these**. Off, it answers with the count and **Write one post from these**. Write up writes that item up as Write it up does; Write one post from these writes one draft from the unused items that hold the word, newest first, up to the creator's "Most items in one draft", exactly as /write does, read at the moment of the press, and says how many ("Writing one post from 3 items in your collection."). It is offered only while an unused item with words matches. Each button acts once; the others stay. Writing runs beside the loop, as always.
- **Interface:** none new; the help and the panel's description of the words switch say it.
- **Stored:** the bot's record of the message: the listed items' ids and the word asked.
- **Leaves the machine:** the count; first lines only with the words switch on; on a press, the items' words to the creator's own provider, as Write it up and /write send them.
- **Preferences:** "The bot lists at most" (item 2), and Combine's "Most items in one draft" (phase 4).
- **Decided against:** a second meaning for "these" (it is /write's rule, said in the help and counted in the answer); listing used items' buttons differently (any item with words can be written up, as in the box).

### 4. Remind me

- **Built:** under "Saved to your collection.", for an item with words, **Remind me** sends a message of its own, "When should I bring it back? It waits in your collection until then.", with one button per moment the creator keeps (by default **This evening**, today at 18:00; **Tomorrow morning**, 09:00; **Next week**, seven days from today at 09:00); a moment already past, or within 15 minutes, is not offered. A moment pressed keeps a reminder, and the message says "I will bring it back Tue 3 Nov, 18:00 (This evening), on your computer's clock. Your collection lists it on the item, with Cancel.", with **Cancel**. At that moment, between polls, the bot says "A reminder you asked for, for Tue 3 Nov, 18:00:" and the item's first line (words switch on), or "an item in your collection, saved Mon 2 Nov." (off), with **Write it up** and **Not now** (Not now sets it aside, as the box's Not now does, while it is new).
- **Rules:** it waits through quiet hours; it is told once (claimed by a conditional update before it is handed over, as the notifications are); it survives a restart (it is a row); a moment that passed while the studio was off is told at the next check, saying the moment it was for; it goes when its item is removed (Remove, Undo, a `Draft:` taken back, Delete everything); it is told only to a paired chat, and the claim is made under the worker's check lock for the bot it was made with, so a removed bot marks nothing told.
- **Interface:** in Your collection, each item lists its waiting reminders ("Reminder: Tue 3 Nov, 18:00 (This evening)") with **Cancel** (`DELETE /api/v1/collection/reminders/{id}`, one new path, reached by the box). In the Telegram panel, **Remind me offers**, the moments, each with its label, its day and its time.
- **Stored:** migration 43, a table of reminders (below).
- **Leaves the machine:** the moment, the label the creator gave it, and the item's first line only with the words switch on. The labels are the creator's names for the buttons, sent as button text as the angles count is.
- **Preferences:** **Remind me offers**: 1 to 4 moments, each a label of up to 24 characters, a number of days from today (0 to 14) and a time; defaults above.
- **Decided against:** a reminder for an item without words (it comes back with Write it up); repeating reminders; a reminder for anything but an item of the collection (a due post has Remind me in an hour).

### 5. Today's ideas on the phone

- **Built:** `/ideas` reads today's batch of From your record (a SELECT: it never builds a batch, and never calls a model, in the poll loop or anywhere). With the words switch on: "Today's ideas from your record:" and each shown card with words of the creator's, numbered, as "<its block>: <its excerpt>", with **Write up 1** and so on, and how many more cards the studio shows that carry no words to send (a vote, a follow, a reaction, a saved post: their titles can name someone else, so they are never sent). Off: "4 ideas are ready in your studio, under From your record." When the model's card is waiting for the creator's first open, it says so. No batch today: "Today's ideas are not made yet. ..." and how they are made: the first time the studio runs each day, a few minutes after it starts, from the creator's own posts, readings, asks and collection.
- **Write up:** writes a draft from that card's words (the creator's own post, opener, ask, comment, or the model's idea) through the creator's provider, beside the loop, grounded as every draft is; the draft carries the card it came from (`origin_card_id`, `origin_day`) and the card is marked used, as the studio's Draft from this marks it. A card made from an item of the collection writes from the item, which is then used. The Composer's note says the draft was written from one of today's ideas.
- **Interface:** the Composer's "What this draft was written from" says "from one of today's ideas in From your record" for such a draft.
- **Stored:** the draft, its card mark, `made_with` naming the card.
- **Leaves the machine:** a count; excerpts only with the words switch on; on a press, the card's words to the provider. Never a figure (a card's figures stay in the studio), never another person's name or words.
- **Preferences:** none of its own: today's cards are what From your record shows, set there; the writing reads Brand, Writing as every draft does.
- **Decided against:** building today's batch or asking the model from the bot; sending a card's figures; a card with no words of the creator's.

### 6. If budget allows: `Schedule <when>:` plans for real

The help warns that `Schedule <when>: your text` "does not schedule anything": the time is read and dropped. With item 2's reader, a `Schedule tue 09:00: text` from the paired chat saves the draft as today and plans it for that time, answered as Plan it is (with Undo), and is told when due as a planned draft is. A time the reader cannot read keeps today's behaviour, and the answer says the time was not read. It removes a documented trap, uses nothing new, and is the same act as item 2.

## Migrations, and why

- **Migration 43, with item 4:** a table of reminders, one row per reminder: the item, the moment (UTC), the label pressed, when it was asked for, and when it was told. A settings row (how phase 2's Remind me in an hour is kept) does not fit: reminders are listed on their items, cancelled one by one from the box while the worker tells others (a JSON list rewritten by two writers loses one), and removed with their item, and they are the creator's own data, which the export lists and Storage counts; settings are never exported. Appended to `MIGRATIONS`, forward only, re-runnable (`IF NOT EXISTS`), behind the automatic backup, with a test that an older database gains it and a second run adds nothing, and named with no word an earlier migration's test finds its own by. Counted in Storage with the collection, exported, removed with an item and by Delete everything, kept in backups with the database.

Nothing else needs one: a plan is the post's own queue time plus a key on `made_with`, the tour reads what exists, and preferences are settings rows.

## Preferences added

| Preference | Default | Set in | Read by |
| --- | --- | --- | --- |
| Plan it offers (`telegram_plan`) | your Queue's next 3 open slots; with none, tomorrow at 09:00 and at 18:00 | the Telegram panel | Plan it |
| The bot lists at most (`telegram_list_at_most`) | 5, from 1 to 10 | the Telegram panel | /plan, /recall |
| Remind me offers (`telegram_remind_moments`) | This evening (today, 18:00), Tomorrow morning (tomorrow, 09:00), Next week (in 7 days, 09:00) | the Telegram panel | Remind me |

Each is tested: changing it changes what the bot offers, and a fresh profile gets the default. Each control shows its default beside it.

## What may go where

| What | To Telegram | To the AI provider | Kept |
| --- | --- | --- | --- |
| The tour, its notice | the product's words, whether a step was seen working or needs a provider | never | the notice in settings, removed with the bot |
| A plan | times; first lines in /plan only with the words switch | never | the post's queue time, `made_with` |
| /recall's list | the count; first lines only with the words switch | the items' words, on a press | the bot's record of the message |
| A reminder | the moment, its label; the first line only with the words switch | the item's words, on Write it up | migration 43's table |
| /ideas | a count; excerpts only with the words switch | the card's words, on a press | the draft, the card's mark |
| Another person's name or words, a card's figures | never | never | never |

## Sections

No new section, per the owner's rule. The Telegram panel (Settings, Local security) gains the tour's list and three preferences under one heading; Your collection gains reminders with Cancel; the Composer's note gains one sentence. One new API path; the census in `tests/test_endpoint_reachability.py` is re-measured in that commit.

## Tests

The fake Bot API runs as phase 4 left it: replies are pushed with `reply_to_message`, presses with `press_button`, and the message ids it answers with link the bot's messages to drafts. The writing runs against the fake provider (`tests/ai_fake.py`). Each item: a failing test first, the code, one guard falsified, one commit; each new test file run three times in a row before its commit; data put in place before the switch that acts on it; no small timing compared. A browser test with axe in both themes (the shared helper) for each new control, waiting for a settled page, and `tools/ui_audit.py` at 0 blocking. At the end, the Telegram and collection set, then one full suite as CI runs it, with flake8.
