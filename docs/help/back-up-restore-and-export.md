# Back up, restore or export your data

Take a backup or export from Brand Studio, find where it was saved, and restore one from the command line.

## Where your data lives

Everything is one SQLite database plus a media folder, inside one data home folder:

| How you run the studio | Data home |
| --- | --- |
| Source checkout (`launch_studio.bat`) | The `studio` folder of the checkout, when `studio/data` exists. Otherwise `%LOCALAPPDATA%\InoxHydra` |
| Portable or installed copy | `%LOCALAPPDATA%\InoxHydra` |
| `INOX_HYDRA_HOME` is set | The folder that variable names |

To see the exact paths, open a terminal in the checkout folder, the one that holds `launch_studio.bat`, and run `python -m studio.cli paths` (portable build: `InoxHydra-CLI.bat paths`). Backups go in the `backups` folder inside the data home.

## Back up now

1. Open **Brand Studio** from the rail.
2. Choose the **Local security** tab.
3. Scroll to **Your data**.
4. Click **Back up now**.

When it finishes, a note reads "Saved *size* to *archive path*". Below the buttons the studio lists how many files the backups folder holds, five of them with their size and time, and the folder path. Your ZIP backups come first, newest first, then the automatic database copies. The file itself is not downloaded through the browser; it stays where the note says.

**What happens:** the studio writes `inox_backup_manual_<date>_<time>.zip`. It contains `data/linkedin_studio.db` (a compact copy taken in one consistent read, so it is consistent even while the studio is running), every file under `assets/`, and a `backup_manifest.json` with the date, the version and the result of the checks. Each backup is checked as it is made: the database copy must pass SQLite's integrity check, and the archive is read back against its checksums. If either fails, no file is kept and the note gives the reason; your earlier backups are unchanged. Photos and videos are stored as they are rather than compressed again, which saves time and no space.

**Automatic daily backup.** While the studio is open, it also makes `inox_backup_daily_<date>_<time>.zip` once a day, checked the same way. Any backup made in the last 24 hours counts, so pressing **Back up now** puts the next one off. Turn it off, and see the last and next backup, in Brand Studio's **Storage and privacy** tab. See [Choose what the studio keeps, and for how long](choose-what-the-studio-keeps.md).

**Which backups are kept.** Of the automatic backups, the studio keeps the newest of each of the last 7 days, then of 4 weeks before those, then of 3 months before those: about 14, reaching back about four months. The backups a cleanup makes first (`inox_backup_pre_cleanup_<date>_<time>.zip`) are counted with them. Backups you make with **Back up now** or the command line, and the safety backups taken before a restore, are never removed by the studio.

The studio also saves a timestamped copy of the database in the same folder before any schema upgrade, named `linkedin_studio_premigration_<date>_<time>.db`. The last 2 are kept. Those appear in the list too, after your ZIP backups.

A backup holds everyone in your leads on the day it was made. If you later forget someone, they stay in older backups until those are removed, unless you remove them from backups too; see [Choose what the studio keeps, and for how long](choose-what-the-studio-keeps.md).

> [!WARNING]
> A backup contains your whole database, including your leads' names and comments, so store backup files carefully. Your AI key, and your LinkedIn session if one is stored, are in it only in sealed form, locked to this computer and your account on it. Restore the backup somewhere else and they read as not set: enter the AI key again there, and reconnect LinkedIn if you use it.

## Export JSON or Export CSV

In the same **Your data** section:

- **Export JSON** writes `inox_export_<stamp>.json`.
- **Export CSV** writes `inox_export_<stamp>.zip`, a ZIP holding one CSV file per table. It is not a single CSV.

Both go in the `exports` folder of the open creator profile (in the data home for your first profile), not the backups folder, and the interface does not list them. The note shows the path followed by "Content only. Credentials are deliberately excluded."

An export holds the drafts, posts, leads, lead interactions, daily analytics, audience demographics and queue items tables, and your own LinkedIn record: your profile, roles, education and skills, your posts with every reading of their figures, what you commented on and reacted to elsewhere, each lead's stage history, your connections from LinkedIn's archive, and a record of each archive import. A backup or an export holds the open creator profile only. The settings table, which holds your LinkedIn session and AI key, is left out on purpose. Media files are not included.

## Export to Obsidian

**Export to Obsidian**, in the same section, writes a folder of linked notes that Obsidian, a free notes app, opens as a vault:

| In the folder | What it holds |
| --- | --- |
| `Home.md` | Counts, the people who engaged on more than one post, and your topics |
| `Me.md` | Your headline, about, roles and skills, once you have confirmed your profile in Setup |
| `Posts/` | One note per post: its text, its figures, its readings over time, and everyone who engaged, as links |
| `People/` | One note per lead: every post they engaged with, what they said, and their stage history |
| `Topics/` | One note per topic, linking its posts |
| `Outbound/` | One note per person whose posts you engaged with, linked to their People note if they engaged back |
| `Drafts/` | Your drafts |

The folder is `exports/obsidian_vault` inside the data home, one per creator profile, and the note shows its path. Press **Export to Obsidian** again to refresh that same vault; the note says how many notes it wrote and whose words it kept. In Obsidian choose **Open folder as vault** and pick it, then open the graph view: your posts are the hubs and the people around them are your audience.

A figure the studio never read says "not measured", not 0.

**Keep your own notes in it.** Every note ends with a **Your notes** heading. Anything you write below it, and any note you add yourself, survives the next export into the same folder, and stays with the same person or post: each note keeps its name from one export to the next, even when someone with the same name is added or removed. When a person's name or a draft's title changes, the note moves to the new name and takes what you wrote with it. The export never writes over a note of yours. If a new person would take the name of a note you made, theirs gets another name, such as `People/Mei Lin (2).md`. If you edit a note above its **Your notes** heading, the export leaves your version as it is and writes the refreshed one beside it. When someone is removed from the studio, their note goes too, unless you wrote something in it: then only what you wrote is kept. To keep a vault somewhere else, export from the command line into it, and again to refresh it: `python -m studio.cli export --format obsidian --output "<vault folder>"`. The studio refuses a folder that has files in it and is not one of its own exports, so it cannot overwrite a vault you already keep.

## Backup or export?

| | Backup | Export |
| --- | --- | --- |
| Contents | Full database and all media | Content tables only, no media |
| Credentials | Included | Excluded |
| Can it be restored? | Yes, from the command line | No |
| Use it for | Getting your studio back | Taking your content to a spreadsheet, Obsidian or another tool |

## Restore a backup

The interface has no restore button. Use a terminal opened in the checkout folder:

1. Close the studio server (the minimized **Inox Hydra Backend** window, or **Inox Hydra Engine** in the portable build).
2. Check the archive first: `python -m studio.cli restore "<path to zip>"`. Without `--yes` it prints the backup's creation date, app version, whether it contains a database, and its media file count, then stops.
3. Restore it: `python -m studio.cli restore "<path to zip>" --yes`.
4. Start the studio again. The command ends with "Restart Inox Hydra for the restored data to take effect."

**What happens:** the studio unpacks the backup beside your data and checks its database first. Then it takes a `pre_restore` safety backup of your current state, swaps the database and the media files in, and prints the safety backup's path. If anything fails part way, everything it had changed is put back, the message starts "Not restored", and it names the safety backup. If you restored the wrong archive, restore the safety backup the same way.

If the studio will not start because its database is damaged, restore your latest backup the same way. The restore still runs: the current database cannot be copied normally, so the safety backup (`inox_backup_pre_restore_damaged_<date>_<time>.zip`) keeps its files exactly as they were, in a `damaged` folder inside the ZIP, and the command says so.

To go back to the state from before an upgrade, restore its automatic copy the same way: `python -m studio.cli restore "<path to linkedin_studio_premigration_<date>_<time>.db>" --yes`. It replaces the database only and leaves your media files as they are. The next start brings it up to the current layout again.

In the portable build, use `InoxHydra-CLI.bat backup`, `InoxHydra-CLI.bat restore <zip>` and `InoxHydra-CLI.bat export`.

### More than one creator profile

Each command acts on the open creator profile and starts by naming it, for example `Profile: Client A (client-a)`. Add `--profile <profile id>` to choose another, or, for `backup` and `export`, `--all` to make one per profile, each in that profile's own folder: `python -m studio.cli backup --all`. Run a restore once per profile, with `--profile` naming the one the backup belongs to.

## Moving to another computer

Restoring on a new PC brings back drafts, posts, leads, analytics, queue items, settings and media. Two things do not come with it:

- **Your LinkedIn session.** It is stored in the database, but on Windows it is encrypted to your Windows account, so another PC or account cannot read it. After a restore there, **Stored session** reads `NONE`. Reconnect it, see [Connect your LinkedIn session](connect-your-linkedin-session.md).
- **The studio token.** Backups skip the `vault` folder where it is kept, so a new one is created. Open the studio page once so your browser receives it; the extension reads it from there.

## If it does not work

| You see | What it means | What to do |
| --- | --- | --- |
| BACKUP FOLDER COULD NOT BE READ | The page could not list the backups folder | Run `python -m studio.cli paths` and check the folder exists and is not locked by sync software |
| NO BACKUPS YET | The folder is empty | Click **Back up now** |
| The note shows a server message or a status code instead of "Saved" | The backup or export did not complete | Read the message. If unclear, run `python -m studio.cli doctor` |
| `No such backup` | The path you typed is wrong | Copy the file name from the list in **Your data** and the folder path shown below it |
| `contains no database and cannot be restored` | The file is an export or another ZIP, not a backup | Choose an `inox_backup_` file |
| `This backup was made by a newer version of Inox Hydra` | The backup comes from a newer studio, for example on another computer, and this one could not open it after restoring | Update this studio to the version the message names, or newer, then restore again. Nothing was changed |
