---
type: source
status: live
tags:
  - source
  - sanctioned
  - onboarding
---

# LinkedIn Data Archive Import

LinkedIn's own export: Settings, Data privacy, "Get a copy of your data". The download link lasts 72 hours.

**Live since 2026-10-19, as Setup step 4.** The studio opens LinkedIn's download page in the bridge browser; once the creator says they asked for it, it looks in their Downloads folder for LinkedIn's export names; it previews file by file; and it imports only what the creator keeps ticked. Messages are never imported, and connections never carry an email address.

**Read:** `Shares.csv` (posts, with dates and no figures), `Comments.csv`, `Reactions.csv`, `Profile.csv`, `Positions.csv`, `Education.csv`, `Skills.csv`, `Connections.csv`. Columns are matched loosely, and a file whose columns are not the known ones is reported with the columns found.

**Still to do:** run it on a real archive and adjust the column aliases to what LinkedIn actually ships today. The parser was built from LinkedIn's documented export, with synthetic fixtures.

**Why it matters:**
- It is the creator's own data, handed over by LinkedIn. No scrolling, no page reading, no terms question. See [[Risk - LinkedIn terms and detection]].
- Day-one history: years of posts and comments in one import instead of a scrolled [[History Import]].
- It brings a node the product has never had: [[Connection]].

**Writes:** [[Creator Identity]], [[Creator Positions and Skills]], [[Own Post]], [[Outbound Engagement]], [[Connection]].

**Code:** `studio/backend/archive_import.py`, `studio/ui/src/components/ArchiveImport.tsx`. **Roadmap:** [[Phase 1 - Own Data Complete]].
