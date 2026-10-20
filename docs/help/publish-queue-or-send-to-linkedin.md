# Publish, queue or send a post to LinkedIn
Learn what Copy and mark posted, Queue it and Send to LinkedIn each do, and which one sends anything.

## Before you start

- **Publish saves first.** Publishing acts on the saved post, so **Publish** saves what is in the editor before the dialog opens, whenever the strip reads UNSAVED or SAVE FAILED. If that save is refused, the dialog does not open: the strip reads SAVE FAILED, and hovering over it shows why.
- **For Send to LinkedIn only:** you need a confirmed identity in Setup, a LinkedIn session synced from the extension after you opened your own LinkedIn profile in that browser (see [Connect your LinkedIn session](connect-your-linkedin-session.md)), and `INOX_ALLOW_LINKEDIN_EGRESS=1` must be set before the studio server starts. `launch_studio.bat` does not set it. First stop the server: when `launch_studio.bat` started it, it runs in a minimised window titled **Inox Hydra Backend**, so close that window. Then open Command Prompt, run `set INOX_ALLOW_LINKEDIN_EGRESS=1`, and start `launch_studio.bat` from that same window. If a server is still running on port 8000, the launcher reuses it and the setting does not reach it.

## Open the dialog

1. On the **Composer**, press **Publish** at the right of the status strip at the top.
2. Check the first line of the post at the top of the dialog. Every choice acts on that post.
3. Read the **NEXT SLOT** box: the date, time and name of the next free slot. **Queue it** and **Send to LinkedIn** both use this time. There is no time picker; to change the times on offer, change your weekly slots on the Queue (see [Use the Queue to plan your posting times](how-the-queue-works.md)).
4. If the box shows orange text about a collision, that slot is inside the 12-hour spacing rule. It is a warning, and the buttons still work. If the orange text is an error instead, such as SCHEDULED TIME MUST BE IN THE FUTURE., **Queue it** and **Send to LinkedIn** are greyed out.
5. Press **Cancel** or `Esc` to close without doing anything.

## The three choices

| | Copy and mark posted | Queue it | Send to LinkedIn |
| --- | --- | --- | --- |
| What it does first | Copies the post's exact text to your clipboard | Nothing else | Asks you to confirm the account and the time |
| What it writes on this machine | Status published, with the current time, only once the copy worked | Status scheduled, at the NEXT SLOT time; due when that time comes | Status scheduled at the NEXT SLOT time, only after LinkedIn accepts; published when that time comes |
| What leaves the machine | Nothing | Nothing | The post text and your stored session cookies, sent to LinkedIn |
| Can you undo it here? | No | No unschedule control; **Pause the queue** on the Queue holds it, and **Back to drafts** takes a due post off it | No. Change or cancel it on LinkedIn |

The dialog itself says of the first two: NEITHER OF THOSE TWO SENDS ANYTHING. BOTH WRITE TO THIS MACHINE ONLY.

## Post it now: Copy and mark posted

**Copy and mark posted** is the orange button, the main action.

1. Press **Publish**, then **Copy and mark posted**. The studio copies the post's exact text, formatting included, to your clipboard, and then records the post as posted by you, now.
2. The strip shows COPIED AND MARKED AS POSTED, and the Composer clears for your next post.
3. Open LinkedIn, start a post, paste, and post it. The studio does not post it for you.

The post now counts toward the 12-hour spacing rule, and appears in **Analytics**. When the bridge later sees it on LinkedIn, it is linked to the LinkedIn post.

If the browser refuses the copy, nothing is recorded, and the dialog says so. Copy the text from the editor yourself (press **Copy** in the top bar, or select it), then press **Mark posted without copying**.

To copy the text without recording anything, press **Copy** in the Composer's top bar. The button reads Copied when the text is on your clipboard.

## Queue it

Press **Queue it**, beside **Copy and mark posted**. The strip shows the time, for example QUEUED FOR MON 26 OCT, 08:30. At that time the post moves to **Due, waiting for you to post it** on the Queue, for you to post yourself; it is recorded as published only when you press **I posted it** there. The queue does not post it. See [Use the Queue to plan your posting times](how-the-queue-works.md).

## Send to LinkedIn

> [!WARNING]
> This is the only control that sends to your real LinkedIn account. The studio's own tests check it against a stand-in for LinkedIn, not the real one, so treat your first send as a test: send a post you are happy to see, then check your scheduled posts on LinkedIn.

1. Press **Publish**.
2. Check **NEXT SLOT**. The request asks LinkedIn to publish at that time. It must be at least 10 minutes and at most about three months away.
3. Below the line, read which account it sends as, for example "Sends as Rae Six (linkedin.com/in/rae-six)." If **Send to LinkedIn** is greyed out, the sentence under it says why and what to do (see the table below).
4. Press **Send to LinkedIn**.
5. Read the question: "Send as <your name> (linkedin.com/in/<you>), for LinkedIn to publish at <date and time> (this computer's time)?" and, in orange, "This sends the post's text to LinkedIn, signed in with your saved LinkedIn session. It cannot be undone from here: after this, changing it means going to LinkedIn."
6. Press **Yes, send as <your name>**, or **Keep it here** to back out.

### The account it sends as

The extension learns which LinkedIn account is signed in to its browser, and that account's member id, when you open your own profile there. It sends both with the session when you press **Sync LinkedIn Session**. The studio sends only as that account, only when it is the account you confirmed in Setup, and names that member id as the post's author. If the session changes to another account after the dialog opened, nothing is sent and the dialog asks you to open it again.

### The record of each send

Every send of a post is recorded on this machine: when, as which account, the exact request sent (the text, the author, the time), and LinkedIn's answer. The dialog shows the last one, for example LAST SEND TUE 20 OCT, 14:02: LINKEDIN REFUSED IT (HTTP 422). The record is read through `GET /api/v1/posts/<post id>/linkedin-send`.

## What happens

**Copy and mark posted** and **Queue it** change one row in the studio's local database and open no connection. The copy is to your own clipboard.

**Send to LinkedIn** reads the text from the saved post, which **Publish** has just saved from the editor. It then sends one request to LinkedIn's `contentcreation/normShares` endpoint with the text, your member id as the author, the slot time, public visibility and a scheduled state, authenticated with your stored `li_at` and `JSESSIONID` cookies. No images are sent. The request asks LinkedIn to hold the post and publish it at that time, so publishing would not depend on your computer being awake. Only after LinkedIn accepts does the local post become scheduled, and the strip shows LINKEDIN IS HOLDING THIS POST AND WILL PUBLISH IT AT THE SCHEDULED TIME. Later edits in the studio, and pausing the Queue, do not reach LinkedIn.

After any of the three, the Composer lets go of the post and clears, so the next post you type is saved as a new one. Your other drafts stay in **Drafts** (see [Start a new post, or find one you wrote earlier](start-a-new-post-or-find-an-earlier-one.md)). A queued post is listed on the **Queue**, and a published one in **Analytics**.

## If it does not work

| The dialog shows | What to do |
| --- | --- |
| SAVE FAILED in the strip, and no dialog opens | The save before publishing was refused. Hover over SAVE FAILED for the reason, for example "There is nothing written to publish." or the 5,000 character limit, fix it, and press **Publish** again. |
| Post is already published | This post was marked as posted earlier, by you or, for a post sent to LinkedIn, at its scheduled time. Nothing more to do. |
| This browser did not allow copying, so nothing was recorded. | The clipboard refused. Copy the text yourself, then press **Mark posted without copying**. |
| Nothing can be sent: this studio has no saved LinkedIn session... | Sync a session from the extension, then try again. See [Connect your LinkedIn session](connect-your-linkedin-session.md). |
| The saved session does not say which LinkedIn account it is... | The session was pasted, or synced by an older extension. Open your own LinkedIn profile in the bridge browser, then press **Sync LinkedIn Session**. |
| The saved session is for linkedin.com/in/..., but this studio is set up for... | That browser is signed in to LinkedIn as someone else. Sign in as yourself, open your profile, and sync again. |
| The studio does not know your LinkedIn member id yet... | Open your own LinkedIn profile in the bridge browser, wait for it to load, then press **Sync LinkedIn Session**. |
| Sending to LinkedIn is switched off in this studio... | Start the studio with `INOX_ALLOW_LINKEDIN_EGRESS=1`, as in **Before you start**. |
| Nothing was sent. The confirmation did not name ... | The session changed account after the dialog opened. Close **Publish** and open it again. |
| That time is less than 10 minutes away... or LinkedIn holds a post for up to about three months ahead... | The slot is outside the window LinkedIn accepts. Nothing was sent. Choose another slot on the Queue, or post it yourself with **Copy and mark posted**. |
| LinkedIn refused the post (HTTP 422: ...) | LinkedIn read the request and said no; its own reason follows the status. Nothing was scheduled, and the attempt is in the post's send record. |
| LinkedIn will not hold a post for a time that has passed. | The dialog was open past the slot time. Close it and open it again. |
| This post has no content to send. | The saved post is empty. Write, **Save**, and try again. |
| A sentence naming `INOX_ALLOW_LINKEDIN_EGRESS`, the circuit breaker, "LinkedIn refused the post (HTTP ...)" or "The studio could not reach LinkedIn" | Nothing was scheduled. The request was refused before sending, could not reach LinkedIn, or LinkedIn rejected it. Likely causes: `INOX_ALLOW_LINKEDIN_EGRESS=1` was not set when the server started, `INOX_NO_EGRESS=1` is set, the safety breaker is open (it opens at once on a 401 or 403 from LinkedIn, or after 3 failures in a row, and then pauses LinkedIn requests for 5 minutes), or LinkedIn refused the post, for example because the session expired. |
| The post was sent, but LinkedIn did not answer within 10 seconds... | LinkedIn may already be holding the post. Open your scheduled posts on LinkedIn and look for it before doing anything else. The studio does not mark it as scheduled. |
| An earlier send of this post ... got no answer from LinkedIn... | The studio holds back a second send of a post whose first send went unanswered, so it cannot be scheduled twice by accident. If the post is not in your scheduled posts on LinkedIn, press **It is not on LinkedIn, send it again**. |
| **Queue it** and **Send to LinkedIn** are greyed out | The next slot could not be loaded, for example because the server stopped, or the slot failed the time check. Close the dialog and check the [Queue](how-the-queue-works.md). |
