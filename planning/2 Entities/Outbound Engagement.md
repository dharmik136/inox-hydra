---
type: entity
status: partial
tags:
  - entity
  - people
  - table
code: studio/backend/migrations.py
---

# Outbound Engagement

`outbound_engagements`: the creator's comments and reactions on other people's posts. Target URN, target author (display name only), excerpt, kind, the creator's text.

**Filled by:** [[Own Activity Reader]]. **Feeds:** [[Insights Engine]] (who you engage with, and whether they come back), [[Outbound Pack]].

Matched to leads by display name only: [[Gap - Outbound has no identity]].
