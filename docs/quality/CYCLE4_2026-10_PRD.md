# Cycle 4: catch, show, sections, ideas (October 2026)

## 1. Mandate

The owner's instruction of 2026-10-26, after three research tracks were delivered: go ahead with all the implementation for all the research done, run as a proper software company with different roles.

This cycle implements the programmes those three reports set out. The reports are the specification; this document says who does what, in which order, under which rules, and which of the reports' open decisions were adopted.

## 2. Inputs

| Report | What it specifies |
| --- | --- |
| Smooth capture from LinkedIn | The capture pipeline: a 39-item programme in eight phases, decisions D1 to D11, a gaps table, the hand diagnostic for network reading, the ten-day coordination plan, the coverage table |
| Sections the studio needs | The rail: sixteen sections in five groups, 29 defects with path:line, an eleven-batch programme, eighteen decisions, the per-section audit |
| Personalised daily ideas section | The section built from what each creator has done and asks: states by tenure, signals, the asked store, the pipeline, cards with provenance, the keep and skip writer, the daily job, evaluation, posture |

The three reports and the research notes behind them are kept outside this public repository, with the owner. They quote third-party reviews and forum posts at length, and they carry a reading of LinkedIn's terms against each feature that is the owner's to publish or not. Everything this cycle builds is specified again in section 6 and recorded with path and line in each track's record, so a reader of the repository does not need them. The creator-facing reading of the terms that the cycle does ship is the help article track 6 writes, which quotes LinkedIn's own words beside each feature.

## 3. Roles

| Role | Who | Responsibility |
| --- | --- | --- |
| Product and coordination | The coordinator | This document, the adopted decisions, track briefs, integration merges, the register, the release |
| Engineering | One engineer per track, in that track's own worktree and branch | Builds the track's items exactly as the report specifies, failing test first, with a record of each item |
| QA | Inside every track | A failing test before each change; every new guard falsified against the fault it is meant to catch before it is kept; the suite green as CI runs it; the interface built and audited when a screen changes |
| Independent review | A reviewer who did not write the track's code | Reads the diff against the report and the rules; outcomes are accept, accept-with-note, or sent back; sent-back items are fixed and reviewed again |
| Release | The coordinator | Version 2.8.0 on every surface, help for every new screen, privacy policy and its published page, CI green on three operating systems plus the clean-install job, the tag, the store package |

## 4. Rules of the cycle

The rules of cycles 1 to 3 hold unchanged, restated so no track has to look them up.

- No em-dash and no en-dash in any tracked file. `tests/test_phase4_algorithmic_safety.py` reads tracked files only, so stage before running it.
- Nothing invented on screen. Every figure comes from a row; "not measured" is a sentence, never a 0; the engines' abstentions are kept; a window label says which days a figure covers.
- Token colours only, zero hex literals, at most six inline styles, one `h1` per screen, help articles link only to help. The extension's own pages join these rules in track 1, phase 3.
- One definition per figure (`results.py`, `fold.py`, `cadence.ts`, `ingest_contract.py`, `paths.py`, `sqlite_open.py`, `text_cut.py`). A new rule gets a guard test, and the guard is falsified before it is kept: a guard that cannot fail protects nothing.
- Zero egress. Anything new that leaves the machine goes through `egress.py` under a named category with the creator's consent, and the privacy policy says so before the feature ships. The policy's tests hold it to the code; its published page is rebuilt from it.
- No ranking of people by score. Own data only. Nothing automated on LinkedIn: per decision D1 the posture statement reads "nothing acts on LinkedIn except when the creator presses Insert".
- Process. One branch per track from `main`, one worktree per branch in a sibling folder of the repository (`inox-hydra-qc4/<track>`). Never edit the main checkout; a live studio runs from it. Never a bare `git stash`. Run the suite from the track's worktree as CI runs it, `pytest tests studio/tests -q -rs`, with the project interpreter. Build the interface with `npm --prefix studio/ui run build` before any browser test. Commit small, in the repository's voice (the subject says what changed for the creator), and end every commit message with the attribution line in use for this cycle.
- Migrations. One migration per track, named for what it changes, numbered 28 in the branch. The coordinator renumbers at integration in merge order, so tests assert the migration's name and the columns it adds, never its number.
- Privacy. Before every push the diff is compared against the live database for real names and post text. The repository is public.
- Records. Each track writes `docs/quality/cycle4/<track>.md`: item, what changed, the test that fails without it, how the guard was falsified, the review outcome. The coordinator assembles `docs/quality/CYCLE4_REGISTER.md` from the records at the end.

## 5. Decisions adopted

Every open decision in the three reports is adopted at the report's recommendation, on the owner's instruction of 2026-10-26 to go ahead with the implementation. Each is reversible by a later decision; none is a legal reading.

### 5.1 From the capture report

| Id | Decision | Adopted |
| --- | --- | --- |
| D1 | The composer click | Keep it. The posture statement becomes "nothing acts on LinkedIn except when you press Insert". A setting that inserts only into an already open composer is added for creators who want the stricter line |
| D2 | Send to LinkedIn through `normShares` | Stays off by default with its per-profile acknowledgement; not extended to profiles beyond the first (see D9). The official posting route is parked until the public-client question is answered from LinkedIn's documentation; track 6 records the answer |
| D3 | In-page elements | The capture confirmation moves to the action badge and the side panel. The import banner stays because it carries Stop. The drift notice goes in the panel header and the badge colour, not in the page. `data-urn` stays. Nothing is ever placed near an advertisement |
| D4 | Network reading | The visibility items are built now (switch state on the heartbeat, the coverage meter, the refused-row fix). The registry is not re-keyed in this cycle; that waits on the owner's diagnostic and on what the coverage meter reports. The XLSX import is the exact-figure source this cycle delivers |
| D5 | Permissions | `cookies` and `webRequest` move to optional permissions and the token is passed by a pairing step, after the coordination block, so the pairing step and the browser instance id arrive together |
| D6 | The Telegram ingress | Leaves dev mode behind a Settings surface with the same sealing as the AI key. It stays marked "not yet tested against the real service" in the help until the owner runs one end-to-end test; the phone sends a URL, never a figure |
| D7 | Phone pairing transport | Design document only this cycle; Tailscale first, WireGuard as the no-third-party option, LAN only with a pairing code; any Host-rewriting relay is refused |
| D8 | Community Management API | An owner action outside the code; nothing in this cycle depends on it |
| D9 | Agency tier sessions | Session sync and Send to LinkedIn are disabled for profiles beyond the first, and the help states that each profile's session must come from that creator's own browser on that creator's own machine |
| D10 | Raw capture retention | Not needed this cycle (D4 holds the re-key) |
| D11 | The extension's light theme | The extension follows the studio's tokens file as copied; the light opt-out comes with it |

### 5.2 From the sections report

| # | Decision | Adopted |
| --- | --- | --- |
| 1 | The count | Seventeen entries in five groups: the sixteen of the sections report plus the personalised section "From your record", third in the Now group (ideas report, decisions 1 and 2). Library is folded into that section as its Kept level, which supplies the writer Library lacked. Review stays deferred |
| 2 | Activity | Kept as the log, re-scoped to its one question, with Health as its sibling in the Bridge group and a chip in the rail foot |
| 3 | Leads or People | Leads keeps its label; the set is called Audience |
| 4 | Brand Studio | Split into Brand (identity and watermark inside) and Settings |
| 5 | Setup | Fixed at the foot; the app lands on it until setup is done |
| 6 | The Queue's drafts list | Becomes a count with one action |
| 7 | The Patterns topic table | The qualified framing is retired; topic becomes a form through the engine; the funnel appears as counts in Audience |
| 8 | Analytics' profile views | Removed until a reader exists |
| 9 | Replies' answered state | A creator-set mark in a new table |
| 10 | The update check | Offered in Health and Settings, off by default |
| 11 | The seven-day capture prune | Rows stay seven days; a per-reader daily summary row is kept longer |
| 12 | Missed-post history | Persisted |
| 13 | Library's writer | The keep, skip and used marks of the personalised section are the writer; Library as a separate section is not built |
| 14 | The capture additions | Scheduled after the precision column. Amended by the owner on 2026-10-26, when track 5 showed the cost: only the labels the reader captured before this cycle can report drift. A new label LinkedIn does not show on a page is recorded as not read, never as drift and never as 0, because low-reach posts carry no demographics and a Basic member may never see profile viewers, and a reader marked drifting for that would send the creator to Setup for nothing. A new label that is never read stays visible instead as a count in Health: "not read on any of the last N post analytics pages" |
| 15 | Group headers | Five headers, never clickable |
| 16 | The rail at desktop width | Expanded with labels at 1200 px and above |
| 17 | The show path | Server-Sent Events |
| 18 | Agency routing | Fixed in the coordination block before any portfolio view; no portfolio view this cycle |

### 5.3 From the personalised daily ideas report

| # | Decision | Adopted |
| --- | --- | --- |
| 1 | The section's name | "From your record", with the blocks "Working for you", "You asked" and "You engaged with" |
| 2 | Placement | Now group, third, after Today and Replies; the rail guard moves from sixteen to seventeen entries |
| 3 | Library | Absorbed as the section's Kept level; the keep mark is the writer |
| 4 | Review | Stays deferred; the Monday card shows counts only, no comparison |
| 5 | Which asks are persisted | Explicit acts only: the Setup fields, the ask box, "More of this", Telegram; the Composer instruction box only behind a tick; nothing silent |
| 6 | Search Queries from the archive | Imported only behind a tick at import time, off by default |
| 7 | When the model stage runs | On the creator's first open of the day, so the policy's "only at the moment you use the feature" stays true; a scheduled switch is a later decision |
| 8 | Tiers | Stage 1 (local, no key, no egress) on every tier; stage 2 (the creator's own model) on the Creator tier once `BETA_OPEN` closes |
| 9 | Cost ceiling | $0.10 a day by default, editable; the Batch option off |
| 10 | The sync module (capture D3's scope) | The current unsigned sync module is deleted; the signed channel is built new |
| 11 | The bundle's content | Forms, patterns and company-authored examples only; nothing quoted from other people's posts |
| 12 | The web route | Designed and gated, off by default, built only after a legal review; not built in this cycle |
| 13 | Notifications | None by default |
| 14 | Slots and the Monday card | Five slots, abstentions left unpadded; the Monday card on |

### 5.4 Owner actions outside the code

These cannot be done from the repository and are not blocking: the fifteen-minute network-reading diagnostic (capture report, Appendix A); the live checks in the capture report's gaps table (labels on the post analytics page, the 24-hour analytics range, impressions on Activity cards, figures above 10,000); one analytics export and one per-post export as real files for the XLSX importer; the real end-to-end Telegram test; the Community Management application; the lawyer's reading; the store submissions; signing.

## 6. Tracks

Each track names the report items it builds, the files it owns, and what "done" means. Two tracks never edit the same region of a file; where two tracks touch one file, the owning region is named.

### Track 1: the bridge (extension and bridge routes)

Branch `qc4/t1-bridge`. Specification: the capture report, sections Catch, Coordinate, Show (the worker side), Appendix A and Appendix B.

Phase 1, items 1, 2, 3, 4, 5, 7, 8, 9, 10: reader self-timing; network-reading state on both heartbeats, `BridgeHeartbeat` and Setup's three honest states; the Resource Timing coverage meter; own-page items marked sent only on an answer; the gate race, the DOM marker, the refused row before `_require_me`, and `EXTRACTORS` aligned with what is sent; Navigation API routes behind feature detection; the worker's `lastCapture` in storage with the per-tab badge and the panel reading storage; the drift notice in the panel header and badge colour; the day-7 and weekly cadence rules in `_open_next`. Also the sections report's defect "WORKING shown for a reader that read nothing" (`onboarding.py:359`), because it lives in `capture_health`.

Phase 2, item 11: the coordination block, Appendix B in full: identity stamps, idempotency keys, worker coalescing and batching, the concurrency cap, the worker-owned heartbeat, the hidden-tab pause, the studio's `already_seen` answer, routing by signed-in vanity to the right creator profile with unmatched captures held rather than dropped, the import claimed per tab, tests, and the ten-tab measurement recorded.

Phase 3, items 13, 29 and D1's setting: the extension under the token system with a frozen ratchet and the three invented values renamed; `cookies` and `webRequest` as optional permissions with the pairing step; the "insert only into an open composer" setting. Items 14 to 17 (catch performance) and 35 (dynamic registration) follow only if item 1's timings justify them.

Owns: `studio/extension/*` except the `POST_METRIC_LABELS` and number-parsing region of `own_pages.js` (track 5); `studio/backend/onboarding.py` (heartbeat, `capture_health`, `record_capture`, `_open_next` cadence rules); the bridge routes in `app.py`; `ingest_contract.py`; `security.py`; the extension help articles.

Done when: Setup can say "network reading is off", "on and seeing N calls" or "on and matching nothing"; "connected" distinguishes a worker heartbeat from a page reading; no capture is dropped silently; ten tabs on one post cost one request and one row per item; a second account's captures land in its own profile or are held; the panel and badge confirm a capture without a studio call; the extension passes the same ratchets as the studio.

### Track 2: the show path

Branch `qc4/t2-show`. Specification: the capture report, section Show (the studio side) and item 12; the sections report, batch 7.

Items: `/api/v1/events` as Server-Sent Events with an in-process event bus set by the ingest paths and a `PRAGMA data_version` backstop; `useRefresh` gains an event trigger; Today's poll to 120 s, Setup's and Activity's to a 30 s backstop; Today's six side panels under refresh; the stream closed when the window is hidden; one stream per window.

Owns: the events route and bus module; `studio/ui/src/lib/refresh.ts`; `App.tsx` (the stream's lifecycle); the interval constants in `TodaySurface.tsx`, `OnboardingSurface.tsx` and `ActivitySurface.tsx`.

Done when: a capture appears on Setup and Activity within about a second; Setup's steady cost falls from about 660 SELECTs a minute, measured before and after; the three security checks are unchanged; the stream survives the `--reload` server and runs inside the Tauri shell.

### Track 3: honesty and moves

Branch `qc4/t3-honesty`. Specification: the sections report, "Twenty-nine defects the redesign must not inherit" and batches 0 and 1.

Items: every defect row except the `capture_health` row (track 1), each closed with a test; Analytics' post table out with the aside linking into Posts; Patterns' cadence block moved to Queue; Patterns' contrasts drawn from the payload it already fetches; the topic table reworked as a form through the engine; the Queue's drafts list as a count with one action.

Owns: `studio/backend/routers/posts.py`, `crm.py` (the two score orderings), `results.py` (the colour cut), the Queue router's due cap, `EvidencePanel.tsx`, `PatternsSurface.tsx`, `AnalyticsSurface.tsx`, `QueueSurface.tsx`, `ActivitySurface.tsx` (reposts, filing date, the dead carrier branch), `TodaySurface.tsx` (the approximate flag, the once-read side panels), the navigation registry's ghosts and `screenKey` entries.

Done when: no screen orders people by score; every figure on the touched screens comes from a row with its window; each host section has one view and one job; the one-view measurement is recorded for each touched section.

### Track 4: the new sections and the splits

Branch `qc4/t4-sections`. Specification: the sections report, "The proposed rail" and batches 2, 3, 4, 5, 6 and 8, decisions 2 to 6, 9 to 12, 15 and 16.

Items: Health (on the existing routes plus one field: run rows per reader) with the chip in the rail foot and Setup's capture health moved; Replies (a paged route from `today.reply_to`'s rules, grouped by post, the `reply_marks` table and its control, Today's count link); Audience (one route ordered by facts, connections by profile URL, funnel and company counts) and the Leads dossier's first, last and times seen; the Brand and Settings split with the Settings overview; Posts' per-post readings as a series by source with the two-day reading and names per row; the Queue's Calendar sub-view with persisted missed events and dispatch and collision detail; the Composer's "What the model is told" panel; Outbound's first seen, reaction kind, excerpt and per-post targets; the five group headers; the expanded rail with labels at 1200 px and above; the update-check consent control; the per-reader daily summary row.

Owns: `studio/ui/src/lib/navigation.ts`, `StudioRail.tsx`, `NavigationTray.tsx`, the new surfaces, `OnboardingSurface.tsx` (the health move), `BrandStudioSurface.tsx` and what it splits into, `PostsSurface.tsx` and `PostDetail.tsx`, `QueueSurface.tsx` (the Calendar sub-view only; track 3 owns its drafts count), `LeadsSurface.tsx`, `OutboundSurface.tsx`, the new routes, `scheduler.py` (missed history), one migration, a help article per new section.

Done when: each new section answers its first-view question in one view; every figure carries its window; the axe sweep passes in both themes; the help explains each new section; the rail reads as five groups.

### Track 5: derive

Branch `qc4/t5-derive`. Specification: the capture report, section Derive and items 18 to 22; sections decision 14.

Items: the precision column on post readings mirroring migration 5; the seven missing post analytics fields (followers gained, profile viewers, link visits, the content-specific metrics, a percentage parser for the network split) and a dated demographics table, each reported as drift when its label is absent; the account series fixes (the profile reader writing followers and connections to `analytics_daily`, the 7-day card stored as a weekly period when no 1-day window exists, the roll-up keeping the first reading of each day); the decay alert and reach half-life through `results.difference` and `results.spread`, abstaining under the engine's minimums; a format column per post from the archive's rich-media field and the card markers.

Owns: one migration; the `POST_METRIC_LABELS`, `NUMBER_ONLY` and number-parsing region of `own_pages.js`; `results.py` (the new derivations); `today.py` (the decay sentence; track 6 owns `_open_next`'s desk-request rule and track 1 its cadence rules, so each adds a separate function); `retention.py` (the roll-up); the analytics routers' new fields. Track 4 draws the new fields on Posts; this track returns them.

Done when: a "12K" reading is stored as approximate; the new labels are captured or reported as drift; followers are a series; the decay sentence names its reading count and abstains below the minimum; the format comparison runs through the existing contrast engine with its abstentions.

### Track 6: posture and the phone

Branch `qc4/t6-posture`. Specification: the capture report, sections Posture and Mobile, items 24, 25, 27, 28, 30, decisions D2, D6, D7, D9.

Items: D9's gating of session sync and Send to LinkedIn to the first profile, with the help sentence; the analytics XLSX import (request, find, preview, import) built against LinkedIn's documented export and marked "verified against a real file" only when the owner supplies one; the phone's share of a post URL through the Telegram ingress becoming a desk request that Today surfaces, with the ingress out of dev mode behind Settings; the archive age nudge in Setup and Today; the pairing design document; the creator-facing terms page in the help quoting LinkedIn's own words with each feature's standing; the risk-note wording (Shield's status, "tolerated, not permitted"); the store listing's disclosures; the written answer on the public-client question for D2.

Owns: `licensing.py`, `accounts.py` and `linkedin_client.py` (the gating); a new XLSX import module and its Setup and Analytics entry points; `ingress.py`; a desk-request table in the track's migration; `today.py` (`_open_next`'s desk-request rule, as its own function); the help articles it adds; `planning/7 Roadmap/` risk notes; `docs/PRIVACY_POLICY.md` only for the Telegram and XLSX sentences, coordinated with track 7, which also edits it.

Done when: a second profile cannot sync a session or send; an XLSX file imports with a preview and every figure it carries lands with its source; a URL shared from the phone becomes a request Today shows; the policy states the two new paths and its tests pass.

### Track 7: the personalised daily section

Branch `qc4/t7-ideas`. Specification: the personalised daily ideas report, in full, with the decisions of section 5.3.

Items: the section "From your record" as the seventeenth rail entry, third in the Now group, with the rail guard updated; the asks store, written from explicit acts only (the Setup fields, the ask box, "More of this", Telegram; the Composer instruction box behind a tick), with retention, the forget-identity path, and the privacy policy and help sentences at the anchors the report names; the importer adopting Saved Items, Member Follows, Company Follows, Votes and Articles, with Search Queries behind a tick that is off by default; stage 1, local and always on (recurring themes over the creator's own posts through FTS5, an on-this-day post, the posts the creator engaged with shown as link plus their own words, the topics typed at setup, and "what worked" through `results.ranking` only, abstaining in words until the thresholds are met); stage 2, the creator's own model through structured outputs wired into the gateway's request builder for every provider, returning only row ids, labels and short phrases, with the digit filter, the allowlist redactor, the verification record that drops any card whose cited row does not exist, run on the creator's first open of the day under the cost ceiling; stage 3, a signed Ed25519 bundle of forms, patterns and company-authored examples under the `library` egress category, matched on the device, with the current unsigned sync module and its wipe-and-replace of `viral_templates` deleted; stage 4, the web route, designed in the record and not built; cards with the six provenance labels plus "abstained", the "because you ..." sentence naming the rows and the rule, and the five marks (keep, skip, used, posted, hide), with the Kept level as the absorbed Library; the daily job computing once into a dated table with an input signature and carry-forward when nothing changed, never calling a model on screen load; the Monday card with counts only; the evaluation (the marks funnel, the contemporaneous comparison abstaining under eight posts, the monthly sentence templates, and a backtest tool the owner can run on their own history); the `/api/inspirations` route and the boot-time table recreation retired or folded in; a help article; the policy updated.

Owns: `archive_import.py` (the new categories and the tick), `agno_agentos/model_gateway.py` (structured outputs), `intelligence_sync.py` (deleted and replaced by the signed channel), a new ideas module and its routes, one migration, the new surface, `navigation.ts` (one entry and the guard's count, coordinated with track 4, which restructures the rail), `docs/PRIVACY_POLICY.md` (the asks store and the model stage; track 6 edits other paragraphs), `voice_pack.py` (openers through `results.ranking`, coordinated with track 3), the help article.

Done when: a creator who imported an archive sees a non-empty, provenance-labelled section on day 0 with no key configured; "what worked" abstains in words rather than guessing; no number on the screen came from a model; every card's cited row exists; the marks persist and the Kept level reads from them; the daily job never runs a model on screen load; the policy's tests pass with the new sentences.

## 7. Integration and release

Tracks merge into `qc4/integration` as they complete, in this order where it matters: track 3, track 2, track 1 phase 1, track 5, track 4, track 6, track 7, track 1 phase 2, track 1 phase 3. Each merge: the suite as CI runs it, the interface built, the audit, the privacy scan, the push, CI on three operating systems and the clean-install job. Migrations are renumbered at each merge.

Release 2.8.0: the version on `studio/__version__.py`, the manifest, `desktop/src-tauri/tauri.conf.json` and the policy; a help article for every new screen and every changed posture; the policy page rebuilt and `gh-pages` pushed; `CYCLE4_REGISTER.md` assembled; the tag only when all four CI jobs are green; the store package refreshed (extension zip, screenshots, the submission text with the new disclosures).

## 8. Parked, with the reason

| Item | Reason |
| --- | --- |
| Capture 23, side panel "This page" | After the extension's tokens; follows track 1 phase 3 if time allows |
| Capture 26, the OCR trial | Needs twenty screenshots only the owner can take |
| Capture 31, the official posting route | Waits on the public-client answer track 6 records |
| Capture 32, the API application | An owner action |
| Capture 33, the datalet reader | Needs a live check that the blocks still exist |
| Capture 34, strategy provenance and the fixture corpus | After a sanitised live snapshot exists |
| Capture 36, the interceptor re-key | D4: after the diagnostic and the coverage meter |
| Capture 37 to 39 | Companion window, phone pairing, notifications: after this cycle |
| Capture 14 to 17 | Only if item 1's timings justify them |
| Sections: Review | Deferred until a weekly module and its test family exist |
| Ideas stage 4, the web route | Designed and gated only; built after a legal review |
