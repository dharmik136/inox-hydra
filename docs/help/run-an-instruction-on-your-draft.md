# Run an instruction on your draft, with or without an AI provider

Type an instruction beside your draft, and see exactly what comes back with no AI provider and with one.

## Where it is

The instruction box is in the **Composer**, in the inspector's **Prompt** tab: open the Composer, open the inspector if it is closed, and choose **Prompt**. It used to be a **Command** section of its own on the rail, which could act on nothing but the draft and could not put its answer back into it.

Above the box, the same tab says which engine will answer and whether anything leaves this machine:

| What it says | Meaning |
| --- | --- |
| Mode **Built-in templates, no model**, Egress **NONE, RUNS LOCALLY** | No provider is configured. Nothing is sent anywhere. |
| Mode **Your provider**, with its name and model, Egress **SENDS TO PROVIDER** | A provider is configured. Your instruction goes to it. |

If the studio cannot read its AI status, the tab says so and the instruction box still works. It does not guess which engine will answer, so the answer itself names the one that wrote it.

## Run an instruction

1. Type in the **Instruction** box.
2. Tick **Include my draft** to send the draft with it. Left unticked, only your instruction is sent. The box is disabled while the editor is empty, and says so.
3. Press Enter, or the arrow button beside the box (read aloud as "Run the command"). Shift+Enter starts a new line. The button stays disabled while the box is empty.

The server keeps the first 5,000 characters of an instruction.

## With no provider

You get the same fixed post every time. Only one sentence changes. The studio takes the first non-empty line of your instruction, removes a leading "write", "create", "draft", "stepping into", "how to" or "why", and drops the rest into a built-in template that ends on a question. So "Write a post about onboarding" gives "...building systems around a post about onboarding." No model runs, and nothing leaves this machine.

## With a provider

The studio sends `Command: <your instruction>` to your provider, with your draft when you ticked the box, together with its own fixed writing rules (no em or en dashes, no buzzwords, short paragraphs, a strong first line, end on a question), and asks for up to 1,500 tokens. The reply is cleaned of dashes before you see it. What else goes with a request is listed in the same tab, under what the provider receives.

If the provider call fails, you get the local template above instead, and the entry names the engine that answered. The studio never falls back to a different provider. To set one up, see [Connect your own AI provider](connect-your-own-ai-provider.md).

## Read and use the answer

Each run is listed under the box, newest first, with:

- **RAN** or **REFUSED**, and the engine that answered.
- Your instruction.
- The answer, as text with its line breaks.
- **Sent with it:** the things that went to the provider with your instruction, when one was used.

Press **COPY** beside an answer to put it on the clipboard, then paste it into the editor. See [Write, format and save a post](write-format-and-save-a-post.md).

## What it cannot do

- It does not read the queue, your leads or your analytics. The draft is the only thing it can be given, and only when you tick the box.
- It runs no agents and takes no actions.
- It does not write its answer into the draft for you. Copy it across.
- The log is kept only on the page. It is cleared when you leave the Composer or reload.

## If it does not work

| What you see | What it means |
| --- | --- |
| An entry marked **REFUSED** | The server rejected or could not answer the request. The text under it is the server's message, or a status code such as `500`. |
| The tab says the engine status is unavailable | The studio could not read which engine answers. An instruction still runs; the answer names the engine. If nothing answers at all, see [The studio will not open](the-studio-will-not-open.md). |
| The same post every time | No provider is configured, or its call failed. The engine named beside each run tells you which. |
| **NOTHING RUN YET IN THIS SESSION** after you ran something | You left the Composer or reloaded, which clears the log. |
