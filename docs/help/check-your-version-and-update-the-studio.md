# Check your version and update the studio

Find your version number, turn update checks on or off, and upgrade without losing your data.

## Check your version

The interface does not show the version. Use any of these:

- With the studio running, open `http://127.0.0.1:8000/api/v1/health` in your browser. It answers without a token, for example `{"status": "ok", "app": "inox-hydra", "version": "2.6.0"}`.
- In a terminal, run `python -m studio.cli --version` (portable copy: `InoxHydra-CLI.bat --version`). It prints `Inox Hydra 2.6.0`.
- Run `doctor`. Its first line starts with `Inox Hydra <version>`. See [Command-line tool reference](command-line-tool-reference.md).

## Update checks are off until you turn them on

The studio never checks for updates on its own. The check is off until you turn it on under **Update check** on **Health**, and the same switch is what the command line enables; while it is off, no request leaves this machine for a version check. Once it is on, **Check now** on Health asks GitHub once for the newest version number, and the command line can do the same. Nothing is downloaded or installed either way. (The desktop app's tray check is separate; see below.)

| Command | Portable copy | What it does |
| --- | --- | --- |
| `python -m studio.cli update enable` | `InoxHydra-CLI.bat update enable` | Stores your permission to check. Sends nothing. |
| `python -m studio.cli update disable` | `InoxHydra-CLI.bat update disable` | Turns checks off. |
| `python -m studio.cli update status` | `InoxHydra-CLI.bat update status` | Shows `current_version`, `enabled`, `asked`, `last_checked`, `last_seen_version`, `manifest_url` and `releases_url`. No network request. |
| `python -m studio.cli update` | `InoxHydra-CLI.bat update` | Checks once. Add `--force` to ignore the cached ETag. |

By default, a check is one HTTPS request to `github.com` for the `latest.json` file attached to the newest published release, which GitHub hands over from its download server (the `INOX_UPDATE_MANIFEST_URL` environment variable changes the address). So a check only ever names a version you can actually download. It sends a User-Agent of `InoxHydra/<version>`, so GitHub sees your IP address and version, and nothing about your content. The studio records when it checked and the latest version it saw. It never downloads, installs or runs anything. For how `INOX_NO_EGRESS` and `INOX_ALLOW_UPDATE_EGRESS` affect this, see [What leaves this machine, and when](what-leaves-this-machine.md).

A check prints `Installed:` and `Latest:`, then either "You are up to date." or "An update is available." with a download link to the releases page. With an update, it also says where your data is: outside the Inox Hydra folder, so the folder can be replaced, or "Your data is INSIDE the Inox Hydra folder", in which case do not delete the folder; follow the source checkout steps below.

## Upgrade a portable copy

1. Download the new file ending in `-win64.zip` from the latest release. Before you extract it, right-click it, choose **Properties**, tick **Unblock** and click **OK**.
2. Take a backup of every creator profile: `InoxHydra-CLI.bat backup --all`. See [Back up, restore or export your data](back-up-restore-and-export.md).
3. Close the minimised **Inox Hydra Engine** window. See [Stop the studio, and use the tray icon](stop-the-studio-and-use-the-tray-icon.md).
4. Delete the Inox Hydra folder and extract the new ZIP in its place.
5. Start the studio as usual, with `InoxHydra.bat` in the new folder.
6. If you loaded the browser extension by hand, load it again from the new folder's `extension` folder. See [After an update, the browser extension reloads itself](after-an-update-reload-the-extension.md).
7. If you made a desktop shortcut, make it again: the folder's name includes the version, so the old shortcut points at a folder that is gone. See [Put a studio shortcut on your desktop](put-the-studio-on-your-desktop.md).

A portable copy keeps your data in `%LOCALAPPDATA%\InoxHydra`, outside the folder, so this is safe by default.

> [!WARNING]
> If you created a folder named `data` inside `app\studio` (true portable mode), your data lives inside the folder you are about to delete. Copy it out first, or you lose it. The same applies to a source checkout, below.

## Upgrade a source checkout

Do not delete the checkout. When `studio\data` exists, your database and media live inside the `studio` folder.

1. Take a backup. A backup holds one creator profile, so take one of each: `python -m studio.cli backup --all`.
2. Stop the studio.
3. Replace the checkout's source files with the newer version, keeping `studio\data`, `studio\assets`, `studio\backups`, `studio\vault`, `studio\logs`, and, if you have them, `studio\profiles` (every creator profile after your first) and `studio\exports`.
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
