# Cycle 4, track 2: the show path

Companion to [CYCLE4_2026-10_PRD.md](../CYCLE4_2026-10_PRD.md), section 6, track 2. Branch
`qc4/t2-show`, from `main` at `cf0ba9d` (2.7.0, schema 27). Specification: the capture report,
section Show (the studio side), the "Show is polling" paragraph, the freshness options and
programme item 12; the sections report, batch 7, and its defect row on Today's once-read side
panels. Line numbers are at the branch head this record was committed with.

| | |
|---|---|
| Items built | 8 of 8: the stream, the bus, the backstop, the event trigger, the three intervals, Today's side panels, the header's mark, one stream per window closed when hidden |
| New test modules | 3, 44 tests (`tests/test_qc4_t2_show_stream.py` 29, `tests/test_qc4_t2_show_browser.py` 10, `tests/test_qc4_t2_show_cost.py` 5) |
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

What changed. `studio/backend/changes.py:105-207`: `publish(kind)` is safe from any thread (the
ingest routes run on the thread pool, the interactions ingest on the single writer) and wakes each
listening stream on its own loop with `call_soon_threadsafe`. Kinds are words, never figures:
`capture`, `heartbeat`, `posts`, `readings`, `outbound`, `queue`, and `database` for a write
nothing named (`changes.py:65`). Nothing starts at import.

The ingest paths, one line each, after the write commits:

| Path | Line | Kind | Test |
|---|---|---|---|
| `record_heartbeat` | `studio/backend/onboarding.py:213` | heartbeat | `test_a_heartbeat_reaches_an_open_stream` |
| `record_capture` | `onboarding.py:329` | capture | `test_a_capture_reaches_an_open_stream_within_a_second` |
| `record_voyager_ingest` | `onboarding.py:496` | readings | `test_a_network_reading_says_readings` |
| `ingest_own_posts` | `onboarding.py:934` | posts | `test_the_creators_posts_say_posts` |
| `ingest_post_analytics` | `onboarding.py:1003` | readings | `test_a_posts_analytics_page_says_readings` |
| `ingest_outbound` | `onboarding.py:1087` | outbound | `test_the_creators_outbound_activity_says_outbound` |
| The queue's dispatch, only when it moved a post | `studio/backend/scheduler.py:573-574` | queue | `test_a_post_the_queue_marks_due_says_queue`, `test_a_queue_check_that_moved_nothing_says_nothing` |

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
cadence on posts and the queue, the totals on readings, the slots on the queue, the waiting count
on a heartbeat (only the extension knows it, and it says so on its heartbeat). None is polled.
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
- `record_heartbeat` publishes before the heartbeat route records the extension's waiting count
  (`studio/backend/app.py`, `post_bridge_heartbeat`); the quarter second a change waits makes the
  read land after the count, and a test holds it. Track 1's worker-owned heartbeat should keep the
  publish after both.
- An ingest that kept nothing (every item skipped) still publishes its kind, so a listening
  screen may read once for nothing; the once a second limit bounds it.
- The header's minute read now fires on Today about once a minute (see the measurement). It could
  instead be scheduled for the moment the bridge's 150 seconds run out; not done, it is outside
  this track's items.

No migration was needed. `security.py`, `api.ts`, `navigation.ts`, the extension and every
surface's content are untouched. `sw.js` is unchanged (item 5).

Lines in files owned by track 1, for the merge. `studio/backend/onboarding.py`: the import at
lines 50 and 55 (`from . import changes`, `import changes`), and one line each at 213
`changes.publish("heartbeat")` (end of `record_heartbeat`), 329 `changes.publish("capture")` (end
of `record_capture`), 496 `changes.publish("readings")` (end of `record_voyager_ingest`), 934
`changes.publish("posts")` (end of `ingest_own_posts`), 1003 `changes.publish("readings")` (end of
`ingest_post_analytics`), 1087 `changes.publish("outbound")` (end of `ingest_outbound`). Each sits
after the `finally: conn.close()` and before the `return`. `studio/backend/app.py`: lines
2027-2035, the router include beside the storage router; none in the bridge routes. Nothing in
`ingest_contract.py` or `security.py`.

Lines in other files outside this track's list. `studio/backend/scheduler.py` (track 4 owns its
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

## Suite, as CI runs it

`pytest tests studio/tests -q -rs` from the worktree with the project interpreter, at `e13acf0`:
3,159 passed, 17 skipped, 0 failed, in 617 s. The skips are the suite's own platform and
optional-dependency skips (Windows shell primitives, macOS only paths, a real desktop browser,
`yaml` not installed). After that run, two of this track's tests were made sturdier on a slow
machine and one was added (`test_a_write_from_another_process_is_noticed`); the run on the
branch head is in the commit that follows.
