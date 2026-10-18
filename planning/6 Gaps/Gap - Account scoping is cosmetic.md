---
type: gap
status: open
tags:
  - gap
  - multi-tenant
---

# Gap - Account scoping is cosmetic

[[Creator Account]] exists, the switcher works, but nothing filters by `account_id` and capture never sets it. The columns were also added inside `init_db()` rather than as a migration, against the repo's own rule.

**Fix:** a real migration, scoping in every router and capture path, and tests that switch accounts and assert isolation. Required before the agency tier in [[Commercial Model]]. **Phase:** [[Phase 1 - Own Data Complete]].
