# Write, format and save a post
Write in the Composer, watch the mobile fold, format a selection, and save your draft to this machine.

## Write

Open **Composer** from the rail. The editor is the large writing area in the middle, with the placeholder "Start writing. The fold mark appears once the post runs past it." The bar at the top shows the first line of your post as its title, or "Untitled draft" while it is empty.

## Watch the fold

On a phone, LinkedIn hides a long post behind "see more". The studio draws that cut at 140 characters.

- Once your post passes 140 characters, a dashed orange line appears in the editor at the point where the cut falls, labelled **LINKEDIN FOLD 140 CHARS**.
- The status strip in the top bar reads, for example, `126 / 3,000 chars · 90% of fold · ~6s read` while you are under the fold, and `352 / 3,000 chars · 212 past fold · ~25s read` once you are over it. The count turns orange past 3,000, the length the Audit's Gate 2 blocks at. The strip is hidden when the window is narrow.
- The read time assumes 200 words per minute. It is an estimate.

The fold is measured as a reader sees the text, so bold letters and struck-through letters count once each, not twice. The count against 3,000 is every character as it is stored, which is what a length limit counts and the same count the Audit uses: underlined and struck-through letters count twice there, and so do the vowel signs of scripts such as Hindi and Gujarati. Which count LinkedIn itself applies has not been measured.

The 140 figure is the product's own approximation, and the studio's server-side checks use the same number. It is not a number LinkedIn publishes, so treat it as a guide.

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
| Clean formatting | Replaces em dashes, spaced en dashes and double hyphens between words with commas, turns unspaced en dashes and number ranges, such as Mon-Fri, Q1-Q4 or 2021-2024, into plain hyphens, and tidies extra spaces inside a line. Indentation at the start of a line is kept |
| Re-Hook | Generates ten alternative openings from the selection. See [Try a different opening line](try-a-different-opening-line.md) |

These are real Unicode characters, not markup, so they survive copy and paste. The studio's own server on this PC does the formatting.

> [!WARNING]
> **Clean formatting** does not undo bold, italic, monospace, underline or strikethrough. It only fixes dashes and spacing. To remove a style, retype the text.

## Save

Saving is manual. Press **Save** in the top bar. While a save is under way the button is greyed out, so a second press cannot make a second copy. If you reload, close the tab or leave the studio with text that is not saved, the browser asks before it lets the text go. Moving between screens in the studio keeps the Composer's text. The mark beside **Save** tells you where you stand:

| Mark | Meaning |
| --- | --- |
| UNCHANGED | Nothing edited since the studio opened |
| UNSAVED | You have changes that are not on disk |
| SAVING | The save is in progress |
| SAVED 14:02:37 | Written to the database at that time |
| SAVE FAILED | The save did not happen. Your text is still in the editor, and the reason is written in orange under the bar |
| MARKED AS PUBLISHED | You used **Mark as published** on this post. After **Queue it** or **Send to LinkedIn**, that action's own message shows here instead, for example SCHEDULED FOR followed by the slot |

## What happens

The first save creates a post in the studio's local database with the status draft. Later saves overwrite that same post. Nothing is sent anywhere. The next time you open the studio, the Composer reopens the draft you created most recently.

## Start a new post

There is no New draft button, no list of drafts, and no way to delete a post from the interface.

After you use **Mark as published**, **Queue it** or **Send to LinkedIn**, the Composer keeps working on that same post. If you then type and press **Save**, you overwrite the text of the post you just recorded or queued. To start a fresh post, reload the page first. The Composer then reopens your most recent remaining draft, or opens empty. See [Publish, queue or send a post to LinkedIn](publish-queue-or-send-to-linkedin.md).

## If it does not work

- **SAVE FAILED**: the reason is written in orange under the top bar, and a screen reader announces it with the mark.
- "There is nothing written to save.": the editor is empty. Type something first.
- "This draft was changed in another window after this one opened it...": the same draft is open in another window or tab, and it was saved there after this one loaded it. Nothing was written, so the other window's text is safe. Press **Keep this version** to save this window's text over it, or copy your text, reload, and compare.
- "Post content exceeds maximum 5,000 character limit.": the server refuses posts over 5,000 characters. Shorten the post and save again. Underlined and struck-through text store an extra mark for every character, so they count double toward this limit and a heavily decorated post reaches it sooner.
- Any other failure usually means the server stopped. See [The studio will not open or shows an error](the-studio-will-not-open.md).
