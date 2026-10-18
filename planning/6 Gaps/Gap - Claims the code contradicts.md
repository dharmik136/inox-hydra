---
type: gap
status: partly fixed
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

**2026-10-18:** the README and the API description now say what the code does. Still open, and the owner's call: one product name, an extension name without "LocalTaplio", and a name without "LinkedIn" in it, since LinkedIn's brand rules restrict its mark in product names and the store review will ask.
