---
type: entity
status: live
tags:
  - entity
  - people
  - table
code: studio/backend/database.py
---

# Lead

`leads`: a person who engaged with the creator's posts. Name, headline, company, profile URL, pipeline status, seniority, `icp_score`, notes.

**Filled by:** [[Comment and Reaction Reader]], through the [[Engagement Gate]].
**Has many:** [[Lead Interaction]], [[Lead Stage Event]].
**Scored by:** [[ICP Scorer]]. **Drafted to by:** [[DM Drafter]].
**Shown in:** [[Lead Dossier and DM]], [[Reply Queue]], [[Obsidian Vault Export]].

Third-party personal data. See [[Risk - Personal data of third parties]].
