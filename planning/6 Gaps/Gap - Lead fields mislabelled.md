---
type: gap
status: partly fixed
tags:
  - gap
  - people
---

# Gap - Lead fields mislabelled

On the CRM capture path `leads.linkedin_urn` holds the profile URL and `leads.profile_url` stays empty; `engagement_type` defaults to "Commented" even for reactions; no post topic is sent, so `suggested_dm_reply` is always empty.

**Fixed 2026-10-18:** the URL is written to `profile_url`, and `engagement_type` follows the strongest interaction on record (comment, then repost, then reaction). It mattered more than it looked: the first-message draft read that field, and told people who had only reacted that they had commented. Migration 17 corrects leads captured before the fix from their own interaction rows. Test: `tests/test_lead_engagement_label.py`.

**Still open:** the reader sends no post topic, so `suggested_dm_reply` stays empty.
