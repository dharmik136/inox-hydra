---
type: gap
status: fixed
tags:
  - gap
  - extension
  - fixed-2026-10-18
---

# Fixed - Voyager analytics column

`record_voyager_ingest` inserted into `analytics_daily.observation_window`, a column that never existed. Every creator analytics reading from [[Voyager Interceptor]] raised, rolled back, and took its [[Capture Health]] row with it.

Fixed 2026-10-18: follower count stored for today; the `impressionAggregate` is not stored as a day because its window is unknown; unread figures are NULL. Test: `tests/test_voyager_ingest_writes.py`.
