# Start a new post, or find one you wrote earlier
See which post the Composer opens, how to start a fresh one without losing the last, and where older posts still appear.

## Which post the Composer opens

When you open or reload the studio, the **Composer** asks the local database for every post with the status draft and opens the one you *created* most recently. That is not necessarily the one you edited last: saving an older draft again does not move it to the front.

- If you start typing before the draft arrives, the Composer keeps what you typed and does not load the draft over it.
- If there is no draft, or the request fails, the Composer opens empty. Your first **Save** then creates a new post.

Your text is held in the page while you work. Switching to another surface in the rail, such as **Queue** or **Leads**, and coming back keeps it. Reloading or closing the tab does not: there is no autosave and no warning before you leave, so anything marked UNSAVED is lost.

## Start a new post

The top bar on the Composer has only **Save** and **Publish**. There is no New draft button.

1. If the post in the editor is finished, press **Publish** and choose **Mark as published**, **Queue it** or **Send to LinkedIn**. Each one moves the post out of the draft list. See [Publish, queue or send a post to LinkedIn](publish-queue-or-send-to-linkedin.md).
2. Reload the page.
3. The Composer opens your most recent remaining draft, or opens empty if none is left.

For what **Save** does and the marks beside it, see [Write, format and save a post](write-format-and-save-a-post.md).

> [!WARNING]
> Do not skip the reload. After **Publish**, the Composer is still attached to the post you just recorded or queued. If you type and press **Save**, you overwrite that post's text.

> [!CAUTION]
> Do not use **Mark as published** just to clear the editor. It records the post as published, and it then appears in **Analytics** as one of your published posts.

## Keep one draft and start another

The interface cannot hold two drafts side by side. The Composer works on one post at a time, and pressing **Save** after you have opened a draft writes the new text over that same draft. It never creates a second one.

If you want to keep a draft and write something different, copy its text somewhere outside the studio first, or take an export (below) so the full text is on disk.

## Find an earlier post

No surface reopens an older post in the Composer. You can still read your posts in these places:

| Where | What you see | Which posts |
| --- | --- | --- |
| **Queue**, under **Scheduled posts** | The scheduled date and time, and the first line of each post | Scheduled only |
| **Analytics**, under **Post comparison** | The first line of each post with its numbers | Published only |
| **Brand Studio** > **Local security** > **Your data**, **Export JSON** or **Export CSV** | The full text of every post, whatever its status | All, including drafts |

The exports are written to the studio's home folder on this machine, and the path is shown under the buttons when the export finishes. See [Back up, restore and export](back-up-restore-and-export.md).

## What happens

- Posts are never deleted from the interface. Every post you have saved stays as a row in the local database, whatever its status.
- Those rows are included in every backup and every export.
- Nothing in this article sends anything off the machine except **Send to LinkedIn**, which is covered in its own article.

## If it does not work

| What you see | What it means |
| --- | --- |
| "There is nothing written to save." (hover over SAVE FAILED) | The editor is empty. Type something before you press **Save**. |
| "Post content exceeds maximum 5,000 character limit." | The server refuses to save a post over 5,000 characters, whether it is new or already saved. Shorten it and save again. |
| Your text is gone after a reload | It was never saved. The mark read UNSAVED when you reloaded, and there is no way to recover it. |
| The Composer opened an older draft than you expected | It opens the draft created most recently, not the one edited most recently. Use **Publish** on drafts you are finished with so they leave the draft list. |
| The Composer opened empty although you have drafts | The request for the draft failed. Reload the page. If it keeps happening, see [The studio will not open](the-studio-will-not-open.md). |
