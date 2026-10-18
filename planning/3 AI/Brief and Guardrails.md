---
type: ai
status: live
tags:
  - ai
  - plumbing
  - quality
code: studio/backend/agno_agentos/briefing.py
---

# Brief and Guardrails

`Brief` builds every prompt from labelled sections (role, objective, inputs, constraints, forbidden, output format). `validate_response` strips preambles, enforces length and forbidden terms. `scar_tissue` holds the banned phrases, removes em-dashes and checks the 140 character fold. `provenance` records whether a model or a template wrote the text.

**Applies to:** every agent in this folder. **Rules:** [[Data Rules for AI]].
