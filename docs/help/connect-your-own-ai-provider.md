# Connect your own AI provider
Plug in your own model key so Re-Hook and the instruction box use it, and see exactly what text it receives.

## You do not need one

Without a key, nothing writes for you. **Re-Hook** offers fill-in templates built around your own words, with a [bracket] wherever a fact of yours belongs, and the hook rail says they are templates. Replace every bracket before you post. The formatting tools and the **Audit** tab work as usual. **Command**, on the same tab, needs a model and says so. The **Prompt** tab sums this up: "NO KEY IS CONFIGURED. RE-HOOK OFFERS FILL-IN TEMPLATES AND THE AUDIT RUNS HERE. COMMAND NEEDS A MODEL." Image generation is the exception: even with no key it sends a prompt to an outside image service (see [Add images and files to your media library](add-images-to-your-media-library.md)). A key changes who writes the text, and it means some of your text leaves your machine.

## Providers

| Provider id | Default model | Key | Requests go to |
| --- | --- | --- | --- |
| `gemini` | `gemini-2.5-flash` | Required | Google |
| `openai` | `gpt-4o` | Required | OpenAI |
| `anthropic` | `claude-sonnet-5-5` (also `claude-opus-5-5`, `claude-haiku-5-5`) | Required | Anthropic |
| `groq` | `llama-3.3-70b-versatile` | Required | Groq |
| `ollama` | `llama3:latest` | None | `http://localhost:11434/v1` |
| `custom_openai` | `default` | Optional | `http://localhost:8080/v1` |
| `local_deterministic` | `deterministic-heuristics-v2` (local templates) | None | Nowhere |

`custom_openai` saves without a key, but the studio only uses it once a key is saved. Until then, features keep answering from local templates.

## Connect

1. Open **Composer** from the rail.
2. If the inspector is closed, click **Open inspector** at the top right, or press Ctrl+K and choose **Show or hide the inspector**.
3. Choose the **Prompt** tab.
4. Under **Connect a provider**, pick the provider id from the list. The **Model** field fills with that provider's default.
5. To use another model, type its name in **Model** or pick one of the suggestions.
6. Paste your key into the **API key** field. Leave it empty for `ollama`.
7. Click **Verify and save**. The note reads "Connected." and the **Egress** row changes to SENDS TO PROVIDER. For `custom_openai` without a key it stays NONE, RUNS LOCALLY.

## What happens

**Verify and save** first sends a short test request to the provider. If that fails, nothing is saved and your previous settings stay. If it succeeds, the provider, key, model and base URL are written to the settings table in your local database.

> [!NOTE]
> The key is sealed before it is saved, the same way as your LinkedIn session: with Windows' own data protection on Windows, and the studio's local vault key on macOS and Linux. The database holds the sealed form, never the key as typed. A key saved by an older version is sealed the next time the studio starts. Because the seal is tied to this computer and your account on it, a database or backup moved elsewhere reads as having no key, and you enter it again there. Exports leave the key out, and the diagnostics bundle records only whether it is set and how long it is.

Once connected, this is what reaches the provider:

| Feature | What is sent |
| --- | --- |
| **Re-Hook** on a selection | A prompt built from the first line of your selection |
| **Instruction** box | Your instruction, and your draft only when **Include my draft** is ticked |
| **Media** tab, **Preview prompt** and **Generate** | Your image description, so the model can describe the scene |
| **Media** tab **Generate**, with `openai` or `gemini` and no image provider chosen | The image prompt, to OpenAI Images or Google Imagen with this key. Choose another under **Images** in the **Prompt** tab |
| **Audit** tab, and message drafts on **Leads** | Nothing. These always run locally. |

Re-Hook and Command also send what the studio knows about how you write, so the model matches your voice rather than a generic one. It is read from your own profile and posts, and only the parts the studio has go:

- once you have confirmed your profile: your headline, your current role and up to two earlier roles, the skills on your profile, and the first 400 characters of your About section
- once at least three of your posts are imported: how your posts are usually shaped (length, paragraphs, opening questions, emoji and hashtags)
- the opening lines of your 3 most-reacted posts

The **Prompt** tab lists exactly which of these the studio holds for you, under **What a provider would receive**, and each Command answer ends with what was sent with it. The model is told not to mention your title or employer unless your text does. There is no setting that leaves this out while a provider is connected.

The **Prompt** tab also lists Repurposing and Tailored DMs, but no control in this interface repurposes text, and message drafts never use the model.

If a provider call fails, Re-Hook and Command say so and give the provider's reason, such as a refused key or an account out of credit, and the **Prompt** tab shows the last failure until a request succeeds. Nothing is replaced with local templates, and your text is not passed to any other provider. A request that has not finished after 40 seconds is stopped. While one Re-Hook is running, pressing it again does nothing.

If no key is saved in the studio, which is always the case for `ollama`, it uses `OPENAI_API_KEY`, `GEMINI_API_KEY` or `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, or `GROQ_API_KEY` from your environment, in that order, and that provider replaces the one you chose. Starting the studio with `INOX_ALLOW_MODEL_EGRESS=0` or `INOX_NO_EGRESS=1` refuses all model traffic.

## Use the instruction box

1. Open the **Composer**, then the **Prompt** tab in the inspector. Command is a block on that tab; it is no longer a rail section.
2. Check the **Engine** rows above it: Mode, Provider, Model, and Egress, which reads NONE, RUNS LOCALLY with no key or SENDS TO PROVIDER with one.
3. Type in the **Instruction** box. Enter runs it. Shift+Enter adds a new line.
4. To have the model work on what you are writing, tick **Include my draft** first. The box is greyed out while the editor is empty.

Each answer is listed under your instruction, with the engine that wrote it beside RAN, and a **COPY** control. With no key, it answers that no model is set up and writes nothing. See [Run an instruction on your draft](run-an-instruction-on-your-draft.md).

## Go back to local only

Choose `local_deterministic` in the **Prompt** tab, leave the key field empty and click **Verify and save**, or run this in the folder that holds `studio_cli.py`:

`python studio_cli.py ai reset`

Both save an empty key. If you had connected `gemini`, a second copy of that key stays in the settings table under `gemini_api_key`, and neither route removes it. If one of the environment variables above is set, the studio will pick that key up instead, so remove it too.

## Set a base URL

The **Prompt** tab sets the model but has no base URL field. Use the command line:

`python studio_cli.py ai configure --provider ollama --model mistral:latest --base-url http://localhost:11434/v1`

A saved base URL applies only to `ollama` and `custom_openai`. It must use https unless the host is `localhost` or a loopback or private IP address; otherwise the default address is saved in its place, with no warning. For other providers the saved setup ignores it. The test request goes to the same address the saved setup will use, so a passing test is a test of what is saved. `ai list-providers`, `ai status` and `ai test` show the options, the saved setup, and a live check of the saved setup.

## If it does not work

| You see | What it means |
| --- | --- |
| A bare "400" under **Verify and save** | The test request failed. Nothing was saved. The panel does not show why. Run `python studio_cli.py ai configure --provider <id>`: it asks for the key and prints the reason, such as a rejected key or Ollama not running. `ai test` only checks the setup already saved. |
| ENGINE STATUS UNAVAILABLE | The tab could not reach the studio's server. Reload the page, then see [The studio will not open or shows an error](the-studio-will-not-open.md). |

See also [What leaves this machine, and when](what-leaves-this-machine.md).
