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

**Also seen in a real export (2026-10-18):** one of 197 outbound authors was stored as "<Name> started a new position", the card's header line rather than the name. Strip LinkedIn's activity verbs when reading the author.
