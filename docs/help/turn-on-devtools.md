# Turn on the Devtools surface

See what the Devtools surface is for, why a normal install hides it, and how a maintainer turns it on.

## What it is

Devtools is a maintainer surface. It holds an internal issue sheet, where the people building the studio record problems they see in the interface, and the screen registry, the list of screens the backend believes exist.

You do not need it to write, queue, publish or read analytics. Nothing on it changes how the studio behaves for you.

## Why you do not see it

- **The rail hides it.** When the studio loads, it asks the server whether dev mode is on. Devtools appears in the rail only when the answer is yes, and it is always the last entry.
- **The server refuses it.** Every route behind the surface answers `404 Not Found` while dev mode is off. The only one that answers either way is the status check the rail uses.
- **The command palette still lists it.** **Go to Devtools** is in the [command palette](use-the-command-palette.md) even when dev mode is off. Choosing it shows **MAINTAINER SURFACE IS OFF**, followed by "SET THE DEV MODE FLAG TO TURN IT ON. EVERY ROUTE BEHIND IT ANSWERS 404 UNTIL THEN."

That message is expected on a normal install. It is not a fault.

## Turn it on

Dev mode is controlled by one environment variable, `INOX_DEV_MODE`, in the environment of the server process. It counts as on when set to `1`, `true`, `yes` or `on`. No launcher sets it, and the launcher inside a portable build actively clears it, so a portable build cannot turn it on. From a source checkout, start the server by hand as below.

1. Stop the running server. See [Stop the studio, and use the tray icon](stop-the-studio-and-use-the-tray-icon.md). A server that is already running keeps the environment it started with.
2. Open a terminal in the checkout folder.
3. Set the variable for that terminal session, for example `set INOX_DEV_MODE=1` in Command Prompt or `$env:INOX_DEV_MODE = "1"` in PowerShell.
4. From that same terminal, start the server: `python -m uvicorn studio.backend.app:app --host 127.0.0.1 --port 8000`.
5. Reload the studio in your browser. **Devtools** now appears last in the rail.

To turn it off again, stop the server and start it from a terminal where the variable is not set.

## What is on it

| Part | What it does |
| --- | --- |
| **Issues**, **Open**, **Resolved**, **Critical** | Counts across the sheet. **Critical** counts open issues of critical severity, and turns orange when it is above zero. |
| **CSV** | Downloads the sheet as a CSV file. |
| **Record an issue** | A form with **Title**, **Target selector, for example .studio-rail**, and **What is wrong, and how to see it**, plus a severity of **low**, **medium**, **high** or **critical** (default **medium**). |
| **Record** | Saves the issue. It stays disabled until the title, target selector and description are all filled in. |
| **Sheet** | The 200 most recent issues, newest first, each with its severity, title and description. **RESOLVE** marks one resolved. Shows **NOTHING RECORDED** when empty. |
| **Screen registry** | The screen names the backend knows about. |

The sheet does not show which issues are resolved. The button reads **RESOLVE** on every issue, including one already resolved, so an issue cannot be reopened from this surface. If a status change fails, nothing is shown.

The form sends only those four fields, and every issue it records is filed with the category bug. There is no element picker and no console or network capture on this surface, even though the backend module describes them.

## What happens

- Issues are written to the studio's local SQLite database. Nothing on this surface sends data off the machine.
- The CSV and the sheet contain your titles, descriptions and target selectors. Treat an exported file as something you might pass to someone else, and keep credentials and private lead details out of it.
- If the server refuses an issue, the reason appears in orange under **Record**. If it gives no reason in words, you see the HTTP status code instead.

## Tools with no controls in the interface

While dev mode is on, the server also answers several maintainer routes that have no button on the Devtools surface. You reach them only through the API.

| Route | Purpose |
| --- | --- |
| `POST /api/v1/devtools/mode` | Switches the surface off for this installation without a restart. It cannot switch it back on, because once the surface is off this route answers 404 like the others. It can never turn dev mode on when the environment variable is missing. |
| `GET /api/v1/devtools/state` | Row counts, worker state and the running build. |
| `GET /api/v1/devtools/migrations` | Where the database sits against the migration ledger. Read only. |
| `POST /api/v1/devtools/migrations/apply` | Applies pending migrations, taking a backup first when any are pending. |
| `GET /api/v1/devtools/coverage` | For each screen, how many recorded issues landed on labelled sections and how many on unlabelled regions. |
| `GET /api/v1/devtools/sheet/export.json` and `POST /api/v1/devtools/sheet/import` | Export the sheet as JSON, and merge such an export into this database. |

## If it does not work

- **Devtools is still missing from the rail.** The server was probably started without the variable, or it was already running when you set it. Stop it and start it again from the terminal where you set `INOX_DEV_MODE`.
- **The variable is set but the surface still says it is off.** Someone switched it off at runtime through `POST /api/v1/devtools/mode`, and that setting is stored in the database, so a restart does not clear it. Nothing in the studio can switch it back on: that route now answers 404 too. The setting is the `devtools_runtime_enabled` row in the `settings` table of the local database, and changing it means editing the database outside the studio.
- **The page says READING DEVTOOLS STATUS and stays there.** The status check did not answer. See [The studio will not open](the-studio-will-not-open.md).
