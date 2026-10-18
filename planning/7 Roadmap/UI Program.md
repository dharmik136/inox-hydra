---
type: roadmap
status: in progress
tags:
  - roadmap
  - ui
  - quality
---

# UI Program

**Tools:**
- `tools/ui_audit.py`: Playwright walks every screen in both themes at desktop and phone width, records console errors, egress, failed API calls, axe-core violations and horizontal overflow, and writes screenshots plus a report.
- Agentation: a dev-only toolbar in `vite dev` that lets a person click any element, write a note, and send it to the agent through the `agentation-mcp` server. It never enters the production bundle (a test checks).

**After the fixes (2026-10-18):** 56 screens (14 sections, 2 themes, 2 widths) with zero axe findings of any impact, no console errors, no egress, no overflow, on both a fresh install and demo data. CI now runs the audit on Linux.

**Agentation loop verified end to end:** a Playwright-driven annotation on the Setup heading reached `agentation-mcp` with its selector, nearby text and source location (`OnboardingSurface.tsx:108:7`).

**First audit findings, all fixed:**
- Composer at narrow widths: the inspector stays docked and the editor disappears on a phone; inspector tabs clip.
- Activity screen: colour contrast fails in the light theme; KPI card grid and "autonomous sync controller" wording go against the design blueprint.
- Most screens have no level-one heading.
- Rail labels stay visible after a mouse click, over the content.
- Long sentences set in 11px uppercase monospace are hard to read in empty states.
