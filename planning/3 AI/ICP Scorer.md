---
type: ai
status: live
tags:
  - ai
  - people
  - deterministic
code: studio/backend/crm.py
---

# ICP Scorer

Deterministic, no model. score = seniority x 0.45 + intent x 0.30 + company x 0.15 + comment quality x 0.10. Tiers at 80, 60, 30. Runs on every interaction ingest.

**In:** headline, company, comment text, interaction type. **Writes:** `icp_score` and seniority on [[Lead]].
