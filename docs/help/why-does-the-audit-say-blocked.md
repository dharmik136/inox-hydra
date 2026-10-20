# Why does the Audit tab say WORTH A LOOK?
Match each message under Checks to its cause and fix, and learn why WORTH A LOOK never stops you posting.

## Short answer

WORTH A LOOK is advice. It does not stop you doing anything. **Publish** in the Composer, and **Copy and mark posted**, **Queue it** and **Send to LinkedIn** in the dialog it opens, never run the checks. The queue does not check them either. You can post a draft that reads WORTH A LOOK, and a draft that reads ALL CLEAR gets no special treatment. Older versions of the studio said BLOCKED here, and meant the same thing.

The **Checks** section sits at the bottom of the inspector's **Audit** tab, below the Distribution audit. With nothing in the Composer, the tab reads NOTHING TO AUDIT YET and runs no checks. For how to open the inspector and read the rest of the tab, see [Check a draft before you post](check-a-draft-before-you-post.md).

## What the checks are

They are six fixed text rules. No person reviews your draft and no AI model is called. The studio's own server on this machine runs the rules against the text in the editor. The table below numbers them 1 to 6; the tab shows only each message.

## Read the count

The header shows how many of the six checks pass, such as 4 OF 6 PASS, then ALL CLEAR or WORTH A LOOK. It counts checks, not messages: check 1 can show two messages and still counts as one.

| Checks passing | Header |
| --- | --- |
| 6 | 6 OF 6 PASS, ALL CLEAR, and the section reads ALL SIX CHECKS PASS |
| 5 or fewer | *n* OF 6 PASS, WORTH A LOOK, then a message for each rule the draft breaks |

Check 6 always passes.

## Message, cause and fix

In the table, *n* stands for the number the message shows.

| Check | Message | Cause | Fix |
| --- | --- | --- | --- |
| 1 | Detected *n* illegal em-dash characters (U+2014). | The draft contains em dashes | Select the text and choose **Clean formatting**, or replace them by hand |
| 1 | Detected generic AI buzzword slop. | The whole word game-changer, revolutionary, synergistic or supercharge, in any case | Reword it |
| 2 | Content is too short for algorithmic authority (<50 characters). | Fewer than 50 characters | Add text |
| 2 | Content exceeds LinkedIn maximum length bounds (>3000 characters). | More than 3,000 characters | Cut it below 3,000 |
| 3 | First line hook (*n* chars) exceeds mobile 140-char limit. | The first line is over 140 characters | Shorten the first line, or break it |
| 3 | Pre-fold text (*n* chars) exceeds mobile fold 210-char threshold. | The first three lines together are over 210 characters | Shorten the opening lines |
| 4 | Content lacks paragraph structure (monolithic block of text). | The draft has no line break at all | Press Enter somewhere to split it |
| 5 | Potential credentials or secret keys detected in text payload. | The text contains `li_at=`, `session_key=`, `bot_token=` or `api_key=` followed by a value in quotes | Remove it. If it was a real credential, treat it as exposed and replace it |

## Things that surprise people

- **Short posts can fail check 3 on their whole length.** When the draft has fewer than three lines, check 3 measures the entire post as pre-fold text. A two-line post of 250 characters fails.
- **A post with no line break fails check 4**, and usually check 3 as well, because check 3 then measures the whole post.
- **Check 2's limit is lower than the save limit.** The studio saves posts of up to 5,000 characters, so a post between 3,001 and 5,000 characters saves, and the studio lets you publish or queue it, while it reads WORTH A LOOK.
- **Check 1 counts only em dashes.** En dashes do not trip it, though the Distribution audit's dash penalty flags them.
- **Check 3 is not the Preview fold.** The Mobile preview cuts the whole post at 140 characters, counted as a reader sees them. Check 3 checks the first line against 140 and the first three lines against 210, in raw characters, so the two can disagree.
- **Formatting marks count.** Checks 2 and 3 count raw characters, so the marks that **Underline** and **Strikethrough** add push the counts up.

## What happens

While the **Audit** tab is open, the checks re-run about 0.7 seconds after you stop typing, on the text in the editor, including unsaved changes. The text goes only to the studio's own server at `127.0.0.1:8000`. Nothing leaves your computer and nothing is saved.

## If it does not work

| You see | What it means |
| --- | --- |
| No Checks section | That request failed on its own. The Distribution audit above it still works. Change the draft, or switch to another inspector tab and back, so the checks run again; if the section stays missing, see [The studio will not open](the-studio-will-not-open.md). |
| AUDIT UNAVAILABLE | The Distribution audit request failed, so the tab shows nothing else, checks included. See [Check a draft before you post](check-a-draft-before-you-post.md). |
