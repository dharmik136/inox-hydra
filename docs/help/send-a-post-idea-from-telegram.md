# Send a post idea or a post link from your phone with Telegram

Make a Telegram bot of your own, set it up under Local security, and the messages you send it arrive in the studio: text as a draft, and a LinkedIn post link as the page Today asks you to open at this computer.

## What it is, and what it is not

- It is optional and off until you set it up. The studio asks Telegram for your bot's messages while it is running, and opens no port. Each request is counted under the `ingress` row of **What has left this machine** in Brand Studio's **Local security** tab.
- The phone sends a link, never a figure. Nothing you send is written as a reading: a post link becomes a request to read that post here, where the extension reads the real page.
- The bot never replies. You get no confirmation in Telegram.
- Your message text passes through Telegram's servers. See [What leaves this machine, and when](what-leaves-this-machine.md).
- The bot belongs to the creator profile you set it up in, and its messages are saved there whichever profile is open. One bot is asked at a time: the one saved most recently, or when the studio starts, the first profile that has one. A profile whose bot is not the one being asked says so in its panel.

> [!NOTE]
> This has not yet been tested against the real Telegram service, only against a simulated one. The panel says so until it has been.

## What you need

Your own bot token and your own numeric chat id. Creating a bot and finding your chat id are done with Telegram's own tools; the studio does not guide you.

## Set it up

1. Open **Brand Studio** from the rail, then **Local security**.
2. Under **Your phone, through Telegram**, paste the bot token into **Bot token** and your chat id into **Your numeric chat id**.
3. Click **Save and start**. The panel reads **SET, SEALED** beside the token, your chat id beside **Your chat id**, and **YES** beside **Asking Telegram for messages**.

The token is sealed before it is stored, like your AI key, and is never shown again. A token or chat id of the wrong shape is refused with a sentence and nothing is stored.

> [!IMPORTANT]
> Both values are needed. Without a chat id the bot has no way to tell you from anybody else, so every message is refused, and a refused message is not delivered again later. Messages from any other chat are dropped. A group's chat id, which starts with a minus sign, is refused, because anyone in the group could then file drafts in your studio.

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
| A link to a profile, a short `lnkd.in` link, or any other address | Kept in the text as an ordinary draft. A short link names no post the studio can read without fetching it, which it will not do |
| A voice note | Only the placeholder "[Voice Memo Received: Local transcription pending]" |
| A photo, file, sticker or other message with no text | Nothing. It is skipped, and so is any caption |

Any `#hashtag` in the text also becomes a tag, up to 30. An em dash in your message is saved as ` -- `.

> [!WARNING]
> `Schedule <when>:` does not schedule anything. The time is read but not stored, and the post is saved as an ordinary draft. Voice notes are not transcribed.

The `Schedule` prefix is recognised only in a one-line message whose `<when>` uses just letters, digits, spaces, colons and hyphens, followed by `:` or `|`. Otherwise the whole message, prefix included, is saved as plain text. If your text contains another colon, everything before the last colon is taken as `<when>` and dropped.

## What happens to a post link

The link names the post by the number in it, which is the same for the app's share-menu form and the feed's. The studio reads only your own posts, so what happens depends on whose post it is.

- **One of your recorded posts:** **Today** says "You asked from your phone to read this post's analytics" under **ONE THING TO OPEN**, oldest request first, with **Open it in the bridge browser**. When your latest post is in its first three days and its figures are due to be read, that comes first, and your request right after it. **Not now** beside it closes the request. Otherwise it is done once that post's analytics page has been read after you asked, and closed with a note after a week unread. See [What to do today](what-to-do-today.md).
- **Anything else**, such as someone else's post, or a post of yours the studio has not read yet: a post that is not yours is never read. The link is listed under **LINKS FROM YOUR PHONE** in the panel with "Not one of your posts", and never appears on Today. If it is yours and new, run **Posts you wrote** in Setup's step 5, then share the link again.

The panel's **Posts asked for from the phone, waiting** line counts the open requests, and **LINKS FROM YOUR PHONE** lists the newest links with what became of each.

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
| **Save and start** stays disabled | Both fields are needed |
| A sentence under the buttons says the token or chat id is not the right shape | Paste the token exactly as BotFather gave it, and the chat id as digits only |
| **Asking Telegram for messages** reads NO after saving | Reload the page. If it stays NO, see [The studio will not open or shows an error](the-studio-will-not-open.md) |
| Nothing arrives, no error | Check the chat id is yours, then search with Ctrl+K instead of waiting for the page |
| A post link arrived but Today does not offer it | The panel lists it as not one of your posts: the studio holds no post of yours with that link. If it is yours and new, run **Posts you wrote** in Setup's step 5, then share it again |
| Arrivals are slow | Night-time polling, error backoff, or a Telegram rate limit, which the studio waits out |
| A message sent while the studio was off is missing | It is fetched at next start only if Telegram still holds it; how long it does is Telegram's policy |
| The same idea appears twice after a restart | It arrived just before the studio stopped, before the studio had confirmed it to Telegram. Delete the extra draft |
