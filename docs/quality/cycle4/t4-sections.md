# Cycle 4, track 4, phase a: the new sections and the rail

Branch `qc4/t4-sections`, from `main` at `cf0ba9d` (2.7.0, schema 27). Specification: the sections report, "The proposed rail" and its migration table, batches 2, 3 and 4, decisions 2, 3, 5, 9, 10, 11, 15 and 16, and Appendix B. Phase b (the Brand and Settings split, Posts and Queue depth, the Composer disclosure panel and Outbound depth) is assigned after review and is not in this record.

Each row names the report's batch and row, what changed with path:line, the test that fails without the change, how any new guard was falsified (the fault planted, the guard seen to fail, the fault removed), and the one-view measurement and audit result where the item is a screen.

## Items

| # | Item | Report | What changed | Fails without it | Guard falsified | One view | Audit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Reply marks and a reader's day kept past the week | Decisions 9 and 11; migration table rows "(new) Replies" and "(new) Health" | One migration, numbered 28 in this branch: `reply_marks` (lead, post, comment key, marked_at) with a trigger that removes a forgotten lead's marks; `capture_days`, one row per reader per UTC day, rolled up by the `capture_day_rolled_up` trigger as each capture lands and kept `CAPTURE_DAYS_KEPT` (180) days; the week already in the log is rolled up when the migration runs. `studio/backend/migrations.py:1429` (window), `:1432` (migration), `:1455`, `:1466`, `:1491`, `:1547` (ledger entry) | `tests/test_qc4_t4_migration.py` (10 tests; they assert the migration's name and columns, never its number) | Trigger's age-out removed: `test_days_older_than_the_kept_window_age_out` and `test_the_kept_window_is_one_number` failed. Drift runs not counted: `test_each_capture_rolls_into_its_reader_day` failed. Both faults removed | n/a | n/a |
| 2 | Health | Batch 2; rail row 13; Appendix B, Q-A; decisions 2, 10 and 11 | A new section on the existing routes plus one field. `studio/backend/health.py:133` (`readers`: per reader, its state from `capture_health` and its runs in the prune's window as counts, `SUM` left NULL when no run measured; the heartbeat summary over the same week), `:183` (`reader`: one reader's newest 20 runs and every day row, one level down), `:118` (the SETUP-17 rule: a network-reading part is listed only once it has run). Routes in a new module, `studio/backend/routers/health.py:30` and `:36` (`/api/v1/bridge/readers`, not under `/api/v1/health`, whose containment would have credited the liveness route). Screen `studio/ui/src/components/HealthSurface.tsx:47`: the bridge line, network reading as reported or "not reported by this extension version" (`:545`), four counted figures, the readers table labelled "last 7 days", heartbeats, waiting captures and refusals "since the studio started", drift events, schema, backup schedule, and the update check off by default with Check now offered only once it is on (`:385`, decision 10). Rail entry `studio/ui/src/lib/navigation.ts:74`; `App.tsx:1020`; audit `tools/ui_audit.py:60`. Setup's capture health block moved out (`OnboardingSurface.tsx:363`, a pointer with Open Health). Help: new `docs/help/check-the-bridge-is-reading.md`; `check-your-version-and-update-the-studio.md`, `set-up-the-studio-from-your-linkedin.md`, `what-to-do-today.md`, `why-is-my-lead-list-empty.md` follow the move | `tests/test_qc4_t4_health.py` (16 tests), `tests/test_qc4_t4_views.py` (3 browser tests); `tests/test_qc_f4b_identity.py`'s two SETUP-17 tests now read Health and its article | Health's reader filter removed: 4 tests failed (the agreement guard, the listing test and both SETUP-17 tests). `_sum_or_none` summing NULL as 0 (before the SQL rewrite): the not-a-zero test failed. Window set to 30 days: the window test failed. All faults removed | 1.00 scroll pages at 1440x900, 95% of the width used, 34% ink in the first viewport; the header, the four figures and the whole readers table end above the fold (`test_health_answers_whether_the_bridge_is_reading_in_the_first_viewport`). On a heavy synthetic week (30,240 heartbeats, 4,860 runs, 1,548 day rows): first paint 6.5 KB over five routes; slowest route `/api/v1/bridge/readers` 43 ms, one reader's detail 32 KB in 7 ms | `tools/ui_audit.py --sections health,setup`: 8 screens (dark and light, desktop and phone), 0 console errors, 0 egress, 0 API failures, 0 axe violations, 0 px overflow |

## Notes on the items

**Health lists the readers Setup listed.** The first draft of the table listed all nine readers, with the two network-reading parts marked "NOT SEEN YET, NETWORK READING". That brought back the defect cycle 2 removed as SETUP-17: network reading is off unless switched on, so the two rows read NOT SEEN YET for everyone, and the advice for that, open the matching page, cannot start them. `tests/test_qc_f4b_identity.py` caught it. The list now follows the same rule as the onboarding state, and `test_health_and_the_onboarding_state_list_the_same_readers` holds the two lists equal.

**The first view carries counts, not rows.** Returning every day row with the first view would have been nine readers by 180 days, past the 150 KB first-paint bar within six months of use. The runs and the day rows are one level down, read when a reader is opened (`test_the_first_view_carries_counts_and_not_rows`).

**Today's one thing to open.** When a reader drifts, Today's reason said "See Capture health in Setup.", beside a Go to Setup button. Setup no longer holds the block, so the sentence now reads "Health shows since when; Setup links to it." (`studio/backend/today.py:308`), which is true with the button as drawn. A `health` action with its own button would be the better fix, and needs `TodaySurface.tsx`, which is track 3's; it is listed below as a follow-up.

## Not done, and why

Filled in at the end of the phase.

## Touched outside this track's files

| File | Lines | Why |
| --- | --- | --- |
| `studio/backend/app.py` | 2027 to 2034 | The include for the new Health router; the routes themselves are in `routers/health.py` |
| `studio/backend/today.py` | 308 | One sentence in `_open_next`'s drift branch, which named a block Setup no longer holds |
| `studio/backend/docs_engine.py` | 640, 712 | Files the new Health article where a creator reads help, and this record under For maintainers |
| `studio/ui/src/App.tsx` | 14, 997, 1020 | The Health import, Setup's Open Health link and the Health case; nothing in the stream lifecycle |
| `studio/ui/src/lib/api.ts` | 3266 to 3454, appended | The Health types and fetchers; nothing existing changed |
| `tools/ui_audit.py` | 60 | The audit walks Health |
| `tests/test_qc_f4b_identity.py` | 196 to 200, 203, 207 to 208, 235 | The two SETUP-17 tests follow the reader list to Health and its article; their assertions are unchanged |
| `tests/test_endpoint_reachability.py` | 250 to 264 | The ledger records two new paths and five newly reached, with the reason |
| `docs/help/*.md` (four articles) | as listed in row 2 | Sentences that sent a creator to Setup for capture health, and the update article's "no update control" |

## Follow-ups for other tracks

- Track 3 (`TodaySurface.tsx`) and the owner of `_open_next`: Today's drift case could return a `health` action with a Go to Health button instead of Go to Setup.

## Commits

Listed at the end of the phase.
