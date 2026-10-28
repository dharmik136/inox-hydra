# Cycle 4: three readers on LinkedIn's 2026 pages (2.10.1)

A capability fix, from the owner's own LinkedIn pages on 2026-10-28. Branch `qc4/readers-2026`, from `main`
at `9e2adf7` (v2.10.0); it ships as 2.10.1, which extensions at 2.10.0 load without a hand reload. Source:
sanitised outlines of three of the owner's pages (element types, stable attributes, label and figure
words), with every fixture rebuilt from them using invented text and an invented vanity. A failing test
first, no independent review, one full suite as CI runs it.

| | |
|---|---|
| Built | The Activity posts reader, the creator analytics reader and the search appearances reader, each on its 2026 page, with the earlier shapes kept as fallbacks |
| New tests | 3 modules, 30 tests: `tests/test_qc4_readers_2026_activity.py` (6), `_analytics.py` (20, six of them the studio's storage, with no browser), `_search.py` (4) |
| Against `main` | On `9e2adf7` 27 of the 30 fail. The 3 that pass are as-before cases: a list that never fills is an empty read, a change percentage was never a count there either, and an article's page reads no loose line |
| Falsified | Fifteen guards, each failing when its part of the fix is taken out and passing when it is put back |
| Migration | One, numbered 36 in this branch, `_migrate_content_page_figures`: "Members reached, saves, sends and the network split from the creator analytics page, by day and by window". The coordinator renumbers it at merge |
| Routes | None added. The overview's windowed readings carry the five new figures |
| Track 1's files | `own_pages.js`: 883-961 (new: the lazy list), `cardCounts` 1083-1104, `sendActivity` 1271-1275, `onActivityPage` 1855-1864, `onRoute` 1924. `content.js`: 731-734 and 752 (the re-read), 918-1083 (new: the reader by words), `extractAndSyncAnalytics` 1084-1207 |
| Suite, as CI runs it | 4,083 passed, 17 skipped, 0 failed at 1f16115 with this record, after `npm --prefix studio/ui run build` |

| Commit | What |
|---|---|
| d836267 | The creator analytics page is read by its own words, and a range it does not name is kept as a window (migration 36, the policy and the help) |
| 6e375e4 | The Activity reader waits for LinkedIn's lazy list and reads each 2026 post |
| f5b552f | Search appearances take the figure before the label and the window after the change |
| 1f16115 | A note or a table cell is never the analytics range, and lines are read on account pages only |

## What each reader does now

**Activity > All** (`own_pages.js`). The studio recorded `items_seen` 0 at 2.5 s while the card stamper saw
38 cards a second later: the list is a LazyColumn that fills after the route settles. The first read
waits for a card while the list is on the page (up to 15 s; 4 s while no list has appeared), and the
list is then watched for a minute, its new cards read 1.2 s after they stop arriving, at most ten times,
never during an import and never on another member's page. A post is `div[data-urn]` with an id from
"expanded" to "FeedType_"; its words are the expandable text box; the comment and repost counts are the
bare figure in the buttons named "Comment" and "Repost"; "6 reactions" is plain text in a link, and
"499 impressions" a plain paragraph, read only when the whole line is the count. Rows with words and no
card this reader knows are drift, `post_cards`.

**Creator analytics** (`content.js`). It reported `metric_cards` drift because the card classes are
hashed. Each section is found by its heading, and only a figure right beside its label is read:
"Content performance" and "Discovery" print the figure first (impressions, members reached), and
"Engagement" prints each label first (reactions, comments, reposts, saves, sends). The network split is
read when a row's label names the network as LinkedIn does ("in your network", "out of network" and
their usual variants) and the two shares add up to about 100. The range is the page's own phrase
("Past 28 days") in its control or starting "Past" or "Last", outside the chart and an open menu's
other options, so a note ("May take up to 48 hours") or a table cell ("2 days") is never the range; a
custom range's two dates stay "unrecognised"; with no phrase, the comparison under the change ("vs. prior 28 days"); with none, the
reading is kept as a window the page did not name (`unnamed`). A 24-hour reading is that day's row in
`analytics_daily`, which now keeps members reached, saves, sends and the split; any other window goes to
`analytics_windows` with the same figures. A page with nothing it knows is read again, 2 s apart, five
times, before it is drift, and only the content page itself can drift: `metric_cards` with no heading,
`metric_labels` with headings and neither impressions nor followers.

**Search appearances** (`own_insights.js`). The card reads "15 Search appearances 0% past 7 days" and
nothing was kept: the window sits after the change, in a line that is no element of its own, and an
account count is kept only with its window. The words after the label in its card (its list item) are
read for the window now, the count can be the word right before the label, and on the account pages a
line holding count, label and window together is read as one. A percentage is never a count.

## The owner's rule, and what is not verified

A figure the page does not show is not read, never 0, and never drift (2026-10-26): members reached,
saves, sends and the split on the analytics page, a repost count on a card that prints none. Drift is
kept for a page that plainly is the page with nothing matching. Not visible in the outlines, so
accepted in the shapes LinkedIn uses and left unread otherwise: the two split labels (38 and 14
characters, likely "in network" and "Out of network"), the range control's own words, and how the range
menu marks its chosen option. The reader's words are English, as the owner's pages are; the range is
read in every language `analyticsPeriodOf` knows.
