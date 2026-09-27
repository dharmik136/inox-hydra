# Connect your own AI provider
Plug in your own model key so Re-Hook and the Command console use it, and see exactly what text it receives.

## You do not need one

Without a key, the text features still answer, from local templates on this machine. The **Prompt** tab says so: "NO KEY IS CONFIGURED. EVERY FEATURE ABOVE STILL ANSWERS, DETERMINISTICALLY." Image generation is the exception: even with no key it sends a prompt to an outside image service (see [Add images and files to your media library](add-images-to-your-media-library.md)). A key changes who writes the text, and it means some of your text leaves your machine.

## Providers

| Provider id | Default model | Key | Requests go to |
| --- | --- | --- | --- |
| `gemini` | `gemini-2.5-flash` | Required | Google |
| `openai` | `gpt-4o` | Required | OpenAI |
| `anthropic` | `claude-3-5-sonnet-20241022` | Required | Anthropic |
| `groq` | `llama-3.3-70b-versatile` | Required | Groq |
| `ollama` | `llama3:latest` | None | `http://localhost:11434/v1` |
| `custom_openai` | `default` | Optional | `http://localhost:8080/v1` |
| `local_deterministic` | `deterministic-heuristics-v2` (local templates) | None | Nowhere |

`custom_openai` saves without a key, but the studio only uses it once a key is saved. Until then, features keep answering from local templates.

## Connect

1. Open **Composer** from the rail.
2. If the inspector is closed, click **Open inspector** at the top right, or press Ctrl+K and choose **Toggle inspector**.
3. Choose the **Prompt** tab.
4. Under **Connect a provider**, pick the provider id from the list.
5. Paste your key into the **API key** field. Leave it empty for `ollama`.
6. Click **Verify and save**. The note reads "Connected." and the **Egress** row changes to SENDS TO PROVIDER. For `custom_openai` without a key it stays NONE, RUNS LOCALLY.

## What happens

**Verify and save** first sends a short test request to the provider. If that fails, nothing is saved and your previous settings stay. If it succeeds, the provider, key, model and base URL are written to the settings table in your local database.

> [!WARNING]
> The panel says the key is stored in an encrypted vault. It is not. The key is stored as plain text in the local database. Backups contain it. Exports leave it out, and the diagnostics bundle records only whether it is set and how long it is.

Once connected, this is what reaches the provider:

| Feature | What is sent |
| --- | --- |
| **Re-Hook** on a selection | A prompt built from the first line of your selection |
| **Command** console | Your instruction only, never your Composer draft |
| **Media** tab, **Preview prompt** and **Generate** | Your image description, so the model can describe the scene |
| **Media** tab **Generate**, with `openai` or `gemini` | The image prompt, to DALL-E 3 or Imagen 3 |
| **Audit** tab, and message drafts on **Leads** | Nothing. These always run locally. |

The **Prompt** tab also lists Repurposing and Tailored DMs, but no control in this interface repurposes text, and message drafts never use the model.

If a provider call fails, Re-Hook and Command fall back to local output. Your text is not passed to any other provider.

If no key is saved in the studio, which is always the case for `ollama`, it uses `OPENAI_API_KEY`, `GEMINI_API_KEY` or `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, or `GROQ_API_KEY` from your environment, in that order, and that provider replaces the one you chose. Starting the studio with `INOX_ALLOW_MODEL_EGRESS=0` or `INOX_NO_EGRESS=1` refuses all model traffic.

## Use the Command console

1. Open **Command** from the rail.
2. Check the banner: it shows the active mode, then STAYS ON THIS MACHINE (no key) or SENT TO THE PROVIDER.
3. Type in the **Instruction** box. Enter runs it. Shift+Enter adds a new line.

The placeholder mentions your draft, but the console does not send it. Paste any text you want used. With no key, the console returns a fixed template post built around the first line of your instruction.

## Go back to local only

Choose `local_deterministic` in the **Prompt** tab, leave the key field empty and click **Verify and save**, or run this in the folder that holds `studio_cli.py`:

`python studio_cli.py ai reset`

Both save an empty key. If you had connected `gemini`, a second copy of that key stays in the settings table under `gemini_api_key`, and neither route removes it. If one of the environment variables above is set, the studio will pick that key up instead, so remove it too.

## Set a model or a base URL

The interface has no model or base URL field. Use the command line:

`python studio_cli.py ai configure --provider ollama --model mistral:latest --base-url http://localhost:11434/v1`

A saved base URL applies only to `ollama` and `custom_openai`. It must use https unless the host is `localhost` or a loopback or private IP address; otherwise the default address is saved in its place, with no warning. For other providers the saved setup ignores it. The test request always goes to the address you typed, with your key, even when the saved setup then ignores or replaces it. `ai list-providers`, `ai status` and `ai test` show the options, the saved setup, and a live check of the saved setup.

## If it does not work

| You see | What it means |
| --- | --- |
| A bare "400" under **Verify and save** | The test request failed. Nothing was saved. The panel does not show why. Run `python studio_cli.py ai configure --provider <id>`: it asks for the key and prints the reason, such as a rejected key or Ollama not running. `ai test` only checks the setup already saved. |
| ENGINE STATUS UNAVAILABLE | The tab could not reach the studio's server. Reload the page, then see [The studio will not open or shows an error](the-studio-will-not-open.md). |
| Command output that looks like JSON | Expected. Read the `output` field; `engine` names who wrote it. Line breaks show as `\n`. |

See also [What leaves this machine, and when](what-leaves-this-machine.md).
