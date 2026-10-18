---
type: entity
status: partial
tags:
  - entity
  - multi-tenant
  - table
code: studio/backend/accounts.py
---

# Creator Account

`creator_accounts`: id, name, vanity, headline, initials, default flag. Drives the profile switcher in the rail.

`posts`, `drafts`, `leads`, `lead_interactions` and `settings` carry an `account_id`, but capture never sets it and no router filters by it. Switching profile changes the avatar, not the data. [[Gap - Account scoping is cosmetic]].

This is the foundation of the agency tier in [[Commercial Model]].
