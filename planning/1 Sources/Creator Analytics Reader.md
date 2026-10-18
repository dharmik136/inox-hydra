---
type: source
status: live
tags:
  - source
  - extension
  - metrics
code: studio/extension/content.js
---

# Creator Analytics Reader

Reads the account-level analytics cards on `/analytics/creator*`, and again after the creator changes the range.

**Captures:** impressions, engagements, followers, with the period label (1d to 365d) and a precision flag, because "1.2K" means somewhere in [1150, 1250), not 1200.

**Sends to:** `/api/analytics/ingest`. Multi-day windows are refused, since storing a 28 day total as today's figure was the original analytics defect.

**Writes:** [[Analytics Daily]] and the raw payload into the telemetry shard.
