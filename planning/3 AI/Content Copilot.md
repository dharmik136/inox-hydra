---
type: ai
status: live
tags:
  - ai
  - writing
code: studio/backend/agno_agentos/agents/content_copilot_agent.py
---

# Content Copilot

`/api/copilot/optimize`.

**In:** the draft (first 600 chars), audience, format, media type; the [[Evidence Briefing]] (the creator's top posts by qualified leads, and conclusive pattern contrasts); [[MCP Grounding]] material.

**Out:** an optimised post, up to 10 hooks under the fold, a dwell estimate labelled as one, a fold flag, provenance including what left the machine. Returned, not stored.

**Missing input:** who the creator is. [[Voice Pack]] closes that.
