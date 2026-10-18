---
type: ai
status: live
tags:
  - ai
  - plumbing
code: studio/backend/agno_agentos/model_gateway.py
---

# Model Gateway

One gateway for every model call. Providers: Gemini, OpenAI, Anthropic, Ollama, Groq, any OpenAI-compatible endpoint, and a local deterministic engine that is the default and needs no key.

The key is sealed in the [[Settings Vault]]. Every call goes through the egress chokepoint under the `model` category, so the ledger can say what left the machine and when.

**Used by:** [[Content Copilot]], [[Hook Generator]], [[Repurposer]], [[Command Engine]], [[Image Prompt Agent]].
