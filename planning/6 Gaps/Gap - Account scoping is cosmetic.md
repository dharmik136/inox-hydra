---
type: gap
status: fixed
tags:
  - gap
  - multi-tenant
---

# Gap - Account scoping is cosmetic

**Fixed 2026-10-19:** not by filtering, but by giving each profile its own database. See [[Creator Account]]. Tests switch profiles and assert that posts, media, backups and exports stay apart.

[[Creator Account]] exists, the switcher works, but nothing filters by `account_id` and capture never sets it. The columns were also added inside `init_db()` rather than as a migration, against the repo's own rule.

**Fix:** a real migration, scoping in every router and capture path, and tests that switch accounts and assert isolation. Required before the agency tier in [[Commercial Model]]. **Phase:** [[Phase 1 - Own Data Complete]].
