---
type: gap
status: open
tags:
  - gap
  - trust
  - commercial
---

# Gap - Claims the code contradicts

The README and app description promise things the code does not do:
- "Encrypted local SQLite": only the [[Settings Vault]] values are sealed.
- "Air-gapped": it is local and egress is gated, which is different.
- "Avoids monkey-patching window.fetch, completely undetectable": [[Voyager Interceptor]] wraps fetch, and "undetectable" is not a claim anyone selling this should make.
- Five product names, and an extension called "LocalTaplio", a competitor's trademark.

Selling with these on the page is a refund, a review and a legal letter waiting to happen. **Phase:** [[Phase 0 - Stabilise and Tell the Truth]].
