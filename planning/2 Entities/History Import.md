---
type: entity
status: live
tags:
  - entity
  - onboarding
  - table
code: studio/backend/onboarding.py
---

# History Import

`self_import_requests`. The studio asks, the extension scrolls the creator's activity pages and reads as it goes, and stops when told to, when the tab is hidden, or after a fixed number of rounds. Chains posts, then comments, then reactions.

The scroll only ever happens because the creator clicked something. The sanctioned alternative is [[LinkedIn Data Archive Import]].
