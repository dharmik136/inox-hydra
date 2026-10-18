---
type: entity
status: live
tags:
  - entity
  - people
  - table
code: studio/backend/database.py
---

# Lead Interaction

`lead_interactions`: one engagement event. Lead, post URN, COMMENT, LIKE or REPOST, comment text, capture context (the page it came from), first and last seen, seen count. Unique per (lead, urn, type, comment).

The edge between a [[Lead]] and an [[Own Post]]. `capture_context` exists because a reactor once got stored from a dialog unrelated to any post, and without the page path such rows cannot be told from real ones.
