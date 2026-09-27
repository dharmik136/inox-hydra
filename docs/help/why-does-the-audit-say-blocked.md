# Why does the Audit tab say BLOCKED?
Match each Governance gates message to its cause and fix, and learn why BLOCKED never stops you posting.

## Short answer

BLOCKED is advice. It does not stop you doing anything. **Publish** in the Composer, and **Mark as published**, **Queue it** and **Send to LinkedIn** in the dialog it opens, never run the gates. The queue does not check them either. You can post a draft that reads BLOCKED, and a draft that reads PASSED gets no special treatment.

The **Governance gates** section sits at the bottom of the inspector's **Audit** tab, below the Distribution audit. For how to open the inspector and read the rest of the tab, see [Check a draft before you post](check-a-draft-before-you-post.md).

## What the gates are

They are six fixed text rules. In the studio's code each gate is named after a role from a product-team framework: CEO & Product Strategist, Engineering Manager, Lead UI/UX Designer, QA & Verification Lead, Chief Security Officer (CSO) and Release & Ops Manager. The messages use the short form, such as CEO or Eng Manager. The roles are only labels. No person reviews your draft and no AI model is called. The studio's own server on this machine runs the rules against the text in the editor.

## Read the score

The header shows a score, then PASSED or BLOCKED. The score is the number of gates passed out of six, shown as a whole number out of 100. It counts gates, not messages: Gate 1 can show two messages and still counts as one failed gate.

| Gates passed | Score |
| --- | --- |
| 6 | 100, PASSED, and the section reads ALL SIX GATES CLEAR |
| 5 | 83, BLOCKED |
| 4 | 66, BLOCKED |
| 3 | 50, BLOCKED |

One failed gate is enough for BLOCKED. Gate 6 always passes, so the score never falls below 16.

## Message, cause and fix

In the table, *n* stands for the number the message shows.

| Message | Cause | Fix |
| --- | --- | --- |
| Gate 1 (CEO): Detected *n* illegal em-dash characters (U+2014). | The draft contains em dashes | Select the text and choose **Clean formatting**, or replace them by hand |
| Gate 1 (CEO): Detected generic AI buzzword slop. | The whole word game-changer, revolutionary, synergistic or supercharge, in any case | Reword it |
| Gate 2 (Eng Manager): Content is too short for algorithmic authority (<50 characters). | Fewer than 50 characters | Add text |
| Gate 2 (Eng Manager): Content exceeds LinkedIn maximum length bounds (>3000 characters). | More than 3,000 characters | Cut it below 3,000 |
| Gate 3 (Designer): First line hook (*n* chars) exceeds mobile 140-char limit. | The first line is over 140 characters | Shorten the first line, or break it |
| Gate 3 (Designer): Pre-fold text (*n* chars) exceeds mobile fold 210-char threshold. | The first three lines together are over 210 characters | Shorten the opening lines |
| Gate 4 (QA): Content lacks paragraph structure (monolithic block of text). | The draft has no line break at all | Press Enter somewhere to split it |
| Gate 5 (CSO): Potential credentials or secret keys detected in text payload. | The text contains `li_at=`, `session_key=`, `bot_token=` or `api_key=` followed by a value in quotes | Remove it. If it was a real credential, treat it as exposed and replace it |

## Things that surprise people

- **Short posts can fail Gate 3 on their whole length.** When the draft has fewer than three lines, Gate 3 measures the entire post as pre-fold text. A two-line post of 250 characters fails.
- **A post with no line break fails Gate 4**, and usually Gate 3 as well, because Gate 3 then measures the whole post.
- **Gate 2's limit is lower than the save limit.** The studio saves posts of up to 5,000 characters, so a post between 3,001 and 5,000 characters saves, and the studio lets you publish or queue it, while it reads BLOCKED.
- **Gate 1 counts only em dashes.** En dashes do not trip it, though the Distribution audit's dash penalty flags them.
- **Gate 3 is not the Preview fold.** The Mobile preview cuts at 180 characters. Gate 3 uses its own 140 and 210 limits, so the two can disagree.
- **Formatting marks count.** Gates 2 and 3 count raw characters, so the marks that **Underline** and **Strikethrough** add push the counts up.

## What happens

While the **Audit** tab is open, the gates re-run about 0.7 seconds after you stop typing, on the text in the editor, including unsaved changes. The text goes only to the studio's own server at `127.0.0.1:8000`. Nothing leaves your computer and nothing is saved.

## If it does not work

| You see | What it means |
| --- | --- |
| No Governance gates section | That request failed on its own. The Distribution audit above it still works. Change the draft, or switch to another inspector tab and back, so the checks run again; if the section stays missing, see [The studio will not open](the-studio-will-not-open.md). |
| AUDIT UNAVAILABLE | The Distribution audit request failed, so the tab shows nothing else, gates included. See [Check a draft before you post](check-a-draft-before-you-post.md). |
