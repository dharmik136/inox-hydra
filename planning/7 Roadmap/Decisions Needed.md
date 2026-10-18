---
type: roadmap
status: open
tags:
  - roadmap
  - roadmap
  - owner
---

# Decisions Needed

Calls only the owner can make. Each blocks something on the [[Roadmap]].

1. **Land the branch.** The work of 2026-10-18 is on `feat/commercial-readiness`, in the worktree `../inox-hydra-work`, not pushed. Review, then push and open a pull request, or merge locally.
2. **One product name.** Today: Inox Hydra, LinkedIn Studio Enterprise, Editorial Motion OS, LocalTaplio, Personal LinkedIn Studio. Drop "LocalTaplio" (a competitor's mark), and choose a name without "LinkedIn" in it, since LinkedIn restricts its mark in product names and the store review will ask. Blocks [[Phase 2 - Commercial Plumbing]].
3. **How profiles are separated.** [[Gap - Account scoping is cosmetic]]. Recommended: one database per creator profile, chosen at startup, rather than an `account_id` on every table. Isolation is then structural instead of a filter every query must remember, and backup, export and deletion per client come for free. Blocks the agency tier in [[Commercial Model]].
4. **Keep or retire the network interceptor.** [[Voyager Interceptor]] carries the most platform risk and, after [[Gap - Voyager data discarded]], keeps only follower counts and feed figures the page readers also see. Recommended: off by default behind an explicit setting, then retire if the archive import covers the need. See [[Risk - LinkedIn terms and detection]].
5. **The commercial model.** Offline signed licence plus a merchant of record ([[Commercial Model]]), and the price points in [[Pricing Hypothesis]], to test with design partners.
6. **Request a real LinkedIn archive.** Settings, Data privacy, Get a copy of your data. The [[LinkedIn Data Archive Import]] should be built against real files, not guessed column names.
7. **The old database in history.** Commit 2cc6582 holds a database with real profile URLs in pushed history. Removing it means rewriting history.
