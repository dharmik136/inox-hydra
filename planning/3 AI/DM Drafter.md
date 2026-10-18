---
type: ai
status: live
tags:
  - ai
  - people
  - writing
code: studio/backend/leads.py
---

# DM Drafter

Drafts a first message from a lead's own record: name, company, headline, what they commented, the post they engaged with. Three styles: peer question, offer a blueprint, suggest a call. Nothing is sent; LinkedIn DMs are not something the studio does.

**Weak spot:** `suggested_dm_reply` is always empty from capture, because the reader sends no post topic. **Out:** [[Lead Dossier and DM]].
