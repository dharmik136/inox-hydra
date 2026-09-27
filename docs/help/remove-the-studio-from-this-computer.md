# Remove the studio and everything it stored
There is no uninstaller or uninstall command, so removing the studio means stopping it and deleting a known list of folders and entries yourself.

The command-line `reset` only clears configuration and keeps your content.

## Before you start

1. To keep anything, take a backup or export and copy it outside the data home. Backups are written inside it, so deleting the data home deletes them. See [Back up, restore or export your data](back-up-restore-and-export.md).
2. Stop the server the way you started it. See [Stop the studio, and use the tray icon](stop-the-studio-and-use-the-tray-icon.md).

## Find your data home

Run `python -m studio.cli paths` in the checkout folder, or `InoxHydra-CLI.bat paths` in the portable folder. The `app_home` line is your data home. It is chosen in this order:

| Checked | Data home |
| --- | --- |
| `INOX_HYDRA_HOME` is set | The folder that variable names |
| A `studio/data` folder exists beside the code | The `studio` folder itself (source checkout, or a portable folder in true portable mode) |
| Otherwise | Windows `%LOCALAPPDATA%\InoxHydra`, macOS `~/Library/Application Support/InoxHydra`, Linux `$XDG_DATA_HOME/inox-hydra` or `~/.local/share/inox-hydra` |

The last row is called the platform folder below. `paths` does not list `backups`, exports, the browser profiles, autostart or keystore entries; see below.

## What is in the data home

| Folder or file | Holds |
| --- | --- |
| `data` | `linkedin_studio.db` (your drafts, leads, settings and session), `analytics_telemetry.db`, and `.intelligence_etag` and `.update_etag` |
| `assets` | `uploads` and `generated` media |
| `vault` | `api_token` (the studio token) and, where used, `vault_key` |
| `logs` | `inox_diagnostics_*.json` bundles, and `engine.log` from the desktop app |
| `backups` | Backup ZIPs and pre-upgrade database copies |
| `inox_export_*.json` or `.zip` | Exports, in the data home itself |

## Remove it by install type

- **Source checkout.** Delete the checkout folder; your state is in its `studio` folder. Then check the platform folder (`%LOCALAPPDATA%\InoxHydra` on Windows), which holds the bridge browser profile even for a checkout.
- **Portable folder.** Delete the folder, then `%LOCALAPPDATA%\InoxHydra`. In true portable mode (you created `app\studio\data`), your data was inside the folder, but the browser profile is still in `%LOCALAPPDATA%\InoxHydra`.
- **Desktop app.** Remove LinkedIn Studio the way your system removes apps (on Windows it installs for the current user only), then delete the platform folder, `%LOCALAPPDATA%\InoxHydra` on Windows. Nothing in the studio deletes that folder, and this project does not define what the uninstaller removes.

## Things outside the data home

- **Browser profiles.** `browser-profiles` in the platform folder (or in `INOX_HYDRA_HOME`), one folder per bridge browser. It holds that profile's LinkedIn sign-in.
- **Autostart**, if it was ever turned on. Windows: `LinkedIn Studio.lnk` in `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`. macOS: `~/Library/LaunchAgents/com.inoxhydra.linkedinstudio.plist`. Linux: `inox-hydra.desktop` in `~/.config/autostart` (or `$XDG_CONFIG_HOME/autostart`). The interface has no control for it; delete the file.
- **Desktop shortcuts**, if you ran a shortcut script. They are on your Desktop. Windows: `LinkedIn Studio.lnk`, and `LinkedIn Studio (<browser name>).lnk` per browser. macOS: `LinkedIn Studio (<browser name>).command` per browser. Linux: `inox-hydra-<browser id>.desktop` per browser.
- **Keystore entry**, macOS and Linux only: service `InoxHydra.LinkedInStudio`, account `vault_master_key`, in the Keychain or Secret Service. Remove it with the system's own tool, such as Keychain Access or `secret-tool clear service InoxHydra.LinkedInStudio account vault_master_key`. Windows needs nothing here; the encrypted session is inside the database.
- **The token cookie** `inox_studio_token`, in any browser that opened the studio, lasts a year unless you clear site data for `127.0.0.1` (and `localhost`, if you opened it that way). It is harmless once the server is gone.

## Remove the extension

- **Loaded by hand:** open `edge://extensions` or `brave://extensions` and click **Remove** on **LinkedIn Studio Bridge (LocalTaplio)**.
- **Loaded by the launcher:** it lives only in the dedicated bridge profile, so it goes when you delete `browser-profiles`.

## What deleting does not do

It does not sign you out of LinkedIn; the stored session was a copy of your browser cookies. Consider signing out of LinkedIn in the bridge browser window before deleting its profile. See [Connect your LinkedIn session](connect-your-linkedin-session.md) and [What leaves this machine, and when](what-leaves-this-machine.md).

## If it does not work

| You see | What to do |
| --- | --- |
| Windows says a file is in use | The server, or a bridge browser window, is probably still open. Close it, then try again |
| The data folder comes back | Something started the studio again, usually autostart. Remove the autostart entry, stop the server, and delete the folder again |
