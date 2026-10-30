# Test your Telegram bot

A five-minute check of the whole path on your real bot and your own phone. Each step says what you should see. If a step does not match, the table at the end says where to look.

Before you start: the studio is running on this computer, and you have your bot's token from BotFather. See [Send a post idea or a post link from your phone with Telegram](send-a-post-idea-from-telegram.md) for what each part does.

## 1. Save the bot (one minute)

1. Open **Settings**, then **Local security**. Under **Your phone, through Telegram**, paste the token into **Bot token**, leave **Your numeric chat id** empty, and click **Save and start**.
2. You should see **SET, SEALED** beside the token, **YES** beside **Asking Telegram for messages**, and **NOT SET YET, PAIR BELOW** beside **Your chat id**.

## 2. Pair your phone (one minute)

1. In Telegram on your phone, open the chat with your bot and send `hello`.
2. On the phone, the bot answers: "Not paired yet. In your studio, open Settings, then Local security, and press This is me beside chat ..." with your chat's number.
3. In the panel, within a few seconds: "1 message refused from chat ..., first: 'hello'. Is that you?" Check the number is the one the bot just sent you, then press **This is me**.
4. On the phone: "Paired. Messages from this chat now arrive in your studio. Send /help to see what I do."

## 3. The bot answers (two minutes)

1. Send `/help`. The bot says what it does, how to pair, and what it sends only if you allow it.
2. Send `Idea: testing the bot`. The bot answers "Saved to your collection." In the studio, open **From your record**, then **Your collection**: it is there, without a reload. (A message starting `Draft:` still goes straight to a draft: "Saved as a draft in your studio.")
3. Send `/status`. The bot answers "Your studio is running." and whether the bridge in your browser is connected.
4. In the LinkedIn app, open one of your own posts, use **Copy link**, and send the link to the bot. The bot answers "Today will ask you to open this link at your computer.", and **Today** shows "You sent a post from your phone". Press **Not now** there if you do not want to open it.
5. Send `Idea: undo me`, then press **Undo** under the answer. The message changes to end "Undone: it is removed from your collection.", its button goes, and **Your collection** no longer lists `undo me`.

## 4. The panel's own check (thirty seconds)

1. Press **Send a test message**. The panel says "Sent: Telegram took it for your chat. Check your phone.", and your phone shows "This is a test message from your Inox Hydra studio."

## 5. Your figures, only if you want them (thirty seconds, optional)

1. Send `/today`. The bot answers that your figures stay in your studio: they are off until you allow them.
2. To see them on the phone, tick **The bot may answer with your figures** and send `/today` again: your latest post's figures with where and when each was read, how many replies are waiting, and when your next post is scheduled. Untick it again if you do not want your figures to sit on Telegram's servers.

## Later: the buttons under a due post, quiet hours and the weekly summary (optional)

These need a post to come due, or an hour to come round, so they take as long as that.

1. Tick **Tell me when a queued post is due** in the panel, and schedule a post in the **Queue** for a few minutes from now.
2. When it comes due, the bot says "A post in your queue is due now. Open your studio to post it.", with **Remind me in an hour** and **Done** under it.
3. Press **Remind me in an hour**: the message changes to end "I will remind you in an hour if it is still due." An hour later, if you have not posted it, the bot says "Reminder: a post in your queue is still due. Open your studio to post it."
4. Press **Done** under the reminder: the message ends "Reminder cleared. Nothing was marked as posted: it stays due in your studio until you post it." In the studio the post is still due: Done changed nothing there.
5. Quiet hours: set **Hold notifications during quiet hours** to run from this hour to the next, and schedule another post a few minutes ahead. When it comes due no message comes, and the panel says "QUIET NOW". Untick **Hold notifications during quiet hours**: within about a minute the bot says the post is due. Set quiet hours back as you like them.
6. The weekly summary: tick **Send me a weekly summary** and pick today and the next whole hour. The panel says "NEXT SUMMARY:" with that time. At that hour the bot sends "Your week, the seven days to ..." with your counts and your next scheduled post, and your figures only if **The bot may answer with your figures** is on. Pick the day and hour you want afterwards.
7. Writing from your collection, with an AI provider connected on the Composer's **Prompt** tab: send `Idea: pricing is a design decision`, then press **Write it up**. The bot answers "Writing it up in your studio.", and a moment later sends "Draft ready in your studio."; the draft is in the Composer. Press the **Angles** button under another idea: "3 angles are ready in your studio, on the item in your collection." Tick **The bot may send me what it writes from my collection** and try again: the angles come to your phone, each with **Write up**.
8. The morning idea: tick **Send me an idea from my collection each morning** (with the switch above on) and pick today and the next hour. At that hour the bot sends "An idea from your collection:" with one of your ideas and an angle, and **Write it up** and **Not today**.
9. Send `/drafts`. The bot answers with how many drafts were made from what you sent in the last seven days, for example "Drafts made from what you sent, in the last seven days: 2.", a count and never their words.
10. Things to remember: send `/remember offer: a workshop for small studios`. The bot answers "Kept in your things to remember.", with **Undo** under it, and **Brand**, then **Writing**, lists it under **Things to remember** without a reload. Press **Write it up** under an idea again: the new draft says, above it in the Composer under **What this draft was written from**, that "a workshop for small studios" went with it. Send `/forget workshop`: "Forgotten: one thing you asked me to remember.", and the list in Brand empties.
11. Send `/recall pricing`. The bot says how many items in your collection hold the word; their first lines come too only while **The bot may send me what it writes from my collection** is on.
12. In the Composer, start a new post that mentions pricing and open **From your collection** above the editor: your unused idea about pricing is there. Press **Add to the draft**, save, and **Your collection** lists it as used, with the draft as what it became.
13. Photos and voice notes: send a photo with a caption. The bot answers "Saved to your collection.", and **Your collection** shows the photo with your caption under it and "KEPT AS IT IS: NEVER READ". Press **Add to your media library**: the item says "In your media library", and the Composer's **Media** tab lists the photo. Send a voice note: it is listed with a player, and plays at this computer; it is never transcribed.

## Phase 4 on your phone (optional)

1. Seen working: open **Settings**, then **Local security**. If your bot has saved anything from your chat before, even before this version, the orange "Not yet seen working on this computer" sentence is gone.
2. The last check: the panel shows **Last checked Telegram** with a time a few seconds old. Send `/status`: the bot adds when the studio last checked before your message.
3. A day off (only when it happens): if the computer is off for more than a day, at the next start the bot says "Your studio did not check Telegram for your messages from ...", and the panel shows **A DAY THE STUDIO DID NOT CHECK TELEGRAM** until you press **Got it**. Check **Your collection** and send again whatever is missing.
4. The / menu: in the chat with your bot, type `/`. The menu lists the bot's commands, each with what it does, as `/help` says them, and the panel says SET beside **The / menu in your chat**.
5. Post from your phone: with **The bot may send me what it writes from my collection** ticked, press **Write it up** under an idea, then **Send me the whole post** under "Draft ready in your studio. It begins:". The bot answers "Sent below as a message of its own: press and hold it, then Copy, and paste it into LinkedIn." and the post arrives alone. Press and hold it, choose **Copy**, and paste it into a new post in the LinkedIn app: it is the whole draft, exactly as the studio holds it. A due post's message carries the same button (**Send me the posts** when several are due).
6. Rewrite from your phone: under the same "Draft ready" message, press **Shorter**. The bot answers "Rewriting it in your studio.", then "Rewritten in your studio (Shorter). It begins:" with the new first line. In the Composer, the draft is the shorter one, and **What this draft was written from** lists the earlier text under "Rewritten from your phone" with **Put it back in the editor**. Press **Undo** under the bot's message to have the earlier text back. Change the buttons under **Brand**, then **Writing**, **Rewrite buttons on your bot**.
7. Build an idea up: send `pricing is a design decision`. Then press and hold it, choose **Reply**, and send `and the price page is the brief`. The bot answers "Added to the item in your collection." with **Undo**, and **Your collection** shows one item with both lines, "from 2 of your messages". Reply to the bot's answer the same way: the words go on the same item. Untick **A reply adds to what it replies to** in the panel to have replies kept as items of their own.
8. Edits follow: send `pricing is a desing decision`, then press and hold it, choose **Edit**, and correct it. The bot answers "Updated in your collection.", and **Your collection** shows the corrected words with "edited on your phone". Edit a `Draft:` message the same way: the bot answers "Updated in your collection. The draft made from it was not changed.", and the Composer still holds the draft as it was.
9. Remember this: send `I write for founders of small design studios` and press **Remember this** under the answer. The message ends "Kept in your things to remember. In your collection it is set as used.", with **Undo**. Under **Brand**, then **Writing**, **Things to remember** lists it; **Your collection** lists the note as used, "Kept in your things to remember". Press **Undo**: it is no longer kept, and the note is new again.
10. `/write`: with two unused notes that mention pricing in your collection, send `/write pricing`. The bot answers "Writing one post from 2 items in your collection.", then "Draft ready in your studio."; the Composer's draft is written from both, and **Your collection** lists them as used. `/write #pricing` takes the items tagged #pricing. **Most items in one draft**, under **Brand**, then **Writing**, is how many it takes at most.
11. Albums, documents and videos: select three photos in Telegram and send them together with one caption. The bot answers once, and **Your collection** shows one item with the three photos and your caption. Send a PDF: it is listed as a document under its own name, with **View** and **Download**, and **Add to your media library** puts it in the Composer's **Media** tab as a document carousel. Send a Word file: it is a download only, with no **View**. Send a short video: it plays in **Your collection**. A sticker still gets "That message had no text, so nothing was saved."

## When a step does not match

| You see | Look at |
| --- | --- |
| **Asking Telegram for messages** reads NO | **Last problem reaching Telegram** in the panel, in plain words. Telegram not recognising the token means the token was pasted wrong: paste it again and save |
| No answer to `hello`, and nothing under **CHATS THE BOT REFUSED** | That you messaged the bot whose token you saved, and that **Asking Telegram for messages** reads YES. Another program asking for the same bot is named under **Last problem reaching Telegram** |
| The panel lists your chat, but the phone got no answer | **Last message the bot could not send**: the bot may be blocked in your chat. Unblock it in Telegram and send it a message |
| The bot answers, but **Your collection** does not list it | Check you are in the profile the bot was set up in, which the panel names when another profile is open. A `Draft:` message is in the Composer's **Drafts** |
| **Send a test message** says Telegram took it, and the phone shows nothing | That you are looking at the chat with your own bot, and that Telegram's notifications are on for it |
| A button keeps spinning, and the message never changes | That **Asking Telegram for messages** reads YES. A press reaches the studio the way a message does; at night the studio asks Telegram less often, so an answer can take up to two minutes |
| **Undo** says the draft has changed | The draft was edited, queued or published in the studio after it arrived, so it was kept. Delete it in the studio if you do not want it |

If a step still does not match, note the panel's two problem lines; they carry no message text and no token, so they can be shared as they are.
