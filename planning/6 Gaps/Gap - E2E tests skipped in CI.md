---
type: gap
status: fixed
tags:
  - gap
  - quality
---

# Gap - E2E tests skipped in CI

The Playwright suite `importorskip`s, and CI never installs Playwright, so every browser test is skipped on every platform. Locally all five pass.

**Fixed 2026-10-18:** CI installs Playwright and Chromium on all three platforms, and runs `tools/ui_audit.py` on Linux with its report kept as an artifact. See [[UI Program]].
