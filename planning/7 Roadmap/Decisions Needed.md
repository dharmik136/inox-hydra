---
type: roadmap
status: decided
tags:
  - roadmap
  - roadmap
  - owner
---

# Decisions Needed

The owner's calls, all made on 2026-10-19, and what was done with each.

1. **Land the branch.** Merged into main and pushed.
2. **One product name: Inox Hydra.** Every user-facing name is Inox Hydra, and the extension is Inox Hydra Bridge. Internal identifiers (data folder, database file, Windows app ID) are unchanged so nothing is orphaned.
3. **One database per creator profile.** Built: see [[Creator Account]]. [[Gap - Account scoping is cosmetic]] is closed.
4. **The network interceptor: off by default.** Built: see [[Voyager Interceptor]]. Retire it once the archive import is shown to cover what it adds.
5. **The commercial model and prices.** Offline signed licence, and the prices in [[Pricing Hypothesis]]. Built: see [[Commercial Model]]. Still open: which merchant of record sells it.
6. **The LinkedIn archive.** Built as Setup step 4, automated where it can be and waiting for the creator where it must: see [[LinkedIn Data Archive Import]]. Still open: run it on a real archive.
7. **Personal data in history.** The repository now holds the product only. The owner's posts, figures, post graphics and scripts, and real members' names, were removed from the current tree and from history, which was rewritten and force-pushed. Copies that only GitHub can delete (older commits still served by SHA, pull request refs) need a GitHub Support request; a leaked Taplio API key needs rotating by the owner.

**Next for the owner:** pick the merchant of record; request your own archive and import it; file the GitHub Support request; rotate the Taplio key.
