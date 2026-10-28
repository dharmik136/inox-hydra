# Cycle 4: network reading retired (2.10.2)

The owner's decision of 2026-10-28. Branch `qc4/retire-network-reading`, from `qc4/release-2.10.1` at
`5d19786`; it ships as 2.10.2, right after 2.10.1. A failing test first where it applied, no independent
review, one full suite as CI runs it.

**Why.** A sanitised Resource Timing list the owner ran on their own feed tab: LinkedIn's 2026 web app makes
no `/voyager/api/` calls at all. Its data arrives through React Server Component actions
(`/flagship-web/rsc-action/actions/pagination`, `server-request`, `server-stream-request`,
`/flagship-web/in/<vanity>`) in an internal streaming format, so the interceptor, the schema registry and
the webRequest observer had nothing to read and could not be re-keyed.

| | |
|---|---|
| Removed, extension | `voyager_interceptor.js`, `voyager_schema.js`; the worker's registration of the interceptor; the `webRequest` listener, `observeLinkedInRequest` and its telemetry dispatch; the `webRequest` permission (grep found no other use); the popup's switch, note and their styles; `content.js`'s interceptor listener, gate and early-capture queue; the Resource Timing coverage meter; the page's network reading report to the worker; the side panel's network reading, Voyager badge, schema registry, 24-hour captures and API drift lines |
| Removed, studio | `record_voyager_ingest`, `record_schema_drift`, the heartbeat's network reading cleaners, report and sentence, `listed_health`, the two `voyager_*` extractors, `OPT_IN_EXTRACTORS`; from the health payload `voyager_active`, `voyager_24h_captures`, `network_reading`, `recent_drift`, `schema_version`; from the readers report `network_reading` and each reader's `opt_in`; Health's network reading sentence and its "Network reading and drift" block; Setup's sentence |
| Answered, not written | `POST /api/v1/bridge/voyager-ingest` and `/api/v1/bridge/schema-drift` answer 200 `{"status": "retired", "outcome": "nothing_new"}` with the sentence, reading nothing, so an extension not yet reloaded neither keeps the capture to resend nor reports an error; neither path is on the routing lists, so nothing is held for an account. The webRequest observer's telemetry (`source: chrome_mv3_observer` on `/api/analytics/ingest`) is answered the same way and not written to the telemetry store. The heartbeat accepts `network_reading` and `voyager_calls` and keeps neither |
| Cleaned up on update | On install, update and browser start the worker unregisters `inox-network-reading` if an earlier version registered it (a registration persists across sessions) and removes `networkReading` and `lastVoyagerCaptureAt` from storage. A tab open with the switch on keeps the old wrapper, which can send nothing, until reloaded |
| Kept | The tables (`schema_drift_events`, the heartbeat's two columns, old `voyager_*` capture rows and day rows, readings marked `voyager_network`), forward only, with no migration; `forget_other_members_readings`, `VOYAGER_KEPT` and `clean_voyager_path`, which cycle 4's migration (`_migrate_reader_timing_and_network_reading`) still runs |
| Said once | "Network reading was retired in 2.10.2: LinkedIn's site no longer sends the data it read." over Health's readers and on Setup's step 1, only where network reading had run: a capture row or a day row of a network reader, a drift event, a reading marked `voyager_network`, or a kept heartbeat with the switch on (`onboarding.network_reading_retired`) |
| Manifest permissions | `sidePanel`, `cookies`, `storage`, `tabs`, `scripting`, `alarms` (`scripting` stays: the readers go into open tabs on update, and the old registration is removed) |
| The guard | `tests/test_network_reading_retired.py`, 14 tests. Fails if any extension script patches `window.fetch` or `XMLHttpRequest` (assigned, defined, wrapped in a Proxy, or a response prototype patched), a MAIN-world script other than `card_urns.js` runs or the stamper touches a request, the worker registers a content script or injects anything but the stamper into LinkedIn's world, or the manifest asks for `webRequest` |
| Falsified | On `5d19786`, 13 of the 14 new tests fail, each for its reason: `voyager_interceptor.js` assigns, defines and proxies `fetch`; the worker calls `registerContentScripts`; the manifest asks for `webRequest`. Five violations planted on the finished branch each fail the guard: `window.fetch = new Proxy(...)` in `content.js`; `XMLHttpRequest.prototype.open = ...` in the stamper; `webRequest` back in the manifest; a MAIN-world registration in the worker; a second MAIN-world script in the manifest |
| Tests | 7 modules of the retired feature removed (`test_network_reading_is_opt_in`, `test_qc_f3_network_reading`, `test_qc4_t1_network_reading_state`, `test_qc4_t1_heartbeat_state`, `test_qc4_t1_voyager_drift`, `test_qc4_t1_voyager_paths`, `test_voyager_ingest_writes`); `test_qc4_t1_voyager_privacy` keeps its migration case only. Shared modules now assert the retired behaviour: tracks 2, 4 and 6's (`test_qc4_t2_show_stream`, `test_qc4_t4_health`, `test_qc4_t6_terms_and_notes`) among them |
| Documents | The privacy policy (and `release/privacy.html`), `release/STORE_DISCLOSURES.md` (no `webRequest` row; user activity unticked), the help (install, terms, reload, Health, Setup, egress, storage), `EXTENSION_AND_SYNC.md`, `ARCHITECTURE.md` |

| Commit | What |
|---|---|
| 1fc14d8 | Network reading retired in the extension and the studio, with the guard |
| 95fa264 | The policy, the help and the store disclosures |
| 6f22c6f | This record, filed in the library |
| ecf1a81 | The two things the first full run found: a help sentence that put a post in Analytics, and track 4's first-viewport test expecting the retired state's words |

## Left as it is

- `schema_drift_events` was pruned to 30 days only when a drift event was written; nothing writes now, so the rows it holds stay until the database is cleared. They name a schema, its fields and a path cleaned of anyone.

## Carried into 2.10.2 with it

| Commit | What |
|---|---|
| 71b6846 | The Telegram bot's token masked in the egress ledger (the poll is counted under `/bot<token>/getUpdates`; the request still carries it), an error answer from Telegram (401, 409, 5xx, `ok: false`) backed off from as a network fault, and a failed update logged by its kind only. The smallest form of the bot's own fixes for 2.11.0 (`2dac22c`, `820ed9c`). `tests/test_qc4_t6_token_and_backoff.py`, 7 tests, all failing on the code before it |
| 84286e6 | The Storage panel's "Network readings log" is the extension readings log, in the panel, its help and the policy; the planning risk register no longer lists the interceptor as an exposure, the interceptor's note is marked retired and the gap about its discarded data closed |
| (release) | The version on every surface, the changelog, the policy's version line and its page, the cycle 4 register |

## Suite, as CI runs it

`pytest tests studio/tests -q -rs` after `npm --prefix studio/ui run build`:

| Run | Result |
|---|---|
| At 6f22c6f | 4,095 passed, 17 skipped, 2 failed in 15 min 6 s: `test_qc4_t3_help_posts_are_on_posts` (the Health article's new sentence said the retired readers' figures stay "with your posts and in Analytics") and `test_qc4_t4_views` (Health's first view expected "not reported by this extension version"). Both fixed in ecf1a81 |
| At ecf1a81 | 4,097 passed, 17 skipped, 0 failed in 14 min 32 s |

The 17 skips are Windows and macOS primitives, PyYAML not installed here, a browser launch that needs a
real desktop, and enrichment the interface does not surface yet.
