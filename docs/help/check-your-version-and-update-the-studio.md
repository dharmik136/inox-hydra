# Check your version and update the studio

Find your version number, turn update checks on or off, and upgrade without losing your data.

## Check your version

The interface does not show the version. Use any of these:

- With the studio running, open `http://127.0.0.1:8000/api/v1/health` in your browser. It answers without a token, for example `{"status": "ok", "app": "inox-hydra", "version": "2.5.2"}`.
- In a terminal, run `python -m studio.cli --version` (portable copy: `InoxHydra-CLI.bat --version`). It prints `Inox Hydra 2.5.2`.
- Run `doctor`. Its first line starts with `Inox Hydra <version>`. See [Command-line tool reference](command-line-tool-reference.md).

## Update checks are off until you turn them on

The studio never checks for updates on its own. There is no update control in the interface: you run the studio's own check from the command line, and only after you enable it. (The server also has an `/api/v1/updates/check` route for the same check, but no control in the interface calls it. The desktop app's tray check is separate; see below.)

| Command | Portable copy | What it does |
| --- | --- | --- |
| `python -m studio.cli update enable` | `InoxHydra-CLI.bat update enable` | Stores your permission to check. Sends nothing. |
| `python -m studio.cli update disable` | `InoxHydra-CLI.bat update disable` | Turns checks off. |
| `python -m studio.cli update status` | `InoxHydra-CLI.bat update status` | Shows `current_version`, `enabled`, `asked`, `last_checked`, `last_seen_version`, `manifest_url` and `releases_url`. No network request. |
| `python -m studio.cli update` | `InoxHydra-CLI.bat update` | Checks once. Add `--force` to ignore the cached ETag. |

By default, a check is one HTTPS request for `release/latest.json` on `raw.githubusercontent.com` (the `INOX_UPDATE_MANIFEST_URL` environment variable changes the address). It sends a User-Agent of `InoxHydra/<version>`, so GitHub sees your IP address and version, and nothing about your content. The studio records when it checked and the latest version it saw. It never downloads, installs or runs anything. For how `INOX_NO_EGRESS` and `INOX_ALLOW_UPDATE_EGRESS` affect this, see [What leaves this machine, and when](what-leaves-this-machine.md).

A check prints `Installed:` and `Latest:`, then either "You are up to date." or "An update is available." with a download link to the releases page.

## Upgrade a portable copy

1. Take a backup. See [Back up, restore and export](back-up-restore-and-export.md).
2. Close the minimised **Inox Hydra Engine** window. See [Stop the studio, and use the tray icon](stop-the-studio-and-use-the-tray-icon.md).
3. Delete the Inox Hydra folder and extract the new ZIP in its place.
4. Start the studio as usual.

A portable copy keeps your data in `%LOCALAPPDATA%\InoxHydra`, outside the folder, so this is safe by default.

> [!WARNING]
> If you created a folder named `data` inside `app\studio` (true portable mode), your data lives inside the folder you are about to delete. Copy it out first, or you lose it. The same applies to a source checkout, below.

## Upgrade a source checkout

Do not delete the checkout. When `studio\data` exists, your database and media live inside the `studio` folder.

1. Take a backup.
2. Stop the studio.
3. Replace the checkout's source files with the newer version, keeping `studio\data`, `studio\assets`, `studio\backups`, `studio\vault` and `studio\logs`.
4. Run `pip install -r requirements.txt`.
5. Rebuild the interface: `npm --prefix studio/ui ci`, then `npm --prefix studio/ui run build`. The launcher only builds it when `studio\frontend_next\index.html` is missing, so after an update it would keep serving the old one.
6. Start the studio.

## The desktop app

In the desktop app, use **Check for Updates** in the tray menu. It checks only when you click it, and is separate from the `update` commands above. The item changes to "Checking for updates...", then to one of:

- Updates are not configured
- You are on the latest version
- Update installed. Restart to use it
- Update found, but it could not be installed
- Could not reach the update server

Unlike the command-line check, this one downloads and installs the update, and only if it is signed with the key built into your copy.

## What happens on first start after an upgrade

If the new version needs a newer database layout, the studio copies your database into the backups folder first, then upgrades it. You do not need to do anything.

## If it does not work

| What you see | What to do |
| --- | --- |
| Update checks are disabled. Nothing was sent. | Run `update enable`, or visit the releases page it prints. |
| Could not check for updates: ... | The request failed or was refused by an egress flag. The message says which. Check manually at the releases page it prints. |
| This database is at schema version *n*, but this build only understands up to *m*... | You started an older version against a newer database. Install the newer version again, or restore a backup from the folder named in the message. `migrate` reports "This database was written by a NEWER version of Inox Hydra." |
| The old interface after updating a checkout | You skipped step 5. Rebuild the interface and reload. |
