---
type: gap
status: closed
tags:
  - gap
  - extension
---

# Gap - Voyager data discarded

**Closed in 2.10.2:** network reading was retired with the [[Voyager Interceptor]], so nothing is intercepted and nothing is discarded.

[[Voyager Interceptor]] sends `identity_profiles`, `social_actions` and `feed_comments`, and the backend only logs that they arrived. Feed update URNs may not match the activity URN pattern either; check against a captured payload.

**Decision needed:** either use them (engager headlines from `identity_profiles` would fix [[Gap - Lead fields mislabelled]]) or stop intercepting them. Intercepting data and throwing it away carries the risk with none of the value. See [[Risk - LinkedIn terms and detection]].
