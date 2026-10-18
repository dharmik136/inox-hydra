---
type: roadmap
status: in progress
tags:
  - roadmap
  - roadmap
---

# Phase 0 - Stabilise and Tell the Truth

**Done 2026-10-18:** two failing tests fixed, three data bugs fixed ([[Fixed - Voyager analytics column]], [[Fixed - Side panel write refused]], [[Fixed - me alias could file another account]]), Playwright installed locally (all browser tests pass), a repeatable UI audit tool, Agentation wired for UI feedback.

**Remaining:**
- [ ] Rewrite README and the app description so every claim is true ([[Gap - Claims the code contradicts]]).
- [ ] One product name across the app, extension, installer and docs; drop "LocalTaplio".
- [ ] Playwright in CI ([[Gap - E2E tests skipped in CI]]); pin GitHub Actions to commit SHAs.
- [ ] Add CHANGELOG.md and tag v2.6.0 (about 60 commits since v2.5.2).
- [ ] Retire the stale docs (DESIGN.md describes the old UI; strategy_playbook.md describes a tool that does not exist).
- [ ] Delete the seven stale remote branches (all merged).
