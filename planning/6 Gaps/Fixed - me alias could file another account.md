---
type: gap
status: fixed
tags:
  - gap
  - extension
  - fixed-2026-10-18
---

# Fixed - me alias could file another account

The latest commit let `/in/me/` activity pages through on the alias alone. `/in/me/` is whoever is signed in to the browser, so with several [[Creator Account]] profiles another account's posts could be filed under the confirmed creator.

Fixed 2026-10-18: one `isOwnActivityPage` check for the route and the scroll handler, refusing the alias when an in-page redirect resolved it to someone else. Tested by running the helper under node.
