# Choose what the studio keeps, and for how long

See how much each kind of data takes, set how long readings and logs are kept, review people who went quiet years ago, and know what happens to forgotten people in backups.

## Open Storage and privacy

1. Open **Settings** from the rail, which opens **Brand Studio**.
2. Choose the **Storage and privacy** tab.

The panel acts on the open creator profile only. Each profile keeps its own data and its own rules.

## What this profile holds

The first section lists each kind of data with its number of rows and its size inside the database: your posts, drafts and queue; post readings; leads and their engagement; your comments and reactions on other posts; connections from your LinkedIn archive; daily analytics; logs; the help search index; and settings. Below them are the database file, the network readings log (a separate file), your media and the backups folder.

If this computer's copy of SQLite cannot measure the parts of the database, each part says "not measured" and only the file sizes are shown.

### Compact the database

When you forget people or a cleanup removes rows, the space they took stays inside the database file. The words themselves are already overwritten. When there is such space, the panel says how much and offers **Compact the database**. Compacting rewrites the file without it, which also drops anything a version of the studio before 2.6.0 left behind in freed space. It takes about a second for every 300 MB and needs twice the database's size free on the drive. Nothing compacts on its own.

## The rules

| What | Default | Choices | Never removed |
| --- | --- | --- | --- |
| Daily backup | On | On, Off | The newest backup |
| Network readings log (what the extension saw of LinkedIn's network requests) | 30 days | 7, 30 or 90 days | |
| Post readings | Every reading for 30 days, then the last reading of each day | 30, 90 or 365 days; Off | The last reading of each day, every reading from 36 to 72 hours after a post went out, and everything recent |
| Reactions older than 24 months | Folded into counts | On, Off | Comments, all of them; how many people reacted to each post; how many old reactions each person made |
| People silent for 24 months | Listed for you to review | List them, Do not list them | Everyone you have not chosen to forget |
| Your posts, drafts, notes, daily analytics, comments, connections | Kept for good | | All of it |

**Post readings.** The extension reads a post's figures many times while it is new. After 30 days, the studio keeps the last reading of each day. Today compares your latest post with your earlier ones at about two days old, so every reading from 36 to 72 hours after a post went out is kept, and Today's comparison and each post's latest figures stay exactly as they were.

**Reactions.** A reaction nobody has seen again for 24 months is folded into counts. Kept: how many people reacted to each post, and how many of these reactions each person made, whether on your posts, and the topics of those posts, so the numbers on every screen stay the same. Lost: which people reacted to which post, and when. Everyone stays in your leads, including people whose only engagement was such a reaction; a person's timeline shows how many old reactions they made. Comments are never folded; every comment is kept. LinkedIn's own reaction figures for your posts are not affected.

### Previews and confirmation

Every rule that removes something has **Preview**, which says what it would remove now, on how many posts, and about how much space that is. Nothing is removed by a preview.

If your studio already held post readings or reactions when you updated to 2.6.0, those two rules show **WAITING FOR YOU**, and nothing is rolled up or folded until you choose **Preview and turn on** and then confirm. Confirming backs up first, runs the cleanup, and keeps the rule on: from then on it runs once a day, after the daily backup. A new install starts with both rules on. **Turn off** stops a rule.

Every cleanup runs after a checked backup, never during an upgrade, and running it again removes nothing more. **Recent cleanups**, at the end of the panel, lists each run with how many rows it removed.

## Review people silent for 24 months

Someone is listed when they are still **New**, you have written no note about them, changed no stage and enriched nothing, and nothing has been seen from them for 24 months. Nobody is forgotten unless you choose them.

1. Choose **Review them**. The list shows the longest silent first, 200 at a time.
2. Tick the people you want to act on, or **Choose all**.
3. Choose **Keep** to keep them. They are not listed again.
4. Or choose **Forget**, then **Forget them** to confirm.

**What happens:** the studio makes a backup first, then checks each person again. Anyone who has engaged, or whom you acted on, since the list was shown is kept, and the message says how many. The others are removed from this database with their engagement, stage history and enrichment.

## Forgotten people and backups

Forgetting removes a person from the database at once. Copies of them stay in backups made before then:

- in automatic daily backups until rotation removes those backups, within 135 days (after you forget someone, the panel gives the date);
- in the database copies taken before an upgrade, until two more upgrades have replaced them;
- in backups you made yourself with **Back up now**, until you delete them.

After anyone is removed from your leads, from this review list, from the Leads screen or by any other removal, this section offers two choices:

- **Remove from backups too** rewrites every backup and pre-upgrade copy in this profile's backups folder without them. Each rewritten file is checked before it replaces the original, and keeps its date. It can take a minute for a large studio. A backup that could not be rewritten is named in the message and still holds them.
- **Leave them until the backups expire** leaves the backups as they are.

To remove them, the studio keeps the list of whom you forgot only until you choose. Backups you copied somewhere else are not touched.

For how backups are made and kept, see [Back up, restore or export your data](back-up-restore-and-export.md). For what leaves this computer, see [What leaves this machine, and when](what-leaves-this-machine.md).

## If it does not work

| You see | What it means | What to do |
| --- | --- | --- |
| STORAGE COULD NOT BE READ | The panel could not reach the studio | Reload the page. If it persists, run `python -m studio.cli doctor` |
| `Nothing was removed: the backup taken first failed` | The backup a cleanup needs failed its check, so the cleanup did not run | Read the reason in the message. Your earlier backups are unchanged |
| `Compacting needs about N MB free on this drive` | There is not room for the new copy | Free space on the drive, then compact again |
| A backup named after "could not be rewritten" | That file could not be read or rewritten | It still holds the forgotten people. Delete it if you do not need it |
