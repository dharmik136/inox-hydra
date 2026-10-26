# Cycle 4, track 2: the show path

Companion to [CYCLE4_2026-10_PRD.md](../CYCLE4_2026-10_PRD.md), section 6, track 2. Branch
`qc4/t2-show`, from `main` at `cf0ba9d` (2.7.0, schema 27). Specification: the capture report,
section Show (the studio side), the "Show is polling" paragraph, the freshness options and
programme item 12; the sections report, batch 7, and its defect row on Today's once-read side
panels. Line numbers are at the branch head this record was committed with.

| | |
|---|---|
| Items built | 8 of 8: the stream, the bus, the backstop, the event trigger, the three intervals, Today's side panels, the header's mark, one stream per window closed when hidden |
| New test modules | 3, 67 tests after round 2 (`tests/test_qc4_t2_show_stream.py` 43, `tests/test_qc4_t2_show_browser.py` 19, `tests/test_qc4_t2_show_cost.py` 5) |
| Round 2 (review) | S2 9693a25; S1 d612112 and a3963c1; S3 and the notes deferred; the load cases measured on main, round 1 and round 2 (below) |
| Guards falsified | 34 planted faults (22 in the server, 12 in the interface), each seen failing; 2 guards were vacuous at first and were rebuilt (below) |
| Setup, one idle minute in a real browser | 1,743 statements to 273; 684 SELECTs to 72; 125 connection opens to 17 |
| Security checks | `security.py` unchanged; the stream passes Host, Origin and token as every route does |
| Interface audit | `tools/ui_audit.py`, every section, dark and light, desktop and phone: 48 screens, 0 blocking findings, 0 console errors, 0 egress |
| Migration | None needed |
| Suite, as CI runs it | See the last section |

| Item | State | Commits | Review |
|---|---|---|---|
| 1. `/api/v1/events` as Server-Sent Events | fixed | ac99d6c | |
| 2. The in-process bus, set by the ingest paths | fixed | ac99d6c | |
| 3. The `PRAGMA data_version` backstop on one long-lived connection | fixed | ac99d6c | |
| 4. `useRefresh` gains an event trigger | fixed | d123fe6 | |
| 5. One stream per window, closed when hidden, reopened on return | fixed | d123fe6 | |
| 6. The header's bridge mark follows the stream | fixed | d123fe6 | |
| 7. Today 120 s, Setup and Activity a 30 s backstop | fixed | 024077e | |
| 8. Today's six side panels under refresh | fixed | 024077e | |
| Measured before and after | recorded | 024077e | |
| The help sentence | updated | 024077e | |

## Item 1. The stream: GET /api/v1/events

What changed. `studio/backend/routers/events.py:99-114` serves a `text/event-stream`, included
beside the other routers at `studio/backend/app.py:2027-2035`. The first event, `hello`
(`events.py:67-78`), names the profile served, because `EventSource` cannot send
`X-Inox-Profile`, and says whether anything changed since the id the window last heard, which the
window sends as `?since=` when it reopens and the browser sends as `Last-Event-ID` on a reconnect
of its own (`events.py:106-109`). A `change` event carries the kinds that changed; a burst is one
message, because a change waits 0.25 s for the rest of its burst (`events.py:50, 84-90`). A comment
every 15 s keeps a quiet stream open (`events.py:48, 91-94`); `retry: 2000` tells the browser how
long to wait before reconnecting (`events.py:55, 78`). An id is the process's boot name and its
count of changes (`studio/backend/changes.py:98, 144-146`), so a window reconnecting across a
restart is never told "nothing changed" by a count that happens to match.

The three checks. The route sits behind `enforce_local_access` like every other `/api` path, and
`security.py` is not touched. Tested over a real socket against a real uvicorn server, because the
test client cannot show what a browser sends:

| Request | Answer | Test |
|---|---|---|
| Only the same-origin cookie, no Origin, as `EventSource` sends it | 200, `text/event-stream`, `hello` first | `test_the_cookie_alone_opens_the_stream_as_a_browser_would` |
| The studio's own Origin with the cookie | 200 | `test_the_studio_own_origin_is_accepted` |
| `https://evil.example`, `https://www.linkedin.com`, `null`, each with the cookie | 403 | `test_a_foreign_origin_is_refused_even_with_the_cookie` |
| No credential | 401 | `test_no_credential_is_refused` |
| A wrong `X-Inox-Token` | 401 | `test_a_wrong_header_token_is_refused` |
| The exempt list is still the two health paths | | `test_the_route_answers_behind_the_same_checks_as_every_other_route` |

Lifetimes. uvicorn waits for every response in flight before it exits, and with no graceful
timeout it waits for ever, so an endless stream would hold `--reload`, Ctrl+C and the desktop
shell's stop. `changes._hook_server_stop` (`changes.py:367-392`) wraps uvicorn's
`Server.shutdown` the first time a stream opens, and ends the streams served on that server's own
loop before uvicorn waits (`changes.py:195-207`). Tests: `test_the_server_stops_promptly_with_a_stream_open`
(stopped by the same signal path a reload sends), `test_a_stopping_server_ends_only_its_own_streams`
(the test process runs several servers), `test_a_client_that_goes_away_is_let_go`.

Measured with a real `uvicorn --reload` studio, a window listening on Setup, and a file touched in
the watched folder: the change was seen at 0.05 s, the old worker shut down at 0.15 s and finished
at 0.25 s, the new worker was ready at 0.65 s, and uvicorn never printed "Waiting for connections
to close". A capture posted to the new worker then reached the open Setup 0.30 s after it was
saved, which only a reconnected stream can explain: Setup's backstop is 30 s. Playwright reports
no second request for a reconnect the browser makes by itself, so the evidence is the capture, not
a request count.

## Item 2. The bus

What changed. `studio/backend/changes.py`: `publish(kind, **identifiers)` is safe from any thread
(the ingest routes run on the thread pool, the interactions ingest on the single writer) and wakes
each listening stream on its own loop with `call_soon_threadsafe`. Kinds are words, never figures:
`capture`, `heartbeat`, `posts`, `readings` (one post's figures), `account` (the daily totals),
`people` (someone engaging with a post of the creator's), `outbound`, `identity`, `imports`,
`queue`, and `database` for a write nothing named. Since round 2 each change also carries the
small identifiers a screen decides by (`IDENTIFIERS`, `FLAGS`): which reader ran and whether it
drifted, whether a heartbeat carried a waiting count, which post, how someone engaged and who by
the studio's own id. Never a name, text or figure: an identifier of the wrong shape is dropped,
and a change without one means "this kind, anywhere". Nothing starts at import.

The writers, one line each, after the write commits (lines at this record's last commit):

| Path | Line | Kind and identifiers | Test |
|---|---|---|---|
| The heartbeat route, after the waiting count is recorded | `studio/backend/app.py:1551` | heartbeat, `waiting` | `test_a_heartbeat_reaches_an_open_stream`, `test_a_heartbeat_says_whether_it_carried_a_waiting_count` |
| `record_capture` | `studio/backend/onboarding.py:328` | capture, `extractor`, `drift` | `test_a_capture_reaches_an_open_stream_within_a_second`, `test_a_capture_names_its_reader_and_whether_it_drifted` |
| `record_voyager_ingest` | `onboarding.py:495` | readings, or account for the account's figures | `test_a_network_reading_says_readings`, `test_a_network_reading_of_the_account_says_account` |
| `ingest_own_posts` | `onboarding.py:933` | posts | `test_the_creators_posts_say_posts` |
| `ingest_post_analytics` | `onboarding.py:1002` | readings, `post` | `test_a_posts_analytics_page_says_readings`, `test_a_posts_reading_names_the_post` |
| `ingest_outbound` | `onboarding.py:1086` | outbound | `test_the_creators_outbound_activity_says_outbound` |
| `update_import` | `onboarding.py:1627` | imports | `test_an_import_event_says_imports` |
| The identity observe route, when it wrote | `app.py:1616` | identity | `test_the_creators_own_profile_page_says_identity` |
| The creator analytics ingest | `studio/backend/routers/analytics.py:570` | account (people, or database, for the older payloads that carry leads or posts) | `test_the_creators_analytics_page_says_account` |
| The interactions ingest | `studio/backend/routers/crm.py:220` | people, `interaction`, `post`, `lead` | `test_an_engagement_on_the_creators_post_says_people`, `test_an_engagement_says_how_on_which_post_and_who_by_id_only` |
| The queue's dispatch, only when it moved a post | `studio/backend/scheduler.py:573-574` | queue | `test_a_post_the_queue_marks_due_says_queue`, `test_a_queue_check_that_moved_nothing_says_nothing` |
| The score and summary catch-ups, derived writes | `studio/backend/crm.py`, `catch_up_scores`; `studio/backend/post_summary.py`, `catch_up` | none: `changes.derived_written()` wakes nobody and keeps the backstop from reporting the write | `test_a_read_that_brings_derived_figures_up_to_date_wakes_nobody`, `test_the_score_catch_up_wakes_nobody`, `test_the_summary_catch_up_wakes_nobody` |

`test_every_path_the_extension_writes_through_is_accounted_for` reads the extension's relay list
and fails when a path is added without being announced or given its reason here.

Without its line each of these writes is still noticed by the backstop, as `database`, so every
test asserts the kind; removing any one line fails its test.

## Item 3. The backstop: PRAGMA data_version

What changed. `changes.py:214-342`, class `_Watch`. One long-lived connection, opened through
`sqlite_open.connect` (so it waits while a restore holds the files), set `query_only`, read with
`fetchall` so no read transaction stays open to hold back a checkpoint or a VACUUM. It looks once a
second while any window listens (`WATCH_EVERY_S`, `changes.py:70`). SQLite changes `data_version`
whenever another connection commits, in this process or another, and every write in the studio
opens its own connection, so the watcher sees the CLI, a second studio and every unhooked path:
the lead interactions ingest, identity observe and confirm, import events, the analytics ingest.
It announces `database` only when the value moved and nothing was published since its last look,
so a hooked write is not announced twice (`changes.py:274-288`).

It stops looking the moment the last window leaves and closes its connection a minute later
(`IDLE_CLOSE_S`, `changes.py:78, 297-319`), so a studio with no window in view runs nothing and
holds no handle on the file; a window back within that minute is told truthfully whether anything
changed, and one back later is told to read again. The restore puts the watcher down with the rest
of the background database work and lets it go after (`studio/backend/support.py:1171, 1181`),
because Windows refuses to replace a file any handle holds; the reopened watcher tells the windows
to read again.

Tests: `test_a_write_the_bus_was_not_told_about_is_still_noticed` (another connection),
`test_a_write_from_another_process_is_noticed` (a child process writing with plain `sqlite3`),
`test_an_announced_write_is_not_announced_twice`, `test_a_write_while_nobody_listened_is_reported_on_return`,
`test_nothing_watches_the_database_while_nobody_listens`, `test_a_window_back_after_the_watcher_let_go_is_told_to_read_again`,
`test_the_watcher_is_put_down_for_a_restore_and_picks_up_after` (through `support._put_the_database_down`).

## Item 4. useRefresh gains an event trigger

What changed. `studio/ui/src/lib/refresh.ts:180-234`: a third argument, `on`, names the kinds a
screen listens for. When the stream reports one, the screen reads again at once, or once a second
has passed since its last read (`CHANGE_GAP_MS`, `refresh.ts:12`), with a read already waiting
covering whatever comes next; a burst is one read and one more. The existing triggers (studio
back, coming back after 15 s, the timer) are unchanged. Tests: `test_a_capture_reaches_setup_within_about_a_second`,
`test_a_post_reaches_activity_within_about_a_second`.

## Item 5. One stream per window, closed when hidden

What changed. `refresh.ts:81-156`: the stream is module state, opened once by the shell
(`studio/ui/src/App.tsx:283`), whichever screen is open, because the browser allows six connections
to the studio and a stream per panel would spend them. It is closed when the window is hidden and
reopened on return naming the last id it heard (`refresh.ts:137-156`). After the first hello, a
hello that says something changed is announced as a catch-up carrying the moment the window came
back, and a screen that already read on coming back skips it (`RETURN_SLACK_MS`, `refresh.ts:19,
212`), so a window back after 15 s reads once, not twice. A hello naming another profile makes the
screens read, and the answer marks the window stale as every read does (`refresh.ts:92-107`). A
refusal closes the stream for good; coming back into view or the studio answering again reopens
it (`refresh.ts:115-121, 147`).

Tests: `test_one_stream_for_the_window_whichever_screen_is_open` (one request across six screens;
the studio counts one listener), `test_a_hidden_window_closes_its_stream_and_reopens_it_on_return`,
`test_a_capture_while_the_window_was_hidden_is_read_on_return`, `test_a_window_back_with_nothing_changed_reads_nothing`,
`test_a_window_back_after_a_while_reads_once_not_twice` (it watches Today's waiting count, which
has no timer that could fire inside the count on a slow machine).

Checked once by hand, because every browser test blocks service workers: with the studio's own
pass-through worker in control of the page, the stream ran through it (`from_service_worker` true),
was still listening after 45 idle seconds, past Chrome's 30 second worker idle limit, and a capture
reached Setup 0.30 s after it was saved. `sw.js` needed no change.

## Item 6. The header's bridge mark follows the stream

What changed. `App.tsx:58, 331-353`: after a heartbeat the header waits 1.5 s for a screen to
report the bridge, and reads it itself if none did, so on Queue, Posts or any screen that does not
read the bridge the mark turns connected within seconds instead of within a minute. The minute's
read stays (`App.tsx:330`), because nothing is written when the bridge goes quiet, so only time can
say it has. Test: `test_the_header_mark_follows_a_heartbeat_on_a_screen_that_does_not_report_it`.

## Item 7. The intervals

What changed. Today 30 s to 120 s (`studio/ui/src/components/TodaySurface.tsx:79, 140`); Setup 3 s
to a 30 s backstop (`studio/ui/src/components/OnboardingSurface.tsx:43, 85`); Activity 2.5 s to a
30 s backstop while auto refresh is on (`studio/ui/src/components/ActivitySurface.tsx:117, 169`).
Each screen reads with `ANY_CHANGE`, so a capture reaches it within about a second; the browser
tests time it from the moment the capture was saved, not from before the write, and allow two
seconds against the 30 s backstop. The probes measured 0.30 s.
Tests: `test_an_idle_setup_reads_twice_a_minute`, `tests/test_qc4_t2_show_cost.py` (the ceiling),
and `tests/test_qc2_r5_refresh.py::test_activity_does_not_poll_a_hidden_window`, which pinned the
2.5 s poll (at least 3 reads in 10 visible seconds) and now pins the backstop (at least 2 reads in
65 visible seconds, none in two hidden minutes). `tests/test_qc3_t4_activity_stream.py`'s docstring
said the screen reads every 2.5 s; it now says what the screen does.

## Item 8. Today's six side panels under refresh

What changed. `TodaySurface.tsx:148-161`. Evidence, cadence, the thirty day totals, the week's
slots, the waiting captures and the backup schedule were each read once per visit, so a panel's
"It is read again when this window comes back" was true of the brief alone (the sections report's
defect row, "Nothing invented", Today's panel failure sentence), and the waiting count could be
stale for the whole session. Each is now read again on coming back to the window and when the
studio is back, and when the stream says what it shows changed: evidence on posts and readings,
cadence on posts and the queue, the totals on the account's figures (`account`, since round 2),
the slots on the queue, the waiting count on a heartbeat that carried one (only the extension knows
it), and every panel on a write nothing named; at most once per fifteen seconds since round 2. None
is polled.
Test: `test_today_says_how_many_captures_wait_as_the_extension_reports_it`.

## Measured before and after

The number of SQL statements the studio executes while one screen sits open and idle. Two ways,
which agree.

A wall-clock minute in a real browser: the studio served in process with `sqlite3.connect`
traced, so every statement on every connection is counted, the watcher's included; a confirmed
creator; headless Chromium idle on the screen for 60 s after it settled.

| Screen | Requests | Statements | SELECT | PRAGMA | Connection opens |
|---|---|---|---|---|---|
| Setup, before | 20 | 1,743 | 684 | 993 | 125 |
| Setup, after | 2 | 273 | 72 | 189 | 17 |
| Activity, before | 25 | 1,123 | 316 | 801 | 101 |
| Activity, after | 2 | 193 | 30 | 157 | 13 |
| Today, before | 2 | 281 | 92 | 177 | 23 |
| Today, after | 1 | 188 | 38 | 141 | 11 |

Per poll, through the application (`tests/test_qc4_t2_show_cost.py`, the second of two calls so
the first call's one-time work is not counted), times the polls a minute each screen declares,
plus the watcher's 60 looks a minute: Setup 85 statements a poll (34 SELECT, 48 PRAGMA, 6 opens),
1,700 a minute before and 230 after; Activity 45 a poll, 1,080 before and 150 after; Today 116 a
poll, 232 before and 118 after. The test holds Setup and Activity under 400 a minute.

The capture report's "about 660 SELECTs a minute" on Setup, estimated from the code, measured 684;
it is now 72. The PRAGMAs are `get_db`'s six or seven per open, and the opens fell with the reads.

Today, after, read `onboarding/state` once and not its own brief: its own read is every two
minutes now, and the header's minute read, which never fired on Today when Today reported the
bridge every 30 s, now fills the gap. Per two minutes that is one brief and about two header reads
against four briefs before.

## The help

`docs/help/what-to-do-today.md:5` said Today "refreshes itself every 30 seconds". It now says
Today reads again within about a second of the studio saving a capture, and every two minutes and
on coming back, which is how it notices the bridge going quiet. No other article describes how
quickly the studio notices a capture (searched for "every few seconds", "refresh", "as it
arrives", "polls" and "seconds").

## Guards, and how each was falsified

Each fault was planted in the source, the guard run and seen failing, and the file restored; the
interface faults were built before their browser test ran, and the bundle rebuilt clean after.

| Fault planted | Caught by |
|---|---|
| Each of the seven publish lines removed (heartbeat, capture, network reading, own posts, post analytics, outbound, queue) | its row in the item 2 table |
| The queue publishes on every check | `test_a_queue_check_that_moved_nothing_says_nothing` |
| The restore no longer puts the watcher down; never lets it go | `test_the_watcher_is_put_down_for_a_restore_and_picks_up_after` |
| `/api/v1/events` added to the exempt list | `test_no_credential_is_refused`, `test_the_route_answers_behind_the_same_checks_as_every_other_route` |
| Any origin allowed | `test_a_foreign_origin_is_refused_even_with_the_cookie` (3) |
| The backstop never announces; announces hooked writes again | `test_a_write_the_bus_was_not_told_about_is_still_noticed` and `test_a_write_from_another_process_is_noticed`; `test_an_announced_write_is_not_announced_twice` |
| No stop hook; a stopping server ends every stream | `test_the_server_stops_promptly_with_a_stream_open`; `test_a_stopping_server_ends_only_its_own_streams` |
| Ids without the boot name | `test_a_reconnect_is_told_whether_anything_changed_while_it_was_away` |
| A gone stream never let go | `test_a_client_that_goes_away_is_let_go` |
| No coalescing | `test_a_burst_is_one_message_not_ten` |
| The watcher never lets the file go; looks with nobody listening; a reopened watcher assumes nothing changed | `test_nothing_watches_the_database_while_nobody_listens` (2); `test_a_window_back_after_the_watcher_let_go_is_told_to_read_again` |
| A hidden window keeps its stream; comes back without naming what it heard | `test_a_hidden_window_closes_its_stream_and_reopens_it_on_return` (2) |
| A stream per screen | `test_one_stream_for_the_window_whichever_screen_is_open` |
| The header does not follow the stream | `test_the_header_mark_follows_a_heartbeat_on_a_screen_that_does_not_report_it` |
| Setup back to 3 s; Activity back to 2.5 s | `test_an_idle_screen_stays_under_the_ceiling` and `test_an_idle_setup_reads_twice_a_minute`; the ceiling |
| Setup, Activity do not listen to the stream | `test_a_capture_reaches_setup_within_about_a_second`; `test_a_post_reaches_activity_within_about_a_second` |
| Today's waiting count read once | `test_today_says_how_many_captures_wait_as_the_extension_reports_it` |
| The hello never catches a window up; catches it up when nothing changed; a return reads twice | `test_a_capture_while_the_window_was_hidden_is_read_on_return`; `test_a_window_back_with_nothing_changed_reads_nothing`; `test_a_window_back_after_a_while_reads_once_not_twice` |

Two guards were vacuous at first and were rebuilt. The burst test published thirty times in a tight
loop, and all thirty landed before the stream woke, so removing the coalescing changed nothing; it
now spreads ten publishes over 0.1 s. The watcher test, run alone, never opened a stream before
asserting that the watcher had stopped, so a watcher that never stopped passed; it now opens and
closes one first. Writing that test showed the watcher kept its file handle for ever once opened,
which is why it now closes after a minute with nobody listening.

## Not done, residuals, and what this track touched outside its files

Not run: the Tauri shell. There is no Tauri runtime here. The shell is a WebView2 window pointed at
the same URL and implements no product behaviour (`docs/DESKTOP_SHELL.md` section 1), so the
stream is the same same-origin `EventSource`; the service worker path a real window adds was
checked in Chromium (item 5). It should be checked once by hand in the shell before the release.

Residuals, each bounded by a backstop:

- On a window's first open, a change landing between a screen's first read and the stream's
  subscription, a window of tens of milliseconds, is not announced: the first hello cannot say
  what the screen's read saw. The screen shows it at its backstop (30 s; 120 s on Today) or with
  the next change.
- A write no path announces reaches the windows through the backstop, within about a second plus
  the quarter second a change waits for its burst, as `database`.
- Fixed in round 2: the heartbeat publishes from its route after the waiting count is recorded
  (`app.py:1551`), since only the route knows whether the beat carried one. Track 1's
  worker-owned heartbeat should keep the publish after both.
- An ingest that kept nothing (every item skipped) still publishes its kind, so a listening
  screen may read once for nothing; the once a second limit bounds it.
- The header's minute read now fires on Today about once a minute (see the measurement). It could
  instead be scheduled for the moment the bridge's 150 seconds run out; not done, it is outside
  this track's items.

No migration was needed. `security.py`, `api.ts`, `navigation.ts`, the extension and every
surface's content are untouched. `sw.js` is unchanged (item 5).

Lines in files owned by track 1, for the merge (at this record's last commit).
`studio/backend/onboarding.py`: the import at 50 and 55 (`from . import changes`,
`import changes`), and one line each at 328 `changes.publish("capture", extractor=..., drift=...)`
(end of `record_capture`), 495 `changes.publish("account" if ... else "readings")` (end of
`record_voyager_ingest`), 933 `changes.publish("posts")` (end of `ingest_own_posts`), 1002
`changes.publish("readings", post=urn)` (end of `ingest_post_analytics`), 1086
`changes.publish("outbound")` (end of `ingest_outbound`) and 1627 `changes.publish("imports")`
(before `update_import` returns). Each sits after the write's `finally: conn.close()`. The line
round 1 put at the end of `record_heartbeat` is gone. `studio/backend/app.py`: the import at 76
and 149, 1551 `changes.publish("heartbeat", waiting=...)` in the heartbeat route after
`note_waiting`, 1616 the identity observe route returning
`changes.published(onboarding.observe_profile(payload), "identity", ("updated", "candidate"))`,
and 2030-2038 the router include beside the storage router. Nothing in `ingest_contract.py` or
`security.py`.

Lines in other files outside this track's list. `studio/backend/routers/analytics.py` (track 5's
analytics routers): the import at 24 and 32 and line 570, `changes.publish_written(...)` after the
creator analytics ingest. `studio/backend/routers/crm.py`: the import at 27 and 45 and line 220,
`changes.publish("people", ...)` after the interactions ingest's write. `studio/backend/crm.py`
(track 3 owns its score orderings): the import at 20 and 26 and line 615,
`changes.derived_written()`, after `catch_up_scores` commits a batch. `studio/backend/post_summary.py`:
the import at 43 and 46 and line 490, `changes.derived_written()`, after `catch_up` commits a batch.
`studio/backend/scheduler.py` (track 4 owns its
missed history): the import at 31 and 36, and lines 573-574, `if actions:` and
`changes.publish("queue")`, at the end of `check_scheduled_queue`. `studio/backend/support.py`: the
import at 45 and 51, `changes.put_down()` at 1171 in `_put_the_database_down` and
`changes.let_go()` at 1181 in `_let_the_database_go`. `studio/ui/src/components/TodaySurface.tsx`
(track 3 owns its once-read side panels): lines 134-161, the brief's refresh call and comment and
the six panels' reads; this also closes the sections report's defect row on the panel failure
sentence, so track 3 should not need to. `studio/backend/docs_engine.py`: this record filed in the
maintainers section. Tests: `tests/test_endpoint_reachability.py` (173 paths, 119 reached, 54
unreachable, with the ledger's note), `tests/test_qc2_r5_refresh.py` and the docstring of
`tests/test_qc3_t4_activity_stream.py`.

For the coordinator: the session scratchpad is shared between tracks. A `falsify.py` of this
track's was overwritten there by track 1's, which resolves its paths from the working directory;
it refused to write in this worktree because its anchors did not match, and nothing was changed.
This track's scripts now live in a folder of their own. Tracks should not share file names there.

## Round 2: the independent review

Review of the branch at `b50797b` (no blocker; three should-fix findings and sixteen notes). On
the owner's direction this round builds S1 and S2 and defers S3 and the notes.

| Finding | Commits | What changed |
|---|---|---|
| S2. Today's side panels never heard "database", and the totals' own writer said nothing | 9693a25 | The creator analytics ingest says `account`, network reading of the account too; the extension's other silent writers say `people`, `identity`, `imports`; every listener, the header included, reads a "database" change as "anything may have changed" |
| S1. Today and the header read the whole aggregate on every change, up to once a second | d612112, a3963c1 | Changes carry identifiers; each screen asks whether a change can alter what it shows; Today's parts and the header read at most once per fifteen seconds with the last change always read; a heartbeat turns the mark connected without a read; the score and summary catch-ups, which a screen's own read sets off, no longer surface as "database" |

What each screen reads again for (every listener also reads for "database"):

| Change | Setup (1 s) | Activity (1 s) | Today's brief (15 s) | Today's panels (15 s) | Header (15 s) |
|---|---|---|---|---|---|
| heartbeat | when it shows the bridge gone | when gone, or "last heard" would read other than "just now" | when it shows the bridge gone | the waiting count, when the beat carried one | marks connected, no read |
| capture | unless a working reader's line reads the same minute | no | unless LAST CAPTURE still reads JUST NOW and nothing drifts or recovers | no | no |
| posts | yes | yes | yes | evidence, cadence | no |
| readings | yes | when the post is on the list, or unnamed | yes | evidence | no |
| account | no | no | no | the thirty day totals | no |
| people | no | yes | a comment; a reaction only from someone on the reply list | evidence | no |
| outbound, identity, imports | yes | yes | identity and imports; not outbound | no | no |
| queue | no | no | yes | cadence, slots | no |

Fifteen seconds for Today and the header: Today is the screen left open while the creator is on
LinkedIn, and its brief re-runs the whole onboarding state; fifteen seconds is the age at which a
returning window reads again, keeps each part to four reads a minute however busy the bridge is,
is still sooner than the 30 second poll it replaced, and a change after a quiet spell is read at
once.

The reviewer's load cases, one minute each in headless Chromium, every statement on every
connection counted (the harness is the review's `probe_client.py`, copied unchanged but for its
paths; the statement totals include the scripted writes, the same in every build, and from round
1 on the watcher's 60 looks). Reads are the screen's own requests; the header is measured on
Queue, which reads nothing about the bridge.

| One minute of | Screen | main (polls) | Round 1 | Round 2 |
|---|---|---|---|---|
| Nothing | Today | 2 briefs, 293 | 1 header read, 188 | 1 header read, 188 |
| | Setup | 20, 1,740 | 2, 272 | 2, 272 |
| | Activity | 24, 1,121 | 2, 192 | 2, 192 |
| | Queue (header) | 1, 257 | 1, 317 | 1, 317 |
| Ten LinkedIn tabs, a heartbeat every 6 s | Today | 2 briefs, 411 | 10 briefs and 10 waiting counts, 1,469 | 1 brief, 346 |
| | Setup | 20, 1,857 | 12, 1,239 | 2, 391 |
| | Activity | 24, 1,239 | 12, 760 | 5, 446 |
| | Queue (header) | 1, 376 | 10, 1,200 | 0, 351 |
| A feed scroll, an engager and a capture every 4 s | Today | 2 briefs, 1,515 | 15 briefs, 3,325 | 4 briefs and 4 evidence reads, 1,960 |
| | Setup | 20, 4,049 | 17, 3,879 | 4, 2,780 |
| | Activity | 24, 2,309 | 17, 2,060 | 17, 2,060 |
| | Queue (header) | 1, 1,447 | 2, 1,597 | 1, 1,512 |

Under a feed scroll Today still reads more than the old poll: the scroll's engagers are kept as
comments, each someone to reply to, and the evidence panel counts people per topic, so both read,
at most four times a minute, where the poll showed the brief up to 30 seconds late and the panels
never. Activity keeps its one second, as directed, and reads for each new person it lists. In the
first round 2 measurement every Today panel and the header still read four times a minute in the
scroll: reading the brief brought a person's score up to date, a write that said nothing; a3963c1
is that fix, and the table above is measured after it.

Guards: S2, 9 planted faults (each new writer silenced, the account kind reverted, a relayed path
left unaccounted for, panels and header deaf to "database", the totals back on post readings),
all caught; S1, 11 planted faults (Today's brief reading every change, its window at one second,
the waiting count reading every heartbeat, the header reading after heartbeats as in round 1,
Setup and Activity reading every capture, changes without identifiers, a change carrying a name,
the two catch-ups silent again, derived writes not counted), all caught. Two browser tests read a
request count after a plain sleep, which Playwright's synchronous API cannot see; both now wait
inside Playwright (`_page_wait_until`).

Deferred on the owner's direction, one line each:

- S3: Setup's and Activity's one second gap has no guard of its own; Today's and the header's
  windows are guarded by S1's tests.
- N1: a reopened stream's `?since=` still wins over a newer `Last-Event-ID`; one needless read
  per listening screen per such drop.
- N2: done in S1: the heartbeat publishes after the waiting count is recorded.
- N3: the stop hook wraps uvicorn's `Server.shutdown` without feature detection; a rename would
  fail `test_the_server_stops_promptly_with_a_stream_open` on CI.
- N4: `changes.let_go()` is not in a `finally` of its own after `resume_catch_up()`.
- N5: each look resolves the database path, a stat and a directory check a second.
- N6: on Windows a command-line restore with a studio window open fails safely; the help says to
  close the studio first.
- N7: done in S2 for the extension's writers; a write from the interface in another window still
  arrives as "database".
- N8: the Tauri shell is not run; for the release checklist.
- N9: the timing tests are single samples with fixed bounds.
- N10: a read slower than its gap can overlap the next.
- N11: after an outage each listening screen reads twice.
- N12: the note on the shared scratchpad below belongs in the hand-off.
- N13: done in S1: changes carry identifiers; `at` is not sent, since a change's arrival is its
  moment.
- N14: the queue test can race the studio's own 30 second job.
- N15: the six connections per origin are shared by every window of one browser profile; only a
  visible window holds a stream.
- N16: nothing on screen says live updates stopped when the stream is refused.

## Merged with release 2.8.0

`qc4/release-2.8.0` at `bc98deb` (tracks 5, 7, 3 and 6 and the integration fixes, released as
2.8.0) is merged into this branch for 2.9.0. Five conflicts, each keeping both sides: the router
includes in `app.py` (the change stream beside the record, phone and analytics export routes);
the maintainers' list in `docs_engine.py`; two returns in `onboarding.py`, where the publish lines
stay before the release's richer answers; the endpoint ledger; and `TodaySurface.tsx`, where track
3 had already put each side panel's read under `useRefresh` inside `useRead`. The panels' stream
rule now rides on that one hook as `useRead`'s third argument, rather than a second hook per panel
that would have read twice on every return. Track 3's guard
(`tests/test_qc4_t3_today_panels_read_again.py`) looked for the literal `useRefresh(again)` and
now accepts the extended call; it still fails with an interval added and with the hook removed.

The release's new writers each say what they wrote, after the commit:

| Writer | Line | Kind | Test |
|---|---|---|---|
| The account and content pages reader (`POST /api/analytics/page-figures`, relayed by the extension) | `studio/backend/routers/analytics.py:380` | account, when it recorded a reading or a point | `test_the_account_and_content_pages_say_account` |
| The analytics export import (track 6) | `studio/backend/routers/analytics_export_routes.py:113` | account and readings | none of its own: it needs a real export file, which track 6's tests build |
| A post the phone asked the desk to read (track 6) | `studio/backend/desk_requests.py:99` | desk | `test_a_post_the_phone_asked_about_says_desk` |
| Today settling the requests whose analytics were read (track 6) | `desk_requests.py:175` | none: a derived write, it wakes nobody | through `test_today` and the suite |
| The daily section's run (track 7) | `studio/backend/record_daily.py:338` | ideas | `test_the_daily_section_and_its_marks_say_ideas` |
| A keep, skip or hide on a card, and its removal (track 7) | `studio/backend/routers/record.py:122, 127` | ideas | the same test |

Setup and Activity show neither new kind; Today's brief shows desk requests and not the daily
section. The coverage test's table names the new relayed path.

A capture now also carries the minute it ran (`minute`), and Setup's same-minute rule compares
the studio's own minute. The rule it replaces asked the browser's clock and, within two seconds
of the turn of a minute, read on every capture to be safe, so a burst across the turn read once a
second: `test_setup_reads_once_for_a_reader_running_again_in_the_same_minute` failed on the merged
tree on that.

Endpoint census on the merged tree, by the ledger's own counting (`tests/test_endpoint_reachability.py`):
206 paths, 149 reached by the interface, 57 unreachable. The release's 205, 148 and 57 plus this
track's `/api/v1/events`, which the interface reaches.

Suite on the merged tree, as CI runs it: 3,674 passed, 18 skipped, 0 failed, in 715 s. The
eighteenth skip is `tests/test_qc2_r4_retention.py`'s own when the two hours before now cross
midnight, as they did during the run. Two failures on the way, both fixed before this: track 3's
guard on the literal hook call (above), and this track's daily section test marking the first
card, which is not always one that is shown; it now picks a shown card, as track 7's tests do.

## Suite, as CI runs it

`pytest tests studio/tests -q -rs` from the worktree with the project interpreter, at `e13acf0`:
3,159 passed, 17 skipped, 0 failed, in 617 s. The skips are the suite's own platform and
optional-dependency skips (Windows shell primitives, macOS only paths, a real desktop browser,
`yaml` not installed). After that run, two of this track's tests were made sturdier on a slow
machine and one was added (`test_a_write_from_another_process_is_noticed`). At `d04a9ad`, the code this record describes:
3,160 passed, 17 skipped, 0 failed, in 599 s, the same 17 skips. The commit after it changes
this paragraph only.

Round 2, at `a3963c1` with this record staged: 3,183 passed, 17 skipped, 0 failed, in 657 s, the
same 17 skips.
