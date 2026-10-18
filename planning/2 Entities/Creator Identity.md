---
type: entity
status: live
tags:
  - entity
  - identity
  - table
code: studio/backend/migrations.py
---

# Creator Identity

`creator_identity`, one row. Vanity, profile URL, display name, headline, location, about, current company, follower and connection counts, contact details, candidate fields, `confirmed_at`.

**Filled by:** [[Own Profile Reader]], later [[LinkedIn Data Archive Import]].

**Gates:** the confirmed vanity is what the [[Engagement Gate]] and every own-post write check against.

**Should feed:** [[Voice Pack]]. Today it feeds nothing AI. [[Gap - Profile never reaches AI]].
