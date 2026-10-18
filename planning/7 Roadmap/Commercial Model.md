---
type: roadmap
status: decided
tags:
  - roadmap
  - commercial
---

# Commercial Model

**Chosen by the owner on 2026-10-19**, and built: see [[Phase 2 - Commercial Plumbing]]. The merchant of record is still to pick.

**The constraint:** the product promises nothing leaves the machine, and the master plan rules out licence servers and telemetry for that reason. That ruled out charging at all.

**The answer:** an offline, signed licence.
- The merchant of record sells; a webhook (on the vendor's side, not the app's) signs `{email, tier, seats, expires}` with an Ed25519 private key and emails the file.
- The app verifies the signature with the embedded public key. No network call, ever.
- Annual licences expire into a read-only mode, never data loss. Lifetime licences keep the version they bought plus a year of updates.
- Piracy is accepted as the cost of the promise. The buyer is a professional who wants updates and support.

**Tiers:**
- Free: composer, fold simulator, audit, hooks from templates, export.
- Creator: analytics, leads, Today, patterns, AI with their own key, Obsidian export, archive import.
- Agency: up to 5 [[Creator Account]] profiles, each its own database, so per-client export and deletion come with it. Carousels already carry only the creator's name.

Prices: [[Pricing Hypothesis]].
