# The Data Architecture of Inox Hydra

> **Status:** assessment, 2026-09-21. Nothing in this document has been implemented.
> It records what the system captures today, what it only appears to capture, and the
> order in which to repair that. Read section 9 first if you are here to start work.

## How this was produced, and how far to trust it

Six independent audits of the pipeline (capture, storage, correlation, surfacing,
untapped surface, modeling), each claim then handed to a separate agent instructed to
refute it against the source. Thirty-two claims survived. Three were killed and are not
repeated here:

| Killed claim | Why it was wrong |
|---|---|
| The two lead writers leave the same person stored as two half-identified records | The column disjointness is real, but the fallback at `crm.py:336` resolves by name and company, so the duplicate-identity conclusion did not hold |
| The 17 seeded drafts are unreachable from any screen | Every seed double-writes the same content into `posts` twelve lines later (`database.py:432-435`), so the content is reachable |
| The lead dossier is labeled with a cloud model's name though f-strings produced the text | The orchestrator does route to a real model for some fields; only the three enrichment fields named in W10 are template output |

One verifier (on the untapped lens) failed with an API error and its claim carries
single-agent confidence rather than verified confidence. It is marked where it appears.

Four findings were additionally reproduced by execution rather than by reading, and are
marked **[reproduced]** in the text below:

- `parseInt("1.2K")` returns `1`. Run against the shipped expression.
- The live `analytics_daily` table is 100 percent synthetic. Proven by matching the
  generator's arithmetic to the stored values: `2330 + 90/3 = 2360` followers,
  `70 + 90/5 = 88` profile views, `base_date = 2026-09-14`, all three exact.
- `lead_interactions.post_id` is populated on 0 of 842 rows; `post_urn` on 336, all of
  which hold one of two test fixtures and join to nothing.
- 225 leads carry exactly one real profile URL. 213 have a NULL urn, which the partial
  unique index at `database.py:296` does not constrain, so duplicates accumulate
  ("Status Validation Test" appears 22 times).

A fifth hypothesis was **disproved** by execution and is recorded so it is not raised
again: the extension sends `interaction_type: "COMMENTED"` while the schema permits only
`'COMMENT'`, which looks like total data loss and reproduces as an `IntegrityError` when
`crm.ingest_interaction` is called directly. It is not a live defect. The route normalizes
at `app.py:1888` before the CRM sees it. The real finding is narrower: the validation lives
in the route rather than the model, so that function is unsafe for any second caller.

---

# THE LINKEDIN STUDIO: A HOLISTIC ASSESSMENT

---

## 1. THE THROUGH-LINE

**This system never records what a fact is about.** Every observation it stores is missing the one dimension that would give it meaning: an engagement has no post, a metric has no window, a score has no outcome, and a row has no provenance.

That single structural absence generates nearly every confirmed symptom. A comment is captured with `post_id` and `post_urn` left NULL (`content.js:249-261` omits both; `crm.py:366-370` writes the NULLs), so three complete, correct, shipped subsystems return zero forever. A metric card showing a 7, 28, or 365 day aggregate is stamped onto today's calendar date (`content.js:116`) and then `SUM`ed across overlapping periods (`app.py:347`). A lead's fit score is written by exactly two lines (`crm.py:350`, `crm.py:361`), neither of which has ever read a reply, a meeting, or a conversion. And because nothing distinguishes a captured row from a seeded one, 90 days of modulo arithmetic (`database.py:1460-1526`) render identically to real telemetry.

The second-order consequence is what actually damages the user. When a fact has no subject, the query that needs it returns zero or nothing. A zero is indistinguishable from an empty state, and an empty state in a dashboard is embarrassing, so at some point a constant was typed in to fill it: `2412` followers (`app.py:384`, `app.js:4296`, `index.html:851`), `104` views, `"96% Safe"` (`app.js:4601`), `"18.4"` percent trend (`app.js:4544`), `"9.0 Vel (2.5x)"` (`app.js:3609-3610`). **The fabricated numbers are not a separate sin. They are the scar tissue over the missing dimension.** Fix the dimension and the constants have nothing to hide.

The engineering here is not careless. The migration ledger wraps each step in `BEGIN IMMEDIATE` with a SQLite-backup-API snapshot (`migrations.py:207-217`, `290-305`). Tokens are DPAPI-encrypted before touching disk (`vault.py:39-80`) and scrubbed from telemetry by a recursive key-folding sanitizer (`background.js:8-48`). The ICP formula publishes its own weights in its docstring (`crm.py:9-10`) and exposes per-factor contributions over an endpoint (`crm.py:157-210`). This is a codebase where the parts that were examined were built well. The broken parts are unexamined, not rushed, which means they are worth repairing rather than replacing.

---

## 2. WHAT ACTUALLY FLOWS IN

### 2.1 Fields that genuinely enter the system

| Field | Source | Mechanism | Fidelity |
|---|---|---|---|
| Commenter name, headline, profile URL, comment text | LinkedIn comment section on a post page the creator opened | DOM scrape, `content.js:163-191`, driven by `MutationObserver` at `content.js:271-274` | **Real.** No post identity. Company derived by splitting headline on `" at "` (`content.js:187`), so "Stripe" / "Stripe Inc." are two companies. In-memory dedupe keyed on `profile_url` alone, per tab (`content.js:158`) |
| Reactor name, headline, profile URL | Any `.artdeco-modal` or `div[role="dialog"]` anywhere on linkedin.com | DOM scrape, `content.js:196-227` | **Contaminated.** Selector falls through to bare `li` (`content.js:199`); gated only on an `/in/` link plus a 2+ char name (`content.js:201-209`). Hardcoded `engagement_type: "Liked"` (`content.js:223`) |
| Impressions, engagements, followers | Creator analytics metric cards | DOM scrape, `content.js:104-115` | **Truncated and mis-windowed.** `parseInt("1.2K")` returns `1` (`content.js:107`). Window is whatever the dropdown was left on, never captured. Runs only on a hard load of an `/analytics/` URL where injection wins a race against `load` (`content.js:91-95`, `manifest.json:41`) |
| Creator name, headline, vanity slug | `GET /voyager/api/me`, server-side, authenticated | `linkedin_client.py:411-436`, triggered from `background.js:146` | **Real, and it is an egress.** The user never initiated this request |
| `li_at`, `JSESSIONID` | `chrome.cookies` | `background.js:65-84`, 15 minute alarm at `background.js:54` | **Real.** Encrypted at rest (`vault.py:39-80`, applied `linkedin_client.py:141`) |
| Post text the creator authored | Studio composer | `app.py:583` | **Real, user-asserted** |
| Draft text from Telegram | Ingress bot | `ingress.py:259` | **Real, user-asserted** |
| Voyager request URL, status code, method | `chrome.webRequest.onCompleted` | `background.js:125-129`, `:135-139`, `:147-150` | **Real and worthless.** Three metadata fields, consumed by nothing (`linkedin_client.py:182-289` matches none of its keys) |

That is the complete list. Seven real sources, two of which are the creator's own typing, one of which is a stance violation, one of which is noise.

### 2.2 Believed to be captured, and is not

| Belief | Where the belief lives | Reality |
|---|---|---|
| Voyager response bodies are intercepted | `background.js:124,134,145` console strings; `DAY_02_IMPLEMENTATION_SPEC.md:92-94`; `DAY_03_IMPLEMENTATION_SPEC.md:82-86` | `onCompleted` exposes no body in any manifest version, and the listener is registered with no `extraInfoSpec` at all (`background.js:118-154`). No `debugger` permission, no MAIN-world injection, no fetch patch exists anywhere in `studio/extension/` |
| Per-post impressions, reactions, comments, shares | `posts` columns `database.py:113-116`; Post Leaderboard `app.py:495-501` | The only non-seed writer is `linkedin_client.py:269-286`, fed from `posts` / `feed_updates` / `elements` keys that no shipped client ever sends. Real published posts hold the `DEFAULT 0` from `app.py:583` and sort last under `ORDER BY impressions DESC` |
| Audience demographics | `/api/analytics/demographics` (`app.py:447`); user data export (`support.py:70-73`) | 18 hand-typed rows (`database.py:1630-1652`), deleted and refabricated at every boot when count < 14 (`database.py:1452-1453`, `app.py:174`). Writer at `linkedin_client.py:247-259` is unreachable from any extension sender |
| Viewer seniority | `background.js:135` handler named `profile_views_seniority` | Forwards `{url, statusCode, method}`. Never a seniority breakdown |
| Profile views | `linkedin_client.py:211` branch | Never fed by any live payload |
| Unique members reached | `database.py:95`, exported as a CSV column via `SELECT *` at `app.py:470` | Zero writers in the entire repository. Permanent `0` |
| Which post an engagement happened on | `crm.py:637-638`, `app.py:516-518`, `/api/v1/analytics/posts/{id}/leads` at `app.py:530` | NULL on every extension-written row. Non-zero only for three seeded demo leads (`database.py:1424-1427`), which is why it demos as working |
| Dwell time | `post_dwell_metrics.dwell_seconds` | Sits next to `reading_velocity_wpm REAL DEFAULT 220.0` (`telemetry_shard.py:84-92`). It is `word_count / 220 * 60`, an estimate, and it has no live writer either |
| When an engagement occurred | `lead_interactions.interacted_at` | `CURRENT_TIMESTAMP` at capture (`crm.py:370`). It records when the creator was browsing, not when the person engaged |
| Early engagement velocity | `viral_templates.velocity_score`, sorts the swipe file (`intelligence_sync.py:598`) | Hand-typed integers (`intelligence_sync.py:54-55`). The legacy migration at `migrations.py:77-89` selects real `likes_count`/`comments_count` and discards them for a literal `8.5` |
| Conversion | `conversion_rate_pct` (`crm.py:534`), funnel bar (`app.js:2996`) | `lead_status` is written by exactly two lines: `crm.py:357` hardcodes `'NEW'`, `crm.py:453` writes `'ARCHIVED'`. The UI writes `status` instead (`leads.py:192`). Structurally pinned at 0.00% |
| Tech stack and friction points of a lead's company | `/api/leads/{id}/enrich`, "Agno Autonomous Multi-Agent Engine" | Substring match on headline into a five-branch if/elif (`agno_agent.py:98-155`), defaulting unrecognized headlines to `"architects"` and confidently asserting Kafka + gRPC + ClickHouse. Enabling Gemini does not change these fields (`agno_agent.py:288-289,316-319`) |
| Reach forecast | `"High Reach"` / `"Suppressed"` (`app.js:2052-2062`) | Six client-side regexes with hand-picked penalties (`app.js:1856-2011`), never once compared against the impressions already in the database |

---

## 3. WHERE IT BREAKS

Ordered by consequence to the user. Three kinds: **WRONG** (the product asserts something false), **MISSING** (a dimension the write path never records), **NEVER SURFACED** (correct code that no screen reads).

### 3.1 WRONG: the product asserts things that are not true

| # | Defect | file:line | Consequence |
|---|---|---|---|
| W1 | 90 days of synthetic analytics generated by modulo arithmetic at every boot, with no marker | `app.py:174` -> `database.py:1446-1451,1460-1526` | Every chart, KPI, range pill, CSV export, and "What Changed" line is fiction on a fresh install. Worse: the table is DELETEd whenever it holds fewer than 60 rows, so a creator with 12 genuinely captured days loses them on the next restart |
| W2 | Fabricated reactors. Bare `li` inside any dialog on any LinkedIn page becomes a "Liked" lead | `content.js:196-227`, stored `crm.py:367-370` with NULL post_id | The creator DMs a stranger asserting an engagement that never happened. Once stored, a fabricated reaction is indistinguishable from a real one |
| W3 | `parseInt("1.2K")` returns `1`; `"1.5M"` returns `1` | `content.js:107` | Only creators under 1,000 impressions get correct numbers. `linkedin_client.py:197` then divides engagements by that `1`, producing engagement rates in the thousands of percent |
| W4 | Hardcoded metrics that fire exactly when the system knows nothing: `2412`, `104`, `"96% Safe"`, `"18.4"`, `"9.0 Vel (2.5x)"`, `2.2x` | `index.html:851,853`; `app.js:4296-4297,4544,4601,3609-3610`; `app.py:384-385` | `||` rather than `??` means a real creator with 0 profile views is shown `104`. `if (!posts.length) return;` at `app.js:4577` fires before `tbody.innerHTML = ""` at `:4579`, so two fake posts at `index.html:903-917` survive every failed fetch, including the window before the first fetch resolves |
| W5 | "High Reach" / "Suppressed": a distribution claim derived from six regexes | `app.js:1856-2011`, verdict at `:2052-2062`; hardcoded into static markup at `index.html:1585,1713` | An empty composer scores 100 and reads "High Reach" before the user types a character. A single bare domain in prose drops a post to 60 and "Suppressed", so the creator rewrites a good post to satisfy a lint rule |
| W6 | Every stored DM says "thanks for the comment on the sovereign creator architecture breakdown", including to people who did not comment | `content.js:259` -> `crm.py:239,238-242`, surfaced with a copy button at `app.js:4689` | For reactors, `content.js:258` ships the literal sentinel, so the DM reads `Your point about "Reacted to post on LinkedIn..." was spot on.` A second hardcoded topic exists at `leads.py:239` |
| W7 | Fabricated LinkedIn identity. When `profile_url` is absent, a `urn:li:person:` is minted from a JS string hash | `content.js:255` | A forged key in LinkedIn's namespace, accepted by the partial unique index at `database.py:296`, that will eventually collide |
| W8 | Non-deterministic lead IDs. `f"lead-{abs(hash(...)) % 1000000}"` | `crm.py:355` | Python string hashing is randomized per process, so the same person gets a different ID after every backend restart. Birthday collision around 1,200 leads |
| W9 | The extension causes an outbound authenticated LinkedIn request the user never made | `background.js:146` -> `app.py:1451` -> `linkedin_client.py:411-415` | Falsifies `DAY_03_IMPLEMENTATION_SPEC.md:87` ("exactly 0 additional HTTP requests"). A live `POST /voyager/api/contentcreation/normShares` also exists at `linkedin_client.py:634-668` |
| W10 | Fabricated company intelligence pasted into real DMs | `agno_agent.py:98-155`, duplicated at `agno_agentos/agents/crm_enrichment_agent.py:24-100` | Unrecognized headlines default to `"architects"` and receive a confident Kafka stack. Labeled "Company Intelligence" and "Enterprise Friction Points" at `index.html:2247,2263` |
| W11 | Every hook is labeled "Truncated", including fold-safe ones | `app.js:2244` reads `h.is_mobile_fold_safe`; backend emits `mobile_safe` (`repurposer.py:301,363`) | The one bit of real information in the hook generator is surfaced inverted |

### 3.2 MISSING: dimensions the write path never records

| # | Missing dimension | file:line | What it kills |
|---|---|---|---|
| M1 | **Post identity on an engagement.** `post_urn` and `post_id` absent from the CRM ingest body | `content.js:249-261`; accepted but unfilled at `app.py:1875-1876`; NULLs written at `crm.py:366-370` | Attribution (`crm.py:637-638`), the leaderboard join (`app.py:516-518`), and `/api/v1/analytics/posts/{id}/leads` (`app.py:530`). All three return zero forever |
| M2 | **Post identity on the creator's own post.** `posts` has no URN column | `database.py:106-120`; `scheduled_urn` minted at `linkedin_client.py:634,668` and discarded | Even if M1 were fixed, the URN on the interaction would have nothing to join to. `app.py:509-518` compares `posts.id` (local TEXT) to `lead_interactions.post_urn` |
| M3 | **Observation window.** `analytics_daily` keyed by `date TEXT PRIMARY KEY` with no period field | `database.py:89-91`; write at `linkedin_client.py:199-207`; read at `app.py:347` | A 28 day aggregate becomes today's impressions, and `SUM()` double-counts overlapping windows. No stored field could ever repair it, because the period was never recorded |
| M4 | **Outcome.** No entity, no table, no event | `crm.py:350,361` are the only writers of `icp_score`, and neither reads a reply, a meeting, or a conversion | Nothing in the product can learn. Every weight is frozen at whatever was typed on day one |
| M5 | **Provenance.** No column anywhere distinguishes observed / asserted / derived / seeded / default | schema-wide | W1 and W4 are unfixable as a class without it. Patched at the render layer, they come back |
| M6 | **Time dimension on demographics.** `(id, dimension, label, percentage)` | `database.py:125-131`; per-label delete-then-insert at `linkedin_client.py:254-258` | Drift is the only interesting thing about demographics and it is unrepresentable. A partial update can leave a dimension summing past 100 |
| M7 | **Idempotency.** No unique constraint on `lead_interactions`; dedupe keyed on `profile_url` in memory per tab | `database.py:300-312`; `content.js:158,179` | One comment becomes N rows across N page loads, and a person who engages on two different posts is captured once. Simultaneously over- and under-counting |
| M8 | **Draft to post link.** No `posts.draft_id` | `database.py:106-120` | `archetype`, `pre_fold_chars`, `is_pre_fold_safe` are real authored data (`database.py:238-242`) that can never be correlated with any outcome |
| M9 | **Engagement time.** `interacted_at DEFAULT CURRENT_TIMESTAMP` | `database.py:309`, written `crm.py:370` | Any timing analysis measures when the creator browses, not when the audience shows up |
| M10 | **Capture surface.** No record of which page region a row came from | `content.js` throughout | W2 is only enforceable with it, and W1 is only detectable with it |

### 3.3 NEVER SURFACED: correct code the UI does not read

| Asset | file:line | Status |
|---|---|---|
| `impressions_delta_pct`, a correct prior-window comparison | computed `app.py:378`, returned `app.py:403` | Read only by tests. `"delta_pct"` appears nowhere in `app.js`. The frontend fabricates `"18.4"` instead |
| `calculate_icp_breakdown`: per-factor weights, contributions, intent signals | `crm.py:141-211`, exposed `app.py:1964-1976` | No frontend caller. The best-designed thing in the repo is invisible |
| Real per-text safety scorer | `POST /api/format/algorithm-audit`, `app.py:1003` | No frontend caller, while `app.js:4601` prints a constant in a column headed "Audit Score" |
| FTS5 document search | `docs_engine.py` | Never queried by the frontend |
| `/api/v1/ingress/drafts` | `app.py:1811-1814` | Zero references in `studio/frontend/`. Drafts created via ingress (`database.py:1809-1834`, no `posts` mirror) have no list view |
| `audience_demographics` endpoint | `app.py:447` | No frontend fetch. The fiction reaches the user through `support.py:70-73`, the data export |
| Telemetry ring buffer contents | `telemetry_shard.py:152` | No non-test caller. Also not durable: flushes only at 25 staged events (`telemetry_shard.py:270-274`), with no timer and no shutdown flush (`app.py:178-180`) |

---

## 4. THE MODEL IT SHOULD HAVE

### 4.1 Nine entities

| Entity | Identity key | Grain, in one sentence with no conjunctions | Where it wrongly lives today |
|---|---|---|---|
| **Creator** | `person_urn` | One row per LinkedIn account connected to this install | Key-value rows in `settings` (`linkedin_client.py:421-436`). No row exists, so nothing can reference one |
| **Composition** | `composition_id` | One row per piece of text the creator is writing | Split across `drafts` (`database.py:234`) and `posts` (`database.py:106`), double-written by every seed (`database.py:433,498,562,...`), with two independent status vocabularies |
| **Publication** | `activity_urn` | One row per published LinkedIn activity | The `status='published'` half of `posts`, with no URN column at all |
| **Member** | `person_urn`, else canonical `/in/` slug, else a local unresolved id | One row per distinct LinkedIn person ever observed | The identity half of `leads` (`database.py:161`), where `crm.py:361` writes `linkedin_urn` and never `profile_url`, and `linkedin_client.py:324` does the reverse |
| **Engagement** | `(creator_id, activity_urn, person_id, engagement_type)` | One row per member per publication per engagement type | `lead_interactions` (`database.py:300`), with both post columns NULL, no unique constraint, and `post_id INTEGER REFERENCES drafts(id)` typed against the wrong table |
| **Relationship** | `(creator_id, person_id)` | One row per creator per member | The pipeline half of `leads`, split across `status` and `lead_status` |
| **Observation** | `(creator_id, subject, metric_key, window_kind, window_start, window_end, observed_at)` | One row per subject per metric per window per observation event | `analytics_daily`, with `date` as the entire primary key |
| **AudienceSlice** | `(subject, dimension, label, as_of_on)` | One row per subject per dimension per label per as-of date | `audience_demographics`, with no date and no subject |
| **Outcome** | `outcome_id` | One row per asserted result event per relationship | **Does not exist.** Closest surrogate is `leads.status='Meeting Booked'`, a mutable field invisible to every analytic |

Three edges do not exist and are the whole game: **Composition to Publication**, **Engagement to Publication**, **Relationship to Outcome**.

### 4.2 The grain table

| Fact | Grain the name implies | Grain actually written | Correct grain | Error class |
|---|---|---|---|---|
| `analytics_daily` | one row per calendar day | one row per date, overwritten, holding an aggregate over an unrecorded window, for an unnamed account | one row per creator per metric per window per observation | window collapse |
| `posts.impressions` etc. | lifetime counters for this post | never written by any live path | one observation row per post per metric per observation time | window collapse |
| `audience_demographics` | one row per dimension per label | same, with no time and replaced per label | one row per subject per dimension per label per as-of date | missing dimension |
| `lead_interactions` | one row per lead per post per interaction | one row per scrape-detection event per person, post NULL | one row per creator per member per publication per type | missing dimension |
| extension dedupe set | n/a | one row per person per browser tab (`content.js:158`) | the Engagement natural key | missing dimension |
| `leads` | one row per lead | identity plus pipeline state plus one engagement type plus free text | split into Member and Relationship | grain stacking |
| `leads.icp_score` | a score for this lead | a monotonic ratchet (`crm.py:342`), unversioned, never recomputed | one row per member per model version per computation time | grain stacking |
| `queue_slots` | measured peak windows | one row per hand-typed weekday and time string (`database.py:1661-1672`) | one row per creator per weekday per slot, with a `basis` field | advisory as measurement |
| `viral_templates.velocity_score` | measured early velocity | one hand-authored editorial rank (`intelligence_sync.py:54-55`) | `editorial_rank`, with `velocity_score` reserved | advisory as measurement |

### 4.3 The schema changes that get you there

All of these go through `migrations.py` as numbered migrations, never into `init_db` (which `database.py:262-297` already violates). The ledger is the best-built thing in the backend: per-migration `BEGIN IMMEDIATE` transactions, a too-new-database guard at `migrations.py:121-127`, and a real SQLite backup-API snapshot at `migrations.py:207-217`. Use it.

| # | Change | Unlocks |
|---|---|---|
| S1 | `ALTER TABLE posts ADD COLUMN activity_urn TEXT` + unique index | M2. Every attribution surface |
| S2 | `ALTER TABLE posts ADD COLUMN content_fingerprint TEXT` | Passive URN binding without depending on LinkedIn CSS classes |
| S3 | `ALTER TABLE posts ADD COLUMN draft_id INTEGER` | M8. Correlating authored form with outcome |
| S4 | `ALTER TABLE posts ADD COLUMN metrics_source TEXT DEFAULT 'none'` | M5 on the leaderboard. Makes mixed-provenance sorting refusable at the query layer |
| S5 | `UNIQUE INDEX ON lead_interactions(lead_id, post_urn, interaction_type)` + `ON CONFLICT DO UPDATE SET last_observed_at` | M7. Turns a re-scrape from a duplicate into a no-op |
| S6 | `ALTER TABLE lead_interactions ADD COLUMN capture_context TEXT` (path plus matched selector) | M10. W2 becomes both preventable and retroactively purgeable |
| S7 | `ALTER TABLE lead_interactions ADD COLUMN occurred_at TIMESTAMP` | M9 |
| S8 | `analytics_daily`: add `source TEXT`, `period_label TEXT`, `precision TEXT`, `captured_at TIMESTAMP` | M3, M5. W1 and W3 become visible instead of silent |
| S9 | `audience_demographics`: add `source TEXT`, `captured_on TEXT`; change the writer to per-dimension replace | M6 |
| S10 | New `post_features(post_id, feature_key, feature_value)` | The contrast engine |
| S11 | New `lead_outcomes(relationship_id, outcome_kind, asserted_at, engagement_id)` | M4. The only path to a product that learns |
| S12 | Collapse `leads.status` into `lead_status`, dual-write for one release, then drop | Unfreezes the funnel |

Two design disagreements resolved here. **The ontology track proposes a full rename and nine-table split; I am taking the additive-column path instead**, because a local-first single-user SQLite app with a good migration ledger gets 90 percent of the benefit from S1 through S12 and a nine-entity rewrite would stall the one change that actually matters. **The untapped track calls the attribution fix "one DOM attribute read"; it is two writes (S1 plus the ingest payload)**, because a URN on an interaction has nothing to join to until the creator's own post carries one.

---

## 5. THE VOCABULARY

**Prime directive: a name may only promise what the write path can deliver.** `analytics_daily` promises daily; the writer delivers whatever window was on screen. `velocity_score` promises velocity; the writer delivers an opinion. Both names are bugs, and both are load-bearing, because the next developer will trust them.

### 5.1 Retire or rename

| Term today | What it actually is | Verdict |
|---|---|---|
| "passively intercepted" (`background.js:124,134,145`) | request metadata observation | **Rename** to `observeRequestMetadata`. Keeping "intercept" guarantees someone plans another feature on a data source that does not exist. The DAY_02 and DAY_03 specs already did |
| "telemetry" (`telemetry_shard.py`, `/api/v1/telemetry/*`) | two different things sharing one name: app health, and captured third-party data | **Split.** This confusion is exactly why request metadata ended up in a ring buffer nobody reads |
| `velocity_score` (`database.py:322`) | an editorial rank | **Rename** `editorial_rank`. Reserve `velocity_score` for the day something measures it |
| `engagement_multiplier` (`"3.5x"`) | a TEXT column holding a number with a unit suffix and no baseline | **Delete** |
| `predicted_score` (`repurposer.py:302,364`) | `is_fold_safe` wearing a number, four possible values | **Delete.** "Predicted" must mean fitted to observed outcomes |
| "Reach Forecast" / "High Reach" / "Suppressed" (`app.js:2052-2062`) | a six-regex formatting checklist | **Delete the verdict, keep every rule.** Replace with "3 things to fix" or "Looks clean". The per-rule checks with one-click fixes are the most honest surface in the app |
| "Audit Score: 96% Safe" (`app.js:4601`) | a string literal | **Delete.** No defense |
| "Agno Autonomous Multi-Agent Engine" (`agno_agent.py`) | a keyword-routed template renderer | **Rename** `lead_brief_templater`. This name matters most, because a creator reads "inferred tech stack" and pastes it into a real DM |
| "Smart Slots" / "Tuesday Peak Hook" (`database.py:1661-1672`) | a default posting schedule | **Rename** `posting_slots` with `basis='default'`. The word "smart" is earned only when `basis='derived'` |
| "sovereign" (`app.py:1813,1877`; `crm.py:249`) | local-first, BYO-key | **Retire from identifiers.** It has leaked into a data value: `post_topic: "sovereign creator architecture"` (`content.js:259`) is now in every stored DM |
| "asymmetric intelligence" (`app.py:2081,2111`) | ETag-conditional template sync | **Retire.** Say the mechanism |
| "anti-slop" (`app.py:164,1946`; `crm.py:245`) | grounded generation | **Rename** `quote_grounded_dm`, and make the name enforceable: no verbatim quote available means abstain, not template |
| "Reverse CRM" (`app.py:164`) | inbound engagement capture | **Rename.** "Enterprise" is decoration on a SQLite file |
| "G-Stack" (`database.py:334`) | a review checklist with a `CHECK(role IN ...)` constraint pinned to a personality brand | **Rename** `work_items`. The constraint will outlive the brand |
| `leads.status` vs `lead_status` | two status columns, one entity | **Retire `status`.** This split costs the product its only outcome signal |
| four VIP thresholds: 80 / 75 / 70 / 60 (`crm.py:167,375,511,686`; `app.py:513,1914`) | a naming failure before it is a logic failure | **One constant, one module.** Two of the three seniority literals at `crm.py:686` are strings `classify_seniority` can never emit |
| `/api/` vs `/api/v1/` mixed throughout `app.py` | roughly 60 unversioned routes beside 30 versioned | **Pick `/api/v1/`, alias the rest** |

### 5.2 Keep

| Term | Why |
|---|---|
| `pre_fold_chars`, `is_pre_fold_safe`, `lines_above_fold` (`database.py:238-241`) | **The best-named columns in the repository.** Precise, observable, unit-bearing, boolean-prefixed correctly. This is the standard |
| "deterministic ICP scoring" (`crm.py:9-10`) | Honest, and the docstring publishing the formula is the single best naming decision here. Rename the field `fit_score_v1` and stop calling a question mark an "intent signal" (`crm.py:198-210`) |
| "swipe file" / `inspirations` (`database.py:135`) | Genuine creator-industry vocabulary, used correctly |
| `unique_members_reached` (`database.py:95`) | The distinction it encodes (reach vs impressions, and the frequency ratio between them) is the right one. Populate it or drop it |

### 5.3 Terms the product needs and has no name for

| Term | Definition | Why its absence caused a bug |
|---|---|---|
| **Observation window** | `window_kind` in {DAY, ROLLING_7D, ROLLING_28D, ROLLING_365D, LIFETIME}, plus start and end | Without this word `content.js` cannot even ask what period the number on screen covers. Highest-leverage single term in this document |
| **Provenance class** | observed / asserted / derived / seeded / default | Without it, `database.py:1460-1526` is indistinguishable from real capture |
| **Capture surface** | the page region a row was read from | The only thing that can constrain the reactor scraper, and enforceable at the API boundary rather than in `content.js` where it can be bypassed |
| **Coverage** | captured engagers divided by LinkedIn's own displayed reaction count | "This post generated 4 VIP leads" is misleading at 7 percent coverage and meaningful at 90. The ratio is free |
| **Survivorship bias** | conclusions from a sample that excludes failures | Four live instances: the swipe file holds only winners; reactor capture sees only the lazy-rendered prefix; analytics exist only on days the creator visited; and **the conversion denominator is unobservable**, since no row exists for the perfect-fit person who read and scrolled on. Any rate here is `reply_rate_among_engagers`, never `conversion_rate` |
| **Cold start** | data begins at install; backfill is impossible under the passive boundary | A user shown 90 days of pre-install history will assume backfill happened |
| **Watermark** | the latest point capture is believed complete | Distinguishes "zero impressions that day" from "we were not watching" |
| **Orphan engagement** | an engagement whose publication could not be identified | Under current code every captured engagement is one. Naming the state lets you count them, show them, and offer manual reattachment instead of returning a confident zero |
| **Model version** | the rules that produced a stored score | Store `score`, `model_version`, `computed_at` together or do not store the score |
| **Abstention / minimum-n** | the threshold below which the honest output is a count and a prompt | Every scorer here emits a point estimate for any input with no floor |
| **Advisory vs measurement** | a two-value classification every displayed number carries | Most of this product's credibility problem is advisories typeset as measurements |
| **Egress** | any HTTP request to LinkedIn the creator's browsing did not already cause | A counted, test-asserted `egress_count` is the only way the passive boundary stays real. It is already crossed at `background.js:146` |

---

## 6. WHAT TO BUILD

### 6.1 Capture work, in dependency order

| ID | Capture | Mechanism | Prereq | Size |
|---|---|---|---|---|
| **C0** | Record the post at the moment of injection | `sidepanel.js:85-113` currently writes nothing to the server. Add `POST /api/posts/{id}/mark-injected`: set `published_at`, store `content_fingerprint`, arm URN capture in `chrome.storage.session` | S1, S2 | 2-3 d |
| **C1** | Bind the activity URN passively | Primary route: when `location.pathname` matches `/feed/update/(urn:li:activity:\d+)` and an armed fingerprint prefixes the page's post text, bind. Depends on no LinkedIn CSS class. Secondary: ancestor update card; tertiary: fingerprint match on any feed card | C0 | 3-4 d |
| **C2** | Stamp post identity on every engager | Add `post_urn` and `post_id` to the body at `content.js:249-261`. **The backend needs no change**: `app.py:1875-1876` already accepts both and `crm.py:366-370` already stores both | C1 | 1 d |
| **C3** | K/M suffix parse plus precision flag | Replace `parseInt` at `content.js:107`; store `1200` with `precision='rounded'`; reject unparseable rather than coercing | S8 | 1 h |
| **C4** | SPA navigation trigger | A URL watcher re-running the extractor when the path becomes `/analytics/`. Today it hangs off a `load` listener inside a guard evaluated once at injection (`content.js:91-95`) | none | 1 h |
| **C5** | Period label | Read the range selector text beside the metric card; write `period_label`. Never write a non-`1d` aggregate into a daily row | S8 | 1 h |
| **C6** | Capture context plus reactor scoping | Record path and matched selector on every interaction; drop the bare `li` fallback at `content.js:199`; require a post-detail path | S6 | half day |
| **C7** | Real engagement time | Parse the relative stamp ("2h", "1w") into `occurred_at` | S7 | half day |
| **C8** | Per-post metrics | Scrape the creator's own single-post analytics view, keyed by URN. Brittle, and the only path to a real per-post engagement rate | C1, C3 | 3-4 d |
| **C9** | `unique_members_reached` | Two edits: a branch in `content.js:109-111`, plus the normalizer and **both** INSERT column lists at `linkedin_client.py:201,221`, or the value is silently dropped server-side | C3 | 2 h |
| **C10** | Real demographics | Scrape the Audience tab; `ingest_analytics_payload` already accepts exactly this shape. Remove the boot delete-and-reseed first | S9 | 1 d |

**C0, C1 and C2 are one unit.** None does anything alone. Together they are the difference between a CRM full of strangers and the sentence this product was built to say.

### 6.2 Dashboards, by what they need

| Dashboard | Question it answers | Needs | The action it produces |
|---|---|---|---|
| **The Desk** (side panel, not a tab) | Who arrived, who do I reply to, is the system blind, did I publish? | nothing for 4 of 5 elements | Reply to 3 people in ICP order, using their own words |
| **D1 Post to People** | Which posts brought people worth talking to? | C0+C1+C2 | Write the sequel to the post that produced senior engagers |
| **D2 The Room** | Who have I not answered? | nothing. The only fully-fed surface today | Reply to the unanswered; mine verbatim comments for the next post's topic |
| **D3 What Works For Me** | Which of my habits correlate with good engagers? | C2, C8, S3, S10 | Keep or drop exactly one habit, with n visible on the same line |
| **D4 Who Shows Up** | Is the room I attract the room I wanted? | nothing (built from engagers, not `audience_demographics`) | Change the topic, or decide the room is the point |
| **D5 Rhythm** | Am I actually publishing? | nothing for the cadence strip | Publish into the empty weeks |
| **D6 Data Health** | Is any of this real, and what do I do about it? | nothing. **Richest on day one** | One click to fix the biggest blind spot, one click to purge the fiction |
| **D7 Reach** | Do I have enough measured days to trust any rate here? | C3+C4+C5 | Calibration: if coverage reads 3 of 60, no rate on any screen is trustworthy this month |

**The Desk lives in the Chrome side panel, not the Studio tab.** The dashboards track and the roadmap track disagree on this; the side panel wins because it is visible exactly when the creator is on LinkedIn, and the Studio tab requires them to go somewhere they were not already going.

### 6.3 The honesty layer, built at the data layer

Four provenance states, with one governing idea: **measured looks plain.** Trust is the absence of marking, so the eye learns to read ornament as doubt.

| State | Visual |
|---|---|
| MEASURED | full-contrast ink, tabular numerals, no ornament. The only state that looks normal |
| DERIVED | ink figure plus a dotted underline that opens the formula and the n |
| SAMPLE | hatched, italic, lighter weight, undismissable chip. Never the same size as measured |
| UNKNOWN | an em-dash and the capture that would fill it. **Never a fallback number** |

Three mechanisms make it stick rather than drift back within two sprints:

1. **The API returns objects, not scalars.** `{value: 1200, provenance: "measured", precision: "rounded", n: 7, as_of: "2026-09-18", period: "7d"}`. A bare numeric in a stat field fails a contract test.
2. **The HTML skeleton contains no digits.** Every `[data-stat]` element ships containing only an em-dash; a lint test greps `index.html` for digit-bearing text nodes inside stat containers and fails the build. That kills `314`, `1,240`, `94`, `96% Safe`, `2,412`, `104` at the root instead of one at a time.
3. **`??`, never `||`.** `Number(data.profile_views || 104)` at `app.js:4297` shows a creator with a truthful zero the number 104.

Sample-size rules: at n of 1 to 4, **no aggregate is computed at all**, show the rows. At 5 to 19, tilde-prefixed, denominator inline, all deltas and rankings suppressed. At 20 or more, full treatment, denominator still visible. No p-values, no confidence intervals, at any n. A creator cannot act on a CI; they can act on "this rests on seven posts."

---

## 7. WHAT TO LEARN

| Approach | Verdict | Reason |
|---|---|---|
| **Training a model** | **No. Never, at this scale.** | A fitted model with four predictors needs roughly 40 outcome events. A solo founder yields 5 to 20 conversion events a year. Any model fitted here memorizes noise and then speaks with authority |
| **Multi-arm ranking** (8 hook archetypes, 10 day-by-slot cells) | **No.** | 25 posts per arm against LinkedIn's roughly log-normal engagement needs 60 to 100 per arm. A solo creator reaches that in year three, by which point their audience has changed and the comparison is invalid. Ten timing cells at ~20 posts each are hopelessly confounded with topic and never separate |
| **Binary contrasts** | **Yes. Exactly three.** | Question CTA present or absent; media attached or not; pre-fold at most 140 chars or more. Two arms, roughly 100 per arm after a year, detects about 40 percent relative differences. Outcome metric is **qualified engagers per post**, not engagement rate, because engagers need only attribution while rate needs measured impressions |
| **Descriptive rates** | **Yes, once the Outcome table exists and n is at least 30.** | "Of 34 VIP-tier engagers, 6 replied (18 percent)" is a real statistic, trustworthy, and needs no model. This is the honest substitute for propensity |
| **Retrieval into an LLM** | **Yes. The single highest-value unbuilt LLM application here.** | Pull the creator's top 5 and bottom 5 published posts by qualified-leads-per-1k-impressions, exact text and exact numbers, plus the new draft, and require three specific edits each citing one of the creator's own post ids. Works at n=10, improves monotonically with every post, grounded in the creator's real voice. Every input already exists in the query at `app.py:495-500`, and **no prompt in the codebase consumes it** |

### The minimum viable feedback loop

Four writes and one question. Nothing here requires a fetch.

1. **Injection writes identity.** `posts.published_at` plus `content_fingerprint` at the moment the side panel types into LinkedIn's composer (C0).
2. **A page visit binds the URN.** The creator clicks through to their own post once, which they wanted to do anyway (C1).
3. **The scrape stamps the URN.** Two keys added to an existing payload (C2). Qualified-engager count per post now exists, and it arrives **without an analytics page visit**, which matters because analytics visits are weekly at best and comment scrapes are daily.
4. **One tap on Monday.** Three values only: replied, no reply, not yet. Maximum three leads asked about per week. Writes `lead_status`, the column the funnel actually reads.

That is the entire loop. Month 1 the composer panel abstains on everything and says so. Month 3 two or three contrasts fire with n at least 8 per arm. Month 12 it argues from a hundred of the creator's own posts and a real ledger of who converted. **The switching cost after six months is that ledger, and it exists nowhere else.**

---

## 8. THE RITUAL

The product today has capture and display and **no voice**. It never initiates. That is the actual week-two churn mechanism, ahead of every data defect, and it deserves equal weight.

The software cannot fetch. So the ritual's real job is to route the creator's existing browsing across the four surfaces that contain the data: their own post detail page, their own comment section, their notifications, and their creator analytics page. Every prompt must be something they would plausibly want to do anyway.

**Triggers are events, not clocks.** A 7am timer fires into an empty room. "Creator opened linkedin.com" is always observed and always well-timed.

### Daily

| Step | Trigger | What happens | Why it is also capture |
|---|---|---|---|
| 1 | First linkedin.com load of the day | Side panel opens to one card: one ready draft with its mechanical checks, or three hooks from `/api/format/re-hook` (`repurposer.py:237`). Never blank, never more than three options | none |
| 2 | Creator clicks Inject | **The load-bearing event.** Writes the posts row, the fingerprint, arms URN capture. Card flips to "Posted 9:12am. I'll watch for engagement." | C0 |
| 3 | Next LinkedIn load 60+ min after an armed post | One in-page toast (`content.js:67-84`): "Your 9:12 post is live. 14 people engaged. Open the comments and I'll pull the senior ones out." | **The button opens their own post detail page, which is exactly where `location.pathname` yields the URN and the comment section is scrapeable. The prompt the creator wants and the capture the product needs are the same click** |
| 4 | Post-page scrape completes | Three named people, real headlines, their actual sentences, a Draft replies button | C2 pays off |
| 5 | Evening | **Nothing.** Deliberately. A second daily touch is where this class of product dies | |

### Weekly

| When | Card | Ask |
|---|---|---|
| Monday, first LinkedIn open | "You posted twice. 31 people engaged, 6 senior. Your Tuesday migration post produced 5 of the 6. Your Thursday hiring post produced 0, at 4x the reactions." | One question, one tap: "Did you message Priya?" replied / no reply / not yet. **This is the only configuration the product will ever ask for, and it is the outcome signal that closes the loop** |
| Friday, first LinkedIn open | "Your impression numbers are 6 days old. 30 seconds on your analytics page and I'll catch up." | Honest framing: the product tells the creator it needs them to walk past the window, because it will not open the window itself |
| Cadence guard, only when true | Tray balloon, once, not repeated: "9 days. Your last three posts all landed Tuesday mornings." | none |

Four asks per week. Three of them are things the creator would have done regardless.

---

## 9. THE SEQUENCE

### FIX (days). Everything here is something the product currently does that is untrue.

| # | Change | Files | Prereq | Test of success |
|---|---|---|---|---|
| **F1** | Gate all metric seeding behind an explicit demo flag. Delete every numeric fallback. Remove static fake rows. Move `tbody.innerHTML = ""` above the early returns | `database.py:1446-1526,1630-1657`; `app.py:174,384-385`; `index.html:851,853,903-917,1585,1713`; `app.js:4296-4297,4544,4574-4579,4601` | none. **Ship Monday** | Boot against a fresh DB: `analytics_daily` row count is 0; grep finds zero occurrences of `2412`, `104`, `96% Safe`, `18.4`, `314`, `1,240` outside the demo branch |
| **F2** | Cut the outbound LinkedIn call. Remove `syncActiveSessionToStudio()` from the interceptor and the alarm's server-side fetch. Delete the live `normShares` POST | `background.js:54-58,143-151`; `linkedin_client.py:349-451,634-668`; `app.py:1448-1457` | none | A stubbed HTTP client fails the test on any outbound call to linkedin.com from the Python process during a full browsing session. This makes `DAY_03_IMPLEMENTATION_SPEC.md:87` true for the first time |
| **F3** | Junk-lead containment: scope the reactor scrape to a post-detail path with a reactions-tab ancestor, drop the bare `li` fallback, stop minting identities from name hashes, record `capture_context` | `content.js:194-232,252,255`; S6 | none | Open messaging overlay, notifications, connection modals, and search filters in sequence: zero `lead_interactions` rows. Open a real reactions modal on a post page: rows written |
| **F4** | Repair the K/M parser; stop period-stamping; add the precision flag | `content.js:97-138`; `linkedin_client.py:176-233`; S8 | none | Unit test: `"1.2K"` to `1200`, `"1.5M"` to `1500000`, `"12,345"` to `12345`, `"~"` to None. No `analytics_daily` row is written from a card whose period label is not `1d` |
| **F5** | Collapse `leads.status` into `lead_status`, dual-write for one release | `leads.py:185-199`; `crm.py:520-540`; S12 | none | Mark a lead "Meeting Booked" in the UI: `conversion_rate_pct` moves. Today it cannot |
| **F6** | Retire the reach verdict. Keep every individual check and every one-click fix | `app.js:2030-2062`; `index.html:1585,1713` | none | No string in the UI asserts a reach outcome. An empty composer shows an em-dash, not `94` |
| **F7** | Suppress the suggested DM when `interaction_type != 'COMMENT'` or the comment text is the sentinel. Send the real post's first line as `post_topic` | `crm.py:229-242,328`; `content.js:258-259`; `leads.py:237-239` | none | No stored DM contains the string "Reacted to post on LinkedIn" or "sovereign creator architecture" |
| **F8** | Small truths: fix `h.is_mobile_fold_safe` to `mobile_safe`; drop `predicted_score`; relabel `velocity_score` as an editor's pick | `app.js:2244`; `repurposer.py:301-302,363-364`; `intelligence_sync.py:54-55,598` | none | Fold-safe hooks no longer read "Truncated" |

On sequencing: F1 ships first because nothing else matters if the creator catches the product lying, **but F1 is subtractive and its ceiling is a product that is honest and empty.** It prevents churn by betrayal; it creates no reason to stay. Calendar-first is not the same as highest-leverage.

### FOUNDATION (weeks). Strict dependency order.

| # | Change | Files | Prereq | Test of success | Unlocks |
|---|---|---|---|---|---|
| **FD1** | Post identity at injection | S1, S2 via `migrations.py`; new route near `app.py:675`; `sidepanel.js:85-113`; `background.js` | none | Inject a post: a `posts` row exists with `published_at` and a fingerprint **before** the user has clicked anything on LinkedIn | FD2, FD4, the entire compound layer |
| **FD2** | Bind the URN passively | `content.js` new `bindPostUrn()`; `PATCH /api/posts/{id}/urn` | FD1 | Post, click through to your own post once: `posts.activity_urn` is populated within one page load. Health strip reads "3 of last 3 bound" | FD3, FD4 |
| **FD3** | Stamp post identity on every engager. **Tiny diff, enormous consequence** | `content.js:249-261`; `app.py:1880-1910` validation only | FD2 | `GET /api/v1/analytics/posts/{urn}/leads` returns non-zero for the first time in this product's life. Also update `tests/test_phase2_extension_csv.py:67-75`, which currently **encodes the omission as the contract** while `docs/API_REFERENCE.md:273` documents the opposite | D1, D3's outcome metric, real DM context |
| **FD4** | Per-post metrics from the creator's own post analytics | `content.js`; `linkedin_client.py:259-286`; `app.py:1474-1485` validation | FD2, F4 | The Post Leaderboard at `app.py:491` ranks posts the creator actually wrote. Today it can only rank seeds | rate-based panels |
| **FD5** | Feature extraction into `post_features` | S3, S10; `formatters.py:294-312` reuse; `app.py:561-600` | none technically, worthless without FD4 | Every saved post produces 8 feature rows | the contrast engine |
| **FD6** | The outcome signal: Monday one-tap card writing `lead_status` | `app.js` weekly card; `crm.py`; `leads.py`; S11 | F5, FD3 | The funnel moves. `conversion_rate_pct` is non-zero after real use | any honest re-weighting of ICP |
| **FD7** | Capture health plus the ritual shell | `content.js`; `background.js`; `sidepanel.js` rewrite; `app.js`; `studio_tray.py` | FD1 | Break a selector deliberately: the health strip turns red within one page load and names the surface. Plus an active canary: on a post page, if primary comment selectors match 0 while a loose `a[href*="/in/"]` count in the comments region exceeds 3, raise `selector_drift` | prevents FM2, silent degradation |

### COMPOUND (months)

| # | Change | Prereq | Test of success |
|---|---|---|---|
| **CP1** | The contrast engine: `post_contrasts` computed nightly by the existing scheduler, binary features only, **abstain below n=8 per arm with the n shown** | FD4, FD5 | At n=3 every contrast reads "not enough yet". A synthetic 20-post corpus with one planted effect surfaces exactly that contrast and no others |
| **CP2** | Evidence-backed composer panel sourced only from contrasts, every claim carrying n and linking to real post ids | CP1 | Every rendered claim can be traced by clicking through to real posts |
| **CP3** | Retrieval brief to the model: top-5 and bottom-5 by qualified-leads-per-1k-impressions, exact text and numbers, every suggestion required to cite a post id | FD4 | Suggestions citing nothing are rejected before display |
| **CP4** | Topic to qualified-lead map: "Your migration posts: 7 qualified leads from 3 posts. Hiring: 0 from 5." **The single highest-value sentence this product can produce** | FD3, FD5, FD6 | It names real topics and real counts |
| **CP5** | Observed timing, reported and never recommended. Delete the ten hardcoded `queue_slots` (`database.py:1661-1672`) rather than replacing them with a differently-dressed guess | FD3, C7 | The panel is titled "when engagers arrived", carries its n, and informs no scheduling suggestion |
| **CP6** | Ground the enrichment panel in observed data or delete it | a decision, not a dependency | No output asserts a tech stack the system did not observe |

### The single highest-leverage change

> **Record the activity URN of every post the creator publishes, and stamp it on every engager captured from that post.** FD1 plus FD2 plus FD3. Files: `sidepanel.js`, `content.js`, `migrations.py`, one new route in `app.py`.

Four reasons it beats every alternative:

1. **It is multiplicative, not additive.** Three complete, shipped, tested subsystems (`crm.py:620-700`, `app.py:509-518`, `app.py:530-536`) are correct code returning zeros forever because nothing tells them which post is which. This flips all three live without touching them.
2. **The dependency graph has exactly one root.** No URN means no post-to-engager link, which means no qualified-lead count per post, which means no outcome variable, which means no contrast engine, no evidence panel, no retrieval brief, no topic map. Everything in COMPOUND descends from this column.
3. **The product already knows the answer and throws it away.** This is not a scraping problem. `sidepanel.js:99` types the creator's words into LinkedIn's composer and writes nothing, anywhere, one line later. The URN is bookkeeping on an event the product itself caused.
4. **It is unambiguously passive.** The primary route reads `location.pathname` on a page the creator opened. No navigation, no fetch, no request.

How you would know it worked, in one week: inject a post at 9:12am and a `posts` row exists with a fingerprint before the creator touches LinkedIn; they click through to their own post once and `activity_urn` populates; they scroll the comments and `lead_interactions` rows carry that URN, the first non-test non-seed rows with post identity this codebase has ever written; `GET /api/v1/analytics/posts/{urn}/leads` returns 4 instead of 0; and the Analytics tab shows "4 leads, 2 senior" beside a post the creator actually wrote.

---

## 10. WHAT NOT TO BUILD

### Fantasy at this data scale

| Do not build | Why |
|---|---|
| **A propensity or conversion model** | Four predictors need roughly 40 outcome events. A solo founder yields 5 to 20 a year. Report "Of 34 VIP-tier engagers, 6 replied" once n is at least 30, and call it `reply_rate_among_engagers`, never `conversion_rate`, because the denominator excludes everyone who read and scrolled on |
| **Best time to post** | Ten day-by-slot cells at roughly 20 posts each, confounded with topic, never separate. A creator who reorganizes their week around a false peak loses real weeks. **The product makes no time-of-day recommendation. Ever.** Report the observed arrival histogram with its n and refuse to advise |
| **Ranking 8 hook archetypes** | 60 to 100 posts per arm needed; a solo creator reaches that in year three, by which point the audience has changed and the comparison is invalid. Answer a different question honestly instead: how often do you reach for each format, which is true at n=1 |
| **Any fine-tuning or training** | There is no training set here and there will not be one. Retrieval works at n=10 and improves with every post |
| **A significance-testing UI** | No p-values, no confidence intervals, at any n. A creator cannot act on a CI. They can act on "this rests on seven posts" |
| **`post_dwell_metrics` as measurement** | Viewer dwell on your posts is not rendered by LinkedIn to anyone. The column sits next to `reading_velocity_wpm DEFAULT 220.0` (`telemetry_shard.py:84-92`), which gives it away. Rename to `estimated_read_seconds` or delete |

### Crosses the passive-observer line

| Do not build | Why |
|---|---|
| **Any server-side Voyager call using the stored `li_at`** | Every one fetches data the user did not request from a session the user is not driving. `linkedin_client.py` already has the token plumbing and a circuit breaker, and the cookies sync every 15 minutes (`background.js:54`), which makes this the easiest boundary in the codebase to cross by accident. It is already crossed at `background.js:146`. F2 removes it; an asserted `egress_count` of 0 in CI is what keeps it removed |
| **Historical analytics from before install** | Requires driving LinkedIn's date picker. Say "cold start" plainly, mark the boundary in the UI, and never let seeded rows occupy the space where backfill would go |
| **Complete reactor or follower lists** | The modal lazy-loads; the full set requires scroll-driven pagination the user did not perform. This is enumeration, and it is forbidden. Print **coverage** instead ("14 of 200 reactors captured"), which makes low coverage honest and visible rather than hidden, and correctly removes the temptation |
| **Demographics for a post the user did not open** | Active navigation |
| **Competitor or "viral inspiration" post metrics** | Impressions on other people's posts are not rendered to you at any time, so no observer passive or active can obtain them. The `inspirations` table's `likes_count`/`comments_count` is the ceiling |
| **Email addresses or phone numbers of engagers** | Not rendered, and not the product |

### Built, and should be deleted rather than fixed

| Delete | Why |
|---|---|
| The `webRequest` listener as an **ingestion path** (`background.js:118-154`) | It cannot read a body in any manifest version. Keep the creator-analytics branch as a trigger only, delete the console strings, and correct the specs at `DAY_02_IMPLEMENTATION_SPEC.md:92-94` and `DAY_03_IMPLEMENTATION_SPEC.md:82-86` that describe a capability the code does not have. **Never plan a feature on it as a data source** |
| The Audit Score column (`app.js:4601`) | A green string constant beside real impression counts |
| The reach verdict and its gauge (`app.js:2052-2062`) | Six regexes presented as a claim about LinkedIn's distribution |
| `predicted_score` (`repurposer.py:302,364`) | Two values keyed on a character count, named as if fitted |
| `velocity_score` and `engagement_multiplier` as displayed figures | Hand-typed, and they are the swipe file's sort order (`intelligence_sync.py:598`) |
| The seeded `audience_demographics` surface | Replaced by engager-derived panels, with LinkedIn's own figures honestly empty until C10 |
| The static demo rows at `index.html:903-917` | Two fabricated posts that survive every failed fetch |
| `mock_ingestion_verification` (`linkedin_client.py:545-590`) as a production code path | Its only callers are tests, and its existence makes the richer ingest branches look reachable when they are not |

### One temptation worth naming explicitly

**Do not build a Capture Inbox triage queue as the fix for fabricated reactors.** The designs disagree here, and scoping plus `capture_context` (F3, S6) wins over a quarantine UI, because a daily Keep/Discard tax is exactly the kind of configuration work this user will not do, and a correctly scoped selector produces nothing to triage. Add the quarantine only if false positives persist after F3 ships.

---

**Monday morning, in order: F1, then F2, then F3.** They take a day and a half combined and they stop the product from lying. Then FD1. Everything the product was supposed to be is downstream of that one column.