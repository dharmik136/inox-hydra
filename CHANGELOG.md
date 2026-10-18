# Changelog

What changed for someone running the studio, newest first. The master plan
asks for an entry per release (`docs/PACKAGING_AND_MAINTENANCE_MASTER_PLAN.md`
section 5.5); this file starts with the work since v2.5.2, which was never
released. Version numbers follow `studio/__version__.py`.

## Unreleased

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
