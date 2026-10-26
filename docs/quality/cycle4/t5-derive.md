# Cycle 4, track 5: derive

Branch `qc4/t5-derive`, from `main` at cf0ba9d (2.7.0, schema 27). Specification: the capture
report, section Derive and programme items 18 to 22; sections decision 14. Every path:line below
is on the branch head unless it says otherwise.

| | |
|---|---|
| Items | 5 of 5 built; item 22's card-marker source is written as a contract, not wired (closing section) |
| Migration | one, `_migrate_reading_precision_and_series`, numbered 28 here, found by tests by its name |
| Commits | 6457e52 (18), d8d9399 (19), 05cee93 (20), 4a9683b (21), 9481da9 (22), b9da5d4 (help), fcc5c87 (20, found by the suite), c4d01ae (19, found in review), 9368722 (a test's cleanup, found by the suite), and this record |
| New tests | tests/test_qc4_t5_derive.py (29), tests/test_qc4_t5_post_analytics_reader.py (10) |
| Full suite | 3155 passed, 17 skipped, 0 failed, as CI runs it (`pytest tests studio/tests -q -rs`, 10 min), on 9368722 with this record and its filing in place; the 17 skips are the environment's (Windows, macOS, a workstation browser, pyyaml). Two earlier runs found two defects, both fixed (closing section) |

## The migration

`studio/backend/migrations.py:1427` `_migrate_reading_precision_and_series`, ledger entry at
`migrations.py:1540`, description "Precision on post readings, dated demographics, a format per post
and windowed analytics as windows". Tests assert the name and the columns
(`test_the_track_has_one_migration_named_for_what_it_changes`), never the number.

| Adds | Columns |
|---|---|
| on `post_metric_observations` | `precision`, `followers_gained`, `profile_viewers`, `link_visits`, `article_views`, `video_views`, `in_network_pct`, `out_of_network_pct` |
| on `own_posts` | `format TEXT NOT NULL DEFAULT 'unknown'` |
| table `audience_demographic_readings` | `observed_at`, `observed_on`, `activity_urn` (`''` for the account), `source`, `dimension`, `label`, `percentage`; one row per day per dimension and label |
| table `analytics_windows` | `date`, `period_label`, `observed_at`, `impressions`, `reactions`, `comments`, `shares`, `followers`, `precision`, `source`; key `(date, period_label)` |

## Items

| Item | What changed (path:line) | Fails without it | Guard and how it was falsified | Unverified, shown as drift |
|---|---|---|---|---|
| 18 Precision column (6457e52) | `own_pages.js:231-267` `parseFigure` keeps whether a figure carried K or M, `parseCount` is the figure alone; the post analytics reader sends one `precision` per reading (`own_pages.js:1320-1326, 1343`). `onboarding.py:991-1001` `PRECISIONS`, `_precision`; `_record_observation` stores it and keeps a reading rounded if either read in the hour was (`onboarding.py:1022-1034`). `results.py:392` `rounding_half_width` moved from the analytics router into the engine, which the router aliases (`routers/analytics.py:57`); `results.py:414` `approximate_fields`; `results.py:425` `growth` (approximate when either reading was rounded, within rounding when the change is no larger than the two half widths). `results.figures` and the summary carry `precision` (`results.py:230, 276`; `post_summary.py:261`). The post detail route returns `figures_precision` and `approximate` (`routers/insights.py:50`), and the Posts detail names the rounded figures in one line (`PostDetail.tsx:116-117`). | `test_a_rounded_reading_is_stored_as_rounded_and_an_unsaid_one_as_unknown`, `test_growth_between_two_rounded_readings_is_approximate_never_measured`, `test_the_posts_detail_says_about_where_a_reading_is_rounded`, `test_a_figure_written_as_12k_is_sent_as_rounded`. The first and the last failed before the change (the store had no column, the reader sent no flag); the run stopped at the first failure, and the other two call `results.growth` and read `figures_precision`, neither of which existed. | `test_the_rounding_width_has_one_definition`: the router's function is the engine's object. Falsified: a second `def rounding_half_width` planted in the router fails it; the precision discarded at ingest fails `test_a_rounded_reading_is_stored_as_rounded_and_an_unsaid_one_as_unknown`. | None. Whether LinkedIn abbreviates above 10K on the post analytics page is a live check; the flag is right either way. |
| 19 Seven missing fields (d8d9399, c4d01ae) | `own_pages.js:1169-1176` comment; `own_pages.js:1186-1192` the five count labels in the Help's wording, two spellings for two of them; `own_pages.js:1194-1204` `POST_SHARE_LABELS`; `own_pages.js:1205-1209` `POST_LABELS_ON_EVERY_POST`; `own_pages.js:1211-1275` `PERCENT_ONLY`, `parsePercent`, the demographics reader, which reads only what follows its heading; `own_pages.js:1297-1311` the split read beside its label; `own_pages.js:1333-1357` a split that does not add up to about 100 is dropped and reported, then demographics and `postAnalyticsDrift`; `own_pages.js:1364-1367` the capture reports the drift. `onboarding.py:967-994` the new count fields and `SHARE_FIELDS` (a share is a percentage, never summed); `onboarding.py:1042-1081` `_record_demographics` (dated, a second read the same day refreshes); `onboarding.py:1105, 1112` the ingest calls it; `onboarding.py:1116-1137` `post_readings` returns every field, `post_demographics` the series. The post detail route returns `readings`, `per_post` (from the newest page reading, with its age) and `demographics` (`routers/insights.py:46-90`). | `test_the_seven_new_labels_are_read_from_the_page`, `test_an_absent_unverified_label_is_drift_not_silence`, `test_the_new_post_figures_and_the_network_split_land_in_the_reading`, `test_demographics_are_a_dated_series`, `test_a_share_outside_the_range_or_a_percentage_sent_as_a_count_is_not_stored`, `test_a_network_split_that_does_not_add_up_is_drift_and_never_stored`, `test_demographics_never_take_the_network_split_above_their_heading`. Falsified: on the reader before this item (6457e52) the five reader tests on the new labels, drift, split and demographics fail; with METRIC_FIELDS cut back to seven, the split not stored, or demographics not recorded, the backend tests named fail; the unhardened reader stores a 62/62 split and takes "In your network" as a demographic. | `test_a_percentage_is_never_read_as_a_count` holds NUMBER_ONLY refusing "62%". `test_an_absent_unverified_label_is_drift_not_silence` is the drift guard. Falsified: with `profile_viewers` taken out of `POST_LABELS_ON_EVERY_POST` it fails. | All of them: "followers gained", "profile viewers" (or "profile views"), "link visits" (or "link clicks"), "article views", "video views", the split ("in your network", "in network", "from your network"; "outside your network", "out of network", "beyond your network") and the demographics heading. Absent on a page where any measured label was found, these are drift by name: `followers_gained`, `profile_viewers`, `in_network_pct`, `out_of_network_pct`, `demographics`; `demographics_entries` when the heading is there and nothing pairs; `network_split` when the two shares do not add up. Link visits and the article and video figures are not drift when absent: a text post has none. |
| 20 Account series (05cee93) | `onboarding.py:659-691` `_record_account_point` and its one call in `observe_profile` (`onboarding.py:750`): a profile read writes the day's followers and connections into `analytics_daily` through the follower card's COALESCE path, nothing else on the row. `linkedin_client.py:205-250` `_store_window`; `linkedin_client.py:409-428, 452, 458-459` a windowed card is kept in `analytics_windows` as its window, while the ingest still answers `window_mismatch` with `saved 0`. `routers/analytics.py:287` `window_words`; the overview returns `windows` labelled "weekly" or by length, never in the daily series or the totals, and counts its range back from the latest daily row as get_kpis does (`routers/analytics.py:301-347`, fcc5c87). `retention.py:425-436` the roll-up keeps the first reading of each day as well as the last; the docstrings, the Storage panel line (`StoragePrivacyWorkspace.tsx:406`) and the help say so. | `test_a_profile_read_writes_followers_and_connections_to_the_daily_series`, `test_a_profile_read_does_not_disturb_a_daily_figure_already_stored`, `test_a_seven_day_card_is_kept_as_a_week_and_shown_as_weekly`, `test_the_roll_up_keeps_the_first_reading_of_each_day_as_well_as_the_last`; all four failed before the change, the last with "2026-09-11 kept 1 readings". `tests/test_qc2_r4_retention.py:277-291` moves its per-day count from 1 to 2: that is the rule change, and the Today-identical test beside it is unchanged and passes. | The window_mismatch tests in five existing modules still hold the line that a weekly figure is never a day. `test_a_window_row_never_moves_the_daily_range`: in the suite's order the first anchor failed it and two existing tests; fixed in fcc5c87. | The 24-hour range and the 7-day default on the 2026 page are live checks. A window the reader could not name ("unrecognised") is never stored as a window. |
| 21 Decay and half-life (4a9683b) | `results.py:898-904` the minimums (`MIN_READINGS_TO_MOVE` 2, `MIN_READINGS_FOR_HALF_LIFE` 3, `HALF_LIFE_AT_HOURS` = `SETTLED_AFTER_HOURS`); `results.py:910` `readings_of` (one page, the newest reading's); `results.py:934` `usual_at_age` (the settle curve's share, abstaining below 20 posts a bucket); `results.py:965` `_ago`; `results.py:981` `movement`, in the brief's form, "still moving: +50 impressions since the reading 26 hours ago, over 2 readings, the latest 2 hours ago", "about" when rounded, "cannot separate" within rounding; `results.py:1080` `half_life`, interpolated and named, refusing below three readings and before seven days, an upper bound when the first reading held half; `results.py:1116-1131` `half_lives`, `half_life_spread`, `half_life_difference` through `results.spread` and `results.difference`. `today.py:146` `_movement` as its own function, attached at `today.py:410`; `_open_next` untouched. The post detail route returns `movement` and `half_life`. Today's latest-post block draws the sentence in one block (`TodaySurface.tsx:986-987`). | Eight tests in the module's item 21 section failed before the engine had these functions. | `test_the_decay_sentence_and_the_half_life_have_one_definition` fails when any backend module but `results.py` defines a derivation of these names or carries the sentence in a string literal outside a docstring. Falsified on the real module: a planted `def half_life()` and "still moving" in today.py were both named at today.py:442; restored byte-identical. `test_the_one_definition_guard_is_not_vacuous` plants the same in memory and shows a docstring that only describes the sentence is not counted. | None. |
| 22 Format column (9481da9) | `studio/backend/post_format.py` (new, imports no studio module): `FORMATS`, `from_archive` (MediaUrl by its address, then SharedUrl), `from_markers` (the card-reader contract), `record` (fills only 'unknown'). `archive_import.py:81-86, 1034, 1048, 1056` the posts import names each row's format. `contrast_engine.py:46` `FORMAT_FEATURES`; `contrast_engine.py:94` `_verdict`, the seven features' verdict moved into one function both evaluators call; `contrast_engine.py:159` `evaluate_format_contrast`, unknown on neither side; `contrast_engine.py:245-251` `format_contrasts` and `format_coverage`. The post detail route returns `format`. | `test_the_archives_media_field_names_a_format_or_says_unknown`, `test_card_markers_name_a_format_only_when_they_agree`, `test_an_archive_import_records_each_posts_format`, `test_format_comparisons_run_through_the_contrast_engine_with_its_abstentions`, `test_format_comparisons_flag_different_periods`; all five failed before the module existed. | Falsified: a classifier that called a row with no media "text" failed two tests; an engine that counted unknown posts as "without" reported 20 against the 14 the test holds. Both files restored byte-identical. | The archive's MediaUrl and SharedUrl shapes (`/image/`, `/vid/`, `/document/`, `/pulse/`, `/newsletters/`, a LinkedIn post) are unverified against a real export; anything else is 'unknown'. No source names "text" or "poll" today. |

## The help

| Article | Lines | What it now says |
|---|---|---|
| docs/help/what-to-do-today.md | 46-47, 52 | The "still moving" line; what the post analytics reader reads, rounded figures, and that Setup may show it drifting until the labels are checked |
| docs/help/set-up-the-studio-from-your-linkedin.md | 110 | The reader's row lists the new figures and the drift rule |
| docs/help/read-your-analytics.md | 10, 14, 19, 26, 37, 82 | A post's page feeds its own readings; a windowed card is kept as its window and the chart uses daily figures only; the profile adds a follower point; rounding on both pages; demographics kept, dated, shown nowhere yet |
| docs/help/choose-what-the-studio-keeps.md | 28, 33 | The roll-up keeps the first and the last reading of each day |
| docs/help/why-is-my-analytics-chart-empty.md | 17 | A post's analytics page feeds that post's readings, never the chart |

## Lines touched in shared files

own_pages.js, against main (Track 1 owns the rest of the extension). Only two regions: `parseCount` and
the post analytics page section, from the section comment to `capturePostAnalytics`.

| Branch lines | Was (main) | What |
|---|---|---|
| 231-237 | 231 | `parseFigure` comment and head (the old `parseCount` head) |
| 262-267 | 256 | `parseFigure` returns `{value, rounded}`; `parseCount` wraps it |
| 1169-1176 | after 1157 | Comment on the unverified labels |
| 1186-1209 | after 1166-1167 | Five count labels, `POST_SHARE_LABELS`, `POST_LABELS_ON_EVERY_POST` |
| 1211-1275 | after 1168 | `PERCENT_ONLY`, `PERCENT_IN_TEXT`, `parsePercent`, `DEMOGRAPHIC_DIMENSIONS`, `dimensionOf`, `readPostDemographics` |
| 1294, 1297-1311 | after 1186, 1188 | `rounded` list; the split read beside its label |
| 1320-1326 | 1197 | A figure keeps its rounding |
| 1329-1357 | 1200 | The split must add up, `precision`, demographics, `postAnalyticsDrift` |
| 1364-1367 | 1207-1209 | `capturePostAnalytics` reports the drift |

Nothing else in own_pages.js changed: the two regions are `parseCount` (main 222-257) and the post analytics page section, from its comment to the end of `capturePostAnalytics` (main 1150-1218); `announce` and everything after it are untouched.

onboarding.py, against main (Track 1 owns the rest of the file).

| Branch lines | Was (main) | Region | What |
|---|---|---|---|
| 659-691 | after 658 | profile (outside the post-analytics handling, needed by item 20) | `_record_account_point` |
| 750 | after 716 | profile (as above) | the one call in `observe_profile` |
| 967-1001 | 933 | post analytics | `METRIC_FIELDS` grows, `SHARE_FIELDS`, `READING_FIELDS`, `_share`, `PRECISIONS`, `_precision` |
| 1010-1034 | 942-960 | post analytics | `_record_observation` stores the shares and the precision |
| 1042-1081 | after 967 | post analytics | `DEMOGRAPHIC_ENTRIES`, `_record_demographics` |
| 1105, 1112 | after 990, 997 | post analytics | `ingest_post_analytics` records demographics and says how many |
| 1116, 1120, 1126-1137 | 1001, 1005, after 1010 | post analytics | `post_readings` returns every field; `post_demographics` |

Other files outside the track's named list, each additive and small, for the coordinator's merge:

| File | Owner per the PRD | Lines | Why |
|---|---|---|---|
| studio/backend/linkedin_client.py | Track 6 (the gating) | 205-250, 409, 418-428, 452, 458-459 | Item 20's weekly card: `_store_window` and the window branch of `ingest_analytics_payload`; nothing in the session or send code |
| studio/backend/archive_import.py | Track 7 (the new categories) | 81-86, 1034, 1048, 1056 | Item 22's archive source: ten added lines in `_import_posts`, no existing line changed |
| studio/ui/src/components/TodaySurface.tsx | Track 3 also edits | 986-987 | The decay sentence, one block in `LatestPost` |
| studio/ui/src/components/PostDetail.tsx | Track 4 draws Posts | 116-117 | The "about" line, one line and its comment |
| studio/ui/src/components/StoragePrivacyWorkspace.tsx | Track 4 (the Brand and Settings split) | 406 | One string: "then the first and the last of each day." |
| studio/ui/src/lib/api.ts | shared | 2154-2166, 2299-2302 | Types for `movement` on Today and `figures_precision`, `approximate` on the detail |
| studio/backend/docs_engine.py | shared | the maintainers section, after `quality/CYCLE3_REGISTER.md` | Files this record, as tests/test_docs_library.py requires |
| tests/test_onboarding_identity.py | shared | the `clean` fixture's wipe | Removes the follower point its profile reads now write (9368722); no assertion changed |
| tests/test_qc2_r4_retention.py | shared | 277-291 | The roll-up's per-day count moves from 1 to 2 with the rule (05cee93) |

## Not done, and why

- **Card markers for item 22.** The card reader and `ingest_own_posts` are Track 1's regions, edited in
  parallel. `post_format.from_markers` is the contract, tested. Wiring is two edits there: the
  activity card reader adds `format_markers` (the format words it found on the card) to each post
  item, and `ingest_own_posts` calls `post_format.record(conn, urn, post_format.from_markers(item.get("format_markers")))`
  after its upsert. Until then a post's format comes from the archive alone.
- **Drawing the new fields.** The routes return them; Track 4 draws Posts in its phase b. Nothing draws
  `windows` on Analytics, `format_contrasts` on Patterns, `half_life`, `per_post` or `demographics` yet,
  and the help claims none of them is on a screen.
- **The live checks** (the owner's): the 2026 labels on the post analytics page, whether a Basic member
  sees "Profile viewers from this post", the 24-hour range, figures above 10K, and the archive's media
  field on a real export.
- **creator_identity's follower count** is not removed: it is the latest point, written in the same
  transaction as the series' point for the day, and the export and Setup read it as the latest.

## For the coordinator

- **Drift and Today.** `_open_next` (Tracks 1 and 6) names a drifting reader before anything else, and
  `capture_health` calls a reader drifting on any drift entry. Until the owner's live check settles the
  labels, a post analytics page that lacks one (a Basic member who never sees profile viewers, a
  low-reach post with no demographics) makes the reader drift and Today point at Setup, with "LAST
  WORKED" left at the last clean read before the change, or unset. That is decision 14's choice (drift, not silence), and it is loud. After the live
  check, trim `POST_LABELS_ON_EVERY_POST` (`own_pages.js:1208`) to the labels verified on every page.
- **Upgraded summaries.** post_summary's stored readings JSON gains a `precision` key. Rows written before
  migration 28 lack it and read it as None, which is the truth for every reading taken before then; a
  new reading marks its post stale and rewrites the row. `post_summary.differences()` (tests only) would
  report the missing key on an upgraded database; nothing at runtime reads it. The migration does not
  mark 1,417 rows stale, which would put their recomputation on the first screen after the update.
- **What the first full run found.** 2 failed, 3150 passed, 17 skipped: `test_analytics_overview_contract` and
  `test_multi_range_kpis_and_slots` saw an empty overview, because the overview was anchored on the latest
  day of either table and `test_analytics_and_funnel_integrity.py` leaves a 28 day window row dated
  2031-07-07 in the shared session database (it clears only the daily rows it writes). Fixed in fcc5c87 by
  anchoring on the daily rows as get_kpis does. Tests that send a multi-day payload to the shared database
  still leave `analytics_windows` rows behind; after the fix they cannot move any range.
- **What the second full run found.** 1 failed, 3154 passed, 17 skipped: `test_multi_range_kpis_and_slots` read one
  day where it expects fourteen. `test_onboarding_identity.py` reads a confirmed profile with 4,200 followers
  into the shared database, and since 05cee93 that read writes the day's follower point; the demo series ends
  on 14 September 2026, so the point became the latest day. Found by running each candidate test before the
  failing one. The behaviour is item 20's; the test's own wipe now removes the point (9368722). Any other test
  that reads a confirmed profile with a follower count into the shared database now leaves such a point; the
  full suite shows no other.
- **Review.** No independent review was run by this track.
