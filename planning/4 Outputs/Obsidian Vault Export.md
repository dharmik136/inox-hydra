---
type: output
status: built
tags:
  - output
  - portability
  - obsidian
code: studio/backend/obsidian_export.py
---

# Obsidian Vault Export

Writes the creator's LinkedIn record as an Obsidian vault on this machine. Nothing leaves it.

- `Me.md`: identity, about, roles, skills.
- `Posts/`: one note per [[Own Post]] with its text, its readings over time, and who engaged, as links.
- `People/`: one note per [[Lead]], linking every post they engaged with, their comments and their stage history.
- `Topics/`: one note per [[Topic]], linking its posts.
- `Outbound/`: one note per person whose posts the creator engages with, linked to their People note when they engaged back.
- `Drafts/`: the studio's drafts.
- `Home.md`: the map, and a graph colour per folder.

**Built 2026-10-18.** Brand Studio, Local security, Your data, "Export to Obsidian"; or `python -m studio.cli export --format obsidian --output <folder>`; or `POST /api/v1/support/export` with `{"format": "obsidian"}`. Code: `studio/backend/obsidian_export.py`, tests: `tests/test_obsidian_export.py`.

Re-exporting into the same folder rewrites only the notes it wrote before (a manifest lists them), removes the ones it no longer writes, and keeps anything under a "## Your notes" heading. It refuses a non-empty folder that is not one of its own exports.

Open it in Obsidian and the graph view is the creator's audience: posts as hubs, people around them, the people who show up on several posts sitting between them.

Unmeasured figures say "not measured". Seeded demo rows are not exported as measurements.

**Feeds back:** [[Vault as AI Context]]. **Roadmap:** [[Phase 1 - Own Data Complete]].
