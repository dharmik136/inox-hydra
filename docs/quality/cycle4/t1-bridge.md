# Cycle 4, track 1, phase 1: the bridge

Companion to [CYCLE4_2026-10_PRD.md](../CYCLE4_2026-10_PRD.md), section 6, track 1. Branch
`qc4/t1-bridge`, from `main` at `cf0ba9d` (2.7.0, schema 27). Specification: the capture report,
items 1 to 5 and 7 to 10, decisions D1 and D3, Appendix A; the sections report's `capture_health`
row. Line numbers are at the branch head this record was committed with.

| | |
|---|---|
| Items built | 9 of 9 (1, 2, 3, 4, 5, 7, 8, 9, 10), plus the sections report's WORKING-at-zero row |
| New test modules | 9, 83 tests (`tests/test_qc4_t1_*.py`) |
| Guards falsified | 21 planted faults, each seen failing and then passing with the fault removed; one guard was vacuous at first and was rebuilt |
| Found by this track's own review | 13 defects after the first green runs, 1 of them a privacy defect; all fixed, listed below |
| Defect found by track 3 on main | A post first found after migration 26 had no post; fixed in 43aadff, with four more found on the way |
| Migration | One, numbered 28 in this branch: "Each reader says how long it took, and the bridge says whether network reading is on" |
| Interface audit | Setup and Today, dark and light: 8 screens, 0 blocking findings |
| Suite, as CI runs it | 3,199 passed, 17 skipped, 0 failed at 1a9c606; the runs before it are in the last section |

| Item | State | Commits | Review |
|---|---|---|---|
| 1. Reader self-timing | fixed | e72949c, 19592ec, f92d705 | |
| 2. Network-reading state on both heartbeats, three honest states | fixed | e72949c, b302b5c, 19592ec, 4152f7c, db0edc7, b907ffe | |
| 3. Resource Timing coverage meter | fixed | 19592ec, 4b92926, b907ffe | |
| 4. Own-page items marked sent only on an answer | fixed | 19592ec, b907ffe | |
| 5. Gate race, DOM marker, refused row, EXTRACTORS aligned | fixed | e72949c, 19592ec | |
| 7. Navigation API routes | fixed, spike first | 19592ec | |
| 8. Worker lastCapture, per-tab badge, panel from storage (D3) | fixed | 4152f7c, 4b92926, b8287f8 | |
| 9. Drift notice | fixed | 4152f7c, 4b92926 | |
| 10. Cadence rules in `_open_next` | fixed | 62dd65e, db0edc7 | |
| Sections report: WORKING shown for a reader that read nothing | fixed | e72949c, b302b5c | |
| Help and the extension document | updated | b302b5c, 2c35aa8, 77f6317, b907ffe | |

## Item 1. Every reader times itself

What changed. Each reader marks the start and end of its read with `performance.now()`
(`studio/extension/content.js:351-387`: `beginRead`, `endRead`, `takeTiming`; own pages reach the
same clock through `window.__inoxReaderTiming`, `studio/extension/own_pages.js:133-140`). The
capture report carries this run's `duration_ms`, the `reads` since the last report, the
`slow_reads` among them (over 50 ms, the Long Tasks threshold), and the `long_tasks` and
`long_task_ms` that overlapped a read (`content.js:442-462`, `own_pages.js:143-163`). The readers
timed: engagers and analytics (`content.js`), profile, the three activity readers and post
analytics (`own_pages.js:695, 1147-1184, 1243`), and the card stamper, which runs in the page's own
world and so writes its run onto the root element, as it writes a post id onto a card; content.js
forwards it as the `card_urns` reader (`studio/extension/card_urns.js:57-113`, `content.js:470-494`).
The studio stores the five figures on the captures row (`studio/backend/onboarding.py:491-524`,
migration at `studio/backend/migrations.py:1426`) and answers them per reader from
`capture_health` (`onboarding.py:538-588`). A run that sent no timing stores NULL, which is "not
measured"; no screen shows the figures yet, by the brief.

Long frames. The isolated world observes one source of long frames: `long-animation-frame` where
the browser has it, else `longtask` (`content.js:411-424`), because the spike below showed the two
entries for one slow task carry the same start and duration, so observing both counted one frame
twice. A read inside a long frame overlaps it however short the read (`content.js:389-405`). A
frame's entry is delivered after the frame ends, so its overlap rides with the reader's next
report: `long_tasks` on a row is the long frames delivered since the reader's previous report.

Tests that fail without it. `tests/test_qc4_t1_timed_readers.py` (9, against the pre-change
scripts: no timing fields, no `card_urns` report, no overlap, two sources);
`tests/test_qc4_t1_capture_rows.py::test_a_timed_run_keeps_its_duration_and_its_slow_read_count`,
`::test_an_untimed_run_is_not_measured_rather_than_zero`, `::test_a_nonsense_timing_is_refused_not_stored`.

Falsified. Both long-frame sources observed: `test_one_source_of_long_frames_is_observed` failed,
then passed restored. The strict overlap test restored:
`test_a_read_too_short_to_measure_inside_a_long_frame_still_overlaps_it` failed, then passed.

Measured: the readers on the fixture pages, without the harness's fake clock (headless Chromium
153.0.8010.12, this machine, one read each):

| Reader | Fixture | duration_ms | reads over 50 ms | long frames overlapped |
|---|---|---|---|---|
| engagers | permalink, 30 posts with 5 comments each, 150 comment cards | 2.5 | 0 | 0 |
| activity_posts | own activity page, 40 cards | 3.7 | 0 | 0 |
| analytics | creator analytics, 2 figure cards | 0.5 | 0 | 0 |
| profile | own profile, top card and 12 positions | 0.6 | 0 | 0 |
| card_urns | 30 feed cards already carrying `data-urn` | 0.1 | 0 | 0 |

These bound each reader's own work on small hand-written pages; they are not LinkedIn. The
fixture cards carry `data-urn`, so the stamper's React-properties scan, the costliest path the
report guessed at, does not run on them; no fixture has React properties. The figure that decides
items 14 to 17 arrives on the captures row from the owner's own browser once the extension is
reloaded. Nothing on the fixtures approaches 50 ms.

Measured: long frames seen from the isolated world (throwaway content-script extension, Chromium
153, fixture page; nothing reached a studio):

| Work | longtask entry | long-animation-frame entry |
|---|---|---|
| Page code, 150 ms on a timer | 150 ms | 150 ms, 1 attributed script |
| Isolated world, 120 ms in a message handler | 120 ms | 120 ms, 0 scripts: no attribution, as Chrome documents |

Both entry types are supported and delivered to an isolated-world observer. A 150 ms loop run
through Playwright's `evaluate` produced neither entry, which is the harness, not the page.

## Item 2. Network-reading state on both heartbeats; three honest states

What changed. The page heartbeat carries `network_reading {switch, registered: null, injected,
voyager_calls_seen, matched, captured, last_capture_at}` and the coverage counts
(`own_pages.js:1470-1481`, state from `content.js:313-325`); nothing is sent while the switch is
unread. content.js and own_pages.js run in one task, so the first heartbeat leaves before the
switch is read; content.js says when the switch is known or changes (`content.js:109, 115`) and
the page reports at once (`own_pages.js:1539`). The worker heartbeat carries the switch and
`registered` from `chrome.scripting.getRegisteredContentScripts`, and leaves the page's figures
null (`studio/extension/background.js:766, 1024-1043`). `BridgeHeartbeat` accepts both fields
(`studio/backend/app.py:1472-1473`, passed on at `:1554`). The studio keeps a field only in its
right shape (`onboarding.py:230-260`), stores it on the heartbeat row (`:263-291`), and answers
one report: the switch from the newest heartbeat, the registration from the newest worker beat,
the counts from the newest page beat, so neither blanks the other (`onboarding.py:314-360`). One
definition gives the sentence every screen prints (`onboarding.py:293-312`): "Network reading is
off.", "Network reading is on and seeing N LinkedIn data calls, K matched.", or "Network reading
is on and matching nothing: the LinkedIn tab that last reported saw N LinkedIn data calls, and
none matched the bridge's patterns.", with "reload that tab" when the interceptor's marker is
absent and "turn the switch off and on" when the reader is not registered. An extension that has
never reported the state is `null`, never "off". Setup's step 1 prints the sentence
(`studio/ui/src/components/OnboardingSurface.tsx:486-497`); the side panel's Health tab prints it
in place of "Active (Exact JSON) / Standby" (`studio/extension/sidepanel.js:583-603`). The opt-in
readers are listed while the switch is on or once they have run, by one rule for Setup and the
panel (`onboarding.py:526-536`, used at `:765` and `:1932`), so with the switch off none reads NOT
SEEN YET.

Tests that fail without it. `tests/test_qc4_t1_network_reading_state.py` (14),
`tests/test_qc4_t1_heartbeat_state.py` (7), `tests/test_qc4_t1_worker_badge.py::test_the_worker_heartbeat_carries_the_switch_and_the_registration`,
`tests/test_qc4_t1_panel_from_storage.py::test_the_health_tab_prints_the_studios_network_reading_sentence`
and `::test_the_health_tab_says_when_the_state_was_never_reported`.

Falsified. The panel's list unfiltered: `test_the_side_panels_list_follows_the_same_rule_as_setup`
failed. The page's prompt heartbeat removed: `test_the_state_is_reported_as_soon_as_the_switch_is_known`
failed.

Not measured: which of the three sentences the owner's install will say. That is the question
Appendix A answers by hand; this item makes it answerable from Setup once the extension is
reloaded and one LinkedIn page is opened with the switch on.

## Item 3. The Resource Timing coverage meter

What changed. While the switch is on, a `PerformanceObserver` on `resource` entries (buffered)
counts each `/voyager/api/` call by its path's shape plus GraphQL query name, the part of `queryId`
before the dot, never a query string, and how many resolve to a registry schema
(`content.js:239-307`). LinkedIn's REST paths carry what was asked about (`/identity/profiles/<vanity>/`,
`/socialActions/<urn>/`), so any segment that is not a plain word, carries a run of digits, or
follows a collection that takes an identifier becomes `_id_` (`content.js:249-262`), and the
studio refuses a key that still carries one (`onboarding.py:206-227`). A new observer is handed
the buffered entries again, so the counts start again with it. The page's buffer holds its first
250 entries before an observer starts, so on a heavy first load the count is of the calls the
bridge saw, which is how the sentence words it. The counts ride on the page heartbeat as
`voyager_calls`, at most 100 keys. The side panel lists them most called first, for example
`voyagerFeedDashMainFeed (9)` (`sidepanel.js:585-603`). Resource Timing lists `fetch` and
`xmlhttprequest` alike, so the meter answers Appendix A's cause 9 as well as cause 3.

Tests that fail without it. `tests/test_qc4_t1_heartbeat_state.py::test_with_the_switch_on_the_heartbeat_counts_calls_by_path_and_query_name`
(four real fetches against routed fixtures; one matches the registry),
`::test_a_call_that_names_a_member_or_a_post_is_counted_without_naming_them`,
`::test_switching_off_and_on_again_does_not_count_a_call_twice`,
`::test_with_the_switch_off_the_heartbeat_says_off_and_counts_nothing`;
`tests/test_qc4_t1_network_reading_state.py::test_the_coverage_meter_is_kept_and_answered_without_query_strings`,
`::test_a_call_key_that_still_names_a_member_or_a_post_is_refused`.

Falsified. Coverage keys loosened to accept any text after the slash; the raw pathname kept in
the page; the studio's identifier check removed; the counters not restarted: each guard above
failed, then passed restored.

Not measured: what LinkedIn's web app calls today. The meter names it on the owner's first page
with the switch on; nothing in this branch claims a name.

## Item 4. Own-page items marked sent only on an answer

What changed. `sendActivity` filters on `sentKeys` and adds an item's key only when the studio
answered: ok, kept by the worker, or a decided refusal, an HTTP status (`own_pages.js:1172-1173`).
With no answer, the items are read again next time. They were marked before the call. An import
adds each round's items to its total and ends when a round adds none, so what is offered for the
first time on the page is counted separately (`offeredKeys`, `own_pages.js:1135, 1161-1174, 1362`):
an item offered again is retried, not counted again.

Tests that fail without it. `tests/test_qc4_t1_sent_on_answer.py::test_items_the_studio_never_answered_are_offered_again`
(the harness's `unreachable` answer, then a scroll, then a studio that is back),
`::test_items_the_studio_kept_or_refused_are_not_sent_again`,
`::test_an_import_while_the_studio_is_down_counts_each_item_once_and_ends`.

Falsified. The import counting what it re-offers: the import test failed (the import never ended
in 60 s of page time), then passed restored.

## Item 5. The gate race, the DOM marker, the refused row, EXTRACTORS aligned

What changed.

- Gate race. `networkReadingOn` starts `null`, not `false`; an interceptor message that arrives
  before the storage read resolves is held (up to 20) and handled once the switch is known, or
  dropped if it is off (`content.js:92-96, 131-143`). The off-check stays word for word where the
  existing guard reads it.
- DOM marker. The interceptor sets `data-inox-voyager="1"` on the document, so the isolated world
  can say whether the page carries it (`studio/extension/voyager_interceptor.js:33-46`); the page
  heartbeat reports it as `injected`.
- Refused row. A creator-analytics reading refused for identity writes its captures row, with
  `refused = 'identity'`, before the refusal is raised (`onboarding.py:686-722`); the reader
  reads "refused" with the reason (`onboarding.py:565`), not `never_run`.
- EXTRACTORS. The three schema names content.js sent and no screen listed
  (`voyager_identity_profiles`, `voyager_social_actions`, `voyager_feed_comments`) are listed,
  opt-in (`onboarding.py:394-421`); a name outside the registry is refused rather than logged
  (`onboarding.py:645`).

Tests that fail without it. `tests/test_qc4_t1_routes_and_gate.py::test_a_capture_that_arrives_before_the_switch_is_read_is_kept`
(the fake storage holds its answer until released), `::test_a_capture_that_arrives_before_a_switch_that_is_off_is_dropped`,
`::test_the_interceptor_marks_the_document_for_the_isolated_world`;
`tests/test_qc4_t1_capture_rows.py::test_a_creator_analytics_reading_refused_for_identity_leaves_a_refused_row`,
`::test_the_schema_names_the_extension_sends_are_the_names_the_health_lists`,
`::test_a_schema_name_the_registry_does_not_know_is_refused`.

Falsified. One voyager name removed from EXTRACTORS: the agreement guard failed, then passed
restored.

## Item 7. Navigation API routes

The spike came first, as the gaps table asks. A throwaway MV3 extension with one isolated-world
content script at `document_idle` on a fixture `https://www.linkedin.com/feed/` (headless Chromium
153.0.8010.12, every other request aborted; nothing could reach a studio):

| Navigation | `navigation` in the isolated world | `currententrychange` | `navigate` |
|---|---|---|---|
| `history.pushState` from page code | yes | delivered, type push, already seen when pushState returned | delivered, destination named |
| `history.replaceState` | yes | delivered, type replace | delivered |
| `location.hash` | yes | delivered, type push | delivered |
| Back (traversal) | yes | delivered, type traverse | delivered; `popstate` too |

Result: the events reach the isolated world, in the same task as the pushState, so the item was
built. Brave and Edge are Chromium and were not run.

What changed. Behind `"navigation" in window`, `currententrychange` drives `checkForNavigation`,
which still compares the URL and dispatches `studio:locationchange`, so everything downstream is
unchanged; `navigate` announces `studio:navigating` as the early leaving-page signal
(`content.js:670-681`). The whole-document `MutationObserver` is gone and the poll is a 5 s net
while visible (`content.js:681`).

Tests that fail without it. `tests/test_qc4_t1_routes_and_gate.py::test_a_push_state_is_announced_in_the_same_task_without_a_mutation`,
`::test_a_replace_state_and_a_traversal_are_announced_too`, `::test_the_same_route_is_not_announced_twice`,
`::test_the_document_observer_is_gone_and_the_poll_is_a_five_second_net`,
`::test_without_the_navigation_api_the_poll_still_sees_the_route`.

Nothing consumes `studio:navigating` yet; the readiness work (item 14) would.

## Item 8. The worker's lastCapture, the per-tab badge, the panel from storage (decision D3)

What changed. The relay knows its sender's tab (`background.js:463`). After each relay of the
creator's data the worker writes `lastCapture {path, at, ok, kept, stored, httpStatus, outcome,
tabId}` to `chrome.storage.local` (`background.js:858-885`), on success, on keep (`:1126`), on a
decided refusal (`:1144`) and on a drained capture (`:685`). `stored` is read from the studio's
own answer: the ingest contract's `outcome`, or `written`, `recorded`, `buckets_ingested`,
`followers_saved`, `items_kept`, or `bound`, `updated`, `candidate` (`background.js:843-856`). A
200 that stored nothing, the engagers of other people's posts, is never counted. The badge counts
stored captures per tab with `chrome.action.setBadgeText`, kept in storage and put back on
`onStartup` (`background.js:858-915`). Its background is the studio's green, and its orange while
captures wait or a drift was noticed this session; a tab with no count of its own shows how many
wait, or `!`, so the orange can be seen; a tab is reset with Chrome's documented `null`
(`background.js:888-915, 999-1022`). The colours are the tokens' values as colour arrays
(`background.js:808-810`), because `chrome.action` takes no CSS variable. Opening the side panel
clears the counts (`background.js:483-491`, sent at `sidepanel.js:307`). The panel's header and
the popup render the last capture from storage and follow `storage.onChanged`, with no studio
call (`sidepanel.js:690-761`, `popup.js:26, 199-266`, elements at `sidepanel.html:222-223` and
`popup.html:180-181`). "Captured" is said only of a stored capture; anything else reads "Read
LinkedIn just now; nothing new to keep." The popup carries no count: the privacy policy says
Today shows how many captures wait, and the side panel and the badge carry it in the extension.

Decision D3. The three in-page confirmations of a capture that worked are gone: the engagers
notice (`content.js:1577`), the analytics "synced" notice (`content.js:894`) and the "linked to
your draft" notice (`content.js:1066`). Every notice the creator must act on stays, as does the
import banner with its Stop control and `data-urn`.

Tests that fail without it. `tests/test_qc4_t1_worker_badge.py` (10, the real worker under node),
`tests/test_qc4_t1_panel_from_storage.py` (11, the shipped panel and popup in Chromium). The
existing `tests/test_qc_f3_analytics_page.py::test_a_saved_day_is_reported_as_synced` asserted the
in-page "synced" notice; per D3 it is now `test_a_saved_day_draws_nothing_into_the_page`, and every
not-saved notice in that module is still asserted. That is a changed expectation, not a weakened
one.

Falsified. Counting any 200: `test_an_answer_that_stored_nothing_is_not_counted` failed. No badge
text while captures wait: `test_a_kept_capture_is_said_and_turns_the_badge_orange` failed. Tab
reset with `""` instead of `null`: `test_opening_the_panel_clears_the_badge` failed. The panel
calling any relay a capture: `test_a_relay_that_stored_nothing_is_never_called_a_capture` failed.
The popup with the count: `test_the_popup_says_a_kept_capture_without_a_count` and the existing
`tests/test_privacy_policy_matches_the_code.py::test_it_does_not_credit_the_popup_with_a_count_it_does_not_show`
both failed.

## Item 9. The drift notice

What changed. When a reader's capture report names drift, the worker notes it once per page kind
per browser session (`driftNoticed:<page_kind>` in `chrome.storage.session`) and writes
`lastDrift {extractor, page_kind, fields, at}` to session storage, so the notice never outlives
the session it was measured in; a later clean run of the same reader on the same kind of page
takes it down (`background.js:918-997`). It shows in the panel header ("LinkedIn's feed page:
cannot read commenter name, noticed 2 min ago. See Capture health in Setup.") and the popup, and
in the badge colour and tooltip, never in the page (`sidepanel.js:704-761`).

Tests that fail without it. `tests/test_qc4_t1_worker_badge.py::test_drift_is_noted_once_per_page_kind_per_session`,
`::test_a_clean_run_of_the_same_reader_takes_the_notice_down`;
`tests/test_qc4_t1_panel_from_storage.py::test_the_drift_notice_is_in_the_panel_header`,
`::test_a_drift_kept_in_local_storage_is_not_shown`, `::test_the_popup_names_the_last_capture_and_follows_storage`.

Falsified. Notice kept in local storage: `test_drift_is_noted_once_per_page_kind_per_session`
failed. Clean run not clearing: `test_a_clean_run_of_the_same_reader_takes_the_notice_down`
failed. Panel reading local storage: `test_a_drift_kept_in_local_storage_is_not_shown` failed.

## Item 10. Cadence rules in `_open_next`

What changed, in `studio/backend/today.py`, which owns `_open_next`:

- The first-hours wording. A latest post younger than 24 hours with no analytics reading at all
  is asked for with "Your latest post has no reading yet in its first hours; a reading taken
  early is the first point its settle curve is built from." (`today.py:324-338, 356`). Older
  posts in the window keep the existing sentence.
- The day-7 ask. A latest post 144 to 240 hours old with no `post_analytics` reading taken at 120
  hours of age or later names its analytics page: "...a reading at about a week old is what your
  usual settle age rests on." (`today.py:353-382`).
- The weekly Activity ask. When the "Your posts" reader's last good capture is older than 7 days,
  or there is none, Today names the creator's Activity > Posts page (`today.py:383-393`). It needs
  a post held: with none, "No post of yours has been imported yet." stands.

They are one function, `_cadence_ask` (`today.py:362`), called once from `_open_next`
(`today.py:339`), so the rules tracks 5 and 6 add sit in their own functions. The day-7 ask comes
first: a post is at its week point for four days, while the Activity page can be read any day.

Tests that fail without it. `tests/test_qc4_t1_cadence.py` (9).

Falsified. "First hours" said of a 50-hour-old post: `test_a_post_past_its_first_hours_is_not_said_to_be_in_them`
failed. The no-posts guard was vacuous at first: its fixture's import read nothing, so the step-5
rule returned before the branch, and the guard passed with the fault planted. Rebuilt on the
reachable case, an import that read to the end and held nothing (every card a repost), it failed
with the fault and passed without it.

## The sections report's row: WORKING shown for a reader that read nothing

What changed. `capture_health` (`onboarding.py:538-588`) has five states, listed once in
`CAPTURE_STATES` (`onboarding.py:422-432`): never_run, working (the latest run read something),
read_nothing (the latest run ran, named no drift and saw nothing), drifting, refused. Read_nothing
used to be WORKING. `last_good_at` excludes refused runs. Setup draws READ NOTHING, LAST RUN with
LAST WORKED, and REFUSED: IDENTITY (`OnboardingSurface.tsx:499-511`, dots at `:367-368`); the
help lists the five states (`docs/help/set-up-the-studio-from-your-linkedin.md`).

Tests that fail without it. `tests/test_qc4_t1_capture_rows.py::test_a_reader_whose_latest_run_read_nothing_does_not_say_working`,
`::test_every_state_is_one_the_screens_know`.

Falsified. A sixth state planted in `CAPTURE_STATES`: `test_every_state_is_one_the_screens_know`
failed, then passed restored.

## Found by this track's own review, after the first green runs

Each was found by reading the diff again, or by a guard that already existed, after the item's
own tests were green. Each is fixed, with a test that failed before the fix.

| Found | What it would have done | Fixed in |
|---|---|---|
| The badge counted every relay the studio answered 200 | Counted the engagers of other people's posts, which the studio answers `nothing_new` and does not store: a number no row stands behind | 4b92926 |
| The drift notice was kept in local storage | Outlived the browser session it was measured in | 4b92926 |
| The badge had no text in a tab with no captures | Its orange, for waiting captures or a drift, could not be seen | 4b92926 |
| The panel's header code reached `chrome.storage` before the composer was wired | Any storage error would have stopped the composer; `tests/test_qc_f1b_sidepanel.py` caught it (7 failures) | 4b92926 |
| Both long-frame sources were observed; the overlap test was strict | One slow frame counted twice; a short read inside a long frame not counted | f92d705 |
| The side panel listed never-run network readers with the switch off | NOT SEEN YET for five readers that cannot run | db0edc7 |
| "First hours" was said of a post up to three days old; the weekly ask replaced "No post of yours has been imported yet." | Two wrong sentences on Today | db0edc7 |
| Coverage keys kept the raw pathname | A plain vanity in `/identity/profiles/<vanity>/` would have been stored in the heartbeat log: another member, kept. The privacy defect | b907ffe |
| An import counted items it re-offered after item 4 | With the studio down, an import never stalled: 250 rounds and an inflated total. A regression item 4 introduced | b907ffe |
| The first page heartbeat left before the switch was read | Setup showed no network-reading state for up to a minute after a page opened | b907ffe |
| A coverage observer started again counted the buffer again | Switching off and on in one tab doubled the early counts | b907ffe |
| The popup was given the side panel's lines, the waiting count included | The privacy policy says Today shows the count; `tests/test_privacy_policy_matches_the_code.py` tripped on the first full run | b8287f8 |
| The no-posts cadence guard could not fail | It protected nothing until rebuilt (item 10) | db0edc7 |

## Defect found by track 3 on main: a post first found after migration 26 had no post

Priority defect, present on `main` and so in the released 2.7.0, found and reproduced by track 3 on
`cf0ba9d`. Fixed in 43aadff.

What it did. A post the bridge or the archive first found after migration 26 got no row in
`posts`. `post_identity.resolve` then found nothing, the engagers route answered 404, and Posts
said "NOBODY CAPTURED FROM THIS POST YET." however many people had engaged.

Cause. Migration 26 gave every publication the studio held its posts row, once: bind it to the one
studio record its words match, else make one from it. Nothing applied that rule afterwards. The
activity reader bound a post only when a studio draft matched (`onboarding._bind_to_studio`, which
called the binder alone), the archive import wrote the publication alone, and an engager read on
the creator's own post left no record of the post at all. The analytics reader refuses a post the
studio has never recorded, by design, so it could only meet a publication already left without a
post.

What changed.

- The rule is one function, `post_identity.ensure_post` (`studio/backend/post_identity.py:862`):
  the post the publication already names or a post already carrying its id in any of LinkedIn's
  three namespaces; else the one studio record the binder (`bind_activity_urn`) proves is its
  source; else a post made from the publication, keyed by its URN as migration 26 keyed them.
  `heal_publications` (`:953`), `anything_to_bind` (`:923`), `forget_reconstruction` (`:973`) and
  `forget_reconstructions` (`:936`) are its companions.
- Every path that can first find a post calls it: the activity reader (`onboarding.py:1261`, still
  the one binder's caller, now through the rule); the engager route (`routers/crm.py:193`, through
  `onboarding.note_own_post` at `onboarding.py:1284`, which records the publication of a post the
  studio had never seen, joins an archive record of it, and writes nothing for a post a studio
  record already carries, `:1317`); the post analytics reader (`onboarding.py:1239`); and the archive
  import (`archive_import.py:1046, 1057`), whose removal takes the posts it made (`:1363`).
- A post made from a publication stands in for it. While nothing in the studio has touched it (no
  tags, no media, not from the drafts store) it gives way to the studio record the binder proves is
  the source (`post_identity.py:575, 806`). Without this, an engager read before the page's text was
  offered (the usual order on a post's own page) would have stopped the studio's own post from
  binding, and a post pasted in and marked published afterwards (WRITE-18) would never link. Its
  words follow its publication's, which LinkedIn lets the creator edit.
- Migration 28 gives every publication left without a post its post on upgrade, by the same rule
  (`migrations.py:1471`), and its name now says so. It stays the track's one migration.

Found on the way, each fixed in the same commit with a test:

- The engagers route answered with nobody for an archive post the bridge had read: `_ref` took the
  post's URN as the publication's (`post_identity.py:326`), so the activity id the publication takes
  when the bridge joins it, the id its engagers are filed under, dropped out.
- Search showed a post made from a publication as an editable studio post instead of as the
  publication, published on LinkedIn and opened in analytics (`universal_search.py:584`).
- Forgetting the creator left the posts made from their publications, which hold their post text and
  LinkedIn ids (`onboarding.py:1081`). Migration 26's own posts were already left this way.
- The lookups the import repeats were scans: `bound_post` compared every bound post's id in Python
  and the legacy-draft step scanned `posts` once a call. A 3,000-post archive went from 0.29 s on
  `main` to 20.4 s; with indexed lookups (`post_identity.py:341, 363`) and the binder asked once per
  import whether anything could bind (`archive_import.py:1019`), it takes 1.0 s.

Tests that fail without it. `tests/test_qc4_t1_one_post_identity.py` (15): a post first read on
the activity page, first seen through its engagers, known only from the archive and then read on its
analytics page, and brought by an archive import, each answers for its engagers; the analytics page
alone still does not make a post the creator's; a post read twice is one post; removing the archive
import takes its posts; engagers filed under the activity id of an archive post are found; an engager
read before the bind does not take the studio's post; a post made from its words gives way to the
post marked published later; a post the creator has touched does not; an engager on a post the
studio carries records nothing new; forgetting the creator takes the posts made from their
publications; the upgrade gives every publication its post again, binding where a draft matches and
running twice to the same result; and the guard below. Of the twelve written before the fix, eleven
failed on `cf0ba9d`'s code and the analytics-alone test passed, which is the design it holds; the
other three (the post marked published later, the touched post, the carried post) came with the
stand-in rule and fail without it.

The guard. `test_every_writer_of_a_post_or_its_engagement_goes_through_the_one_rule` reads every
function in `studio/backend` from its syntax tree. A function that inserts into `own_posts` must
pass a way through the rule after the insert, on the way out of the function; a function that writes
an engagement must take one anywhere around it, because the route makes the post known first.
Comments and docstrings do not count. The ways through are named, and each must itself call the next
step down to `ensure_post`. Only the rule's own module, the one low-level engagement writer (its
callers are held instead) and the migrations are exempt.

Falsified. Thirteen planted faults, each run against its behaviour test and, for the three ingest
paths, against the guard too: all sixteen checks failed with the fault and passed with it removed.
The first version of the guard was function-granular and passed when the call beside the archive
insert was removed (the function still called the rule in its other branch); it now follows the
flow from each insert. The first version of the activity-reader test captured an engager before
asking, so the engager path healed the post and the test passed with the activity reader broken; it
now asks first. The first version of the stand-in rule kept a post made from words when a later
studio post matched, which broke WRITE-18 and two existing binding tests; it now yields to whatever
the binder would have bound.

Existing tests changed by this fix. `tests/test_today.py`'s cleanup now also removes the posts made
from the publications it removes: left behind, every module's imports made other modules' posts look
like the creator's to Today. Nothing it asserts changed.

Files outside this track's ownership: `studio/backend/routers/crm.py` (the engager ingest route
only), `studio/backend/archive_import.py` (track 7's file; the posts insert and the posts removal
only), `studio/backend/universal_search.py` (one clause), `tests/test_today.py` (its cleanup).

Not done, with the reason. Network reading's `feed_updates` schema writes a reading for every post in
LinkedIn's feed response, the creator's or not (`onboarding.record_voyager_ingest`); it writes no
publication or post, so it is outside this defect, and it is listed for the coordinator.

## Second round: the review of f18e610, and two defects before it

The independent review of `f18e610` found no blockers, nine should-fix findings and eighteen notes.
The coordinator added two items first: the privacy defect below, and the sections report's row 5,
Voyager drift. Each finding has its own commit and a failing test first.

### Privacy defect: network reading kept other members' posts

Raised by the coordinator from a gap this track left listed. Fixed in 0afff61.

What it did. With network reading on, the feed ingest stored a reading for every post in the
creator's LinkedIn feed response: other members' post identities and their engagement figures, with
a summary row for each, in the creator's database. The three schemas that carry other members
(profiles, reactions on posts, comments) were relayed to the studio as well; the studio stored
nothing of their data, but logged a run for each and kept their drift events, whose address for a
profile names the member.

What changed.

- The feed ingest keeps a reading only for a post that is the creator's own: one of their
  publications, or a post the studio carries, in any of LinkedIn's three spellings of its id, each
  looked up by its index (`onboarding._creators_post`, `studio/backend/onboarding.py:810`). Every
  other entry is dropped before anything is written (`:732`), and the run records how many, as a
  number only, in a new `captures.items_dropped` column (migration 28).
- What each schema keeps (`VOYAGER_KEPT`, `onboarding.py:437`):

  | Schema | What it keeps |
  | --- | --- |
  | `feed_updates` | readings of the creator's own posts; every other post in the response is dropped and counted |
  | `creator_analytics` | the creator's follower count, for the confirmed account |
  | `identity_profiles` | nothing: not copied by the interceptor, not sent by the page, refused by the studio |
  | `social_actions` | nothing, likewise |
  | `feed_comments` | nothing, likewise |

  The one thing the product keeps about another member, an engager on the creator's own post, comes
  from the DOM engagers reader, by design, and is unchanged.
- The interceptor copies only the two kept schemas' responses (`voyager_interceptor.js:67`);
  `content.js` forwards only those two (`FORWARDED_SCHEMAS`, `content.js:98, 176`); the studio
  refuses the other three on both of its routes (`onboarding.py:547, 667, 719`). `EXTRACTORS` lists
  the two network readers that keep something.
- A drift event keeps its address as the words of LinkedIn's API, every other segment `_id_`
  (`clean_voyager_path`, `onboarding.py:473, 690`), the allowlist finding S1 asks for, used here first.
- Migration 28, after the ledger's backup, deletes the readings of posts that are not the creator's,
  recomputes their summaries (an empty one is removed), deletes the drift events of the three
  schemas, and cleans the address of the rest (`forget_other_members_readings`, `onboarding.py:824`,
  called at `migrations.py:1487`).

Tests that fail without it. `tests/test_qc4_t1_voyager_privacy.py` (10): a feed response mixing
the creator's posts with other members' keeps only the creator's, with no summary, publication or
post for the others and their count only on the run; a feed of other members writes nothing about
them; a post the studio carries counts as the creator's; each of the three schemas is refused with
nothing written; a drift event keeps a path that names nobody, and one for profiles is refused; the
upgrade removes what the old behaviour stored, on a database built with both kinds of rows.
`tests/test_qc4_t1_routes_and_gate.py::test_a_response_about_other_members_never_leaves_the_page`
holds the page.

Falsified, by planting the old behaviour, one fault at a time: the feed ingest keeping every post (2
tests failed), the studio taking any schema (3 failed), a drift event keeping its raw address,
migration 28 without the clean-up, the page forwarding every schema, and the interceptor copying
reactions again; each failed and passed again with the fault removed. A first plant, one of the
studio's two refusals removed, was caught by neither guard, because the other refusal still held;
the plant was replaced by the old behaviour itself.

Existing tests changed by this fix. `tests/test_qc_f3_network_reading.py`'s endpoint test asserted
the interceptor copied reactions and comments; it now asserts it copies the kept schemas' endpoints
and not the three about other members. `tests/test_qc4_t1_capture_rows.py` and
`tests/test_qc4_t1_network_reading_state.py` follow the two network readers.

The privacy policy. Two sentences in `docs/PRIVACY_POLICY.md`, section "Only if you switch 'Read
LinkedIn's network responses' on", no longer match the code, and the coordinator applies the change
at merge (tracks 6 and 7 own the policy):

- Item 1 says the script copies the JSON of responses for "feed updates, profiles, creator
  analytics, social actions and comments". It now copies only feed updates and creator analytics,
  and keeps from them the figures of the creator's own posts and their follower count; every other
  post in the feed response is dropped before anything is written.
- Item 2 says the extension notes "the address, the HTTP status and the method" of each data
  request. What is stored is the address cut before any part that names a member (by
  `studio/core/telemetry_shard._path_shape`, unchanged here), the status and the method; the
  coverage meter, if the policy mentions it, sends counts by the words of an address and a GraphQL
  query name only (finding S1 below).

Checked and left. The worker's request observer forwards the address of three request families to
the telemetry store, which already cuts a path before `/identity/profiles` and replaces URNs; it is
outside this fix and unchanged.

## Guards that already existed and held

Five existing guards caught a draft of this work, and the code was changed to satisfy each:

- `tests/test_network_reading_is_opt_in.py::test_feed_cards_get_their_post_id_whether_or_not_network_reading_is_on`
  forbids `postMessage` in `card_urns.js`; the stamper reports through a root attribute instead.
- `tests/test_network_reading_is_opt_in.py::test_the_page_cannot_feed_it_while_off` reads the
  off-check word for word; it stays word for word.
- `tests/test_own_pages_extension.py::test_a_strangers_profile_does_not_leave_the_page` reads the
  ownership check; the profile read is timed after it, not around it.
- `tests/test_qc_f1b_sidepanel.py` caught the panel's header code reaching storage too early.
- `tests/test_privacy_policy_matches_the_code.py` caught the popup showing the waiting count.

## Could not do, and why

- What LinkedIn calls today, and which of the three sentences the owner's install will say, were
  not run against LinkedIn: no live check is permitted from here. Both arrive from the owner's
  browser after one reload of the extension; until then Setup and the panel say "not reported",
  never "off".
- The reader timings above are fixture pages. The decision on items 14 to 17 needs the owner's
  own rows (`captures.duration_ms`, `slow_reads`, `long_tasks`), which no screen shows yet.
- Long frames name the page, not the extension (measured above), so `long_tasks` is a count of
  long frames that coincided with a read, not an attribution of cost to the read.
- The badge colours are the token values written as colour arrays; when the tokens change, these
  three lines must follow. Phase 3's copy of the tokens file into the extension can generate them.
- Item 2 asks for a migration. The two heartbeat columns are in the track's one migration, with
  the six captures columns.
- Phases 2 and 3, and decision D1's setting, were not started, by the brief.

## For the coordinator

- The privacy policy (`docs/PRIVACY_POLICY.md`, tracks 6 and 7) lists what the extension keeps
  "In the browser". This track adds four keys, none holding anyone's name, and the policy should
  say so before release. Suggested words, after "so that your own activity is not lost": "; a
  record of the last capture, saying what kind of thing it was, when, what Inox Hydra answered and
  which tab it came from, never who; this session's count of captures per tab; and, until the
  browser closes, the last notice that a part of the capture could not read a page, naming the
  part, the kind of page and the fields." While network reading is on, the heartbeat also carries
  counts of LinkedIn's data calls by the words of their address, from a fixed list of the words
  LinkedIn's API uses, every other part written as a blank, and by GraphQL query name or "other"; they are kept with the heartbeat log on this
  computer for its seven days.
- `studio/backend/docs_engine.py` files every document under `docs/` in a help section, and each
  track's record needs the same one-line addition beside `quality/CYCLE3_REGISTER.md`; this
  branch adds `quality/cycle4/t1-bridge.md`. A prefix rule for `quality/cycle4/` at integration
  would serve all seven.
- Commit trailers: the six commits before an interruption carry the trailer then in use; the
  commits after it carry the trailer the environment now specifies.

## Files outside this track's ownership that were touched

- `studio/ui/src/components/OnboardingSurface.tsx` (track 4's, for the health move): only
  `healthLine`, `bridgeLine` and the two dot-colour lines (`:367-368, 486-511`).
- `studio/ui/src/lib/api.ts`: the `CaptureHealth` fields, `NetworkReadingState`, and
  `BridgeStatus.network_reading` (`:1751, 1798-1830`).
- `studio/backend/today.py` (shared with tracks 5 and 6): `_cadence_ask` is its own function, but
  the first-hours wording is inside `_open_next`'s existing analytics branch (`today.py:324-338`),
  a region track 6's desk-request rule may also touch.
- `studio/extension/own_pages.js`, beside track 5's region: one line, `beginRead("post_analytics")`
  (`:1243`), sits directly above `readPostAnalytics()`. Nothing in `POST_METRIC_LABELS`,
  `NUMBER_ONLY` or `parseCount` was edited.
- `studio/backend/docs_engine.py`: one path, this record's (see above).
- Help articles beyond the extension's: `set-up-the-studio-from-your-linkedin.md`,
  `read-your-analytics.md`, `why-is-my-analytics-chart-empty.md`, `why-is-my-lead-list-empty.md`,
  `what-leaves-this-machine.md` (the per-page counts and the extension's own capture record), and
  `docs/EXTENSION_AND_SYNC.md`.
- Shared tests: `tests/qc_f3_pages.py` gains a `session` storage area and an optional `session=`
  argument; `tests/test_qc_f3_analytics_page.py` as described under item 8.

## The suite, as CI runs it

`pytest tests studio/tests -q -rs` from the worktree, with the project interpreter, after
`npm --prefix studio/ui run build`:

| Run | Passed | Skipped | Failed |
|---|---|---|---|
| Before this track's own review fixes | 3,192 | 17 | 1: the privacy tripwire on the popup, fixed in b8287f8 |
| After them | 3,193 | 17 | 6: `tests/test_qc_f4b_history.py` runs `runImport` beside stand-ins for its closure, and the new `offeredKeys` was not among them; the stand-in now declares it, assertions unchanged (c1ebd5f) |
| Final, at 1a9c606 | 3,199 | 17 | 0 |

The 17 skips are the suite's own and none is in this track's modules: Windows and macOS
primitives (the tray, autostart, the mutex, Job Objects, the Keychain, LaunchAgent), a desktop
with browsers installed, one interface state the suite marks as current, and `pyyaml`, which this
interpreter does not have. This record's own commit, which came after the final
run, was checked again with `tests/test_docs_library.py` and `tests/test_phase4_algorithmic_safety.py`.
