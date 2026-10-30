# Send a post idea or a post link from your phone with Telegram

Make a Telegram bot of your own, set it up under Local security, and everything you send it lands in your collection in the studio, under **From your record**: notes, ideas, messages you forward and links. A link to one of your own LinkedIn posts is also the page Today asks you to open at this computer.

## What it is, and what it is not

- It is optional and off until you set it up. The studio asks Telegram for your bot's messages while it is running, and opens no port. Each request is counted under the `ingress` row of **What has left this machine** under **Local security** in **Settings**.
- The phone sends a link, never a figure. Nothing you send is written as a reading: a post link becomes a request to read that post here, where the extension reads the real page.
- The bot answers each message with one short fixed sentence, so you can tell it arrived. See [What the bot says back](#what-the-bot-says-back). Some of its messages carry buttons, such as **Undo** under what you sent. See [Buttons you can press](#buttons-you-can-press).
- Your message text passes through Telegram's servers. See [What leaves this machine, and when](what-leaves-this-machine.md).
- The studio must run at least once a day. Telegram keeps a bot's messages for one day, so anything you send while the studio is off, asleep or offline for longer may never arrive. When that may have happened, the bot and the panel say so once. See [A day the studio did not check](#a-day-the-studio-did-not-check).
- The bot belongs to the creator profile you set it up in, and its messages are saved there whichever profile is open. One bot is asked at a time: the one saved most recently, or when the studio starts, the first profile that has one. A profile whose bot is not the one being asked says so in its panel.

> [!NOTE]
> First tested against the real Telegram service on 2026-10-28, on the owner's computer: the studio asked Telegram for messages, refused a chat that was not the one saved, and saved a message once the right chat was paired. Until something from your own chat has been saved on your computer, the panel says it has not been seen working there. Anything saved from your chat counts, whenever it came: an item in your collection, a thing to remember or an ask, including what was saved before this version. After you pair a different chat, only what comes from that chat counts.

## What you need

Your own bot token. Creating a bot is done with Telegram's own tools (BotFather); the studio does not guide you. You do not need to find your chat id, which Telegram never shows you: the studio learns it from your first message when you press **This is me**.

## Set it up

1. Open **Settings** from the rail, then **Local security**.
2. Under **Your phone, through Telegram**, paste the bot token into **Bot token**, leave **Your numeric chat id** empty, and click **Save and start**. The panel reads **SET, SEALED** beside the token and **YES** beside **Asking Telegram for messages**.
3. On your phone, message the bot once. Anything will do: that message only says which chat is yours, and it is not saved.
4. Within a few seconds the panel lists it under **CHATS THE BOT REFUSED**, for example "1 message refused from chat 487215963, first: 'hello'. Is that you?". If that is your message, press **This is me**. Your chat id is saved, and from then on every message you send the bot arrives in the studio.

If you know your chat id already, you can type it into **Your numeric chat id** instead. The token is sealed before it is stored, like your AI key, and is never shown again. A token or chat id of the wrong shape is refused with a sentence and nothing is stored.

> [!IMPORTANT]
> Until a chat id is saved, the bot cannot tell you from anybody else, so every message is refused, and a refused message is not delivered again later. Only **This is me** pairs a chat: the studio never pairs one by itself, so a stranger who finds your bot is refused and listed, and stays refused. Messages from any other chat than the one saved are dropped. A group's chat id, which starts with a minus sign, cannot be saved, because anyone in the group could then file drafts in your studio. The chats refused are kept in memory only, until the studio stops: each chat's id, how many messages, when, and the first 60 characters of the first one. Nothing of a refused message is written to the database, and the log keeps only its chat id.

For maintainers, the older way still works: `INOX_DEV_MODE=1`, `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in the environment the studio starts from (`PRUDENT_TELEGRAM_BOT_TOKEN` and `PRUDENT_TELEGRAM_CHAT_ID` are also accepted), read once at startup. A token in the environment alone, without dev mode, starts nothing.

## Send an idea, or a post

Send the bot a message. You can start it with a prefix, in any letter case. Nothing is written from what you send until you ask: it waits in your collection.

| You send | Where it goes |
| --- | --- |
| Plain text | Your collection, as a note |
| `Idea: your text`, or `/idea your text` | Your collection, as an idea, without the prefix |
| A message you forward from another chat | Your collection, as a forwarded note: its text, and never who or what it was forwarded from |
| `Draft: your text` | Straight to a draft in the Composer, as before, and listed in your collection as used |
| `Schedule <when>: your text` | Straight to a draft, as `Draft:` is (see below), and listed as used |
| A link to one of your own posts, from the LinkedIn app's share menu or copied from the feed | A request on Today to read that post's analytics at this computer, listed in your collection; any words with it are kept there as your note |
| `Read: <post link>` | The same |
| A link to someone else's post, or to a post the studio does not hold | A bookmark in your collection: the post's address rebuilt from its number (never the name and words the address you shared carries), with your own words. The studio never opens it |
| A short `lnkd.in` link, which the LinkedIn app's **Copy link** gives, alone or with text around it | A post sent from your phone: Today shows "You sent a post from your phone", and your collection lists it. Nothing else in that message is kept, so send an idea in a message of its own. See below |
| A link to a profile, or any other address | Kept in the words of your note |
| A photo, with or without a caption | Your collection, as a photo, kept as it is and never read: no text is taken from it. Its caption is your words, with **Write it up** and the angles when it has one. See [Photos and voice notes](#photos-and-voice-notes) |
| A voice note | Your collection, as a voice note, kept as it is and never transcribed |
| Photos sent together, as an album | One item, with all its photos and the caption, kept as they are |
| A document: a PDF, or any other file, a music file among them | Your collection, as a document, kept as it is with its own name, and never read: no text is taken from it. Its caption is your words |
| A video, a round video message, or a GIF | Your collection, as a video, kept as it is and never transcribed |
| A sticker, a location, a contact or other message with no text | Nothing. It is skipped |

A link you hid behind words in Telegram (words you made into a link) is kept too: its address is written into the item's words right after them, and a LinkedIn post link behind words is taken as if you had pasted it, so one of your posts is asked for on Today and anyone else's is a bookmark, without the name and words its address carries. The same goes for a caption.

Any `#hashtag` in the text is one of the item's tags, up to 30 (a link's `#fragment` is not one), and its topic is the first of your own topics from Setup ("What you write about") that its words name, or else its first hashtag. An em dash in your message is saved as ` -- `.

> [!WARNING]
> `Schedule <when>:` does not schedule anything. The time is read but not stored, and the post is saved as an ordinary draft. Voice notes are kept as they are, and never transcribed.

The `Schedule` prefix is recognised only in a one-line message whose `<when>` uses just letters, digits, spaces, colons and hyphens, followed by `:` or `|`. Otherwise the whole message, prefix included, is saved as plain text. If your text contains another colon, everything before the last colon is taken as `<when>` and dropped.

## Your collection

Everything you send your bot lands in **From your record**, on its **Your collection** level, the moment it arrives: the page shows it without a reload. Each item says what it is (Note, Idea, Forwarded, Bookmark, Your post, Link, Photo or Voice note), when it came, its words, its tags and topic, and what it became.

- **New**, **Not now**, **Used** and **All** show the items of each kind of status, each with how many; **Every kind** and **Find a word** narrow the list.
- **Use as a draft** makes a Composer draft of the item's words as they are, and opens it. The item is then used, and says "Became: A draft in the Composer", with **Open it**.
- **Not now** sets an item aside, and **Back to new** brings it back.
- **Remove** takes an item out for good, once you confirm. A draft made from it stays a draft.

**Make a post**, **Angles** and **Combine** write from your items through your own AI provider. See [Make something out of it](#make-something-out-of-it).

A link to one of your posts, and a short link, are also requests on Today, and the item says what became of the request. A link to someone else's post is a bookmark, which the studio never opens; your own browser does, if you click it. What you sent before this version is listed too, as used: each message the bot saved as a draft, and each link it asked Today to open.

### Photos, voice notes, documents and videos

A photo or a voice note you send is downloaded from Telegram as it is, into your studio's media folder, and listed in your collection: a photo is shown, and a voice note has a player. Neither is read: no text is taken from a photo, a voice note is never transcribed, and nothing of either is sent anywhere. A photo's caption is your words, and can be written up like any note. Telegram sends the largest size of a photo it holds; a file over 20 MB is not downloaded, and the bot says so.

A document or a video is kept the same way, with its own name, and never read: no text is taken from a PDF and nothing is transcribed from a video. In **Your collection** a video plays, and a document offers **View** (a PDF, a picture or a plain text) and **Download**, under its own name. A file the studio cannot show, such as a Word document or a web page, is kept as a download only, and is never opened in the studio's own window. Photos you send together, as an album, arrive as one item, all its photos shown together, with the caption you wrote on any of them as its words; the bot answers the album once.

- **Add to your media library** copies what the media library takes into the Composer's **Media** tab, to use in a post: a photo or a picture (PNG, JPEG or WebP), every photo of an album, a PDF (as a document carousel) and an MP4 or WebM video, each checked as an upload is. It is not offered for anything else. The item is then used, and says "In your media library". The copy stays there even if you remove the item.
- **Undo** under the bot's answer, and **Remove** in the box, take the file with the item. Deleting everything the studio holds about you deletes every photo and voice note you sent, but not a copy you added to your media library, which is yours like anything you upload.

Your unused items come back while you write. In the Composer, **From your collection**, folded above the editor beside **What worked, from your own posts**, lists up to three new items whose words your draft shares, matched on this computer as you type, and says how many on its folded line. **Add to the draft** puts an item's words at the end of your draft, and the item is then used, with your draft as what it became; on a post you have not saved yet, that happens when you save it, if its words are still there. **UNDO** beside it takes the words back out, and the item is new again. The **You asked** card in **From your record** may draw an unused idea too, and the weekly summary counts them.

Your collection is counted in **Storage and privacy** as "Your collection: what you sent your bot", is in the data export and in backups like everything else, and is deleted when you delete everything the studio holds about you. A message is kept once, even if Telegram sends it again after a restart.

### Build an idea up over the day

Reply in Telegram to something you sent your bot, or to the bot's answer about it, and your new words go on that item in your collection, after its words, instead of making a new item: press and hold the message, choose **Reply**, and write. The bot answers "Added to the item in your collection.", with **Undo** under it, which takes those words back off while you have not used the item since. With **The bot may send me what it writes from my collection** on, the answer also says the item's first line, so you can see which it was. If the item already became a draft, the words still go on the item, and the bot adds "The draft made from it was not changed." In **Your collection**, an item built this way says "from 3 of your messages".

A command in a reply is still a command, a photo or a file in a reply is an item of its own, and a reply to something no longer in your collection makes a new item. **A reply adds to what it replies to**, in the panel, is on until you untick it; off, a reply is an item of its own. To follow a reply, the studio keeps which of your messages, and which of the bot's answers, each item came from (their numbers in your chat with the bot), from this version on: a message sent before it cannot be replied to this way.

### Edits follow

Edit a message you sent your bot (press and hold it, then **Edit**) and the item it made changes with it, in **Your collection** at once, read as the message was: an `Idea:` or `/idea` is still an idea, without the prefix, and a post link in it does not make a second request on Today. The bot answers "Updated in your collection." The item then says "edited on your phone". Edit a reply that added to an item, and only its words change.

Once you have used the item, the draft made from it is kept as it is: the item takes your edit, says it was edited after it became a draft, and the bot answers "Updated in your collection. The draft made from it was not changed." An edit of a message that made nothing, such as a command, changes nothing, and the bot says so. An edit from any chat but yours is refused like a message from it. To follow an edit, the studio uses the same record of which message each item came from as for replies, so a message sent before this version does not follow its edits.

## Make something out of it

In the studio, on an item of **Your collection**:

- **Make a post** writes a draft from it through your own AI provider and opens it in the Composer. The item is then used.
- The **Angles** button, which says how many it offers (**3 angles** unless you change it), finds that many opening lines for a post from it, and lists them under the item, each with **Write it up**.
- Tick two or more items, up to your **Most items in one draft** (ten unless you change it under **Brand**, then **Writing**), and **Combine** writes one draft from all of them.

On your bot, under "Saved to your collection.", **Write it up** and the **Angles** button do the same. The bot answers at once ("Writing it up in your studio.") and keeps answering everything else while your provider writes; when it is done it sends a new message, which your phone notifies.

What is sent to your provider, and nothing else: the words of the items you pressed it on, what the studio knows about how you write (as for Re-Hook and Command), your writing preferences, and your [things to remember](#things-to-remember), as you chose. Every choice it makes is yours: how long a draft is, its tone, its language, its opening line, emojis, hashtags, line breaks, how it ends, words it never writes, and how many angles. Each has a default you can see, under **Brand**, then **Writing**, and each feature shows the ones it reads beside it. See [Set up your Brand and your Settings](set-up-brand-studio.md#brand-writing).

What is kept is only what you sent: a draft or an angle that carries a figure, or the name of a person the studio knows of, that is not in your words or your things to remember is refused and said, never repaired, and nothing is kept. A draft written from your collection says, above it in the Composer under **What this draft was written from**, which provider wrote it and when, from how many items, and which of your things to remember went with it. With no AI provider set up, each says so plainly, and **Use as a draft** gives you the item's words as they are.

**The bot may send me what it writes from my collection**, in the panel, is off until you tick it. Off, the bot says only "Draft ready in your studio." or that the angles are ready in your studio. On, its message carries what was written: a draft's first line, or the angles, each with a **Write up** button. Those words of yours then sit on Telegram's servers, as everything in the chat does.

### Post from your phone

With that switch on, "Draft ready in your studio. It begins:" carries **Send me the whole post**, and so does "A post in your queue is due now." and its reminder (**Send me the posts** when several are due). Press it and the bot sends the post as your studio holds it now, changes you made at the desk included, as a message of its own with nothing else in it: press and hold it, choose **Copy**, and paste it into the LinkedIn app. Nothing is posted for you, and nothing reaches LinkedIn from the studio. The message keeps its other buttons. A post longer than one Telegram message (4,096 characters, more than LinkedIn takes in one post) comes in parts, cut between paragraphs, each beginning "Part 1 of 2": copy each without that line. With the switch off the button is not there, and pressing it on an older message says why and sends nothing.

| What happened | The bot says |
| --- | --- |
| You pressed **Write it up** | Writing it up in your studio. |
| The draft is written, with the switch off | Draft ready in your studio. |
| The draft is written, with the switch on | Draft ready in your studio. It begins: (and its first line) |
| You pressed the **Angles** button | Finding angles in your studio. |
| The angles are found, with the switch off | 3 angles are ready in your studio, on the item in your collection. |
| The angles are found, with the switch on | Angles from your collection. Press one to write it up: (and the angles, each with **Write up**) |
| No AI provider is set up | No AI provider is set up in your studio, so nothing was written. Connect yours on the Composer's Prompt tab, or use it as a draft in your collection. |
| Your provider did not write it | Your AI provider did not write it, so nothing changed. Open your studio to see why. |
| What it wrote named a figure or a person not in your note | Nothing was kept: what your AI provider wrote had a figure or a name that is not in your note. |

### Rewrite a draft from your phone

With **The bot may send me what it writes from my collection** on, a draft the bot wrote carries your rewrite buttons too: **Shorter**, **New opening** and **Another angle** unless you change them under **Brand**, then **Writing** (see [Rewrite buttons on your bot](set-up-brand-studio.md#brand-writing)). Press one and the bot answers "Rewriting it in your studio."; it keeps answering everything else while your provider writes. What is sent to your provider: the draft as it is now, the items it was written from, your things to remember as you chose, your writing preferences, and what that button asks for, nothing else. A rewrite that brings in a figure or a person not in what was sent is refused and said, never repaired.

The draft in your studio then changes in place, if it is still a draft and nobody changed it while it was rewritten; a draft queued or published is left as it is. The Composer keeps no versions, so the text a rewrite replaced is kept on the draft: in the Composer, **What this draft was written from** lists each one under "Rewritten from your phone", newest first, the ten newest, with **Put it back in the editor**; save it to keep it. A Composer open on the draft with nothing unsaved shows the new text at once; with unsaved changes, saving says the draft changed elsewhere, and **Keep this version** keeps yours.

| What happened | The bot says |
| --- | --- |
| You pressed a rewrite button | Rewriting it in your studio. |
| It is rewritten | Rewritten in your studio (Shorter). It begins: (and its new first line), with **Send me the whole post**, your rewrite buttons and **Undo** |
| **Undo** under it | Undone: the draft is back as it was before the rewrite. |
| The draft changed in your studio while it was rewritten | Not rewritten: the draft has changed in your studio since, so it was kept as it is. |
| It is queued or published | Not rewritten: that post is queued or published, so it was kept as it is. |
| It was deleted in your studio | Nothing was rewritten: that draft is no longer in your studio. |
| You removed that button in Brand since | That rewrite is no longer one of yours in Brand, under Writing, so nothing was done. |
| You turned the words switch off since | Nothing was rewritten: your studio no longer sends your words here. Turn on The bot may send me what it writes from my collection under Local security. |

No AI provider set up, a provider that fails, and a rewrite that is refused are said as for **Write it up**, and nothing changes.

## A morning idea

Tick **Send me an idea from my collection each morning** in the panel, and pick the days (Monday to Friday unless you change them) and the hour (08:00). On those mornings the bot sends one unused item from your collection, the one it offered least recently, under "An idea from your collection:", with an angle from what worked in your own posts, for example "Angle: open with a question, as the posts of yours that did best did.", and **Write it up** and **Not today** under it. **Not today** leaves it in your collection ("Not today. It stays in your collection.").

It carries your words, so it comes only while **The bot may send me what it writes from my collection** is on, and it waits through quiet hours like every notification. **Ideas draw on**, beside it, says whether the idea comes from your collection and whether its angle comes from your posts. A day with nothing new to offer sends nothing.

## Things to remember

Tell the studio facts about you that every writing request should know: about you, your audience, an offer, or a date. Send `/remember` and a sentence, for example `/remember I write for founders of small design studios`. Start it with `audience:`, `offer:` or `date:` to say what it is about, as in `/remember offer: a workshop for small studios`; without one, it is about you. The bot answers "Kept in your things to remember.", with **Undo** under it.

Or keep a note you sent as one: under "Saved to your collection.", a note or an idea of at most 300 characters carries **Remember this**. Press it and its words are kept as a thing to remember, about you, or about what a prefix such as `offer:` at its start says, as `/remember` reads it. The message then says "Kept in your things to remember. In your collection it is set as used.", with **Undo**, and **Your collection** lists the item as used, "Kept in your things to remember". **Undo** removes the thing to remember and puts the item back with the new ones. A forward, a link and a file never carry it: a forward's words are someone else's.

`/forget` and words from one of them removes it: "Forgotten: one thing you asked me to remember." If the words match several, nothing is removed and the bot says how many, so you can say more of it, or remove it in your studio. It never guesses.

In the studio they are listed under **Brand**, then **Writing**, under **Things to remember**, where you can add, edit, tick, untick and remove them, and choose which go with writing: all of them (the default), only the ones ticked, or none. See [Set up your Brand and your Settings](set-up-brand-studio.md#things-to-remember).

`/recall` and a word answers with how many items in your collection hold it, for example "2 items in your collection hold that word.", and only with **The bot may send me what it writes from my collection** on, their first lines, up to five.

## Commands

Send a command as a message on its own, as Telegram's menu does. Letter case does not matter, and `/help@YourBot` is read as `/help`.

The commands are in Telegram's **/** menu of your chat too: type `/` in the chat with your bot and pick one, with what it does beside it, in the words `/help` uses. The studio registers that menu with Telegram for your paired chat only, once it reaches Telegram after you pair, and again only when a new version changes the commands. Pairing another chat takes the menu from the chat before, and **Remove the bot** takes it away, if Telegram can be reached then.

| You send | What happens |
| --- | --- |
| `/start` or `/help` | The bot says what it does, its commands as the **/** menu lists them, what **Undo** does, how to pair a chat, and that it sends your words and figures only if you allow them, and nothing about anyone else |
| `/idea your idea` | Your idea is kept in your collection as an idea, as `Idea: your idea` is. A link inside it stays part of the idea |
| `/ask what to remember` | It is remembered as an ask in **From your record**, with the source Telegram, and listed under **What the studio knows** there, where you can change or remove it. It takes effect on tomorrow's cards. It is not kept in your collection |
| `/status` | Whether your studio is running, whether the bridge in your browser is connected, and when the studio last checked Telegram before your message, for example "Before this message, it last checked Telegram for your messages 2 days ago (Thu 29 Oct, 18:02 on your computer's clock)." No figures |
| `/today` | Your latest post's figures, how many replies are waiting and when your next post is scheduled, only if you turned on **The bot may answer with your figures**. Otherwise it says your figures stay in the studio |
| `/drafts` | How many drafts were made from what you sent in the last seven days: "Drafts made from what you sent, in the last seven days: 5." A `Draft:` message, or an item you used as a draft. A count, never their words |
| `/remember something` | It is kept in your things to remember, with **Undo** under the answer. See [Things to remember](#things-to-remember) |
| `/forget words` | The one thing to remember that holds those words is removed; with several, nothing is, and the bot says how many |
| `/recall word` | How many items in your collection hold the word, as a word or a tag, and their first lines only with **The bot may send me what it writes from my collection** on. `/recall #tag` counts the items that carry the tag |
| `/write word` or `/write #tag` | One draft from the unused items in your collection that hold the word, or carry the tag, newest first, up to your **Most items in one draft**, through your own AI provider as **Combine** writes: "Writing one post from 3 items in your collection.", then "Draft ready in your studio." Those items are then used. Nothing matching: "Nothing new in your collection holds that word, so nothing was written." |
| Any other command | "I do not know that command. Send /help to see what I do." |

`/start`, `/help`, `/status`, `/today`, `/drafts`, `/forget`, `/recall` and `/write` are answered even when **The bot confirms each message** is off, because you asked a question. A command from a chat that is not paired is refused like any other message.

## Your figures on Telegram, only if you allow it

**The bot may answer with your figures** is off until you tick it in the panel. With it on, `/today` answers, for example:

> Your latest post, published 2 days ago: 1,234 impressions, 56 reactions, 7 comments, read on its analytics page 3 hours ago. Replies waiting: 2. Next scheduled post: Thu 30 Oct, 09:00 (your computer's time).

Each figure says where it was read and how long ago; a figure nobody read is left out, never shown as 0. Replies are a count. It never carries a person's name, a comment, or the words of your posts. Once sent, those figures sit on Telegram's servers, as everything in the chat does. Untick the switch and `/today` says your figures stay in the studio.

## Notifications, each only if you tick it

Three, each with its own switch in the panel, all off until you tick them:

| Switch | What the bot sends |
| --- | --- |
| **Tell me when a queued post is due** | "A post in your queue is due now. Open your studio to post it." When several are due at once, how many. Never the post's words. With **Remind me in an hour** and **Done** under it |
| **Send my latest post's figures at about 24 hours** | Once, when the studio has read your latest post at about a day old (between 20 and 30 hours) while it is under two days old: "Your latest post at about 24 hours: 880 impressions, 31 reactions, 4 comments, read on its analytics page." |
| **Send me a weekly summary** | Once a week, on the day and at the hour you pick beside it (Monday at 09:00 on this computer's clock unless you change them), one message about the seven days to that moment. See [The weekly summary](#the-weekly-summary) |

Each is sent once to your paired chat: the studio keeps what it has told, so a restart does not send it again. The studio looks for something to tell about once a minute while it is asking Telegram for messages. The figures then sit on Telegram's servers, as everything in the chat does; never a person's name or a comment. During quiet hours they wait: see below.

## The weekly summary

Tick **Send me a weekly summary** and pick a day and a whole hour beside **On** and **at**. The panel then says when the next one goes, for example "NEXT SUMMARY: MON 02 NOV, 09:00". The first comes at the first such moment after you tick it or change the day or hour, never at once. The summary reads, line by line:

| Line | What it is |
| --- | --- |
| Your week, the seven days to Mon 02 Nov, 09:00 on your computer's clock: | The seven days it covers, ending at the moment you picked |
| Posts published, as your studio recorded them: 3 | Your posts the studio holds as published in those days. A post the studio has not read yet is not counted |
| Drafts made from what you sent: 5 | Drafts made in those days from what you sent your bot: a `Draft:` message, or an item you used as a draft, even one you changed or deleted in the studio since. One you took back with **Undo** is not counted |
| Replies waiting: 2 | Comments on your posts waiting for your reply, as Today counts them. A count, never who or what |
| Next scheduled post: Thu 05 Nov, 09:00 (your computer's time). | Or "No post is scheduled." |

Only if **The bot may answer with your figures** is on, it goes on with "Your figures, each as last read:" and a line for each post of the week, newest first, named by its day: for example "- Published Fri 30 Oct: 1,234 impressions, 56 reactions, 7 comments, read on its analytics page 3 hours ago", or "no figures read yet". A figure nobody read is left out, never shown as 0. Up to seven posts are listed; any more are counted in a last line.

It never carries a person's name or a comment, nor the words of your posts or drafts. Each week's summary is sent once: the studio keeps that it was told, so a restart does not send it again, and deleting everything forgets that too. If the studio is not running at that moment, it goes when the studio next runs that week, up to the end of Sunday. During [quiet hours](#quiet-hours) it waits like every notification.

## Quiet hours

The notifications wait during quiet hours and go when they end, each still sent once: a post that came due at 02:00 is told at 07:00, if it is still due then, and three that came due in the night are told in one message. A reminder you asked for with **Remind me in an hour**, and the weekly summary, wait the same way.

**Hold notifications during quiet hours** is ticked, from 23:00 to 07:00 on this computer's clock, until you change it in the panel: pick whole hours beside **From** and **to**, or untick it to have notifications at any hour. While it is quiet, the panel says "QUIET NOW: NOTIFICATIONS WAIT UNTIL 07:00". A start and an end on the same hour are refused with a sentence, and nothing is saved.

Answers to your own messages, your commands and your presses of a button are never held: the bot answers them at any hour.

Quiet hours are not the studio's slower checking at night. Between 23:00 and 06:00 the studio asks Telegram less often, whatever quiet hours say, so an answer at night can take up to two minutes (see [What happens to text](#what-happens-to-text)). Quiet hours never change how often the studio asks, and the slower checking never holds a notification back.

## Buttons you can press

These messages carry buttons, which you press in Telegram:

| Under | Button | What it does |
| --- | --- | --- |
| "Saved to your collection." | **Write it up** | Writes a draft from it through your own AI provider. See [Make something out of it](#make-something-out-of-it) |
| The same | The **Angles** button | Finds your number of opening lines for a post from it |
| The same | **Undo** | Takes it out of your collection, while it is still new there: never used as a draft and never set aside |
| The same, for a note or an idea of at most 300 characters | **Remember this** | Keeps its words as a thing to remember, and the item is used. See [Things to remember](#things-to-remember) |
| "Kept in your things to remember. In your collection it is set as used." | **Undo** | Removes that thing to remember, and the item is new again: "Undone: it is no longer kept, and it is new in your collection again." |
| "An idea from your collection:" | **Write it up** and **Not today** | See [A morning idea](#a-morning-idea) |
| "Kept in your things to remember." | **Undo** | Removes it from your things to remember: "Undone: it is no longer kept." |
| "Added to the item in your collection." | **Undo** | Takes those words back off the item, while you have not used it since: "Undone: those words are taken back off the item." Otherwise "Not undone: you have used the item in your studio since, so the words stay on it." |
| "Saved as a draft in your studio." | **Undo** | Removes that draft from your studio, and its line in your collection, while it is untouched there: still a draft, with the words, tags and media the bot saved, never queued or published. A draft you changed is kept |
| "A post in your queue is due now." | **Remind me in an hour** | The bot tells you again in an hour, if the post is still due then, with the same two buttons |
| The same | **Done** | Clears the reminder, and that is all: nothing is marked as posted, and nothing is done on LinkedIn. The post stays due in your studio until you post it |
| "Draft ready in your studio. It begins:" and "Rewritten in your studio (...). It begins:" | Your rewrite buttons (**Shorter**, **New opening**, **Another angle** unless you change them) | Rewrites the draft through your own AI provider. See [Rewrite a draft from your phone](#rewrite-a-draft-from-your-phone) |
| "Rewritten in your studio (...). It begins:" | **Undo** | Puts the draft back as it was before that rewrite, while it is still as the rewrite left it |
| The same, and "Draft ready in your studio. It begins:", with **The bot may send me what it writes from my collection** on | **Send me the whole post**, or **Send me the posts** when several are due | Sends each post as a message of its own, to copy into the LinkedIn app. See [Post from your phone](#post-from-your-phone). The message keeps its other buttons |

After a press your phone shows a short notice, the message says under its first words what became of it, and its buttons go:

| What happened | The bot says |
| --- | --- |
| **Undo** took it out of your collection | Undone: it is removed from your collection. |
| **Undo** found you had used it, or set it aside | Not undone: you have used it in your studio since, so it was kept. |
| **Undo** found it already removed | Nothing to undo: it is no longer in your collection. |
| **Undo** removed the draft | Undone: the draft is removed from your studio. |
| **Undo** found the draft changed in your studio | Not undone: the draft has changed in your studio since, so it was kept. |
| **Undo** found the draft already deleted in your studio | Nothing to undo: the draft is no longer in your studio. |
| **Remind me in an hour** | I will remind you in an hour if it is still due. |
| An hour later, still due | Reminder: a post in your queue is still due. Open your studio to post it. |
| **Done** | Reminder cleared. Nothing was marked as posted: it stays due in your studio until you post it. |
| **Send me the whole post** | Sent below as a message of its own: press and hold it, then Copy, and paste it into LinkedIn. |
| **Send me the posts** | Sent below, each post a message of its own: press and hold one, then Copy, and paste it into LinkedIn. |
| Either, after you turned the switch off | Nothing was sent: your studio no longer sends your words here. Turn on The bot may send me what it writes from my collection under Local security. |
| Either, for a post deleted in the studio since | Nothing was sent: that post is no longer in your studio. |
| A button pressed a second time | That button was already used, so nothing more was done. |
| A button the studio no longer knows, such as one from long ago, or from before you deleted everything | That button is old, so nothing was done. |
| A press your studio could not carry out, after three tries | Your studio could not do that. Open the studio to see why. |

Each button works once, and only in your paired chat: a press from any other chat is refused as a message from it would be, and listed under **CHATS THE BOT REFUSED** as "a button press". A button carries an id that names nothing, never your words or a draft's. What each button does is kept in your studio for the newest 100 messages that carry buttons, and deleted with everything else when you delete everything. A press is answered even when **The bot confirms each message** is off, because you pressed it. Untick **Tell me when a queued post is due** and no reminder comes either.

## What the bot says back

Each message gets one short sentence back, the same words every time. None carries your words, your figures or anything about anyone else:

| What became of your message | The bot says |
| --- | --- |
| Kept in your collection | Saved to your collection. (With **Undo** under it.) |
| A link to one of your posts | Saved to your collection. Today will ask you to open this post's analytics at your computer. |
| A short `lnkd.in` link | Saved to your collection. Today will ask you to open this link at your computer. |
| A link to a post that is not yours | Saved to your collection as a bookmark. Your studio never opens other people's posts. |
| A `Draft:` message | Saved as a draft in your studio. (With **Undo** under it.) |
| A photo, an album, a voice note, a document or a video | Saved to your collection. (With **Undo** under it, and **Write it up** and the angles when it has a caption. An album is answered once.) |
| A photo, a voice note, a document or a video over 20 MB | That file is larger than your studio keeps from the phone (20 MB), so nothing was saved. |
| A file Telegram would not hand over | Telegram did not hand that file over, so nothing was saved. Send it again. |
| A sticker, a location, a contact or anything else with no text | That message had no text, so nothing was saved. |
| A message your studio could not save, after three tries | Your studio could not save that message. Open the studio to see why. |
| The studio checked again more than a day after its last check | Your studio did not check Telegram for your messages from ... until ..., on your computer's clock. Telegram keeps a bot's messages for one day, so anything you sent before ... may not have arrived. Send again whatever is missing from Your collection. |
| You pressed **This is me**, or saved a chat id | Paired. Messages from this chat now arrive in your studio. Send /help to see what I do. |
| A message before any chat is paired | Not paired yet. In your studio, open Settings, then Local security, and press This is me beside chat 487215963. (Your own chat's number.) |
| A message from a chat that is not the paired one | This bot takes messages only from the chat its owner paired. |
| `/ask` | Remembered. Your studio uses it when it picks what to write about, from tomorrow's cards. |
| `/remember` | Kept in your things to remember. Your studio's writing reads it, as you chose in Brand, under Writing. (With **Undo** under it.) |
| **Remember this**, with words already kept | That is already in your things to remember, so nothing more was kept. |
| **Remember this**, on a note you used since | Not kept: you have used it in your studio since, so nothing was done. |
| A reply that added to an item | Added to the item in your collection. (With **Undo** under it; with the words switch on, "Added to the item in your collection that begins:" and its first line.) |
| A reply that added to an item that became a draft | Added to the item in your collection. The draft made from it was not changed. |
| You edited a message on your phone | Updated in your collection. |
| You edited a message whose item became a draft | Updated in your collection. The draft made from it was not changed. |
| You edited a message that made nothing in your collection | That edit changed nothing in your studio: the message it edits made nothing in your collection. |
| `/remember` with more than 300 characters | A thing to remember is at most 300 characters. Send it shorter, or as two. |
| `/forget`, with one match | Forgotten: one thing you asked me to remember. |
| `/forget`, with several matches | 2 things to remember hold those words. Say more of it, or remove it in your studio. |
| `/forget`, with none | Nothing you asked me to remember holds those words. |
| `/recall` | 2 items in your collection hold that word. (Or "One item in your collection holds that word.", or "Nothing in your collection holds that word.") |
| `/idea`, `/ask`, `/remember`, `/forget`, `/recall` or `/write` with nothing after it | How to send one, with an example |
| `/write` | Writing one post from 3 items in your collection. (Or "Writing one post from one item in your collection.") Then, as for **Write it up**, "Draft ready in your studio." |
| `/write`, with nothing new that matches | Nothing new in your collection holds that word, so nothing was written. |

A chat that is refused is answered at most once in ten minutes. The answers are on by default; to stop them, untick **The bot confirms each message** in the panel. Your messages are still saved. If a sentence cannot be sent, the panel says why under **Last message the bot could not send**, and the studio tries again after a network fault or when Telegram asks it to wait.

## What happens to a post link

The link names the post by the number in it, which is the same for the app's share-menu form and the feed's. The studio reads only your own posts, so what happens depends on whose post it is.

- **One of your recorded posts:** **Today** says "You asked from your phone to read this post's analytics" under **ONE THING TO OPEN**, oldest request first, with **Open it in the bridge browser**. When your latest post is in its first three days and its figures are due to be read, that comes first, and your request right after it. **Not now** beside it closes the request. Otherwise it is done once that post's analytics page has been read after you asked, and closed with a note after a week unread. See [What to do today](what-to-do-today.md).
- **Anything else**, such as someone else's post, or a post of yours the studio has not read yet: a post that is not yours is never read. The link is listed under **LINKS FROM YOUR PHONE** in the panel with "Not one of your posts", and never appears on Today. If it is yours and new, run **Posts you wrote** in Setup's step 5, then share the link again.

The panel's **Posts asked for from the phone, waiting** line counts the open requests, and **LINKS FROM YOUR PHONE** lists the newest links with what became of each.

## What happens to a short link

The LinkedIn app's **Copy link** gives a short link, such as `https://lnkd.in/p/AbC123`, with no post number in it. The studio never fetches it, and never contacts lnkd.in or LinkedIn to find out where it goes: your own browser does, when you open it.

1. **Today** says "You sent a post from your phone" under **ONE THING TO OPEN**, with **Open it in the bridge browser**, **Done** and **Not now**.
2. **Open it in the bridge browser** opens the short link in your browser with `#inox-desk-` and the request's number on the end. A browser keeps that ending when the short link sends it on to the post, so the extension, on the post's page, tells the studio which post it was.
3. If it is one of your posts, **Today** then asks you to open that post's analytics, as for any post link, and the request is done once that page has been read. If it is someone else's post, the request is closed as not one of your posts.
4. If LinkedIn's page drops that ending before the extension can read it, nothing is reported, and the studio does not guess: press **Done** on Today once you have seen the post. **Not now** closes it either way, and it is closed with a note after a week.

In the panel, a short link is listed by its address until its post is known.

## What happens to text

Each message lands in your collection, not in the Composer: open **From your record**, then **Your collection**, where it appears as soon as it arrives. Nothing is written from it until you press **Use as a draft**. A message starting `Draft:` is saved as a draft as before: open **Drafts** in the Composer, or press Ctrl+K and look under **Posts**. See [Search everything with Ctrl+K](use-the-command-palette.md) and [Start a new post, or find one you wrote earlier](start-a-new-post-or-find-an-earlier-one.md).

Each check asks Telegram to wait up to 30 seconds for a new message, so a message sent during a check arrives straight away. Between checks the studio pauses about 2 seconds, 120 seconds between 23:00 and 06:00 local time, and up to 60 seconds after errors. When Telegram asks it to slow down, it waits as long as Telegram says. This night-time pause is fixed, and separate from [quiet hours](#quiet-hours), which hold only notifications.

## A day the studio did not check

Telegram keeps the messages you send your bot until the studio asks for them, but for one day at most. So the studio keeps the time of its last successful check, and when it checks again more than a day later (the computer was off, asleep or offline), it tells you once:

> Your studio did not check Telegram for your messages from Thu 29 Oct, 18:02 until Sat 31 Oct, 09:15, on your computer's clock. Telegram keeps a bot's messages for one day, so anything you sent before Fri 30 Oct, 09:15 may not have arrived. Send again whatever is missing from Your collection.

The panel shows it at once, under **A DAY THE STUDIO DID NOT CHECK TELEGRAM**, until you press **Got it**. The bot sends it once, after quiet hours if it is quiet then, whatever the notification switches say. It never says a message was lost, and never gives a number: the studio cannot know what Telegram did not keep. Anything you sent within the day before that check arrives as usual. A new bot token starts afresh, and removing the bot forgets the time and the notice.

## Check it is running

The panel under **Your phone, through Telegram** reads:

- **Asking Telegram for messages**: YES while the studio is polling.
- **Messages saved since the studio started**: how many messages were saved since startup.
- **Posts asked for from the phone, waiting**: open requests.
- **Last checked Telegram**: when Telegram last answered the studio's check for messages, kept when the studio stops. NOT YET before the first.
- **The / menu in your chat**: SET once Telegram took the bot's commands for your paired chat.
- **Last problem reaching Telegram**: the most recent problem, in plain words, such as Telegram not recognising the token, another program asking for the same bot's messages, or no connection. It is cleared after each successful check. After a problem the studio waits longer before asking again, and as long as Telegram asks when it says to slow down.
- **Last message the bot could not send**: why the bot's last answer did not go, in plain words.

**Send a test message** sends one fixed sentence to your paired chat at once: "This is a test message from your Inox Hydra studio. If you can read it, the bot can reach you." The panel then says whether Telegram took it, or why not. Telegram taking it means your chat received it; whether your phone showed it, only your phone can say.

For a five-minute check of the whole path on your real bot, follow [Test your Telegram bot](test-your-telegram-bot.md).

## Turn it off

Click **Remove the bot** in the panel. The token and chat id are removed from this profile and the studio stops asking Telegram. To block the connection without removing them, set `INOX_ALLOW_INGRESS_EGRESS=0` before you start the studio; `INOX_NO_EGRESS=1` refuses it along with every other outbound category. In both cases each attempt is counted as refused in the ledger.

## If it does not work

| You see | What to do |
| --- | --- |
| **Save and start** stays disabled | Paste the bot token: it is the one value needed to start |
| No chat appears under **CHATS THE BOT REFUSED** after you message the bot | Check **Asking Telegram for messages** reads YES, and that you messaged the bot whose token you saved. The list is kept in memory, so it starts empty each time the studio starts |
| A sentence under the buttons says the token or chat id is not the right shape | Paste the token exactly as BotFather gave it, and the chat id as digits only |
| **Asking Telegram for messages** reads NO after saving | Reload the page. If it stays NO, see [The studio will not open or shows an error](the-studio-will-not-open.md) |
| Nothing arrives, no error | Press **Send a test message**. If it says Telegram took it and your phone shows nothing, check you are looking at the chat with your own bot |
| **Last problem reaching Telegram** says Telegram does not recognise the token | Paste the token BotFather gave you again, and save |
| **Last problem reaching Telegram** says another program is asking for this bot's messages | Only one program can ask at a time: close the other studio, or remove the webhook the bot was given elsewhere |
| A post link arrived but Today does not offer it | The panel lists it as not one of your posts: the studio holds no post of yours with that link. If it is yours and new, run **Posts you wrote** in Setup's step 5, then share it again |
| Today still says "You sent a post from your phone" after you opened it | The post's page did not keep the link's ending, so the extension could not say which post it was. Press **Done** once you have seen it |
| Arrivals are slow | Night-time polling, error backoff, or a Telegram rate limit, which the studio waits out |
| A message sent while the studio was off is missing | Telegram keeps a bot's messages for one day, so one sent more than a day before the studio next checked may never arrive. The panel and the bot say when that may have happened: send it again |
| A message you sent is not in your collection | Check you are in the profile the bot was set up in, which the panel names when another profile is open. A `Draft:` message is in the Composer's **Drafts**, and listed in your collection under **Used** |
