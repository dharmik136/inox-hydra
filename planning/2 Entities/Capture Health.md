---
type: entity
status: live
tags:
  - entity
  - health
  - table
code: studio/backend/onboarding.py
---

# Capture Health

`captures` (7 days), `bridge_heartbeats` (7 days), `schema_drift_events` (30 days). Every extractor run records what it saw and what it kept, so a broken LinkedIn selector shows up as a number going to zero instead of a feature quietly emptying.

**Filled by:** every source, [[Bridge Heartbeat]]. **Shown in:** Setup.
