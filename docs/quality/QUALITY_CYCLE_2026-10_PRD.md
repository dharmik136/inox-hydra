# PRD: Quality cycle before the first paid release

| | |
|---|---|
| Status | In delivery |
| Owner | Dharmik Shingala |
| Started | 2026-10-19 |
| Release | 2.6.0 (unreleased) |
| Register | [BUG_REGISTER_2026-10.md](BUG_REGISTER_2026-10.md) |

## 1. Problem

Inox Hydra is moving from one creator's own tool to a product people pay for.
Its owner walks one path every day: one profile, one machine, one browser, a
studio that already knows who they are. A paying creator walks every other
path first: a fresh install, Setup from nothing, an archive LinkedIn produced
last week, a second profile, Windows, a backup restored onto a new laptop.
Defects on those paths are invisible to the owner and cost a buyer their first
hour, which is when refunds happen.

2.6.0 also changed a great deal at once: one database per creator, the offline
licence, the archive import, network reading behind a switch. Each was
reviewed, but nobody had yet used them together as a stranger would.

## 2. Goals

1. Find the defects and workflow blockers that cost a paying creator the most,
   across the whole product, by using it the way they will.
2. Targets: 30 very high (S1), 50 high (S2) and 70 medium (S3) findings found
   and fixed. The targets set the depth of the search; they are not quotas. A
   finding that is not real is rejected at triage, and the register reports the
   true count.
3. Every fix ships with a regression test that fails before the fix and passes
   after it.
4. No regressions: the full suite, the UI audit and CI on Windows, macOS and
   Linux are green before anything merges to main.

## 3. Non-goals

- New features. An improvement is in scope only where a workflow cannot be
  completed, or is completed wrongly, without it.
- Anything that automates LinkedIn on the user's behalf or widens what the
  bridge reads.
- A visual redesign.

## 4. Scope

Six areas, each audited by its own reviewer in an isolated copy of the code:

| Area | What a creator does there |
|---|---|
| SETUP | Install, Setup's five steps, the archive import, the history sync |
| BRIDGE | The browser extension and everything it captures |
| WRITE | Composer, drafts, scheduling, the copilot and own AI keys, carousels |
| AUDIENCE | Leads, dossiers, DMs, outbound, analytics, patterns, search, help |
| PLATFORM | Profiles, licence, backup and restore, migrations, security, packaging |
| UX | The interface as a whole: states, feedback, navigation, keyboard, phone width |

## 5. Severity

| | Meaning |
|---|---|
| S1, very high | Blocks a core workflow with no workaround; loses, corrupts or leaks the user's or a third party's data; a security or privacy hole; shows invented or wrong facts as true; crashes a screen; breaks install, upgrade, backup or restore |
| S2, high | Wrong results or a partly working feature with a workaround; a silent failure; broken on one OS; confusing enough to cause a wrong action; a missing guard that bites in normal use |
| S3, medium | Edge cases, misleading messages, inconsistent state after an action, slowness, accessibility gaps, flows that need an improvement cycle |

Each finding is also typed as a `bug`, a `blocker` (the workflow cannot be
finished) or an `improvement` (works as written; the flow must change for a
user to succeed).

## 6. Lifecycle

| Stage | Entry | Work | Exit |
|---|---|---|---|
| 1. Discover | Brief and area assigned | Use the product in a sandbox; reproduce; record evidence | Findings file with repro, evidence, location, proposed fix |
| 2. Triage | All findings in | Deduplicate, re-rate severity against section 5, reject what is not real, group into fix batches by the files they touch | Register with every accepted finding, severity and owner batch |
| 3. Plan | Batch assigned | Read the code path, confirm the root cause, design the smallest correct fix | Root cause stated; test named |
| 4. Build | Plan | Write the failing test, then the fix | Test fails before, passes after; area tests green |
| 5. Review | Branch per batch | An independent reviewer reads each fix against its finding and looks for regressions | Every fix accepted or sent back |
| 6. Integrate | Reviewed branches | Merge, resolve conflicts, full suite, UI build and audit, e2e | All green on one integration branch |
| 7. Release | Integration green | CHANGELOG, help text, privacy scan of the diff, merge to main, push | CI green on all three OSes |
| 8. Verify | On main | Rebuild the owner's studio; spot-check the S1 fixes by hand | Register closed |

Rules that hold at every stage: no em-dashes; nothing invented on screen;
token colours only; one h1 per screen; zero egress; the owner's live studio,
data and logged-in browser are never touched; the repository is public, so
nothing personal enters it.

## 7. Definition of done, per finding

- The register says what was wrong, from the user's side, and what changed.
- A test that reproduces the defect exists and passes.
- User-facing behaviour changes are in CHANGELOG 2.6.0 and, where a help
  article describes the flow, in that article.
- A reviewer who did not write the fix has accepted it.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Parallel batches edit the same file | Batches are cut by file ownership at triage; shared files go to one batch |
| Findings inflated to meet a target | Triage rejects unproven findings; the register reports real counts |
| A fix changes behaviour the owner relies on | Review against the owner's workflow; S1 fixes spot-checked on the live studio after release |
| LinkedIn changes its pages mid-cycle | Bridge fixes are tested against fixtures, not live pages |

## 9. Results

Filled in at the end of the cycle; see the register for the line items.
