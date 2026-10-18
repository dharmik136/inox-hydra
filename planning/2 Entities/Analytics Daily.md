---
type: entity
status: live
tags:
  - entity
  - metrics
  - table
code: studio/backend/database.py
---

# Analytics Daily

`analytics_daily`, keyed by date. Followers, connections, profile views, impressions, reach, reactions, comments, shares, engagement rate, source (observed or seed), period label, precision.

**Filled by:** [[Creator Analytics Reader]], [[Voyager Interceptor]] (followers only).

Rule: a figure nobody read is NULL and shows as "not measured", never 0. Seeded demo rows say so on screen.
