# Cycle 4, track 3: honesty fixes and the second jobs

Branch `qc4/t3-honesty`, from `main` at cf0ba9d (2.7.0, schema 27). The
specification is the sections report: "Twenty-nine defects the redesign must
not inherit" (every row except the `capture_health` row, which is track 1's),
batches 0 and 1 of its programme, and decisions 6, 7 and 8 as the cycle's PRD
adopts them (section 5.2). The track adds no migration.

| | |
|---|---|
| Defect rows closed | 20 of the 28 this track holds, plus the TodayPerson type from the audit's list |
| Rows not closed | 7 with the reason, and 1 the report flags without judging (section "Not done, and why") |
| Moves | 5, and decision 8's removal |
| Guards added or widened, each falsified before it was kept | 6: no ranking by score, the ratio cut (which also reads the help), the contrast status names, the screen registry, the panel's minimums, and the gap format read from the tree |
| Commits | 28 |
| Suite, as CI runs it | 3,179 passed, 17 skipped (Windows, macOS, a workstation browser, pyyaml not installed, one deliberate), 0 failed, in 9 min 46 s, on the final tree |
| Interface audit | `tools/ui_audit.py`, both themes, desktop and phone: 48 screens over a seeded history and 48 on a fresh install, none with a blocking finding |

Every commit on the branch type-checks (`npm --prefix studio/ui run typecheck`
was run at each one), and the nine tests the first full run found failing pass
at every commit. The branch was rebuilt twice before it left this worktree,
with the same final tree each time: a TodaySurface.tsx syntax error was folded
back into the profile-views commit that introduced it, and five test
corrections the first full run asked for were folded into the commits that
made them necessary (a fixture key that read as a real one, two fixtures
without a settled date, and three tests pinned to code a move had retired).

## Batch 0: the honesty fixes

Each row gives the report's defect, the commit, what changed with path:line in
the branch's final tree, the test that fails without it, and how a guard was
falsified where one was added. The review column is the reviewer's.

| # | Rule broken: defect (report) | Commit | What changed | Fails without it | Guard falsified | Review |
|---|---|---|---|---|---|---|
| 1 | No ranking by score: the engagers route orders people `ORDER BY l.icp_score DESC`, and PostDetail draws them in that order (`routers/posts.py:681`) | 396d88c | Newest engagement first (`studio/backend/routers/posts.py:694`). The unused `crm.list_high_value_leads` ordered the same way and now orders by when the lead last changed (`studio/backend/crm.py:807`) | `tests/test_no_ranking_of_people_by_score.py`: a post's engagers come out newest first on a history where the facts order and the score order disagree | `test_no_backend_query_orders_people_by_their_score` reads every backend module for an ORDER BY over a score column, an alias of one, or a Python sort keyed on one; it extends `today.py:15-16` to the whole backend. Falsified by planting `ORDER BY l.icp_score DESC` back into the route, which it named at `routers/posts.py:686`. A second test plants each shipped shape (plain, the `sort_score` alias, a renamed alias, a Python sort) and asserts each is caught and a hook template's `velocity_score` is not | |
| 2 | No ranking by score: post attribution orders `ORDER BY sort_score DESC`, and Analytics draws server order (`crm.py:1117`) | 396d88c | The alias is gone and the rows order by `interacted_at DESC` (`studio/backend/crm.py:1128`). The two index tests that compare the scan with the index use the new order on both sides | the same file's attribution test | the guard above | |
| 3 | Nothing invented: Activity hides "Reposts" when the captured count is 0 (`ActivitySurface.tsx:171`) | 08893e5 | Every figure through `measured()`: a read 0 prints 0, a missing one "not measured" (`studio/ui/src/components/ActivitySurface.tsx:174-179`) | `tests/test_qc4_t3_activity_lines.py::test_reposts_are_printed_whenever_they_were_read` | | |
| 4 | Nothing invented: "WORKING" shown for a reader that read nothing (`onboarding.py:359`) | track 1 | Excluded by the brief: it lives in `capture_health` | | | |
| 5 | Nothing invented: the Voyager ingest logs drift as NULL (`onboarding.py:475-489`) | not done | See "Not done, and why" | | | |
| 6 | Nothing invented: the EvidencePanel claims its contrasts are "injected directly into your BYO-AI Copilot prompt context" (`EvidencePanel.tsx:142-145`) | 8ec3ecc | "Where this goes: nowhere by itself", with what Re-Hook and Command do send (`studio/ui/src/components/EvidencePanel.tsx:151`) | `tests/test_qc4_t3_evidence_claim.py` holds the sentence to the code: no interface file calls `/api/copilot`, and the repurposer reads the voice pack and not the brief. A change to either fails it and names the sentence to rewrite | | |
| 7 | Nothing invented: Today's "It is read again when this window comes back" is true only of `/api/v1/today`; the six side panels are read once (`TodaySurface.tsx:618, 94, 138-143`) | d2e2160 | `useRead` puts each panel's read under `useRefresh` with no interval: on the studio coming back and on the window coming back (`studio/ui/src/components/TodaySurface.tsx:100`). Track 2 closed the same row on its branch (its `TodaySurface.tsx:134-161`); the coordinator reconciles the two at merge | `tests/test_qc4_t3_today_panels_read_again.py` | | |
| 8 | Nothing invented: Activity's "Bridge: {carrier}" can never render (`routers/browser.py:370`) | 08893e5 | The sentence, the always-null key and its type are removed (`ActivitySurface.tsx:424`, `studio/backend/routers/browser.py:369`, `ActivityStreamData` in `api.ts`) | `tests/test_qc4_t3_activity_lines.py` (route and screen) | | |
| 9 | Nothing invented: Setup prints "No Chromium browser was found" when `/api/v1/browser/status` failed (`OnboardingSurface.tsx:77, 818-823`) | b97f7fa, b88edca | A failed read marks the answer unreachable, and the box says the studio could not be asked (`studio/ui/src/components/OnboardingSurface.tsx:80, 827`; `BrowserBridge.unreachable` in `api.ts`); the Setup article says what that means | `tests/test_qc4_t3_setup_browsers_unasked.py` | | |
| 10 | Nothing invented: Analytics offers profile views, which no reader fills (`AnalyticsSurface.tsx:34`); decision 8 | fcf0a77, 439f1b6, 24a4a81 | Gone from Analytics' measures and figures and from Today's thirty days (`studio/ui/src/components/AnalyticsSurface.tsx:28`); the route keeps the column, so a reader can bring it back. Two help articles stop listing it | `tests/test_qc4_t3_profile_views_removed.py` (both screens, comments stripped, and the help) | | |
| 11 | Nothing invented: the extension side panel's Health tab (`sidepanel.js:573-600`) | not done | See "Not done, and why" | | | |
| 12 | Captured days only: rounded figures are flagged on Analytics and unflagged on Today's "Last 30 days" (`TodaySurface.tsx:820-831`) | 1740421 | `approximate` and `within_rounding` on the shared `AnalyticsKpis`; Today marks a rounded figure and its change with ~ and "about" for a screen reader, and says what the mark means (`studio/ui/src/components/TodaySurface.tsx:845`, `About` at :580) | `tests/test_qc4_t3_today_approximate.py` | | |
| 13 | Captured days only: topic attribution totals use `own_posts.reactions` (`evidence_briefing.py:225, 277`) (S) | cce5a10 | The totals read `results.figures` (`studio/backend/evidence_briefing.py:308`) | `tests/test_qc4_t3_topic_totals_are_one_reading.py`: with a newer reading of one post the topic summed 12, the snapshot, instead of 57 | | |
| 14 | Captured days only: the voice pack's openers are ranked by raw reactions (`voice_pack.py:113-114`) (S) | cc78841 | The openers follow `results.ranking`: settled posts only, against the creator's own median (`studio/backend/voice_pack.py:112`, the ranking at :122). The report names this as the precondition for any Library of the creator's openers | `tests/test_voice_pack.py::test_openers_come_from_the_one_ranking_so_a_young_post_is_not_an_exemplar` | | |
| 15 | Captured days only: a Patterns verdict of `not_measured` lands in the main list worded "not enough posts to say" (`PatternsSurface.tsx:97, 372-373`) | be622db | Each verdict has its own words, and a line with no ratio is listed under NO RATIO CAN BE MEASURED (`studio/ui/src/components/PatternsSurface.tsx:368`, and the notes in `Comparisons`) | `tests/test_qc4_t3_patterns_not_measured_wording.py` | | |
| 16 | Captured days only: post readings carry no precision column | not done | Track 5's item 18 | | | |
| 17 | One definition: the interface colours ratios at 1.2 and 0.8 while the engine's cut is 1.25 and 0.8 (`results.py:97-98`) | 8a1b3ca, e2c2364 | One module, `studio/ui/src/lib/results.ts:14` (`NOTABLE_HIGH`, `NOTABLE_LOW`, `ratioTone` at :29), read by Patterns, Posts, PostDetail and Today; the Evidence panel's arrow follows the engine's verdict. The Posts and Today articles corrected from 1.2 to 1.25 | `tests/test_ratio_cut_is_one_number.py` | Reads `lib/results.ts` and `results.py`, because nothing else joins them, and fails on a component that compares a ratio with a literal and on a help article that states another cut. Falsified by planting the shipped `ratio >= 1.2` line back into Patterns (named at `PatternsSurface.tsx:399`) and by putting 1.2 back into the Today article (named) | |
| 18 | One definition: EvidencePanel hard-codes "Fewer than 3" and "n >= 8" (`EvidencePanel.tsx:47, 70, 76`) | 4345a9e | The brief carries `min_settled_posts` and `min_per_side` from the engine in both of its shapes and judges its cold start by `MIN_FOR_MEDIAN` (`studio/backend/evidence_briefing.py:486`); the panel prints what it is handed (`EvidencePanel.tsx:50, 73`) | `tests/test_qc4_t3_evidence_minimums.py` | The source check failed on the shipped panel, naming its four literals | |
| 19 | One definition: the interface type says `insufficient_sample` where the engine sends `not_enough_data` (`api.ts:2446`) | bf5089f | The union names exactly the engine's statuses (`studio/ui/src/lib/api.ts:2391`), and the Patterns cast is gone | `tests/test_qc4_t3_contrast_status_names.py` reads the engine's evaluators by AST and the interface's union | Failed on the shipped union; also fails on any `.status as string` in a component | |
| 20 | One definition: two identities, Brand Studio's profile and Setup's confirmed identity (S) | not done | Batch 5, track 4 | | | |
| 21 | One definition: two "usual" figures, with no screen saying they differ (`today.py:55-58`; `PostsSurface.tsx:138`) | 4219640 | Today names its usual and says Posts' is a different figure (`studio/ui/src/components/TodaySurface.tsx:1053`); Posts already names its own (`PostsSurface.tsx:139`) | `tests/test_qc4_t3_two_usuals.py` | | |
| 22 | One definition: `today.py` says "the Queue lists every one" of the due posts, but both callers use `DUE_LIMIT` of 10 (`today.py:62`; `routers/queue.py:170`) | 401ff74 | Lifted: the Queue asks for every due post (`studio/backend/routers/queue.py:173`), `due_posts` takes `limit=None` (`studio/backend/today.py:247`), and Today keeps its ten, which the comment now says (`today.py:62`) | `tests/test_qc4_t3_due_cap.py`: the Queue held 10 of 12 due posts before the change | | |
| 23 | One definition: "is a LinkedIn session stored" is answered from two settings keys (S) | not done | Batch 5, track 4 | | | |
| 24 | One definition: the demo seeder's unclamped rate; crm's literal 60.0 and 80.0 | no change | The report flags these and does not judge them: seed data and blend weights, not a figure any screen draws | | | |
| 25 | Structural: Activity files a post under `last_seen_at` (`routers/browser.py:217`; `ActivitySurface.tsx:176`) | 08893e5 | Filed under `published_at`, with "read Nd ago" on the line (`studio/ui/src/components/ActivitySurface.tsx:185`) | `tests/test_qc4_t3_activity_lines.py` | | |
| 26 | Structural: seven sections have no `screenKey`, and the registry lists the cut Swipe File and Command (`navigation.ts:35-43`; `devtools.py:165-173`) | d16b19c | Every section declares a key and `screenKey` is required (`studio/ui/src/lib/navigation.ts:46`); the registry has one entry per section and no other (`studio/backend/devtools.py:171-183`) | `tests/test_qc4_t3_screen_registry.py` | Holds the two lists in both directions; it failed on the shipped rail (seven sections without a key) and registry (`swipe`, `ai_command`) | |
| 27 | Structural: an MCP server's `env` and `cwd` are returned to the browser (`mcp_client/servers.py:120-128`) | 522a6f9 | The listing and the add route answer without the environment, with a count of its variables (`studio/backend/mcp_client/servers.py:144`, `studio/backend/app.py:2126`); the launcher still reads it | `tests/test_qc4_t3_mcp_env_stays_home.py` plants a key-shaped value and reads both routes for it | | |
| 28 | Structural: the lead stage migration promises "from which post" and writes no post column | not done | See "Not done, and why" | | | |
| 29 | Structural: every Today and Setup poll runs the whole `onboarding_state` | track 2 | The event stream and its lighter backstops | | | |
| + | (the audit's list, in batch 0) The `TodayPerson` type omits `engaged_at`, patched locally (`api.ts:2113-2122`; `TodaySurface.tsx:928`) | aff86b0 | Declared on the shared type (`studio/ui/src/lib/api.ts:2051`); the local patch is gone | `tests/test_qc4_t3_today_person_type.py` compares a live brief's keys with the declared fields | | |

## Batch 1: the second jobs removed

| # | Move (report; decision) | Commit | What changed | Fails without it | Guard falsified | Review |
|---|---|---|---|---|---|---|
| M1 | The Queue's eight-row drafts list becomes a count with one action (decision 6) | c275f69 | "N drafts are waiting", the newest one's first line and Queue the newest draft, through the same next-slot route as before (`studio/ui/src/components/QueueSurface.tsx:433`). The posts route says how many posts a status holds beside the rows asked for (`studio/backend/routers/posts.py:226`), so the Queue reads one draft and a count (`fetchDraftsWaiting`, `studio/ui/src/lib/api.ts:3211`); a failed read says it failed instead of reading as no drafts | `tests/test_qc4_t3_queue_drafts_count.py`; the two Queue browser tests in `tests/test_qc3_t5_queue_week_window.py` describe the count and its one action | | |
| M2 | Patterns' cadence block moves to the Queue, where the week lives | fec0571, 91c0749 | The Queue's rhythm block gains the longest gap with its dates, the next 14 days against their slots, posts by month with its scale in words, posts by weekday and the sentence on why no best day is named (`QueueSurface.tsx:694`, `MonthStrip` at :902). Patterns stops fetching the cadence payload and keys its empty state on `posts_held` (`studio/backend/insights.py:631`). After the measurement below, the next slot offered moved above the rhythm (`QueueSurface.tsx:632`) | `tests/test_qc4_t3_cadence_moved_to_queue.py`; `tests/test_one_gap_on_screen.py` compares Today with the Queue | `tests/test_one_gap_format.py` reads which screens print a gap from the tree instead of a list that named Patterns, so a new screen that prints one is held to the formatter. Falsified by planting a gap field into Outbound without the formatter, which it named | |
| M3 | Patterns' contrasts drawn from the payload it already fetches | 6421e04 | The comparison lines are the contrast engine's own records, the ones the Evidence panel is built from: more and fewer, "no difference" as its own list, the period guard, a line with no ratio, and the engine's abstention with its counts (`studio/ui/src/components/PatternsSurface.tsx:142`, `Comparisons`). The EARLY tag, built from the records' status and key alone, could not fire and is gone; a failed read says so | `tests/test_qc4_t3_patterns_from_the_engine.py` plants an engine payload the patterns payload could not produce and reads it back off the screen | Failed against the previous screen, three of three | |
| M4 | The topic table becomes a form through the engine; the qualified framing is retired (decision 7) | b233aef | One evaluator for any form in the engine (`studio/backend/contrast_engine.py:61`, `evaluate_feature`), which the seven features now go through unchanged; the creator's topics compared by it (`studio/backend/evidence_briefing.py:251`, `topic_forms`), with both lists from one reading of the figures (`patterns_comparisons` at :285, answered by `/api/v1/insights/contrasts`, `studio/backend/routers/insights.py:59`). Patterns draws the topics in their own column (`PatternsSurface.tsx:110`) and no longer fetches the attribution route | `tests/test_qc4_t3_topic_forms.py`, including a spy that proves each topic went through the engine's evaluator | Falsified with an answer that carried no topics: two of four failed | |
| M5 | Analytics' fourteen-row post table out, the aside linking into Posts | 99fc7e3 | The table, its pager and its per-row attribution are gone. The aside reads `GET /api/analytics/best` (`studio/backend/routers/analytics.py:521`), which answers `results.best` without rows, and a new panel, Every post, links to `#/posts` (`studio/ui/src/components/AnalyticsSurface.tsx:489`). The drawer under the table was the one place that said how many of a post's people are kept only as counts, so that note moved with the table: the engagers route carries the post's folded people (`studio/backend/routers/posts.py:704`) and Posts' detail says how many (`studio/ui/src/components/PostDetail.tsx:163`) | `tests/test_qc4_t3_analytics_table_moved.py`, including the folded count read from a seeded fold; the sections browser test follows Open Posts to the one table; `tests/test_qc2_integration_folds.py` reads the post detail | The source check failed against the previous screen | |
| M6 | Analytics' profile views removed until a reader exists (decision 8) | fcf0a77 | Row 10 above | | | |

## One-view measurements

Measured the way cycle 3 measured its sections (`CYCLE3_2026-10_PRD.md:56-57`
and 106-110): 1440x900, dark, service workers blocked, the work area only.
Scroll pages is the work area's height in viewports. Ink is the share of the
first viewport of the work area covered by text, controls and drawn marks,
sampled on a 6 px grid. The answers are the headings of each section's
answers, and whether each sits in the first viewport. Before is `main` at
cf0ba9d, exported and built in a scratch folder; after is this branch. Both
ran over the same synthetic history in a scratch home: 720 posts over three
years, 1,500 people with about 5,000 engagements, 120 days of analytics, 12
drafts, 4 queued and 2 due posts, 300 outbound engagements. Every row is
invented; it stands in for the three-year install, which this track does not
open.

| Section | What this track changed there | Scroll pages | Ink | Characters in view | Answers in the first view, before | After |
|---|---|---|---|---|---|---|
| Setup | the load-by-hand box's failure sentence (no layout change) | 2.12 to 2.12 | 15.5% to 15.5% | 1,043 to 1,043 | 2 of 2 | 2 of 2 |
| Today | the approximate mark, the usual sentence, profile views out, side panels read again | 1.00 to 1.00 | 37.8% to 38.9% | 2,445 to 2,654 | 7 of 7 | 7 of 7 |
| Activity | post lines: reposts, the published day, the read time; the dead carrier sentence | 2.17 to 2.20 | 24.6% to 24.2% | 2,307 to 2,388 | 3 of 3 | 3 of 3 |
| Composer | the Evidence tab's minimums and its claim, one click into the inspector by design | 1.03 to 1.03 | 46.0% to 46.0% | 74 to 74 | the editor fills the view | the editor fills the view |
| Queue | drafts as a count with one action; the rhythm moved in; the due cap lifted; the next slot above the rhythm | 1.11 to 1.15 | 24.7% to 24.8% | 2,066 to 1,977 | 6 of 6 | 6 of 7; the weekly slot editor below, as the audit placed it |
| Posts | the ratio colour cut; the detail's folded-count note | 1.84 to 1.84 | 31.3% to 31.3% | 2,317 to 2,317 | 1 of 1 | 1 of 1 |
| Patterns | cadence out; lines from the engine's records; topics as forms; the topic table out | 1.34 to 1.00 | 35.3% to 33.9% | 2,614 to 2,416 | 5 of 5; the topic table's heading at the fold, its rows below | 4 of 4: forms, no difference, topics and the settle curve |
| Analytics | the post table out, the aside linking into Posts; profile views out | 1.31 to 1.05 | 35.3% to 29.8% | 1,888 to 1,611 | 6 of 6; the post table at 573 px, running below the fold | 6 of 6, Every post at 815 px |

Patterns now answers in one view, and Analytics nearly does: its aside runs
45 px past the fold. Analytics' ink fell because the table's rows were ink,
and Patterns' because the cadence block moved out, while both screens hold
their answers in the first view. The Queue's next slot offered sits at about
460 px. Each touched section stays under the PRD's 2 scroll pages except
Setup and Activity, which were over it before this track: Setup is unchanged
(its health block is track 4's move), and Activity moved from 2.17 to 2.20
because its post lines now carry reposts and the read time; its log is a
list. Setup
(15.5%) and the Queue and Activity (about 25%) are at or below the 25% ink
bar, as they were.

## Not done, and why

| Report row | Why not here | Where it belongs |
|---|---|---|
| The Voyager ingest logs drift as NULL (`onboarding.py:475-489`) | The whole fix is in `onboarding.py`, which the brief rules out for this track: `capture_health` reads only `captures.drift`, the Voyager ingest writes it NULL, and the extension's drift reports land in `schema_drift_events` (`onboarding.py:364`), which capture health never reads. No interface wording names a Voyager reader, so there is no screen half to do alone | Track 1, beside the `capture_health` row: have `capture_health` read the newest `schema_drift_events` for the `voyager_*` extractors, or have the Voyager ingest write the drift it saw |
| The extension side panel's Health tab (`sidepanel.js:573-600`) | The extension is ruled out by the brief, and the report gives it to the capture track's rank 5 | Track 1, phase 3 |
| Post readings carry no precision column | A migration, and the PRD's item 18 for track 5 | Track 5 |
| Two identities, Brand Studio's profile and Setup's confirmed identity (S) | Batch 5, "reconcile the two identities", in the Brand and Settings split | Track 4 |
| "Is a LinkedIn session stored" answered from two settings keys (S) | Batch 5, "move Setup's backups and session" | Track 4 |
| The lead stage migration promises "from which post" and writes no post column | The report's fix is a column added "forward from the day it ships", which needs a migration, and this track carries none. It is the column a funnel by post would read | Track 4 (Audience's funnel), in its migration, or a later batch |
| Every Today and Setup poll runs the whole `onboarding_state` | The event stream and its lighter backstops | Track 2 |
| The demo seeder's unclamped rate; crm's literal 60.0 and 80.0 | The report flags them and does not judge them | No change |

## Files outside the track's list, and why

The brief makes every defect row this track's except `capture_health`, so a row
that lives in another file was closed there, at the smallest scope that closes
it.

| File | Region | Why |
|---|---|---|
| `studio/backend/today.py` | the `DUE_LIMIT` comment and `due_posts`' `limit` | The due cap row: the Queue asks for `limit=None` |
| `studio/backend/mcp_client/servers.py`, `mcp_client/__init__.py`, `app.py` | `for_screen`, `list_servers_for_screen`; the MCP list and add routes | The MCP environment row |
| `studio/backend/voice_pack.py` | `_openers` | The openers row (S) |
| `studio/backend/evidence_briefing.py` | the brief's minimums; the topic totals; `topic_forms` and `patterns_comparisons` | Rows 13 and 18; move M4 |
| `studio/backend/contrast_engine.py` | `evaluate_feature`, which `evaluate_contrast_for_posts` now calls | Move M4: a topic goes through the engine's rules rather than a copy of them |
| `studio/backend/routers/insights.py` | the contrasts route; the attribution route's docstring | Move M4 |
| `studio/backend/insights.py` | `patterns_overview` returns `posts_held` | Move M2: Patterns' empty state without the cadence payload |
| `studio/backend/routers/analytics.py` | `GET /api/analytics/best` | Move M5 |
| `studio/backend/routers/browser.py` | the activity stream's summary | The dead carrier row |
| `studio/backend/devtools.py` | `SCREEN_REGISTRY` | The screenKey and ghosts row |
| `studio/ui/src/components/OnboardingSurface.tsx` | the browser read and the load-by-hand box only | The Setup row |
| `studio/ui/src/components/PostsSurface.tsx` | one line, the ratio colour | The colour cut row |
| `studio/ui/src/components/PostDetail.tsx` | one line for the ratio colour; the Who engaged block for the folded-count note | The colour cut row; move M5, so the note the Analytics drawer held is not lost. Track 4 owns this file otherwise |
| `studio/ui/src/components/QueueSurface.tsx` | besides the drafts and cadence regions, one sentence in Queued posts' empty state | It pointed at "the drafts waiting below"; it now points at the newest draft |
| `studio/ui/src/lib/api.ts` | the types and readers of the rows and moves above | |
| `studio/ui/src/lib/results.ts` | new | The one colour cut in the interface |
| `studio/backend/docs_engine.py` | `HELP_SECTIONS`, maintainers | Files this record, as the coordinator asked |
| `docs/help/` | `read-your-analytics.md`, `why-is-my-analytics-chart-empty.md`, `see-what-worked-and-where-your-attention-goes.md`, `how-the-queue-works.md`, `what-to-do-today.md`, `start-a-new-post-or-find-an-earlier-one.md`, `set-up-the-studio-from-your-linkedin.md` | Each describes a screen this track changed |

Existing tests changed because the behaviour they pinned was the defect, or a
job that moved, each with its reason in its commit: the reference queries in
`test_qc3_t4_engagers.py` and `test_qc2_r3_indexes.py` (score order to facts
order, on both sides of the comparison); `test_devtools.py` (the registry's
size read from the registry); `test_voice_pack.py` and `test_qc_f2_disclosure.py`
(fixture posts given a settled date, so the one ranking can rank them);
`test_qc3_t5_queue_week_window.py` (two tests, the drafts count);
`test_qc2_r5_patterns.py` (the month strip on the Queue, the topics section,
EARLY gone from the help); `test_one_gap_on_screen.py` (Today against the
Queue); `test_one_gap_format.py` (screens read from the tree);
`test_qc_f5b_screens.py` (AUDIENCE-09 read on Posts, AUDIENCE-22 one read of
the best posts, AUDIENCE-12 and 27 and the keyboard test on the topics
section); `test_qc3_t6_sections_browser.py` (Open Posts to the one table);
`test_qc3_t6_posts_table.py` (the verdict check on the engine's records, the
controls without the retired sortable table, and no order line or rate note
for a table Analytics no longer draws); `test_qc2_integration_folds.py` (the
folded-count note on the post detail); `test_help_matches_the_paged_tables.py`
(the Analytics article says where the posts went); and
`test_endpoint_reachability.py` (172 to 173 routes, reached 118 to 117,
unreachable 54 to 56, each route named in its comment).

## Follow-ups for other tracks and the coordinator

- Found while checking move M5 in a browser, and present on `main` as well: a
  post first captured after migration 26 has no `posts` row. Migration 26 gave
  every publication that existed then a row, but the own-posts ingest only
  binds a capture to a studio record that already matches it
  (`onboarding._bind_to_studio`) and makes none. `post_identity.resolve` needs
  that row, so `GET /api/v1/posts/{id}/engagers` answers 404 for such a post,
  and Posts' detail turns the failure into "NOBODY CAPTURED FROM THIS POST YET."
  however many people engaged (reproduced on cf0ba9d: one imported post, one
  commenter, 404). The folded-count note added here reaches only the posts the
  route resolves. The fix belongs in the ingest (track 1's `onboarding.py`) or
  in `post_identity.resolve`, and the detail's swallowed failure is in track 4's
  file; neither was in this track's brief.

- Patterns' rail blurb still ends "and how steadily you post", and
  `docs/help/open-the-studio-for-the-first-time.md:69` repeats it. The blurb is
  track 4's region of `navigation.ts`, and the rhythm is on the Queue now.
- `docs/help/how-the-queue-works.md` says "The Queue page does not refresh
  itself"; it has refreshed every 30 seconds since cycle 3. Track 2 changes that
  interval and should rewrite the sentence with it.
- Posts' detail turns a failed engagers read into an empty list, so it reads
  "NOBODY CAPTURED FROM THIS POST YET." over an outage (`PostDetail.tsx`, the
  engagers `.catch`). It is the shape of row 9 and of the Queue's drafts read,
  both fixed here, and it sits in track 4's file.
- Three routes have no caller in the interface now and stay for the API and
  their tests: `/api/v1/insights/attribution` (AUDIENCE-12 holds its people
  counts), `/api/v1/analytics/posts/{id}/leads`, and `/api/analytics/posts`
  (already counted unreached: its client wrote the path in a template literal
  the reachability test does not read). `patterns_overview` still computes
  comparison lines of its own that no screen draws; the agreement tests hold
  them equal to the engine's records. Retiring them is a separate change.
