# Cycle 4 register (October 2026)

What cycle 4 shipped in 2.8.0, what it carried to 2.9.0, and where each
track's own record is. The PRD is `docs/quality/CYCLE4_2026-10_PRD.md`.

## How the cycle ran

Seven tracks were built in parallel, one engineer and one worktree each, with
a failing test before each change. The first five finished tracks went through
an independent review; every review found real defects, and each went back to
its engineer for a second round. On 26 October the owner redirected the cycle
toward capability ("we just want the product's capability to be enhanced"):
the remaining reviews were stopped, the open second rounds were cut to what
changes data, privacy or behaviour, and wording items were deferred. From
then on a track merged when its full suite passed and the coordinator's
privacy scan of its added lines against the live databases was clean.

## In 2.8.0

| Track | Record | What it gave the creator |
| --- | --- | --- |
| 5, derive | `docs/quality/cycle4/t5-derive.md` | Precision on readings, the post analytics page's other figures (a figure not shown is not read, never 0 or drift), followers as a series, the decay sentence and half-life, a format per post |
| 7, From your record | `docs/quality/cycle4/t7-ideas.md` | The daily section built from the creator's own record and asks, the marks and Kept, the model stage under the creator's own key with row-id citations, the signed library in place of the unsigned sync |
| 3, honesty and moves | `docs/quality/cycle4/t3-honesty.md` | People ordered by engagement time, each section's second job moved to its home, posts and people the moves could have hidden listed on Posts, the Queue's draft action made safe |
| 6, posture and the phone | `docs/quality/cycle4/t6-posture.md` | Sessions and Send to LinkedIn for the first profile only, the analytics export import, the phone's post link as a desk request, LinkedIn's own words beside each feature |
| 5, phase 2 | `docs/quality/cycle4/t5-derive.md` | New readers for the creator's own profile views, search appearances, new followers, articles, newsletters, watch time, reposts and edits, kept as counts with their windows |

The coordinator's integration commits added one fix the tracks found and did
not own: search opens a published post on Posts, where published posts are
listed now.

### Defects the reviews found before release

Among them: an address meter that could have stored another member's
vanity; a sentence telling the creator nothing reached the AI provider when
the voice pack's openers did; a button that could flip a published post back
to scheduled; an export whose dates landed four years early in the 1904 date
system; a second profile's 2.7.0 session that survived the upgrade; a
demographics reader that paired labels with the wrong percentages. Each was
fixed with a test before merge; the tracks' records carry the detail.

## In 2.9.0

Tracks 1 (the bridge), 2 (the show path) and 4 (the new sections and the
rail, and the screens for track 5's phase 2 readings), each merged with
2.8.0 by its own engineer and then combined on track 4's branch. The
combination caught one defect no single track could: track 1 moved the
capture write into a helper, and track 2's publish line still read the
helper's variables from the old place, so every capture would have
answered 500 after its row was saved; it is fixed with a test. Records:
`docs/quality/cycle4/t1-bridge.md`, `t2-show.md`, `t4-sections.md`.

## In 2.10.0

Track 1's phase 2 (coordination and self-update), track 4's phase b (the
deeper screens, the demo content and the store screenshots) and track 7's
phase 2 (the enhancer), each built on 2.9.0 under the owner's direction of
capability first and merged on a release branch. Ten tabs on one post went
from 620 requests to 3. Records: `docs/quality/cycle4/t1-phase2.md`,
`t4-phase-b.md`, `t7-phase2.md`.

## In 2.12.0

The Telegram bot, phase 3, on the owner's direction of 2026-10-29: one bot for
one person as the single collection box, made into posts in real time and
remembered ("make something out of those things and remember them"), with
every choice in the AI work the creator's preference ("do not hardcode
things"). Three migrations (38 to 40), rehearsed on a copy of the owner's live
database before release: integrity ok, every count unchanged, the two phone
drafts already held appearing in the collection. Records:
`docs/quality/cycle4/collection-box.md` (the PRD) and the phase 3 section of
`docs/quality/cycle4/telegram-bot.md`.

## In 2.11.0

The Telegram bot, phases 1 and 2, the standing assignment the owner asked for
on 2026-10-28 ("a dedicated agent to start making the telegram chat bot
better and start testing and adding features to it"). The owner's first test
against the real service showed the path worked and felt dead: the bot never
replied. It now replies, takes commands, reports the creator's own figures
and reminds only when asked, and carries buttons, quiet hours and a weekly
summary. Everything runs against a fake Bot API on 127.0.0.1 in the suite;
the owner's checklist covers the real service. No migration. Record:
`docs/quality/cycle4/telegram-bot.md`.

## In 2.10.2

Network reading retired, on the owner's decision of 2026-10-28: a sanitised
Resource Timing list from their own feed tab showed LinkedIn's 2026 web app
makes no /voyager/api/ calls, so the interceptor, its schema registry and the
webRequest observer had nothing to read. With it, the Telegram bot's token,
which the egress ledger had shown on Local security since the ingress went
through the chokepoint, is masked there, and an error answer from Telegram is
backed off from instead of being asked again every two seconds; both carried
back in their smallest form from the bot's own work for 2.11.0. Record:
`docs/quality/cycle4/retire-network-reading.md`.

## In 2.10.1

The first tests on the owner's live LinkedIn pages found three readers that
LinkedIn's 2026 rebuild had broken (the posts list, the analytics page and
search appearances), a real analytics export with three sheets the importer
did not know, and the Telegram path's first contact with the real service
(pairing by chat id, short links). The owner captured sanitised outlines of
their own pages with a console snippet; the readers were rebuilt from them.
They also showed that LinkedIn's site no longer calls /voyager/api/, so
network reading has nothing to read. Records:
`docs/quality/cycle4/readers-2026.md`, `export-2026.md`.

## Carried to 2.9.0, as planned at 2.8.0

| Work | Why it waits |
| --- | --- |
| Track 1, the bridge (phase 1 and its review round) | Still in its second round when the owner asked for the release. It holds the fix for a post first seen after 2.7.0 lacking its studio record, the feed reader keeping only the creator's own posts, the address allowlist, and moving notices off LinkedIn's page |
| Track 2, the show path | Its second round (re-reads only when an event can change the screen) was in progress |
| Track 4, the new sections and the rail | Merging the integration branch into its own when the release was cut, unless it lands first |
| Drawing the new readings | Track 5's phase 2 routes have no screen yet: Analytics' profile views, the content figures, reposts and edits |
| Deferred review items | Listed per track in each record's "deferred" lines |

## Owner actions

From the PRD, unchanged: the network reading diagnostic, the live label
checks, a real analytics export file, a real Telegram test, the Community
Management API application and LinkedIn enabling PKCE for posting, the lawyer's
reading, store submissions and signing. New in this cycle: back up the
library signing key at `~/.config/inox-hydra/library-signing/` offline; and when
2.9.0 brings the live update stream, check it once in the desktop shell.
