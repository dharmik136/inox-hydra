# Changelog

What changed for someone running the studio, newest first. The master plan
asks for an entry per release (`docs/PACKAGING_AND_MAINTENANCE_MASTER_PLAN.md`
section 5.5); this file starts with the work since v2.5.2, which was never
released. Version numbers follow `studio/__version__.py`.

## 2.6.0 (not yet released)

### Before you use 2.6.0: four things to do once

- **Reload the extension** on your browser's extensions page
  (brave://extensions, edge://extensions or chrome://extensions). A browser
  keeps running the old extension until then, and the old one reports some
  things the studio now refuses (it may still say "synced").
- **Open your own profile once** at `https://www.linkedin.com/in/me/` in the
  bridge browser. Analytics are now kept only when the browser is signed in to
  the LinkedIn account you confirmed in Setup, and this is how the extension
  learns which account that is.
- **Run one posts import** from Setup with the reloaded extension. Imports the
  old extension called complete can no longer be shown to have reached the end,
  so Today and the Leads review wait for one that does. Nothing is deleted.
- **Sample drafts from 2.5.1 are removed.** The 16 Launch Kit drafts an earlier
  version put into every install are removed on the first start, but only those
  you never edited, queued or published, and only after a backup of your
  database. Today tells you once what was removed and where the copy is.

- **A daily backup now runs on its own**, keeps about 14 copies, and checks
  each one as it is made. Brand Studio has a new **Storage and privacy** tab
  that shows what the studio holds, its retention rules, and its backups.
  Folding reactions older than two years into counts, and listing leads silent
  for two years, both ask you first; nothing of yours is removed without that.

### One name
- **The product is Inox Hydra**, and the extension is **Inox Hydra Bridge**.
  Before, it went by five names, one borrowing a competitor's mark.
  Shortcuts and the extension take the new name; a Startup shortcut made
  under the old one still works and is replaced the next time autostart is
  switched on. Your data stays where it was.

### Creator profiles
- **Each creator profile is its own database.** Profiles used to share one,
  so switching changed the avatar and nothing else. Now each profile has its
  own posts, drafts, leads, analytics, media, backups and exports, and
  nothing one holds appears in another. Your first profile is your studio as
  it was. Scheduled posts in every profile fall due on time, whichever one is
  open.
- Deleting a profile asks you to type its name, and removes its folder.

### Licence and prices
- **An offline licence.** Brand Studio, Licence: paste the key from your
  purchase, and it is checked on this machine with nothing sent anywhere.
  Free; Creator at $12 a month billed yearly, or $249 once with a year of
  updates; Agency at $39 a month for up to 5 creator profiles. During the
  beta every Creator feature stays open to everyone; a licence changes the
  number of profiles you can keep.

### Setup
- **Your LinkedIn archive is a Setup step.** The studio opens LinkedIn's
  "Get a copy of your data" page, finds the export in your Downloads folder
  once you say you asked for it, shows what it holds, and imports only what
  you keep ticked: your posts with their dates, your comments and reactions,
  your profile, roles, education and skills, and your connections (never
  their email addresses). Messages are never imported. Nothing the bridge
  captured is overwritten.

### The extension
- **Network reading is off unless you switch it on.** The part of the
  extension that wraps LinkedIn's page `fetch` to copy exact figures now
  runs only after you turn on "Read LinkedIn's network responses" in its
  popup, where what it does is written beside the switch.

### Your data
- **Export to Obsidian.** Brand Studio, Local security, Your data. Writes your
  posts, the people who engaged with them, your topics, the people whose posts
  you engage with, and your drafts as a folder of linked notes. Export again
  into the same folder to refresh it: notes you add, and anything under a
  "Your notes" heading, are kept. Also `python -m studio.cli export --format obsidian`.
- **The JSON and CSV exports carry your own LinkedIn record**: your profile,
  roles, education and skills, your posts with every reading of their figures,
  your comments and reactions elsewhere, and each lead's stage history. Before,
  none of it could be exported. Credentials are still never included.

### Writing
- **Drafts in your own voice.** When a model is configured, the copilot's hooks
  are now written from who you are and how you write: your headline, roles,
  skills and about, measured habits from your own posts (length, paragraphs,
  how often you open with a question), and the openers of yours that drew the
  most reactions. Each part is sent only when there is real data for it, and
  the response records which parts went.

### Fixed
- An installed copy of the studio starts again. The package left out the
  folder that holds most of its API routes, so a fresh install failed at its
  first import; CI now finds every package on disk instead of trusting a list.
- Carousel slides are signed with your own name and headline from Brand Studio
  (or your confirmed LinkedIn profile), or left unsigned. They used to fall back
  to the original author's job title, which every new user's slides carried.
- The command engine, the hook rail and the repurposer write for you, using the
  same voice pack as the copilot, instead of a system prompt describing one
  particular author.
- A first-message draft no longer tells someone who only reacted to your post
  that they commented on it. Every lead the bridge captured was labelled
  "Commented"; the label now follows how they actually engaged, and leads
  captured before this are corrected from their own records when the studio
  upgrades its database (a backup is taken first, as always).
- A captured lead's LinkedIn profile link is stored where the dossier reads it.
- Follower counts read from LinkedIn's network responses were never saved: the
  write named a column that does not exist, and failed every time without a
  trace. They are saved now. The impressions figure beside them is not, because
  it covers a period the response does not name.
- A post placed in LinkedIn's composer from the side panel is recorded again,
  so it can be linked to its LinkedIn post once published.
- An activity page reached through LinkedIn's `/in/me/` address is read as
  yours only when nothing in the browser says it belongs to another account.
- The Composer works in a narrow window: below 1024 pixels the inspector opens
  as a drawer over the editor instead of squeezing it out, and its close
  control can no longer be pushed out of reach by its own tab labels.
- The Activity screen follows the light theme and meets contrast, and no
  longer names a browser that has not reported in.
- Posts, Patterns and Outbound keep their heading before anything is imported,
  and every screen has one level-one heading for screen readers.
- Rail labels no longer stay over the page after you click a section.
- Reload on brave://extensions no longer fails with "Cannot load extension
  with file or directory name __pycache__". The packaging script lived in the
  extension folder, and running the tests left a Python cache beside the
  manifest; it now lives in `tools/`.

### Ready for a normal creator, and for years of data

A second cycle: four research reports (install, backend, frontend, data at
scale), owner decisions, seven parallel batches, an independent review of each
and a re-check of every fix sent back. The plan is
docs/quality/CYCLE2_2026-10_PRD.md.

#### Installing and updating
- The release smoke test passes the studio's own security gate, so a 2.6.0
  release can actually publish its portable ZIP and update manifest.
- The desktop app installer includes the studio interface instead of opening
  on an error page.
- macOS and Linux builds carry their own pinned, checksum-verified Python, and
  a build that would depend on the build machine's Python now fails instead of
  shipping.
- A release is published only when the portable ZIP, the update manifest and
  the Windows installer are all on it; until then it stays a draft nobody
  sees.
- The portable launcher opens the studio only once it is really running, says
  when another program holds port 8000, and shows the engine's error instead
  of a page that cannot connect.
- When another program uses port 8000, the portable launcher starts the studio
  on the next free port and says that the browser extension needs 8000.
- Double-clicking create_desktop_shortcut.vbs in the portable folder now makes
  a working desktop shortcut.
- The README inside the download no longer points at a store listing that does
  not exist.
- The studio's Docs screen in a downloaded copy shows the help articles only,
  not the project's internal engineering documents.
- The install, upgrade and removal instructions match what the Windows
  download does today, and macOS and Linux users are told to run from source
  for now.
- Hindi and Gujarati quote overlays appear on generated images in the Windows
  download and desktop app, which now include the text layout library Pillow
  needs.

#### Writing, drafts and publishing
- A queued post missed while the computer slept now waits as due at its own
  time, and Today says it was missed, with Post now and Move to next slot; it
  is never moved without asking.
- Your weekly posting slots can now be added, retimed, renamed and removed on
  the Queue, and start with plain names such as Monday morning.
- New studios start with neutral fill-in hook forms; the engineering creator
  pack of 36 forms is now an opt-in from the Swipe File.
- The Composer now has Drafts and New post: see every draft, open, find or
  delete one, and clearing the editor never saves over an earlier draft.
- Publish's main action is now Copy and mark posted: it copies the exact text
  and records it as posted by you, with Queue it beside it and a Copy button
  in the Composer.
- Send to LinkedIn now names you as the author, sends only as the account you
  confirmed after asking with that account and the time, refuses times
  LinkedIn will not hold, and keeps a record of each send and LinkedIn's
  answer.
- Removed POST /api/v1/scheduler/native/stage, an unguarded duplicate of Send
  to LinkedIn.

#### Images
- Images: a generation that fails or is blocked now says so and why, and
  nothing is added to your library; choose who makes your images (the free
  public generator, your OpenAI, Google Imagen, Stability AI, Replicate,
  fal.ai or Together account, or AUTOMATIC1111, Forge or ComfyUI on your own
  machine, or Off) in the Prompt tab, with what leaves your computer shown for
  each. Image providers never follow a redirect to another address, and if you
  already made images with an OpenAI or Gemini key, the studio keeps using the
  model you had until you choose another.
- Images: quotes and your watermark are drawn at full size on Windows, macOS
  and Linux, and Hindi and Gujarati quotes and names are drawn in their own
  letters instead of boxes.

#### Everyday screens, help and restore
- Reply to their comment drafts straight away from the post the person
  commented on, without asking you to type it.
- Screens that could not load while the studio was stopped recover by
  themselves when it is back, and Queue, Leads and Posts stay current while
  open.
- Activity and Setup stop asking the studio for updates while their window is
  hidden.
- Help and search show creators the help articles only; maintainer and retired
  documents no longer appear unless developer mode is on.
- Docs lists the help articles only; the studio's engineering documents and
  retired manuals are no longer part of the customer's library.
- Brand Studio can now restore a backup: Local security, Your data, Restore. A
  safety backup is taken first, and people you forgot after the backup was
  made stay forgotten.
- The import of your LinkedIn history has one name, Import your history, on
  Setup, Today and Activity.
- Setup says when it is done and takes you to Today.
- Times on a screen use one clock format, a queued post shows its date, and an
  unread figure on Activity reads not measured instead of 0.
- Patterns compares each form once, in plain words, and no longer says Other
  posts posts.
- The help on saving a post no longer tells you to reload before starting the
  next post.
- The studio opens straight on Setup or Today without flashing the Composer
  first.
- The bridge mark beside Activity always agrees with the screen under it.
- Demo mode now includes a sample creator with posts and people who engaged,
  so Today, Posts, Patterns and Outbound show data.
- After you mark a post as published, Today names it until the bridge sees it
  on LinkedIn.
- Today's status line no longer says nothing was captured when your posts are
  already imported.
- Search names a lead's stage as Leads does.
- In the Composer, Ctrl+S saves and Ctrl+B, Ctrl+I and Ctrl+U format the
  selection.
- Empty Posts, Patterns and Outbound screens have a Go to Setup button.
- After copying a message on Leads you can mark the person as Outreach Sent in
  one click.
- Forgetting a lead says that older backups keep them until rotation, and
  where to remove them from backups too.

#### Speed with years of data
- Posts, Analytics, Patterns, Outbound, Today, Activity and the Leads review
  open in under a tenth of a second on years of data, where they took up to
  two seconds.
- Search answers as you type, in milliseconds, on years of data; it matches
  words from their start, so 'pric' finds pricing, and finds words you wrote
  in bold or italic.
- Exporting your data needs about 20 MB of memory however much you have, where
  three years took over a gigabyte.
- The database keeps its query statistics current, after updates and while the
  studio runs.
- The Leads screen opens at once however many leads you have, and searches on
  the server.

#### Storage, retention and privacy
- Forgetting someone now overwrites their words in the database file on every
  system, and Storage and privacy says how long they stay in older backups and
  can remove them from backups too.
- The studio now backs itself up once a day, checks every backup as it is
  made, stores photos without recompressing them, and keeps about 14 automatic
  backups and the last 2 pre-upgrade copies instead of every one ever made.
- New Storage and privacy tab in Brand Studio: see what each kind of data
  takes, choose how long readings and logs are kept, preview every cleanup
  before it runs, fold two-year-old reactions into counts without changing any
  number on screen, and review people who have been silent for two years.

#### Reliability and privacy under the hood
- A comment cut through an emoji is now captured as a lead, and any failure
  inside the studio answers a readable sentence instead of 'Internal Server
  Error'.
- When the database is busy or the disk is full, the studio says so and asks
  you to try again, and the rest of the studio keeps answering meanwhile.
- The diagnostics file and the studio's log no longer contain searches,
  message topics, names or profile addresses.
- Starting the studio keeps the previous session's log as engine.log.1 instead
  of deleting it.
- A grounding source that hangs no longer freezes the preview or leaves
  programs running.
- Grounding sources started with npx now work on Windows.
- Grounding sources no longer receive the studio's API keys.
- A grounding source that fails now says why.
- If the studio's database is damaged, the studio still opens and offers to
  restore your newest backup.
- Telemetry no longer grows with oversized payloads and loses nothing when the
  studio stops.
- Telemetry no longer keeps text or names, and forgetting your identity clears
  it.
- Deleting a media file now removes it, or says it could not and keeps it in
  the library.
- A very short image concept gets a clear message instead of an error.
- Removed about thirty unused API routes (listed in the commit); anyone
  scripting against them should use the studio's own routes. Telegram ingress
  is now a maintainer feature that needs INOX_DEV_MODE=1.

### Fixed before release

A quality cycle before the first paid release: six audits used the studio the
way a new customer would, 160 findings were triaged to 142 real defects
(26 very high, 50 high, 66 medium), and every fix was independently reviewed
and carries a test. The register is in docs/quality/BUG_REGISTER_2026-10.md.

#### Setup and your LinkedIn history
- The archive preview says whose archive it is, and an archive in someone
  else's name, or imported before you confirm your profile, is imported only
  when you tick a box naming you both.
- Importing LinkedIn's first, basic archive no longer ends the archive step:
  Setup keeps looking for the complete archive with your posts, and an account
  with no posts can say so.
- Importing a large LinkedIn archive takes seconds rather than a minute,
  drafts and bridge captures keep saving while it runs, and an import cut off
  part way can be removed.
- Posts with the same words on different days import as separate posts, and
  image, video or document posts without a caption are imported instead of
  dropped.
- An archive Safari unpacked into a folder is found in your Downloads folder,
  and Setup's archive step can be pointed at a folder with Choose the folder.
- What an archive import added can be removed from the archive step, even
  before you confirm your profile, and what the bridge has read since is kept.
- On Windows, Setup looks for the archive in your Downloads folder even after
  you moved it to another drive or into OneDrive, and says which folder it is
  watching.
- A LinkedIn archive still downloading is shown as STILL DOWNLOADING instead
  of being offered and then refused as a broken file.
- The archive import result names what it filled in plain words and says why
  rows were skipped.
- Setup now recognises your profile when your LinkedIn address contains
  accented or non-Latin letters (for example josé, müller, 王伟, राहुल).
- Leads who commented on posts brought in from your LinkedIn archive are
  recognised as yours and are no longer offered for removal as 'engaged only
  with other people's posts'.
- A history import that stalls, hits its limit or reads nothing is recorded as
  partial, and Setup says so; only an import that reaches the end of your
  posts lets Leads call anyone 'not on your posts'. If your browser still runs
  the extension from before the update, Setup and Today say to reload it on
  the browser's extensions page before importing again.
- Deleting everything the studio holds about you now shows what will be
  deleted, says whether a backup exists, offers one, and asks you to type
  'delete' first.
- Removing the wrong account in Setup now also clears the name, headline and
  company it filled in Brand Studio, unless you changed them.
- Opening your own profile no longer cuts the skills and roles read from your
  archive or the full lists down to the few the profile page shows.
- Import all three now says what actually happened: which browser opened, in
  what order the imports run, or why nothing could start.
- Setup's 'Your history' step now ticks only once your posts have been read to
  the end of the list, so Today never sends you to a Setup that looks
  finished.
- In Setup and Today, the result of a click, including errors, now appears
  next to the button you pressed.
- An import you asked for more than 30 minutes ago now reads 'Expired, click
  Import again' instead of waiting forever.
- Import all three carries on through comments and reactions even if the
  studio restarts mid-import, and Setup shows which import is running.
- Capture health no longer lists two network-reading rows that stay 'not seen
  yet' unless you turned network reading on.
- Setup's 'Sync All Activity' is now 'Import all three', with a plain
  description, and the help explains it.
- With only Chrome installed, Setup's first step shows the extension folder
  and how to load it by hand; with no suitable browser it says to install Edge
  or Brave.
- A history import no longer turns a new draft that reuses an old post's
  opening into that old published post.
- The Activity screen's Leads list now shows the people just captured first.
- Today's Reply to shows when someone commented rather than when the comment
  was last re-read, and leaves out people who only reacted.

#### The browser extension
- Opening the reactions list of someone else's post in your feed no longer
  files its reactors as your leads; a list whose post the bridge cannot tell
  is not saved.
- In LinkedIn's rebuilt comment layout, commenters on other people's posts are
  no longer filed under your post.
- On a German, Italian, French or other non-English LinkedIn, followers and
  impressions are read correctly (8.210 is 8210), and a figure the bridge
  cannot read with certainty is no longer saved.
- Analytics read with LinkedIn's 'Past 365 days' (or a range in another
  language) are no longer saved and charted as today's figure.
- Analytics and follower counts are saved only when the browser is signed in
  to the LinkedIn account confirmed in Setup; open
  `https://www.linkedin.com/in/me/` once in the bridge browser so it knows which
  account that is.
- Insert into LinkedIn Composer no longer types your draft into an open
  comment box or a message.
- A stranger's comment you replied to is no longer saved as your own comment.
- A post you reposted is no longer imported as one you wrote.
- Setup's 'Connect the browser' step no longer unticks while you read Setup
  with LinkedIn in the tab beside it.
- A post that mentions a number of impressions or comments no longer has that
  number stored as its own figures.
- Your follower count is saved whatever range LinkedIn's analytics page shows.
- The extension help no longer says leads are captured on your activity pages.
- The analytics notice on LinkedIn no longer says 'synced' when the studio was
  closed, unpaired or refused the figures.
- With network reading on, the exact analytics figures are no longer dropped
  on a busy LinkedIn page.
- The extension popup's LinkedIn Session line shows whether the studio holds a
  session, and its side panel button says when the panel could not open.
- A short reactions list that finishes loading just after it opens is now
  captured.
- Engagers seen while the studio was not running are captured once it is back,
  without reloading the page.
- A post whose LinkedIn card shows only a document or share id is no longer
  saved under an id LinkedIn never issued.
- Opening a repost of your post no longer links the repost to your studio post
  in place of the real one.
- The bridge's notices on LinkedIn are announced to screen readers and stay on
  screen longer.
- Captured analytics days no longer report a members reached of 0 that was
  never read.

#### Writing and publishing
- Reloading or closing the studio with unsaved writing in the Composer now
  asks before the text is lost.
- Applying a hook no longer replaces the whole post when blank lines hold a
  space or LinkedIn's blank spacer, and a new Undo button puts your opening
  back.
- Typing a Windows Alt code such as Alt+0149, or Alt and a number in another
  field, no longer applies a hook over your opening.
- Saving a draft that was changed in another window since you opened it is now
  refused with an explanation, and Keep this version lets you replace it on
  purpose.
- Double-clicking Save on a new post no longer creates duplicate drafts.
- Words typed while Bold, Italic or Clean is still working are no longer
  thrown away.
- Clean formatting no longer turns ranges like Mon-Fri into lists, flattens
  indentation, or glues '.env' to the word before it.
- The Composer's character count now shows LinkedIn's 3,000 limit and agrees
  with the Audit for Hindi, Gujarati and emoji.
- When a save fails, the Composer now says why on screen instead of in a hover
  tooltip.
- Every studio screen now has its own address, so reloading keeps your place,
  links open the right screen, and Back moves between screens.
- The studio now follows your computer's light or dark setting, remembers your
  choice, and has a theme button in the top bar.
- The header no longer shows a fixed DRAFT 01 or a green 'live' dot when the
  bridge has not been seen.
- At phone width the header's Search button and the Composer's fold label stay
  on screen.
- Deleting a media file now asks first and reports a failure, and the Composer
  no longer suggests it can attach files or show carousel slides.
- A queued post's text can be corrected from the Queue with Edit text, and a
  save over a queued or published post now asks before changing it or saves
  your text as a new draft, instead of overwriting it by accident.
- With the studio open in two windows, switching profile in one now tells the
  other, and the other's saves are refused instead of landing in the wrong
  creator's profile.
- After Publish the Composer clears for the next post; writing the next post
  no longer overwrites the one you just published or queued.
- Publish saves what is on screen first, so Queue it and Send to LinkedIn act
  on the text you see, and the dialog shows which post it is acting on.
- Publish on an empty or unsavable draft explains why in the status strip
  instead of opening a dialog with no way out.
- The Queue no longer records a post as published when its time comes: it
  moves to Due on the Queue for you to post, and counts as published once you
  press I posted it or the bridge sees it on LinkedIn.
- Inserting a post from the side panel no longer records it as published
  before you post it, and no longer makes a second copy of a queued post.
- A post you marked as published, queued or sent to LinkedIn from the studio
  is now linked to its LinkedIn post when you open it, so its engagers are
  attributed.
- Posts written in Hindi, Gujarati, Chinese, Arabic, Russian or any other
  script can now be linked to their LinkedIn post, and the side panel says
  when a post cannot be identified.
- The Queue lists posts at your local time, matching the Composer and Today.
- Errors such as a wrong AI key or a refused Send to LinkedIn now show the
  reason instead of a bare '400' or '502'.
- When the studio stops answering, every screen says so in one line instead of
  'Failed to fetch', and the line goes away when it is back.
- The side panel's queue no longer invents a time for an unscheduled post, and
  shows text in angle brackets as written.
- The side panel's Fold Safe verdict and character count now agree with the
  studio's.
- If LinkedIn does not answer a Send to LinkedIn, the studio says the post may
  already be scheduled and holds back a second send until you have checked.
- The Publish dialog keeps keyboard focus while open and returns it to Publish
  when closed.
- The Publish dialog says plainly that Send to LinkedIn sends the post's text
  and uses your saved LinkedIn session.

#### Your own AI provider
- Your AI provider key no longer appears in the Local security data, the
  server log, error messages or the diagnostics bundle; Gemini's key is sent
  in a header instead of the address.
- With no AI provider set up, nothing is written for you that you did not say:
  Re-Hook offers fill-in templates with a [bracket] for each fact of yours,
  and Command says a model is needed.
- The Prompt tab now lists exactly what goes to your AI provider, including
  the parts of your profile and posts sent to match your voice, and each
  Command answer says what was sent with it.
- When your AI provider refuses your key, runs out of credit or fails, Re-Hook
  and Command now tell you why instead of quietly showing templates, and the
  Prompt tab shows the last failure.
- A stalled AI provider can no longer freeze the studio: requests stop after
  40 seconds, Re-Hook shows that it is working, and pressing it again while it
  runs does nothing.
- Claude can be connected from the Prompt tab again, with current models, and
  you can now choose the model there for any provider.
- The Command console shows the model's answer as text, not JSON, and can
  include your Composer draft when you tick the box.
- Carousel slide titles and text now show in the theme's colours instead of
  black.
- Carousel slides are no longer headed ARCHITECTURE or signed 'Creator' when
  you have not given a tag or a name.
- Generated images no longer put stock quotes under famous names or sign
  quotes 'Leadership'; only words you typed are drawn.
- The Audit tab no longer scores an empty draft, and its checks read as advice
  (WORTH A LOOK) without team-role jargon.
- The Linux and macOS source launcher now keeps its log in the app's logs
  folder, where the diagnostics bundle finds it, and tells you if the server
  did not start.
- The Prompt tab says plainly when no AI model is set up, instead of showing
  an internal engine name.

#### Leads, messages and your Obsidian vault
- Lead drafts no longer claim an architecture blueprint, an engineering
  background or a tech stack: they use only the person's record and what you
  type, and Offer something offers only what you name.
- Forgetting a lead now removes their stage history too, from the studio and
  every export, and it no longer comes back if the same person engages again.
- Exporting to Obsidian again never overwrites a note you wrote or edited: a
  generated note that would take its name is written under another name, and
  the export says so.
- In an Obsidian vault, each note stays with the same person or post across
  exports, so your notes no longer move to someone else when a namesake is
  added or removed, and a renamed person or draft moves to the new name with
  your notes.
- The Leads CSV shows a commenter's name or headline that starts with = or @
  as text instead of running it as a spreadsheet formula, and its Status
  column matches the screen.
- In a lead's dossier you can now edit your notes and forget the person, which
  removes them and everything the studio recorded about them.
- Demo data no longer stays once the studio starts without INOX_DEMO_DATA:
  untouched sample people, drafts, posts and figures are removed after a copy
  of the database is saved to the backups folder, and anything you queued,
  published or edited is kept.
- Export to Obsidian in Brand Studio now refreshes the same vault each time,
  keeping what you wrote in it, and says what it kept.
- The lead dossier shows times and dates in your own time zone.
- A lead scored 0 now shows 0 and its tier instead of 'Not scored'.
- A post's VIP lead count uses the same 80-point rule as the rest of the
  studio.
- The lead stream can be searched by name, company, headline or notes and
  filtered by stage, and long lists load 200 at a time.
- On a phone-sized window, choosing a lead opens their dossier full width,
  with a way back to the list.

#### Analytics, patterns and search
- Analytics no longer reports a rise such as +650% when the previous period
  was barely captured: a change is shown only when both periods have at least
  80% of their days, compared per captured day, and the screen says how many
  days each has.
- Figures LinkedIn rounded (1.2K) are marked approximate on Analytics, and a
  change smaller than that rounding is not reported.
- Analytics' Post comparison now lists your posts imported from LinkedIn, and
  a figure nobody read shows 'not measured' instead of 0 or 0%.
- Analytics opens quickly with thousands of posts and no longer goes blank
  when you change the range.
- Search finds people whose names have accents or umlauts however you type
  them, ignores quotes around a word, and no longer offers unrelated help for
  such names.
- Search now finds words in your posts imported from LinkedIn.
- Patterns counts each person once per topic, and its qualified share can no
  longer read above 100%; Outbound's 'On your posts' counts posts, not
  interactions.
- Patterns no longer calls a comparison conclusive, or passes it to the
  copilot, when its two sides come from different years.
- Patterns' topics are now the words and hashtags your own posts share, not a
  fixed software vocabulary, and the screen says they are a keyword grouping.
- The Patterns page can be scrolled with the keyboard.
- After an archive import, Outbound says how many reactions and comments were
  imported and how to add their authors, instead of saying none were imported.
- After an archive import, Posts and Patterns say your imported posts have no
  figures yet and how to read them, instead of saying they are too new.

#### Profiles, licence, backups and installing
- Restore works when the studio's database is damaged: the damaged file is
  kept in the safety backup and the good backup goes in.
- When an Agency licence ends, profiles beyond the free tier stay on disk and
  listed but closed until it is renewed; they can still be backed up, exported
  or deleted, and your first profile always works.
- Deleting a creator profile while an image generation or other work for it is
  running no longer leaves its folder behind.
- The automatic database copy taken before an upgrade can now be restored with
  the restore command.
- A restore that fails part way now changes nothing and tells you where the
  safety backup is.
- Restoring a backup made by a newer version is refused with a message to
  update the studio first, instead of leaving a studio that will not start.
- Large media uploads no longer load the whole file into memory, and files
  over the size limit are refused with a clear message.
- On Linux, autostart and the desktop shortcut now work when the studio is
  installed in a folder whose path has a space.
- The update command no longer tells a portable-mode user to delete the folder
  that holds their data.
- `reset` now clears only the AI setup and the LinkedIn session; a paused
  queue stays paused and the Brand Studio profile is kept.
- Switching to a profile written by a newer version now says why it cannot
  open, instead of a server error.
- Brand Studio's backups list now shows your newest backups first.
- Update checks now report only versions that have actually been released.
- A creator profile can no longer be given an id Windows cannot use as a
  folder name, such as 'con' or 'aux'.
- The diagnostics bundle no longer contains your computer account's folder
  name, or a copy of the previous bundle.
- The command-line backup, export, restore and doctor now say which creator
  profile they used, and take --profile, with --all for backup and export.
- Setting the computer's clock back no longer brings an ended licence back,
  and a clock that was once set far ahead no longer locks out a valid licence.
- Command-line commands run before the studio's first start now explain that
  there is no data yet, instead of crashing or writing an empty backup.
- In the Windows tray, Exit now also stops the studio server the tray started.
- The packaged studio now ships its help articles; every help section in Docs
  is filled.
- The profile switcher now shows the right number of drafts for each profile.

#### Across the studio
- Copy the folder path on an empty Leads screen no longer says 'Copied' when
  the clipboard was unreachable; it shows why and selects the path. The lead
  dossier's COPY and Activity's copy URN confirm only once the copy happened.
- Open the post on Posts and Open in Bridge Browser on Activity now show that
  they are working and then say which browser opened, or why none could.
- The profile switcher opened from the navigation tray now opens below the
  profile card instead of above the top of the window.
- The navigation tray scrolls on short laptop screens, so Docs and Brand
  Studio are reachable, and Brand Studio's tabs wrap on a phone instead of
  running off screen.
- The command palette, navigation tray and profile switcher now keep keyboard
  focus while open, close with Escape one layer at a time, and give focus back
  to what opened them.
- On a licence with no room for another creator profile, the profile switcher
  explains the limit instead of offering a form that is refused after you fill
  it in.
- Brand Studio's Local security no longer says drafts and the LinkedIn session
  never leave this machine; it lists what stays and exactly which actions send
  what, and where.
- The inspector no longer says Brand Studio is not built, the Command screen
  no longer opens with an internal engine codename, and the Activity screen is
  called Activity everywhere it is linked.
- Switching profile with unsaved Brand Studio edits now asks first, and says
  which unsaved work would be lost.
- Help articles in Docs are readable on a phone-width window; before, opening
  one changed nothing on screen.
- Typing a search on the Docs home screen keeps every letter; it used to keep
  only the first.
- The LOCAL shield on the rail no longer says all processing is local: it says
  your work is kept on this machine and where to see what leaves it.
- Activity's Imports tab says how each import ended in words, and shows only
  an import read to the end as complete.
- Activity says when the studio last answered instead of "Live updates on",
  says so when the studio stops answering, and the header button is called
  Activity.
- With an AI provider connected, hooks are no longer written for "Engineering
  & Product Leaders" unless you asked for that audience.
- The Distribution audit no longer quotes reach penalties nobody measured,
  such as "-40% algorithmic reach penalty"; it says what it found in your
  draft.
- The command-line reference describes what reset clears today: the AI
  provider settings and the LinkedIn session, nothing else.
- The release notes no longer tell a portable-mode user to delete the folder
  that holds their data.
- The README, the docs and the command-line help name only Claude models
  Anthropic still serves.
- An import that pauses because its LinkedIn tab is hidden now says so in
  Setup, and that the tab must be in front, instead of SCROLLING NOW.
- Today shows posts that are due to post now, with Copy text and I posted it.
- After the studio removes sample content an earlier version added, Today says
  once what it removed and where the copy of your database from before is.
- In a lead's dossier, a copy the browser refuses now points to the text above
  it, and the message goes once a copy works.

### For developers
- The repository no longer holds the owner's own posts, figures, post
  graphics or Taplio scripts, or real members' names; demo seeds use
  labelled samples.
- The desktop shell's installer now carries the name Inox Hydra. A
  development install made under the old name is not upgraded in place;
  uninstall it first. No release ever shipped the desktop shell.
- CSV exports prefix a cell that begins with =, +, - or @ with an
  apostrophe, so a name or comment someone else wrote cannot run as a
  spreadsheet formula.
- `tools/licence_keys.py` makes the licence signing key outside the
  repository and issues licences. Ed25519 is the RFC 8032 reference code,
  checked against the RFC's vectors.
- `tools/ui_audit.py` drives every screen in both themes at desktop and phone
  width and reports console errors, egress, failed API calls, accessibility
  violations and overflow, with screenshots. CI runs it on Linux.
- Playwright is installed in CI, so the browser suite runs instead of skipping.
- No test starts a real browser. Setup's sync test launched Brave on every
  run on a machine that had it, pointed at the live studio, and left the
  window open; the launcher's process calls are now recorded instead.
- Agentation, a dev-only review toolbar, sends element-anchored notes to an
  agent through `agentation-mcp` (`.mcp.json`). It never enters a build.
- `npm run dev` works against any backend (`INOX_API_TARGET`) and receives the
  studio token before its first request.
- `planning/` is an Obsidian vault mapping what the bridge reads to what the
  product does with it, the open gaps, and the commercial roadmap.
- The README no longer claims an encrypted database, an air-gapped install, or
  an extension that does not wrap `fetch`. It describes what the code does.

### Since v2.5.2, before this entry
About 140 commits landed between v2.5.2 and the work above. The larger pieces:

- A React interface replaced the vanilla page, with self-hosted fonts.
- Setup: the studio learns who you are from your own LinkedIn profile and
  imports your history, with capture health showing what each reader saw.
- Today, Posts, Patterns and Outbound: what to do in the next hour, which posts
  worked against your own usual and who they brought, and whose content you
  engage with.
- Lead dossiers with a drafted first message that says nothing the record
  cannot support, and a history of every lead's stage.
- Universal search, a help centre, and the playbook in Docs.
- One egress chokepoint with a ledger, and the AI key sealed at rest.
- Grounding drafts in your own material through MCP servers.
- A native desktop shell for Windows, macOS and Linux, with signed updates wired
  but off until keys exist.
- Creator profiles in the rail (their data is not yet separated; see
  `planning/6 Gaps/Gap - Account scoping is cosmetic.md`).
- Live activity stream, router split, terminal monitor and streaming AI.
