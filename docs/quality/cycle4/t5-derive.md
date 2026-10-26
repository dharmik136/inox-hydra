# Cycle 4, track 5: derive

Branch `qc4/t5-derive`, from `main` at cf0ba9d (2.7.0, schema 27). Specification: the capture
report, section Derive and programme items 18 to 22; sections decision 14 as amended by the owner on
2026-10-26 (PRD commit a0ef01b, line 81). Every path:line below is on the branch head unless it says
otherwise; "main" lines are cf0ba9d's.

| | |
|---|---|
| Items | 5 of 5 built. Not built: item 22's card-marker wiring and the Activity tab's precision flag (both in Track 1's regions), and the watch-time and newsletter figures (closing section) |
| Migration | one, `_migrate_reading_precision_and_series` (`migrations.py:1427`, ledger `:1548`), numbered 28 here, found by tests by its name |
| First round | 6457e52 (18), d8d9399 (19), 05cee93 (20), 4a9683b (21), 9481da9 (22), b9da5d4 (help), fcc5c87 (20, found by the suite), c4d01ae (19, found in review), 9368722 (a test's cleanup, found by the suite), 3ed0665 (this record) |
| The owner's decision | d439ccb (the rule and the sightings), 573b8df (the endpoint ledger), 6be09de (this record) |
| Second round | the review of 3ed0665, finding by finding, in the section of that name |
| New tests | tests/test_qc4_t5_derive.py (47), tests/test_qc4_t5_post_analytics_reader.py (15) |
| Full suite | 3177 passed, 18 skipped, 0 failed, as CI runs it (`pytest tests studio/tests -q -rs`, 9 min 50 s), on 76cffe7 with this record in place. 17 skips are the environment's (Windows, macOS, a workstation browser, pyyaml); the 18th, `test_qc2_r1_launcher.py:156`, skips when the kernel leaves no TIME_WAIT on its port, which varies from run to run |

## The owner's decision of 2026-10-26: an absent unverified label is not drift

The first version of item 19 reported each label added this cycle as drift whenever a post analytics page
lacked it, as decision 14 then asked. This record showed the cost, and the reviewer reached the same
judgement independently: `_open_next` names a drifting reader before anything else, so a Basic member who
never sees profile viewers, or any post too small for demographics, would have had Today saying "Your
posts' analytics pages has stopped reading LinkedIn's pages" for good, while the seven figures were read
every time. The owner amended decision 14 on 2026-10-26, through the coordinator (PRD a0ef01b): only the
labels the reader captured before this cycle can report drift; a new label LinkedIn does not show is
recorded as not read, never as drift and never as 0, and stays visible as a count in Health. Built in
d439ccb:

- `POST_LABELS_ON_EVERY_POST` (`own_pages.js:1211`) holds the seven labels read since cycle 2 (members
  reached, impressions, reactions, comments, reposts, saves, sends) and nothing else; a page lacking one of
  them beside the others reports it by name, and a page with none reports `metric_labels`, as on main.
- A new label that is absent sends nothing, so nothing is stored, never a 0, and the reader stays working.
  A new field present but failing its own check (a split that does not add up to about 100, a demographics
  block nothing in which can be bound) is dropped, and is not drift either.
- The count in Health: `onboarding.post_analytics_sightings` (`onboarding.py:1139-1201`, one definition)
  derives from the readings and the dated demographics, with no new column in the capture log, per new
  field, when a post analytics page last carried it and how many post analytics readings have been taken
  since. Route `GET /api/analytics/post-field-sightings` (`routers/analytics.py:355`), for Track 4's Health
  section. Fields: `post_analytics_readings`; `fields`, one per new field, each with `field`, `label`,
  `last_read_at` (ISO, null when never read), `readings_since` (all of them when never read) and
  `sentence`, such as "followers gained from this post: not read on any of the last 12 post analytics
  pages, last read 2026-10-20"; and `meaning`, "LinkedIn may not show this figure to every member or on
  every post. If it never appears, the label may have changed." The help says the same.
- Tests: `test_a_page_missing_every_new_label_is_read_with_no_drift` (the capture recorded, the reader
  working), `test_a_page_missing_a_verified_label_still_reports_drift` (drift `["saves"]`),
  `test_sightings_say_how_long_each_new_field_has_gone_unread` (five pages: a field seen once and then not
  again, one never seen, one seen again on the latest), `test_only_the_labels_read_before_this_cycle_can_drift`
  and `test_the_drift_guard_is_not_vacuous`. Falsified: a planted `"followers_gained"` in the list fails the
  static guard and the page test; a sightings count of every reading rather than those since gives 4
  against 3. Both files restored byte-identical.

## The migration

| Adds | Columns |
|---|---|
| on `post_metric_observations` | `precision`, `followers_gained`, `profile_viewers`, `link_visits`, `article_views`, `video_views`, `in_network_pct`, `out_of_network_pct` |
| on `own_posts` | `format TEXT NOT NULL DEFAULT 'unknown'` |
| table `audience_demographic_readings` | `observed_at`, `observed_on`, `activity_urn` (`''` for the account), `source`, `dimension`, `label`, `percentage`; one row per day per dimension and label |
| table `analytics_windows` | `date`, `period_label`, `observed_at`, `impressions`, `reactions`, `comments`, `shares`, `followers`, `precision`, `source`; key `(date, period_label)` |
| and | marks every stored per-post summary row's readings stale, so the catch-up rewrites them with per-figure entries (second round, S2) |

Why a new table for the weekly card, not the specification's `period_label '7d'` row in `analytics_daily`:
that table's key is the date alone, so a 7 day row would replace, or be replaced by, the same day's daily
row; `get_kpis` counts any non-daily row in its range as an excluded unknown-window day, so a weekly row
would have printed a false note under Analytics; and the overview plots every row of the table as a day.
`analytics_windows` keys a reading by the day it was read and the window it covers, and nothing that sums
days reads it.

## Items

| Item | What changed (path:line) | Fails without it | Guard and how it was falsified | Unverified labels and drift |
|---|---|---|---|---|
| 18 Precision column (6457e52, 05a7540) | `own_pages.js:231-267` `parseFigure` keeps whether a figure carried K or M; the post analytics reader sends one `precision` per reading (`own_pages.js:1364-1370, 1373-1388`). `onboarding.py:968-1002` `PRECISIONS`, `_precision`; `_record_observation` keeps a reading rounded if either read in the hour was (`onboarding.py:1011-1035`). `results.py:444` `rounding_half_width` (the step rule, once; the analytics router aliases it at `routers/analytics.py:59`); `results.py:466` `reading_half_width`, a missing flag is unknown, never exact (S3); `results.py:481` `approximate_fields`; `results.py:495` `growth`. The Posts detail names the figures that may be rounded in one line (`PostDetail.tsx:116-117`). | `test_a_rounded_reading_is_stored_as_rounded_and_an_unsaid_one_as_unknown`, `test_growth_between_two_rounded_readings_is_approximate_never_measured`, `test_the_posts_detail_says_about_where_a_reading_is_rounded`, `test_a_figure_written_as_12k_is_sent_as_rounded`, and for S3 `test_a_reading_with_no_flag_may_have_been_rounded`, `test_the_upgraded_database_case_never_reports_a_change_rounding_could_hide`. | `test_the_rounding_width_has_one_definition`. Falsified: a second rule planted in the router fails it; the flag discarded at ingest fails the storage test; a missing flag read as exact again fails both S3 tests. | None. Whether LinkedIn abbreviates above 10K on this page is a live check; the flag is right either way. |
| 19 Seven missing fields (d8d9399, c4d01ae, d439ccb, 84d66f1) | `own_pages.js:1169-1178` comment; `:1188-1194` the five count labels; `:1196-1212` `POST_SHARE_LABELS` and `POST_LABELS_ON_EVERY_POST`; `:1214-1319` the percentage parser and the demographics reader, which binds an entry by its own element (S1); `:1341-1355` the split read beside its label; `:1373-1388` a split that does not add up is dropped; `:1392-1398` `postAnalyticsDrift`, verified labels only; `:1404-1405` the capture reports it. `onboarding.py:968-1002` the new count and share fields; `:1043-1082` `_record_demographics`, dated; `:1106, 1113` the ingest calls it; `:1117-1203` `post_readings`, `post_demographics`, the sightings. The post detail route returns every reading, `per_post` (each figure from the newest analytics-page reading that has it) and the demographics series (`routers/insights.py:44-94`). | `test_the_seven_new_labels_are_read_from_the_page`, `test_the_new_post_figures_and_the_network_split_land_in_the_reading`, `test_demographics_are_a_dated_series`, `test_a_share_outside_the_range_or_a_percentage_sent_as_a_count_is_not_stored`, `test_a_network_split_that_does_not_add_up_is_dropped_and_is_not_drift`, `test_demographics_never_take_the_network_split_above_their_heading`, the five S1 layout tests, and the decision's tests above. | `test_a_percentage_is_never_read_as_a_count`; `test_only_the_labels_read_before_this_cycle_can_drift`. Falsified: on the reader before this item (6457e52) three of the original reader tests fail and the other seven hold either way; each S1 layout test fails on the reader before 84d66f1; the planted label above. | All of them: "followers gained", "profile viewers" (or "profile views"), "link visits" (or "link clicks"), "article views", "video views", the split's six phrasings and the demographics heading. None is drift when absent (the decision above). |
| 20 Account series (05cee93, fcc5c87, 9368722, a2d2990) | `onboarding.py:659-691, 750` a profile read writes the day's followers and connections into `analytics_daily` (an upsert of those two columns). `linkedin_client.py:205-252` `_store_window`; `:409, 418-428, 452, 458-459` a windowed card is kept in `analytics_windows` while the ingest still answers `window_mismatch` with `saved 0`. `linkedin_client.py:510-535, 590-607` both daily writes are upserts of the columns they read (Track 6's finding). `routers/analytics.py:289` `window_words`; the overview returns `windows` labelled "weekly" or by length and counts its range back from the latest daily row, as get_kpis does (fcc5c87). `retention.py:425-434` the roll-up keeps the first reading of each day as well as the last. | `test_a_profile_read_writes_followers_and_connections_to_the_daily_series`, `test_a_profile_read_does_not_disturb_a_daily_figure_already_stored`, `test_a_seven_day_card_is_kept_as_a_week_and_shown_as_weekly`, `test_the_roll_up_keeps_the_first_reading_of_each_day_as_well_as_the_last`, `test_a_window_row_never_moves_the_daily_range`, `test_a_daily_write_never_clears_a_column_another_writer_filled`. `tests/test_qc2_r4_retention.py:277-291` moves its per-day count from 1 to 2 with the rule. | The window_mismatch tests in five existing modules still hold that a weekly figure is never a day. Falsified: the first anchor failed the window test and two existing tests in the suite's order; INSERT OR REPLACE failed the column test. | The 24-hour range and the 7-day default are live checks. "unrecognised" is never stored as a window. |
| 21 Decay and half-life (4a9683b, a0a8a58) | `results.py:969-975` the minimums; `:986` `series_words`, `:990` `series_source`, the one page a figure's series is read from (S2); `:1015` `readings_of`; `:1038` `usual_at_age`; `:1069` `_ago`; `:1085` `movement`, "still moving: +50 impressions since the reading 26 hours ago, over 2 readings on its analytics page, the latest 2 hours ago"; `:1141-1188` `half_life`; `:1224-1239` `half_lives`, `half_life_spread`, `half_life_difference` through `results.spread` and `results.difference`. `today.py:146` `_movement`, attached at `:410`; `_open_next` untouched. `TodaySurface.tsx:986-987`, one block. | The eight item 21 tests failed before the engine had these functions; the S2 tests (a stray reading, the denser page, the sentence naming it) fail before a0a8a58. | `test_the_decay_sentence_and_the_half_life_have_one_definition`, widened in 5d7c1b1 (below). | None. |
| 22 Format column (9481da9) | `studio/backend/post_format.py` (new, imports no studio module). `archive_import.py:81-87, 1034, 1048, 1056`. `contrast_engine.py:46` `FORMAT_FEATURES`; `:94` `_verdict`, the seven features' verdict moved into one function both evaluators call; `:159` `evaluate_format_contrast`, unknown on neither side; `:245-250` `format_contrasts`, `format_coverage`. The post detail route returns `format`. | The five item 22 tests failed before the module existed. | Falsified: a classifier that called a row with no media "text" failed two tests; an engine that counted unknown posts as "without" reported 20 against 14. | The archive's MediaUrl and SharedUrl shapes are unverified against a real export; anything else is 'unknown'. No source names "text" or "poll" today. |

## Second round: the review of 3ed0665

The independent review (scratchpad/reviews/t5-derive-review.md) sent items 19, the help and this record
back, and accepted 18, 20, 21 and 22 with notes. Each fix below came with its test failing first.

| Finding | Commit | What changed |
|---|---|---|
| B1, drift from labels LinkedIn does not show | d439ccb, 573b8df | The owner's decision (section above); the endpoint ledger counts the sightings route |
| S1, demographics stored mis-paired | 84d66f1 | An entry is the nearest element holding exactly one percentage and one other text; the category is the entry's own heading; a tab bar leaves it unknown; the split is never an entry; loose siblings store nothing. Fixtures for the reviewer's three layouts, a tab bar and loose siblings |
| S2, one reading erasing others (with Track 6's export finding) | a0a8a58 | Each figure's latest value is the newest reading that has it ("by_figure"); a rate is measured only from one reading; a derivation reads one page's series per figure, the page that read it most often, the post's analytics page on a tie, named in the sentence. Also N5 (wording) and N7 (per_post per figure) |
| S3, a missing flag taken as exact | 05a7540 | `reading_half_width`: unknown is "may have been rounded" |
| Track 6, the daily write replacing the row | a2d2990 | Both daily writes are per-column upserts; also N10 (the window message) |
| S4, forget leaving the demographics | 8ea2eff | `audience_demographic_readings` added to the forget list (`onboarding.py:871-872`) |
| S5, the export leaving out both tables | 20fe2fb | Both added to `EXPORTABLE_TABLES` (`support.py:106-109`), and the help sentence (which also no longer promises queue items) |
| S6, the privacy policy | 27c98ef | The post analytics paragraph (`PRIVACY_POLICY.md:48-56`) names every figure and that demographics are aggregate percentages, never names; `release/privacy.html` rebuilt; a guard ties the paragraph to the reader's labels |
| N12 and item 8, the narrow guard | 5d7c1b1 | Names bound any way, the wording joined across literals, and the interface source, all checked; each of the reviewer's three escapes, planted in the real tree, fails it |
| N11, two help claims | 76cffe7 | No screen shows weekly readings yet; the first reading of a day is what the half-life rests on |
| S7, this record | this commit | Every file edited outside the named list, the weekly-table reason, the not-done items, the amended decision, this section |

## The help

| Article | What it says now |
|---|---|
| docs/help/what-to-do-today.md | The "still moving" line and the page its series is read on; what the post analytics reader reads; a missing newer figure stores nothing and does not mark the reader; rounded figures |
| docs/help/set-up-the-studio-from-your-linkedin.md | The reader's row lists the new figures; only a missing one of the seven marks the reader |
| docs/help/read-your-analytics.md | A post's page feeds its own readings; a windowed card is kept as its window, shown nowhere yet; the profile adds a follower point; rounding on both pages; demographics kept, dated, shown nowhere yet |
| docs/help/choose-what-the-studio-keeps.md | The roll-up keeps the first and the last reading of each day, and what each is for |
| docs/help/why-is-my-analytics-chart-empty.md | A post's analytics page feeds that post's readings, never the chart |
| docs/help/back-up-restore-and-export.md | The export carries the dated demographics and the windowed readings |

## Lines touched in own_pages.js and onboarding.py

own_pages.js against main (Track 1 owns the rest of the extension). Two regions only: `parseCount` (main
222-257) and the post analytics page section, from its comment to the end of `capturePostAnalytics`
(main 1150-1218). `postAnalyticsUrn` and `const metrics = readPostAnalytics();` are main's lines
unchanged; `announce` and everything after it are untouched.

| Branch lines | Was (main) | What |
|---|---|---|
| 231-237 | 231 | `parseFigure` comment and head |
| 262-267 | 256 | `parseFigure` returns `{value, rounded}`; `parseCount` wraps it |
| 1169-1178 | after 1157 | Comment on the unverified labels and the owner's decision |
| 1188-1194 | after 1166 | Five count labels |
| 1196-1212 | after 1167 | `POST_SHARE_LABELS`; `POST_LABELS_ON_EVERY_POST`, the seven verified labels |
| 1214-1319 | after 1168 | `PERCENT_ONLY`, `PERCENT_IN_TEXT`, `parsePercent`, the demographics reader (`DEMOGRAPHIC_DIMENSIONS`, `EVERY_PERCENT`, `dimensionOf`, `percentCount`, `textPieces`, `boundLabel`, `namesTheSplit`, `readPostDemographics`) |
| 1338, 1341-1355 | after 1186, 1188 | `rounded` list; the split read beside its label |
| 1364-1370 | 1197 | A figure keeps its rounding |
| 1373-1388 | after 1199 | The split must add up; `precision`; demographics |
| 1392-1398 | after 1202 | `postAnalyticsDrift` |
| 1404-1405 | 1208-1209 | `capturePostAnalytics` counts the figures and reports drift for verified labels only |

onboarding.py against main (Track 1 owns the rest of the file).

| Branch lines | Was (main) | Region | What |
|---|---|---|---|
| 659-691 | after 658 | profile (outside the post-analytics handling; item 20 needs it) | `_record_account_point` |
| 750 | after 716 | profile (as above) | its one call in `observe_profile` |
| 871-872 | 837 | forget (Track 1; S4 asked for one line) | `audience_demographic_readings` in the forget list |
| 968-1002 | 933 | post analytics | `METRIC_FIELDS` grows, `SHARE_FIELDS`, `READING_FIELDS`, `_share`, `PRECISIONS`, `_precision` |
| 1011-1035 | 942-960 | post analytics | `_record_observation` stores the shares and the precision |
| 1043-1082 | after 967 | post analytics | `DEMOGRAPHIC_ENTRIES`, `_record_demographics` |
| 1106, 1113 | after 990, 997 | post analytics | `ingest_post_analytics` records demographics and says how many |
| 1117, 1121, 1127-1203 | 1001, 1005, after 1010 | post analytics | `post_readings`; `post_demographics`; `UNVERIFIED_FIELDS`, `SIGHTINGS_MEANING`, `post_analytics_sightings` |

## Every file this track edited outside its named list

The PRD names this track's files as one migration, the label and number-parsing region of own_pages.js,
results.py, today.py's decay sentence, retention.py's roll-up and the analytics routers' new fields. The
coordinator's brief added post_summary.py, contrast_engine.py and the post-analytics region of
onboarding.py. Everything else below was edited outside that list, each change small, additive where it
could be, and listed for the merge.

| File | Owner or other editor | Lines | Why |
|---|---|---|---|
| studio/backend/post_summary.py | brief only, not the PRD | 258-262, 283-285, 288-289, 293, 297-306 | The summary's readings carry precision and, per figure, the newest reading that has it |
| studio/backend/contrast_engine.py | brief only, not the PRD | 18, 23, 26, 40-48, 91-100, 159-194, 216-223, 232-238, 244-250 | Format features; the seven features' verdict moved into `_verdict` (the reviewer confirmed their behaviour is unchanged) |
| studio/backend/routers/insights.py | Track 4 also extends it, likely on `readings` | 13-14, 16, 20-21, 23, 44-94, 101 | The post detail route's derived fields: precision, approximate, readings, per_post, demographics, movement, half_life, format |
| studio/backend/routers/analytics.py | analytics routers' new fields | 13, 21, 29, 55-59, 289-301, 309-349, 355-365, 394, 405, 452-454, 529-530 | The rounding alias, the windows, the sightings route, the leaderboard's one-reading rate |
| studio/backend/linkedin_client.py | Track 6 (the gating) | 205-252, 409, 418-428, 452, 458-459, 510-535, 590-595, 597-607 | The weekly window; both daily writes made upserts; nothing in the session or send code |
| studio/backend/archive_import.py | Track 7 (the new categories) | 81-87, 1034, 1048, 1056 | Item 22's archive source in `_import_posts`, no existing line changed |
| studio/backend/support.py | shared | 106-109 | The export lists both new tables |
| studio/backend/docs_engine.py | shared | 711 | Files this record |
| docs/PRIVACY_POLICY.md and release/privacy.html | Tracks 6 and 7 edit other paragraphs | 48-56; the whole page rebuilt | The post analytics paragraph; the page is generated, so each track's rebuild must be redone on the merged policy |
| studio/ui/src/components/TodaySurface.tsx | Track 3 also edits | 986-987 | The decay sentence, one block in `LatestPost` |
| studio/ui/src/components/PostDetail.tsx | Track 4 draws Posts | 116-117 | The "about" line |
| studio/ui/src/components/StoragePrivacyWorkspace.tsx | Track 4 (the Brand and Settings split) | 406 | "then the first and the last of each day." |
| studio/ui/src/lib/api.ts | shared | 2154-2166, 2299-2302 | Types for `movement` on Today and `figures_precision`, `approximate` on the detail |
| tests/test_onboarding_identity.py | shared | 56-62 | Its wipe removes the follower point its profile reads now write (9368722) |
| tests/test_qc2_r4_retention.py | shared | 277-291 | The roll-up's per-day count moves from 1 to 2 with the rule |
| tests/test_endpoint_reachability.py | shared; every track that adds a route moves these numbers | 250-259 | Total 172 to 173, unreachable 54 to 55; measure again on the merged tree |
| six help articles | shared | see The help | |

## Not done, and why

- **Card markers for item 22, and the Activity tab's precision flag (S3).** Both readers are Track 1's
  regions. The integration follow-ups: the activity card reader (`cardCounts`, main `own_pages.js:945-977`)
  reads its counts with `parseFigure` and adds `precision` and `format_markers` (the format words it found
  on the card) to each post item; `ingest_own_posts` (main `onboarding.py:919-923`) passes the item's
  precision to `_record_observation` and calls `post_format.record(conn, urn,
  post_format.from_markers(item.get("format_markers")))` after its upsert. `post_format.from_markers` is
  written and tested as the contract.
- **Video watch time, average watch time, and a newsletter's email sends and open rate.** The report's
  content-specific metrics include them; this track read article views and video views only. Watch time is
  a duration ("3h 20m") and the open rate a share of sends, so each needs a parser no reader has, and no
  page or fixture of a video or newsletter post's analytics exists to write their labels against. They are
  walked past as before, and the sightings do not list them because nothing reads them.
- **Drawing the new fields.** The routes return them; Track 4 draws Posts in its phase b and the Health
  count. Nothing draws `windows` on Analytics, `format_contrasts` on Patterns, `half_life`, `per_post` or
  the demographics yet (review N4), and the help claims none of them is on a screen.
- **A format for posts already held (review N6).** Every post existing at the upgrade stays 'unknown', and
  only a fresh archive import fills it; a known format is never overwritten, so an unverified archive
  shape that misfiles one cannot be corrected by a later card marker. Nothing shows the format yet.
- **Review notes not taken up:** N2 ("500+ connections" stored as 500), N3 (follower-only days counted as
  captured days, which the weekly path already did), N8 (`window_words` repeats `_WINDOW_LABEL`), N9 (a
  window row says 7 days but not which seven), N13 (the Storage panel files the new tables under "other")
  and N16 (the sentence prints the change, not both readings). Each is small and none puts a wrong figure
  on a screen today.
- **The live checks** (the owner's): the 2026 labels on the post analytics page, whether a Basic member
  sees profile viewers, the 24-hour range, figures above 10K, and the archive's media field on a real
  export.

## For the coordinator

- **Upgraded databases.** Migration 28 marks every stored per-post summary row stale, so the catch-up
  rewrites each once with per-figure entries; until it has, results.figures reads those posts from the
  readings, which is the same answer. Readings taken before the migration carry no precision flag and are
  treated as possibly rounded, so an old 12K pair reads "about", never as a measured change.
- **What the full runs found on the way.** The first: an overview anchored on the newest window row
  emptied two existing tests' range (fcc5c87). The second: a profile read's follower point, left by
  `test_onboarding_identity.py` in the shared database, became the latest day (9368722). The fourth: the
  endpoint ledger counted the sightings route (573b8df). Tests that send a multi-day payload or a
  confirmed profile to the shared database now leave a window row or a follower point; neither can move a
  range now.
- **Merge order.** routers/insights.py meets Track 4, TodaySurface.tsx Track 3, linkedin_client.py Track 6,
  archive_import.py Track 7, the policy and its page Tracks 6 and 7, and the endpoint ledger every track
  that adds a route.

## Phase 2: the creator's own surfaces (the owner's direction, 2026-10-26)

New capability on the owner's direction to capture more and show it, without an independent review this
phase: each test failed first, each new page has a fixture, one full suite at the end.

| | |
|---|---|
| Commits | 48640ea (the studio: migration, storage, routes, sightings), 9be9975 (the readers, the manifest and relay lines, the policy), e429437 (two findings of the first full run), and this record with the help |
| Migration | `_migrate_account_and_content_readings`, "Account figures, own article and newsletter readings, own reposts, edited posts and watch time", numbered 29 here, renumbered at merge; tests find it by name |
| Tests | tests/test_qc4_t5_insights.py (19), tests/test_qc4_t5_insights_reader.py (10) |
| Full suite | 3207 passed, 17 skipped, 0 failed, as CI runs it, on e429437 with this record in place; the skips are the environment's. The first run found two rules doing their jobs: the relay allowlist ratchet (`tests/test_mcp_routes.py`), which now names the new path with its review, and the distribution check, which reads `/in/me/` as the alias only when the address ends its string, as it now does (e429437) |

What each page keeps, counts and windows only, never another member:

| Page | Keeps |
|---|---|
| The analytics dashboard (`/dashboard/`, `/analytics/creator/...`) | Profile views and search appearances, each with the window its own card or the range control names; new followers by day from the graph's accessible labels |
| Who viewed your profile (`/me/profile-views/`) | The viewer count and its window; no viewer's name, headline, company or link is read |
| Search appearances (`/me/search-appearances/`) | The count and its window; no searcher or company |
| An article's or a newsletter's analytics page (`/analytics/article/<urn>/`, `/analytics/newsletter/<urn>/`) | Article views, impressions, members reached, reactions, comments, reposts; subscribers, email sends, email open rate |
| A video post's analytics page | Watch time and average watch time, in seconds, on the post's readings |
| The creator's own Activity tab | That a card is their repost, its date and its own figures (the embedded original taken out first), never the original's author, words or figures; when a post was first seen marked edited |

Routes for the interface to draw next:

- `GET /api/analytics/account-figures?range=30d`: `profile_views` and `search_appearances`, each a list of
  `{date, value, period_label, covers, label, precision, source, read_at}`; `new_followers`, a list of
  `{date, value, precision, source}`; `from`, `to`. What Analytics needs to show profile views again
  (sections decision 8).
- `GET /api/analytics/content-figures`: `content`, a list of `{content_urn, kind, readings, latest}`, where
  `latest` holds each figure's newest value with its time, window and precision.
- `GET /api/v1/insights/reposts`: `reposts`, a list of `{activity_urn, reposted_at, reactions, comments,
  reposts, impressions, first_seen_at, last_seen_at}`.
- `GET /api/v1/insights/posts/{urn}`: `edited_first_seen_at`, and `per_post` gains `watch_time_seconds` and
  `average_watch_seconds`.
- `GET /api/analytics/post-field-sightings`: the post analytics fields, now with watch time, and `pages`, a
  list of `{page, readings, fields}` for the account and content pages and the Activity tab, each field
  `{field, label, last_read_at, readings_since, sentence}`.
- `POST /api/analytics/page-figures`: the extension's; the owner check is the analytics ingest's.

Lines in Track 1's files:

| File | Branch lines | What |
|---|---|---|
| studio/extension/own_pages.js | 1080-1082 | The Activity reader's one call to `inoxOwnCardFacts` (own_insights.js); in this track's post analytics region, 1209-1215, 1234-1252 and 1369-1378 (watch time) |
| studio/backend/onboarding.py | 47-54, 880-881, 918, 930-934, 971, 979 | The import of own_insights and results; `own_reposts` in the forget list; the repost and edited call sites and the count in `ingest_own_posts`. In this track's region: 990-992, 1171-1172, 1203-1204 |
| studio/extension/manifest.json | 44 | Loads own_insights.js after own_pages.js |
| studio/extension/background.js | 36-37 | Relays `POST /api/analytics/page-figures` |

Unverified and not done:

- Every page path and label above is the Help's wording or a plausible form, unverified against 2026
  pages. Unknown layouts send nothing, and the sightings say how long each figure has gone unread.
- A repost card's URN may be the original's rather than the repost's, in which case `reposted_at` is the
  original's date; the record keeps no author either way. A repost's own figures are read only when an
  embedded original can be taken out of the card.
- The new readers report no capture runs: Setup's capture health is keyed by Track 1's extractor registry,
  and under the owner's rule their absent labels are not drift. Their visibility is the sightings route.
- Video analytics on a page of their own are not read: LinkedIn shows a video post's figures on its post
  analytics page, where watch time is now read.
- No screen draws the new figures yet. Whether profile viewers become lead candidates like engagers is the
  owner's separate decision; nothing about them is stored.
