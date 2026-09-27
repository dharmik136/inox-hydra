# Connect your LinkedIn session
Store your LinkedIn session so Send to LinkedIn can work, and learn where it is kept and what it is used for.

## Do you need it?

Only **Send to LinkedIn** uses the session. It is the one control that hands a saved post to LinkedIn's own scheduler (see [Publish, queue or send a post to LinkedIn](publish-queue-or-send-to-linkedin.md)). Lead and analytics capture read pages you open yourself and do not need it. If you only write, queue and record posts, skip this.

The session is two LinkedIn cookies, `li_at` and `JSESSIONID`.

> [!CAUTION]
> `li_at` is a full LinkedIn login. Anyone holding it can act as you. Paste it only into the studio, never into a chat, a document or a support request.

## Option A: press Sync in the extension

1. In the browser where you are logged in to LinkedIn and the [browser extension](install-the-browser-extension.md) is loaded, open `http://127.0.0.1:8000` once, so the extension has the studio's access key.
2. Click the extension's toolbar icon.
3. Click **Sync LinkedIn Session**.

The popup says what happened: "Session saved to the studio, for sending to LinkedIn only." on success, "Sign in to LinkedIn in this browser first." if you are not logged in, "The studio is not running on port 8000." if it cannot reach the studio, or "The studio refused this browser." if step 1 was skipped.

The session is copied only when you press the button. Nothing copies it on a timer.

## Option B: paste it

1. Open **Brand Studio** from the rail.
2. Choose **Local security**.
3. Scroll to **LinkedIn session**.
4. Paste your `li_at` value into the field marked `li_at`.
5. Paste your `JSESSIONID` value into the field marked `JSESSIONID`.
6. Click **Save to vault**. It stays disabled until both fields are filled.

The fields clear and the note reads "Saved to the local vault."

The studio does not tell you how to find these values. As general browser steps, not studio behaviour: on linkedin.com, open your browser's developer tools, go to the storage or application panel, open the cookies for `https://www.linkedin.com`, and copy the value of each cookie.

Pressing **Sync LinkedIn Session** in the extension later overwrites what you pasted.

## Check it

Under **LinkedIn session**, **Stored session** reads:

| Value | Meaning |
| --- | --- |
| PRESENT | Both values are stored |
| NONE | One or both are missing or unreadable |
| READING | The studio is still checking, or could not read the status. Reload the page if it stays. |

PRESENT only means values are stored. Nothing checks that LinkedIn still accepts them. The **LinkedIn session** row in the list above it reads CONNECTED or NOT CONNECTED and is coloured green either way, so read the words, not the colour.

## What happens

- Both values are encrypted and written to the settings table in your local database. On Windows the encryption uses the Data Protection API, tied to your Windows account. It is not hardware backed.
- Saving contacts nobody. The panel says so: "SAVING CONTACTS NOBODY: SYNCING WITH LINKEDIN IS A SEPARATE ACTION YOU TAKE DELIBERATELY."
- Every request the studio itself makes to LinkedIn is refused unless it was started with `INOX_ALLOW_LINKEDIN_EGRESS=1` and without `INOX_NO_EGRESS=1`. A stored session alone sends nothing.
- The diagnostics bundle redacts the session, and exports leave it out. Backups include it, still encrypted.

## Remove it

1. Open **Setup** from the rail.
2. Under **LINKEDIN SESSION**, click **Delete**.

The line changes to "Not stored." Only the session is removed; nothing else in your settings changes. It is not copied back unless you press **Sync LinkedIn Session** again. Backups taken before you deleted it still hold the encrypted session.

## If it does not work

| Symptom | Cause and fix |
| --- | --- |
| **Stored session** reads NONE after restoring a backup on another PC or under another Windows account | The session was encrypted under another machine or Windows account and cannot be read here. Paste it again. |
| A bare "502" after **Send to LinkedIn**, with PRESENT | The dialog does not say which of these happened. If the **linkedin** line under **What has left this machine** is marked OFF, the studio was not started with `INOX_ALLOW_LINKEDIN_EGRESS=1`, and nothing was sent. Otherwise LinkedIn declined the request, for example after you logged out, or the studio paused sends for five minutes after a 401, a 403 or three failures in a row. Saving the session again ends that pause. The studio also sends a placeholder author id rather than your member id, so LinkedIn may decline a send even when the session is valid. |
| A message appears under **Save to vault** instead of "Saved to the local vault." | The studio refused the save. Reload the page and try again. If it persists, see [The studio will not open or shows an error](the-studio-will-not-open.md). |

See also [What leaves this machine, and when](what-leaves-this-machine.md).
