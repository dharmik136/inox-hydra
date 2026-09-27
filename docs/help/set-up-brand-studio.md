# Set up Brand Studio: identity, watermark, grounding and local security
Save the name and headline your previews show, and find the watermark, grounding and privacy settings.

## Open it

Press **Brand Studio** in the rail. It has four tabs: **Identity**, **Watermark**, **Grounding** and **Local security**.

## How saving works

The **Save** button at the top right saves **Identity** and **Watermark** only, together.

- It is greyed out until you first change something, and while a save is running. After a save it stays available.
- The mark beside it reads UNSAVED, SAVING, SAVED or SAVE FAILED. Hover over SAVE FAILED to read the reason.

The controls on **Grounding** and **Local security** act as soon as you use them and do not need **Save**.

## Identity

1. Open the **Identity** tab.
2. Fill in **Name** ("How you sign your work"), **Headline** ("The line under your name") and, if you like, **Company** ("Optional").
3. Check the **As the feed shows it** card beside the fields. It shows Unnamed and No headline while they are empty, and your company when there is no headline.
4. Press **Save**.

Until a name has been saved, the tab reads UNTIL A NAME IS SAVED, WATERMARKS AND THE FEED PREVIEW STAY UNNAMED RATHER THAN GUESSING ONE.

Outside Brand Studio, your identity is used in two places only: the **Preview** tab and the **Brand** tab of the inspector beside the **Composer**. It is not added to your posts.

## Watermark

| Control | What it sets |
| --- | --- |
| **Stamp generated media** | Whether the watermark is on |
| **Watermark text** | The mark. The field shows your Name as its placeholder, or "Your mark" |
| **Position** | One of nine squares in a 3 by 3 grid |
| **Style** | glass pill, solid bar or plain text |

The **Preview frame** shows the mark where you placed it. It is labelled A DRAWN FRAME, NOT ONE OF YOUR IMAGES, and reads WATERMARK OFF when the box is unticked or NO MARK SET when there is no text and no name.

> [!WARNING]
> These settings are saved, but nothing in the interface applies them yet. Images you generate from the **Media** tab are never stamped with your watermark, whatever you choose here.

## Grounding

This tab lets you register local programs (MCP servers) that the studio may run to read reference material. Adding one stores a command this machine will execute, so it is a larger grant than anything else here. See [Add a grounding source (MCP), and what you are allowing](add-a-grounding-source.md).

## Local security

The tab opens with "This install processes your work on this machine." and four status rows.

| Row | What it shows | What it really means |
| --- | --- | --- |
| Server binding | LOOPBACK ONLY | Fixed text. The server listens on 127.0.0.1 |
| Credential store | LOCAL SQLITE VAULT | Fixed text, always green. Your LinkedIn session is encrypted, but an AI provider key is stored as plain text. See [Connect your own AI provider](connect-your-own-ai-provider.md) |
| Model engine | RUNS LOCALLY or SENDS TO PROVIDER | SENDS TO PROVIDER when an AI key is saved. UNKNOWN if the status could not be read |
| LinkedIn session | CONNECTED or NOT CONNECTED | Shown in green either way |

Below the rows, the line YOUR DRAFTS, LEADS AND LINKEDIN SESSION NEVER LEAVE THIS MACHINE is not the whole story: **Send to LinkedIn** sends the post itself to LinkedIn, using your session. Then come three sections:

- **What has left this machine**, the egress ledger. See [What leaves this machine, and when](what-leaves-this-machine.md).
- **LinkedIn session**, where you paste your session. See [Connect your LinkedIn session](connect-your-linkedin-session.md).
- **Your data**, with **Back up now**, **Export JSON** and **Export CSV**. See [Back up, restore and export](back-up-restore-and-export.md).

## What happens

- **Identity** and **Watermark** are stored together as one record in the settings table of the local database. Each **Save** replaces the whole record.
- Nothing is sent anywhere when you save.
- Backups include the record. Exports do not, because they leave out the settings table.
- `python -m studio.cli reset --yes` clears the whole settings table, so it clears your identity and watermark too, after taking a safety backup.

## If it does not work

| What you see | What it means |
| --- | --- |
| LOADING BRAND STUDIO stays on screen | The profile has not arrived. Reload the page |
| THE PROFILE COULD NOT BE READ. | The request failed, usually because the server stopped. See [The studio will not open](the-studio-will-not-open.md) |
| SAVE FAILED | Hover over it for the server's reason. Your edits are still in the form, so press **Save** again once it is fixed |
| The inspector's **Brand** tab says EDITED IN BRAND STUDIO, WHICH IS NOT BUILT YET | That note is out of date. Brand Studio is built, and this is where you edit the profile |
