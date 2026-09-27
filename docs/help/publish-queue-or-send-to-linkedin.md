# Publish, queue or send a post to LinkedIn
Learn what Mark as published, Queue it and Send to LinkedIn each do, and which one sends anything.

## Before you start

- **Save the draft.** Publishing acts on the saved post. If the draft has never been saved, **Publish** saves it first. If it was saved earlier and the strip now reads UNSAVED, your latest edits are not included, so press **Save** before **Publish**.
- **For Send to LinkedIn only:** you need a stored LinkedIn session (see [Connect your LinkedIn session](connect-your-linkedin-session.md)), and `INOX_ALLOW_LINKEDIN_EGRESS=1` must be set before the studio server starts. `launch_studio.bat` does not set it. First stop the server: when `launch_studio.bat` started it, it runs in a minimised window titled **LinkedIn Studio Backend**, so close that window. Then open Command Prompt, run `set INOX_ALLOW_LINKEDIN_EGRESS=1`, and start `launch_studio.bat` from that same window. If a server is still running on port 8000, the launcher reuses it and the setting does not reach it.

## Open the dialog

1. On the **Composer**, press **Publish** at the right of the status strip at the top.
2. Read the **NEXT SLOT** box: the day, time and label of the next free slot. **Queue it** and **Send to LinkedIn** both use this time. There is no time picker.
3. If the box shows orange text about a collision, that slot is inside the 12-hour spacing rule. It is a warning, and the buttons still work. If the orange text is an error instead, such as SCHEDULED TIME MUST BE IN THE FUTURE., **Queue it** and **Send to LinkedIn** are greyed out.
4. Press **Cancel** or `Esc` to close without doing anything.

## The three choices

| | Mark as published | Queue it | Send to LinkedIn |
| --- | --- | --- | --- |
| What it writes on this machine | Status published, with the current time | Status scheduled, at the NEXT SLOT time | Status scheduled at the NEXT SLOT time, only after LinkedIn accepts |
| What leaves the machine | Nothing | Nothing | The post text and your stored session cookies, sent to LinkedIn |
| Can you undo it here? | No | No unschedule control; **Pause publishing** on the Queue holds it | No. Change or cancel it on LinkedIn |

The dialog itself says of the first two: NEITHER OF THOSE TWO SENDS ANYTHING. BOTH WRITE TO THIS MACHINE ONLY.

## Record a post you published yourself

1. Post the text on LinkedIn yourself.
2. In the studio, press **Publish**, then **Mark as published**.

The strip shows MARKED AS PUBLISHED. The post now counts toward the 12-hour spacing rule.

## Queue it

Press **Queue it**. The strip shows the time, for example SCHEDULED FOR MONDAY 08:30. At that time the local queue marks the post as published on this machine. It does not post it. See [Use the Queue to plan your posting times](how-the-queue-works.md).

## Send to LinkedIn

> [!WARNING]
> This is the only control that sends to your real LinkedIn account. It is experimental: the studio's own tests check it against a stand-in, not the real LinkedIn. The studio does not store your LinkedIn member id, so the request names a placeholder author, and LinkedIn may reject it. Check your scheduled posts on LinkedIn afterwards.

1. Press **Save**, then **Publish**.
2. Check **NEXT SLOT**. The request asks LinkedIn to publish at that time.
3. Press **Send to LinkedIn**, below the line.
4. Read the orange text: "This sends the post to LinkedIn for <day> <time>. It cannot be undone from here: after this, changing it means going to LinkedIn."
5. Press **Yes, send it to LinkedIn**, or **Keep it here** to back out.

## What happens

**Mark as published** and **Queue it** change one row in the studio's local database and open no connection.

**Send to LinkedIn** reads the text from the saved post, not from the editor. It then sends one request to LinkedIn's `contentcreation/normShares` endpoint with the text, the slot time, public visibility and a scheduled state, authenticated with your stored `li_at` and `JSESSIONID` cookies. No images are sent. The request asks LinkedIn to hold the post and publish it at that time, so publishing would not depend on your computer being awake. Only after LinkedIn accepts does the local post become scheduled, and the strip shows LINKEDIN IS HOLDING THIS POST AND WILL PUBLISH IT AT THE SCHEDULED TIME. Later edits in the studio, and pausing the Queue, do not reach LinkedIn.

After any of the three, the Composer still holds the same post, and the next **Save** overwrites it. To start a new post, reload the page. The Composer reopens your newest remaining draft, or opens empty.

## If it does not work

| The dialog shows | What to do |
| --- | --- |
| Save the draft first. Publishing acts on a stored post... | Write something, press **Save**, then **Publish**. |
| Post is already published | This post was marked as published earlier, by you or by the Queue at its scheduled time. Nothing more to do. |
| Nothing was sent. This studio has no saved LinkedIn session... | Store a session, then try again. See [Connect your LinkedIn session](connect-your-linkedin-session.md). |
| LinkedIn will not hold a post for a time that has passed. | The dialog was open past the slot time. Close it and open it again. |
| This post has no content to send. | The saved post is empty. Write, **Save**, and try again. |
| 502 | Nothing was scheduled. The request was refused before sending, could not reach LinkedIn, or LinkedIn rejected it. Likely causes: `INOX_ALLOW_LINKEDIN_EGRESS=1` was not set when the server started, `INOX_NO_EGRESS=1` is set, the safety breaker is open (it opens at once on a 401 or 403 from LinkedIn, or after 3 failures in a row, and then pauses LinkedIn requests for 5 minutes), or LinkedIn refused the post, for example because the session expired. |
| **Queue it** and **Send to LinkedIn** are greyed out | The next slot could not be loaded, for example because the server stopped, or the slot failed the time check. Close the dialog and check the [Queue](how-the-queue-works.md). |
