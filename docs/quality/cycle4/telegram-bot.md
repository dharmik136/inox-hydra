# The Telegram bot, phases 1 and 2 (2.11.0)

The record of the first phase of the standing assignment on the Telegram bot: make it better, test it, add features. The owner's first test against the real service (2026-10-28) showed the path works and feels dead: the bot never replied, so nothing said whether a message had arrived. Branch `qc4/telegram-bot`, from `qc4/release-2.10.1` at 5d19786 (version 2.10.1, schema 36). No migration: every new setting is a row in `settings`. No independent review: each item has a failing test first, and one full suite ran at the end.

## How it is tested

`tests/telegram_fake.py` is a fake Telegram Bot API on 127.0.0.1: getUpdates with long polling and offsets that confirm, sendMessage, and the failures a real bot meets, planned per method (429 with retry_after, a dropped connection, an error status, a blocked chat, another token). The studio's own worker is started by saving the bot through the panel's route and talks to the fake over HTTP through `telegram_bot.API_BASE`, through the egress check, as it does to api.telegram.org. The suite's network guard refuses anything else, so the older Telegram tests now simulate sendMessage as well as getUpdates.

## Items

| Item | Commit | What changed | The test that fails without it | How the guard was falsified |
| --- | --- | --- | --- | --- |
| The fake Bot API, end to end | e84aff7 | `tests/telegram_fake.py`; `studio/backend/telegram_bot.py` holds the one Bot API base the ingress now builds its address from | `tests/test_telegram_bot_e2e.py`: a paired chat's message saved and only then confirmed; a stranger refused; an update that cannot be stored asked for again and stepped over after three tries; a 429 waited out; a dropped connection retried with a growing wait | Before the base existed, the first test reached for api.telegram.org and the suite's network guard failed it |
| 1. The bot answers every message | 132ae2b | `telegram_bot.SENTENCES`, the outbox and `send_message`; `ingress.py` queues an answer for each update and flushes after each poll. Fixed sentences only: saved as a draft; Today will ask you to open this post (or this link); not one of your posts; no text; could not save; paired; not paired yet, with how to pair and that chat's own id; another chat. A refused chat is answered at most once in ten minutes. On by default; "The bot confirms each message" (`/api/v1/ingress/options`). Help and policy list what is sent | `tests/test_telegram_bot_replies.py` (12): each sentence; the words never go back; a 429 and a dropped send retried; a blocked chat said in plain words and not retried; the switch | The draft's text appended to its answer: the test failed |
| The token in the egress ledger | 2dac22c | Found by the panel's browser test while building item 1: the ledger keeps each category's last destination with its path, and a Bot API path carries the token, so Local security showed it after the first poll (true since the ingress went through the chokepoint). Both calls are now counted under `/bot<token>/` (`telegram_bot.ledger_url`) | `test_the_token_never_reaches_the_egress_ledger` | The test failed against the code before the fix |
| 2. Commands | fa195c4 | /start and /help (what the bot does, how to pair, what it never sends); /idea (a draft tagged idea; a link inside stays part of it); /ask (an ask through the asks store's own rule, which now names "telegram" among its sources; the section's box still refuses to claim it); /status (studio and bridge, no figure); an unknown command. Questions are answered whatever the confirmations switch says | `tests/test_telegram_bot_commands.py` (11) | Not a guard beyond the tests |
| 3. Figures, opt-in | f601ee7 | "The bot may answer with your figures", off by default. /today: the latest post's figures, each with where and how long ago it was read, replies waiting as a count, the next scheduled post's time. A figure nobody read is left out. Panel and policy say the figures then sit on Telegram's servers | `tests/test_telegram_bot_figures.py` (7), with a commenter's name and words, and the creator's own post text, seeded to be absent | The switch check skipped: the off-by-default test failed. A commenter's name appended: the no-names test failed |
| 4. Notifications, each opt-in | f8a0300, 9d9c4ac | "Tell me when a queued post is due" (a count) and "Send my latest post's figures at about 24 hours" (that reading's own figures, while the post is under two days old), none by default; each told once, kept in `telegram_told` so a restart does not repeat it, and forgotten with everything else | `tests/test_telegram_bot_notifications.py` (7) | The told record not written: four tests failed |
| 5. Reliability and visibility | 820ed9c | Send a test message (`/api/v1/ingress/test-message`); the last problem in plain words (a token Telegram does not know, a second program asking, Telegram's own error, no connection, a rate limit); an error answer backed off from as a network fault, where it used to be polled again every two seconds; a failed update logged by its kind, never its text | `tests/test_telegram_bot_reliability.py` (9), `tests/test_telegram_bot_panel_ui.py` (2, axe in both themes) | The backoff on error answers removed: the backoff test failed. The exception's text logged again: the quiet-logs test failed |
| 6. The owner's checklist | 9a9e984 | `docs/help/test-your-telegram-bot.md`, five timed steps on the real bot and phone, filed beside the Telegram guide | `tests/test_telegram_bot_checklist.py` (4): every sentence it promises is quoted from the code that says it | Not a guard beyond the tests |

Census: `tests/test_endpoint_reachability.py` 226 paths to 228, reached 178 to 180 (the switches and the test message, both from the panel).

## What remains unverified

The real service: everything here runs against the fake. The checklist is the owner's run of it. Telegram's long poll can hold a reply that waits on a 429 or a network fault until the poll returns, up to 30 seconds; the first answer to a message goes at once, after the poll that brought it.

## Suite

As CI runs it, at the end: `pytest tests studio/tests -q -rs`, 4,216 passed, 0 failed, 17 skipped (each skip names a Windows or macOS primitive, a workstation's browser, or a missing yaml module, as before). Also: flake8 with CI's selection, 0; `tools/sync_version.py --check`, in sync at 2.10.1; `tests/test_studio_backend.py`, all nine suites passed; the interface built; `tools/ui_audit.py`, 68 screens, 0 with blocking findings.

## Phase 2

The record of the second phase of the same assignment: buttons on the bot's messages, quiet hours for its notifications, a weekly summary, and one small command. Branch `qc4/telegram-bot`, from phase 1's record at 2fbaa70 (version 2.10.1). No migration: every new thing kept is a row in `settings` (`telegram_buttons`, `telegram_remind`, `telegram_quiet`, `telegram_weekly`), and the week's summary is told once through phase 1's `telegram_told`. No new API path: the options route takes the new switches. No independent review: each item has a failing test first and a guard falsified, and the full suite ran at the end (three times: see Suite).

### How it is tested

`tests/telegram_fake.py` now takes button presses as Telegram delivers them. `press` pushes a callback_query update with any data from any chat, and `press_button` presses a button the phone shows now, by its label. answerCallbackQuery answers a press once and refuses a second answer, as Telegram does. editMessageText and editMessageReplyMarkup change a sent message as the phone then shows it (an edit without reply_markup takes the buttons away), and refuse an edit that changes nothing ("message is not modified"). getUpdates remembers allowed_updates as Telegram does, so a bot once set to messages only never delivers a press unless the poll asks for it. The computer's clock as the bot reads it (`telegram_bot.local_now`) is set by the tests that depend on it: the notification tests read it as midday, the quiet hours tests set the hours they need, and the weekly tests hold it at the moment they began and pick that day and hour. Nothing else of the clock is faked.

### Items

| Item | Commit | What changed | The test that fails without it | How the guard was falsified | Census change | Suite result |
| --- | --- | --- | --- | --- | --- | --- |
| 1. Buttons on the bot's messages | 55ed1c4 | Undo under "Saved as a draft in your studio.", removing that draft while it is untouched in the studio (still a draft, with the words, tags and media the bot saved, never queued, published or bound to a post), in one conditional delete; a draft changed at the desk is kept and the bot says so. Remind me in an hour and Done under "A post in your queue is due now.": the reminder is told again an hour later if the post is still due; Done only clears it, nothing is marked as posted and nothing reaches LinkedIn. Each press is answered (answerCallbackQuery) and its message edited to say what became of it, buttons gone; acts once, only for the paired chat by its own person (any other press is refused as a stranger's message, listed as "a button press"), and an old or unknown button says so. A press the studio cannot carry out is answered after the three tries every update gets. The poll names `allowed_updates` (message, callback_query). A button's data is an opaque id and one letter. The outbox carries any Bot API method; two refusals that mean "already done" (an edit that changes nothing, a press Telegram stopped waiting for) are not shown as problems. Forgotten with everything else | `tests/test_telegram_bot_buttons.py` (13): Undo removes and says so, with opaque data; kept when edited or queued; nothing to undo when deleted; once only; old and unknown; another chat refused; a failed press answered; a bot set to messages only still hears a press; Done marks nothing as posted and reaches no LinkedIn; Remind me in an hour told again only while still due; forgotten; named in the help and the policy | The paired-chat check on a press loosened to "a chat is paired": a press in the owner's chat by another person removed the draft, and the refusal test failed. The untouched conditions dropped from Undo's delete: the edited and the queued tests failed | None: 228 paths, 180 reached, 48 unreachable | The bot's suites and their neighbours at the commit, 230 passed |
| 2. Quiet hours | 254183c | The opt-in notifications, and a reminder asked for, wait while quiet hours are on and go when they end, each once; while it is quiet the check looks at nothing, so nothing is marked as told. "Hold notifications during quiet hours", on by default from 23:00 to 07:00 on the computer's clock, two selects of whole hours, can be turned off; a start and an end on the same hour refused with a sentence. "QUIET NOW: NOTIFICATIONS WAIT UNTIL 07:00" on the panel. Answers to the creator's messages, commands and presses never held | `tests/test_telegram_bot_quiet_hours.py` (19, with the window's hours as cases) and a browser test of the controls with axe in both themes | The quiet gate taken out of `check_notifications`: three tests failed (a notification during quiet hours, inside changed hours, a reminder) | None | 184 passed |
| 3. A weekly summary | 1190821 | "Send me a weekly summary", off by default, Monday 09:00 unless changed: the seven days to that moment, posts the studio recorded as published, drafts saved from the phone, replies waiting (a count), the next scheduled post; each of the week's posts' figures with where and when they were read only if the figures switch is on, a figure nobody read left out, a post nobody read said so. Told once a week (`week:<year>-W<n>` in `telegram_told`), after the first chosen moment since it was turned on or changed, later that week if the studio was not running, held by quiet hours. "NEXT SUMMARY:" on the panel. /today's figure words shared with it, unchanged | `tests/test_telegram_bot_weekly.py` (10) and a browser test of the controls with axe in both themes | The figures switch check skipped: "figures went with the figures switch off". The week's told key not written: "the week's summary was told twice" | None | 259 passed |
| Small: /drafts | 86c289f | /drafts answers "Drafts saved from your phone in the last seven days: 5.", or that none was: a count, never words; a question, answered whatever the confirmations switch says; a stranger's refused | 3 in `tests/test_telegram_bot_commands.py` | The seven days widened to ten years: the count test failed (4, not 3) | None | 31 passed |
| Found by the suite: the tests at any hour | 6d5e2a7 | The full suite run a second time, after 23:00, failed eight notification tests: quiet hours, on by default, rightly held what they waited for. Their fixture now reads the bot's clock as midday (the quiet hours tests set it themselves). Checking that under five time zones found the weekly tests' "a week later" an hour short across Los Angeles' change of summer time on 1 November: they now move the clock by wall-clock days. The bot was right both times | The same tests, run at night here and under five time zones (night, midday, 07:47, 00:18, and Los Angeles the week before its change) | Before the fix the eight failed at 23:13 here and passed under `TZ=UTC`, and two weekly tests failed under `TZ=America/Los_Angeles`; after it, all pass in each | None | The bot's suites at night, 159 passed; the weekly tests under five zones, 10 passed each |
| Two corrections | 3163393, fb365aa | The help says a phone draft changed or deleted in the studio since still counts as saved that week, and only Undo takes it out; the panel says the summary counts the posts the studio recorded as published, as the summary itself says | Not a guard beyond the tests | Not a guard | None | The panel's tests, with axe in both themes, 36 passed |

Each item's help, privacy policy (with `release/privacy.html` rebuilt) and checklist lines were written in its own commit, and the checklist test quotes each new sentence from the code. Phase 2 adds 51 tests: 42 in three new files, 9 in phase 1's (two browser tests, four checklist tests, three /drafts tests). One older test, `tests/test_qc4_t6_phone_settings.py`, pinned the poll's exact parameters and now checks the token and the offset it was written for.

### Quiet hours and the poller's night pace: kept separate

The poller's night pace (`ingress.is_quiet_hours`, 23:00 to 06:00, fixed) is the studio's own: between polls it waits 120 seconds instead of 2, so an answer at night can take up to two minutes. The bot's quiet hours (`telegram_bot.in_quiet_hours`) are the creator's: 23:00 to 07:00 by default, changeable, and can be turned off, and they hold only notifications. Neither changes the other, and a test holds that: with quiet hours off, or moved to noon, the poller keeps its night pace at 02:00 and its day pace at noon. Reconciling them was considered and not done: tying the pace to quiet hours would slow every answer at night for a creator who only wants notifications to wait, for a saving of a few requests an hour. They are named apart in the code, the help and here; `is_quiet_hours` keeps its name because older tests and the status route read it.

### Decisions, and what was decided against

- Undo removes the draft only. A message that was also a post link keeps its request on Today, which has its own Not now.
- Done only marks its button used: no status changes, no request to LinkedIn. The test counts the linkedin egress category before and after a press, and the Bot API methods the fake saw.
- A stranger's press is refused as a stranger's message is: kept for the panel's "Is that you?", answered at most once in ten minutes, in the notice the phone shows and never a message of its own, and not at all with the confirmations off.
- An old button is answered "old" and its buttons are taken away; its text is not rewritten. Buttons are kept for the newest 100 messages that carry them, by count rather than by age.
- Unticking "Tell me when a queued post is due" drops any reminder asked for.
- Decided against: setMyCommands, to fill Telegram's command menu (it changes the bot on Telegram, which the creator did not ask for); commands that change a setting from the phone; keeping each message's id at send time (a press carries its own message).

### What remains unverified

The real service: everything here runs against the fake, as in phase 1. In particular, on the real Bot API: that an edit without reply_markup takes the buttons away (as documented), how long the phone's spinner waits for its answer (at night the poller's pace can delay it up to two minutes; an answer Telegram stopped waiting for is taken as nothing left to do, since the edit after it says the outcome), and that allowed_updates is kept between polls. The owner's checklist covers them: Undo in step 3 of the five minutes, and the due post's two buttons, quiet hours, the weekly summary and /drafts in its later, optional part.

### Suite

As CI runs it, at the end, on 6d5e2a7, from 23:26 to 23:43 on this computer's clock, inside the default quiet hours: the interface built, then `pytest tests studio/tests -q -rs`, 4,267 passed, 0 failed, 17 skipped (each skip names a Windows or macOS primitive, a workstation's browser, or a missing yaml module, as in phase 1): phase 1's 4,216 and the 51 this phase added. Also, on the same code (6d5e2a7 changed tests only): flake8 with CI's selection, 0; `tools/sync_version.py --check`, in sync at 2.10.1; `tests/test_studio_backend.py`, all nine suites passed; `tools/ui_audit.py`, 68 screens, 0 with blocking findings. Before it the same suite ran twice: on 3163393, before 23:00, 4,267 passed; on fb365aa, across 23:00, 8 failed, which 6d5e2a7 fixed (above).

## Phase 4

The record of the fourth phase, asked for on 2026-10-30 ("see what more can be done in it") and written down before its code in [the phase 4 PRD](bot-phase4.md). Branch `qc4/bot-phase4`, from `8962bce` (2.12.0, schema 40). Twelve items, in the owner's order, each with a failing test first, the code, one guard falsified, and one commit. No independent review. The version stays 2.12.0.

### How it is tested

The fake Bot API (`tests/telegram_fake.py`) gained what this phase meets, each as Telegram does it: setMyCommands, getMyCommands and deleteMyCommands kept per scope with Telegram's limits (100 commands; 1 to 32 lowercase letters, digits and underscores; descriptions of 1 to 256 characters); `edit`, an edited_message update delivered only to a poll that asks for one; a refusal of a message over 4096 characters (counted in UTF-16 code units) and of a button whose callback_data is over 64 bytes; and one message-id sequence per chat both ways, as in Telegram, where the phone's messages and the bot's never share an id (they used to, which made a reply look like one of the bot's own messages). Documents, videos and albums go through the fake's getFile as photos did. The writing runs against the fake provider (`tests/ai_fake.py`). Nothing reaches the network.

### Items

Census in `tests/test_endpoint_reachability.py` as total paths / reached by the interface / unreachable.

| Item | Commit | What changed for the creator | Test first | How the guard was falsified | Census | Suite at the commit |
| --- | --- | --- | --- | --- | --- | --- |
| The PRD | c285666 | Nothing yet: each item's build, place, storage, what may leave and under which switch, preferences and what was decided against; Telegram's rules quoted from the Bot API page | | | 240/192/48 | The docs suites, 89 passed |
| 1. Seen working, truthfully | 09020b8 | The panel's orange "Not yet seen working" sentence goes once anything from the paired chat is in the profile (an item, a thing to remember, an ask), including what was saved before the marker existed; the marker is then set, so it stays. The moment a chat is paired is kept, so after a change of chat only what came after counts | `tests/test_telegram_bot_seen_working.py` (6) | The pairing moment ignored: the new chat-change test and the pairing suite's "goes with the chat" failed | 240/192/48 | Neighbours, 61 passed |
| 2. Nothing lost silently | 20ebfe3 | The last successful check is kept in the bot's profile (at most once a minute, and when the worker stops). A check more than a day after the last one is told once on the bot ("Your studio did not check Telegram for your messages from ... until ..."), after quiet hours if it is quiet, whatever the notification switches say, and in the panel at once until **Got it**: never "lost", never a count. The panel says when Telegram was last checked; /status says when the studio last checked before the message; /help says the studio must run at least once a day | `tests/test_telegram_bot_gap.py` (12), the notice in a browser with axe in both themes | The gap never recorded: seven of the twelve failed | 241/193/48 (`/api/v1/ingress/gap/seen`) | The Telegram, collection and phone suites: 532 passed and 1 failed, phase 1's sentence rule (the notice carried times in a sentence over 200 characters); the notice moved out of SENTENCES, as the weekly summary is, and those files rerun, 41 passed |
| 3. The "/" menu | 21c29ac | Typing / in the chat lists the bot's commands, registered with setMyCommands for the paired chat's scope only, through the egress check, counted without the token; again only when the chat or the list changes (a fingerprint is kept), a refusal tried again after ten minutes; another chat paired, or the bot removed or replaced, takes the menu away. /help's command lines are written from the same list. The panel says "The / menu in your chat: SET" | `tests/test_telegram_bot_menu.py` (9), the panel's row in a browser | The fingerprint ignored: "not sent again at every start" and "a changed list is registered once" failed | 241/193/48 | Neighbours, 92 passed |
| 4. Post from the phone | 6f58012 | With the words switch on, "Draft ready" and a due post carry **Send me the whole post** (**Send me the posts** when several are due): the post as the studio holds it now, alone in a message, for press and hold, Copy; over 4096 characters it is cut between paragraphs, each part beginning "Part 1 of 2". The message keeps its other buttons. Off, no button, and a press on an older message says why | `tests/test_telegram_bot_whole_post.py` (11) | The switch not checked at the press: "a press on an older message after the switch went off" failed | 241/193/48 | 560 passed and 2 failed: the policy did not name Send me the posts, and a phase 3 test listed the Telegram methods without setMyCommands (item 3's, fixed inside its commit); both fixed and their files rerun, 41 passed |
| 5. Shape a draft from the phone | 98f4bb8 | Under a draft the bot wrote (words switch on), the creator's rewrite buttons (Shorter, New opening, Another angle by default), each rewriting through their own provider beside the loop, grounded as every draft is; the draft changes in place only while it is unchanged since it was read; the text it replaced is kept on the draft (the ten newest), listed in the Composer with **Put it back in the editor**, and the bot's answer has **Undo**. An open Composer with nothing unsaved follows the change | `tests/test_telegram_bot_reshape.py` (19), `tests/test_telegram_bot_reshape_ui.py` (2, axe in both themes) | The "unchanged since it was read" condition dropped: "a draft changed at the desk while it was rewritten is kept" failed | 241/193/48 | 633 passed |
| 6. Build an idea up | 21abe5e | A Telegram reply to the creator's message, or to the bot's answer about one, adds its words to that item instead of a new one, with **Undo**; a drafted item takes the words and the bot says the draft was not changed. "A reply adds to what it replies to", on by default, in the panel. The box says "from 3 of your messages" | `tests/test_telegram_bot_build_up.py` (16, with the migration and the table's custody), the switch and the box's line in a browser | The switch not read: "switched off, a reply is an item of its own" failed | 241/193/48 | 1,049 passed |
| 7. Edits follow | 76169ca | The poll asks for edited_message. An edit updates the item it made, live, read as the message was; once used, the draft is kept and the bot says so; the box marks "edited on your phone". An edit from any other chat is refused like a stranger's message | `tests/test_telegram_bot_edits.py` (9), the box's mark in a browser | The paired-chat check on an edit dropped: "an edit from another chat is refused" failed | 241/193/48 | 1,059 passed |
| 8. Remember this | cad0171 | Under "Saved to your collection.", a note or an idea that fits (300 characters) carries **Remember this**: its words become a thing to remember, the item is used ("Kept in your things to remember"), and **Undo** undoes both | `tests/test_telegram_bot_remember_this.py` (6) | The kinds it is offered for not checked: "not offered for a forward, a link or words too long" failed | 241/193/48 | 1,063 passed and 2 failed: phase 3's tests of the buttons under a note, which now list Remember this; updated and rerun, 17 passed |
| 9. `/write` | e2831de | `/write pricing` or `/write #pricing`: one draft from the unused items that match, newest first, through Combine; nothing matching is said and nothing is asked. Combine's fixed ten is now the preference "Most items in one draft", read by Combine and /write | `tests/test_telegram_bot_write_command.py` (10), `tests/test_telegram_bot_write_ui.py` (1) | /write took used items too: "one draft from the unused items" failed | 241/193/48 | 1,077 passed |
| 10. Everything in one box | 4e6890b | Albums arrive as one item, answered once; documents and videos are kept as they are, with their own names, within 20 MB, never read. A file the studio cannot show is a download only, never opened in its window. The box shows View and Download, plays a video, shows an album together; **Add to your media library** only for what the library takes (an image, a PDF as a carousel, an MP4 or WebM video), each checked by its first bytes | `tests/test_phone_files.py` (11, with the migration), `tests/test_phone_files_ui.py` (1) | A file stored under its own extension, so a web page was served as one: three tests failed | 241/193/48 | 1,105 passed and 3 failed: phase 3's tests that a document or a video is not kept and that only a photo goes into the library; updated and their files rerun, 46 passed |
| 11. Text kept whole | c02a584 | A link hidden behind words (a text_link entity, UTF-16 offsets) is written into the words after them; a LinkedIn post link behind words is taken as a visible one. `/recall #tag` reads tags. A link's #fragment is no longer taken as a hashtag | `tests/test_telegram_bot_entities.py` (9) | The offsets read as Python characters: the emoji test failed | 241/193/48 | 1,379 passed |
| 12. One line per failed check | 65e3554 | A failed check is logged once; a read timeout, a dropped connection and this computer's own egress switch are warnings, anything else an error; the token stays redacted | `tests/test_telegram_bot_logs.py` (3) | The loop logging every failure again: all three failed | 241/193/48 | The bot's and the ingress suites, 506 passed |

"Suite at the commit" is the set run before that commit: the Telegram bot's, the collection's, the phone's, memory's, the ingress's and pairing's suites, the census, and every test that reads the writing preferences, the migration ledger or the custody lists, as each item touched them.

### Migrations

- **41** (item 6), `collection_messages`: one row per Telegram message about an item, the creator's own with the words it gave the item, and the bot's answers once Telegram took them, by chat and message id. Replies and edits name a message that way, and nothing kept held its id; changing `origin_ref` instead would have let a message handled again across the upgrade be kept twice. Counted in Storage with the collection, exported, removed with an item, Undo and Delete everything, kept in backups.
- **42** (item 10), `collection_items` rebuilt for the kinds `document` and `video` (a CHECK constraint, which SQLite changes only by rebuilding the table), every row copied with its id and the id sequence carried over, so a removed item's id is never given again to an old button; and `media_group`.

Both forward only, re-runnable, behind the automatic backup before any migration, each with a test that an older database gains it and a second run adds nothing, and neither named with a word an earlier migration's test finds it by.

### Preferences added

| Preference | Default | Set in | Read by |
| --- | --- | --- | --- |
| Rewrite buttons on your bot (`reshapes`) | Shorter ("Make it about a third shorter. Keep its point, its first line and its voice."), New opening ("Write a new first line for it, as the opening line preference says. Keep the rest as it is."), Another angle ("Rewrite it from another angle on the same notes, at about the same length."); up to six, labels up to 24 characters, instructions up to 200, none allowed | Brand, Writing; named on the Telegram panel | the bot's rewrite buttons |
| Most items in one draft (`combine_at_most`) | 10 (the fixed limit until now), from 2 to 20 | Brand, Writing | Combine in Your collection, /write |
| A reply adds to what it replies to | on | the Telegram panel | the bot |

### Changed in earlier phases' tests, and why

- Phase 1's /status test pinned "no digit at all": the owner asked for the last check time, so it now allows that one sentence and still refuses any figure.
- Phase 2's and phase 3's tests that list the Telegram methods a press or a voice note involves now include setMyCommands, the menu (fixed inside item 3's commit, which first missed them).
- Phase 3's tests of the buttons under a note now list **Remember this**; "a document or a video is not kept" became "a sticker is not kept"; "only a photo goes into the media library" now says what the library takes.

### Decided against, while building

- Saying anything about a gap under a day (Telegram still holds it all), or counting what may be missing.
- A switch for the gap notice: it carries only times, once per gap, and a creator who ticked nothing needs it most.
- The default command scope, and a list per language.
- A link that opens LinkedIn with the post filled in: copy and paste, nothing automated.
- Rewriting with the words switch off, a new draft per rewrite, and versions for every Composer save.
- Matching a reply by its date or words; adding a photo to an item by replying with it.
- Following an edit into a draft.
- Remember this on a forward, a link or a file.
- /write from used items.
- A local Bot API server for files over 20 MB; reading any file.
- Keeping bold or italic formatting; a separate column of links.

### What remains unverified

The real service: everything here runs against the fake. In particular, on the real Bot API: that setMyCommands with a chat scope shows in the phone's / menu at once; that a caption's edit arrives as edited_message (the Bot API page does not say so in words; `edited_message` is "New version of a message that is known to the bot and was edited"); how an album's messages are spread over getUpdates batches; and that the phone's long-press Copy takes the message's text exactly. The owner's checklist covers each, in "Phase 4 on your phone".

### Found by the full suite, and fixed

The full suite run at the end, at 02:22 UTC, failed two tests outside the bot, and both fail the same way on the released 8962bce (2.12.0): commit 533e0da. `tests/test_qc4_t4_health.py` placed two captures "20 days ago" three hours apart, measured back from the clock; a capture's day is its UTC date, so between 00:00 and 03:00 UTC they fell on two days. `tests/test_qc4_t7_asks_and_marks.py` expected "More of this" to write Hiring or Pricing, but the recurring words of the posts it seeds are "Changed" and "Pricing", and which card is shown depends on the day. Test-only fixes; both pass at the hour they failed, under five time zones.

### Found while building, not fixed here

`tests/test_privacy_page_is_the_policy.py` puts `tools/` first on `sys.path`, and `tools/library_bundle.py` then shadows the backend's `library_bundle` for a test run that imports `app` for the first time after it (running that file and `tests/test_telegram_bot_commands.py` alone, in that order, errors). The full suite imports `app` earlier, so CI never meets it.

### Suite

As CI runs it, at the end: the interface built, then `pytest tests studio/tests -q -rs`. The first run, on 65e3554, ending at 02:22 UTC: 4,492 passed, 2 failed, 17 skipped; the two failures were the clock-dependent tests above, which fail the same way on 8962bce, fixed in 533e0da. The second run, on 533e0da with this record and two comment corrections: 4,493 passed, 0 failed, 18 skipped (each skip names a Windows or macOS primitive, a workstation's browser, or a missing yaml module, as before; the eighteenth is `tests/test_qc2_r1_launcher.py`, which skips when the kernel leaves no TIME_WAIT on the port). 4,511 tests collected: phase 3's 4,375 and the 136 this phase added (129 in sixteen new files, 7 in the checklist's test). Also: flake8 with CI's selection, 0; `tools/sync_version.py --check`, in sync at 2.12.0; `tools/ui_audit.py` on a fresh install, 68 screens, 0 with blocking findings.

## Phase 5

The record of the fifth phase, asked for on 2026-11-02 ("continue") and written down before its code in [the phase 5 PRD](bot-phase5.md). Branch `qc4/bot-phase5`, from `b2f1754` (2.13.0, schema 42). Five items in the brief's order and a sixth the PRD argued for, each with a failing test first, the code, one guard falsified, and one commit. No independent review. The version stays 2.13.0.

### How it is tested

The fake Bot API (`tests/telegram_fake.py`) gained one plan, `("hold", seconds)`: a method's answer, as it would be, given only after a wait, so a test can remove the bot while Telegram is still answering. Replies are pushed with `reply_to_message`, presses with `press_button`, and the message ids the fake answers with link the bot's messages to the drafts they are about. Writing runs against the fake provider (`tests/ai_fake.py`). Times that depend on the clock are computed from the real clock where the studio checks them against it (a plan or a reminder in the past is refused), and the bot's own clock (`telegram_bot.local_now`) is read as midday only for quiet hours. Nothing reaches the network.

### Items

Census in `tests/test_endpoint_reachability.py` as total paths / reached by the interface / unreachable.

| Item | Commit | What the creator now sees | Test first | How the guard was falsified | Census |
| --- | --- | --- | --- | --- | --- |
| The PRD | e9acaf2 | Nothing yet: each item's build, place, storage, what may leave and under which switch, preferences and what was decided against; Telegram's rules quoted from the Bot API page; migration 43 and why | | | 241/193/48 |
| 1. A guided first run | 93b6e0c | `/tour` sends what to try a few steps at a time, as the checklist groups them; **Next** replaces a part in the same message, **Stop the tour** ends it, the last part offers **From the start**. A writing step says when no provider is connected and points to the Prompt tab; a step needing the words switch says so; a step seen working says so. "Paired." now carries **Start the tour**; after an upgrade that adds commands a bot paired before it is told once which are new (2.13.0's menu record is recognised by its fingerprint). The Telegram panel lists the steps that leave something, SEEN WORKING or NOT YET, derived from what the profile holds, never from a press | `tests/test_telegram_bot_tour.py` (17), `tests/test_telegram_bot_tour_ui.py` (1, axe in both themes) | `register_menu` writing whatever the guard says: "a registration outliving the stop keeps nothing for a bot that is gone" failed | 241/193/48 |
| 2. Plan it from the phone | 8517f26 | "Draft ready" carries **Plan it**, words switch on or off; a press sends a few times as buttons; the one pressed puts the draft in the Queue then, with **Undo**, saying when and whether another post is within 12 hours or the Queue is paused. At that time the Queue marks it due and the due reminder brings it back (with Send me the whole post under the words switch), even with the due notification off. A reply with `/plan <day> <time>` plans it; `/plan` alone lists what is planned. Nothing posts and nothing reaches LinkedIn | `tests/test_telegram_bot_plan.py` (17), `tests/test_telegram_bot_plan_ui.py` (2, axe in both themes) | The check that a post LinkedIn holds is never planned, taken out of the state read and the update: the desk-and-LinkedIn test failed | 241/193/48 |
| 3. Act on what /recall finds | 418b003 | With the words switch on, `/recall` lists first lines, numbered, as many as **The bot lists at most**, each with **Write up**, and **Write one post from these** (`/write`'s rule, read at the press); off, the count and **Write one post from these**. Each button acts once, the others stay | `tests/test_telegram_bot_recall.py` (9) | Write one post from these taking every matching item, used ones too: "writes the unused items that hold the word" failed | 241/193/48 |
| 4. Remind me | 12fb5ec | Under "Saved to your collection.", **Remind me** offers the creator's moments; the one pressed keeps a reminder with **Cancel**. At that moment the bot brings the item back with **Write it up** and **Not now**: once, after quiet hours, after a restart, never once the item is removed. Your collection lists each waiting reminder on its item with **Cancel** | `tests/test_telegram_bot_remind.py` (17, with the migration), `tests/test_telegram_bot_remind_ui.py` (2, axe in both themes) | An item's removal leaving its reminders: the removal test failed | 242/194/48 (`/api/v1/collection/reminders/{reminder_id}`) |
| 5. Today's ideas on the phone | 2a8b62a | `/ideas` reads today's batch, never builds one: with the words switch on, each card with words to write from (the creator's own, their model's idea, or an Inox library form), with **Write up** (a card whose title can name someone, such as a follow, is only counted, and no figure goes); off, how many are ready; with no batch, that it is not made yet and how it is made. Write up writes a draft from the card, marks it used, and the Composer says where it came from | `tests/test_telegram_bot_ideas.py` (9) | `/ideas` building today's batch when none was there: "builds nothing" failed | 242/194/48 |
| 6. `Schedule <when>:` plans for real | 8f6273c | `Schedule tue 09:00: text` saves the draft and plans it for then, with **Undo** that unplans it; a time not read, or past, keeps an ordinary draft and the answer says why. The help's warning that it "does not schedule anything" is gone | `tests/test_telegram_bot_schedule.py` (4) | A planned Schedule message carrying the draft's own Undo, which refuses a queued draft: the Undo test failed | 242/194/48 |

Each item's help, privacy policy (with `release/privacy.html` rebuilt) and checklist lines were written in its own commit, in a "Phase 5 on your phone" section of `docs/help/test-your-telegram-bot.md`, and the checklist test quotes each new sentence from the code (six new checks, and a seventh with this record, holding the upgrade's notice word for word to what a bot paired under 2.13.0 is told).

### Migration

- **43** (item 4), `item_reminders`: one row per reminder: the item, the moment (UTC), the label of the moment pressed, when it was asked for, and when it was told. A row rather than a settings list because reminders are listed on their items and cancelled one by one in the box while the worker tells others, and they are the creator's own data. Counted in Storage with the collection, exported, removed with an item (Remove, Undo, a `Draft:` taken back) and by Delete everything, kept in backups. Forward only, re-runnable, behind the automatic backup, with a test that an older database gains it and a second run adds nothing, named with no word an earlier migration's test finds its own by.

### Preferences added

| Preference | Default | Set in | Read by |
| --- | --- | --- | --- |
| Plan it offers (`telegram_plan`) | your Queue's next 3 open slots (1 to 4), found as the Queue finds its next open slot; with none open in two weeks, your own times: tomorrow at 09:00 and at 18:00 (1 to 4, each 0 to 14 days ahead) | the Telegram panel | Plan it |
| The bot lists at most (`telegram_list_at_most`) | 5, from 1 to 10 | the Telegram panel | /plan, /recall |
| Remind me offers (`telegram_remind_moments`) | This evening (today, 18:00), Tomorrow morning (tomorrow, 09:00), Next week (in 7 days, 09:00); 1 to 4, labels up to 24 characters | the Telegram panel | Remind me |

Each control shows its default beside it; each is tested: changing it changes what the bot offers, a wrong value is refused with a sentence and nothing is saved, and a fresh profile gets the default. The fixed five first lines of `/recall` are gone: the list follows the preference.

### What else is kept

- The worker's state, kept only for the bot it was made for (the phase 4 race, now one pattern): the menu's record (with the command names, since this phase), the upgrade's notice (`telegram_tour`), what notifications mark told, and a reminder's claim, each written under the worker's check lock after checking the token; removal stops the worker, then deletes the menu record again with the other rows. The notice is removed with the bot and by Delete everything.
- On a draft's `made_with`: `via: telegram` for a draft asked for on the phone (the tour's evidence), `planned` for a plan from the phone, and `card`, `day` and `card_title` for a draft written from one of the day's ideas.
- With a message's buttons: Telegram's id for a message about a draft (so a `/plan` reply finds it), the times or moments offered, the items `/recall` listed and the word asked, the cards `/ideas` listed.

### Changed in earlier phases' tests, and why

- "Paired." now offers the tour; the tests compare with `SENTENCES["paired"]`, so only the checklist's quoted sentence changed.
- `tests/test_telegram_bot_phase4_panel_ui.py`: the menu's commands are read from the code (help, tour, idea, ...), no longer "help, idea".
- `tests/test_telegram_bot_reshape.py`: the buttons under a draft now include **Plan it** (four lists).
- `tests/test_collection_bot_writing.py`, `tests/test_phone_files.py`, `tests/test_phone_media.py`, `tests/test_telegram_bot_remember_this.py`: the buttons under a saved item now include **Remind me**.

### Decided against, while building

- A separate tour message after pairing: "Paired." carries the button, so pairing still sends one message.
- An upgrade notice when the menu record cannot say what the chat had: nothing is offered rather than a guess.
- Plan it and Remind me spending themselves: both stay on their message, to be pressed again for fresh choices.
- A message of times when none is open: the notice says how to reply with `/plan`.
- Planning a due post, a post queued at the desk, or one LinkedIn holds; a `/plan` reply to "Saved as a draft" (the PRD's decision kept).
- Remind me for an item without words, and reminders for anything but an item.
- Marking a tour step seen for steps that leave nothing (/help, /status, Send me the whole post, /recall's list).
- A browser test for the Composer's one-sentence change: it adds no control.

### What remains unverified

The real service: everything here runs against the fake. In particular, on the real Bot API: that editMessageText replaces a tour part and its buttons in place on the phone; that the owner's own 2.13.0 menu record is recognised (tested against 2.13.0's list word for word); that a reply to the bot's own message carries `reply_to_message` for `/plan`; how a row of five number buttons reads on a phone; and that a plan's due reminder and a reminder arrive at their times on the owner's machine (the scheduler marks due every 30 seconds; quiet hours hold both). The owner's checklist covers each, in "Phase 5 on your phone".

### Suite

As CI runs it, at the end, on 8f6273c: the interface built, then `pytest tests studio/tests -q -rs`: 4,577 passed, 0 failed, 19 skipped, in 21 minutes 46 seconds. 4,596 tests collected: 2.13.0's 4,512 and the 84 this phase added (78 in nine new files, 6 in the checklist's test). Each skip names a Windows or macOS primitive, a workstation's browser, this machine's autostart, or a missing yaml module. Also: flake8 with CI's selection, 0; `tools/sync_version.py --check`, in sync at 2.13.0; `tools/ui_audit.py` on a fresh install, 68 screens, 0 with blocking findings. Before each commit, the new test files ran three times in a row, and the Telegram, collection, phone, ingress and memory suites ran whole after items 1 and 2 (425 and 682 tests; the failures they found were the earlier phases' button lists this phase changed, listed above). After the suite, this record's commit added the seventh checklist check; the checklist and docs suites then passed, 121 tests.

## Phase 6

The record of the sixth phase, asked for on 2026-11-03 ("continue", after phase 5 shipped) and written down before its code in [the phase 6 PRD](bot-phase6.md). Branch `qc4/bot-phase6`, from `6c1bba2` (2.14.0, schema 43). A chore and five items in the brief's order, and a Composer fix found while reading for the PRD, each with a failing test first, the code, one guard falsified, and one commit. No independent review. The version, the CHANGELOG and the privacy policy's "Last updated" line stay as they are: the release does those.

### How it is tested

As phase 5 left it: the fake Bot API (`tests/telegram_fake.py`) and the fake provider (`tests/ai_fake.py`), both on loopback, the studio's own worker driven end to end. Nothing new was needed in either. Three habits from CI's last rounds were kept throughout: the bot's clock (`telegram_bot.local_now`) is held before the worker starts and never moved while it runs (a setting's `since` is written on its row, and quiet hours are changed by their setting, not the clock); a button's answer is read only after waiting for it; and a reply to one of the bot's messages is pushed only once the bot has kept Telegram's id for that message, which it does a moment after the phone shows it. Browser tests wait for a settled page and run the shared axe helper, which stills transitions, in both themes. Nothing reaches the network.

### Items

Census in `tests/test_endpoint_reachability.py` as total paths / reached by the interface / unreachable: 242/194/48 throughout, since the one route this phase needed is a parameter on an existing path.

| Item | Commit | What the creator now sees | Test first | How the guard was falsified | Suite at the commit |
| --- | --- | --- | --- | --- | --- |
| The PRD | 840f8b8 | Nothing yet: each item's build, place, storage, what may leave and under which switch, preferences and what was decided against; the evidence read in the code first; Telegram's rules quoted again from the Bot API page; no migration | | | The docs suite, 56 passed |
| 0. Any set of test files runs together | 7ae1889 | Nothing: a hand-picked run of test files no longer errors on `library_bundle` | `tests/test_any_test_files_run_together.py` (2: the privacy page's renderer test, and `tests/test_licensing.py`, each run before a bot test in a process of its own) | The conftest's binding taken out: the licensing pair failed again | The files that touch `library_bundle`, 107 passed |
| Found while reading: the Composer opens a draft planned with `Schedule` | 6f3a199 | A draft saved and planned with `Schedule tomorrow 09:00:` from the phone, or unplanned with Undo, opens from the Queue's **Edit text** and from Your collection's **Open it**; until now the page went blank | `tests/test_composer_reads_any_draft_record_ui.py` (2, axe in both themes) | The note reading `made.items` as it was: both failed with the page error | Every test that reads the Composer's note, 32 passed |
| 1. It connects to, in real time | 37eb3ca | When something with words is saved, "Saved to your collection." also says how many other unused items share at least two of its meaningful words or tags ("It shares words with 3 other unused items in your collection."), with **Write one post from these**: the item and the ones it connects to, read again at the press, through Combine. Their first lines only with the words switch on. Your collection says on each new item what it connects to and the words they share, with **Open the group** and **Combine these 4 into one post**. Matched on the computer | `tests/test_telegram_bot_connected.py` (13), `tests/test_telegram_bot_connected_ui.py` (3, axe in both themes) | The pool of connections taking used and set-aside items: three failed | 575 passed |
| 2. Bring back an unused idea | 9b4c60f | Off by default: on the creator's days and hour, the oldest unused item with words older than their age comes back, never one set aside, used or with a reminder waiting, never the one brought back last nor the one the morning idea offered last, with **Write it up**, **Remind me** and **Not now**; its kind and age, and its first line only with the words switch on. Once a day, after quiet hours; the panel says "NEXT ONE BROUGHT BACK:" | `tests/test_telegram_bot_bring_back.py` (15), `tests/test_telegram_bot_bring_back_ui.py` (1, axe in both themes) | "The one brought back last" taken out of what is passed over: the never-twice test failed (on the first try it passed, since marking the item offered covered it alone; the test now has the morning idea offer another item in between) | 840 passed and 1 failed, below; fixed in the commit, the panel's browser tests then 21 passed |
| 3. See what you have from the phone | df76da6 | `/recall` alone lists the newest unused items (first lines and **Write up** only with the words switch on; off, how many and where). A new `/remembered` lists the things the studio remembers, each with **Forget**, their words only with the words switch on. The menu gains `/remembered`; a bot whose menu 2.14.0 registered is told once of it alone | `tests/test_telegram_bot_lists.py` (13: 12 failed before the code) | `COMMANDS_2_14` left out of `EARLIER_COMMANDS`: the frozen-list test and the fingerprint-only notice failed | 619 passed |
| 4. Reply to a draft with what to change | b331361 | A plain reply to the bot's message about a draft offers **Rewrite it with what you said** and **Keep it as a note** instead of filing a note. The rewrite uses the creator's words as the instruction through their provider, keeps the replaced text for **Undo** ("before your reply" in the Composer), and sends its first line only with the words switch on; with no provider the offer says so. A draft planned from the phone may be rewritten and keeps its plan | `tests/test_telegram_bot_draft_reply.py` (12; the first 11, written before the code, all failed), `tests/test_telegram_bot_draft_reply_ui.py` (2, axe in both themes) | Any queued post taken as rewritable: "a post queued at the desk or published is not rewritten" failed | 636 passed (the series file deselected) |
| 5. A series from a group | 8cc11cd | **Write it as a series** under `/recall`'s answer for a word two or more unused items hold, and **Write a series of 3 from these** in Your collection's group: the creator's number of drafts in one request, each checked, all kept or none, each its own draft recording its part. **Plan the series** puts the parts into the Queue's next open slots, in order, the Queue's cooldown apart, through Plan it's path, with **Undo**; too few slots plans nothing. Nothing is posted | `tests/test_telegram_bot_series.py` (9: 8 failed before the code), `tests/test_telegram_bot_series_ui.py` (2, axe in both themes) | A series keeping the parts that pass the check when one does not: "one part with a figure not sent keeps none" failed | 674 passed, with the Queue's own suites and the census |

"Suite at the commit" is the Telegram bot's, the collection's, the phone's, the ingress's and memory's suites, with phase 4's pairing and phone-settings files, and the record or Queue suites where an item touched them, run before that commit.

Each item's help, privacy policy (with `release/privacy.html` rebuilt by `tools/build_privacy_page.py`) and checklist lines were written in its own commit, in a "Phase 6 on your phone" section of `docs/help/test-your-telegram-bot.md`; the checklist test quotes each new sentence from the code (six new checks).

### Migration

None: the schema stays 43. Every new preference is a settings row or a field of the writing preferences' row; which item was brought back last is a settings row; a group is worked out when asked; a reply's words wait with their message's buttons; a series is a key on each part's `made_with`.

### Preferences added

| Preference | Default | Set in | Read by |
| --- | --- | --- | --- |
| Words two items share to be connected (`connect_shared`) | 2, from 1 to 5 | Brand, Writing | the bot's saved answer and its press, Your collection |
| Connected items offered with one (`connect_offer`) | 3, from 1 to 9, never more than Most items in one draft with the item | Brand, Writing | the same |
| Say what something new connects to (`telegram_connect`) | on: a line and one button on an answer already sent | the Telegram panel | the bot's saved answer |
| Bring back an unused idea (`telegram_bring_back`) | off; Fridays at 16:00; older than 14 days (3, 7, 14, 21, 30, 60 or 90) | the Telegram panel | the bot, between polls |
| What a reply to a draft does (`telegram_draft_reply`) | offer to rewrite the draft with it | the Telegram panel | a reply to the bot's message about a draft |
| Drafts in a series (`series_parts`) | 3, from 2 to 5 | Brand, Writing | Write it as a series, on the bot and in Your collection |

"The bot lists at most" (phase 5) is now read by `/recall` alone and `/remembered` too. Each control shows its default beside it; each is tested: changing it changes what the bot or the box does, a wrong value is refused with a sentence and nothing is saved, and a fresh profile gets the default.

### What else is kept

- `telegram_brought_back`: which item an unused idea brought back was last, and when, written under the worker's check lock for the bot that told it, removed with the bot and by Delete everything. The item it brought back is marked offered (`offered_at`), as the morning idea marks one.
- With a message's buttons: the ids `/recall` alone and `/remembered` listed; under the offer a reply to a draft is answered with, that reply's words, dropped from the record once one of its buttons is pressed; under a series, its parts and, once planned, their times.
- On a draft's `made_with`: `connected` for a draft written from what an idea connects to, `series` (its id, its part, how many) for each part of a series, and a rewrite's earlier text said `by` "your reply" when a reply asked for it.

### Changed in earlier phases' tests, and why

- `tests/test_privacy_page_is_the_policy.py` (cycle 2) loads the renderer by its file and no longer puts `tools/` on the path (item 0).
- `tests/test_collection_writing_ui.py` (phase 3) names the morning idea's Saturday exactly: Bring back an unused idea has its own days, and "Sat" also matched its "on Saturday" box (item 2).
- `tests/test_resurfacing.py` (phase 3): `/recall` alone now lists the newest unused items, where it said how to send a word (item 3).
- `tests/test_telegram_bot_checklist.py` (phase 5): the upgrade notice a 2.13.0 bot was told is read from 2.14.0's own list, `COMMANDS_2_14`, since a 2.13.0 bot updated now is told of `/remembered` too (item 3).
- `tests/test_telegram_bot_plan_ui.py` (phase 5): "The bot lists at most" now says it reads `/remembered` too (item 3).
- `tests/test_telegram_bot_recall.py` (phase 5): `/recall`'s answer carries **Write it as a series** while two or more unused items hold the word (item 5).

### Found while building, and fixed

- The Composer's crash on a draft planned with `Schedule` (2.14.0, phase 5 item 6), above: a fix of its own, with a browser test, before item 1.
- Item 1's switch description named the words switch, "The bot may send me what it writes from my collection", word for word, and so did item 2's first draft; a phase 3 browser test finds that switch by its name, and found three. Both now say "the switch that lets the bot send what it writes", as the morning idea's always did. Fixed in item 2's commit, which is where the run that found it ran.
- The PRD counted 2.14.0's commands as eleven; there are thirteen. Corrected in item 3's commit.
- Item 2's age test forgot today's told mark before it saved the new age, so a turn of the worker between the two could mark the day told again under the old age; it never failed here, and the order was found by reading. The new age is saved first now (20381be).

### Decided against, while building

- A connection line under the answer to a reply that added to an item, or to an edit: those answers are about the words just added; Your collection shows the item's connections.
- Ticking a group's items for Combine when it is opened: a creator's own ticks would be overwritten, so the group has a button of its own.
- Changing the Composer's From your collection to read the new preferences: it ranks by shared words and shows three, as phase 3 chose; named here as a candidate for later.
- Listing the morning idea in the panel's seen-working list: a day it is marked told does not prove an idea went.
- Write one post from these under `/recall` alone: the newest items share nothing but their age. An Undo under Forget: the list showed its words, and `/remember` keeps it again.
- Checking a draft's state when the rewrite is offered: the press reads it and says what became of it, so the offer stays one message and the reply's words wait with it. Following an edit of the reply into the offer. Offering the rewrite under "Saved as a draft" (the creator's own words, planned at the desk: phase 5's decision kept).
- Rewriting a due post: once due it is the moment to post, at the desk.
- A series from the saved answer itself (its buttons are already many), with the creator's own times (two on one day break the Queue's spacing rule), or keeping the parts that pass the check when one does not.

### What remains unverified

The real service: everything here runs against the fake. In particular, on the real Bot API: that a reply to the bot's own message carries `reply_to_message` as Telegram documents (phase 5 relied on it for `/plan`; the rewrite offer relies on it for every reply); how a saved answer with a connection line and five rows of buttons reads on a phone; that an idea brought back arrives at the creator's hour on the owner's machine (the worker looks once a minute; quiet hours hold it); and that the owner's own 2.14.0 menu record is recognised (tested against 2.14.0's list word for word, by its names and by its fingerprint). The owner's checklist covers each, in "Phase 6 on your phone".

### Suite

As CI runs it, at the end, on 8cc11cd with this record: the interface built, then `pytest tests studio/tests -q -rs`: 4,661 passed, 0 failed, 16 skipped, in 23 minutes 24 seconds. 4,677 tests collected: 2.14.0's 4,597 (counted again from its tag) and the 80 this phase added (74 in eleven new files, 6 in the checklist's test). Each skip names a Windows or macOS primitive, a workstation's browser, this machine's autostart, or the lead enrichment the interface does not surface; with pyyaml installed from the requirements, no yaml skip. Also: flake8 with CI's selection, 0; `tools/sync_version.py --check`, in sync at 2.14.0; `tools/ui_audit.py` on a fresh install, run against a sandbox studio in the scratchpad whose browser launcher starts nothing and whose browser contexts block service workers, 68 screens, 0 with blocking findings. Before each commit, the new test files ran three times in a row, and the Telegram, collection, phone, ingress and memory suites ran whole, with the pairing and phone-settings files and the record or Queue suites where an item touched them: 575, 840, 619, 636 and 674 tests at items 1 to 5 (the one failure, at item 2, is above). After the suite, this record's commit added a few words to the checklist's first phase 6 step (a collection that holds other notes about pricing says how many); the checklist and docs suites then passed.
