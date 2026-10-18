---
type: entity
status: live
tags:
  - entity
  - metrics
  - table
code: studio/backend/migrations.py
---

# Post Metric Observation

`post_metric_observations`: one reading of a post's figures with the post's age at that moment. Unique per (urn, source, hour). Sources: `activity_page`, `post_analytics`, `voyager_network`.

The time series that lets [[Today Brief]] compare a post at 48 hours against the creator's own usual at 48 hours, instead of comparing a two-hour-old post to a two-week-old one.
