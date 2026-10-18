---
type: gap
status: fixed
tags:
  - gap
  - portability
---

# Gap - Export omits your own data

[[Data Export and Backup]] exported drafts, studio posts, leads and analytics, but not [[Creator Identity]], [[Own Post]], [[Post Metric Observation]], [[Outbound Engagement]] or [[Lead Stage Event]]. The creator's most valuable record could not be taken elsewhere, which is both a portability promise broken and a data-access question under GDPR and DPDP.

**Fixed 2026-10-18:** the JSON and CSV exports carry all of those tables (credentials still excluded), and the [[Obsidian Vault Export]] writes the same record as linked notes.
