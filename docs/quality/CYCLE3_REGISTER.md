# Cycle 3 register: every section worth its place

Companion to [CYCLE3_2026-10_PRD.md](CYCLE3_2026-10_PRD.md). Six research
reports, eight batches, four independent reviews, every claim re-measured by
someone who did not make it.

| | |
|---|---|
| Findings delivered | 51 |
| Fixed / partial / other | 47 / 1 / 3 |
| Sent back by review, then fixed | 7 |
| Tests | 2,824 to 3,074 passing |
| Screens audited | 48 fresh and 48 with data, no blocking finding |

Three claims a reviewer measured and found wrong, each corrected by the batch
that made it: a queue density figure that needed rows written straight into
the database; an endpoint improvement reported as 51,000 ms when the old code
took 1,095 ms; and a root cause that was never the cause.

| Batch | ID | State | Review | What changed |
|---|---|---|---|---|
| T1 | P-7 | fixed |  | Every post answers for its engagers, asked by the studio id, an activity, share or ugcPost URN, a permalink, a slug, a bare activity id or a fingerpri |
| T1 | P-6 | fixed |  | Publishing from the studio now does what an imported post does: the publication record, the fingerprint that binds it later, the engagement row, the s |
| T1 | P-4 | fixed |  | The engagers endpoint uses the join post_summary documents, so the busiest post of a three year install answers in 13 ms instead of 404. |
| T1 | T1-1 | fixed |  | One binder, post_identity.bind_activity_urn, used by the permalink route, the history import and migration 26. The second binder is four lines that ca |
| T1 | T1-2 | fixed |  | The drafts list shows every draft, including the ones that were held in the legacy store. |
| T1 | P-17 | partial |  | The dead queue is gone, and the legacy drafts store can no longer hold writing the record does not. |
| T2 | AUDIENCE-S1-B | fixed |  | Every screen names the same best and worst posts, from the whole history, and says what the ranking rests on: the creator's own median reactions over  |
| T2 | AUDIENCE-S1-C | fixed |  | A rate is computed from one reading, and a post whose recorded engagements exceed its impressions carries no rate at all: the table says not measured  |
| T2 | AUDIENCE-S1-A | fixed |  | A lead's score is recomputed whenever their headline, their company or their engagements change, so Posts, Patterns, Analytics and the dossier always  |
| T2 | CORRELATION-13a | fixed |  | One post has one set of figures on every screen, with the page they were read from and when named beside them, and Today's two day comparison still sa |
| T2 | T4-PAGING-BEST | fixed |  | The Analytics aside names the post that worked best across the whole history, with how many settled posts the answer rests on, and no longer ranks by  |
| T2 | DERIVED-D1-D1b-D2 | fixed |  | The settle age is measured from the creator's own readings and the screens say so; every post on the Posts screen carries its reach and its response a |
| T2 | DERIVED-R4-R6 | fixed |  | A comparison can answer 'no difference your own posts can separate', and Patterns says it rather than printing a 1.1x line as a finding; the topic tab |
| T3 | P-2 | fixed | accept | A capture carrying the studio's own post key is accepted and stored instead of being rejected and lost, and the extension and studio now agree in writ |
| T3 | P-3 | fixed | accept | A refusal the creator can act on now reaches them: a sentence on the LinkedIn page they are standing on, a block in the side panel naming the last one |
| T3 | P-14 | fixed | accept-with-note | Every path that carries the creator's own data is kept when the studio cannot take it, the queue drains on its own without waiting for a browser resta |
| T3 | P-8 | fixed | accept-with-note | Removed. The module, its seven publishers and every claim about a stream are gone, and nothing a creator can reach went with them. |
| T3 | P-9 | fixed | accept-with-note | Thirty engagers captured at once finish in 1.5 s instead of 6.0 s, with the slowest request 1.5 s instead of 6.2 s, so a busy post no longer pushes ca |
| T4 | DERIVED-D6 | fixed | accept-with-note | Posts and Analytics compute each post's people and lead attribution for the posts on screen rather than for every post ever written, and the index tha |
| T4 | P-5 | fixed | accept-with-note | Both lists answer with one page of 50 posts, in the order they always used, and say the total, the limit, the offset and whether there is more; a limi |
| T4 | P-4 | fixed | accept | A post's engagers come back through the index, 2.8x faster end to end, as the same rows in the same order. |
| T4 | P-11 | fixed | accept | A capture is judged by one indexed lookup of the post's key instead of a pass over every post the creator has written. |
| T4 | P-1 | fixed | accept | The hourly backup, reaction folding and retention cleanup run when the machine wakes however late they are, and /api/v1/storage now says whether the n |
| T4 | ONEVIEW-ACTIVITY-TWICE | cannot-reproduce | accept | Nothing changed in the endpoint; the one read per visit and the size of one read are now held by tests. |
| T4 | P-9-MEASURE | wontfix | accept | Re-measured after this batch's changes, as the task asked; not changed. |
| T5 | T5-TODAY | fixed | accept-with-note | Today is a thin summary that cannot complete anything (ONEVIEW.md section 2, S1; PRD section 6) |
| T5 | T5-QUEUE | fixed | sent back, fixed | The Queue is thin and cannot say that a post was missed or why (ONEVIEW.md section 2, S3; PRD section 6) |
| T5 | T5-COMPOSER-FEED | fixed | sent back, fixed | What the creator learns never reaches what they write (MAKING.md section 1.11 and M-11) |
| T5 | M-1 | fixed | accept-with-note | One click on the Swipe File replaces every hook in the Composer with another author's invented claims, and the Composer never says so (MAKING.md S2) |
| T5 | T5-RAIL-CLAIM | fixed | accept-with-note | The Swipe File's one honest claim, and the pack's only control, lost their home when T7 cut the screen |
| T5 | T5-PAYLOAD | fixed | accept | Every screen's first paint carried 259 KB of drafts, to reopen one of them |
| T6 | T6-REVIEW-1 | fixed | accept | Posts is a table that sorts, filters and searches the creator's whole history and pages through it, with the count beside the pager (1-20 of 1,417) an |
| T6 | T6-REVIEW-2 | cannot-reproduce | accept | Nothing to fix. The behaviour was verified and then guarded: the named best post does not move with the page, Analytics and Posts name the same post,  |
| T6 | T6-POSTS | fixed | accept-with-note | A real table: sortable, filtered, searched and paged, with reach and response as a pair per post, the post against the creator's usual, a settle state |
| T6 | T6-ANALYTICS | fixed | sent back, fixed | The screen opens on the five figures of the range, each with its own change and its own "not measured" where nothing was read, the chart beside the wr |
| T6 | T6-PATTERNS | fixed | accept-with-note | The screen shows the creator's own settle curve, measured: the share of its final reactions and impressions a post had reached by each age, the posts  |
| T7 | T7-LEADS-01 | fixed | sent back, fixed | The fields are one column below the small breakpoint, and at wide widths the dossier uses its pane in two columns, which also lifts 'Draft a message'  |
| T7 | T7-LEADS-02 | fixed | sent back, fixed | The dossier groups a person's engagement by the creator's post: comments, reactions and the last date per post, from the whole history rather than the |
| T7 | T7-OUTBOUND | fixed | accept-with-note | Rebuilt across the window on what the live path records: the people you engage with, the last thing you said to each, how many of your posts they enga |
| T7 | T7-ACTIVITY | fixed | accept-with-note | One log, newest first, grouped by day, one line per thing read, with the kinds as filters over that one list and the newest 24 drawn out of what the a |
| T7 | T7-SWIPE | fixed | sent back, fixed | The section is gone: component deleted, nav entry and route removed, and a hook form found with Ctrl+K opens the Composer, where the rail applies it. |
| T7 | T7-COMMAND | fixed | sent back, fixed | The instruction box, the tick box and the session log are a block in the Composer's Prompt panel, beside the draft and under the disclosure that says  |
| T7 | T7-BRAND | fixed | accept-with-note | Your data is the first thing in the Storage and privacy pane; Local security keeps what stays on this machine and what leaves it. |
| T8 | T8-1 | fixed | sent back, fixed | The never-click claim is now conditional and the exception has its own table row: what the import does, that it runs only after the creator presses Im |
| T8 | T8-2 | fixed | accept-with-note | The row now separates the two: the extension still issues no request of its own, and its click on LinkedIn's control is what causes LinkedIn's page to |
| T8 | T8-3 | fixed | accept | The diagram now names the drain alarm the worker actually has, routes captures to the two endpoints they use, and gives the side panel its own node fo |
| T8 | T8-4 | fixed | accept-with-note | The threat row now names both automated paths, says each runs only when the creator asks, and points at the risk register. The register (planning/7 Ro |
| T8 | T8-5 | fixed | accept | Before the first send on an installation, send_readiness() refuses with code risk_not_acknowledged and the risk sentence; the Publish dialog shows tha |
| T8 | T8-6 | fixed | sent back, fixed | Four additions, no restructuring: the import exception in the page-reading paragraph; the update row now says nothing in the interface turns it on and |
| T8 | T8-7 | fixed | accept-with-note | Section 3 no longer states a table count and points at database.py and migrations.py as the source of truth, saying the list is deliberately partial.  |
| T8 | T8-8 | fixed | accept-with-note | The publish article gains a The first send from this studio asks you once section, a renumbered step 4, a row in its three-choices table and a row in  |
