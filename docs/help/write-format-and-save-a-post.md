# Write, format and save a post
Write in the Composer, watch the mobile fold, format a selection, and save your draft to this machine.

## Write

Open **Composer** from the rail. The editor is the large writing area in the middle, with the placeholder "Start writing. The fold mark appears once the post runs past it." The bar at the top shows the first line of your post as its title, or "Untitled draft" while it is empty.

> [!NOTE]
> The label **POST / DRAFT 01** in the top bar is fixed text. It is not a draft number.

## Watch the fold

On a phone, LinkedIn hides a long post behind "see more". The studio draws that cut at 180 characters.

- Once your post passes 180 characters, a dashed orange line appears in the editor at the point where the cut falls, labelled **LINKEDIN FOLD 180 CHARS**.
- The status strip in the top bar reads, for example, `142 chars · 79% of fold · ~12s read` while you are under the fold, and `352 chars · 172 past fold · ~25s read` once you are over it. The strip is hidden when the window is narrow.
- The read time assumes 200 words per minute. It is an estimate.

Characters are counted as a reader sees them, so bold letters and struck-through letters count once each, not twice.

The 180 figure is the product's own approximation, taken from its design blueprint. It is not a number LinkedIn publishes, so treat it as a guide.

## Format a selection

1. Select some text in the editor.
2. A small toolbar appears above the selection. The formatting buttons are icons; hover one to see its name.
3. Press a button. The text stays selected, so you can apply more than one.

| Button | What it does |
| --- | --- |
| Bold | Swaps the letters for Unicode bold characters |
| Italic | Swaps the letters for Unicode italic characters |
| Underline | Adds an underline mark after each character |
| Monospace | Swaps the letters for Unicode monospace characters |
| Strikethrough | Adds a strike mark after each character |
| Clean formatting | Replaces em dashes, en dashes and double hyphens between words with commas, turns en dash number ranges such as 2021-2024 into plain hyphens, and tidies extra spaces |
| Re-Hook | Generates ten alternative openings from the selection. See [Try a different opening line](try-a-different-opening-line.md) |

These are real Unicode characters, not markup, so they survive copy and paste. The studio's own server on this PC does the formatting.

> [!WARNING]
> **Clean formatting** does not undo bold, italic, monospace, underline or strikethrough. It only fixes dashes and spacing. To remove a style, retype the text.

## Save

Saving is manual. Press **Save** in the top bar. The mark beside it tells you where you stand:

| Mark | Meaning |
| --- | --- |
| UNCHANGED | Nothing edited since the studio opened |
| UNSAVED | You have changes that are not on disk |
| SAVING | The save is in progress |
| SAVED 14:02:37 | Written to the database at that time |
| SAVE FAILED | The save did not happen. Your text is still in the editor |
| MARKED AS PUBLISHED | You used **Mark as published** on this post. After **Queue it** or **Send to LinkedIn**, that action's own message shows here instead, for example SCHEDULED FOR followed by the slot |

## What happens

The first save creates a post in the studio's local database with the status draft. Later saves overwrite that same post. Nothing is sent anywhere. The next time you open the studio, the Composer reopens the draft you created most recently.

## Start a new post

There is no New draft button, no list of drafts, and no way to delete a post from the interface.

After you use **Mark as published**, **Queue it** or **Send to LinkedIn**, the Composer keeps working on that same post. If you then type and press **Save**, you overwrite the text of the post you just recorded or queued. To start a fresh post, reload the page first. The Composer then reopens your most recent remaining draft, or opens empty. See [Publish, queue or send a post to LinkedIn](publish-queue-or-send-to-linkedin.md).

## If it does not work

- **SAVE FAILED**: hover over the mark to read the reason. It is only shown as a tooltip.
- "There is nothing written to save.": the editor is empty. Type something first.
- "Post content exceeds maximum 5,000 character limit.": the server refuses posts over 5,000 characters. Shorten the post and save again. Underlined and struck-through text store an extra mark for every character, so they count double toward this limit and a heavily decorated post reaches it sooner.
- Any other failure usually means the server stopped. See [The studio will not open or shows an error](the-studio-will-not-open.md).
