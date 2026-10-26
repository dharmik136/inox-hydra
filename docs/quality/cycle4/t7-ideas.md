# Cycle 4, track 7: From your record

Branch `qc4/t7-ideas`, from `main` at cf0ba9d (2.7.0, schema 27). The
specification is the personalised daily ideas report, all of it, with the
fourteen decisions the cycle's PRD adopts (section 5.3) and track 7's items
(section 6). The track adds one migration, `_migrate_record_section`, which
is number 28 on this branch; its tests assert its name, its tables and their
columns, never the number, so the renumbering at merge changes no test.

| | |
|---|---|
| Batches done | 0 to 9 of the report's programme, with the rail entry, the help article and the policy |
| Batches not done | 10 (on-device embeddings, optional) and 11 (the web route: designed below, not built, decision 12) |
| Guards added, each falsified before it was kept | 8: the rail entry, no second ranking of posts, the other person's text never on a card, the job never imports the model stage, no number from a model on screen, a hide sets aside every kind of card, the Monday line out of the funnel, half an ask's words before a playbook match |
| Tests | 140 test functions in eleven files `tests/test_qc4_t7_*.py`, four of them Playwright |
| Commits | 24 |
| Suite, as CI runs it | SUITE_RESULT |
| One view, three invented years | Today's cards: 1.08 scroll pages, 46.5% ink, every answer in the first view; first paint 19.0 KB of API; the section's routes 3.2 to 15.0 ms median, 16.0 ms worst; the daily job 78 ms median a day |
| Interface audit | `tools/ui_audit.py`, both themes, desktop and phone: 52 screens on a fresh install and 4 record screens on three invented years, none with a blocking finding; and axe on all four of the section's views, both themes, both widths, twice (without and with a provider and a playbook line), 32 of 32 with no violation |

Every figure above is from data this track invented (no owner data was opened,
and none is in the repository). The commit trailers before batch 3 name the
model the environment specified then; from batch 3 on, the one it specifies now.

## The batches

Each row gives the report's batch, the commits, what changed with path:line in
the branch's final tree, the tests that fail without it, and how a guard was
falsified where one was added. Batch 5 was built before batch 4: the screen
only reads what the job writes, so the job came first.

| # | Batch (report) | Commits | What changed | Fails without it | Guard falsified |
|---|---|---|---|---|---|
| R | The rail entry (decision 2) | f4b193e | "From your record" after Today, with its blurb and screen key (`studio/ui/src/lib/navigation.ts:73`, the `SectionId` at :22); the screen registry (`studio/backend/devtools.py:174`); the audit walks it (`tools/ui_audit.py:59`); the route (`studio/ui/src/App.tsx:1026`) | `tests/test_qc4_t7_rail_entry.py` (7) | `test_the_guard_is_not_vacuous` removes the entry from a copy of the rail and asserts the guard's parser then finds no such section. Track 4's sixteen-entry guard becomes seventeen at merge (the coordinator's) |
| 0 | Honesty prerequisites | 99a84a5, 5667176 | The voice pack's openers come from `results.ranking`: track 3's cc78841 made the same change and was accepted, so this branch carries that version of `voice_pack.py` and of its two tests byte for byte, and the merge keeps one (the model stage's two helpers that were added to the voice pack live in `record_model.py`); `/api/inspirations` and its Viral Inspirations route are gone from `app.py`; `init_db` no longer recreates the `inspirations` table migration 2 drops (`studio/backend/database.py:331-336`), and the frozen baseline records its absence (`schema_baseline.json`); the swipe harvester agent is deleted, with its registry, orchestrator and contract lines | `tests/test_qc4_t7_honesty_prerequisites.py` (5); track 3's `tests/test_voice_pack.py::test_openers_come_from_the_one_ranking_so_a_young_post_is_not_an_exemplar` | `test_no_module_ranks_openers_by_raw_reactions` reads the voice pack for an `ORDER BY reactions`; falsified by planting the old query into a copy of the source, which it caught |
| 1 | Schema and custody | 6b0e318 | The migration: `asks`, `daily_run`, `daily_view`, `card_marks`, `record_notes`, `archive_records`, `library_entries`, `posts.origin_card_id` and `origin_day`, and the `record_card_posted` trigger that writes "posted" whichever path publishes a post that came from a card (`studio/backend/migrations.py:1426-1577`, registered at :1606-1608); the storage panel's categories (`studio/backend/retention.py:253, 261-267`); forget identity clears the section's rows (`studio/backend/onboarding.py:837-840`) and the archive's (`archive_import.forget`); the export carries them (`studio/backend/support.py:106-110`); the diagnostics allowlist was left alone, which is what keeps every ask and the section's settings out of it; the policy's paragraph on what is stored (`docs/PRIVACY_POLICY.md:144-166`) and the storage help's rows | `tests/test_qc4_t7_schema_and_custody.py` (9) | |
| 2 | Importer extension (decision 6) | 90cb538, 12003a1, 90683cb | Saved Items, Member Follows, Company Follows, Votes, Articles and Instant Reposts into `archive_records`, each row with its source file, import date and import id, deduplicated, and undone with its import (`studio/backend/archive_import.py:193-250`, `_record_importer` at :1312); Search Queries only behind a tick that is off (`archive_import.py:246`), and a search becomes an ask only when it shares one of the creator's recurring topic words, and is never sent to a model (`studio/backend/record_daily.py:150`, `studio/backend/record_model.py:292`); an absent file is neither guessed at nor listed. Instant Reposts is in the report's batch 2 though not in the PRD's list; it is kept as a link and a date, like a saved post | `tests/test_qc4_t7_archive_categories.py` (9); `tests/test_qc4_t7_daily_job.py::test_a_search_from_the_archive_becomes_an_ask_only...`; `test_qc4_t7_model_stage.py::test_an_ask_from_an_archive_search_is_never_sent` | |
| 3 | Local cards engine | e773ec2, 652d830, 6fba683 | `studio/backend/record_cards.py`: What worked through `results.best` and nothing else, abstaining in words ("Not enough settled posts yet: N of 3") (:335); On this day (:417); the resurfaced opener with the quality filter, the 7, 14 and 28 day holds, the halving per showing, the stored seed and the evergreen text rule (:454, the draw at :273, the weight at :236); You asked, an ask matched to the creator's posts by the search index (:522, :586) and to the playbook section that shares at least half its words, named and linked, never quoted (:549); You engaged with, a comment as link, date and the creator's own words, or a reaction, saved post or repost as link and date, never the other person's text (:671); the Monday card, counts only (:860); every card's cited rows looked up before it is kept, a missing one dropping the card (:827, :840). A hide sets aside the two cards the record chooses rather than draws, and a skip for 14 days, for the next post in the same ranking's order (`_set_aside` at :257). "Habits" in the report's sense, measured counts over the creator's own rows, are the engaged-with card's topic count and the Monday card | `tests/test_qc4_t7_local_cards.py` (23) | `test_no_second_ranking_of_posts_lives_in_the_section` reads the section's modules for an ORDER BY or a sort on a figure; falsified by planting `ORDER BY reactions DESC`. `test_the_other_persons_post_is_never_on_a_card` reads for a SELECT of `target_author` or `target_excerpt` and proves itself on a planted one. The set-aside rule: with its two checks removed, four tests failed. The playbook rule: with "half the words" set to one, the one-word test failed |
| 5 | Daily job | 6509ae1 | `studio/backend/record_daily.py`: the input signature (:98); Telegram ideas become asks (:126); the open slot's card (:197); `run_today`, read and build first, then one short `BEGIN IMMEDIATE` write, carried forward with "Nothing new since" when the signature has not moved, the dated slot and the Monday card drawn for the day (:260, :241); pruning that never removes a day a mark or a draft refers to (:345); the hourly job on the maintenance turn, tried again next hour when it is busy (:382, :392), registered a minute after start (`studio/backend/scheduler.py:736-755`); the screen's read, a SELECT (:434) | `tests/test_qc4_t7_daily_job.py` (14) | `test_the_job_never_calls_a_model` reads the job's imports for the model stage with a regex proven on a planted import |
| 4, 6 | The section screen; asks | 26e3729, 7432730, e9b9351, 2368277 | `studio/ui/src/components/RecordSurface.tsx` (one view: the Monday strip :212, the five slots :227, the ask box :284, Kept :238, the model's first-open request :72, read again only when the window comes back :83, the dropped-card line :148); `RecordCardView.tsx` (the label words :32, Why this?, the five actions, the playbook line :119); `RecordKnowsPanel.tsx` (asks to edit, retire or remove, the marks and Unhide all :135, the archive counts, how long batches are kept :164, the daily batch); `RecordSetupFields.tsx`, in Setup (`OnboardingSurface.tsx:342`) and on What the studio knows; the Composer's tick (`PromptPanel.tsx:410`); the store (`studio/backend/record_store.py`: asks from explicit acts only :56 and :88, Setup's three fields :115, marks :220 with what each does to each kind of card :243, More of this :287, Draft from this :311, Kept :338, settings :375, What the studio knows :435); the routes (`studio/backend/routers/record.py`, the ask route accepts only the box and the tick :162). Setup's delete confirmation names the section's rows (`OnboardingSurface.tsx:775-779`). After the measurement: the level reads "Today's cards", not a second button named Today | `tests/test_qc4_t7_asks_and_marks.py` (18); `tests/test_qc4_t7_record_browser.py` (4, Playwright: the day's cards in one view with their labels, a keep reaching Kept, an ask reaching What the studio knows, no sideways scroll on a phone) | |
| 7 | Model stage (decisions 7, 8, 9) | 734b4d2 | Structured outputs in the gateway's request builder for every family: OpenAI-shaped `response_format` with a strict JSON schema, Anthropic `output_config.format`, Gemini `responseMimeType` and `responseJsonSchema` with what it does not document stripped (`studio/backend/agno_agentos/model_gateway.py:668-760`, `execute_structured_completion` at :887); an unstructured request is byte for byte what it was. `studio/backend/record_model.py`: the dated price table and provider statements (:102, :117); the digit filter in any script with "times" and "percent" (:140); the allowlist redactor (:182); the creator's habits in words and who they are, on the voice pack's own readers (:225, :253); the bundle (:259); the schema of ids, closed angles and short phrases (:349); the preview of exactly what would be sent (:379); the ceiling, estimated before the call, $0.10 a day by default (:588, `record_store.py:63`); the first-open run, at most two calls a day (:486, :80); verification that drops, never repairs, an idea citing a row not sent or gone, quoting words not in the post, carrying a number or a name, or past 160 characters (:634); the Creator tier once `BETA_OPEN` closes (:444) | `tests/test_qc4_t7_model_stage.py` (25 functions, 47 cases) | `test_a_number_planted_in_the_models_answer_never_reaches_the_screen` plants digits, a percentage and number words in the fake provider's answer; `test_the_number_guard_is_what_stops_it` switches the filter off and the planted digit reaches the screen |
| 8 | Evaluation harness | 883a81c, e9b9351 | `studio/backend/record_evaluation.py`: shares under the sample rules (:70); the funnel by kind and by label, without the Monday line, which has no buttons (:84, :60); the comparison at about 48 hours against the creator's other posts of the same 90 days, abstaining under 8 a side and when the posts could not show less than a doubling (:199); the three monthly templates (:240); the note. `tools/backtest_record.py`: month by month on a read-only copy, using only rows observed before the month, stability, foresight, resurfacing and the model's validity, tuned on one year and read on the others; the report holds no text, id or name (format documented in its docstring) | `tests/test_qc4_t7_evaluation.py` (11) | The Monday exclusion: with `UNMARKABLE` emptied, its test failed |
| 9 | Signed bundle (decisions 10, 11) | 214c8de | `studio/backend/library_bundle.py`: the ILB1 format (:59), the committed public key (:69), verification where the key that verifies must be the key the content names (:116), validation that refuses anything but the company's own forms, patterns and examples, any other author and any LinkedIn link (:154), a table of its own (:215), the fetch under `library`, `_egress.require` in the same function as `urlopen` (:259, :283-284), sending the address, a User-Agent and the held copy's tag and nothing of the creator's; import from a file (:312); matched on the device to the creator's topics (:344). `tools/library_bundle.py`: a new keypair written outside the repository and refused inside it, signing and verifying, the format documented. `intelligence_sync.py` and its two test files are deleted; the hook forms it held moved verbatim to `studio/backend/hook_forms.py`; its three routes are gone | `tests/test_qc4_t7_library_bundle.py` (15) | The existing egress chokepoint test failed on the first version, which opened the URL in a helper; the fetch now names the category in the function that opens it. A changed byte, an unlisted key, the old unsigned shape and a key naming another all refuse |
| H | The help and the references | 5650ec2, 9c690cc, 7d27b22, and in each batch above | `docs/help/find-what-to-write-from-your-own-record.md`, filed under Write and publish (`studio/backend/docs_engine.py:623-624`); the first-run rail table's row; the Prompt tab article's tick; the API reference's section 9, which documented the sync's two routes, now documents the library's (`docs/API_REFERENCE.md`), found by the full suite | `tests/test_docs_library.py`, `tests/test_qc3_t7_sections_removed.py` (the rail table names only sections the rail has), `tests/test_qc2_r2_route_surface.py::test_the_api_reference_documents_only_routes_that_exist` | |

The PRD's done-when, each held by a test: a creator with an archive and no key
sees a non-empty, labelled section on day 0
(`test_day_zero_with_an_archive_fills_the_section_and_abstains_on_what_worked`);
"what worked" abstains in words (`test_what_worked_abstains_in_words_below_the_engine_minimum`);
no number on the screen came from a model (the planted-digit pair above); every
cited row exists (`test_a_card_citing_a_missing_row_is_dropped`,
`test_a_row_that_is_gone_by_the_time_the_answer_arrives_is_dropped`); the marks
persist and Kept reads from them (`test_kept_reads_from_the_keep_marks_and_hides_what_is_hidden`,
the browser test); the job never runs a model on screen load
(`test_reading_the_section_and_the_daily_job_never_call_the_model`); the
policy's two tests pass with the new sentences.

## The fourteen decisions, as built

| # | Decision | Where |
|---|---|---|
| 1 | The name and the three blocks | `record_cards.py:99`, the rail entry |
| 2 | Third in the Now group | After Today on this branch's flat rail; the group and Replies are track 4's, at merge |
| 3 | Library absorbed as Kept | `record_store.kept` (:338) reads the keep marks; the Kept level |
| 4 | Review deferred; Monday counts only | `record_cards.monday_card` (:860), compared with nothing |
| 5 | Explicit asks only | `record_store.py:56`; the route takes only the box and the tick (`routers/record.py:162`); Telegram and ticked searches through the job |
| 6 | Search Queries behind a tick, off | `archive_import.py:246` |
| 7 | The model on first open | Asked once per mount from the screen (`RecordSurface.tsx:72`), as its own POST; never by the job or a read |
| 8 | Tiers | Stage 1 untiered; stage 2 `licensing.allows("ai")` (`record_model.py:444`) |
| 9 | $0.10 a day, editable; no Batch option | `record_store.py:63`, `record_model.py:588`; the providers' batch interfaces are not used |
| 10 | The unsigned sync deleted | `intelligence_sync.py` and its tests gone; `library_bundle.py` new |
| 11 | Company-authored content only | `library_bundle.validate` (:154) |
| 12 | The web route designed, not built | Below |
| 13 | No notifications | Nothing notifies |
| 14 | Five slots, unpadded; Monday on | `record_cards.SLOTS` (:71); an abstention is a sentence, never another card |

## One-view measurement

Measured the way cycle 3 measured its sections (`CYCLE3_2026-10_PRD.md:56-57`)
and track 3 measured its own: ink is the share of the first 1440x900 viewport
of the work area covered by text, controls and drawn marks, sampled on a 6 px
grid; scroll pages are the work area's height in viewports. The data is three
invented years built for this measurement: 1,417 posts, 14,264 readings, 44,000
outbound rows (13,000 of them comments), 2,222 archive records, 15 asks, the
Docs index as the studio builds it at start, and the last 120 days of batches
built by the daily job itself, with marks on about a third of the days and 40
drafts from cards, 32 of them posted. No provider is connected, and nothing
left loopback. Taken on the final tree.

| View | Scroll pages | Ink | Characters | First view |
|---|---|---|---|---|
| Today's cards | 1.08 | 46.5% | 4,498 | the title, Working for you, You asked, You engaged with, the fifth card and the ask box |
| Kept | 1.00 | 34.5% | 2,820 | all |
| What the studio knows | 1.95 | 29.6% | 2,627 | all but Your marks and Your own model, which are the second viewport |
| Did these help? | 1.00 | 26.3% | 2,002 | all |

The same in both themes. The first paint reads 19,021 bytes of API, 16,175 of
them the day's batch. Each of the section's routes, one warm call then ten:

| Route | Median | Worst | Bytes |
|---|---|---|---|
| `GET /api/v1/record` | 8.2 ms | 8.5 ms | 16,175 |
| `GET /api/v1/record/knows` | 15.0 ms | 16.0 ms | 7,492 |
| `GET /api/v1/record/kept` | 4.3 ms | 5.0 ms | 16,688 |
| `GET /api/v1/record/evaluation` | 7.7 ms | 8.6 ms | 3,360 |
| `GET /api/v1/record/days/{day}` | 4.6 ms | 6.5 ms | 12,915 |
| `GET /api/v1/record/setup` | 3.2 ms | 3.9 ms | 103 |

The daily job built each of the 120 days in 78 ms median, 103 ms at worst, and
today's in 94 ms. `tools/backtest_record.py` ran over the same three years in
1.7 seconds; on invented data its shares show only that it runs.

What the measurement changed (e9b9351, 2368277): Did these help? showed the
funnel by kind only, and now by label too; the Monday line was counted as a
card shown and never acted on; with neither a provider nor the library, the two
panels said the fifth card waited for each other; the open slot and the model's
card had two headings; the daily batch printed its date twice; and the level
button named "Today" sat beside the rail's Today button with the same name.

## Interface audit

`tools/ui_audit.py` on a fresh install: 52 screens (every section, both themes,
desktop and phone), no console error, no egress, no failed API call, no axe
violation, no sideways overflow. On the three invented years, the section's own
screen: 4 of 4 the same. The audit opens a section's first view, so the other
three views were swept with the same axe-core and the same call, in both themes
at both widths, with every Why this? open: 16 of 16 with no violation, no
overflow and no request off loopback. Then again with a local provider
configured and its stage off, the preview of what would be sent shown, and an
ask that meets the playbook, so the You asked card carries its playbook line
and link: 16 of 16 the same. Followed from the card, the link opens Docs on the
playbook at that section.

## Stage 4: the web route, designed and not built

Decision 12 keeps it out of this cycle, and the report marks it as the one
shape the terms, LinkedIn's robots.txt and the review evidence all expose. If
it is ever built, it is built like this, and only after a legal review.

**What it is.** On a You asked card, a button that sends that ask, and nothing
else, to the creator's own provider's web search, and shows what the provider
cites. It is never run by the daily job, never on a screen load, and never for
an ask the creator did not press it on.

**Its egress.** A new category, `search`, with its own flag defaulting to
refused, like `linkedin`, because it differs from `model` in kind: the payload is
the creator's idea text, a third party beyond the provider (the search index)
receives a query derived from it, and the answer carries other people's
content. Each call asks first, naming the provider, the exact query and the
cost ("Send this idea, 'hiring without a recruiter', to OpenAI web search?
$0.01 plus tokens"); three a day at most; a ledger line with the destination
host and the query; listed on Brand Studio's Local security tab. `egress.require`
sits in the same function as the request, as the chokepoint test demands.

**What it renders.** Only the provider's own citation objects: OpenAI's
`url_citation` annotations, Anthropic's `web_search_result_location` with its
`cited_text` of up to 150 characters, Google's `url_citation` with the Search
Suggestions it requires, Perplexity's title, url, snippet and date. The model's
own prose is discarded. The card is labelled "retrieved", with the provider and
the query, and fills the open slot for that day only.

**What it keeps.** Other people's posts do not belong in the database
(migration 2's reason), so a row keeps the URL, the title, the provider, the
query, the date and the creator's mark, and nothing of the snippet, which is
held for that day's display only. The page behind a URL is never fetched, which
LinkedIn's 8.2 and Google's prohibition on using links to find pages to crawl
both require. Google allows grounded text to be kept for up to two years but
not cached, analysed or trained on, and shown only to the person who asked;
OpenAI and Anthropic require visible, clickable citations.

**What it could find.** LinkedIn's robots.txt disallows PerplexityBot,
ClaudeBot, GPTBot and anthropic-ai, and does not disallow Googlebot, Bingbot or
OAI-SearchBot on `/posts/` and `/pulse/`, so only Google's coverage of public
posts is self-evident; which index the other providers use is undocumented. A
provider with no web search (a local model, Groq, an endpoint of the creator's
own) gets no button, not an error.

**What it costs** (the report's figures, as documented on 2026-10-26): about
$0.01 a search on OpenAI or Anthropic plus tokens, $0.014 on Gemini 3 after
5,000 free a month, $0.005 on Perplexity ($0.001 fast). The daily ceiling holds
it, as it holds the model stage.

**The tests it would need first.** The category refused by default and by the
master switch; no call without that call's consent; the fourth search of a day
refused; no snippet column in the schema; no request to any cited URL (a
structural test over the module, like the chokepoint's); a rendered card built
only from citation fields, proven by planting prose in a fake answer; and the
policy and help naming it before the first row lands.

## Not done, and why

- **Batch 10, on-device embeddings.** Optional in the report. Not built: it
  needs an installer or download decision the report leaves open, and no
  throughput figure exists for the model it names.
- **Batch 11, the web route.** Decision 12; designed above.
- **A Health row for the daily job.** Health is track 4's section and does not
  exist on this branch. The job's state is ready for it (`record_daily.status`,
  `record_daily.py:499`) and is shown meanwhile under The daily batch on What
  the studio knows.
- **The Now group and Replies.** Track 4's; on this branch the rail is flat,
  and the entry sits after Today.
- **The batch keep rule in the storage panel's rules.** The panel lists the
  section's categories and their sizes; the setting itself (90, 365 days or for
  good) is on the section's own page, with its preview, and the daily job is
  what prunes, so there is one path that removes a batch rather than two.
- **The report's weekly grounded summary and model re-rank (stage 2).** Not
  built: decision 4 keeps Review deferred, and the report keeps a re-rank only
  if it beats the rule order on the backtest, which says so in its output.
- **A topic diversity rule across slots.** The report names it as one
  mitigation of self-imitation; the opener is drawn by its topic's share as the
  report's resurfacing rule specifies, and no rule across slots was specified.
- **Follows, votes and articles on a card.** Imported, counted on What the
  studio knows and carried by export and forget; no card uses them yet.
- **Replies answered on the Monday card.** It counts track 4's `reply_marks`;
  on this branch the table does not exist and the card says "not measured".
- **The provider shapes against live services.** The OpenAI, Anthropic and
  Gemini request shapes follow each provider's documentation and are tested
  against a fake gateway; none was sent to a real provider from here.
- **The library file itself.** No bundle is published at the default address
  yet, so Fetch answers that it was not found and may not be published yet.
  The company has to write the entries; the keypair exists, its secret half
  outside the repository, readable by the owner only.
- **The playbook's own claims.** The You asked card now links into
  `docs/strategy_playbook.md`, which states figures nobody measured ("determine
  80% of your post's reach") and names another product's engine. It is help
  content outside this track and was not edited; the card takes its section
  heading only.
- **A block on Today.** The brief allowed a small one; none was added. The
  rail entry sits directly under Today, which two other tracks change this
  cycle.
- **The policy's date.** "Last updated" is the coordinator's at release, with
  the version.

## Merge notes

- **The rail entry and the screen registry.** "From your record" declares
  `screenKey: "record"` (`navigation.ts:73`), and the registry has its row in
  the shape every section's row has, `"tab-record": {"key": "record", "label":
  "From your record", "owner": "DESIGNER"}` (`devtools.py:174`). Read with the
  logic of track 3's `tests/test_qc4_t3_screen_registry.py`, the entry is
  declared and registered both ways; the sections that still lack a key on
  this branch, and the two ghosts, are main's, which track 3 fixes.
- **The voice pack.** Identical to track 3's `voice_pack.py`,
  `tests/test_voice_pack.py` and `tests/test_qc_f2_disclosure.py` at cc78841;
  nothing of this track's is left in them.
- **The rail guard's count** goes from sixteen to seventeen with track 4's
  rail; this branch's own guard asserts the entry, not a count.
- **The migration** is `_migrate_record_section`, 28 here; renumber it after
  the others at merge. Its tests read its name, tables and columns.

## Lines touched outside this track's files

This track's own files are the importer, the gateway, the replaced sync module
(`library_bundle.py`, `hook_forms.py`), the new `record_*.py` modules and
`routers/record.py`, the migration, the new `Record*.tsx` components,
`navigation.ts`'s one entry, `voice_pack.py`, the help article, the two tools
and the new tests. Every other line it changed, by path and line in the final
tree (a "removed" entry names the line the removal sits at):

- `docs/PRIVACY_POLICY.md:144-166, 192-195, 200, 205` (the asks store and the model stage; track 6 edits the Send to LinkedIn, Telegram and XLSX paragraphs) and `release/privacy.html:85, 90, 97, 102`, rebuilt from it
- `README.md:57-58`; `docs/API_REFERENCE.md:273, 275, 277-281` (section 9)
- `docs/help/choose-what-the-studio-keeps.md:14, 32-33`; `open-the-studio-for-the-first-time.md:65`; `run-an-instruction-on-your-draft.md:22-23`; `set-up-the-studio-from-your-linkedin.md:63-64, 133`; `what-leaves-this-machine.md:10, 16, 19`
- `studio/backend/agno_agentos/__init__.py` removed at 11, 18, 29, 38; `agents/__init__.py` removed at 4, 10; `agents/swipe_harvester_agent.py` deleted; `contracts.py` removed at 113; `orchestrator.py` removed at 24, 29, 104; `registry.py` removed at 51
- `studio/backend/app.py:70, 142, 203`, removed at 1744, `1914-1921, 2750-2752, 2772, 2775-2780`
- `studio/backend/database.py:242-243, 331-336`; `schema_baseline.json` removed at 70
- `studio/backend/devtools.py:174`; `docs_engine.py:623-624, 713` (the help article, and this record under maintainers); `onboarding.py:837-840`; `retention.py:253, 261-267`; `routers/search.py:27, 42, 300`; `scheduler.py:736-755`; `support.py:106-110`; `updates.py:4, 248-249`
- `studio/ui/src/App.tsx:13, 682-696, 1026-1035`; `components/OnboardingSurface.tsx:28, 339-344, 775-779`; `components/PromptPanel.tsx:4, 303-306, 318-323, 402-412`; `lib/api.ts:3266-3568` (appended)
- `tools/ui_audit.py:59`
- Tests: `test_agno_agentos.py:42`, removed at 27, 46; `test_byo_ai.py` removed at 43, 48; `test_connection_hygiene.py:40-41, 117`; `test_day03_prudent_handoff.py:27-28, 119, 133, 135-140, 147, 153, 160-161, 163`, removed at 148; `test_devtools.py:128-130`; `test_endpoint_reachability.py:250-286`; `test_milestone2_days05_08.py:24-25, 90, 92-97, 99-102, 162`; `test_multitenancy_accounts.py:243-262, 265-267`, removed at 263; `test_package_importability.py:44-45`; `test_prototype_sweep.py:82-85, 87-88, 90, 97-99, 106-110, 112, 115-117`; `test_qc2_r6_starter_hooks.py:26, 57, 73, 76-80, 84, 89, 91`, removed at 66; `test_qc3_t4_scheduler.py:74-76`; `test_qc3_t5_hook_rail.py:6, 33, 105`; `test_qc3_t7_sections_removed.py:27-34, 263, 265-267, 273, 275`; `test_qc_f2_disclosure.py` and `test_voice_pack.py`, both exactly as track 3's cc78841 left them; `test_silent_state_loss.py:102`; `test_surface_agreement.py:145, 147-149, 151-152, 154, 157-158`; `test_swipe_file_refactor.py:9-10, 24-25, 66, 96-102, 106-107, 109, 115-118, 124-125, 127`, removed at 110, 112; `test_universal_search.py:164, 166-169, 171-172, 175-180, 182, 184`. `tests/test_intelligence_sync_hardening.py` and `tests/test_intelligence_sync_host.py` are deleted with the module they tested (decision 10)

Each test edit follows the code it tests: the retired routes answer 404, the
hook forms are read from `hook_forms`, the reachability ledger counts the new
routes and the three that left, the scheduler's job list includes the daily
batch, and the registry's screen count is nine.
