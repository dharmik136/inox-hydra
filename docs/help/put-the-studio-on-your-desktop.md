# Put a studio shortcut on your desktop
Which shortcut you can make depends on how you run the studio, and only a source checkout has a ready-made script for it.

## Pick your case

| How you run the studio | What to use |
| --- | --- |
| Source checkout, started with `launch_studio.bat` | The bundled `create_desktop_shortcut.vbs` script |
| Portable folder, started with `InoxHydra.bat` | An ordinary Windows shortcut to `InoxHydra.bat` |
| Desktop app | The app's own entry |
| Edge or Chrome, with the server already running | The browser's own install option |

## Source checkout

1. In the checkout's top folder, double-click `create_desktop_shortcut.vbs`.
2. A message reads "Shortcut created on Desktop, pointing at:" followed by the path to `launch_studio.bat`.
3. Double-click **LinkedIn Studio** on your desktop to start the studio.

What happens: the shortcut runs `launch_studio.bat`. If the interface has not been built yet, it builds it first, which needs Node 22 or newer. If nothing answers on port 8000, it starts the server in a minimised window and waits three seconds, then opens `http://127.0.0.1:8000` in a Chrome app window when Chrome is installed in its standard Program Files or Program Files (x86) folder, or in your default browser otherwise. It does not check that the server really started. See [Open the studio for the first time](open-the-studio-for-the-first-time.md).

To start the tray icon instead, add `--tray` after the target in the shortcut's properties. The launcher then starts the Windows-only tray program and exits. See [Stop the studio, and use the tray icon](stop-the-studio-and-use-the-tray-icon.md).

## Portable folder

The portable folder includes `create_desktop_shortcut.vbs`, but it does not work there: it looks for `launch_studio.bat`, which the portable folder does not have, and stops with "Could not find launch_studio.bat next to this script."

Make an ordinary Windows shortcut instead. This is a Windows feature, not part of the studio.

1. Open the portable folder.
2. Right-click `InoxHydra.bat` and choose **Send to**, then **Desktop (create shortcut)**. On Windows 11 you may need **Show more options** first.
3. Rename the shortcut if you like.

The portable folder's name includes the version, for example `InoxHydra-2.5.2-win64`. After an upgrade, the shortcut points at a folder that no longer exists, so make it again.

## Desktop app

Use the app's own entry. This guide does not say whether its installer adds a desktop or Start menu shortcut. Launching the app a second time brings back the window already open rather than starting a second copy. The browser extension still needs a real browser; see [Install the browser extension that captures leads and analytics](install-the-browser-extension.md).

## Install it as an app from the browser

The studio publishes a web app manifest named **LinkedIn Studio** (short name **Studio**), so Edge or Chrome may offer to install it. That offer is a browser feature; the studio's tests check the manifest's shape, not an actual install.

> [!IMPORTANT]
> The installed window only shows the studio's local address. It does not start the server. If the server is not running, the window shows a connection error.

## Start with Windows instead

The studio can add a `LinkedIn Studio.lnk` entry to your Windows Startup folder that runs `InoxHydra.bat` or `launch_studio.bat` minimised at sign-in. It is off until you turn it on, and there is no control for it in the interface; see the maintainers note below. Because it runs the full launcher, it also opens the studio window at sign-in. To remove it, delete `LinkedIn Studio.lnk` from `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`.

> [!NOTE]
> For maintainers: these routes need the studio token and have no interface control.
>
> - `POST /api/v1/desktop/autostart` with `{"enabled": true}` creates the Startup entry, and `{"enabled": false}` removes it. On macOS it writes a LaunchAgent, `com.inoxhydra.linkedinstudio.plist`, in `~/Library/LaunchAgents`; on Linux, `~/.config/autostart/inox-hydra.desktop`. It reports the state it achieved. `GET /api/v1/desktop/integration` reports the current state.
> - `POST /api/v1/browser/create-shortcuts` writes one launcher per detected browser: `LinkedIn Studio (<browser>).lnk` on Windows, `LinkedIn Studio (<browser>).command` on macOS, `inox-hydra-<id>.desktop` on Linux. Each opens LinkedIn in the bridge browser profile with the extension loaded; it does not open the studio, so it does not pair the browser by itself. It also makes one for Chrome, which ignores the extension flag. The macOS and Linux launchers are tested with fake browsers only.

## If it does not work

| What you see | What to do |
| --- | --- |
| "Could not find launch_studio.bat next to this script." | You are in a portable folder, or the script was moved. Use the portable steps above, or keep the script in the checkout's top folder. |
| The shortcut opens a page that cannot connect | The server is not running. See [The studio will not open or shows an error](the-studio-will-not-open.md). |
| The shortcut does nothing after an upgrade | It points at the old folder. Make it again. |
