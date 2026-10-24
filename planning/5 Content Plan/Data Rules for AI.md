---
type: plan
status: live
tags:
  - plan
  - quality
  - privacy
---

# Data Rules for AI

1. Never show or prompt with a number nothing measured. Unmeasured reads "not measured", never 0.
2. Patterns are correlation, and are withheld below a minimum sample.
3. No em-dashes; the first 140 characters must stand alone (the fold).
4. Every model output carries provenance: model or template, and what left the machine.
5. Third-party personal data (engagers' names, comments) stays local unless the creator turns on a cloud model and the call needs it. Aggregates first. See [[Risk - Personal data of third parties]].
6. The studio never comments, reacts, messages or connects on LinkedIn. It does act in three named places, each only when the creator asks: Send to LinkedIn schedules a post through LinkedIn's private API (see [[Risk - LinkedIn terms and detection]]), a history import clicks and scrolls the creator's own activity pages, and the side panel types a draft into LinkedIn's composer without posting it.

**Enforced by:** [[Brief and Guardrails]] and the test suite.
