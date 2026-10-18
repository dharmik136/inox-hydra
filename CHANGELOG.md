# Changelog

What changed for someone running the studio, newest first. The master plan
asks for an entry per release (`docs/PACKAGING_AND_MAINTENANCE_MASTER_PLAN.md`
section 5.5); this file starts with the work since v2.5.2, which was never
released. Version numbers follow `studio/__version__.py`.

## 2.6.0 (not yet released)

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
