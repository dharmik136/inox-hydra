---
type: entity
status: live
tags:
  - entity
  - secrets
  - table
code: studio/backend/vault.py
---

# Settings Vault

`settings`, a key/value store. Sealed at rest: the LinkedIn session cookies and the AI provider key. Plain: provider, model, creator profile JSON, MCP server list, queue status, active account.

The database file itself is not encrypted. Only these values are. See [[Gap - Claims the code contradicts]].
