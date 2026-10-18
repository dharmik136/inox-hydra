---
type: source
status: live
tags:
  - source
  - extension
code: studio/extension/content.js
---

# Comment and Reaction Reader

Reads the people who engaged with the creator's posts, from the page the creator has open.

**Reads on:** `/feed/`, `/posts/`, `/feed/update/...activity-N`. Profile pages are excluded on purpose.

**Captures, per person:** name, headline, company (parsed from "at" or "@" in the headline), profile URL, comment text (first 140 chars), the post URN, the post author. Reactors only come from a verified reaction modal, never from a bare list in any dialog.

**Sends to:** `POST /api/v1/crm/interactions/ingest`, one call per person, through the worker relay.

**Writes:** [[Lead]], [[Lead Interaction]], scored by [[ICP Scorer]], admitted only through the [[Engagement Gate]].

**Feeds:** [[Reply Queue]], [[Lead Dossier and DM]], [[Patterns and Attribution]], [[Audience Pack]].

**Known issues:** [[Gap - Lead fields mislabelled]].
