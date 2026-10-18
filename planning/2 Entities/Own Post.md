---
type: entity
status: live
tags:
  - entity
  - post
  - table
code: studio/backend/migrations.py
---

# Own Post

`own_posts`, keyed by `activity_urn`. Text, `published_at` (decoded from the URN: id >> 22 is milliseconds since the epoch), reactions, comments, reposts, impressions, first and last seen.

The main post node. Everything about "what worked" stands on it.

**Filled by:** [[Own Activity Reader]], [[Post Analytics Reader]], [[Voyager Interceptor]].
**Has many:** [[Post Metric Observation]], [[Lead Interaction]] (by URN).
**Bound to:** [[Studio Post]].
**Grouped by:** [[Topic]].
**Feeds:** [[Evidence Briefing]], [[Contrast Engine]], [[Insights Engine]], [[Today Brief]], [[Obsidian Vault Export]].
