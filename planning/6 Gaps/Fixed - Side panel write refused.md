---
type: gap
status: fixed
tags:
  - gap
  - extension
  - fixed-2026-10-18
---

# Fixed - Side panel write refused

The side panel recorded an injected post through the content-script relay, whose allowlist rightly refuses `/api/v1/posts/injected`. The refusal was swallowed, so injected posts never got the row that [[Post Permalink Binder]] attaches to.

Fixed 2026-10-18: a `PANEL_WRITE` lane, accepted only from the extension's own pages, for that one path.
