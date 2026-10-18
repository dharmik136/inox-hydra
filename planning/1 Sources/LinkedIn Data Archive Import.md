---
type: source
status: proposed
tags:
  - source
  - sanctioned
  - onboarding
---

# LinkedIn Data Archive Import

LinkedIn's own export: Settings, Data privacy, "Get a copy of your data". The download link lasts 72 hours.

**Known contents:** `Connections.csv` (first-degree connections: name, email only where they chose to share it, company, position, connected on); `Comments.csv` (date, link to the post, the comment text). Profile, positions, skills, posts and reactions files are also part of the full archive; confirm exact file and column names against a real archive before building the parser.

**Why it matters:**
- It is the creator's own data, handed over by LinkedIn. No scrolling, no page reading, no terms question. See [[Risk - LinkedIn terms and detection]].
- Day-one history: years of posts and comments in one import instead of a scrolled [[History Import]].
- It brings a node the product has never had: [[Connection]].

**Writes:** [[Creator Identity]], [[Creator Positions and Skills]], [[Own Post]], [[Outbound Engagement]], [[Connection]].

**Roadmap:** [[Phase 1 - Own Data Complete]].
