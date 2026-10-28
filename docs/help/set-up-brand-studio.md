# Set up your Brand and your Settings
See your profile as LinkedIn last showed it and set how you sign your images in **Brand**; see your backups, what has left this machine and your licence in **Settings**.

## Open them

**Brand** and **Settings** are two entries in the rail. They used to open one screen, Brand Studio, with six tabs that opened on a Name, Headline and Company form; they are two screens now, each opening on what it is for, with the rest one level down.

- **Brand** opens on **Profile**, with **Identity**, **Watermark** and **Writing** beside it.
- **Settings** opens on **Overview**, with **Grounding**, **Local security**, **Storage and privacy** and **Licence** beside it.

## Brand: your profile as LinkedIn last showed it

**Profile** shows what the bridge read from your own LinkedIn profile, once you have confirmed it in **Setup**: your name and headline, your location, company and About, your roles with their dates, location and description, your education and your skills. Each says when it was read, for example READ TUE 20 OCT; your name, headline, About and the rest of the top of your profile are read together, so they share one date. Nothing here is edited: it changes when the bridge next reads your profile.

Beside it, **Followers and connections** lists the counts on the days your profile was read, newest first. They are the days it was read, not every day, and the screen says how many. **How you sign images and slides** shows your byline as the feed preview draws it, and **How you write** your habits, measured across your posts once three are held.

Before you confirm your profile, **Profile** says so and offers **Go to Setup**.

## Brand: Identity, your two identities side by side

The studio holds two identities. **Your profile on LinkedIn** is the one **Setup** confirmed and the bridge reads; it is shown here, read only, with when it was read. **Your byline** is how the studio signs images, slides and the feed preview: **Name** ("How you sign your work"), **Headline** ("The line under your name") and **Company** ("Optional").

Your byline starts as your LinkedIn profile when you confirm it in **Setup**, where its fields are empty; what you typed there is never replaced. When the two differ, **Use what LinkedIn shows** copies your profile's name, headline and company into the byline; press **Save** to keep it.

1. Open **Brand**, then **Identity**.
2. Fill in or change **Name**, **Headline** and, if you like, **Company**.
3. Check the **As the feed shows it** card beside the fields. It shows Unnamed and No headline while they are empty, and your company when there is no headline.
4. Press **Save**.

Until a name has been saved, the screen reads UNTIL A NAME IS SAVED, WATERMARKS AND THE FEED PREVIEW STAY UNNAMED RATHER THAN GUESSING ONE. Outside **Brand**, your byline is used in two places only: the **Preview** tab and the **Brand** tab of the inspector beside the **Composer**. It is not added to your posts.

## How saving works

**Save**, at the top right of **Brand** while **Identity** or **Watermark** is open, saves both together. **Writing** has a **Save** of its own.

- It is greyed out until you first change something, and while a save is running. After a save it stays available.
- The mark beside it reads UNSAVED, SAVING, SAVED or SAVE FAILED. Hover over SAVE FAILED to read the reason.
- While it reads UNSAVED or SAVE FAILED, leaving **Brand** or switching profile asks first, naming "Your Brand edits", because the edits would be lost.

The controls in **Settings** act as soon as you use them and do not need **Save**.

## Brand: Watermark

| Control | What it sets |
| --- | --- |
| **Stamp generated media** | Whether the watermark is on |
| **Watermark text** | The mark. The field shows your Name as its placeholder, or "Your mark" |
| **Position** | One of nine squares in a 3 by 3 grid |
| **Style** | glass pill, solid bar or plain text |

The **Preview frame** shows the mark where you placed it. It is labelled A DRAWN FRAME, NOT ONE OF YOUR IMAGES, and reads WATERMARK OFF when the box is unticked or NO MARK SET when there is no text and no name.

> [!WARNING]
> These settings are saved, but nothing in the interface applies them yet. Images you generate from the **Media** tab are never stamped with your watermark, whatever you choose here.

## Brand: Writing

How the studio writes for you. Every writing request reads these: **Make a post**, **Combine** and **Angles** in **From your record**'s **Your collection**, **Write it up** on your Telegram bot, and **Command** and **Re-Hook** in the Composer. Each says its default under it, and each feature shows the ones it reads beside it.

| Preference | Default |
| --- | --- |
| Length of a draft | About 150 words (60, 100, 150, 200 or 300) |
| Tone | punchy, high-signal, authentic and authoritative |
| Language | The language of what you wrote |
| Opening line | A first line that stops the scroll, or one of Re-Hook's forms |
| Emojis | No emojis |
| Hashtags | Only those already in what you wrote |
| Line breaks | Short paragraphs of one or two sentences |
| Ending | A thoughtful question or takeaway |
| Words to avoid | In today's fast-paced world, game-changer, delve, testament |
| Angles | 3 opening lines (2 to 5) |

The defaults are what Command was told until now. Press **Save** under them to keep your changes, or **Back to the defaults**. The rules that keep writing honest are not choices: only what you sent is used, no figure, person, date or quote is invented, and no em dash. The provider every request goes to is the one connected on the Composer's **Prompt** tab, named at the top.

## Settings: Overview

**Overview** shows six values, each with a link to the place one level down where it can be changed:

| Value | What it says |
| --- | --- |
| **Last backup** | When the newest backup was made, whether its check passed ("verified", "its check failed", or "made before checks were recorded"), and when the next daily backup is due, or that the daily backup is off |
| **Next cleanup** | For old telemetry, old post readings and old reactions: on, off or waiting for you, and how many rows a cleanup would remove now. Cleanups run every hour while the studio runs, behind a checked backup |
| **What has left this machine** | How many counted requests have left since the studio started, and how many were refused |
| **Licence** | Your tier, and when it ends or until when it gets updates |
| **Update check** | On or off, and when it last checked. **Turn it on** or **Turn it off** changes it here. While it is off, no request leaves this machine for a version check |
| **Start with your computer** | Whether the studio starts when you sign in, with **Turn it on** or **Turn it off**, or that it is not available on this system |

## Settings: Grounding

This lets you register local programs (MCP servers) that the studio may run to read reference material. Adding one stores a command this machine will execute, so it is a larger grant than anything else here. See [Add a grounding source (MCP), and what you are allowing](add-a-grounding-source.md).

## Settings: Local security

It opens with "This install processes your work on this machine." and four status rows.

| Row | What it shows | What it really means |
| --- | --- | --- |
| Server binding | LOOPBACK ONLY | Fixed text. The server listens on 127.0.0.1 |
| Credential store | LOCAL SQLITE VAULT | Fixed text, always green. Your LinkedIn session and your AI provider key are both sealed before they are stored. See [Connect your own AI provider](connect-your-own-ai-provider.md) |
| Model engine | RUNS LOCALLY or SENDS TO PROVIDER | SENDS TO PROVIDER when an AI key is saved. UNKNOWN if the status could not be read |
| LinkedIn session | CONNECTED or NOT CONNECTED | Shown in green either way |

Below the rows, a short list says what stays and what leaves: your drafts, posts, leads, analytics and media stay on this machine, and three actions send something only when you use them. **Send to LinkedIn** sends the post's text to LinkedIn with your session. With an AI provider connected, **Re-Hook**, **Command** and the other writing actions send the draft or instruction text to it; the line says whether one is connected. **Generate** in the Media tab sends a prompt built from your image description to an image service. Then come three sections:

- **What has left this machine**, the egress ledger. Each kind of request now also shows the switch that controls it, whether it is on by default, and the last place it was sent or refused. See [What leaves this machine, and when](what-leaves-this-machine.md).
- **LinkedIn session**, the one control for your session: whether one is stored, when it was saved and, for a session the extension's **Sync** captured, which account it belongs to; **Delete**, which asks "Yes, delete the session" or "Keep it"; and the fields to paste one by hand. **Setup** used to show the session with its own **Delete**; it now points here. See [Connect your LinkedIn session](connect-your-linkedin-session.md).
- **Your phone, through Telegram**. See [Send a post idea from Telegram](send-a-post-idea-from-telegram.md).

## Settings: Storage and privacy

**Your data** comes first, with **Back up now**, **Export JSON** and **Export CSV**, and the backup list. Each backup in the list says whether its check passed when it was made (VERIFIED, CHECK FAILED, or NOT CHECKED for one made before checks were recorded) and the schema of the database it holds. The list opens on the newest five; **Show all** lists every one. See [Back up, restore and export](back-up-restore-and-export.md) and [Choose what the studio keeps](choose-what-the-studio-keeps.md).

At the foot, **Kept from the review** lists the people you chose to keep in the silent-lead review, with the day you kept each. **Take back** removes the keep, so the person can be listed for review again when they qualify.

## Settings: Licence

Your tier, your licence and its end, and how many creator profiles it covers. See [Keep each creator separate, and enter a licence](keep-each-creator-separate-and-enter-a-licence.md).

## What happens

- **Identity** and **Watermark** are stored together as one record in the settings table of the local database. Each **Save** replaces the whole record. Your profile as LinkedIn showed it is kept apart from it, and only the bridge changes it.
- Nothing is sent anywhere when you save.
- Backups include the record. Exports do not, because they leave out the settings table.
- `python -m studio.cli reset --yes` clears the whole settings table, so it clears your byline and watermark too, after taking a safety backup.

## If it does not work

| What you see | What it means |
| --- | --- |
| LOADING YOUR BRAND stays on screen | The byline has not arrived. Reload the page |
| YOUR BRAND COULD NOT BE READ. | The request failed, usually because the server stopped. See [The studio will not open](the-studio-will-not-open.md) |
| SETTINGS COULD NOT BE READ. IS THE STUDIO RUNNING? | The overview could not be read. It reads again when the studio answers |
| SAVE FAILED | Hover over it for the server's reason. Your edits are still in the form, so press **Save** again once it is fixed |

<!-- Strict Invariants: zero em-dashes. -->
