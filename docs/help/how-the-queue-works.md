# Use the Queue to plan your posting times
See your weekly slots and scheduled posts, keep 12 hours between posts, and learn what happens at a scheduled time.

> [!IMPORTANT]
> The Queue never posts to LinkedIn. At a post's time it moves the post to **Due, waiting for you to post it**, at the top of the Queue, and you post the text yourself. Only [Send to LinkedIn](publish-queue-or-send-to-linkedin.md) hands a post to LinkedIn.

## Read the Queue

Open **Queue** in the rail. The top row shows:

| Figure | Meaning |
| --- | --- |
| **Queued** | How many posts are queued and not yet due |
| **Collisions** | Pairs of scheduled posts less than 12 hours apart |
| **Closest spacing** | The smallest gap between two scheduled posts, in hours. Reads Not measured with fewer than two scheduled posts |
| **Slots a week** | How many weekly slots are switched on |

**Against your own rhythm** sets those slots beside how you have actually posted, measured from the posts the studio holds:

| Line | Meaning |
| --- | --- |
| **Posts read** | How many of your posts the studio holds |
| **Your usual gap** | The median gap between your posts, for example 0.9 days between posts |
| **Since your last** | How long since your newest post |
| **These slots** | The gap your slots ask for, for example one post every 1.4 days, with a sentence saying whether that is more, less or about what you have kept |
| **Longest gap** | Your longest gap between two posts, with its dates |
| **Next 14 days** | How many posts are queued in the next 14 days, against the slots those two weeks hold |

Under them, **POSTS BY MONTH** draws one bar per month and says how many posts the tallest bar stands for, and **POSTS BY WEEKDAY** counts your posts by the day they went out. No best day or time is named: you chose the days you posted on, and a few posts per day cannot separate the day from everything else about those posts. Any line the studio cannot measure, such as a gap with only one post, reads Not measured.

**Next slot** shows the day, time and label of the next free slot, then either `12H CLEAR OF THE LAST POST` or `ONLY 6H SINCE THE LAST POST` (with your own figures). The hours are the distance to the nearest scheduled or published post.

**Due, waiting for you to post it** lists every post whose time has come, with DUE and its time, its first line, **Copy text** and **I posted it**, or NOTHING IS DUE.

**Weekly slots** shows a card per day with each slot's time and label, or None. **Queued posts** lists every queued post, earliest time first, with its time in this computer's local time and its first line, or NOTHING IS QUEUED.

To add a post, use **Publish** then **Queue it** on the Composer, or press **Queue the newest draft** under **Drafts waiting**.

**Drafts waiting** says how many drafts you have saved and gives the first line of the newest. **Queue the newest draft** puts that one in the next slot the Queue offers, through the same check **Queue it** uses: the next of your slots at least 12 hours from your other posts, or, when none is, a time 24 hours ahead. The sentence under the heading says which time it chose, and when that time is inside your 12-hour cooldown. It moves the post only if it is still a draft at that moment: if it was queued or published since the screen last read it, the studio leaves it as it is, says so, and reads the block again. The drafts themselves are listed once, under **Drafts** in the Composer. If the count could not be read, the block says so instead of reporting no drafts.

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

Each is named after its day and the part of the day, such as Monday morning or Thursday evening. A studio that started with the older names (such as Monday Morning Kickoff) is renamed the same way, unless you had renamed a slot yourself.

## Change your weekly slots

1. Open **Queue** and find **Weekly slots**.
2. Press **Change slots**. Each slot is listed with its day, its time and its name.
3. To change a slot, edit its time or its name, then press **Save** on its row. A name left empty is filled in from the day and the part of the day.
4. To remove a slot, press the bin button on its row.
5. To add a slot, choose a day and a time at the bottom, type a name if you want one, and press **Add slot**. Two slots on the same day at the same time are refused.
6. Press **Done**.

Times are this computer's local time. Posts already queued keep their times when you change or remove a slot. **Queue it** in **Publish** then offers the next of your slots that is clear of the 12-hour rule. If you remove every slot, it offers a time 24 hours ahead instead.

## What happens at a scheduled time

While the studio server is running, it checks the queue every 30 seconds. For each queued post whose time has come:

- **Up to 120 minutes late:** it becomes due and moves to **Due, waiting for you to post it**. It is not recorded as published, and it does not appear on **Posts**. Nothing is posted.
- **More than 120 minutes late** (for example, the computer was asleep or the studio was closed): it becomes due at its own time and is marked as missed. Nothing moves it to another time. **Today** shows it first, in a box headed A POST WAS MISSED, with the time it was due and two choices:
  - **Post now** copies the post's exact text to your clipboard and records it as posted by you now. Paste it into LinkedIn and post it there; the studio does not post it.
  - **Move to next slot** puts it back in the queue at the next free slot, and Today says which time.

The Queue page does not refresh itself. Leave it and come back to see changes.

Posts you sent with **Send to LinkedIn** are listed here too. LinkedIn publishes those itself, so at their time they are recorded as published at that time, never as due, even if the studio was closed then.

## Post a due post

1. Open **Queue**. The post is under **Due, waiting for you to post it**.
2. Press **Copy text**, paste it into LinkedIn and post it.
3. Press **I posted it**. The post is recorded as published now, and appears on **Posts**.

**Today** shows the same post first, in a box headed A POST IS DUE, with **Copy text** and **I posted it**, so you see it when you open the studio.

If you decide not to post it, press **Back to drafts** instead. It leaves the Queue with its text kept, and you can open it again from search (**Ctrl+K**).

If you open the post on LinkedIn with the bridge running, it is linked to its LinkedIn post and recorded as published even if you skip step 3.

## Check for due posts

1. Open **Queue**.
2. Press **Check for due posts**.
3. Read the note below the buttons: for example 1 POST MARKED DUE, or NOTHING WAS DUE.

## Pause the queue and Resume the queue

Press **Pause the queue**. The studio stores the setting, reads it back, and shows THE QUEUE IS PAUSED. QUEUED POSTS STAY QUEUED AND ARE NOT MARKED DUE UNTIL YOU RESUME IT. The button becomes **Resume the queue**.

While paused, the 30-second check skips every post and **Check for due posts** reports NOTHING WAS DUE even when posts are due. Pausing does not stop a post already handed to LinkedIn; LinkedIn publishes it. When you resume, posts more than 2 hours overdue become due at their own time, marked as missed, as above.

## What the Queue cannot do

The Queue page has no control to reschedule or unschedule one queued post; a missed post can be moved with **Move to next slot** on **Today**. To fix the text of a queued post, press **Edit text** on its row. The post opens in the Composer with a line under the bar saying you are editing a queued post; **Save** asks before it changes that post's text, and the post stays at its time in the queue. **Save as a new draft** keeps the queued post as it was and saves your text as a separate draft.

## If it does not work

| You see | What it means |
| --- | --- |
| QUEUE UNAVAILABLE | The studio server did not answer. See [The studio will not open or shows an error](the-studio-will-not-open.md). |
| A sentence below the buttons after **Check for due posts** | The server refused the check, and the sentence says why. Try again, then check the server is running. |
| A post shows MISSED, WAS DUE on Today | It was more than 2 hours late when the studio checked it, usually because the computer was asleep or the studio was closed. Press **Post now** or **Move to next slot**. |
| `H CLEAR OF THE LAST POST` with no number | There is no queued, due or published post within about 900 hours (37 days) of the slot to measure against. |
| A post is under Due and you already posted it | Press **I posted it**, or open the post on LinkedIn once with the bridge running. |
