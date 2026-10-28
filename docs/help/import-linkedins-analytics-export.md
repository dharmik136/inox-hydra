# Import LinkedIn's analytics export

Bring the .xlsx file LinkedIn's analytics page writes when you press Export, and the studio keeps your exact daily figures, your posts' figures and the demographics LinkedIn gives as percentages, once you have seen what is in it.

> [!NOTE]
> Verified against a real file: yes, on 2026-10-28. A real export was checked that day: LinkedIn's aggregate export, a file named AggregateAnalytics followed by your name and the first and last days of its range. Its sheets are DISCOVERY, ENGAGEMENT, MOST RECENT POSTS, TOP POSTS, FOLLOWERS, AUDIENCE DEMOGRAPHICS and CONTENT DEMOGRAPHICS, and it gave 399 days of exact daily figures. A post's own export has not been checked yet. Anything the studio does not recognise is still listed as not recognised and left out, never guessed at.

## Why it is worth doing

- Your LinkedIn archive (Setup, step 4) carries your posts, but no figures.
- The bridge reads the figures LinkedIn shows on the pages you open, and LinkedIn rounds those above a thousand, so 1.2K is anything from 1,150 to 1,249. See [Read your analytics](read-your-analytics.md).
- The export holds your figures exactly, by day, for a range from the past 7 days up to the past 365 days. It is LinkedIn's own download, so nothing reads LinkedIn's pages to get it. See [Where each feature stands with LinkedIn's terms](where-each-feature-stands-with-linkedins-terms.md).

## Export it from LinkedIn

1. Open **Setup**. In step 4, under **LinkedIn's analytics export, for exact figures**, click **Open LinkedIn's analytics page**.
2. On LinkedIn, choose the range you want and press **Export**. LinkedIn saves an .xlsx file.
3. Back in Setup, click **I have exported it**. From then on, while Setup is open, the studio looks in your Downloads folder for a spreadsheet named like LinkedIn's export and lists it under **IN YOUR DOWNLOADS FOLDER**. It looks only after you click this, and only until you import one. If you saved the file somewhere else, click **Choose the file**.

A post's own analytics page is reported to have an Export of its own; its file is read the same way.

## See what is in it

Click **See what is in it**. Nothing is written yet. The line under the file's name says which days the export covers and where that was read from: the file's name, or the days in it. Then every sheet in the file is listed:

| The preview says | What it means |
| --- | --- |
| **Impressions and engagements by day**, **New followers by day, and your follower total**, **Your top posts of the range**, **Your most recent posts**, **Totals over the range**, **Your audience's demographics**, **Who engaged with your posts**, **One post's own figures** | A sheet the studio recognises, with how many rows it holds and what it would write |
| **NOT RECOGNISED** | A sheet the studio does not know. Nothing in it is imported, and the preview shows its first row so you can see what it was |
| Not recognised, and left out: ... | Columns of a recognised sheet that the studio does not know. The rest of the sheet is read |
| Recognised, left out because the studio keeps no such figure yet: ... | Figures LinkedIn gives that the studio has no place for yet, such as profile viewers from a post |
| Recognised, but not imported: ... | The sheet is known, but something in it could not be read with certainty, for example dates written 10/5/2026 when nothing in the file says whether the day or the month comes first. Nothing from that sheet is imported |
| Left out: 1 share LinkedIn gives only as a bound, such as < 1% ... | LinkedIn says only that the share is under one percent, not what it is, so it is not kept as a figure |
| **Demographics** | A sheet called only Demographics does not say whose shares it holds, your audience's or those of the people who engaged with your posts. It is recognised, and not imported |

## Import it

Untick anything you do not want, then click **Import what is ticked**. Every figure is marked as read from LinkedIn's export, and exact.

| Sheet | Where it goes |
| --- | --- |
| ENGAGEMENT | Your daily analytics: each day's impressions, and its engagements, which **Analytics** shows where it shows the engagements card the bridge reads |
| FOLLOWERS | Each day's new followers, and your follower total on the day the sheet names |
| TOP POSTS | A reading of each of your recorded posts that was published inside the export's range: its impressions and engagements up to the range's last day |
| MOST RECENT POSTS | Read the way TOP POSTS is: a reading of each of your recorded posts in the list that was published inside the export's range, each figure under its own name, dated the range's last day. A post the studio does not hold is left out, never created |
| A post's own export | A reading of that post, dated when the file was written, with impressions, members reached, reactions, comments, reposts, saves and sends each under its own name |
| DISCOVERY | The totals over the range, kept with the record of the import. A total over a range is not a day's figure, so the chart does not plot it |
| AUDIENCE DEMOGRAPHICS | Your audience's demographics: each group's share as a percentage, for example the share of your audience with one job title or in one location, kept as one reading dated the range's last day |
| CONTENT DEMOGRAPHICS | The same, for the people who engaged with your posts over the range, kept apart from your audience's so the two are never mixed |

- A day the bridge already read from your analytics page is kept as it was read, and the result says how many were kept. A day holds one source's figures.
- A top post published before the export's range is left out, because its figure covers only part of its life. A post that is not one of your recorded posts is left out too; import your posts first.
- Importing the same export again adds nothing twice: the days it wrote are brought up to date, and each post keeps one reading from it.
- The two demographics sheets hold groups and their shares, and no one's name; nothing else in them is kept. Another export that ends on the same day replaces that day's shares, so one day's shares always come from one export. No screen shows them yet.
- A file you chose by hand is kept by the studio only until it is imported or you click **Not now**, or for a day. A file in your Downloads folder is never moved or deleted.
- Nothing in the file is sent anywhere.

Deleting everything the studio holds about you in Setup removes the record of each import, the post readings it wrote and the demographics it kept. The days it wrote stay with your daily analytics, as the days the bridge read do.

## If it does not work

| You see | What to do |
| --- | --- |
| That file is not an .xlsx spreadsheet | Choose the file LinkedIn's Export wrote, not a copy saved in another format |
| Recognised, but not imported: its dates are written as numbers with slashes ... | The studio could not tell the day from the month. An export whose file name carries its range, as LinkedIn's is reported to, settles it |
| A post you expected was not read | It is not among your recorded posts, or it was published before the export's range. Run **Posts you wrote** in Setup's step 5, then import the export again |
| A day still shows a rounded figure | The bridge read that day from your analytics page before the import, and that day keeps the page's figures |
| Recognised, but not imported: its shares are written as bare numbers ... | The demographics sheet writes its shares as numbers such as 0.3 with no percent sign, and 0.3 could be 30 percent or 0.3 percent. Nothing from that sheet was imported; the rest of the file was |
| Recognised, but not imported: it gives figures without a link to each post ... | A list of posts is matched to your recorded posts only by each post's link, so a list without links is not read |
| Every sheet reads NOT RECOGNISED | LinkedIn's export is laid out differently from what the studio expects. Nothing was imported |
