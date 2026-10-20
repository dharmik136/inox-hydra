# The studio will not open or shows an error

Match what you see to its cause and fix the most common start-up problems.

## First check: is the server up?

Open `http://127.0.0.1:8000/api/v1/health` in your browser. This address needs no token.

- If it shows `"status": "ok"`, `"app": "inox-hydra"` and a version, the studio server is running. The problem is the page or the browser, so go to the table below.
- If the browser cannot connect, the server is not running.
- If it shows something else, a different program is using port 8000.

## Symptoms and fixes

| What you see | Cause | Fix |
| --- | --- | --- |
| The browser cannot connect to `127.0.0.1:8000` | The server did not start, for example because `python` is not on PATH or the requirements are not installed. The launcher checks neither | Read the server's own error (next section) |
| A plain JSON page: "The studio interface has not been built. Run npm ci and npm run build in studio/ui, which writes studio/frontend_next." | The React interface was never built in this checkout | From the checkout folder, run `npm --prefix studio/ui ci` then `npm --prefix studio/ui run build`, then reload |
| The launcher says "npm was not found on PATH." | Node is missing, and the interface needs building | Install Node 22 or newer from nodejs.org, then run the launcher again |
| The launcher says "The build finished but produced no interface." | The build failed | Scroll up in the launcher window to the npm error |
| "This server answers on loopback only." | You reached the studio through a name other than a loopback address such as `127.0.0.1` or `localhost`, for example an alias that points at this computer | Use `http://127.0.0.1:8000` |
| "Missing or invalid studio token." | The page lost its token cookie, or the token was reset | Reload `http://127.0.0.1:8000`, which sets the cookie again |
| A different app appears at port 8000 | Another program holds the port. `launch_studio.bat` treats anything on port 8000 as the studio and opens the browser anyway | Close that program, or stop it, then run the launcher again |
| The portable launcher says "Port 8000 is in use by another program, not Inox Hydra." | Another program holds the port, so the studio started on the next free port, 8001 to 8009, which the launcher names | Use the address it gives. The browser extension only connects on port 8000: to capture again, close the other program, close the **Inox Hydra Engine** window and start `InoxHydra.bat` again |
| The portable launcher says "The studio engine stopped while it was starting." and stays open | The server exited during start-up | Read the log lines it shows, and send `logs\engine.log` from your data folder with the report below |

## Read the server's own error

`launch_studio.bat` starts the server in a minimized window titled **Inox Hydra Backend**, then opens the browser three seconds later without checking that it worked.

The portable `InoxHydra.bat` starts it in a window titled **Inox Hydra Engine** and waits until it answers. When it does not, the launcher window stays open with the last lines of the engine's log and the path of the whole log, `logs\engine.log` in your data folder (`%LOCALAPPDATA%\InoxHydra` unless you chose another). That log is the server's own error; the steps below are for a source checkout.

1. Restore the **Inox Hydra Backend** window from the taskbar. If the window is gone, the server exited straight away.
2. If you cannot see an error, start the server by hand in a terminal opened in the checkout folder, the one that holds `launch_studio.bat`:
   1. `pip install -r requirements.txt`
   2. `python -m uvicorn studio.backend.app:app --host 127.0.0.1 --port 8000`
3. Read the last lines. A missing module means step 1 did not complete; an address already in use means another program has port 8000.

The studio needs Python 3.10 or newer.

> [!TIP]
> To stop the studio, close the **Inox Hydra Backend** window. Avoid commands that stop every Python process, since they also end any other Python program you are running.

## Reset the token

If reloading does not clear "Missing or invalid studio token.", issue a new token from a terminal in the checkout folder:

1. Run `python -m studio.cli token reset`.
2. It prints "Reload the studio in your browser, and reload the extension." Do both.

The command also prints the new token. Do not paste it anywhere public.

## Get a report you can share

Run `python -m studio.cli doctor` for a summary: version, data location, database state, backups on disk and any problems found. Add `--bundle` to write a fuller report to a file:

`python -m studio.cli doctor --bundle`

It prints where the file was written. Settings are redacted by an allowlist, so session cookies, API keys and any setting it does not recognise are hidden. The file still holds your folder paths, which include your Windows user name, and the last lines of any log files. The command describes the file as safe to attach to a public issue; open it in a text editor to confirm before you share it.

In the portable build, use `InoxHydra-CLI.bat doctor --bundle` and `InoxHydra-CLI.bat token reset`.

## Still stuck

When you ask for help, include:

- What `http://127.0.0.1:8000/api/v1/health` shows.
- The last lines of the **Inox Hydra Backend** window or the manual start.
- Whether you used `launch_studio.bat` or the portable `InoxHydra.bat`.
- The `doctor --bundle` file.

If your data is at risk, take a backup first, see [Back up, restore or export your data](back-up-restore-and-export.md). For first-time setup, see [Open the studio for the first time](open-the-studio-for-the-first-time.md).
