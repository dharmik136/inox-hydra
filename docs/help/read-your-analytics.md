# Read your analytics

See how your daily figures reach the studio, and read the chart, the three observations and the post comparison.

## How numbers get in

The studio does not fetch your analytics. The browser extension reads them from LinkedIn's own analytics page while you have it open. You need the extension loaded and paired first; see [Install the browser extension that captures leads and analytics](install-the-browser-extension.md).

1. In that browser, open your LinkedIn analytics page.
2. Set LinkedIn's range selector to the past 24 hours.
3. Wait a couple of seconds. The extension reads the impressions, engagements and followers cards and saves them under today's date (UTC).

One visit records one day. A second visit the same day updates that day. Days you do not visit have no figures, and nothing is filled in later.

| Notice on LinkedIn | Meaning |
| --- | --- |
| "LinkedIn Studio: creator analytics synced to your local studio." | The extension sent the figures. It also shows this when the studio could not be reached, so confirm on **Analytics**. |
| "...so they were not saved as today's numbers. Set the range to 24 hours to sync a daily figure." | The page showed a multi-day total, which the studio refuses. Change the range; the extension reads again. |

If the extension cannot tell which range is selected, it still saves the figures, labelled as an unknown period. Check the selector before you visit. Abbreviated figures such as 1.2K are stored as the rounded number, 1200, and marked as rounded.

## Read the page

- **Range**: **7d**, **30d** (the default) or **90d**, counted back from the latest day the studio holds, not from today.
- **Measure**: **Impressions**, **Reactions**, **Comments**, **Profile views** or **Followers**. The chart plots one per day; hover to read a day, or open **TABLE VIEW** under the chart.

| Measure | Where it comes from |
| --- | --- |
| Impressions | The impressions card |
| Reactions | The engagements card |
| Followers | The followers card |
| Comments | Not captured. It reads 0 on every captured day. |
| Profile views | Not captured. The chart shows NOTHING MEASURED IN THIS RANGE. |

## The three observations

- **What changed**: Impressions and Engagements (reactions, comments and shares) summed over the range and compared with the previous period of the same length. Profile views compares the last day's figure with the first day's, and Followers is the difference between them. If the first day has no figure, the last day stands in for it, so the change reads 0. With nothing in the previous period, a change reads +100.0%.
- **What moved with it**: one sentence on how reach and engagement moved together.
- **What to look at next**: your post with the highest engagement rate.

These describe the numbers. They do not claim a cause.

## Post comparison

The table lists every post whose status is published, including posts you only marked as published. Rate is (reactions + comments + shares) divided by impressions, as a percentage.

> [!NOTE]
> The extension does not capture per-post figures, so posts written in the studio show 0 impressions, reactions and comments, and a rate of 0%. The strongest-post observation then reports 0.00%.

Click a row to see leads linked to it: a count of leads and interactions with names, or NO LEADS ATTRIBUTED TO THIS POST. In this build, posts written in the studio are not linked to their LinkedIn posts. The extension reports which post you opened, but the step that prepares a post for matching is refused by the extension itself, so expect NO LEADS ATTRIBUTED TO THIS POST.

## The seeded-data banner

If you see "N of M days are seeded sample data, not measurements.", those days are generated samples, written only when the studio was started with `INOX_DEMO_DATA` set. The chart and the observations include them. The banner says captured days replace seeded ones. In fact a captured day replaces only the seeded day with the same date, and keeps any seeded figure it did not capture, such as comments and profile views.

## Export

Click **CSV** beside the range buttons. It downloads every stored day, whatever range is selected, as `linkedin_analytics_export.csv`.

## If it does not work

| You see | What to do |
| --- | --- |
| ANALYTICS UNAVAILABLE | The studio did not answer or refused the request. Check it is running and reload. |
| NOTHING MEASURED IN THIS RANGE | No figures exist for that measure in this range. Visit your LinkedIn analytics page with the extension running. Profile views always shows this. |
| "not measured" | That figure was never captured for that day or post. Under **What changed**, it was not captured on the latest day the studio holds, or nothing has been captured at all. |
| NO PUBLISHED POSTS TO COMPARE | No post has the published status yet. |

Audience demographics are not shown anywhere in the studio.
