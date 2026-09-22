# Documentation

Thirty-six documents accumulated here without an index, which is why recent ones
were hard to find. This is the map.

**Read in this order if you are new to the codebase:** `ARCHITECTURE.md` for the
shape of it, `DATA_ARCHITECTURE.md` for what the product actually knows and how
it learned it, then `FIRST_RUN.md` for what a new user faces.

These are maintainer documents. They are not the product's onboarding, and they
should not be handed to a creator who just installed the studio. What a new user
needs on day one is described in `FIRST_RUN.md` and is built, not read.

---

## Start here

| Document | What it is |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | The shape of the system: backend, frontend, extension, and how they reach each other |
| [DATA_ARCHITECTURE.md](DATA_ARCHITECTURE.md) | **What the studio actually captures from LinkedIn, and what it only appears to capture.** Six audits, each claim adversarially verified. The entity model the schema should converge toward, the vocabulary the domain needs, and what can honestly be learned at one creator's data scale |
| [FIRST_RUN.md](FIRST_RUN.md) | **What a new person faces on a fresh install.** The setup ladder in dependency order, the connection panel, per-screen empty-state copy, and the list of things a second user must not inherit |
| [GETTING_STARTED.md](GETTING_STARTED.md) | Install and run, both paths |

## How it works

| Document | What it is |
|---|---|
| [EXTENSION_AND_SYNC.md](EXTENSION_AND_SYNC.md) | The Chrome extension and how capture reaches the backend |
| [AI_ENGINE.md](AI_ENGINE.md) | The generation layer and its deterministic fallbacks |
| [BYO_AI_ARCHITECTURE.md](BYO_AI_ARCHITECTURE.md) | Bring-your-own-key provider configuration |
| [API_REFERENCE.md](API_REFERENCE.md) | Endpoint reference |
| [DESKTOP_SHELL.md](DESKTOP_SHELL.md) | The native window, why it wraps the backend rather than replacing it, and how it is built |

## Interface

| Document | What it is |
|---|---|
| [DESIGN.md](DESIGN.md) | The visual system |
| [UI_CONVENTIONS.md](UI_CONVENTIONS.md) | Token families, the dark-first mechanism, the accessibility floor, and the debt that is ratcheted rather than fixed |
| [ICON_SYSTEM.md](ICON_SYSTEM.md) | The sprite contract, the naming convention, and how to add an icon |
| [linkedin_studio_reimagined_design.md](linkedin_studio_reimagined_design.md) | An earlier design exploration |

## Per-module manuals

These are the seven entries the in-app docs hub serves.

| Document | Module |
|---|---|
| [modules/01_STUDIO_AND_EDITOR.md](modules/01_STUDIO_AND_EDITOR.md) | Composer and editor |
| [modules/02_SCHEDULE_AND_QUEUE.md](modules/02_SCHEDULE_AND_QUEUE.md) | Scheduling and the queue |
| [modules/03_INBOUND_CRM.md](modules/03_INBOUND_CRM.md) | Captured engagers |
| [modules/04_VIRAL_SWIPE_FILE.md](modules/04_VIRAL_SWIPE_FILE.md) | The hook library |
| [modules/05_ANALYTICS.md](modules/05_ANALYTICS.md) | Captured metrics |
| [modules/06_AI_COMMAND.md](modules/06_AI_COMMAND.md) | The AI command hub |
| [ENTERPRISE_USAGE.md](ENTERPRISE_USAGE.md) | Operating the studio day to day |

## Product and planning

| Document | What it is |
|---|---|
| [PACKAGING_AND_MAINTENANCE_MASTER_PLAN.md](PACKAGING_AND_MAINTENANCE_MASTER_PLAN.md) | Distribution, updates, and the phases of the packaging work |
| [PRD_AGNO_AGENTOS_MEDIA_STUDIO.md](PRD_AGNO_AGENTOS_MEDIA_STUDIO.md) | The media studio requirement |
| [strategy_playbook.md](strategy_playbook.md) | Content strategy notes |
| [DEEP_QA_BRIEF.md](DEEP_QA_BRIEF.md) | A QA pass brief |

## History

Kept because they record why decisions were made, not because they describe
current behaviour. Where they conflict with the code, the code is right.

- `prudent_handoff/` - day-by-day implementation specs and feedback, days 01 to 04
- `builder_feedback/` - review notes

**A caution on the day specs.** `DAY_02_IMPLEMENTATION_SPEC.md:92-94` and
`DAY_03_IMPLEMENTATION_SPEC.md:82-86` describe intercepting Voyager API response
bodies. That capability does not exist and never did: `webRequest.onCompleted`
cannot read a response body in any manifest version. `DAY_03:87` also claims
"exactly 0 additional HTTP requests", which was false until the egress guard
landed. Do not plan a feature on either statement. See `DATA_ARCHITECTURE.md`
section 2.2.

---

## Where the open work lives

Not in these documents. The backlog is in the `gstack_backlog` table, reachable
at `GET /api/v1/gstack/backlog` or in the app's governance view. Eighteen items
from the data and first-run assessments are filed there as ids 243 to 260,
each carrying a full specification and file references.

The two assessments above state what is true. The backlog states what to do
about it.
