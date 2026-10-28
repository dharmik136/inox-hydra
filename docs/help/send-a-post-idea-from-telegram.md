# Send a post idea or a post link from your phone with Telegram

Make a Telegram bot of your own, set it up under Local security, and the messages you send it arrive in the studio: text as a draft, and a LinkedIn post link as the page Today asks you to open at this computer.

## What it is, and what it is not

- It is optional and off until you set it up. The studio asks Telegram for your bot's messages while it is running, and opens no port. Each request is counted under the `ingress` row of **What has left this machine** under **Local security** in **Settings**.
- The phone sends a link, never a figure. Nothing you send is written as a reading: a post link becomes a request to read that post here, where the extension reads the real page.
- The bot answers each message with one short fixed sentence, so you can tell it arrived. See [What the bot says back](#what-the-bot-says-back).
- Your message text passes through Telegram's servers. See [What leaves this machine, and when](what-leaves-this-machine.md).
- The bot belongs to the creator profile you set it up in, and its messages are saved there whichever profile is open. One bot is asked at a time: the one saved most recently, or when the studio starts, the first profile that has one. A profile whose bot is not the one being asked says so in its panel.

> [!NOTE]
> First tested against the real Telegram service on 2026-10-28, on the owner's computer: the studio asked Telegram for messages, refused a chat that was not the one saved, and saved a message once the right chat was paired. Until a message from your own chat has been saved on your computer, the panel says it has not been seen working there.

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

Send the bot a text message. You can start it with a prefix, in any letter case. Every saved draft is tagged `mobile-ingress`.

| You send | What the studio saves |
| --- | --- |
| Plain text | The text, as a draft |
| `Draft: your text` | The text without the prefix |
| `Idea: your text` | The text without the prefix, also tagged `idea` |
| `Schedule <when>: your text` | The text without the prefix, also tagged `scheduled` |
| A link to one of your own posts, from the LinkedIn app's share menu or copied from the feed | A request to read that post's analytics at this computer. Nothing is saved as a draft |
| `Read: <post link>` | The same request; any text beside the link is saved as a draft tagged `read` |
| Text and a post link together | The request, and the text without the link as a draft |
| A link to someone else's post, or to a post the studio does not hold | Nothing is read. The link is listed in the panel as not one of your posts |
| A short `lnkd.in` link, which the LinkedIn app's **Copy link** gives, alone or with text around it | A post sent from your phone: Today shows "You sent a post from your phone". Nothing in that message is saved as a draft, so send an idea in a message of its own. See below |
| A link to a profile, or any other address | Kept in the text as an ordinary draft |
| A voice note | Only the placeholder "[Voice Memo Received: Local transcription pending]" |
| A photo, file, sticker or other message with no text | Nothing. It is skipped, and so is any caption |

Any `#hashtag` in the text also becomes a tag, up to 30. An em dash in your message is saved as ` -- `.

> [!WARNING]
> `Schedule <when>:` does not schedule anything. The time is read but not stored, and the post is saved as an ordinary draft. Voice notes are not transcribed.

The `Schedule` prefix is recognised only in a one-line message whose `<when>` uses just letters, digits, spaces, colons and hyphens, followed by `:` or `|`. Otherwise the whole message, prefix included, is saved as plain text. If your text contains another colon, everything before the last colon is taken as `<when>` and dropped.

## What the bot says back

Each message gets one short sentence back, the same words every time. None carries your words, your figures or anything about anyone else:

| What became of your message | The bot says |
| --- | --- |
| Saved as a draft | Saved as a draft in your studio. |
| A link to one of your posts | Today will ask you to open this post's analytics at your computer. |
| A short `lnkd.in` link | Today will ask you to open this link at your computer. |
| A link to a post that is not yours | That is not one of your posts, so your studio will not read it. |
| A photo, a sticker or anything with no text | That message had no text, so nothing was saved. |
| A message your studio could not save, after three tries | Your studio could not save that message. Open the studio to see why. |
| You pressed **This is me**, or saved a chat id | Paired. Messages from this chat now arrive in your studio. Send /help to see what I do. |
| A message before any chat is paired | Not paired yet. In your studio, open Settings, then Local security, and press This is me beside chat 487215963. (Your own chat's number.) |
| A message from a chat that is not the paired one | This bot takes messages only from the chat its owner paired. |

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

Each accepted message is saved in the local database as a post with status draft. The open studio page does not update by itself. To find it:

- Press Ctrl+K and look under **Posts**. See [Search everything with Ctrl+K](use-the-command-palette.md).
- Or reload the page. The Composer opens the draft you created most recently, which may or may not be this one. See [Start a new post, or find one you wrote earlier](start-a-new-post-or-find-an-earlier-one.md).

Each check asks Telegram to wait up to 30 seconds for a new message, so a message sent during a check arrives straight away. Between checks the studio pauses about 2 seconds, 120 seconds between 23:00 and 06:00 local time, and up to 60 seconds after errors. When Telegram asks it to slow down, it waits as long as Telegram says.

## Check it is running

The panel under **Your phone, through Telegram** reads:

- **Asking Telegram for messages**: YES while the studio is polling.
- **Messages saved since the studio started**: how many messages were saved since startup.
- **Posts asked for from the phone, waiting**: open requests.
- **Last problem reaching Telegram**: the most recent error, with the bot token removed. It is cleared after each successful check.

## Turn it off

Click **Remove the bot** in the panel. The token and chat id are removed from this profile and the studio stops asking Telegram. To block the connection without removing them, set `INOX_ALLOW_INGRESS_EGRESS=0` before you start the studio; `INOX_NO_EGRESS=1` refuses it along with every other outbound category. In both cases each attempt is counted as refused in the ledger.

## If it does not work

| You see | What to do |
| --- | --- |
| **Save and start** stays disabled | Paste the bot token: it is the one value needed to start |
| No chat appears under **CHATS THE BOT REFUSED** after you message the bot | Check **Asking Telegram for messages** reads YES, and that you messaged the bot whose token you saved. The list is kept in memory, so it starts empty each time the studio starts |
| A sentence under the buttons says the token or chat id is not the right shape | Paste the token exactly as BotFather gave it, and the chat id as digits only |
| **Asking Telegram for messages** reads NO after saving | Reload the page. If it stays NO, see [The studio will not open or shows an error](the-studio-will-not-open.md) |
| Nothing arrives, no error | Check the chat id is yours, then search with Ctrl+K instead of waiting for the page |
| A post link arrived but Today does not offer it | The panel lists it as not one of your posts: the studio holds no post of yours with that link. If it is yours and new, run **Posts you wrote** in Setup's step 5, then share it again |
| Today still says "You sent a post from your phone" after you opened it | The post's page did not keep the link's ending, so the extension could not say which post it was. Press **Done** once you have seen it |
| Arrivals are slow | Night-time polling, error backoff, or a Telegram rate limit, which the studio waits out |
| A message sent while the studio was off is missing | It is fetched at next start only if Telegram still holds it; how long it does is Telegram's policy |
| The same idea appears twice after a restart | It arrived just before the studio stopped, before the studio had confirmed it to Telegram. Delete the extra draft |
