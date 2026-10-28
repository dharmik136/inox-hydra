# The collection box: everything sent to the bot, in one place, made into posts, and remembered

Phase 3 of the Telegram bot, written before any of its code (2026-10-29). Branch `qc4/collection-box`, from `a360b74` (2.11.0). It says what will be built, where each part lives, what is stored, what may leave the machine and under which switch, and what was decided against. The record of what was built follows it, item by item, once each is committed.

## The owner's words, and the reading built here

"no as this will be used by single person they can have this one of this collection box having everything here in one bot also that is way much more real time ideas and features are needed here on the bot and on our product to make something out of those things and remember them for some things"

And, the same day, for every AI feature: "do not hardcode things as they will be users preference in AI work".

Read as:

1. One person, one bot, and that bot is the single collection box for everything they send. No bot per profile.
2. No screenshot OCR and no voice transcription in this phase.
3. Collect everything in one place; make something out of it in real time, on the bot and in the studio; have the studio remember it and use it later.
4. Every choice an AI feature makes is the creator's preference, with a default they can see and change, read the same way in the studio and on the bot.

## What exists, and how each item reuses it

| What exists | Where | How this phase uses it |
| --- | --- | --- |
| Phone text saved as a draft, tagged `mobile-ingress` (and `idea` for `/idea` and `Idea:`) | `ingress._store`, `database.create_draft` | No longer the landing place: text lands in the collection and becomes a draft only when the creator makes one from it. `Draft:` and `Schedule <when>:` still go straight to a draft, recorded in the collection as used |
| `/ask` | `record_store.add_ask(..., "telegram")` | Unchanged. An ask steers From your record; it is not material for a post, so it is not copied into the collection |
| A link to one of the creator's posts, and an `lnkd.in` short link | `desk_requests.record` and `record_short`; Today's "ONE THING TO OPEN" | Unchanged. The collection lists it too, pointing at the request rather than holding a copy, with the request's state |
| A link to someone else's post | a refused desk request, "not one of your posts" | Kept as a bookmark: the post's address rebuilt from its activity id, and the creator's own words sent with it. The address's slug, which carries the author's name and the post's words, is never kept |
| Idea drafts turned into asks each day | `record_daily.sync_telegram_ideas` | Left for idea drafts sent before this phase. New ideas reach the cards from the collection itself (item 3) |
| The daily cards and their grounding | `record_cards.compute_local`, `you_asked` (slot 3), `ROW_KEYS`, `verify` | Slot 3 may draw an unused collected idea, cited by its row like any card, so a removed item drops its card |
| The model gateway | `model_gateway.get_current_ai_config`, `execute_structured_completion`, `ProviderError`; egress category `model` | Every new request goes through it: the creator's own provider, counted under `model`, refused with `INOX_NO_EGRESS` |
| Grounding | `record_model.has_number`, `known_names`, `scrub`, `verify_ideas` (drops, never repairs); `formatters.clean_text_formatting` | The writer follows the same rule: an answer carrying a figure, or a person known to the studio, that is not in what was sent is refused and said, never repaired |
| The voice pack | `voice_pack.prompt_block`, `told` | Sent with every new request and listed where it is today |
| Command, Re-Hook, the daily idea | `repurposer.command_ai_engine`, `generate_10x_hooks`, `record_model` | Read the same preferences and things to remember |
| A draft made from a card | `record_store.draft_from`; `App.onDraftFromCard` | The pattern for Use as a draft and Make a post: a posts row, which the Composer adopts |
| The change stream | `changes.publish`, `/api/v1/events`, `refresh.ts` | A new kind, `collection` |
| Storage, export, forget, backups | `retention.CATEGORIES`, `support.EXPORTABLE_TABLES`, `onboarding.forget_phone_and_export`, `support.create_backup` | The new tables are counted, exported, forgotten with everything else, and backed up with the database |
| The bot's buttons, quiet hours and weekly summary (2.11.0) | `telegram_bot` | New buttons in the same store, the morning idea held by quiet hours, the weekly summary counting unused ideas |
| Settings rows | `settings` | Every preference is a row there, read through one module |

## Why migrations, and which

The collection needs a table. Each item has a kind, its words, a status the creator changes (new, used, not now) and what it became, and no existing store holds that: drafts are posts in progress (the Composer's list, the Queue, search), desk requests are Today's list of pages to open with their own lifecycle, and asks steer the cards. Saving raw ideas as drafts is what filled the Composer's drafts list with phone fragments.

- Migration 38, with item 1: `collection_items`. What was already sent from the phone (each `mobile-ingress` draft, each request from Telegram) is recorded in it once, as used, so the box shows everything sent and the counts carry on. Re-runnable: `IF NOT EXISTS`, and each recorded row keyed so it is written once.
- Migration 39, with item 3: `remembered`, the things to remember, and `posts.made_with`, what a draft was written from and with which things to remember.
- Migration 40, with item 4: `collection_items.media` (where a photo's or a voice note's file is kept, its type and size, and a photo's width and height or a voice note's length; never what is in it) and `collection_items.media_asset_id` (the media library's copy of a photo, once the creator puts it there).

## The items, as they will be built

### 1. The collection box

What the bot does with what it is sent:

| The creator sends | Kind | Kept | Also | The bot answers |
| --- | --- | --- | --- | --- |
| Text | note | the text, its hashtags as tags, a topic | | Saved to your collection. |
| `/idea text` or `Idea: text` | idea | the text | | Saved to your collection. |
| A forwarded message | forward | its text, as the creator's note | the forward's origin (a person, an account, a channel, a signature) is never kept | Saved to your collection. |
| A link to one of their posts | your post | the address rebuilt from its id, and any words with it | a request on Today, as now | Saved to your collection. Today will ask you to open this post's analytics at your computer. |
| An `lnkd.in` short link | link | the short link | a request on Today, as now | Saved to your collection. Today will ask you to open this link at your computer. |
| A link to someone else's post | bookmark | the address rebuilt from its id, and the creator's own words with it | nothing is opened or fetched | Saved to your collection as a bookmark. Your studio never opens other people's posts. |
| `Draft: text`, `Schedule <when>: text` | note, used | the text | saved straight as a draft, as now | Saved as a draft in your studio. |
| A photo or a voice note | photo, voice | item 4: the file as it is, and any caption | never read | Saved to your collection. |

Each item has: when it arrived; its kind; its words; tags (its hashtags) and a topic (the first of the creator's own topics from Setup that its words name, else its first hashtag, else none: local, no model); a status (new, used, not now); and what it became (a draft, which opens in the Composer, or the request on Today with that request's state).

In the interface: From your record gains a level, "Your collection", beside Today's cards, Kept, What the studio knows and Did these help?. It lists the items newest first, filtered by status (new by default), kind and a word, and re-reads on the `collection` change, so a message sent from the phone appears without a reload. In item 1 each item offers Use as a draft (its words, as they are, into the Composer), Not now, Back to new and Remove.

Undo (2.11.0) stays under the bot's answer: it removes an item that is still new, or a `Draft:` draft that is still untouched in the studio.

### 2. Make something out of it

In the studio, on an item: Make a post (a draft written from it, into the Composer) and Angles (the creator's number of opening lines, each with Write it up); on two or more selected: Combine (one draft from all of them, ten at most so a request stays small). With no provider set up, each says so plainly and offers Use as a draft.

What is sent to the provider, and nothing else: the items' words, the things to remember the creator allowed, the voice pack as Command sends it, and the writing preferences, under the existing `model` category. The answer is cleaned of em dashes. A draft or an opening line that carries a figure, or the name of a person known to the studio, that is not in what was sent is refused and said, never repaired. What a draft was written from, and with which things to remember, is kept on the draft (`made_with`) and shown in the Composer.

On the bot, under "Saved to your collection.": Write it up, and "<n> angles", n from the preference. A press is answered at once ("Writing it up in your studio.") and the writing runs beside the bot's loop, never in it; when it is done the bot sends a new message, which the phone notifies (an edit does not). A new switch, off by default, "The bot may send me what it writes from my collection": off, the bot says only "Draft ready in your studio." or that the angles are ready in the studio; on, the message carries the draft's first line, or the angles with a button to write each up. The creator's own words then sit on Telegram's servers: the panel, the help and the policy say so, as they do for figures.

A morning idea, off by default, on the days and at the hour the creator picks (Monday to Friday, 08:00), held by quiet hours, and only while the switch above is on, since it carries words: one unused item, the one offered least recently, with an angle from the creator's own record (the form of the openings of their posts that did best against their usual, as the voice pack reads them; never a figure), and Write it up and Not today.

### 3. Memory

`/remember <something>` and `/forget <words>` on the bot, and "Things to remember" in Brand, in a new view, Writing: each fact with what it is about (you, your audience, an offer, a date), whether it is used in writing, edit and remove. Used as context in every writing request (Command, Re-Hook, the daily idea, Make a post, Combine, Angles, Write it up), as the creator chose (all of them, chosen ones, or none); never in an image prompt. A draft the studio writes says which were used; Command's answer lists them with what was sent; What the model is told lists them.

Counted in Storage, exported, removed by Delete everything, and kept in backups with the database.

Resurfacing: the Composer shows "From your collection", the unused items whose words the draft shares, folded like What worked for you; the daily cards' slot 3 may draw an unused collected idea, cited like an ask; the weekly summary counts unused ideas; `/recall <word>` answers with how many items match, and their first lines only with the switch above on.

### 4. Photos and voice notes, kept as they are (if budget allows)

Downloaded with getFile under the `ingress` category, counted under an address without the token; kept in the profile's assets folder; shown or played in the box; a photo can be a post's image. Never read: no OCR and no transcription.

As built: the largest size of a photo, or the voice note, is fetched (getFile, then the file, each through `egress.require` under `ingress`, counted as `.../bot<token>/getFile` and `.../file/bot<token>/<file>`), refused before it is fetched over 20 MB, and kept under `assets/phone` by a random name, never Telegram's own path. A caption is the creator's words, so a photo with one can be written up. A post's image, in this product, is an image in the media library: the Composer attaches no file to a post, and the creator adds it on LinkedIn, so **Add to your media library** copies a photo there (`POST /api/v1/collection/{item_id}/media`), where it stays even if the item is removed. Undo, Remove and Delete everything take the files with the items.

## Preferences

Every choice the writing features make is one of these. They are read through one module (`studio/backend/writing.py`), kept as rows in `settings`, and the template each request is built from lives in that module and is filled from them, so no wording a creator would want to change is fixed in a prompt. The rules that keep an answer honest (only what was sent, no invented figure or person, no em dash) are the product's guarantees, not preferences.

| Preference | Default, as a fresh profile gets it | Set in | Read by |
| --- | --- | --- | --- |
| Length of a draft | about 150 words | Brand, Writing | Make a post, Combine, Write it up |
| Tone | punchy, high-signal, authentic and authoritative (Command's words until now) | Brand, Writing | every writing request |
| Language | the language of what you wrote | Brand, Writing | every writing request |
| Opening line | a first line that stops the scroll (Command's rule until now), or one of Re-Hook's forms | Brand, Writing | Make a post, Combine, Angles, Write it up, Command |
| Emojis | none | Brand, Writing | every writing request |
| Hashtags | only those in your note | Brand, Writing | every writing request |
| Line breaks | short paragraphs of one or two sentences, with generous spacing (Command's words until now) | Brand, Writing | every writing request |
| Ending | an authentic, thoughtful question or takeaway (Command's words until now) | Brand, Writing | Make a post, Combine, Write it up, Command |
| Words to avoid | In today's fast-paced world, game-changer, delve, testament (Command's list until now) | Brand, Writing | every writing request |
| How many angles | 3, from 2 to 5 | Brand, Writing; shown in the box and on the Telegram panel | Angles, and the bot's "<n> angles" button |
| Things to remember | all of them; or chosen ones; or none | Brand, Writing, beside the list | every writing request |
| Ideas draw on | your collection, your posts and your asks | From your record, What the studio knows; shown beside the morning idea | the daily cards, the daily idea, the morning idea |
| Ideas asked for each day | 3, from 1 to 5 (it was a fixed three); the first that passes every check is shown | What the studio knows, beside the model stage | the daily idea |
| Morning idea | off; Monday to Friday; 08:00 | the Telegram panel | the bot |
| The bot carries what it writes | off | the Telegram panel | Write it up, angles, the morning idea, `/recall` |
| Provider and model | as connected on the Composer's Prompt tab | the Prompt tab, as now: the product connects one provider for every task | every request; named beside each feature |

Re-Hook keeps its ten forms (its catalogue, one opening line each), and reads the tone, language, emojis, words to avoid and things to remember. Each feature names the preferences it reads, with their values and defaults, beside it: the box, the Prompt tab (Command and Re-Hook), What the studio knows and the Telegram panel. Each preference is tested: changing it changes what the fake provider receives, or what the bot offers, and a fresh profile gets the default.

## What may go where

| What | To Telegram | To the AI provider | Kept |
| --- | --- | --- | --- |
| The creator's words in an item | only with "The bot may send me what it writes from my collection": a draft's first line, the angles, the morning idea, `/recall`'s first lines | when they press Make a post, Combine, Angles or Write it up | `collection_items` |
| Things to remember | never | with each writing request, as chosen | `remembered` |
| Writing preferences | the angle count, as a button's label | with each writing request | `settings` |
| A forward's origin, another person's name or words, a post's slug | never | never | never |
| Figures | only as before: `/today`, the 24 hour figures and the weekly summary, each with the figures switch | none added by this phase | as before |
| Photos and voice notes | never sent back | never | the profile's assets folder |

## Sections, and why

The owner's rule for the interface is "things in sections only, but each section properly optimised".

- The collection is a level of From your record, not a new rail section. The record is "what is worth writing from today", the collection is the creator's own material for that, and a level costs one button where a section costs a rail entry. Today stays a one-screen brief, and the Composer still opens on its editor.
- Brand gains one view, Writing, for the preferences and the things to remember: both are about the creator and how they want to sound, beside the read-only "How you write" in Profile. One editor; every feature that reads a preference shows its value and where to change it.
- The Composer gains a folded "From your collection" beside What worked for you, and its Prompt tab shows the preferences Command and Re-Hook read.
- Settings, Local security: the Telegram panel gains the bot's switches.

About ten new API paths, each reached by the interface; the census in `tests/test_endpoint_reachability.py` is re-measured in each commit that adds one.

## Decided against

- A bot per profile, OCR and transcription: the owner's decision.
- Writing a draft the moment something arrives: nothing is written until the creator asks.
- Fetching a link, reading another person's post, or keeping a slug, a forward's origin or another person's name.
- Sending the creator's words to Telegram by default.
- A provider or model per task: the product connects one; each feature names it.
- Things to remember in image prompts: those describe a picture, not the creator's writing.
- Ctrl+K search over the collection: the box has its own filter, and an index for it is a migration of its own, later.
- Changing Re-Hook's count: its ten forms are its catalogue.
- Copying asks into the collection, or the collection into asks.

## Tests

Per item: a failing test first, against the fake Bot API and a fake provider on loopback (moved into `tests/ai_fake.py`, shared as `tests/telegram_fake.py` is); a guard falsified; the custody checks each new table passes (the pattern of `tests/test_qc4_t7_schema_and_custody.py`); a browser test with axe in both themes for each new control; the census re-measured. One full suite as CI runs it at the end, with flake8 and `tools/ui_audit.py`.

## Phase 3 record

What was built, item by item, on `qc4/collection-box` from `a360b74` (2.11.0). Each item: a failing test first, the code, one guard falsified, one commit. Census in `tests/test_endpoint_reachability.py` as total paths / reached by the interface / unreachable.

| Item | Commit | What the creator sees | Tests first | Falsified, and caught by | Census |
| --- | --- | --- | --- | --- | --- |
| This PRD | `01bf14f` | Nothing yet: the reading, the reuse, the migrations, the preferences, what may go where, and the sections | | | 228/180/48 |
| 1. The collection box | `9f33436` | Your collection, a view of From your record: everything sent to the bot, live, with status filters (with counts), a kind filter and Find a word; Use as a draft, Not now, Back to new, Remove. A bookmark is the post's address rebuilt from its id with the creator's words; a forward keeps its text, never its origin | `test_collection_box.py`, `test_collection_custody.py`, `test_collection_box_ui.py` | A bookmark kept as the address sent (with its slug): `test_someone_elses_post_is_a_bookmark_kept_without_its_slug` | 232/184/48 |
| 2. Make something out of it | `aabbe0d` | Make a post, the "<n> angles" button and Combine in the box; Write it up and "<n> angles" on the bot; the switch "The bot may send me what it writes from my collection" and the morning idea, both off; Brand's Writing view, every preference with its default | `test_collection_writing.py`, `test_collection_bot_writing.py`, `test_collection_writing_ui.py` | The grounding check switched off: `test_an_invented_figure_or_a_known_name_is_refused_never_repaired`; the words switch forced on: `test_the_words_switch_is_off_by_default` | 235/187/48 |
| 3. Memory | `a88126d` | Things to remember under Brand, Writing (add, edit, tick, choose which go, remove), `/remember` with Undo, `/forget`, `/recall`; the Composer's What this draft was written from and From your collection (Add to the draft, Undo); Ideas draw on and Ideas asked for each day on What the studio knows | `test_memory.py`, `test_memory_custody.py`, `test_resurfacing.py`, `test_memory_ui.py` | Things to remember sent with memory off: `test_only_the_ticked_ones_with_chosen_and_none_with_off` | 239/191/48 |
| 4. Photos and voice notes | `2ed09cc` | A photo shown and a voice note with a player in the box, each "kept as it is", never read; Add to your media library on a photo; the bot's two new sentences for a file too big or not handed over | `test_phone_media.py`, `test_phone_media_ui.py` | The file's real address (with the token) given to the egress check: `test_the_file_is_fetched_through_the_egress_check_and_counted_without_the_token` | 240/192/48 |

The full suite as CI runs it (`pytest tests studio/tests -q -rs`), at the end: 4,358 passed, 0 failed, 17 skipped (phase 2 of the bot ended at 4,267 passed). flake8 as CI runs it: 0. `tools/ui_audit.py`: 68 screens, 0 with blocking findings. The version stays 2.11.0.

Migrations: 38 (`collection_items`), 39 (`remembered`, `posts.made_with`), 40 (`collection_items.media`, `media_asset_id`), each appended to `MIGRATIONS`, forward only, re-runnable, with the automatic backup before it and a test that an older database gains it and a second run adds nothing.

### The preferences, as built

Every AI choice is the creator's, read through `writing.py` from one `settings` row (`writing_preferences`), with its default shown beside the feature it shapes: length of a draft, tone, language, opening line, emojis, hashtags, line breaks, ending and words to avoid (Brand, Writing; read by Make a post, Combine, Angles, Write it up, Command and, for tone, language, emojis and words to avoid, Re-Hook); how many angles (Brand, Writing; the box's and the bot's button says the number); which things to remember go (all, the ticked ones, or none; Brand, Writing); what ideas draw on (your collection, your posts, your asks; What the studio knows, and beside the morning idea); how many ideas the daily model stage asks for (3, one to five; What the studio knows, beside the model stage; it was a fixed three); the morning idea's switch, days and hour, and whether the bot carries what it writes (the Telegram panel). Each is tested: changing it changes what the fake provider receives or what the bot offers, and a fresh profile gets the default. The provider and model are the one connected on the Prompt tab, named beside each feature: the product connects one for every task.

### Decided against, while building

- A per-task provider or model: the product connects one provider; each feature names it.
- Changing Re-Hook's ten forms or its count: they are its catalogue.
- Attaching a photo to a post in the Composer: no Composer post carries a file today (the Media tab says so), so a photo goes to the media library, where the images for a post are kept.
- Fetching anything for a sticker, a file or a video: still not kept.
- Writing anything when an item arrives: nothing is written until the creator asks.

### Also corrected

- The bot's `/help` said it never sends the creator's words, which stopped being true with the words switch: it now says it sends their words and figures only if they allow them, and nothing about anyone else.
- `/recall` said "1 items"; one match is now said in the singular.
- A `/remember` over 300 characters was answered as if it were empty; it now says how long a thing to remember may be.
- `tests/test_qc_f7_ui.py` counted Brand's three views; Writing is the fourth, and all four fit at 375 pixels.
- A LinkedIn post's address inside a note's or a forward's words is rebuilt from its id, without the slug that names its author, but no test held it: switching that off broke nothing. `test_a_post_link_inside_a_forward_is_kept_without_its_slug` now catches it.
- `test_a_strangers_photo_is_never_fetched`: a photo from any chat but the paired one is refused before anything is asked of Telegram.

### On the real phone

`docs/help/test-your-telegram-bot.md`, steps 7 to 13 of the later, optional part: Write it up and the angles, with the words switch off and on; the morning idea; `/drafts`; `/remember` with its Undo and the note on a draft it went with, then `/forget`; `/recall`; the Composer's From your collection; a photo with a caption and Add to your media library; a voice note played at the computer.
