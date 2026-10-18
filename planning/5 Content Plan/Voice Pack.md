---
type: plan
status: partial
tags:
  - plan
  - ai-context
---

# Voice Pack

Context so drafts sound like the creator, not like a model.

**Contents** (about 1,200 tokens):
- headline, about (trimmed), current role and the two before it, top skills, from [[Creator Identity]] and [[Creator Positions and Skills]];
- three to five of their own posts that brought the most qualified leads, in full, from [[Own Post]];
- measured habits: median length, line break rhythm, how often they open with a question, emoji and hashtag use, computed locally from [[Own Post]].

**Consumers:** [[Content Copilot]], [[Hook Generator]], [[Repurposer]], [[DM Drafter]].

**Egress:** it is the creator's own public profile and posts. Sent to a cloud model only when one is configured, and the provenance line says so.

**Built 2026-10-18, first consumer:** `studio/backend/voice_pack.py` builds the who, habits and openers parts, each only when there is data for it (habits need 3 posts; who needs a confirmed profile). The [[Content Copilot]] carries it as `author_voice` and records which parts it sent in the provenance as `voice_pack`. Tests: `tests/test_voice_pack.py`.

**Still to wire:** [[Hook Generator]], [[Repurposer]], [[DM Drafter]].

Closes [[Gap - Profile never reaches AI]].
