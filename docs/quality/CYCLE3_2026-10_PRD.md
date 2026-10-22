# PRD: Every section worth its place, and one truth underneath

| | |
|---|---|
| Status | Awaiting owner decisions, then delivery |
| Owner | Product owner |
| Started | 2026-10-22 |
| Release | 2.7.0 |
| Research | six reports in `~/.cache/inox-qc3/research/`: MAKING, AUDIENCE, PIPELINES, CORRELATION, DERIVED, ONEVIEW |

## 1. Problem

Two cycles made the studio correct. This one makes it coherent and worth
paying for. Six researchers used it against a three year install and found
the same shape from six directions:

- **The studio contradicts itself.** Seven different answers to "which post
  worked best", three answers to "how did this post do", six definitions of
  "settled". Analytics prints 116.25% engagement as fact.
- **Modules do not feed each other.** Data flows in from LinkedIn and never
  reaches where the creator writes. Publishing from the studio updates the
  post table and nothing else, so the studio cannot see its own published
  post until the extension re-imports it.
- **Sections are thin.** Median ink coverage is 16%: a reading column wrapped
  around a few numbers. Outbound renders 321 characters on an install holding
  44,000 outbound rows. Command renders 147. Meanwhile Posts renders 324,344
  characters down a column 176 screens tall, and two sections together fetch
  4.65 MB to answer one question.
- **The best data is untouched.** 362,996 readings of how each post grew are
  used by nothing, while the screens guess.

## 2. Goal

Every section earns its place: dense, honest, useful at every edge, fast on
three years of data. Underneath, one identity for a post, one truth about
results, one path in.

The owner's instruction, verbatim: *things in sections only, but in those
sections the view should be properly optimised and useful at every edge and
bit, and overall for all sections, so the thing should be properly optimised
for usage and backend.*

So: no merging of sections into one page. Each section is redesigned to the
density and usefulness the one-view prototype proved possible, and each gets
a backend that can serve it quickly.

## 3. What this cycle is not

- Not a feature cycle. New capability only where a section cannot be useful
  without it (Outbound is the clear case).
- Not a visual restyle. Same tokens, same type, same spacing scale.
- Not automation of LinkedIn beyond what exists.

## 4. Measured starting point

Three year install, 1440x900, dark. Ink is the share of the work area
carrying content. Scroll pages is the screen's height in viewports.

| Section | ink | chars | controls | scroll pages | payload | verdict |
|---|---|---|---|---|---|---|
| Swipe File | 31.9% | 3,861 | 10 | 1.0 | small | duplicates the hook rail |
| Activity | 18.2% | 13,669 | 16 | 6.1 | 118 KB, fetched twice | too long, repeats itself |
| Posts | 18.1% | 324,344 | 7 | **176.2** | **2,207 KB** | unusable at scale |
| Docs | 17.8% | 2,375 | 30 | 1.0 | small | sound |
| Analytics | 17.8% | 133,930 | 18 | **58.9** | **2,447 KB** | unusable at scale |
| Today | 16.1% | 1,874 | 8 | 1.4 | small | thin, 42% of width used |
| Patterns | 16.0% | 1,776 | 2 | 1.3 | small | two controls, contradicts itself |
| Leads | 15.3% | 10,852 | 25 | 1.0 | 104 KB | sound, dossier cramped |
| Setup | 10.8% | 2,302 | 5 | 2.3 | small | fine for its job |
| Queue | 8.7% | 770 | 3 | 1.0 | small | thin |
| Outbound | 5.1% | **321** | 1 | 1.0 | small | empty on 44,000 rows |
| Brand Studio | 2.3% | 142 | 10 | 1.0 | small | tabs hide everything |
| Command | 2.2% | **147** | 3 | 1.0 | small | duplicates the Prompt tab |
| Composer | 0.0% | 0 | 1 | 1.0 | small | correct: it is a writing surface |

## 5. The three structural faults

Fixing sections one by one without these would be decoration.

**5.1 One identity for a post.** Four tables hold "something the creator
wrote": `posts` (896), `own_posts` (1,417), `drafts` (1,044, no screen reads
it), `queue_items` (894, no reachable writer). 523 own_posts have no posts
row, which strands 182,115 of 500,061 interactions: the busiest post in the
dataset answers 404 from the engagers endpoint while Analytics shows it
fine. The drafts endpoint returns an empty list while the drafts table holds
150 rows, which can lose a creator's work.

**5.2 One truth about results.** Six modules compute "what worked", with
their own denominators, settle rules and tie breaks, and they disagree on
real data. `icp_score` is written once at capture and never recomputed:
stored scores say 0% of 49,142 people qualify, the live engine says 32.7%.
The engagement rate has no clamp. The precedent for the fix is already in the
repo: `fold.py` with `test_fold_is_one_number.py`.

**5.3 One path in.** Nine ingest paths, three ideas of post identity, two
binders, no version handshake. A declined capture answers 200 "skipped" with
no notice; one route declares a numeric post id for a text key, so a correct
value is rejected and the capture lost. Publishing updates nothing
downstream. The event bus has five event types, seven publishers and zero
subscribers; the single writer actor has processed zero tasks while the
README sells it, and 30 concurrent captures run 4.3x slower than sequential
for want of it.

## 6. What each section becomes

Every section target below is: what question it answers, what is on it, and
the measurable bar. The bar for all: **under 150 KB on first paint, under
100 ms for its own endpoints on the three year dataset, at least 25% ink at
1440x900, and no more than 2 scroll pages** unless it is a list the creator
asked to be long.

| Section | Becomes |
|---|---|
| **Today** | The command centre the prototype proved: one thing to fix, who to reply to with their actual words, your latest post read honestly against your own history, what worked and what did not, what is next out, the 30 day line, your rhythm. Three columns, no scrolling at 1440. |
| **Composer** | Unchanged as a writing surface, but fed: what worked is one click from here, and the hook rail stops being hijacked by the swipe pack. |
| **Queue** | The week at a glance with its slots, what is due, what was missed and why, cadence against the creator's own measured rhythm. |
| **Posts** | A table, not a column of cards: sortable, filtered, paged, with reach and response shown as a pair and a settle state per post. Opens one post into its detail rather than rendering everything. |
| **Leads** | Keep the stream and dossier; fix the dossier at phone width; show each person's actual words and their engagement history on the creator's posts. |
| **Outbound** | Rebuilt on data that exists: the creator's own comments and reactions, who they engaged with, who engaged back, who has gone quiet. Needs `target_author`, which is the one capture gap. If the live extension cannot fill it, the section is cut, per the standing judgement. |
| **Patterns** | One engine, one answer, with confidence stated and "no difference" said plainly when that is the truth. Reach and response as a pair; the settle curve measured, not assumed. |
| **Analytics** | Paged and summarised server side, not 2.4 MB. Trailing windows, never a percentage on a partial one. The 116.25% clamped and explained. |
| **Swipe File** | Either the creator's own best openers and shapes, derived from their history, or cut. It currently renders the same table as the hook rail through a second endpoint. |
| **Command** | Folded into the Composer's Prompt panel unless it earns a purpose: 147 characters is not a section. |
| **Activity** | What the bridge did, as a log that fits: grouped, truncated, fetched once. |
| **Setup** | Unchanged in purpose; the archive and history steps keep their fixes. |
| **Brand Studio** | Tabs that do not hide the thing being looked for: export belongs with Storage and privacy, not under Local security at y=1322. |
| **Docs** | Sound. Leave it. |

## 7. Backend targets

| Thing | Now | Target |
|---|---|---|
| Per post lead attribution | **334 s** | under 200 ms (index plus the query rewrite, with a full ANALYZE in the same migration) |
| `/api/v1/insights/posts` | 2,201 KB | paged, under 150 KB |
| `/api/analytics/posts` | 2,432 KB, `limit` ignored | paged, under 150 KB |
| `/api/v1/posts/{id}/engagers` | 404 on 36% of posts | answers for every post |
| Concurrent captures (30) | 6,200 ms, 4.3x worse than sequential | at or better than sequential |
| Hourly backup after sleep | skipped for an hour | runs on wake, visible if stale |
| Publish | writes 2 tables | updates everything downstream |

## 8. Decisions for the owner

Taken as defaults where research recommended and the owner has not objected;
say so and they change.

| # | Decision | Default taken |
|---|---|---|
| D1 | Sections | **Keep all sections** (owner's instruction). Each redesigned to the bar in section 6. Command and Swipe File must earn their place or fold into the screen they duplicate. |
| D2 | Send to LinkedIn | **Keep, and say plainly what it does.** It posts to LinkedIn's private API, which is the highest terms of service risk in the product, while `ARCHITECTURE.md` claims zero automated activity. Docs corrected; first use asks for an explicit acknowledgement. |
| D3 | Dead code | **Wire the valuable, delete the rest.** Keep and connect the copilot's answer validation, the CRM score breakdown and funnel. Delete three unused agents, both carousel renderers, the dead sync module and the unread telemetry store. |
| D4 | Outbound | **Rebuild if the live extension can fill `target_author`; cut if it cannot.** One real capture settles it, and only the owner can run it. |
| D5 | Privacy policy | Already corrected: the store text claimed the extension stores "four values and nothing else", which the capture retry queue made false. |

## 9. Delivery

Same shape as cycles 1 and 2, which worked: parallel batches, one owner per
file, a failing test before each change, an independent reviewer per batch,
re-verification of anything sent back, then integration, full suite, screen
audit, CI on three platforms, changelog, privacy scan, release.

| Batch | Scope |
|---|---|
| T1 | One post identity: the four tables, the binders, the engagers endpoint, publish updating everything downstream |
| T2 | One truth: a single results engine, the clamp, recomputed scores, settle curve from measured data, reach and response as a pair |
| T3 | One path in: the ingest contract, honest refusals, the capture queue surfaced, event bus either used or removed, the writer actor wired or removed with the README corrected |
| T4 | Backend performance: the 334 s query, paging, payload sizes, the sleep-safe scheduler |
| T5 | Sections A: Today, Queue, Composer feeding |
| T6 | Sections B: Posts, Analytics, Patterns |
| T7 | Sections C: Leads, Outbound, Activity, Swipe File, Command, Brand Studio |
| T8 | Docs honesty: extension and architecture claims, the risk register, the help articles each change touches |

Phase gate: T1 to T4 land and are green before T5 to T7 build on them.

## 10. Definition of done

Per finding: a test that fails before the fix; the section meets its bar,
measured on the three year dataset and recorded; an independent reviewer has
accepted it; the changelog says what changed for a creator; no personal data
in the diff; CI green on Windows, macOS and Linux plus the clean install.
