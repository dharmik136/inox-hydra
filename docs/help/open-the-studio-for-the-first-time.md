# Open the studio for the first time
Start the studio on your PC, open it at 127.0.0.1:8000, and learn what each part of the screen is for.

## Before you start

There are two ways to run the studio. Use the one that matches the folder you have.

| You have | Launcher | What it needs |
| --- | --- | --- |
| A portable folder | `InoxHydra.bat` | Nothing extra. It runs the Python that ships inside the folder (`runtime\python.exe`). |
| A source checkout | `launch_studio.bat` | Python 3.10 or newer with the requirements installed, reachable as `python` on your PATH. The first time, it also needs Node 22 or newer to build the interface. |

The portable folder also has `InoxHydra-CLI.bat`, which runs the support commands (backup, export, diagnostics). You do not need it to open the studio.

## Start the studio

1. Double-click the launcher (`InoxHydra.bat` or `launch_studio.bat`).
2. From a source checkout, on the very first run only, the launcher builds the interface. It prints "The studio interface has not been built yet. Building it now." and runs `npm --prefix studio/ui ci` and `npm --prefix studio/ui run build`. This can take a few minutes.
3. The launcher starts the server in a minimized window. From a source checkout it is titled **LinkedIn Studio Backend**; from the portable folder it is titled **Inox Hydra Engine**. Leave that window open. Closing it stops the studio.
4. After a few seconds (3 from a source checkout, 4 from the portable folder) the studio opens. If Google Chrome is installed in its standard location (Program Files or Program Files (x86)), it opens as a 1440 by 920 Chrome app window. Otherwise it opens in your default browser.
5. You can also type `http://127.0.0.1:8000` into any browser on this PC.

If the server is already running on port 8000, the launcher says so and opens the studio without starting a second copy.

## What happens

The server listens only on `127.0.0.1`, so only this PC can reach it. Your drafts, leads, analytics and settings are kept in SQLite files in a `data` folder, and your media in an `assets` folder beside it:

| How you run it | Where your data lives |
| --- | --- |
| Source checkout | Inside the `studio` folder of the checkout: databases in `studio/data`, media in `studio/assets` |
| Portable or installed copy | `%LOCALAPPDATA%\InoxHydra` |
| Either, with `INOX_HYDRA_HOME` set | The folder that variable names |

## What a fresh install shows

A new database starts almost empty, on purpose. Nothing about you or your account is invented.

- **Composer**: an empty editor. Above it, the hook rail shows specimens from the 36 built-in hook forms.
- **Queue**: 11 default weekly posting slots and no posts.
- **Leads**: "No leads captured yet" and setup instructions for the browser extension.
- **Analytics**: empty until the extension captures your numbers.
- **Brand Studio**: no name. While the **Name** field is empty, the preview shows "Unnamed".

## Find your way around

The rail on the left lists the surfaces. Hover an icon to see its name.

| Rail label | What it is for |
| --- | --- |
| Composer | Write, re-hook and stage the next post |
| Queue | Scheduled posts and peak engagement slots |
| Leads | Lead stream and person dossiers |
| Swipe File | Saved specimens and structural patterns |
| Analytics | Time series, observations and comparisons |
| Command | Agent runs and local model routing |
| Docs | Offline playbook and strategy search |
| Brand Studio | Identity, watermark and local security |

- The mark at the top of the rail opens a tray that lists the same surfaces with their labels.
- Press **Ctrl+K** (**Cmd+K** on a Mac) to open the command palette. Press **Escape** to close it. It has a "Go to" entry for each surface, plus **Switch theme** and **Toggle inspector**.
- On the Composer, the inspector sits on the right with the tabs **Preview**, **Audit**, **Media**, **Brand** and **Prompt**. If you close it, a small panel icon in the top right corner (named **Open inspector**) brings it back.
- The studio opens in the dark theme. **Switch theme** changes it, but the choice is not saved: reloading the page or reopening the studio brings back the dark theme.

> [!NOTE]
> Some palette entries only move you to a surface. **Generate 5 hooks**, **Make sharper**, **Add contrarian angle** and **Turn into carousel** switch to the Composer and change nothing. **Go to Devtools** is listed but leads to a surface that does not work in a normal install.

The **LOCAL** shield at the bottom of the rail says all processing is local. That stops being fully true once you connect a cloud AI provider or generate an image. See [What leaves this machine, and when](what-leaves-this-machine.md).

## What to set up next

All of these are optional.

1. Open **Brand Studio**, stay on **Identity**, fill in **Name** (and **Headline** and **Company** if you like), then press **Save**.
2. To capture leads and your analytics, follow [Install the browser extension that captures leads and analytics](install-the-browser-extension.md).
3. To use your own AI model, follow [Connect your own AI provider](connect-your-own-ai-provider.md).

## If it does not work

The launcher does not check that the server actually started. It opens the browser after a few seconds either way, so a failed start looks like a page that cannot connect. Any other program already using port 8000 is also treated as the studio. See [The studio will not open or shows an error](the-studio-will-not-open.md).

If a source checkout stops with "npm was not found on PATH.", install Node 22 or newer from nodejs.org and run the launcher again.
