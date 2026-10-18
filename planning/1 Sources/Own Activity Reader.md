---
type: source
status: live
tags:
  - source
  - extension
code: studio/extension/own_pages.js
---

# Own Activity Reader

Reads the creator's own activity feeds: posts they wrote, comments they left elsewhere, posts they reacted to.

**Reads on:** `/in/<you>/recent-activity/all/`, `/comments/`, `/reactions/`.

**Captures:** posts (URN, text with line breaks, reactions, comments, reposts, impressions); comments (target URN, the creator's text, target author name, 300 char excerpt); reactions (target URN, kind, target author, excerpt).

**Sends to:** `/api/v1/self/posts/ingest` and `/api/v1/self/outbound/ingest`.

**Writes:** [[Own Post]], [[Post Metric Observation]], [[Outbound Engagement]]. Scrolling back through history only happens on request: [[History Import]].

**Guard:** an activity page is read only when it is the creator's. See [[Fixed - me alias could file another account]].
