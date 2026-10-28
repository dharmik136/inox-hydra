---
type: source
status: retired
tags:
  - source
  - extension
  - network
  - risk
code: studio/extension/voyager_interceptor.js (removed in 2.10.2)
---

# Voyager Interceptor

**Retired in 2.10.2 (2026-10-28, owner's decision).** Testing on the owner's own account showed LinkedIn's 2026 web app makes no `/voyager/api/` requests: its data arrives through React Server Component actions (`/flagship-web/rsc-action/...`) in an internal streaming format, so the interceptor read nothing. It, its schema registry, the observer, the popup switch and the `webRequest` permission are gone (`tests/test_network_reading_retired.py`), and the studio answers an older extension's two routes "retired" and keeps nothing. The page readers, rebuilt on LinkedIn's 2026 markup in 2.10.1, and the analytics export import cover what it was meant to add. The rest of this note describes it as it was.

**Off by default since 2026-10-19** (owner's decision). It runs only after the creator switches on "Read LinkedIn's network responses" in the extension popup, where what it does is written beside the switch; while it is off, its two capture paths are refused. Retire it once [[LinkedIn Data Archive Import]] and the page readers are shown to cover what it adds.

Runs inside LinkedIn's own page and copies the JSON of `/voyager/api/` responses LinkedIn's app already fetched. Read only, 30 per minute, 2 MB cap.

**Schemas:** `feed_updates`, `identity_profiles`, `creator_analytics`, `social_actions`, `feed_comments`.

**Sends to:** `/api/v1/bridge/voyager-ingest`, plus top-level key drift to `/api/v1/bridge/schema-drift`.

**Kept today:** feed update counts into [[Post Metric Observation]], and the follower count into [[Analytics Daily]]. Everything else only reaches [[Capture Health]].

**Status:** the analytics half never wrote at all until [[Fixed - Voyager analytics column]]. Three schemas are still discarded: [[Gap - Voyager data discarded]].

**Risk:** this is the most visible part of the product to LinkedIn: it wraps `window.fetch`. The README and the extension doc now say so, and that it is off unless switched on. See [[Risk - LinkedIn terms and detection]] and [[Gap - Claims the code contradicts]].
