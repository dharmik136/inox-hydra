---
type: entity
status: live
tags:
  - entity
  - post
  - table
code: studio/backend/database.py
---

# Studio Post

`posts`: the studio's own record of a post. Content, media, status (draft, scheduled, published), schedule, tags, `activity_urn` once bound, a content fingerprint, `draft_id`.

**Bound to:** [[Own Post]] by [[Post Permalink Binder]] or by fingerprint during import.
**Comes from:** [[Draft]], [[Telegram Ingress]].
**Goes to:** [[Queue]], [[Native Scheduler Handoff]].
