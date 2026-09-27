# Send a post idea from your phone with Telegram
If you create your own Telegram bot and set two environment variables before starting the studio, messages you send that bot arrive in the studio as drafts.

## What it is, and what it is not

- It is optional and off unless you configure it. There is no switch or setting for it anywhere in the studio interface. The only trace is the `ingress` row under **What has left this machine** in Brand Studio's **Local security** tab, which counts each request to Telegram.
- The bot never replies. You get no confirmation in Telegram.
- It works only while the studio is running. The studio asks Telegram for messages and opens no port.
- Your message text passes through Telegram's servers. See [What leaves this machine, and when](what-leaves-this-machine.md).

> [!NOTE]
> This has been tested only against a simulated Telegram, not end to end against the real service.

## What you need

Your own bot token and your own numeric chat id. Creating a bot and finding your chat id are done with Telegram's own tools; the studio does not guide you.

## Set it up

1. Set `TELEGRAM_BOT_TOKEN` to your bot token and `TELEGRAM_CHAT_ID` to your chat id, in the environment the studio server starts from. (`PRUDENT_TELEGRAM_BOT_TOKEN` and `PRUDENT_TELEGRAM_CHAT_ID` are also accepted.)
2. Stop the studio and start it again. See [Stop the studio, and use the tray icon](stop-the-studio-and-use-the-tray-icon.md). Both values are read once at startup, so a change needs a restart.

> [!IMPORTANT]
> Set the chat id as well as the token. Without it every message is refused, and a refused message is not delivered again after you fix it. Messages from any other chat are dropped.

## Send an idea

Send the bot a text message. You can start it with a prefix, in any letter case. Every saved message is tagged `mobile-ingress`.

| You send | What the studio saves |
| --- | --- |
| Plain text | The text |
| `Draft: your text` | The text without the prefix |
| `Idea: your text` | The text without the prefix, also tagged `idea` |
| `Schedule <when>: your text` | The text without the prefix, also tagged `scheduled` |
| A voice note | Only the placeholder "[Voice Memo Received: Local transcription pending]" |
| A photo, file, sticker or other message with no text | Nothing. It is skipped, and so is any caption |

Any `#hashtag` in the text also becomes a tag, up to 30. An em dash in your message is saved as ` -- `.

> [!WARNING]
> `Schedule <when>:` does not schedule anything. The time is read but not stored, and the post is saved as an ordinary draft. Voice notes are not transcribed.

The `Schedule` prefix is recognised only in a one-line message whose `<when>` uses just letters, digits, spaces, colons and hyphens, followed by `:` or `|`. Otherwise the whole message, prefix included, is saved as plain text. If your text contains another colon, everything before the last colon is taken as `<when>` and dropped.

## What happens

Each accepted message is saved in the local database as a post with status draft. The open studio page does not update by itself. To find it:

- Press Ctrl+K and look under **Posts**. See [Search everything with Ctrl+K](use-the-command-palette.md).
- Or reload the page. The Composer opens the draft you created most recently, which may or may not be this one. See [Start a new post, or find one you wrote earlier](start-a-new-post-or-find-an-earlier-one.md).

Each check asks Telegram to wait up to 30 seconds for a new message, so a message sent during a check arrives straight away. Between checks the studio pauses about 2 seconds, 120 seconds between 23:00 and 06:00 local time, and up to 60 seconds after errors. When Telegram asks it to slow down, it waits as long as Telegram says.

## Check it is running

Open `http://127.0.0.1:8000/api/v1/ingress/status` in the browser where you use the studio; it needs the studio's token cookie. An automated test calls this endpoint, but it has not been checked in a browser. Look at:

- `is_running`: whether the worker started.
- `has_token` and `has_authorized_chat_id`: whether each value was found.
- `total_polls` and `total_messages_processed`: how many checks have run and how many messages were saved since startup.
- `last_error`: the most recent problem with reaching Telegram, with the bot token removed. It is cleared after each successful check.

## Turn it off

Remove the two variables and restart the studio. To block the connection to Telegram without removing them, set `INOX_ALLOW_INGRESS_EGRESS=0` before you start the studio; `INOX_NO_EGRESS=1` refuses it along with every other outbound category. In both cases the worker keeps running, and each attempt it makes is counted as refused in the ledger.

## If it does not work

| You see | What to do |
| --- | --- |
| Nothing arrives and `is_running` is false | The token was not in the studio's environment at startup. Set it and restart |
| `has_authorized_chat_id` is false | Set `TELEGRAM_CHAT_ID` to your own numeric chat id and restart. Messages sent before that are gone; send them again |
| Nothing arrives, no error | Check the chat id is yours, then search with Ctrl+K instead of waiting for the page |
| Arrivals are slow | Night-time polling, error backoff, or a Telegram rate limit, which the studio waits out |
| A message sent while the studio was off is missing | It is fetched at next start only if Telegram still holds it; how long it does is Telegram's policy |
| The same idea appears twice after a restart | It arrived just before the studio stopped, before the studio had confirmed it to Telegram. Delete the extra draft |
