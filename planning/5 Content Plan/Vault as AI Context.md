---
type: plan
status: proposed
tags:
  - plan
  - obsidian
  - ai-context
---

# Vault as AI Context

The round trip:
1. [[Obsidian Vault Export]] writes the creator's posts, people and topics as linked notes.
2. The creator thinks in Obsidian: adds notes, ideas, meeting notes against People notes.
3. A filesystem MCP server pointed at the vault is added in Brand Studio, and [[MCP Grounding]] feeds those notes into [[Content Copilot]].

The creator's own notes become grounding for the next post, without the studio storing or uploading them.

**Next step after that:** a native reader for the vault folder, so no MCP server is needed.
