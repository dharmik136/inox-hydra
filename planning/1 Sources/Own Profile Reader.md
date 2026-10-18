---
type: source
status: live
tags:
  - source
  - extension
  - identity
code: studio/extension/own_pages.js
---

# Own Profile Reader

Reads the creator's own profile, and only theirs. Ownership is proved before anything leaves the page: LinkedIn's `isSelfProfile=true` marker, owner-only edit controls, or the `/in/me/` redirect landing on a vanity.

**Reads on:** `/in/<you>/`, `/details/experience`, `/details/education`, `/details/skills`, `/overlay/contact-info`.

**Captures:** display name, headline, location, follower and connection counts, about, positions (title, company, dates, location, description), education, skills, contact email, phone, birthday, websites.

**Sends to:** `POST /api/v1/identity/observe`. Held as a candidate until the creator confirms it is them.

**Writes:** [[Creator Identity]], [[Creator Positions and Skills]].

**The waste:** none of this reaches a prompt. See [[Gap - Profile never reaches AI]] and the fix, [[Voice Pack]].
