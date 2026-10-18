---
type: entity
status: live
tags:
  - entity
  - multi-tenant
code: studio/backend/accounts.py
---

# Creator Account

**One database per creator profile, since 2026-10-19** (owner's decision). Each profile is a folder with its own database, media, backups and exports; the default profile is the application home, so existing data stayed put, and the others live in `profiles/<id>/`, listed in `profiles/profiles.json`. Every request is pinned to one profile, `/assets` serves the active profile's media, and the scheduler visits every profile's queue. More than one profile needs the Agency licence.

The old `creator_accounts` table and the `account_id` columns remain in each database but nothing reads them; their rows were adopted into the registry. [[Gap - Account scoping is cosmetic]] is closed.

This is the foundation of the agency tier in [[Commercial Model]].
