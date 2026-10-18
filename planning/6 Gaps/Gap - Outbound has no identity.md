---
type: gap
status: open
tags:
  - gap
  - people
---

# Gap - Outbound has no identity

[[Outbound Engagement]] stores the target author's display name only, so "did they engage back" is a name match. Two people with one name merge; a renamed person splits.

**Fix:** read the author's profile link from the activity card, and match against [[Connection]] once the archive import exists.
