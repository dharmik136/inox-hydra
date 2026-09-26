# Command-line tool reference
Run the studio's support commands from a terminal, with every command, option and confirmation in one place.

## How to run it

| How you run the studio | Command |
| --- | --- |
| Source checkout | Open a terminal in the folder that holds `launch_studio.bat` and run `python -m studio.cli <command>` |
| Portable build | Run `InoxHydra-CLI.bat <command>` from the portable folder. With no arguments it lists every command |

A second tool, `python studio_cli.py ai ...`, manages the AI provider. It exists only in a source checkout; the portable build does not ship it.

Some command output suggests `python -m studio.cli ...` even in the portable build. There, type `InoxHydra-CLI.bat` in its place.

## Commands

| Command | Options | What it does |
| --- | --- | --- |
| `doctor` | `--bundle`, `--output PATH` | Prints the version, schema state, data location and how it was chosen, database size, backups on disk (it counts at most 10), content row counts and any problems. `--bundle` also writes a redacted `inox_diagnostics_<stamp>.json`, to the logs folder unless you give `--output` |
| `paths` | none | Lists where this installation keeps its data, database, media, uploads, generated files, vault, logs, interface and docs |
| `backup` | `--label LABEL` (default `manual`) | Writes `inox_backup_<label>_<stamp>.zip` to the backups folder |
| `restore` | `ARCHIVE`, `--yes` | Replaces your current data with a backup |
| `export` | `--format json` or `csv` (default `json`), `--output PATH` | Writes drafts, posts, leads and analytics without credentials. CSV is a ZIP of one file per table |
| `reset` | `--yes` | Clears the settings table and keeps your content |
| `migrate` | `--dry-run` | Shows the schema version against the one this build targets, lists pending migrations and applies them, taking a backup first. `--dry-run` only lists them. It refuses when the database was written by a newer version |
| `token` | `show` (default) or `reset` | Prints the studio token, its header name and accepted origins. `reset` issues a new one |
| `update` | `check` (default), `enable`, `disable`, `status`, `--force` | Checks for a newer release, or turns checking on or off. `--force` ignores the saved ETag, so the version file is downloaded in full; it never overrides the off setting |
| `--version` | none | Prints the version |

For walkthroughs, see [Back up, restore and export](back-up-restore-and-export.md) and [Check your version and update the studio](check-your-version-and-update-the-studio.md).

## AI provider commands (source checkout only)

| Command | What it does |
| --- | --- |
| `python studio_cli.py ai configure` | Sets a provider. Takes `--provider`, `--api-key`, `--model` and `--base-url`, and asks for anything required you left out. It tests the connection and saves nothing if the test fails |
| `python studio_cli.py ai test` | Tests the saved provider |
| `python studio_cli.py ai status` | Shows the saved provider, model and a masked key |
| `python studio_cli.py ai list-providers` | Lists the providers you can choose |
| `python studio_cli.py ai reset` | Switches back to the built-in local engine |

To do this in the interface instead, see [Connect your own AI provider](connect-your-own-ai-provider.md).

## Commands that change things

`restore` and `reset` do nothing without `--yes`. Run them once without it to see what they would do; they then exit with code 1.

- **restore** first prints the archive's creation date, app version, whether it holds a database and its media file count, then "This REPLACES your current drafts, leads and analytics." With `--yes` it takes a `pre_restore` safety backup, writes the database and media back, and tells you to restart. Stop the studio before you run it; the command does not check.
- **reset** takes a `pre_reset` safety backup, then deletes every row of the settings table.

> [!WARNING]
> The `reset` message mentions only AI provider settings and the LinkedIn session. It clears more: your AI key, the LinkedIn session, the Brand Studio profile, grounding sources, the queue pause setting, the update-check preference and the Devtools switch. Drafts, posts, leads and analytics stay. Its closing hint suggests `python studio_cli.py ai configure`, which the portable build does not have.

## Handle secrets carefully

- `token` and `token reset` print the live studio token. Anything holding it can read and write your studio, so treat it like a password and never paste it anywhere public. After `token reset`, reload the studio in your browser and reload the extension.
- `ai configure --api-key` leaves your key in your shell history. If you let it prompt instead, the key shows on screen as you type.
- A `backup` archive contains the settings table, including your AI key. A `doctor --bundle` file redacts keys and cookies in the settings table, but it still holds your folder paths and the last lines of up to three files in the logs folder, which are not redacted.

## If a command fails

An unexpected problem prints `Error:` followed by the reason, then "If this keeps happening, run `doctor --bundle` and attach the file to an issue." The command exits with code 1. A mistyped backup path prints `No such backup:` instead. For a studio that will not start, see [The studio will not open](the-studio-will-not-open.md).
