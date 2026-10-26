# Open the studio for the first time
Start the studio on your PC, open it at 127.0.0.1:8000, and learn what each part of the screen is for.

## Before you start

There are two ways to run the studio. Use the one that matches the folder you have.

| You have | Launcher | What it needs |
| --- | --- | --- |
| A portable folder (Windows) | `InoxHydra.bat` | Nothing extra. It runs the Python that ships inside the folder (`runtime\python.exe`). |
| A source checkout on Windows | `launch_studio.bat` | Python 3.10 or newer with the requirements installed, reachable as `python` on your PATH. The first time, it also needs Node 22 or newer to build the interface. |
| A source checkout on macOS or Linux | `./launch_studio.sh` | The same as on Windows. There is no packaged macOS or Linux build yet, so this is the way to run it there. |

Get the portable folder from the latest release: download the file ending in `-win64.zip`. Before you extract it, right-click it, choose **Properties**, tick **Unblock** and click **OK**. The build is not code signed yet, so if Windows still shows "Windows protected your PC", click **More info**, then **Run anyway**. Extract it anywhere.

The portable folder also has `InoxHydra-CLI.bat`, which runs the support commands (backup, export, diagnostics). You do not need it to open the studio.

## Start the studio

1. Double-click the launcher (`InoxHydra.bat` or `launch_studio.bat`).
2. From a source checkout, on the very first run only, the launcher builds the interface. It prints "The studio interface has not been built yet. Building it now." and runs `npm --prefix studio/ui ci` and `npm --prefix studio/ui run build`. This can take a few minutes.
3. The launcher starts the server in a minimized window. From a source checkout it is titled **Inox Hydra Backend**; from the portable folder it is titled **Inox Hydra Engine**. Leave that window open. Closing it stops the studio.
4. The portable launcher waits until the server answers as Inox Hydra, then says "The studio is ready at" its address. `launch_studio.bat` waits a fixed 3 seconds instead.
5. The studio opens. If Google Chrome is installed in its standard location (Program Files or Program Files (x86)), it opens as a 1440 by 920 Chrome app window. Otherwise it opens in your default browser.
6. You can also type `http://127.0.0.1:8000` into any browser on this PC.

If the studio is already running, the launcher says so and opens it without starting a second copy.

### If port 8000 is taken

The portable launcher checks what is on port 8000. If it is another program, it says "Port 8000 is in use by another program, not Inox Hydra." and starts the studio on the next free port, from 8001 to 8009, then tells you which one. Use the address it gives.

The browser extension only connects on port 8000, so while the studio is on another port it cannot capture leads or analytics. To move it back, close the other program, close the **Inox Hydra Engine** window, and start `InoxHydra.bat` again.

## What happens

The server listens only on `127.0.0.1`, so only this PC can reach it. Your drafts, leads, analytics and settings are kept in SQLite files in a `data` folder, and your media in an `assets` folder beside it:

| How you run it | Where your data lives |
| --- | --- |
| Source checkout | Inside the `studio` folder of the checkout: databases in `studio/data`, media in `studio/assets` |
| Portable or installed copy | `%LOCALAPPDATA%\InoxHydra` |
| Either, with `INOX_HYDRA_HOME` set | The folder that variable names |

## What a fresh install shows

A new database starts almost empty, on purpose. Nothing about you or your account is invented.

The studio opens on **Setup** until Setup is done, all five of its steps, and on **Today** afterwards (see [What to do today](what-to-do-today.md)). Each screen has its own address, such as `#/leads` after the studio's address, so reloading keeps you on the screen you were on, a bookmark or link opens that screen, and the browser's Back and Forward buttons move between the screens you visited. It connects the bridge browser and reads your own LinkedIn: see [Set up the studio from your own LinkedIn](set-up-the-studio-from-your-linkedin.md).

- **Composer**: an empty editor. Above it, the hook rail shows the 12 starter hook forms a new studio is seeded with.
- **Queue**: 11 default weekly posting slots and no posts.
- **Leads**: "No leads captured yet" and setup instructions for the browser extension.
- **Analytics**: empty until the extension captures your numbers.
- **Brand** and **Settings** (both open **Brand Studio** for now): no name. While the **Name** field is empty, the preview shows "Unnamed".

## Find your way around

The rail on the left lists the sixteen sections, in five groups: **Now**, **Make**, **Learn**, **Bridge** and **Studio**. In a window 1200 pixels wide or more it shows each section's name under its group; in a narrower window it shows icons, and hovering an icon, or moving to it with **Tab**, shows its name. The group names are headings, not buttons.

| Rail label | Group | What it is for |
| --- | --- | --- |
| Today | Now | Who to reply to and how your latest post is doing |
| Replies | Now | Every comment on your posts that is waiting on a reply |
| Composer | Make | Write, re-hook and stage the next post |
| Queue | Make | Scheduled posts and peak engagement slots |
| Outbound | Make | Whose content you engage with, and whether it comes back |
| Posts | Learn | Which of your posts worked, and who each one brought |
| Leads | Learn | Lead stream and person dossiers |
| Audience | Learn | Who keeps coming back, who has gone quiet, and who is a connection |
| Patterns | Learn | What your own posts suggest, and how steadily you post |
| Analytics | Learn | Time series, what changed, and comparisons |
| Brand | Learn | Your identity and watermark. For now it opens **Brand Studio**, as **Settings** does |
| Activity | Bridge | What the bridge has read from your LinkedIn, as it arrives |
| Health | Bridge | Whether the bridge is reading, and what it could not read |
| Setup | Studio | Connect the browser and teach the studio who you are |
| Docs | Studio | Offline playbook and strategy search |
| Settings | Studio | Grounding, local security, storage and privacy, and your licence. For now it opens **Brand Studio**, as **Brand** does |

The **Studio** group sits at the foot of the rail, so **Setup** is always in the same place. Below it, the **Bridge** chip says whether the bridge browser has been heard from and opens **Health**.

- The mark at the top of the rail opens a tray that lists the same surfaces with their labels.
- Press **Ctrl+K** (**Cmd+K** on a Mac), or click the magnifier at the top of the rail, to search your posts, leads, hook forms and help from anywhere. Press **Escape** to close it. See [Search everything with Ctrl+K](use-the-command-palette.md).
- On the Composer, the inspector sits on the right with the tabs **Preview**, **Audit**, **Media**, **Brand** and **Prompt**. If you close it, a small panel icon in the top right corner (named **Open inspector**) brings it back.
- The studio opens in the light or dark theme your computer is set to. The sun or moon button in the top bar of every screen except the Composer, or **Switch theme** in Ctrl+K, changes it, and the studio remembers your choice in this browser.

The **LOCAL** shield at the bottom of the rail says all processing is local. That stops being fully true once you connect a cloud AI provider or generate an image. See [What leaves this machine, and when](what-leaves-this-machine.md).

## What to set up next

All of these are optional.

1. Open **Brand Studio**, stay on **Identity**, fill in **Name** (and **Headline** and **Company** if you like), then press **Save**.
2. To capture leads and your analytics, follow [Install the browser extension that captures leads and analytics](install-the-browser-extension.md).
3. To use your own AI model, follow [Connect your own AI provider](connect-your-own-ai-provider.md).

## If it does not work

If the portable launcher cannot start the studio, its window stays open and opens no page. It says what happened, shows the last lines of the engine's log, and gives the log's full path (`logs\engine.log` in your data folder). Press a key to close it.

`launch_studio.bat` in a source checkout does not check that the server actually started. It opens the browser after a few seconds either way, so a failed start looks like a page that cannot connect, and any other program already using port 8000 is treated as the studio.

See [The studio will not open or shows an error](the-studio-will-not-open.md).

If a source checkout stops with "npm was not found on PATH.", install Node 22 or newer from nodejs.org and run the launcher again.
