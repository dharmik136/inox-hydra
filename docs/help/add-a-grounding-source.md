# Add a grounding source (MCP), and what you are allowing

Connect a local MCP server so the studio can read your own notes, and understand what that lets it run and send.

## What a grounding source is

A grounding source is an MCP server: a program on this computer that the studio starts, asks what documents it holds, reads a few of them, and stops again. The idea is that posts can draw on your own notes instead of generic material.

> [!IMPORTANT]
> Nothing in the interface uses grounding material yet. You can connect a source and preview what it hands over, but no button in the composer, Re-Hook or the Command console gathers it. The only code that does is a copilot route that no control in the interface calls.

## What you are allowing

- **The studio will run the command you type**, with your Windows account's permissions, every time grounding is gathered (today, that means every time you press the preview).
- **It only reads.** The studio lists and reads the program's resources. It never calls the program's tools, so it never asks it to send mail, write files or take any other action.
- **The program's own network traffic is outside the studio.** The Brand Studio ledger says so directly: a connected MCP source "is a program on this machine that may make its own requests, which this studio neither sees nor can stop." `INOX_NO_EGRESS` does not reach it. See [What leaves this machine, and when](what-leaves-this-machine.md).

Only add a command you would be willing to run yourself.

## Add one

1. Open **Brand Studio** in the rail and choose the **Grounding** tab.
2. Under **Connect a source**, type a **Name**.
3. In the command box (placeholder `Command, for example: npx -y @some/mcp-server`), type the command that starts the server.
4. Check the line that appears underneath, for example `RUNS AS 3 ARGUMENTS: [npx] [-y] [@some/mcp-server]`. That list is exactly what will be run. It never goes through a shell.
5. Optionally fill in **What it holds (optional)**.
6. Press **Add, switched off**.

You see "Added, and switched off. Turn it on when you want it read." The source is stored in your local database under the settings key `mcp_servers`. You can have at most 12.

## Turn it on, off or remove it

- The checkbox beside each source (read aloud as "Let *name* be read") switches it on or off. Only switched-on sources are started.
- The bin icon ("Remove *name*") deletes the source immediately. It does not ask for confirmation.

## See what it hands over

Press **SHOW WHAT THEY HAND OVER**. The studio then, for each switched-on source:

1. starts the program (it gets 10 seconds to start and 15 seconds per request, and is killed if it does not answer),
2. lists its resources and reads up to 3 of them,
3. trims each to 1,500 characters and the whole set to 6 KB,
4. stops the program.

The **What would be handed over** panel shows each source's name and text, then `<used> OF <budget> BYTES`. If nothing came back it reads **NOTHING GATHERED**.

## Where the material would go

The **Where grounding material goes** box at the top works this out from your current AI provider. It shows one of these:

| Your setup | Message |
| --- | --- |
| No provider (local engine) | Grounding stays on this machine. The local engine makes no network request. |
| A provider at a loopback address (`localhost`, `127.x`, `::1` or `0.0.0.0`) | Grounding stays on this machine. *provider* is answering at *address*, which is this computer. |
| A provider elsewhere | Grounding material will be sent to *address*. Anything gathered here leaves your machine as part of the prompt. |
| A provider with no address set | ...cannot tell where that is. Treat it as leaving your machine. |

To change the provider, see [Connect your own AI provider](connect-your-own-ai-provider.md).

## If it does not work

| What you see | What it means |
| --- | --- |
| **NO SOURCES CONNECTED** although you added some | The list could not load, usually because the server is not running. See [The studio will not open](the-studio-will-not-open.md). |
| `[object Object]` under the preview | A source failed (it did not start, or offered nothing). The interface cannot print the reason; check the command runs in a terminal. |
| A server named *X* already exists. | Names must be unique, ignoring case. Pick another. |
| A server needs a plain name and a command given as a list of arguments. | The name must start with a letter or digit and use only letters, digits, spaces, `_`, `.` or `-`. |
| `422` | The name is longer than 48 characters, or the command has more than 24 arguments. |
| At most 12 servers. | Remove one first. |
| A path with spaces is split into pieces | Quotes are not honoured when the command is split, so such a path cannot be entered from the interface. A working folder and environment variables are not available in the interface either. |
| A checkbox springs back, or a source you removed is still listed | Switching or removing failed. No message is shown, and the list keeps showing what it last loaded. |
