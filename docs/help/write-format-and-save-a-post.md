# Write, format and save a post
Write in the Composer, watch the mobile fold, format a selection, and save your draft to this machine.

## Write

Open **Composer** from the rail. The editor is the large writing area in the middle, with the placeholder "Start writing. The fold mark appears once the post runs past it." The bar at the top shows the first line of your post as its title, or "Untitled draft" while it is empty.

## Watch the fold

On a phone, LinkedIn hides a long post behind "see more". The studio draws that cut at 140 characters.

- Once your post passes 140 characters, a dashed orange line appears in the editor at the point where the cut falls, labelled **LINKEDIN FOLD 140 CHARS** in the margin, or **FOLD 140** where the margin is narrow, as on a phone.
- The status strip in the top bar reads, for example, `126 / 3,000 chars · 90% of fold · ~6s read` while you are under the fold, and `352 / 3,000 chars · 212 past fold · ~25s read` once you are over it. The count turns orange past 3,000, the length the Audit's Gate 2 blocks at. The strip is hidden when the window is narrow.
- The read time assumes 200 words per minute. It is an estimate.

The fold is measured as a reader sees the text, so bold letters and struck-through letters count once each, not twice. The count against 3,000 is every character as it is stored, which is what a length limit counts and the same count the Audit uses: underlined and struck-through letters count twice there, and so do the vowel signs of scripts such as Hindi and Gujarati. Which count LinkedIn itself applies has not been measured.

The 140 figure is the product's own approximation, and the studio's server-side checks use the same number. It is not a number LinkedIn publishes, so treat it as a guide.

## Format a selection

1. Select some text in the editor.
2. A small toolbar appears above the selection. The formatting buttons are icons; hover one to see its name.
3. Press a button. The text stays selected, so you can apply more than one.

From the keyboard, **Ctrl+B** applies bold, **Ctrl+I** italic and **Ctrl+U** underline to the selection (**Cmd** on a Mac).

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

Saving is manual. Press **Save** in the top bar, or **Ctrl+S** (**Cmd+S** on a Mac) while you type. While a save is under way the button is greyed out, so a second press cannot make a second copy. If you reload, close the tab or leave the studio with text that is not saved, the browser asks before it lets the text go. Moving between screens in the studio keeps the Composer's text. The mark beside **Save** tells you where you stand:

| Mark | Meaning |
| --- | --- |
| UNCHANGED | Nothing edited since the studio opened |
| UNSAVED | You have changes that are not on disk |
| SAVING | The save is in progress |
| SAVED 14:02:37 | Written to the database at that time |
| SAVE FAILED | The save did not happen. Your text is still in the editor, and the reason is written in orange under the bar |
| COPIED AND MARKED AS POSTED | You used **Copy and mark posted** on this post. After **Queue it** or **Send to LinkedIn**, that action's own message shows here instead, for example QUEUED FOR followed by the slot |

## What happens

The first save creates a post in the studio's local database with the status draft. Later saves overwrite that same post, unless you have cleared the editor or replaced all of its text at once since (see below). Nothing is sent anywhere. The next time you open the studio, the Composer reopens the draft you created most recently.

## Start a new post

Press **New post** in the top bar. The editor clears, and the post you were writing stays in **Drafts** as it was last saved. If it has unsaved changes, the studio asks before it lets them go.

If you empty the editor, or select all of its text and type or paste over it, the Composer treats what follows as a new post. A line under the bar says your earlier draft is kept as it was saved, and the next **Save** creates a separate draft. Press **Write over that draft instead** on that line if you meant to rewrite the earlier draft.

After **Copy and mark posted**, **Queue it** or **Send to LinkedIn**, the post leaves the draft list and the Composer clears, so the next post you type is saved as a new one and the one you just recorded or queued is not touched. A queued post stays on the **Queue**, and a published one in **Analytics**. See [Start a new post, or find one you wrote earlier](start-a-new-post-or-find-an-earlier-one.md) and [Publish, queue or send a post to LinkedIn](publish-queue-or-send-to-linkedin.md).

## If it does not work

- **SAVE FAILED**: the reason is written in orange under the top bar, and a screen reader announces it with the mark.
- "There is nothing written to save.": the editor is empty. Type something first.
- "This post is already queued, so its text was not changed...": the Composer still holds a post that has been queued, published or sent, and the studio will not write new text over it by accident. Press **Correct the queued post** (or the published or sent post) to change that post's text after confirming, or **Save as a new draft** to keep the post as it was and save your text as a new draft. A post that has already gone to LinkedIn changes only in the studio; correct it on LinkedIn as well.
- "This draft was changed in another window after this one opened it...": the same draft is open in another window or tab, and it was saved there after this one loaded it. Nothing was written, so the other window's text is safe. Press **Keep this version** to save this window's text over it, or copy your text, reload, and compare.
- "Post content exceeds maximum 5,000 character limit.": the server refuses posts over 5,000 characters. Shorten the post and save again. Underlined and struck-through text store an extra mark for every character, so they count double toward this limit and a heavily decorated post reaches it sooner.
- Any other failure usually means the server stopped. See [The studio will not open or shows an error](the-studio-will-not-open.md).
