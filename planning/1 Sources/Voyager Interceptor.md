---
type: source
status: partial
tags:
  - source
  - extension
  - network
  - risk
code: studio/extension/voyager_interceptor.js
---

# Voyager Interceptor

Runs inside LinkedIn's own page and copies the JSON of `/voyager/api/` responses LinkedIn's app already fetched. Read only, 30 per minute, 2 MB cap.

**Schemas:** `feed_updates`, `identity_profiles`, `creator_analytics`, `social_actions`, `feed_comments`.

**Sends to:** `/api/v1/bridge/voyager-ingest`, plus top-level key drift to `/api/v1/bridge/schema-drift`.

**Kept today:** feed update counts into [[Post Metric Observation]], and the follower count into [[Analytics Daily]]. Everything else only reaches [[Capture Health]].

**Status:** the analytics half never wrote at all until [[Fixed - Voyager analytics column]]. Three schemas are still discarded: [[Gap - Voyager data discarded]].

**Risk:** this is the most visible part of the product to LinkedIn. It wraps `window.fetch`, which the README says the product does not do. See [[Risk - LinkedIn terms and detection]] and [[Gap - Claims the code contradicts]].
