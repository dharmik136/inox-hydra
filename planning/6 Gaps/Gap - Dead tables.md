---
type: gap
status: open
tags:
  - gap
  - schema
---

# Gap - Dead tables

`post_dwell_metrics` has no writer. `lead_enrichments` is behind routes that answer 410. `inspirations` is recreated empty on every boot. [[Audience Demographics]] has an ingest path and no sender.

**Fix:** retire them through a migration, or give each one a writer. A table nothing fills is a screen that will one day show nothing as if it were a finding.
