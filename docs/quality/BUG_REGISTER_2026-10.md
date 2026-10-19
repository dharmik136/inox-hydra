# Bug register: quality cycle 2026-10

Companion to [QUALITY_CYCLE_2026-10_PRD.md](QUALITY_CYCLE_2026-10_PRD.md).
Every finding here was found by using the product in a sandbox; 148 of the 160
raw findings were reproduced, the rest traced to exact lines.

| Stage | Count |
|---|---|
| Raw findings from six audits | 160 |
| Duplicates folded into another finding | 18 |
| Accepted | 142 |
| Very high (S1) / high (S2) / medium (S3) | 26 / 50 / 66 |
| Targets | 30 / 50 / 70 |

The targets set how deep each audit looked. Nothing was invented or inflated
to meet them: each auditor reported fewer S1s than asked rather than pad, and
triage re-rated a finding only with a stated reason, listed below.

## Re-rated at triage

| ID | Change and reason |
|---|---|
| AUDIENCE-12 | S2 to S1: '6 qualified leads' from 3 people and 600% conversion shown as fact: wrong numbers |
| BRIDGE-11 | S2 to S1: a year of impressions saved and charted as one day's, marked measured: wrong numbers |
| SETUP-07 | S2 to S1: one click deletes all imported history with no confirmation: data loss (UX-02 rated it S1) |
| WRITE-10 | S2 to S1: no post in a non-Latin script can ever bind or be attributed: a core workflow blocked for whole language groups, no workaround |
| WRITE-15 | S2 to S1: the queue records a post as published when nothing was posted: a false fact, and the post is missed (UX-04 rated it S1) |
| WRITE-16 | S2 to S1: with no model set, drafts carry invented statistics and another author's background: invented facts in the user's own posts |

## Very high (S1): 26

| ID | Area | Kind | What was wrong | What changed | Test | Status |
|---|---|---|---|---|---|---|
| AUDIENCE-01 | AUDIENCE | bug | First-message drafts claim an architecture blueprint and engineering background the creator does not have |  |  | open |
| AUDIENCE-02 | AUDIENCE | bug | Forgetting a lead leaves their stage history behind, and it comes back on the dossier if they engage again |  |  | open |
| AUDIENCE-03 | AUDIENCE | bug | Re-exporting to Obsidian silently overwrites a note the creator wrote when a new person or post gets the same name |  |  | open |
| AUDIENCE-04 | AUDIENCE | bug | Obsidian 'Your notes' move to a different person after a lead is deleted or a namesake is captured |  |  | open |
| AUDIENCE-05 | AUDIENCE | bug | Analytics 'What changed' shows +650% on flat numbers because the previous period was only partly captured |  |  | open |
| AUDIENCE-06 | AUDIENCE | bug | Leads CSV download keeps spreadsheet formulas written by commenters |  |  | open |
| AUDIENCE-12 | AUDIENCE | bug | Topic attribution counts each interaction as a qualified lead, giving '6 qualified leads' from 3 people and a 600% conversion rate |  |  | open |
| BRIDGE-01 | BRIDGE | bug | Reactors of someone else's post become your leads when you open its reactions list in the feed |  |  | open |
| BRIDGE-02 | BRIDGE | bug | In LinkedIn's rebuilt comment layout, commenters on every post in the feed are filed under the first post's author |  |  | open |
| BRIDGE-03 | BRIDGE | bug | Inserting a draft from the side panel records it as published before you press Post, and a scheduled post then never reconciles |  |  | open |
| BRIDGE-04 | BRIDGE | bug | A history import that stalls or hits its round cap is recorded as complete, and the studio then offers to delete real leads as 'not on your posts' |  |  | open |
| BRIDGE-05 | BRIDGE | bug | German and Italian LinkedIn pages store followers and impressions a thousand times too small, marked exact |  |  | open |
| BRIDGE-11 | BRIDGE | bug | 'Past 365 days' is not recognised, so a year's impressions are saved and charted as today's |  |  | open |
| PLATFORM-01 | PLATFORM | blocker | Restore refuses to run when the live database is damaged, which is exactly when a creator needs it |  |  | open |
| PLATFORM-04 | PLATFORM | bug | Follower counts read from LinkedIn's network responses are filed under whichever creator profile is active, whoever is signed in to LinkedIn |  |  | open |
| SETUP-01 | SETUP | bug | Another member's LinkedIn archive imports into the confirmed creator without a word: their posts, about, roles and connections become yours |  |  | open |
| SETUP-02 | SETUP | blocker | Step 2 can never complete for a creator whose LinkedIn address has an accented or non-Latin letter |  |  | open |
| SETUP-03 | SETUP | bug | Leads who commented on your archive-imported posts are declared 'engaged only with other people's posts' and offered for permanent deletion |  |  | open |
| SETUP-07 | SETUP | bug | One click on the small 'DELETE EVERYTHING THE STUDIO HOLDS ABOUT YOU' line wipes all history and figure readings, with no confirmation |  |  | open |
| WRITE-01 | WRITE | bug | With the studio open in two tabs, switching profile in one makes the other tab save its writing into the other creator's profile |  |  | open |
| WRITE-02 | WRITE | bug | After Publish, the Composer stays attached to the post, so writing the next post and pressing Save overwrites the published or queued post |  |  | open |
| WRITE-03 | WRITE | bug | Publish queues or sends the last saved text, not what is on screen, then replaces the UNSAVED mark so the unsaved edits are lost on the next reload |  |  | open |
| WRITE-04 | WRITE | bug | A Gemini key is exposed in plain text in /api/v1/egress/status and in the server log whenever a request fails |  |  | open |
| WRITE-10 | WRITE | bug | Posts written in Hindi, Gujarati, Chinese, Arabic or any non-Latin script can never be bound or attributed |  |  | open |
| WRITE-15 | WRITE | improvement | At its scheduled time a queued post is silently marked published although nothing was posted, and it then counts as a published post everywhere |  |  | open |
| WRITE-16 | WRITE | bug | With no model configured, Re-Hook, Command and the copilot write invented statistics and another author's background into the creator's post |  |  | open |

## High (S2): 50

| ID | Area | Kind | What was wrong | What changed | Test | Status |
|---|---|---|---|---|---|---|
| AUDIENCE-07 | AUDIENCE | bug | Universal search cannot find capitalised accented names or quoted terms, and returns unrelated help for them |  |  | open |
| AUDIENCE-08 | AUDIENCE | bug | Universal search never searches the creator's own LinkedIn posts |  |  | open |
| AUDIENCE-09 | AUDIENCE | bug | Analytics 'Post comparison' ignores imported LinkedIn posts and shows unmeasured studio posts as 0 impressions and 0% |  |  | open |
| AUDIENCE-10 | AUDIENCE | bug | Rounded LinkedIn figures (1.2K) are shown and compared as exact numbers |  |  | open |
| AUDIENCE-11 | AUDIENCE | bug | Follower count is thrown away whenever LinkedIn's analytics range is not 24 hours |  |  | open |
| AUDIENCE-13 | AUDIENCE | bug | Patterns screen contradicts itself: the same hashtag difference is 'mixed up with when you posted' above and 'conclusive' below, and the copilot is told to use it |  |  | open |
| AUDIENCE-14 | AUDIENCE | improvement | The lead dossier has no way to forget a person or write a note |  |  | open |
| AUDIENCE-15 | AUDIENCE | bug | Demo data seeded with INOX_DEMO_DATA stays in the install for good once the flag is off |  |  | open |
| AUDIENCE-16 | AUDIENCE | bug | Activity screen's 'Leads' list is ordered by a hash, so the newest captured people are missing |  |  | open |
| AUDIENCE-17 | AUDIENCE | improvement | 'Export to Obsidian' in Brand Studio can never refresh an existing vault |  |  | open |
| BRIDGE-06 | BRIDGE | bug | Insert into LinkedIn Composer types the draft into a comment box or an open message instead of the post composer |  |  | open |
| BRIDGE-09 | BRIDGE | bug | On your comments activity page, a stranger's comment that you replied to is saved as your own comment |  |  | open |
| BRIDGE-10 | BRIDGE | bug | A post you reposted is imported as a post you wrote when LinkedIn's rebuilt cards hide the author link, and nothing reports it |  |  | open |
| BRIDGE-12 | BRIDGE | bug | Setup's 'Connect the browser' step un-ticks while LinkedIn is open, because the bridge stops reporting when its tab is not in front |  |  | open |
| BRIDGE-25 | BRIDGE | bug | A short post that mentions a number of impressions or comments has that number stored as its own figures |  |  | open |
| PLATFORM-05 | PLATFORM | bug | The licence's profile limit is checked only when a profile is created, so one month of Agency keeps five profiles working forever |  |  | open |
| PLATFORM-06 | PLATFORM | bug | tools/licence_keys.py issues a monthly Agency licence that runs for a year unless --days is typed |  |  | open |
| PLATFORM-07 | PLATFORM | bug | Deleting a profile while work is running in it brings its folder back with the client's data, and that profile id can never be created again |  |  | open |
| PLATFORM-08 | PLATFORM | bug | The automatic pre-upgrade backups cannot be restored with `restore`, and the error tells the user to pass --into-active-profile |  |  | open |
| PLATFORM-09 | PLATFORM | bug | A restore that fails while writing media leaves the database already replaced, and the CLI only prints 'Error' without naming the safety backup |  |  | open |
| PLATFORM-10 | PLATFORM | bug | Restore accepts a backup written by a newer version, after which the studio refuses to start |  |  | open |
| PLATFORM-11 | PLATFORM | bug | Media upload has no size limit and reads the whole file into memory |  |  | open |
| PLATFORM-12 | PLATFORM | bug | Linux autostart and the desktop shortcut break for any install path containing a space, including the desktop shell's own 'Inox Hydra' binary |  |  | open |
| PLATFORM-13 | PLATFORM | bug | In portable data mode the update command tells the user to delete the folder that holds all their data |  |  | open |
| PLATFORM-15 | PLATFORM | bug | `reset` also resumes a paused queue and wipes the Brand Studio identity, while saying it clears only the AI provider and LinkedIn session |  |  | open |
| SETUP-04 | SETUP | bug | Importing LinkedIn's first (basic) archive ticks the archive step and stops watching Downloads, so the complete archive with your posts is never offered |  |  | open |
| SETUP-05 | SETUP | bug | A large Shares.csv takes about a minute to import and locks the database: drafts and bridge captures fail with 500 meanwhile |  |  | open |
| SETUP-06 | SETUP | bug | Distinct posts with the same words are merged into one and reported 'already here'; posts without a caption are dropped |  |  | open |
| SETUP-08 | SETUP | bug | 'Not you?' leaves the forgotten person's name and headline in Brand Studio, and confirming the right account does not replace them |  |  | open |
| SETUP-09 | SETUP | bug | Opening your own profile wipes the archive's full skills and roles down to the few the profile page shows; roles cannot be re-imported |  |  | open |
| SETUP-10 | SETUP | bug | Outbound says none of your reactions or comments have been imported right after the archive imported them |  |  | open |
| SETUP-11 | SETUP | bug | Sync All Activity says 'Autonomous activity sync started' when no browser opened, when only Chrome is installed, or when the bridge is not connected |  |  | open |
| SETUP-12 | SETUP | blocker | On a Mac, Safari unpacks the archive into a folder, and Setup can neither find it nor let you choose it |  |  | open |
| SETUP-13 | SETUP | bug | Today sends you to Setup to import your post history while Setup shows all five steps ticked |  |  | open |
| UX-06 | UX | bug | Setup reports what happened at the bottom of a long page, out of sight of the button you pressed |  |  | open |
| UX-08 | UX | bug | 'Copy the folder path' says 'Copied to the clipboard' when the copy failed |  |  | open |
| UX-09 | UX | bug | At phone width, lead dossiers and Docs articles get zero width and cannot be reached |  |  | open |
| UX-10 | UX | bug | Opening the profile switcher from the navigation tray draws it above the top of the window |  |  | open |
| UX-12 | UX | bug | The packaged studio ships without its help: every help topic in Docs shows 0 documents |  |  | open |
| UX-14 | UX | bug | 'Open the post' on Posts and 'Open in Bridge Browser' on Activity give no feedback and swallow failures |  |  | open |
| UX-15 | UX | bug | Local security promises drafts and the LinkedIn session never leave the machine, which the product contradicts |  |  | open |
| WRITE-05 | WRITE | improvement | Reloading or closing the tab silently discards unsaved writing: no autosave, no leave-page warning |  |  | open |
| WRITE-06 | WRITE | bug | Applying a hook replaces the whole post when a blank line contains a space or LinkedIn's blank-line spacer (U+2800), with no undo |  |  | open |
| WRITE-07 | WRITE | bug | Typing a Windows Alt-code bullet (Alt+7, Alt+0149) applies hooks and replaces the opening paragraph |  |  | open |
| WRITE-08 | WRITE | bug | The same draft open in two tabs: the later Save silently overwrites the earlier one, and the first tab still says SAVED |  |  | open |
| WRITE-09 | WRITE | bug | A post marked as published, queued or sent from the studio can never bind to its LinkedIn post when the creator opens it |  |  | open |
| WRITE-11 | WRITE | bug | Re-Hook and Command send the creator's profile, about text and top post openers to the provider, while the screen and help say only the selection or instruction is sent |  |  | open |
| WRITE-12 | WRITE | bug | When the configured provider fails (revoked key, no credit, outage), Re-Hook and Command silently return canned template text as a success |  |  | open |
| WRITE-13 | WRITE | bug | A provider that stalls mid-response hangs Re-Hook indefinitely, and repeated presses freeze the whole studio including Save |  |  | open |
| WRITE-14 | WRITE | blocker | The Anthropic provider defaults to retired model ids and the Prompt tab has no model field, so Claude cannot be connected from the interface |  |  | open |

## Medium (S3): 66

| ID | Area | Kind | What was wrong | What changed | Test | Status |
|---|---|---|---|---|---|---|
| AUDIENCE-18 | AUDIENCE | bug | Today's 'Reply to' shows old comments as 'JUST NOW' and lists people who only reacted |  |  | open |
| AUDIENCE-19 | AUDIENCE | bug | Lead dossier prints UTC times as if they were local |  |  | open |
| AUDIENCE-20 | AUDIENCE | bug | A lead who was scored zero is shown as 'Not scored' |  |  | open |
| AUDIENCE-21 | AUDIENCE | bug | 'VIP' on Analytics and post attribution uses 75 and seniority labels that do not exist, while the CRM uses 80 |  |  | open |
| AUDIENCE-22 | AUDIENCE | bug | Analytics takes 4 to 5 seconds to open at 2,000 posts and blanks again on every range change |  |  | open |
| AUDIENCE-23 | AUDIENCE | improvement | The lead stream has no search, filter or sort, so 5,000 leads are one scrolling list |  |  | open |
| AUDIENCE-25 | AUDIENCE | bug | Patterns page fails axe: scrollable regions are not keyboard reachable |  |  | open |
| AUDIENCE-26 | AUDIENCE | bug | Captured analytics days store 'members reached' as 0 although it is never read |  |  | open |
| AUDIENCE-27 | AUDIENCE | improvement | Post topics are classified with the original author's software vocabulary, so most creators get one bucket |  |  | open |
| BRIDGE-13 | BRIDGE | bug | The help article says commenters are captured on activity pages, but the reader skips every /in/ page |  |  | open |
| BRIDGE-15 | BRIDGE | bug | The analytics page says 'synced to your local studio' when the studio is not running or refused the browser |  |  | open |
| BRIDGE-16 | BRIDGE | bug | With network reading on, the exact figures are dropped on a busy page because every LinkedIn response counts against a 30 per minute cap |  |  | open |
| BRIDGE-17 | BRIDGE | bug | The popup reports states it never checked: 'LinkedIn Session: Active' from the browser cookie, and 'Side panel opened' after a failure |  |  | open |
| BRIDGE-18 | BRIDGE | bug | The side panel's queue invents 'Today at 5:30 PM' for a post with no time and renders post text as HTML |  |  | open |
| BRIDGE-19 | BRIDGE | bug | The side panel calls a draft 'Fold Safe' that the studio says is cut off by the fold |  |  | open |
| BRIDGE-20 | BRIDGE | bug | A reactions list that finishes loading within 4 s of the previous read is not read until something else on the page changes |  |  | open |
| BRIDGE-21 | BRIDGE | bug | Engagers seen while the studio was unreachable are never sent again on that page, even after the studio comes back |  |  | open |
| BRIDGE-22 | BRIDGE | bug | A post whose card carries only a ugcPost or share id is saved under an activity id LinkedIn never issued |  |  | open |
| BRIDGE-24 | BRIDGE | bug | Opening a repost's permalink can bind the reposter's URN to your studio post, after which your real post never binds |  |  | open |
| BRIDGE-26 | BRIDGE | improvement | The in-page notices on LinkedIn are not announced to screen readers |  |  | open |
| PLATFORM-16 | PLATFORM | bug | Switching to a profile whose database was written by a newer build answers a bare 500 Internal Server Error |  |  | open |
| PLATFORM-17 | PLATFORM | bug | The backups list is sorted by file name, so the newest backups are hidden and unrestorable .db files are listed first |  |  | open |
| PLATFORM-18 | PLATFORM | improvement | Installed copies read the update manifest from the main branch, so they are told about a release that does not exist yet |  |  | open |
| PLATFORM-19 | PLATFORM | bug | A custom profile id may be a Windows device name (con, nul, aux, prn, com1...), which cannot be a folder on Windows |  |  | open |
| PLATFORM-20 | PLATFORM | bug | Without a launcher next to the code, enabling autostart registers bare python, which does nothing at login |  |  | open |
| PLATFORM-21 | PLATFORM | improvement | The 'safe to post publicly' diagnostics bundle carries the OS account name in every path, and embeds earlier bundles |  |  | open |
| PLATFORM-22 | PLATFORM | improvement | The CLI backs up, restores and diagnoses only the active profile, cannot choose another, and never says which one it used |  |  | open |
| PLATFORM-23 | PLATFORM | improvement | Setting the computer's date back revives an ended licence |  |  | open |
| PLATFORM-24 | PLATFORM | bug | Before the studio has ever been started, `update enable` crashes and `backup` writes an empty archive and calls it a backup |  |  | open |
| PLATFORM-25 | PLATFORM | improvement | Exit in the tray leaves the server it started running with no window, and the only documented way to stop it is Task Manager |  |  | open |
| PLATFORM-26 | PLATFORM | bug | The Linux/macOS source launcher writes the server log to a shared /tmp file outside the app home |  |  | open |
| SETUP-14 | SETUP | bug | An import request older than 30 minutes shows 'WAITING FOR THE PAGE TO OPEN' forever, though the extension will no longer pick it up |  |  | open |
| SETUP-16 | SETUP | bug | Sync All's chain lives only in server memory: a studio restart mid-import silently drops the comments and reactions steps |  |  | open |
| SETUP-17 | SETUP | bug | Capture health lists nine parts including two 'Voyager ... interception' rows that stay NOT SEEN YET for everyone by default; the help says seven and tells you to open the page |  |  | open |
| SETUP-18 | SETUP | improvement | The help article never mentions 'Sync All Activity', and the button's copy contradicts the help's promise about what the studio does on LinkedIn |  |  | open |
| SETUP-19 | SETUP | bug | An archive imported before you confirm your profile cannot be deleted from Setup |  |  | open |
| SETUP-20 | SETUP | bug | Windows: a Downloads folder moved to another drive or into OneDrive is never searched |  |  | open |
| SETUP-21 | SETUP | bug | A download still in progress is offered, and opening it says 'That file is not a ZIP archive LinkedIn produced' |  |  | open |
| SETUP-22 | SETUP | bug | With only Chrome installed, step 1 tells you to 'load the extension by hand from the path below', but Setup shows no path |  |  | open |
| SETUP-23 | SETUP | bug | After an archive import, Posts and Patterns blame post age: 'your 0 posts at least a week old' for posts that are years old |  |  | open |
| SETUP-24 | SETUP | bug | The import result shows database column names: 'filled display_name, headline, about, location' |  |  | open |
| UX-16 | UX | bug | 'SAVE FAILED' hides its reason in a hover tooltip |  |  | open |
| UX-17 | UX | bug | Publish with nothing stored opens a dialog with no buttons that says 'Save the draft first', even right after a save failed |  |  | open |
| UX-18 | UX | bug | Modals do not take or hold keyboard focus; Tab walks the page behind the Publish dialog |  |  | open |
| UX-19 | UX | improvement | No addresses for screens: no deep links, Back leaves the studio, reload always lands on Today |  |  | open |
| UX-20 | UX | bug | Theme ignores the OS setting, is not remembered, and is only switchable from the Ctrl+K palette |  |  | open |
| UX-21 | UX | bug | Errors arrive as 'Failed to fetch' or a bare status code, and losing the server is never announced |  |  | open |
| UX-22 | UX | bug | Status marks that are not measured: a fixed 'DRAFT 01', an always-pulsing green 'Live' dot, a permanent online dot |  |  | open |
| UX-23 | UX | improvement | The Audit tab scores an empty draft 100 and says BLOCKED for advice, in team-role jargon |  |  | open |
| UX-24 | UX | bug | Inspector's Brand tab says Brand Studio 'IS NOT BUILT YET'; Command opens with 'ANTIGRAVITY LOCAL ENGINE' jargon |  |  | open |
| UX-25 | UX | bug | Phone width: the header's Search button is cut off, the fold label hides under the rail, Brand Studio tabs run off screen |  |  | open |
| UX-26 | UX | improvement | Media library: one-click delete that fails silently, hover-only controls, and uploads that can never be used in a post |  |  | open |
| UX-27 | UX | improvement | 'Add Creator Profile' is offered on a one-profile licence and refuses only after the form is filled |  |  | open |
| WRITE-17 | WRITE | bug | Double-clicking Save on a new draft creates duplicate drafts, and duplicates later stop the post from binding |  |  | open |
| WRITE-18 | WRITE | bug | A history import can take over an unpublished draft that reuses an old post's opening, marking it published with the old date |  |  | open |
| WRITE-20 | WRITE | bug | Text typed while a formatting request is in flight is silently thrown away |  |  | open |
| WRITE-21 | WRITE | bug | Clean formatting changes meaning: word ranges become lists, indentation is flattened, and '.env' is glued to the previous word |  |  | open |
| WRITE-22 | WRITE | bug | The Queue lists scheduled posts in UTC while the Composer, slots and Today use local time |  |  | open |
| WRITE-23 | WRITE | bug | The character counter and the 3,000 limit check give different answers for Indic scripts and emoji, and the counter never shows LinkedIn's limit |  |  | open |
| WRITE-24 | WRITE | bug | Provider and LinkedIn failures show only a bare status code ('400', '502') because the server's reason is an object the UI does not read |  |  | open |
| WRITE-25 | WRITE | bug | The Command console prints raw JSON and never sends the draft, although its placeholder offers to work with 'your draft' |  |  | open |
| WRITE-26 | WRITE | bug | Carousel deck slides render their title and body in black on the default dark theme |  |  | open |
| WRITE-27 | WRITE | bug | Carousel slides without a tag or name are labelled 'ARCHITECTURE' and signed 'Creator' |  |  | open |
| WRITE-28 | WRITE | bug | The profile switcher says '0 drafts' for a profile that has drafts |  |  | open |
| WRITE-29 | WRITE | bug | Generated images put disputed quotes under famous names (Seneca, Marcus Aurelius) |  |  | open |
| WRITE-30 | WRITE | bug | A Send to LinkedIn that times out is reported as 'nothing was scheduled', inviting a retry that can schedule the post twice |  |  | open |

## Folded into another finding: 18

| ID | Why |
|---|---|
| AUDIENCE-24 | duplicate of UX-09 |
| BRIDGE-07 | duplicate of WRITE-10 |
| BRIDGE-08 | duplicate of SETUP-09 |
| BRIDGE-14 | duplicate of AUDIENCE-11 |
| BRIDGE-23 | duplicate of PLATFORM-04 |
| PLATFORM-02 | duplicate of WRITE-01 |
| PLATFORM-03 | duplicate of UX-12 |
| PLATFORM-14 | duplicate of WRITE-04 |
| SETUP-15 | duplicate of BRIDGE-12 |
| UX-01 | duplicate of WRITE-02 |
| UX-02 | duplicate of SETUP-07 |
| UX-03 | duplicate of WRITE-03 |
| UX-04 | duplicate of WRITE-15 |
| UX-05 | duplicate of WRITE-22 |
| UX-07 | duplicate of WRITE-24 |
| UX-11 | duplicate of WRITE-07 |
| UX-13 | duplicate of WRITE-05 |
| WRITE-19 | duplicate of BRIDGE-03 |
