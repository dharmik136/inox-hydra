---
type: entity
status: live
tags:
  - entity
  - schedule
  - table
code: studio/backend/database.py
---

# Queue

`queue_items` (draft, slot) and `queue_slots` (day of week, time). The calendar the creator posts against.

**Read by:** [[Today Brief]], cadence in [[Insights Engine]]. **Hands off to:** [[Native Scheduler Handoff]].
