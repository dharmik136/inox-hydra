---
type: gap
status: fixed
tags:
  - gap
  - trust
  - fixed-2026-10-18
---

# Fixed - Founder identity in a fresh install

Three places still put the original author into every install: the carousel deck's default byline (their job title, on every slide, because the interface never sends one), the command engine's system prompt (which described them to the model for every user), and the sandbox profile (their vanity and headline, written into settings).

Fixed 2026-10-18: bylines come from Brand Studio, then the confirmed profile, then nothing; prompts carry the [[Voice Pack]] instead; the scan in `tests/test_fresh_install_is_impersonal.py` now knows the lowercase vanity and the title.
