# Check the bridge is reading
Open **Health** to see whether the browser extension is still reading your LinkedIn, what each reader read in the last 7 days, and what it could not read.

The extension reads LinkedIn's pages, and LinkedIn changes how they are built without notice. When a part of the capture stops matching, it finds nothing and says nothing, which looks exactly like nobody engaging. Health is where that shows. It used to be a block at the foot of **Setup** called **CAPTURE HEALTH**; Setup now points to Health.

## The line under the title

It says whether the bridge browser has been heard from, which extension version it runs, and how long ago it last reported. If the extension is older than the studio expects, the line says to reload it; see [After an update, reload the browser extension](after-an-update-reload-the-extension.md).

Under it, one sentence about network reading. Network reading is off unless you turn it on in the extension's popup. An extension that reports its switch state says here whether it is off, on and seeing LinkedIn's data calls, or on and matching nothing. An older extension does not report it, and the line says "not reported by this extension version" rather than guessing.

## The four figures

| Figure | What it counts |
| --- | --- |
| Readers working | How many of the readers listed below read something on their latest run |
| Readers that cannot read | How many found their page but not the fields they need |
| Captures waiting | How many captures the extension is holding for a studio that was busy, as it last reported. "Not reported" until the extension has reported since the studio started |
| Heartbeats | How many times the bridge reported in the last 7 days. It reports once a minute while a LinkedIn tab is open |

## Readers, last 7 days

One row per reader. The studio keeps a week of runs, which is why the table says **last 7 days**: a run older than that is gone from the log, except each reader's latest run and its latest run that worked, which are kept so the last two columns can always be answered.

| Column | What it is |
| --- | --- |
| STATE | **WORKING**, **CANNOT READ** and the fields it could not read, or **NOT SEEN YET** when the extension has never run that reader |
| RUNS | How many times the reader ran in the last 7 days |
| SEEN and KEPT | How many items those runs found on the page, and how many the studio kept. **not measured** when no run of the week counted |
| DRIFTED | How many of those runs could not read a field they need |
| LAST READ | When the reader last ran, however long ago |
| LAST WORKED | When it last read something without drift |

Click a reader's name to open its runs: each run's time, the kind of page, what it saw and kept, what it could not read, and the extension version that ran it. Below the runs is a row per day, kept for 180 days, so a reader's history outlives the week of runs: how many runs each day, how much they saw and kept, and how many drifted. A day whose runs counted nothing reads **not measured**, not 0.

When a reader is **CANNOT READ**, the page was found but the fields it needs could not be read, which usually means LinkedIn has changed how the page is built. Nothing from that part is captured until the extension is updated. There is nothing to fix on your side; keep the studio up to date.

## Which readers there are

The table lists these seven parts, the same seven Setup used to list:

| Part | What it reads |
| --- | --- |
| Comments and reactions on your posts | The people who become leads |
| Your profile | Your name and details, for Setup's step 3 |
| Your posts | The **Posts you wrote** import |
| Your comments | The **Comments you left** import |
| Your reactions | The **Posts you reacted to** import |
| Creator analytics | The figures in **Analytics** |
| Your posts' analytics pages | The figures on one of your own posts' analytics pages, such as members reached, saves and sends. Only your recorded posts are read |

Network reading is off unless you turn it on in the extension's popup. If you do, two more parts appear in the table once they have run: **Network reading: your posts' figures** and **Network reading: creator analytics**. They are not listed while network reading has not run, because opening a page cannot start them.

## The blocks on the right

- **Bridge heartbeats, last 7 days**: how many times the bridge was heard from, the first and last time, the longest silence between two heartbeats and when it ended, and each extension version seen with its first and last heartbeat. A machine that slept or a tab that was closed shows as a silence.
- **Waiting captures and refusals, since the studio started**: the captures the extension is holding for a studio that was busy, as it last said, and how many captures each refusal reason turned away. Both are counted from the moment the studio started, and say so.
- **Network reading and drift**: the newest drift events the network reader recorded, each with the response it could not read and when. While network reading is off there are none, and the block says so.
- **Database schema**: the database's version against the version this studio expects, and what will happen on the next restart if they differ.
- **Backup schedule**: whether the daily backup is on, the newest backup and when the next is due, and whether the schedule has stopped producing backups. See [Back up, restore and export](back-up-restore-and-export.md).
- **Update check**: off unless you turn it on. While it is off, the studio makes no request to check for a newer version. Turn it on and **Check now** asks GitHub once for the newest version number; nothing is downloaded or installed. See [Check your version and update the studio](check-your-version-and-update-the-studio.md).

Health reads its figures again every 30 seconds while the window is in view, and when you come back to it.

## What this changes elsewhere

- **Today**'s line under the title still says how many parts of the capture have stopped working; the detail is here.
- **Setup** keeps its five steps and points here for capture health.
- **Activity** is the log of what the bridge read; Health is whether the readers work. The two answer different questions, which is why both exist.
