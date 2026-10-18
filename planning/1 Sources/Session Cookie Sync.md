---
type: source
status: live
tags:
  - source
  - extension
  - secrets
code: studio/extension/background.js
---

# Session Cookie Sync

Only when the creator presses Sync in the popup: reads the `li_at` and `JSESSIONID` cookies and hands them to the studio, which seals them at rest.

**Writes:** [[Settings Vault]].

**Enables:** profile sync from `/voyager/api/me` and the [[Native Scheduler Handoff]]. Both stay blocked unless `INOX_ALLOW_LINKEDIN_EGRESS=1`, because a request from the studio to LinkedIn is the one thing the product otherwise never does.
