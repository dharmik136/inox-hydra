# Use the Queue to plan your posting times
See your weekly slots and scheduled posts, keep 12 hours between posts, and learn what happens at a scheduled time.

> [!IMPORTANT]
> The Queue never posts to LinkedIn. At a scheduled time it only changes the post's status on this machine, so you still post the text yourself. Only [Send to LinkedIn](publish-queue-or-send-to-linkedin.md) hands a post to LinkedIn.

## Read the Queue

Open **Queue** in the rail. The top row shows:

| Figure | Meaning |
| --- | --- |
| **Scheduled** | How many posts have the status scheduled |
| **Cadence health** | 100% with no collisions, otherwise 100 minus 25 for each collision, never below 20% |
| **Collisions** | Pairs of scheduled posts less than 12 hours apart |
| **Closest spacing** | The smallest gap between two scheduled posts, in hours. Reads Not measured with fewer than two scheduled posts |

**Next slot** shows the day, time and label of the next free slot, then either `12H CLEAR OF THE LAST POST` or `ONLY 6H SINCE THE LAST POST` (with your own figures). The hours are the distance to the nearest scheduled or published post.

**Weekly slots** shows a card per day with each slot's time and label, or None. **Scheduled posts** lists every scheduled post, earliest time first, with its time and first line, or NOTHING IS SCHEDULED.

To add a post, use **Publish** then **Queue it** on the Composer.

## The 12-hour rule

A time is a collision when it falls within 12 hours of another scheduled post or of a post marked published. When the studio picks the next slot, it looks ahead 14 days, skips slots less than 15 minutes away, and skips any slot that collides. If every slot collides, it offers a time 24 hours from now, labelled "24-Hour Buffer Slot (still inside the cooldown)" when that is still too close. A collision is a warning, not a block.

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

While the studio server is running, it checks the queue every 30 seconds. For each scheduled post whose time has come:

- **Up to 120 minutes late:** its status becomes published in the local database, stamped with the time of the check. Nothing is posted.
- **More than 120 minutes late** (for example, the studio was closed): it moves to the next free slot and stays scheduled.

The Queue page does not refresh itself. Leave it and come back to see changes.

Posts you sent with **Send to LinkedIn** are listed here too, and are marked published locally at their time. If the studio was closed for more than 2 hours past that time, the local record moves to a new slot, even if LinkedIn has already published the post.

## Run due posts

1. Open **Queue**.
2. Press **Run due posts**.
3. Read the note below the buttons: for example 1 ACTION TAKEN, or NOTHING WAS DUE. Each post marked published or moved counts as one action.

## Pause publishing and Resume publishing

Press **Pause publishing**. The studio stores the setting, reads it back, and shows AUTOMATED PUBLISHING IS PAUSED. SCHEDULED POSTS WILL NOT GO OUT. The button becomes **Resume publishing**.

While paused, the 30-second check skips every post and **Run due posts** reports NOTHING WAS DUE even when posts are due. Pausing does not stop a post already handed to LinkedIn; LinkedIn publishes it. The banner's "will not go out" overstates things: nothing goes out from the local queue, paused or not. When you resume, posts more than 2 hours overdue move to the next slot.

## What the Queue cannot do

The Queue page has no controls to add, edit or remove slots, or to reschedule or unschedule a post. The rows are not clickable. The only way to move a queued post is to open it on the Composer and press **Publish** then **Queue it** again, which puts it at the NEXT SLOT shown then.

## If it does not work

| You see | What it means |
| --- | --- |
| QUEUE UNAVAILABLE | The studio server did not answer. See [The studio will not open or shows an error](the-studio-will-not-open.md). |
| THE DISPATCH RUN WAS REFUSED | The server rejected **Run due posts**. Try again, then check the server is running. |
| Scheduled posts times look hours off | That list shows stored times in UTC. Slots and **Next slot** are local time, so they differ by your UTC offset. |
| A post moved to a later slot | It was more than 2 hours late when the studio checked it, usually because the studio was closed. |
| `H CLEAR OF THE LAST POST` with no number | There is no scheduled or published post within about 900 hours (37 days) of the slot to measure against. |
| A post shows as published but is not on LinkedIn | Expected. The Queue records a status; post the text yourself. |
