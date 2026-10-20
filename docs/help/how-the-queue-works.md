# Use the Queue to plan your posting times
See your weekly slots and scheduled posts, keep 12 hours between posts, and learn what happens at a scheduled time.

> [!IMPORTANT]
> The Queue never posts to LinkedIn. At a post's time it moves the post to **Due, waiting for you to post it**, at the top of the Queue, and you post the text yourself. Only [Send to LinkedIn](publish-queue-or-send-to-linkedin.md) hands a post to LinkedIn.

## Read the Queue

Open **Queue** in the rail. The top row shows:

| Figure | Meaning |
| --- | --- |
| **Queued** | How many posts are queued and not yet due |
| **Cadence health** | 100% with no collisions, otherwise 100 minus 25 for each collision, never below 20% |
| **Collisions** | Pairs of scheduled posts less than 12 hours apart |
| **Closest spacing** | The smallest gap between two scheduled posts, in hours. Reads Not measured with fewer than two scheduled posts |

**Next slot** shows the day, time and label of the next free slot, then either `12H CLEAR OF THE LAST POST` or `ONLY 6H SINCE THE LAST POST` (with your own figures). The hours are the distance to the nearest scheduled or published post.

**Due, waiting for you to post it** lists every post whose time has come, with DUE and its time, its first line, **Copy text** and **I posted it**, or NOTHING IS DUE.

**Weekly slots** shows a card per day with each slot's time and label, or None. **Queued posts** lists every queued post, earliest time first, with its time in this computer's local time and its first line, or NOTHING IS QUEUED.

To add a post, use **Publish** then **Queue it** on the Composer.

## The 12-hour rule

A time is a collision when it falls within 12 hours of another queued or due post, or of a post marked published. When the studio picks the next slot, it looks ahead 14 days, skips slots less than 15 minutes away, and skips any slot that collides. If every slot collides, it offers a time 24 hours from now, labelled "24-Hour Buffer Slot (still inside the cooldown)" when that is still too close. A collision is a warning, not a block.

## Default weekly slots

Slot times are in this computer's local time.

| Day | Times |
| --- | --- |
| Monday to Thursday | 08:30 and 17:30 |
| Friday | 09:00 |
| Saturday | 10:30 |
| Sunday | 11:00 |

Each has a label, such as Monday Morning Kickoff.

## What happens at a scheduled time

While the studio server is running, it checks the queue every 30 seconds. For each queued post whose time has come:

- **Up to 120 minutes late:** it becomes due and moves to **Due, waiting for you to post it**. It is not recorded as published, and it does not appear in **Analytics**. Nothing is posted.
- **More than 120 minutes late** (for example, the studio was closed): it moves to the next free slot and stays queued.

The Queue page does not refresh itself. Leave it and come back to see changes.

Posts you sent with **Send to LinkedIn** are listed here too. LinkedIn publishes those itself, so at their time they are recorded as published at that time, never as due, even if the studio was closed then.

## Post a due post

1. Open **Queue**. The post is under **Due, waiting for you to post it**.
2. Press **Copy text**, paste it into LinkedIn and post it.
3. Press **I posted it**. The post is recorded as published now, and appears in **Analytics**.

**Today** shows the same post first, in a box headed A POST IS DUE, with **Copy text** and **I posted it**, so you see it when you open the studio.

If you decide not to post it, press **Back to drafts** instead. It leaves the Queue with its text kept, and you can open it again from search (**Ctrl+K**).

If you open the post on LinkedIn with the bridge running, it is linked to its LinkedIn post and recorded as published even if you skip step 3.

## Check for due posts

1. Open **Queue**.
2. Press **Check for due posts**.
3. Read the note below the buttons: for example 1 POST MARKED DUE OR MOVED TO A LATER SLOT, or NOTHING WAS DUE.

## Pause the queue and Resume the queue

Press **Pause the queue**. The studio stores the setting, reads it back, and shows THE QUEUE IS PAUSED. QUEUED POSTS STAY QUEUED AND ARE NOT MARKED DUE UNTIL YOU RESUME IT. The button becomes **Resume the queue**.

While paused, the 30-second check skips every post and **Check for due posts** reports NOTHING WAS DUE even when posts are due. Pausing does not stop a post already handed to LinkedIn; LinkedIn publishes it. When you resume, posts more than 2 hours overdue move to the next slot.

## What the Queue cannot do

The Queue page has no controls to add, edit or remove slots, or to reschedule or unschedule a post. To fix the text of a queued post, press **Edit text** on its row. The post opens in the Composer with a line under the bar saying you are editing a queued post; **Save** asks before it changes that post's text, and the post stays at its time in the queue. **Save as a new draft** keeps the queued post as it was and saves your text as a separate draft.

## If it does not work

| You see | What it means |
| --- | --- |
| QUEUE UNAVAILABLE | The studio server did not answer. See [The studio will not open or shows an error](the-studio-will-not-open.md). |
| A sentence below the buttons after **Check for due posts** | The server refused the check, and the sentence says why. Try again, then check the server is running. |
| A post moved to a later slot | It was more than 2 hours late when the studio checked it, usually because the studio was closed. |
| `H CLEAR OF THE LAST POST` with no number | There is no queued, due or published post within about 900 hours (37 days) of the slot to measure against. |
| A post is under Due and you already posted it | Press **I posted it**, or open the post on LinkedIn once with the bridge running. |
