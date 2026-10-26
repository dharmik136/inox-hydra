# Check the bridge is reading
Open **Health** to see whether the browser extension is still reading your LinkedIn, what each reader read in the last 7 days, and what it could not read.

The extension reads LinkedIn's pages, and LinkedIn changes how they are built without notice. When a part of the capture stops matching, it finds nothing and says nothing, which looks exactly like nobody engaging. Health is where that shows. It used to be a block at the foot of **Setup** called **CAPTURE HEALTH**; Setup now points to Health.

## The line under the title

It says whether the bridge browser has been heard from, which extension version it runs, and how long ago it last reported. If the extension is older than the studio expects, the line says to reload it; see [After an update, reload the browser extension](after-an-update-reload-the-extension.md).

## The four figures

| Figure | What it counts |
| --- | --- |
| Readers working | How many of the readers listed below read something on their latest run |
| Readers that cannot read | How many found their page but not the fields they need |
| Captures waiting | How many captures the extension is holding for a studio that was busy, as it last reported. "Not reported" until the extension has reported since the studio started |
| Heartbeats | How many times the bridge reported in the last 7 days. It reports once a minute while a LinkedIn tab is open |

## Readers, last 7 days

Over the table, one sentence says which of three states network reading is in, as the bridge last reported it. Network reading is off unless you turn it on in the extension's popup.

- "Network reading is off.", with a grey dot.
- "Network reading is on and seeing N LinkedIn data calls, K matched.", with a green dot.
- "Network reading is on and matching nothing", in orange, with the count of data calls the LinkedIn tab that last reported saw and none matched. It adds "reload that tab" when that tab does not carry the reader, and "turn the switch off and on" when the browser has not registered it.

An extension that has not reported the state says "not reported by this extension version" rather than "off". The same sentence is in Setup's step 1 and in the extension's side panel, under **Health**.

One row per reader. The studio keeps a week of runs, which is why the table says **last 7 days**: a run older than that is gone from the log, except each reader's latest run and its latest run that worked, which are kept so the last two columns can always be answered.

| Column | What it is |
| --- | --- |
| STATE | One of five states, from the reader's latest run: **NOT SEEN YET** when the extension has not run it; **WORKING** when it read something; **READ NOTHING** when it ran and found nothing to read, which is an empty page or a page it no longer recognises; **CANNOT READ** and the fields it could not read, in orange; or **REFUSED: IDENTITY**, in orange, when the studio refused what it read |
| RUNS | How many times the reader ran in the last 7 days |
| SEEN and KEPT | How many items those runs found on the page, and how many the studio kept. **not measured** when no run of the week counted |
| DRIFTED | How many of those runs could not read a field they need |
| LAST READ | When the reader last ran, however long ago |
| LAST WORKED | When it last read something without drift |

Click a reader's name to open its runs: each run's time, the kind of page, what it saw and kept, what it could not read, and the extension version that ran it. Below the runs is a row per day, kept for 180 days, so a reader's history outlives the week of runs: how many runs each day, how much they saw and kept, and how many drifted. A day whose runs counted nothing reads **not measured**, not 0.

When a reader is **CANNOT READ**, the page was found but the fields it needs could not be read, which usually means LinkedIn has changed how the page is built. Nothing from that part is captured until the extension is updated. There is nothing to fix on your side; keep the studio up to date.

When a reader is **REFUSED: IDENTITY**, it ran, and the studio refused what it read because the LinkedIn account signed in to the bridge browser is not the profile you confirmed in Setup, or has not been noted yet. Open your own profile in that browser once, and check that it is the account you confirmed. A refused run is listed with the reader's runs, marked "refused", and is never counted as the reader's last working run.

## All readers by day

Under the readers, one row per day for the last 14 days, newest first, with every reader together: how many runs, how much they saw and kept, and how many could not read a field. These rows are kept for 180 days, so they outlive the week of runs. Days are counted in UTC.

- **nothing read**: a day the studio was keeping, on which no reader ran. The bridge browser was closed, or no LinkedIn page was open.
- **before the studio kept days**: a day before the studio began keeping these rows, which it did from the version that added them, starting with the week of runs it still held. Not a day of silence.

## Which readers there are

The table lists these eight parts:

| Part | What it reads |
| --- | --- |
| Comments and reactions on your posts | The people who become leads |
| Post ids on feed cards | Which post each commenter or reactor belongs to, copied from the card onto the page |
| Your profile | Your name and details, for Setup's step 3 |
| Your posts | The **Posts you wrote** import |
| Your comments | The **Comments you left** import |
| Your reactions | The **Posts you reacted to** import |
| Creator analytics | The figures in **Analytics** |
| Your posts' analytics pages | The figures on one of your own posts' analytics pages, such as members reached, saves and sends, and where the page shows them followers gained, profile viewers, link visits, the share of impressions from inside and outside your network, and the viewer demographics. Only your recorded posts are read. Only a missing impressions, members reached, reactions, comments, reposts, saves or sends figure marks this reader as not reading the page. LinkedIn may not show the others to every member or on every post, so a missing one stores nothing and is not counted against the reader; if one never appears, the label may have changed |

Network reading is off unless you turn it on in the extension's popup. While it is on, and once either has run, two more parts are listed: **Network reading: your posts' figures** and **Network reading: creator analytics**. They are not listed while the switch is off and neither has run, because opening a page cannot start them. Network reading keeps the figures of your own posts and your follower count, and nothing else: the other posts in LinkedIn's feed response are dropped before anything is written, and the profiles, reactions and comments LinkedIn's page also downloads are not sent to the studio at all.

## The blocks on the right

- **Bridge heartbeats, last 7 days**: how many times the bridge was heard from, the first and last time, the longest silence between two heartbeats and when it ended, and each extension version seen with its first and last heartbeat. A machine that slept or a tab that was closed shows as a silence.
- **Waiting captures and refusals, since the studio started**: the captures the extension is holding for a studio that was busy, as it last said, and how many captures each refusal reason turned away. Both are counted from the moment the studio started, and say so.
- **Network reading and drift**: the newest drift events the network reader recorded, each with the response it could not read and when. While network reading is off there are none, and the block says so.
- **Post analytics fields**: for each figure the reader of your posts' analytics pages started looking for in this version (such as followers gained and profile viewers), when one of those pages last carried it, or on how many it was not read, for example "not read on any of the last 12 post analytics pages". LinkedIn does not show every figure to every member or on every post, so a figure that is missing is not counted as the reader failing; this is where one that never appears shows.
- **Database schema**: the database's version against the version this studio expects, and what will happen on the next restart if they differ.
- **Backup schedule**: whether the daily backup is on, the newest backup and when the next is due, and whether the schedule has stopped producing backups. See [Back up, restore and export](back-up-restore-and-export.md).
- **Update check**: off unless you turn it on. While it is off, the studio makes no request to check for a newer version. Turn it on and **Check now** asks GitHub once for the newest version number; nothing is downloaded or installed. See [Check your version and update the studio](check-your-version-and-update-the-studio.md).

Health reads its figures again within about a second of a reader running or the bridge being heard from, and at most every 15 seconds while runs keep landing; every 30 seconds while the window is in view, which is how it notices the bridge going quiet; and when you come back to it.

## What this changes elsewhere

- **Today**'s line under the title still says how many parts of the capture have stopped working; the detail is here.
- **Setup** keeps its five steps and points here for capture health.
- **Activity** is the log of what the bridge read; Health is whether the readers work. The two answer different questions, which is why both exist.
