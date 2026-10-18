---
type: gap
status: open
tags:
  - gap
  - quality
---

# Gap - Order-dependent roadmap test

`tests/test_milestone4_days13_17.py::test_day17_launch_manifesto_and_full_roadmap_integrity` expects at least 17 drafts in the shared sandbox, and only gets them when earlier tests have created some. Run alone it fails, on main as well. It should seed what it counts.
