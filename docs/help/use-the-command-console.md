# What the Command console does, with or without an AI provider

Run an instruction in Command, and see exactly what comes back with no AI provider and with one.

## Check the banner first

Under the **Command** heading is a line showing which engine will answer:

| Banner | Meaning |
| --- | --- |
| `ANTIGRAVITY LOCAL ENGINE (DETERMINISTIC ZERO-EGRESS)` · **STAYS ON THIS MACHINE** | No provider is configured. Nothing is sent anywhere. |
| `<PROVIDER> (<MODEL>)` · **SENT TO THE PROVIDER** | A provider is configured. Your instruction goes to it. |

If there is no banner at all, the studio could not read its AI status. It does not guess, so check the server is running before typing anything you would not want sent.

## Run an instruction

1. Choose **Command** in the rail.
2. Type in the **Instruction** box.
3. Press Enter, or the arrow button beside the box (read aloud as "Run the command"). Shift+Enter starts a new line. The button stays disabled while the box is empty.

Only your instruction is sent to the studio's server. Your draft is not attached. The server keeps the first 5,000 characters.

## With no provider

You get the same fixed post every time. Only one sentence changes. The studio takes the first non-empty line of your instruction, removes a leading "write", "create", "draft", "stepping into", "how to" or "why", and drops the rest into this template:

```
Zero manual intervention.   (in Unicode bold)

That is the single metric that matters when building systems around <your line>.

Here is why:

Most teams focus on typing faster.
Top practitioners focus on deterministic architecture.

Three principles that compound over time:

1. Decouple business logic from transient storage.
2. Make every state transition auditable.
3. Eliminate manual handoffs between teams.

Simple principles. Difficult discipline.

What is your team's standard?
```

So "Write a post about onboarding" gives "...building systems around a post about onboarding." The label "Antigravity Local Engine" is only the name of this template. No model runs.

## With a provider

The studio sends `Command: <your instruction>` to your provider, together with its own fixed writing rules (no em or en dashes, no buzzwords, short paragraphs, a strong first line, end on a question), and asks for up to 1,500 tokens. The reply is cleaned of dashes before you see it.

If the provider call fails, you get the local template above instead, with `engine` set to `Antigravity Local Engine`. The studio never falls back to a different provider. To set one up, see [Connect your own AI provider](connect-your-own-ai-provider.md).

## Read the output

Each result appears as a block of JSON with three fields:

- `status`: `success`.
- `engine`: who wrote it, for example `Antigravity Local Engine` or your provider and model.
- `output`: the text itself.

Line breaks inside `output` show as `\n`. To reuse the text, copy what is between the quotes after `output` and replace each `\n` with a real line break in the editor. See [Write, format and save a post](write-format-and-save-a-post.md).

## What it cannot do

The placeholder says "Ask the engine to do something with your draft or your pipeline" and the rail calls it "Agent runs and local model routing". Neither is accurate today:

- It does not read your draft, the queue, leads or analytics.
- It runs no agents and takes no actions.
- It does not save or insert its output anywhere.
- The log is kept only on the page. It is cleared when you switch to another surface or reload.

## If it does not work

| What you see | What it means |
| --- | --- |
| An entry marked **REFUSED** | The server rejected or could not answer the request. The text under it is the server's message, or a status code such as `500`. |
| No banner | The AI status could not be read. The server may be down; see [The studio will not open](the-studio-will-not-open.md). |
| The same post every time | No provider is configured, or its call failed. Check `engine` in the output. |
| **NOTHING RUN YET IN THIS SESSION** after you ran something | You left Command or reloaded, which clears the log. |
