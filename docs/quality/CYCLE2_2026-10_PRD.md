# PRD: Ready for a normal creator, and for years of data

| | |
|---|---|
| Status | Delivered, awaiting release |
| Owner | Product owner |
| Started | 2026-10-20 |
| Release | 2.6.0 (unreleased) |
| Research | four reports: install, backend, frontend, data |

## 1. Problem

Cycle 1 made the studio correct for the paths it audited. Four things still
stand between it and a paying creator:

1. **Nobody can install it.** No 2.6.0 download exists, and tagging today would
   publish a broken desktop installer, no portable ZIP and no update manifest.
   Nothing is signed; the extension has no store listing.
2. **Backend defects remain** where cycle 1 did not reach: a diagnostics file
   that leaks typed lead names, comments lost when cut mid-emoji, missed posts
   moved silently, an image studio that reports failures as success, Send to
   LinkedIn that cannot work, and about 30 unused routes that bypass guards.
3. **Everyday flows dead-end.** One draft at a time with a silent overwrite, no
   way to copy a post, a reply flow that asks for what the page already shows,
   internal documents in the customer's help, no restore button.
4. **Data grows without limits.** Three years of heavy use is 368 MB; Posts,
   Patterns and search take 1 to 2 s; export needs over 1 GB of memory; nothing
   is retained or maintained; a forgotten person stays readable on disk.

## 2. Goals

- A creator on Windows downloads one file, opens it, and reaches Setup in two
  minutes without a terminal; macOS and Linux follow (phase 3).
- Every S1 and S2 from the four reports fixed or explicitly decided.
- Main screens under 100 ms on the three-year dataset; export in bounded memory.
- Retention the creator controls, with nothing of theirs lost without asking.
- Every fix carries a test; every batch is reviewed; CI green on three OSes.

## 3. Decisions (owner, 2026-10-20)

| Decision | Choice |
|---|---|
| Send to LinkedIn | Fix it: author from the bridge, explicit confirmation, owner tests on a real account |
| Image fallback | Free public generator stays on by default; a profile setting chooses a provider, with what leaves the machine stated for each |
| Drafts | Drafts list with New post and delete; Publish's main action is Copy and mark posted, with Queue it beside it |
| Retention | Daily automatic backup with rotation; ask before forgetting leads silent 24 months; fold reactions older than 24 months into counts; connections stay |

Defaults taken where the research recommended and the owner did not object:
missed post becomes due at its time and Today says so; unused dangerous
routes removed and Telegram ingress plus the internal backlog dev-gated;
internal documents left out of packaged help and hidden from search; restore
gets a button with a safety backup first; neutral starter slots and hooks;
prefix full-text search; forgotten people disclosed as remaining in older
backups until rotation removes them; release tagged only after phase 0.

## 4. G-Stack view

| Role | Requires |
|---|---|
| CEO | Install in two minutes; no invented content; the creator's work never lost; honest about every request that leaves the machine |
| Engineering Manager | Small correct changes; indexed queries; safe, idempotent, rehearsed migrations; one owner per file |
| Designer | Flows that end in the action the creator came for; one name per thing; states that say what happened |
| QA Lead | A failing test first; the three-year dataset as a benchmark; clean-install checks per OS |
| CSO | Zero egress unless chosen and disclosed; secure delete; no third-party data in diagnostics; least API surface |
| Release Manager | All-or-nothing releases; a smoke test that passes the security gate; signed artifacts; an update path |

## 5. Phases

| Phase | Scope | Exit |
|---|---|---|
| 0, before tagging | Release pipeline fixes, the S1s, egress guard in tests | A dry-run release produces every artifact; S1s closed |
| 1, this cycle | Remaining S2/S3, data performance, retention and the Storage panel, drafts, Copy and post, Send to LinkedIn, image providers, honest launchers | Suite and UI audit green; benchmarks met |
| 2, owner actions | Signing certificate, Apple enrolment, store listings, tag v2.6.0 | Signed installer and listed extension |
| 3, next minor | Interactions table rebuild (id types), macOS/Linux runtime, uncommon port with the store extension, bundle trimming | Rehearsed migration on real-sized data |

## 6. Batches (phase 0 and 1)

| Batch | Scope |
|---|---|
| R1 Release | Release workflows, smoke test, desktop UI build, runtime pin, honest launchers, port probe, packaged help without internal docs, install docs |
| R2 Backend and privacy | Error handler and emoji truncation, diagnostics leak, MCP hang and env, telemetry limits, log rotation, busy and damaged database, route removal, dev gates, egress guard in the test suite |
| R3 Data performance | Indexes, per-post summary table, paging, FTS5 search, streaming export, maintenance |
| R4 Retention | Secure delete, daily backup with rotation and verification, telemetry expiry, lead review list, reaction folding, Storage and privacy panel |
| R5 Everyday flows | Reply from the comment shown, reconnect and refresh, help and search cleanup, restore button, terminology and time format, demo identity |
| R6 Writing | Drafts list, Copy and mark posted, slot editing and neutral names, missed post as due, Send to LinkedIn |
| R7 Images | Provider setting and providers, honest results, fonts for every script |

## 7. Definition of done

As cycle 1: a failing test before each fix, the batch's tests and the full
suite green, UI audit clean on changed screens, an independent review, the
changelog line written by the integrator, no personal data in the diff.

## 8. What only the owner can do

Windows signing identity; Apple Developer Program; updater signing keys;
Chrome Web Store and Edge Add-ons accounts and submissions; pushing the tag;
testing Send to LinkedIn on a real account; clean test machines per OS.

## 9. Results

| | |
|---|---|
| Research findings | install 18, backend 22, frontend 26, data 18 |
| Batches | 7 built, 7 reviewed; 10 fixes sent back (one of them twice), all fixed and re-checked |
| Tests | 2198 to 2787 passing; UI audit 56 screens fresh and demo, no blocking finding |
| Speed (three-year dataset) | main screens 0.4 to 1.9 s down to 9 to 78 ms; search about 2 s down to 4 to 53 ms; export peak memory 1.1 to 1.5 GB down to 22 MB |
| Storage | secure delete everywhere; daily verified backups with rotation; readings roll-up and reaction fold proven count-identical on a copy |
| Release | phase 0 fixed: smoke test, desktop UI build, all-or-nothing publishing, self-contained runtime, honest launchers |

Process lessons:
- Every sandbox and the test suite now refuse outbound connections at the
  socket level. Two research helpers and two existing tests had reached real
  services before that guard existed.
- Count-preserving data changes are proven endpoint by endpoint on a copy of a
  realistic dataset; the first fold design passed its own totals and still
  changed six screens.
- When a merge conflict is settled by taking one side of a file, the rest of
  that file's changes from the other side are lost; resolve per hunk.

Still the owner's: Windows signing, Apple enrolment, updater keys, store
listings for the extension, a manual dry run of the release workflow, the
first real Send to LinkedIn test, and pushing the v2.6.0 tag.
