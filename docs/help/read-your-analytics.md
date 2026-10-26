# Read your analytics

See how your daily figures reach the studio, and read the chart, the three observations and the post comparison.

## How numbers get in

The studio does not fetch your analytics. The browser extension reads them from LinkedIn's own analytics page while you have it open. You need the extension loaded and paired first; see [Install the browser extension that captures leads and analytics](install-the-browser-extension.md).

1. Confirm your profile in **Setup**, and open your own profile once in that browser at `https://www.linkedin.com/in/me/`, which works in every language. LinkedIn's analytics page does not say whose analytics it shows, so the extension remembers which account the browser is signed in to from your own profile, and the studio keeps analytics only from the account confirmed in **Setup**. Signing out of LinkedIn, or in as someone else, makes the extension forget, until you open `https://www.linkedin.com/in/me/` again. LinkedIn refreshing its sign-in does not.
2. In that browser, open your LinkedIn creator analytics page, whose address starts `linkedin.com/analytics/creator`. A single post's analytics page is not read.
3. Set LinkedIn's range selector to the past 24 hours.
4. Wait a couple of seconds. The extension reads the impressions, engagements and followers cards and saves them under today's date (UTC).

One visit records one day. A second visit the same day updates that day. Days you do not visit have no figures, and nothing is filled in later.

Anything that was not saved is said at the top of the extension's side panel, with a `!` on its badge until you open it; nothing is drawn into LinkedIn's page.

| What you see | Meaning |
| --- | --- |
| No notice in the side panel; the extension's badge counts one more and the side panel's header reads "Captured creator analytics just now." | The studio saved today's figures. |
| "...so they were not saved as today's numbers. Set the range to 24 hours to sync a daily figure." | The page showed a multi-day total, which the studio refuses. "Your follower count was saved." follows when the page showed one: followers are a count at one moment, so they are kept whatever the range. Change the range; the extension reads again. |
| "Inox Hydra: could not reach your studio, so these analytics were not saved." | The studio is not running. Start it and reload the analytics page. |
| "Inox Hydra: the studio refused this browser, so these analytics were not saved. ..." | This browser was never paired. Open the studio once in it, then reload the analytics page. |
| "Inox Hydra: the studio did not save these analytics: ..." | The studio answered and refused; the rest of the notice says why. "these analytics are from linkedin.com/in/..." means the browser is signed in to a different LinkedIn account from the profile open in the studio. "the bridge could not tell which LinkedIn account is signed in" means open `https://www.linkedin.com/in/me/` once in that browser, then reload. |

The extension reads the range selector in English and in the other languages LinkedIn offers, for example "Past 365 days", "Past 12 months" or "Letzte 7 Tage". If it finds a range it cannot read, such as a custom date range, the notice says it "could not tell which period these figures cover", and only the follower count is saved. If the page shows no range selector at all, it still saves the figures, labelled as an unknown period. The chart still plots that day, but the totals under **What changed** leave it out and say how many days they left out. Check the selector before you visit.

Figures are read in the page's language: on a German or Italian page 8.210 is 8210, and 1,2K is 1200. Abbreviated figures such as 1.2K or 1,2 Mio. are stored as the rounded number and marked as rounded. A figure the extension cannot read with certainty, such as 8.210 on a page that does not say its language, is not saved at all, rather than saved as 8. LinkedIn writes one decimal below 10K and whole thousands above, so 1.2K is anything from 1,150 to 1,249 and 23K from 22,500 to 23,499. On **Analytics** a figure or change built from one is shown with a ~, a note under the chart says how many plotted days are rounded, and a change smaller than the rounding is not shown.

## Read the page

- **Range**: **7d**, **30d** (the default) or **90d**, counted back from the latest day the studio holds, not from today.
- **Measure**: **Impressions**, **Reactions**, **Comments**, **Profile views** or **Followers**. The chart plots one per day; hover to read a day, or open **TABLE VIEW** under the chart.

| Measure | Where it comes from |
| --- | --- |
| Impressions | The impressions card |
| Reactions | The engagements card |
| Followers | The followers card |
| Comments | Not captured. Days captured now hold no figure; days captured by an earlier version read 0. |
| Profile views | Not captured. The chart shows NOTHING MEASURED IN THIS RANGE. |

## The panels beside the figures

The changes themselves are no longer in this list: each one now sits beside its own figure in the strip at the top, with a `~` where the source figure was rounded. What is left here is the reading, in up to four panels, some of which appear only when there is something to say.

- **How to read the figures**: the caveats that apply to the strip above. Impressions and Engagements (reactions, comments and shares) over the range, counting only days that hold a single day's figures, compared with the previous period of the same length by the level per captured day. A change is shown only when each period has that figure captured on at least 80 percent of its days (6 of 7, 24 of 30, 72 of 90), counted figure by figure: a day whose impressions were read and whose engagements were not counts for impressions only, and its engagements are not measured, never 0. Otherwise the change reads "not measured" and a note says on how many days each period has the figure. The engagement rate uses only days on which both were read. Days captured with an unknown range are left out, and a note under the list says how many. Profile views compares the last day's figure with the first day's, and Followers is the difference between them. If either day has no figure, or the previous period holds nothing to compare with, the change reads "not measured" rather than 0 or +100.0%.
- **What moved with it**: one sentence on how reach and engagement moved together.
- **Your best and your weakest**: shown when enough of your posts have settled to name them.
- **What to look at next**: your strongest post across all of your posts whose figures have settled, as a multiple of your usual, with the note that comparing its opening against the weaker ones is the one comparison this data supports. It is no longer the highest engagement rate on the page: that read the rate out of the rows in view, which could name a post with a handful of impressions. If nothing of yours has settled, it says so instead.

These describe the numbers. They do not claim a cause.

## Post comparison

The table lists your LinkedIn posts, the ones imported from your activity pages or your archive, and any post you marked as published in the studio that has not been matched to one of them. Rate is (reactions + comments + reposts) divided by impressions, as a percentage.

Fourteen posts are shown at a time, most seen first, which means most impressions. The line above the table says where you are, for example `1-14 of 1,418, most seen first`, and the two arrows beside it turn the page. The table used to list every post you have, which on three years of posting was 2.4 MB read before the screen could draw.

> [!NOTE]
> A figure the bridge has not read shows "not measured", never 0. Impressions are read only from a post's own analytics page, so most posts show "not measured" for impressions and rate. A post marked published in the studio has no figures of its own until it is matched to its LinkedIn post.

If a note under the table says a post has more engagements recorded than impressions, so no rate can be measured, it counts the posts **on the page you are looking at**, not all of yours. Turn the page and the count is about the posts there.

Click a row to see leads linked to it: a count of leads and interactions with names, or NO LEADS ATTRIBUTED TO THIS POST. An imported LinkedIn post carries the people the bridge captured on it. A post written in the studio is linked only once it has been matched to its LinkedIn post; until then expect NO LEADS ATTRIBUTED TO THIS POST.

## The seeded-data banner

If you see "N of M days are seeded sample data, not measurements.", those days are generated samples, written only when the studio was started with `INOX_DEMO_DATA` set. The chart and the observations include them. The banner says captured days replace seeded ones. In fact a captured day replaces only the seeded day with the same date, and keeps any seeded figure it did not capture, such as comments and profile views.

## Export

Click **CSV** beside the range buttons. It downloads every stored day, whatever range is selected, as `linkedin_analytics_export.csv`.

## If it does not work

| You see | What to do |
| --- | --- |
| ANALYTICS UNAVAILABLE | The studio did not answer or refused the request. Check it is running and reload. |
| NOTHING MEASURED IN THIS RANGE | No figures exist for that measure in this range. Visit your LinkedIn analytics page with the extension running. Profile views always shows this. |
| "not measured" | That figure was never captured for that day or post. Under **What changed**, one of the figures it compares was not captured, or the previous period holds nothing to compare with. |
| NO PUBLISHED POSTS TO COMPARE | None of your LinkedIn posts has been imported, and no studio post is marked published. Import your posts in Setup. |

Audience demographics are not shown anywhere in the studio.
