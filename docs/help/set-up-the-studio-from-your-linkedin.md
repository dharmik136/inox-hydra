# Set up the studio from your own LinkedIn

Show the studio your own LinkedIn profile once, so it can fill in your details, import your posts and activity, and tell your posts apart from everyone else's.

A new install opens on **Setup**, first in the rail. It has five steps, and each ticks itself when the studio has actually seen the thing it asks for.

## Before you start

You need the studio running and a browser that can carry the extension. Edge and Brave work; Chrome does not. See [Install the browser extension that captures leads and analytics](install-the-browser-extension.md).

## 1. Connect the browser

Click **Open LinkedIn with the bridge**. The studio starts Edge or Brave with the extension loaded, on your LinkedIn feed, with the studio in a second tab so the extension can reach it. It opens in its own browser profile, so it works even when that browser is already open, and your usual windows are left alone. The first time, sign in to LinkedIn there.

If no browser on this computer can load the extension by itself, for example when Chrome is the only one, the step says so and shows the extension's folder with **Copy the folder path**, for loading it by hand with **Load unpacked**. If no Chromium browser is found at all, nothing opens and the step asks you to install Edge or Brave.

The step ticks when the extension reports in, which it does every minute while a LinkedIn tab is in view. The status line reads "Connected" with the extension's version. If it later reads "Last heard from ...", no LinkedIn tab is open in the bridge browser.

## 2. Show it your profile

Click **Open my profile**. The bridge browser opens your own profile.

A few seconds later a notice on the LinkedIn page reads "The studio found your profile. Confirm it's you in the studio's Setup screen." Back in the studio, Setup shows the name, headline and address it found, and why it thinks the profile is yours: either the edit controls only you see were on the page, or LinkedIn itself sent its "my profile" address there.

Click **Yes, that's me**. If it is not you, click **No**.

The studio never asks this about a stranger. A profile without one of those signs is not sent to the studio at all.

## 3. Your profile

Once you confirm, the studio reads your profile: name, headline, location, about, follower and connection counts, experience, education and skills. The status line lists what it has read so far, for example "Read: 3 roles, 2 schools, 12 skills".

The profile page does not show everything, so three buttons open the pages that do:

- **Read contact info** opens your contact panel. Your email, phone, birthday and websites are read from it.
- **Read all skills** opens your full skills list. The profile itself shows only a few.
- **Read profile again** reads it afresh, for example after you change your headline.

Anything the page did not show is left as it was, so a section that had not loaded yet does not erase what was read before. Your profile page shows only your first few roles, schools and skills, so what it shows is added to the lists already read, from your archive or the full lists, and never shortens them. A full list replaces the stored one only when it is read from its own page, such as **Read all skills**. A field reading "Not read" is one the studio has not found yet.

Confirming also fills your name, headline and company in **Brand Studio**, but only where those are empty. What you typed there is never replaced. If you later delete what the studio holds about you, the fields it filled are cleared again, unless you have changed them since.

## 4. Your LinkedIn archive

LinkedIn gives every member a copy of what it holds about their account. It is the quickest and safest way to bring in your history: years of posts, comments and reactions, your roles and skills, and your connections, in one file, with nothing read from LinkedIn's pages. This step does not need the bridge, apart from opening LinkedIn's page for you.

1. Click **Open LinkedIn's download page**. On it, choose **Download larger data archive**, then **Request archive**. LinkedIn asks for your password, then emails you a link: usually within minutes for the first part, and within a day for all of it. The link lasts 72 hours.
2. Click **I have asked for it**. From then on, while this step is on screen, the studio looks in your Downloads folder for a file named like LinkedIn's export, such as `Complete_LinkedInDataExport_10-19-2026.zip`. It looks only for those names, only after you click this, and stops once an archive with your posts has been imported. The step names the folder it is looking in; on Windows that is your Downloads folder wherever you have moved it, to another drive or into OneDrive.
3. When the file appears under **IN YOUR DOWNLOADS FOLDER**, click **See what is in it**. While your browser is still downloading it, it is marked **STILL DOWNLOADING** and cannot be opened yet. If you saved it somewhere else, click **Choose the file** instead. Safari unpacks a downloaded archive into a folder of the same name and removes the file; that folder is offered in the same way, and if it is somewhere else, click **Choose the folder**.
4. The studio says whose archive it is, from the name in it, and lists each file it can read, with how many rows it holds, all ticked. Untick anything you do not want, then click **Import what is ticked**. Nothing is written before you do.

Everything in an archive becomes your own record, so the studio checks the name in it against the profile you confirmed in step 2. If they differ, it says so, for example "This archive belongs to Sample Alice, but the studio knows you as Sample Bob", and imports nothing until you tick the box naming both of you. It asks the same if you have not confirmed your profile yet, because it cannot check.

LinkedIn sends the archive in two parts. The first, `Basic_LinkedInDataExport_...`, arrives within minutes and holds your profile, roles and connections but no posts. You can import it, and the step then reads "without your posts" and keeps looking in your Downloads folder for the complete one, `Complete_LinkedInDataExport_...`, which usually follows within a day; files you have imported already are marked **ALREADY IMPORTED**. The step ticks once your posts are in. If your account has no posts, click **My account has no posts**.

| File in the archive | Where it goes |
| --- | --- |
| Posts you wrote (`Shares.csv`) | Your posts, with their dates. Reposts with nothing written are skipped. They arrive without reactions or impressions, because the archive does not have them; the bridge fills those in when it next reads your posts. |
| Comments you wrote, posts you reacted to | Your own activity, as in step 5. They never become leads. |
| Your name, headline and about | Fills only what is empty. What the bridge read is kept. |
| Your roles, education and skills | Roles and education only if none were read yet; skills are added to the ones already there. |
| Your connections | Name, company, position and the date you connected. Email addresses are never imported. |

Your messages stay in the archive and are never imported, and the list under **other files stay in the archive** says which other files were not read. If a file reads **NOT UNDERSTOOD**, LinkedIn has changed its columns; the note lists the ones it found, and nothing from that file is imported.

Importing the same archive again adds nothing twice. When the bridge later reads a post the archive brought in, the two become one: the archive's date and full text, and the figures LinkedIn shows on the page. A comment or reaction whose date the studio cannot read is skipped and counted, never given today's date. A file you chose by hand is kept by the studio only until it is imported or you click **Not now**, or for a day; a file in your Downloads folder is never moved or deleted.

To take out what an import added, for example an archive that was not yours, click **Remove what this import added** in this step, then **Remove it**. The posts, comments, reactions, roles, skills and connections it added are deleted, and the profile details it filled are put back as they were. What was in the studio before the import stays, and so does anything the bridge has read since: a post, a comment or reaction, your skills, and your profile details once the bridge has read your profile again. This works before you have confirmed your profile, too. One import runs at a time. If the studio stopped part way through one, the step says the import did not finish; remove what it added, then import the archive again.

## 5. Your history

If you imported your archive in step 4, this step only adds what has happened since and the counts LinkedIn shows on your posts. The step ticks once an import of **Posts you wrote** has read your posts to the end of the list, which is what **Today** needs to know your usual; posts from the archive alone do not tick it. Three imports read your activity pages:

| Import | What it reads |
| --- | --- |
| **Posts you wrote** | Your posts, their dates, and the counts LinkedIn shows on them. Reposts are skipped, because the writing is someone else's. |
| **Comments you left** | Your comments on other people's posts, and which post each was on. |
| **Posts you reacted to** | The posts you reacted to, and the reaction you used where the page says. |

Click **Import**. The bridge browser opens that activity page, and the extension scrolls it for you. A banner at the bottom of the page reads "Studio is importing your posts: N so far." with a **Stop** button.

- Keep the tab in view. The import pauses while the tab is hidden, and Setup then says PAUSED AT the count so far, BRING THE LINKEDIN TAB TO THE FRONT TO GO ON.
- It stops by itself when the list stops growing. If the page has nothing more to load, that is the end of the list: the banner reads "Done. N posts imported." and the row in Setup reads **READ TO THE END**.
- If the page still offers more (a **Show more** button, or a list still loading), the list stalled rather than ended. The banner says so, and the row reads **THE LIST STOPPED LOADING AT N. IMPORT AGAIN**. One import also reads at most 250 rounds of the list; past that the row reads **THE MOST ONE IMPORT READS**.
- **Stop** ends it early. What was read so far is kept.
- Only an import of your posts that read to the end counts as your whole post history. Until one has, **Leads** never calls anyone "engaged only with other people's posts", and never offers to remove them on that ground. Posts from your archive count as yours too.
- An import you asked for is picked up only within 30 minutes. After that its row reads **EXPIRED, CLICK IMPORT AGAIN**; click **Import** again.

**Import your history** does the three imports one after another. It is the same button, under the same name, on **Today** and on **Activity**. It opens your posts page; when that import ends, the bridge moves to your comments page by itself, then to your reactions page, and scrolls each one the same way. The line under it reads, for example, "IMPORTING ONE AFTER ANOTHER: POSTS NOW, THEN COMMENTS AND REACTIONS", and the studio remembers where it is if it restarts. **Stop** on any page, leaving the page, or clicking one of the single **Import** buttons ends it. If no browser that can carry the bridge opens, nothing is imported and the step says why.

Your comments and reactions are kept as your own activity. They never become leads.

When every step is ticked, a line under step 5 says Setup is done, with a **Go to Today** button.

> [!NOTE]
> Scrolling is the one thing the studio does on LinkedIn on your behalf, and only on your own activity pages, only after you click **Import** or **Import your history**. With **Import your history**, the bridge also moves from one of your activity pages to the next by itself. It reads what the page shows. The extension makes no requests to LinkedIn of its own.

## Check the capture is still working

The extension reads LinkedIn's pages, and LinkedIn changes how they are built without notice. When a part of the capture stops matching, it finds nothing and says nothing, which looks exactly like nobody engaging. Setup shows whether each of these seven parts is still working, under **CAPTURE HEALTH**:

| Part | What it reads |
| --- | --- |
| Comments and reactions on your posts | The people who become leads |
| Your profile | Your name and details, for step 3 |
| Your posts | The **Posts you wrote** import |
| Your comments | The **Comments you left** import |
| Your reactions | The **Posts you reacted to** import |
| Creator analytics | The figures in **Analytics** |
| Your posts' analytics pages | The figures on one of your own posts' analytics pages, such as members reached, saves and sends. Only your recorded posts are read |

Network reading is off unless you turn it on in the extension's popup. If you do, two more parts appear here once they have run: **Network reading: your posts' figures** and **Network reading: creator analytics**. They are not listed while network reading has not run, because opening a page cannot start them.

Each part shows one of three states:

- **NOT SEEN YET**, with a grey dot: the extension has not run that part in the last week. Open the matching LinkedIn page in the bridge browser.
- **WORKING, LAST READ** and a date and time, with a green dot.
- **CANNOT READ** and what it cannot read, for example `CANNOT READ NAME`, with an orange dot, and **LAST WORKED** and a date when it has worked before. The page was found, but the fields it needs could not be read.

When a part is orange, Setup adds: "A part marked in orange found the page but could not read it, which usually means LinkedIn has changed how the page is built. Nothing from that part is being captured until the extension is updated." There is nothing to fix on your side. Keep the studio up to date; see [After an update, reload the browser extension](after-an-update-reload-the-extension.md).

The extension reports at most once a minute per part per page, and the studio keeps these reports for a week. They say how much was found and kept, never what it was.

## What this changes elsewhere

- **Leads** keeps only people who engaged with your own posts, and never you. See [Why is my lead list empty?](why-is-my-lead-list-empty.md)
- Everything read here stays in the database on this machine. The diagnostics bundle reports how many rows each table holds, not what is in them.

## Delete it

Under **Your profile**, click **NOT YOU, OR WANT IT GONE? DELETE EVERYTHING THE STUDIO HOLDS ABOUT YOU**. Nothing is deleted yet. Setup lists what would go, with counts: your identity and profile, your imported posts and every reading of their figures, your comments and reactions, your connections, the record of your archive and history imports, and the Brand Studio fields Setup filled. Your leads and drafts are kept.

It also says whether a backup of the studio exists, and **Back up first** takes one. Type `delete` and click **Delete everything** to go ahead, or **Keep it** to leave everything as it is. It cannot be undone except from a backup. The next time you open your profile, Setup asks again.

**LINKEDIN SESSION** at the bottom of Setup is separate. It shows whether a session is stored for sending posts to LinkedIn, with its own **Delete**, which asks once more before it deletes. See [Connect your LinkedIn session](connect-your-linkedin-session.md).

## If it does not work

| What you see | What to do |
| --- | --- |
| Step 1 never ticks | Check the extension is loaded in the bridge browser, and open `http://127.0.0.1:8000` once in that browser so it has the studio's access key. Reload the extension after an update. |
| Step 2 never asks "Is this you?" | Open your profile from the bridge browser, not another one, and wait for the page to finish loading. If it still does not ask, LinkedIn may have changed its page; the studio refuses to guess. |
| A field reads "Not read" | Open the page that holds it with the buttons above. If it still does not fill, the extension did not recognise that part of the page. |
| The import stops early | The list may have stopped loading, or the tab was left. Click **Import again**; posts already read are not duplicated. |
| A row reads **WITH AN OLDER EXTENSION, END NOT KNOWN** | The browser is still running the extension from before the studio was updated, which cannot tell the end of the list from a stall. Importing again does not help until it is reloaded: open the browser's extensions page (`edge://extensions` or `brave://extensions`), click **Reload** on Inox Hydra Bridge, then click **Import again**. See [After an update, reload the browser extension](after-an-update-reload-the-extension.md). |
