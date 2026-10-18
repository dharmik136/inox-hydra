---
type: source
status: live
tags:
  - source
  - ai
  - grounding
code: studio/backend/mcp_client/grounding.py
---

# MCP Grounding

Starts the creator's own MCP servers over stdio and reads up to 3 resources per server, 1500 bytes each, 6 KB total. Added switched off. Nothing is stored.

**Feeds:** [[Content Copilot]] hook prompts.

This is the door an Obsidian vault already fits through: point a filesystem MCP server at the exported vault and the copilot reads the creator's own notes. See [[Vault as AI Context]].
