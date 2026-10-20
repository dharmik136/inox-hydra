# Start a new post, or find one you wrote earlier
See every draft, start a new post without losing the last one, open or delete a draft, and find older posts.

## Which post the Composer opens

When you open or reload the studio, the **Composer** asks the local database for every post with the status draft and opens the one you *created* most recently. That is not necessarily the one you edited last: saving an older draft again does not move it to the front.

- If you start typing before the draft arrives, the Composer keeps what you typed and does not load the draft over it.
- If there is no draft, or the request fails, the Composer opens empty. Your first **Save** then creates a new post.

Your text is held in the page while you work. Switching to another surface in the rail, such as **Queue** or **Leads**, and coming back keeps it. There is no autosave, so reloading or closing the tab with text marked UNSAVED makes the browser ask first; if you choose to leave, that text is lost.

## Start a new post

Press **New post** in the Composer's top bar (on a narrow window it shows only its icon). The editor clears for the next post. The post you were writing stays in **Drafts** as it was last saved; if it has unsaved changes, the studio asks first, and **Cancel** keeps you on it.

Its first **Save** creates a new draft. Nothing you saved before is touched.

If you empty the editor, or select all of its text and type or paste over it, the studio does the same: the next **Save** creates a new draft, and a line under the bar says your earlier draft is kept as it was saved. Press **Write over that draft instead** on that line if you meant to rewrite it.

After **Copy and mark posted**, **Queue it** or **Send to LinkedIn**, the post leaves the drafts and the editor clears for the next one. See [Publish, queue or send a post to LinkedIn](publish-queue-or-send-to-linkedin.md). For what **Save** does and the marks beside it, see [Write, format and save a post](write-format-and-save-a-post.md).

## See every draft

1. Press **Drafts** in the Composer's top bar. A panel lists every draft, newest first, with its first line, when it was started and its length. The one open in the Composer is marked OPEN NOW.
2. To find one, type a word from it in **Find a draft**.
3. Click a draft to open it in the Composer. If the Composer holds unsaved changes, the studio asks before it discards them.
4. Press **New post** in the panel to start an empty post, or `Esc` to close the panel.

## Delete a draft

1. Press **Drafts**, then the bin button on the draft's row.
2. The studio asks, naming the draft. Press **OK** to delete it, or **Cancel** to keep it.
3. The panel says it was deleted. Press **Undo** straight away to save the same text again as a new draft.

If you delete the draft open in the Composer, the Composer clears. Only a draft can be deleted this way. A post that is queued keeps its place on the Queue (use **Back to drafts** there first), and a published or sent post is part of your record and cannot be deleted from the interface.

## Find an earlier post

Use **Drafts** for drafts (above). For any post, press **Ctrl+K**, or click the magnifier at the top of the rail, and type a word from the post. Choosing a draft reopens it in the **Composer**; if the Composer holds unsaved text, you are asked first. A queued or published post opens **Queue** or **Analytics** instead, because **Save** would write over it. See [Search everything with Ctrl+K](use-the-command-palette.md).

You can also read your posts in these places:

| Where | What you see | Which posts |
| --- | --- | --- |
| **Queue**, under **Scheduled posts** | The scheduled date and time, and the first line of each post | Scheduled only |
| **Analytics**, under **Post comparison** | The first line of each post with its numbers | Published only |
| **Brand Studio** > **Local security** > **Your data**, **Export JSON** or **Export CSV** | The full text of every post, whatever its status | All, including drafts |

The exports are written to the studio's home folder on this machine, and the path is shown under the buttons when the export finishes. See [Back up, restore and export](back-up-restore-and-export.md).

## What happens

- A draft you delete is removed from the local database. Every other post you have saved stays as a row in the database, whatever its status.
- Those rows are included in every backup and every export. A deleted draft stays in backups taken before you deleted it.
- Nothing in this article sends anything off the machine except **Send to LinkedIn**, which is covered in its own article.

## If it does not work

| What you see | What it means |
| --- | --- |
| "There is nothing written to save." (under the bar, beside SAVE FAILED) | The editor is empty. Type something before you press **Save**. |
| "Post content exceeds maximum 5,000 character limit." | The server refuses to save a post over 5,000 characters, whether it is new or already saved. Shorten it and save again. |
| Your text is gone after a reload | It was never saved, and you chose to leave when the browser asked. There is no way to recover it. |
| The Composer opened an older draft than you expected | It opens the draft created most recently, not the one edited most recently. Press **Drafts** to open the one you want. |
| "This post is published, not a draft, so it was kept." | Only drafts can be deleted. The post has gone out, so it stays in your record. |
| The Composer opened empty although you have drafts | The request for the draft failed. Reload the page. If it keeps happening, see [The studio will not open](the-studio-will-not-open.md). |
