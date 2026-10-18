---
type: source
status: live
tags:
  - source
  - extension
  - metrics
code: studio/extension/own_pages.js
---

# Post Analytics Reader

Reads one post's analytics page when the creator opens it.

**Reads on:** `/analytics/post-summary/urn:li:activity:N`.

**Captures:** members reached, impressions, reactions, comments, reposts, saves, sends.

**Sends to:** `/api/v1/self/posts/analytics`.

**Writes:** [[Post Metric Observation]] (source `post_analytics`) and the latest impressions on [[Own Post]].
