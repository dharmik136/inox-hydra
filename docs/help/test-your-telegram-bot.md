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

1. Send `/help`. The bot says what it does, how to pair and what it never sends.
2. Send `Idea: testing the bot`. The bot answers "Saved as a draft in your studio." In the studio, press Ctrl+K and search for `testing the bot`: the draft is there.
3. Send `/status`. The bot answers "Your studio is running." and whether the bridge in your browser is connected.
4. In the LinkedIn app, open one of your own posts, use **Copy link**, and send the link to the bot. The bot answers "Today will ask you to open this link at your computer.", and **Today** shows "You sent a post from your phone". Press **Not now** there if you do not want to open it.

## 4. The panel's own check (thirty seconds)

1. Press **Send a test message**. The panel says "Sent: Telegram took it for your chat. Check your phone.", and your phone shows "This is a test message from your Inox Hydra studio."

## 5. Your figures, only if you want them (thirty seconds, optional)

1. Send `/today`. The bot answers that your figures stay in your studio: they are off until you allow them.
2. To see them on the phone, tick **The bot may answer with your figures** and send `/today` again: your latest post's figures with where and when each was read, how many replies are waiting, and when your next post is scheduled. Untick it again if you do not want your figures to sit on Telegram's servers.

## When a step does not match

| You see | Look at |
| --- | --- |
| **Asking Telegram for messages** reads NO | **Last problem reaching Telegram** in the panel, in plain words. Telegram not recognising the token means the token was pasted wrong: paste it again and save |
| No answer to `hello`, and nothing under **CHATS THE BOT REFUSED** | That you messaged the bot whose token you saved, and that **Asking Telegram for messages** reads YES. Another program asking for the same bot is named under **Last problem reaching Telegram** |
| The panel lists your chat, but the phone got no answer | **Last message the bot could not send**: the bot may be blocked in your chat. Unblock it in Telegram and send it a message |
| The bot answers, but no draft appears | Reload the studio page. The draft is saved in the profile the bot was set up in, which the panel names when another profile is open |
| **Send a test message** says Telegram took it, and the phone shows nothing | That you are looking at the chat with your own bot, and that Telegram's notifications are on for it |

If a step still does not match, note the panel's two problem lines; they carry no message text and no token, so they can be shared as they are.
