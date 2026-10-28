# Cycle 4, track 7, phase 2: the enhancer made better (2.10.0)

Branch `qc4/t7-phase2`, from `main` at e9ab6ff (2.9.0). Five items from
track 7's own "not done" list (`t7-ideas.md`), each built failing test first
in `tests/test_qc4_t7_phase2.py`. Capability first, no independent review.
No migration was needed: every item reads tables the section already has.

| | |
|---|---|
| Commits | 7, and this record |
| Tests | `tests/test_qc4_t7_phase2.py`, 17 functions; each failed before the change it holds, except the one that holds the diversity rule's fallback (a slot with only a repeated topic still fills), which passes either way by design |
| Guards falsified | topic diversity (two tests fail with the rule switched off); the date's slot taking turns (its test fails on the previous rule) |
| Suite, as CI runs it | 3,942 passed, 17 skipped (Windows, macOS, a workstation browser, pyyaml not installed, one deliberate), 0 failed, in 12 min 59 s, on 2ae2b3d; only this line changed after it |
| One view, three invented years | Today with the strip: 1.00 scroll pages, every block in the first view; the section: 1.13 scroll pages, 47% ink; Health: the block in the second viewport of 1.56, as its other blocks are |
| Interface audit | `tools/ui_audit.py`, both themes, desktop and phone: 68 screens on a fresh install and Today, the section and Health on three invented years (12 screens), none with a blocking finding |

## The items

| # | Item | Commits | What changed | Fails without it |
|---|---|---|---|---|
| 1 | Cards from follows, votes and articles | 3337c01, c0f9ea8 | An article of the creator's own whose title goes under a recurring topic, in the date's slot (`studio/backend/record_cards.py:604`); a poll they voted in and a company or member they follow, under a topic, in the engaged-with slot (:808, :892, :919), each citing its archive row with a "Because you published", "voted" or "follow" sentence. A vote shows its topic and link, never the poll's options, which are its author's words; a follow shows the name and date the archive holds. Each slot draws its kind by a stated weight (:96-97, `_choose_kind` at :346): a comment twice as often as each other kind; the post of the date twice as often as an opener or an article (c0f9ea8: on three invented years of a creator posting most days the post of the date had filled the slot on all 121 days, so openers and articles were never shown) | `test_an_article_of_yours_on_a_recurring_topic_can_be_working_for_you`, `test_a_poll_you_voted_in_and_an_account_you_follow_can_be_you_engaged_with`, `test_without_a_comment_the_other_activity_still_fills_the_slot`, `test_the_dates_slot_takes_turns_so_a_daily_poster_still_sees_openers_and_articles` |
| 2 | A Today block | 63d1e88, b9e2590 | `studio/ui/src/components/RecordTodayBlock.tsx`: today's cards, one line each, every line a link into the section, drawn only once today's batch exists, read again on the "ideas" change; its read `GET /api/v1/record/lines` is a SELECT of the stored batch (`studio/backend/record_daily.py:488`, `routers/record.py:161`), so opening Today builds nothing | `test_today_has_lines_only_once_todays_batch_exists`, `test_reading_the_lines_builds_nothing`, `test_today_draws_one_block_that_links_into_the_section` |
| 3 | Topic diversity across the slots | 889c0b4 | One rule in the draw (`_draw` at `record_cards.py:289`, said at :100): the slots are filled in order and each drawn slot takes a card on a recurring topic no earlier card of the day shows, when its pool has one; a repeat only when nothing else is free, so the rule never empties a slot. Every card carries its topic (`card_topic` at :340); the library's card (`library_bundle.py:365`) and a carried-forward day's dated card (`record_daily.py:254-255`) avoid the day's topics too. What worked is the record's and is never changed for it | `test_the_days_cards_are_four_topics_when_four_are_there`, `test_the_library_card_takes_a_topic_the_day_has_not_shown`; `test_a_slot_with_only_a_repeated_topic_still_fills` holds the fallback. Falsified by switching the rule off in `_draw` and `_choose_kind`: the first two failed |
| 4 | A Health block for the daily job | f1f87a4, b9e2590 | `studio/backend/record_health.py`: when the batch was last built, whether it was carried forward, how many cards failed a check; the model stage's spend against the daily ceiling from the dated price table, or why it spent nothing; whether a signed library is held and whether its key is one this studio still ships (`library_bundle.signature_state` at :340). `GET /api/v1/record/health` (`routers/record.py:167`), read beside Health's six routes | `test_the_health_read_says_when_the_job_ran_and_whether_it_carried_forward`, `test_the_health_read_sets_the_spend_against_the_ceiling`, `test_the_library_signature_state_is_said`, `test_health_draws_the_daily_job_block` |
| 5 | The weekly summary | 5dad506 | On the Monday card, beside the week's own counts: last week's cards shown and how many the creator kept, skipped, hid, drafted from and posted, each with the table it was counted from and compared with nothing (`record_week` at `record_cards.py:1085`; the strip at `RecordSurface.tsx:218`). A week with no card shown says so in words. The report's model-written summary stays out: decision 4 keeps Review deferred | `test_the_monday_card_counts_last_weeks_cards_and_marks`, `test_a_week_without_cards_is_said_not_counted`, `test_the_monday_strip_says_the_summary` |

The help says each: `docs/help/find-what-to-write-from-your-own-record.md`
(the cards table, the diversity paragraph, the Monday line, the Today and
Health mentions), `what-to-do-today.md` (a section for the strip) and
`check-the-bridge-is-reading.md` (the block).

## Measured

On the three invented years the phase 1 record describes (1,417 posts,
44,000 outbound rows), rebuilt with this branch: the daily job builds a day
in 96 ms median, 119 ms at worst (phase 1: 73 and 100); the extra is the
topic of each comment, vote, follow and article it now reads. Today stays one
view with the strip; the section's first view is 1.13 scroll pages.

Over 121 built days, two topics repeated only where both cards are the
record's own choice and not drawn: What worked against the post of the date
(32 days), and the post of the date against a comment carried forward from
the day before (3 days). The invented posts share their sentences, so their
recurring words are those sentences' words, and the invented follows, votes
and articles matched none of them: the tests, not this history, show those
cards.

## Not done, and why

- **The model's idea and the diversity rule.** The model chooses its own
  idea; its prompt is not told the day's topics, so its card can repeat one.
- **Two record-chosen cards on one topic.** What worked and the post of the
  date can share a topic: neither is drawn, and changing which post is best or
  which was posted on this date would make the cards untrue.

## Lines touched outside this track's files

- `studio/ui/src/components/TodaySurface.tsx:36` (the import) and `:655-657` (the block); track 4 edits this file in parallel
- `studio/ui/src/components/HealthSurface.tsx:9, 20, 71, 82, 89, 106-107, 479-494`
- `studio/ui/src/lib/api.ts:3382-3383, 3626-3649` (appended types and reads)
- `tests/test_endpoint_reachability.py:402-410` (215 -> 217 paths, 167 -> 169 reached)
- `docs/help/what-to-do-today.md:60-63`; `docs/help/check-the-bridge-is-reading.md:78`
- `studio/backend/docs_engine.py`: this record's line under maintainers
