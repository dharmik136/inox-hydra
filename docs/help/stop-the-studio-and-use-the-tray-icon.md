# Stop the studio, and use the tray icon
Stop the studio server the right way for how you started it, and see what each tray menu item does.

## Closing the studio window does not stop the studio

The window you work in is only a view. The server behind it keeps running, and keeps checking the queue, until you stop the server itself.

## Stop it

| How you started it | How to stop it |
| --- | --- |
| `launch_studio.bat` (source checkout) | Close the minimized window titled **LinkedIn Studio Backend** in the taskbar |
| `InoxHydra.bat` (portable folder) | Close the minimized window titled **Inox Hydra Engine** |
| `launch_studio.bat --tray` | See "The tray icon" below. **Exit Inox Hydra** does not stop the server |
| The LinkedIn Studio desktop app | Right-click its tray icon and choose **Quit** |

To confirm it has stopped, open `http://127.0.0.1:8000/api/v1/health` in your browser. If the studio is still running you see a short JSON reply whose `status` is `ok`. If it has stopped, the browser cannot connect.

## Start with a tray icon (source checkout only)

Run `launch_studio.bat --tray`. The launcher starts the tray in the background and exits without opening the studio. The tray starts the server itself if nothing is already running on port 8000. The portable folder does not include the tray.

Double-click the icon to open the studio. Right-click it for the menu.

## The tray menu

| Menu item | What it does |
| --- | --- |
| **Open Inox Hydra Studio** | Starts the server if needed, then opens the studio in a Chrome app window, or in your default browser if Chrome is not installed in the usual places |
| **Open Inbound CRM** | Opens the studio in your default browser. It lands on the Composer, not on Leads; use **Leads** in the rail from there |
| **Run Automated QA Tests** | A developer action. It runs the project's test suite in the background, needs the test tools installed, and shows no result anywhere. You can ignore it |
| **Restart Local Server** | Stops the server only if this tray started it, then starts one if port 8000 is free. A server started by `launch_studio.bat` is left alone |
| **Exit Inox Hydra** | Removes the tray icon. A server the tray started keeps running, with no window |

> [!WARNING]
> After **Exit Inox Hydra**, the server the tray started is still running with nothing on screen to close. To stop it, open Task Manager, go to **Details**, and end the `pythonw.exe` process that belongs to the studio, or sign out of Windows or restart. Do not end every Python process, since that also closes any other Python program you are running.

## The desktop app's tray

This applies only if you installed the LinkedIn Studio desktop app.

- Left-click the icon to show the studio window. Right-click for the menu.
- Closing the window hides it while the tray icon is there; the studio keeps running in the tray. If the app could not create its tray icon, closing the window quits the app instead.
- **Open Studio** shows the window.
- **Check for Updates** checks for a newer version. See [Check your version and update the studio](check-your-version-and-update-the-studio.md).
- **Quit** closes the app and stops the server if the app started it. If a server was already running when the app opened, **Quit** leaves that server running; stop it the way it was started.

## What happens

While the server runs, it checks the queue every 30 seconds. Stopping the server pauses that check until you start it again. See [How the queue works](how-the-queue-works.md) for what happens to posts that fell due while it was stopped.

Stopping the studio does not delete anything. Your drafts, leads and settings stay in the local database.

## If it does not work

| What you see | Why, and what to do |
| --- | --- |
| **Exit Inox Hydra** left the studio running | Expected. End the process as described above |
| **Restart Local Server** did nothing | The server was not started by this tray, for example by `launch_studio.bat` or by an earlier tray you exited. Stop it the way it was started, then choose **Restart Local Server** again |
| **Open Inbound CRM** opened the Composer | Expected. Click **Leads** in the rail |
| Starting the tray a second time opened the studio in your browser but added no icon | A tray is already running, so the second launch opens the studio and exits. Use the existing icon; it may be in the hidden icons area of the taskbar |
| **Check for Updates** changes to "Updates are not configured" | This build of the desktop app was made without update settings |

If the studio will not start again after you stop it, see [The studio will not open](the-studio-will-not-open.md).
