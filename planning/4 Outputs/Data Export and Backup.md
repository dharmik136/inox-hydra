---
type: output
status: partial
tags:
  - output
  - portability
code: studio/backend/support.py
---

# Data Export and Backup

`python -m studio.cli export --format json|csv|obsidian`, `/api/v1/support/export`, and `backup` / `restore`.

The JSON and CSV exports carried drafts, studio posts, leads, interactions, daily analytics, demographics and the queue, but none of the creator's own LinkedIn record. [[Gap - Export omits your own data]].
