# What leaves this machine, and when

See exactly which actions send data off your computer, where it goes, and the switches that stop it.

## What stays here

Your drafts, posts, leads, analytics, settings and media are one SQLite database file and one media folder on this computer. The server listens on `127.0.0.1` only, so other computers on your network cannot reach it. The interface's fonts are bundled with the studio, so opening it makes no request to Google Fonts.

> [!IMPORTANT]
> Brand Studio shows the line "YOUR DRAFTS, LEADS AND LINKEDIN SESSION NEVER LEAVE THIS MACHINE." and the rail tooltip says "All processing is local to this machine". Neither is fully true: **Send to LinkedIn** sends your post text and session cookies to LinkedIn, **Re-Hook** or **Command** with a provider configured sends your text to that provider, and **Generate** sends a prompt built from your image description to an image service. The table below is the full picture.

## Everything that can leave

| Category | What triggers it | What is sent | Where it goes | On by default? | Flag |
| --- | --- | --- | --- | --- | --- |
| `model` | Re-Hook, Command, other writing actions and the prompt-writing step of **Generate**, only after you configure an AI provider | Text from your draft or command, inside a prompt the studio writes | Your configured AI provider. Ollama runs on this computer, but its requests are still counted here | Yes | `INOX_ALLOW_MODEL_EGRESS` |
| `image` | Pressing **Generate** in the Media tab | A prompt built from your image description, and the size | OpenAI if it is your AI provider, Gemini if a Gemini key is set, and Pollinations if neither is set or both fail | Yes | `INOX_ALLOW_IMAGE_EGRESS` |
| `linkedin` | **Send to LinkedIn**, and session or profile checks against LinkedIn | Your post text, its scheduled time and your LinkedIn session cookies | LinkedIn | No | `INOX_ALLOW_LINKEDIN_EGRESS` |
| `library` | A hook template sync. No button in the interface triggers it | A request for a template file | GitHub | Yes | `INOX_ALLOW_LIBRARY_EGRESS` |
| `updates` | `python -m studio.cli update`, after you opt in with `update enable`. No button in the interface triggers it | A request for a version file | GitHub | Yes, but opt-in first | `INOX_ALLOW_UPDATE_EGRESS` |
| `ingress` | Only if `TELEGRAM_BOT_TOKEN` or `PRUDENT_TELEGRAM_BOT_TOKEN` is set when the studio starts | Polling for bot messages | Telegram | Yes, but inert without the token | `INOX_ALLOW_INGRESS_EGRESS` |

The update check runs in the command's own process, not in the server, so the ledger below does not count it, and a flag counts for it only if it is set in the terminal where you run the command.

Every other publish control, and the whole Queue, only writes a status on this machine. See [Publish, queue or send a post to LinkedIn](publish-queue-or-send-to-linkedin.md).

## Read the ledger

1. Open **Brand Studio** from the rail.
2. Choose the **Local security** tab.
3. Scroll to **What has left this machine**.

Each category shows `N sent`, and `N refused` once something was refused. A category that is currently blocked has an `OFF` tag. When nothing has gone out, the page reads "No counted request has left this machine."

The counters are held in memory. They start at zero each time the studio starts, so they describe this session, not all time.

## Turn it all off

Set `INOX_NO_EGRESS=1` before you start the studio. Every category is then refused, including the ones on by default, and the ledger shows "INOX_NO_EGRESS IS SET. NOTHING MAY OPEN A CONNECTION."

A refusal does not always look like an error. A refused **Send to LinkedIn** fails with a message naming the flag. A refused writing action or **Generate** falls back to local output instead: template text, or a drawn placeholder image. The ledger's `refused` count is where that shows.

To switch a single category, set its flag from the table to `1` (allow) or `0` (refuse). These are environment variables of the server process, so set them in the terminal before starting it. `launch_studio.bat` sets none of them. The studio reads them on every request, but a variable set in another window does not reach a server that is already running.

## Two things the ledger cannot count

The page says so itself:

- **Opening LinkedIn in your browser from the studio.** Your browser contacts LinkedIn directly with your own login. The `linkedin` counter can read zero right after this.
- **A connected MCP source.** It is a separate program on your computer, and whatever it does on the network is outside the studio's view. `INOX_NO_EGRESS` cannot stop it.

The browser extension talks to the local studio at `127.0.0.1:8000`, not to a server of ours. When it sees certain LinkedIn API requests, it forwards the address without its query string, the status code and the method, with authentication fields removed. It also copies your LinkedIn session cookies to the local studio every 15 minutes. See [Install the browser extension](install-the-browser-extension.md).

## Who can talk to the studio

- **Loopback only.** A request addressed to anything other than a loopback name such as `127.0.0.1`, `localhost` or `::1` gets "This server answers on loopback only."
- **Allowed origins.** When a browser sends an API call, it is accepted only from the studio's own page and the extension. Any other website gets "This origin is not permitted to use the local studio." A call with no origin, such as from a local script, still needs the token.
- **A token.** API calls must carry the studio token or get "Missing or invalid studio token." The token is set as an HttpOnly, SameSite=Strict cookie when the studio page loads, so scripts and other sites cannot borrow it.

> [!WARNING]
> If you entered your AI key in the studio, it is stored unencrypted in the local database. It does not leave the machine because of that, but every backup carries it. See [Back up, restore or export your data](back-up-restore-and-export.md).

## If it does not work

| You see | What it means | What to do |
| --- | --- | --- |
| EGRESS LEDGER UNAVAILABLE | The page could not read the counters from the server | Reload the studio. If it persists, see [The studio will not open or shows an error](the-studio-will-not-open.md) |
| A category shows `OFF` you did not expect | `INOX_NO_EGRESS` or that category's flag is set in the server's environment | Close the server, clear the variable, start it again |
| A category you set to `1` still shows `OFF` | `INOX_NO_EGRESS=1` overrides every category | Remove `INOX_NO_EGRESS` |
