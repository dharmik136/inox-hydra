# Run an instruction with Command

Run an instruction from the Composer's Prompt tab, with or without a model, and see exactly what was sent.

## Where it is

Command is a block on the **Prompt** tab of the Composer's inspector. It used to be its own rail section; it moved beside the draft because the draft is the only thing it can act on.

1. Open the **Composer** from the rail.
2. Choose **Prompt** in the inspector on the right. If the inspector is closed, the panel icon in the top right corner (**Open inspector**) brings it back.

## Check the engine first

At the top of the **Prompt** tab, **Engine** gives four rows:

| Row | With no key | With a provider saved |
| --- | --- | --- |
| Mode | Built-in templates, no model | Your provider |
| Provider | None set up | The provider you chose |
| Model | None | The model you typed |
| Egress | NONE, RUNS LOCALLY, in green | SENDS TO PROVIDER, in orange |

If a saved key has stopped working, a line under the rows gives the provider's own reason and when it failed, and stays until a request succeeds.

## Run an instruction

1. Type in the **Instruction** box. The placeholder reads "Tell the model what to write. Tick the box below to include your draft."
2. To have the model work on what you are writing, tick **Include my draft** underneath first. It is greyed out while the editor is empty, and says so: "(the editor is empty)".
3. Press Enter, or the arrow button beside the box (read aloud as "Run the command"). Shift+Enter starts a new line. Nothing runs while the box is empty.

## With no model

Nothing is written for you, and the answer says so rather than inventing one: "No model is set up, so nothing was written for this instruction." It points you at connecting a provider on this tab, and reminds you that **Re-Hook** still offers fill-in templates built around your own words and that the formatting tools still work on your text.

An earlier version answered this case with a fixed post about deterministic architecture, with your first line dropped into it, offered as your own writing. It no longer does.

## With a provider

The studio sends `Command: <your instruction>`, and under `Context/Draft:` your draft, but only when you ticked **Include my draft**. With it go the studio's own writing rules (no em or en dashes, no buzzwords, short paragraphs, a first line that stops the scroll, end on a question) and what the studio knows about how you write, read from your own profile and posts. It asks for up to 1,500 tokens, and the reply is cleaned of dashes before you see it.

If the provider refuses or fails, you get its reason, not a local template, and your text is not passed to another provider. See [Connect your own AI provider](connect-your-own-ai-provider.md) and [What leaves this machine, and when](what-leaves-this-machine.md).

## Read the answer

Each run is listed under the box:

- **RAN** or **REFUSED**, with the engine that answered beside it.
- The answer itself, as text.
- "Sent with it:" naming what left the machine for that run.
- **COPY**, which puts the answer on your clipboard and reads COPIED once the browser has taken it.

Paste it into the editor yourself. No control writes an answer into your draft.

## What it cannot do

- It does not read the queue, your leads or your analytics. Your draft goes only when you tick the box.
- It runs no agents and takes no actions.
- Nothing is kept. The list lives on the page, and leaving the **Prompt** tab, leaving the Composer or reloading clears it.

## If it does not work

| What you see | What it means |
| --- | --- |
| An entry marked **REFUSED** | The request was rejected or could not be answered. The text under it is the reason, or a status code such as `500`. |
| The answer says no model is set up | No provider is saved, so nothing was written. See [Connect your own AI provider](connect-your-own-ai-provider.md). |
| No **Engine** rows at all | The studio could not read its AI status. Check the server is running before typing anything you would not want sent; see [The studio will not open](the-studio-will-not-open.md). |
| **NOTHING RUN YET IN THIS SESSION** after you ran something | You left the **Prompt** tab, left the Composer or reloaded, which clears the list. |
