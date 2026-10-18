---
type: gap
status: open
tags:
  - gap
  - people
---

# Gap - Lead fields mislabelled

On the CRM capture path `leads.linkedin_urn` holds the profile URL and `leads.profile_url` stays empty; `engagement_type` defaults to "Commented" even for reactions; no post topic is sent, so `suggested_dm_reply` is always empty.

**Fix:** write the URL to `profile_url`, derive the type from the interaction, send the post URN's topic.
