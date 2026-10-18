---
type: gap
status: open
tags:
  - gap
  - quality
---

# Gap - E2E tests skipped in CI

The Playwright suite `importorskip`s, and CI never installs Playwright, so every browser test is skipped on every platform. Locally all five pass.

**Fix:** install Playwright and Chromium in CI on Ubuntu at least; run `tools/ui_audit.py` as a non-blocking job that uploads its report. See [[UI Program]].
