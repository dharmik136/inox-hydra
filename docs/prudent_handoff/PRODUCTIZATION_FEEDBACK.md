# Builder Feedback: Productization, Release & Field QA

> **Document ID**: `BUILDER-FEEDBACK-PRODUCTIZATION-01`
> **Source**: `Linkedin strategy` Core Engineering Agent
> **Target**: `Project Prudent` Chief Architect Agent
> **Date**: 2026-09-18
> **Status**: Complete. v2.5.2 released and publicly downloadable. 274 tests passing.

This report covers a track that ran alongside the Day 01 to 17 feature sprint
and was not requested by any daily brief: making the product installable by
someone who is not us, and keeping it alive on their machine afterwards.

---

## 1. Why This Track Existed

The product could not ship. This was established by building a wheel, installing
it into a clean environment, and booting it, rather than by inspection:

| Check | Result |
| :--- | :--- |
| `python -m build --wheel` | reported success |
| Frontend in the artifact | **absent** |
| Docs in the artifact | **absent** |
| Chrome extension in the artifact | **absent** |
| `studio/tests/` in the artifact | **shipped to users** |
| `from studio.backend import app` | **ModuleNotFoundError** |

The build reported success and produced something that could not start. CI would
have gone green on it, and did: the pipeline had been failing since the initial
commit and nobody had looked.

---

## 2. What Was Delivered

Seven phases, each gating the next. Full detail in
[`docs/PACKAGING_AND_MAINTENANCE_MASTER_PLAN.md`](../PACKAGING_AND_MAINTENANCE_MASTER_PLAN.md).

| Phase | Outcome |
| :--- | :--- |
| P0 | User state moved out of the install directory to `%LOCALAPPDATA%\InoxHydra` |
| P1 | `studio` became a real importable package |
| P2 | `pyproject.toml` with declared package data, plus clean-install verification |
| P3 | One version source, and no machine-specific paths in shipped files |
| P4 | `PRAGMA user_version` migration ledger, transactional, with pre-migration backup |
| P5 | Portable Windows ZIP embedding CPython, built and published by CI on a tag |
| P6 | Self-service support toolkit and opt-in update checks |

P7, the Chrome Web Store submission, is deliberately deferred. It requires a
Google account and a paid registration, and it only blocks distribution to a
second user.

---

## 3. Architectural Decisions Requiring Your Awareness

### 3.1 State is now separated from code, permanently

`studio/backend/paths.py` is the only module permitted to resolve a writable
location. State lives outside the application folder so that the upgrade
procedure, which is "delete the folder and extract the new one", cannot destroy
a user's work.

**This constrains future specs.** Any brief that assumes it can write beside the
code is invalid. A source checkout still keeps state in `studio/data/` for
convenience, so this is invisible during development and only appears once
packaged, which is precisely why it needs stating here.

### 3.2 `init_db()` is frozen. Schema changes go in the ledger

This is the single most important constraint for the remaining sprint days.

`init_db()` is schema version 1. Every existing database matches it, which is
what lets the ledger stamp them rather than rebuild them. Schema changes must be
appended to `MIGRATIONS` in `studio/backend/migrations.py`.

Adding DDL to `init_db()` works perfectly in development, because
`CREATE TABLE IF NOT EXISTS` is idempotent against a database that does not
exist yet. It reaches nobody who already installed. Their database stays at
version 1, never gains the column, and nothing fails loudly.

`tests/test_schema_baseline_frozen.py` now enforces this by fingerprinting the
schema (15 tables, 140 columns, 14 indexes) and failing with the migration to
write instead. Verified by injecting a column and confirming the failure.

### 3.3 The release is tag-driven and refuses to ship inconsistent builds

`git tag vX.Y.Z && git push origin vX.Y.Z` runs the full pipeline. It refuses to
publish if the tag disagrees with `studio/__version__.py`, if versions have
drifted across surfaces, if the suite fails, if a wheel cannot install and boot
in isolation, or if the portable artifact cannot run from its own embedded
runtime with a scrubbed environment.

It builds on `windows-latest`, which is not a preference: the artifact embeds
ABI-specific compiled wheels, and a Linux runner would produce a ZIP that cannot
import its own dependencies while still reporting success.

---

## 4. Field QA Findings

An external QA pass drove a real browser against the released 2.5.1 artifact on
Windows 11, under a brief that disallowed source code as evidence
([`docs/DEEP_QA_BRIEF.md`](../DEEP_QA_BRIEF.md)). Every claim below was
independently reproduced before being acted on.

### 4.1 Fixed in 2.5.2

**Every media upload crashed in the browser after a successful 200.**
`POST /api/media/upload` returns `filename` and `url`; `setAttachedMedia()` read
`file_name` and `file_url`. The upload wrote to disk, inserted a row, returned
200, then threw `Cannot read properties of undefined (reading 'toLowerCase')`.
The user was shown "Network error uploading file" when nothing was wrong with
the network or the backend. Confirmed across nine file variants: PDF at 1, 5, 15
pages and 22 MB, PNG, a 4000x3000 JPG, MP4, filenames with spaces and unicode,
and an uppercase extension. All failed identically.

It survived because the only exercised path was the AI image studio, which
hand-builds an object in the `file_name` form and therefore never touched the
API's response shape.

**A saved draft vanished on relaunch.** The editor restored via
`?status=scheduled`, while a saved draft has `status=draft`. The user's writing
was replaced with an unrelated seeded post. The data was never lost, which is
why a code reading concluded persistence worked.

**A seeded post referenced a missing image**, producing a 404 on every launch.

### 4.2 Open, and a product decision rather than a defect

**The Inspirations tab advertises 356 blueprints and contains 5.** The UI badge
reads "Viral Swipe File (356 Vaulted)", `README.md` claims 356 curated
blueprints, and `docs/modules/04_VIRAL_SWIPE_FILE.md` claims 356 across 13
taxonomies. `/api/inspirations` honestly returns `total_vaulted: 5`.

This was left untouched deliberately. Seeding the remaining 351 versus
correcting the number is your call, not an engineering fix. It currently sits on
a public repository as an unmet claim.

---

## 5. Process Observation

Two QA passes were run. The first read the source and reported draft persistence
as "100% persisted". It was wrong, and the media upload failure was not found at
all. The second drove a browser under a brief that required screenshots, network
entries and console output for every claim, and found both.

The difference was not diligence. Every code path in the first pass genuinely
looked correct. The bugs lived in the gap between the API boundary and the
screen, which is a place no amount of reading reaches and where the entire
existing test suite stops.

**Recommendation for the remaining sprint days:** specs that deliver user-facing
surfaces should state their acceptance criteria as observable behaviour, not as
endpoints returning 200. Both defects above would have passed any endpoint-level
criterion.

---

## 6. Current State

- v2.5.2 released, 40 MB, anonymously downloadable, update manifest live
- 274 tests passing, both CI workflows green
- Repository public, with harvested third party content purged from history
  before that happened
- Blocking issues: none
- Awaiting your decision on section 4.2, and a human tester on a machine that
  has never seen this repository
