---
type: roadmap
status: planned
tags:
  - roadmap
  - roadmap
  - commercial
---

# Phase 2 - Commercial Plumbing

- [x] Offline licence: an Ed25519-signed key (`IHL1.`), verified with the public key in the app; Brand Studio has a Licence tab; `tools/licence_keys.py` issues them. The signing key lives outside the repository. See [[Commercial Model]].
- [ ] Merchant of record (Lemon Squeezy, Paddle or similar) so tax across India, the EU and the US is someone else's job; it emails the licence file.
- [x] Tier map in the app (`licensing.FEATURES`), read from the licence. Enforced today: more than one profile needs Agency.
- [ ] Turn off `BETA_OPEN` at launch so the Creator features need a licence.
- [ ] EULA and privacy policy (the store listing requires one), and an in-app "what leaves this machine" page that matches the egress ledger.
- [ ] Chrome Web Store listing (unlisted first), with the data-use disclosures; Edge add-ons in parallel. See [[Risk - Distribution and signing]].
- [ ] Signed Windows installer, notarised macOS build, signed update manifests with the key kept offline.
- [ ] A landing page, outside this repository's zero-egress rules.
