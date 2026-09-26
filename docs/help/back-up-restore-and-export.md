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

When it finishes, a note reads "Saved *size* to *archive path*". Below the buttons the studio lists how many files the backups folder holds, five of them with their size and time, and the folder path. The five are the first by file name in reverse order, not necessarily the newest. The file itself is not downloaded through the browser; it stays where the note says.

**What happens:** the studio writes `inox_backup_manual_<date>_<time>.zip`. It contains `data/linkedin_studio.db` (copied through SQLite's backup API, so it is consistent even while the studio is running), every file under `assets/`, and a `backup_manifest.json` with the date and version.

The studio also saves a timestamped copy of the database in the same folder before any schema upgrade, named `linkedin_studio_premigration_<date>_<time>.db`. Those appear in the list too, and because of the name order they are listed before your ZIP backups.

> [!WARNING]
> A backup contains your whole database, including the settings table. Your AI key is stored there in plain text, next to your leads' names and comments. Store backup files as carefully as a password file.

## Export JSON or Export CSV

In the same **Your data** section:

- **Export JSON** writes `inox_export_<stamp>.json`.
- **Export CSV** writes `inox_export_<stamp>.zip`, a ZIP holding one CSV file per table. It is not a single CSV.

Both go in the data home folder, not the backups folder, and the interface does not list them. The note shows the path followed by "Content only. Credentials are deliberately excluded."

An export holds the drafts, posts, leads, lead interactions, daily analytics, audience demographics and queue items tables. The settings table, which holds your LinkedIn session and AI key, is left out on purpose. Media files are not included.

## Backup or export?

| | Backup | Export |
| --- | --- | --- |
| Contents | Full database and all media | Content tables only, no media |
| Credentials | Included | Excluded |
| Can it be restored? | Yes, from the command line | No |
| Use it for | Getting your studio back | Taking your content to a spreadsheet or another tool |

## Restore a backup

The interface has no restore button. Use a terminal opened in the checkout folder:

1. Close the studio server (the minimized **LinkedIn Studio Backend** window, or **Inox Hydra Engine** in the portable build).
2. Check the archive first: `python -m studio.cli restore "<path to zip>"`. Without `--yes` it prints the backup's creation date, app version, whether it contains a database, and its media file count, then stops.
3. Restore it: `python -m studio.cli restore "<path to zip>" --yes`.
4. Start the studio again. The command ends with "Restart Inox Hydra for the restored data to take effect."

**What happens:** the studio first takes a `pre_restore` safety backup of your current state, then replaces the database and writes the media files back, and prints the safety backup's path. If you restored the wrong archive, restore the safety backup the same way.

In the portable build, use `InoxHydra-CLI.bat backup`, `InoxHydra-CLI.bat restore <zip>` and `InoxHydra-CLI.bat export`.

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
