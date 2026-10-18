---
type: rule
status: live
tags:
  - rule
  - identity
  - privacy
code: studio/backend/onboarding.py
---

# Engagement Gate

A lead is stored only if the post they engaged with is the creator's: the post author is the confirmed vanity, or the post URN is one of the creator's [[Own Post]] rows.

Without it, scrolling the feed would fill the CRM with strangers who commented on other people's posts.

**Depends on:** [[Creator Identity]]. **Guards:** [[Lead]], [[Lead Interaction]].
