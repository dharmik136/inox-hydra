# Try a different opening line
Replace your opening paragraph with a saved hook form, or generate ten alternatives from any text you select.

## Use the hook rail

The hook rail is the strip above the editor in the **Composer**. It shows the 12 highest-rated forms from the studio's local hook library, numbered 01 to 12.

1. Scroll the rail sideways to read the specimens.
2. Click a specimen, or press **Alt** plus its number (1 to 9). The first nine carry an ALT label, and the rail reads ALT + NUMBER TO APPLY.
3. The specimen replaces your opening paragraph.

Your opening paragraph is everything up to the first blank line. If your draft has no blank line, the specimen replaces the whole draft. If the editor is empty, the specimen becomes the draft.

> [!WARNING]
> Applying a hook replaces your first paragraph outright. There is no undo button. Save before you try hooks, or copy your opening somewhere first.

The status mark turns to UNSAVED. Press **Save** to keep the change.

## Re-Hook a selection

1. Select a line or passage in the editor.
2. In the toolbar that appears, press **Re-Hook**.
3. The rail title changes to **Generated from selection** and shows ten alternatives.
4. Click one, or press **Alt** plus its number, to replace your opening paragraph with it.
5. Press **BACK TO LIBRARY** to return to the saved forms.

## Read a specimen

| Label | Where it appears | What it means |
| --- | --- | --- |
| VELOCITY | Library forms | A rating stored with the form in the library |
| SCORE | Generated hooks | A fixed number set by the fold check below: 90 if the hook fits and 75 if not when it comes from the local templates, 92 or 80 when it comes from an AI provider |
| FITS FOLD | Generated hooks | The hook's first line is 140 characters or fewer and the whole hook is 240 or fewer |
| PAST FOLD | Generated hooks | The hook fails that length check |

This check is not the same as the 180 character fold mark in the editor. Both numbers are the studio's own ratings. They are not LinkedIn measurements, and the two are not on the same scale. Library forms carry no fold verdict.

## What happens

- The hook rail reads the library in the local database. Nothing leaves the machine.
- **Re-Hook** with no AI provider configured builds the ten hooks from local templates on this PC. It takes a subject from the first line of your selection and fills it into ten fixed patterns.
- **Re-Hook** with an AI provider configured sends a prompt to that provider. The prompt contains a subject taken from the first line of your selection, not the whole post. If the call fails or the reply cannot be read, the studio falls back to the local templates without saying so.

See [Connect your own AI provider](connect-your-own-ai-provider.md) and [What leaves this machine, and when](what-leaves-this-machine.md).

## Browse more in the Swipe File

The rail shows 12 forms. The full library of 36 built-in hook forms is in **Swipe File** on the rail.

- Type in **Search specimens** to filter by text.
- Press an archetype chip to narrow the list, or **All** to clear it. The count reads, for example, `6 OF 36`.
- Hover over a card to read the full specimen. It collapses when the pointer leaves.

The banner reads "These are hook forms, not posts anyone measured." The library stores patterns, not real posts, so no reaction or comment counts are shown.

There is no button that moves a specimen into the Composer. Select the text on the card, copy it, and paste it into the editor.

## If it does not work

| What you see | What it means |
| --- | --- |
| HOOK LIBRARY UNAVAILABLE | The rail could not reach the server. Reload the page. If it persists, see [The studio will not open or shows an error](the-studio-will-not-open.md) |
| NO HOOKS IN THE LOCAL LIBRARY YET | The server returned no forms. The studio refills an empty library with the 36 built-in forms each time it reads it, so this usually means the database could not be read. Reload the page, then restart the studio if it persists |
| LOADING HOOKS stays | The server is slow or stopped |
| Re-Hook seems to do nothing | The request failed. No error is shown, and if generated hooks were on the rail it returns to the library. Check that text is actually selected (a selection of only spaces is ignored), then try again |

Pulling new hook forms from an online bundle is not available from the interface.
