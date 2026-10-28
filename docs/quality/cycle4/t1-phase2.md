# Cycle 4, track 1, phase 2: one bridge per browser, and no reload by hand

Companion to [CYCLE4_2026-10_PRD.md](../CYCLE4_2026-10_PRD.md), section 6, track 1, and to
[t1-bridge.md](t1-bridge.md), phase 1. Branch `qc4/t1-phase2`, from `main` at `e9ab6ff` (v2.9.0).
Specification: the capture report's Appendix B in full, and "never reload by hand", parts a to c.
The owner's direction: capability first, no independent review, a failing test first, one full
suite as CI runs it at the end. Code is cited by function, not by line.

| | |
|---|---|
| Built | Appendix B in full (ten parts, below) and never reload by hand (a, b, c), plus the two cases a self-reload cannot mend |
| New tests | 9 modules, 73 tests (`tests/test_qc4_t1p2_*.py`), with two node harnesses (`tests/bridge_worker_harness.js`, `tests/ten_tabs_harness.js`) and one end-to-end test of the real extension in Chromium |
| Against `main` | The new tests run on `e9ab6ff`: 66 of the 71 that can run there fail or error. The 5 that pass are the as-before cases (a report with no stamp is a row, two browsers are two rows, an import for a tab with no stamp, the test copy cannot reach a studio, a capture after the window is sent again) |
| Migration | One, numbered 34 in this branch, `_migrate_bridge_coordination`: "One bridge per browser: heartbeats and capture rows per browser and minute, and a history import claimed by one tab". The coordinator renumbers it at merge |
| Ten tabs on one post | 620 requests to the studio became 3; each engagement written 10 times became once; 10 capture rows became 1; 310 heartbeat rows became 1 |
| Routes | None added: the batched read is an `items` list on the existing engagement route |
| Interface audit | Health and Setup, dark and light: 8 screens, 0 blocking findings |
| Suite, as CI runs it | See the last section |

| Commit | What |
|---|---|
| 05c8f32 | The studio keeps one bridge per browser, routes by account and hands an import to one tab (migration 34) |
| 2f6558b | The studio answers a replay `already_seen`, and a read of a post is one request |
| 2400c09 | The worker coordinates the tabs; readers go into open tabs on install and update; an unpacked install reloads itself |
| 5f7f1f1 | "Reload required" is said only when it truly is, and Health names each browser |
| d4aa850 | The real extension reloads itself and gives the open tab its readers, in Chromium |
| 1286c60 | One run report per reader per minute, and ten tabs on one post measured |
| 513b4e6 | The two reloads a self-reload cannot do are said (folder gone, folder not the studio's), and Setup stops saying reload once it is done |
| 7cc35f9 | The browser keeps digests of the profiles' accounts, not their names |
| 355313d | The policy and the help say what is stored, and that a reload is no longer by hand |

## Appendix B, as built

1. **The stamp.** The worker stamps every relayed body (`stampFor` in `background.js`): an id it mints
   once per browser install (`browserInstanceId`, `crypto.randomUUID`, kept in `chrome.storage.local`),
   the browser's own name, the tab, window, frame and document, whether the tab is active, and the
   signed-in vanity, the creator's own. The vanity also rides as `X-Inox-Account`. The studio keeps
   only what `onboarding.clean_stamp` lets through, and stores only the browser id on a run and the
   browser and tab on an import.
2. **Idempotency keys on the studio's grains.** An engagement's key is the account, the post, the
   person by `/in/` vanity, the normalised type and the comment, which is `lead_interactions`'
   unique (`engagementKey`; the studio's `_engagement_grain` in `routers/crm.py`); a post analytics
   reading is the author, the post, the hour and the figures, so a refresh with new figures inside
   the hour is still written; anything else is the account and the item as read.
3. **Coalesced across tabs.** `coalesce` keeps a SHA-256 key per item forwarded in the last ten
   seconds in `chrome.storage.session`; an identical item from any tab in the window is answered
   `already_seen` by the worker. A reader's run is keyed by reader, page kind, drift and UTC minute.
4. **One batched request per read.** `content.js` sends one read of a post as `items`; the studio's
   `_ingest_read` answers each item in read order, in one writer turn, at most 300 items.
5. **A concurrency cap.** At most four requests to the studio at once (`MAX_IN_FLIGHT`), the
   heartbeat included.
6. **One worker heartbeat per browser per minute.** Pages send `PAGE_STATE` to the worker, which keeps
   a tab registry in session storage and beats on a minute's alarm and soon after a change; the
   studio upserts one row per browser id and minute (`record_heartbeat`).
7. **The observer paused while hidden.** `followCommentsWhileVisible` disconnects the comment
   observer when the tab is hidden and reads once when it is shown.
8. **`already_seen` before the writer.** `ingest_contract.RecentKeys`, 10,000 keys for 600 seconds,
   in memory, answers a replay before `through_the_writer`.
9. **Routed by signed-in vanity.** `bridge_routing.decide` pins a capture to the profile that
   confirmed its account; a capture for an account no profile holds is answered 202 `held`, kept by
   the worker with that account, counted on the heartbeat and listed on Health; a moment or a
   question for such an account is `nothing_new`; a profile still being set up takes what its
   browser reads; a capture with no account goes to the active profile, as before. The heartbeat
   answers SHA-256 digests of the confirmed accounts (`profile_accounts`), and the worker sends what
   it held once its account's digest is among them.
10. **An import claimed by one tab.** `claimed_by` is browser and tab, renewed by a progress event
    every 30 seconds and live for 90; a tab hidden for a minute releases it, a second tab is told
    `claimed_elsewhere` and stops, and leaving the page releases it.

## Ten tabs on one post

Measured on both trees the same way: one LinkedIn feed page with one of the creator's posts and 30
commenters, read once by the real page script in a browser harness; that read replayed from ten tabs
at once through each tree's real `background.js` under node; against that tree's real studio on a
free port, with `INOX_HYDRA_HOME` under the scratchpad; rows counted in its database afterwards.
`tests/test_qc4_t1p2_ten_tabs.py` holds the branch's figures in CI.

| | `main` at e9ab6ff | This branch |
|---|---|---|
| Requests to the studio | 620: 300 engagement writes, 10 run reports, 310 heartbeats | 3: 1 read, 1 run report, 1 heartbeat |
| Requests per engagement | 10 | one request carries all 30 |
| `lead_interactions` rows | 30 | 30 |
| Writes per engagement (`seen_count`) | 10 | 1 |
| `captures` rows for the engagers reader | 10 | 1 |
| `bridge_heartbeats` rows | 310 | 1 |
| Wall time, first message to last answer | 4.1 s and 9.8 s in two runs | 0.57 s and 1.5 s |

The counts were the same in both runs; the wall times moved with the shared machine's load.

## Never reload by hand

- **a. Readers into open tabs.** On install and update, `injectIntoOpenTabs` asks each LinkedIn tab
  which version of the readers it carries (`window.__inoxBridgeVersion`) and gives it this
  version's: `card_urns.js` in the page's world, the four readers in the isolated one. A discarded
  tab is skipped, since it loads afresh; a tab that cannot be reached is counted as needing a
  reload, and Health says so on its own line.
- **b. An unpacked install reloads itself.** `checkOwnFiles` reads its own `manifest.json` through
  `chrome.runtime.getURL` on start-up, every five minutes, and when the studio answers with another
  version, and calls `chrome.runtime.reload()` when the version there differs. The spike, in
  Playwright's Chromium: with developer mode on, the reload reads the files from disk,
  `onInstalled` fires with "update", and readers injected into a tab land in a fresh world with no
  clash; with developer mode off, the reload unloaded the extension. The studio's launcher already
  turns developer mode on in its profile (`_ensure_developer_mode_enabled`), and Load unpacked needs
  it. `test_qc4_t1p2_self_reload.py` runs the real extension in Chromium.
- **c. "Reload required" only when it truly is.** The handshake judges what the extension said: the
  heartbeat on the line, else the newest heartbeat inside the freshness window, else nothing, and
  then `reload_required` is null rather than true. A reload is required for an older contract that
  is not about to update; for an older version that cannot reload itself (before 2.10, the owner's
  2.7.0 case); for a folder that is gone, which the worker learns when its fetch of its manifest
  fails (seen in Chromium by deleting the folder); and for a folder that is not the studio's: older
  than the studio, while a look at its folder taken after the studio started still finds its own
  version. Setup's step 5 and Today say "reload, then import again" after an import an older
  extension read only while the bridge heard from still needs it (`heard_current`).

## What is stored, and where it is said

The privacy policy's "What is stored, and where" names each new value, in the browser and on the
computer; `release/privacy.html` was rebuilt. The help says the same in the update, Health, Setup,
install, egress and terms articles, and in `EXTENSION_AND_SYNC.md`. One decision on the way: the
heartbeat first answered the profiles' account names, which with an Agency licence would have put
every client's account into the browser running the bridge; it answers digests since 7cc35f9.

## Outside this track's files

- `studio/ui`: `HealthSurface.tsx` (the reload message only when true, the tabs sentence, the list of
  browsers, a gone folder), `OnboardingSurface.tsx` (the browsers on step 1, the import row's reload
  advice), `lib/api.ts` (types). Track 4's surfaces; only those lines.
- Shared tests changed for the new shape: `conftest.py` (the in-memory keys cleared per test),
  `qc_f3_pages.py`, `test_network_reading_is_opt_in.py`, `test_onboarding_identity.py`,
  `test_qc3_t3_ingest_contract.py`, `test_qc3_t3_one_writer.py`, `test_qc4_t1_heartbeat_state.py`,
  `test_qc4_t1_no_marks.py`, `test_qc4_t1_one_post_identity.py`, `test_qc4_t1_worker_badge.py`,
  `test_qc_f3_heartbeat.py`, `test_qc_f4b_history.py`, `test_review_regressions.py`.

## Limits

- The self-reload compares version numbers: a change to the files that keeps the version, a source
  checkout between releases, still needs Reload.
- With developer mode off, the reload unloaded the extension in Chromium; the help says to leave it on.
- What the kept queue does across a studio restart (its depth, how long it takes to drain) was not
  measured.
- The `already_seen` keys live in memory: after a studio restart a replay reaches the writer, which
  keeps one row per grain but counts the sighting again.
- Rows from before migration 34 keep NULL in its columns; an extension before 2.10 still writes one
  heartbeat row per beat.

## Suite, as CI runs it

Not run yet at this record's first commit.
