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

## Carried to 2.9.0

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
