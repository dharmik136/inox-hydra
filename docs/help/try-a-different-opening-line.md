# Try a different opening line
Replace your opening paragraph with a saved hook form, or generate ten alternatives from any text you select.

## Use the hook rail

The hook rail is the strip above the editor in the **Composer**. It shows the 12 highest-rated forms from the studio's local hook library, numbered 01 to 12.

1. Scroll the rail sideways to read the specimens.
2. Click a specimen, or press **Alt** plus its number (1 to 9) on the row of number keys above the letters. The first nine carry an ALT label, and the rail reads ALT + NUMBER TO APPLY. The shortcut works while you are writing in the editor or when nothing else has focus, never while you type in another field. The number pad is left alone, so Windows Alt codes such as Alt+0149 for a bullet still type their character. On a Mac, Option and a number types a symbol, so there is no shortcut and the labels are not shown; click the specimen instead.
3. The specimen replaces your opening paragraph.

Your opening paragraph is everything up to the first blank line. A line that holds only spaces, or the blank spacer character people paste from LinkedIn, counts as blank. If your draft has no blank line, the specimen replaces the whole draft. If the editor is empty, the specimen becomes the draft.

> [!NOTE]
> After a hook replaces your opening, the rail reads **OPENING REPLACED** with an **UNDO** button. Press it to put your own opening back. It stays while the hook is still your first line, and it brings back your words even if you tried several hooks in a row. Ctrl+Z does not undo a hook.

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
| EDITOR'S RATING | Engineering pack forms | A rating typed into the library by whoever wrote the form, not a measurement. Starter forms show no number |
| No score | Generated hooks | Generated hooks show no number, only the fold verdict below |
| FITS FOLD | Generated hooks | The hook's first line is 140 characters or fewer and the whole hook is 240 or fewer |
| PAST FOLD | Generated hooks | The hook fails that length check |

This check is not the same as the 140 character fold mark in the editor, which measures the whole post as a reader sees it. The editor's rating and the fold verdict are the studio's own judgements, not LinkedIn measurements. Library forms carry no fold verdict.

## What happens

- The hook rail reads the library in the local database. Nothing leaves the machine.
- **Re-Hook** with no AI provider configured builds the ten hooks from local templates on this PC. It takes a subject from the first line of your selection and fills it into ten fixed patterns.
- **Re-Hook** with an AI provider configured sends a prompt to that provider. The prompt contains a subject taken from the first line of your selection, not the whole post. If the call fails or the reply cannot be read, the studio falls back to the local templates without saying so.

See [Connect your own AI provider](connect-your-own-ai-provider.md) and [What leaves this machine, and when](what-leaves-this-machine.md).

## What the forms are, and are not

These are hook forms, not posts anyone measured. The library stores patterns:
a form with a bracketed blank for you to fill, such as `[Number] years of
[your work] taught me one thing about [topic]:`. No reaction or comment count
is shown for one, because none was ever read for one.

A rating on a form was typed in by whoever wrote it. The studio shows it as
an editor's rating, never as a measurement, and a form with no rating shows
none rather than a zero.

To search the whole library rather than the twelve in the rail, press
**Ctrl+K** (**Cmd+K** on a Mac) and type a word from a form. Choosing one
opens the Composer, where the rail applies it. See
[Search everything with Ctrl+K](use-the-command-palette.md).

## If it does not work

| What you see | What it means |
| --- | --- |
| HOOK LIBRARY UNAVAILABLE | The rail could not reach the server. Reload the page. If it persists, see [The studio will not open or shows an error](the-studio-will-not-open.md) |
| NO HOOKS IN THE LOCAL LIBRARY YET | The server returned no forms. The studio refills an empty library with the 12 starter forms each time it reads it, so this usually means the database could not be read. Reload the page, then restart the studio if it persists |
| LOADING HOOKS stays | The server is slow or stopped |
| Re-Hook seems to do nothing | The request failed. No error is shown, and if generated hooks were on the rail it returns to the library. Check that text is actually selected (a selection of only spaces is ignored), then try again |

Pulling new hook forms from an online bundle is not available from the interface.
