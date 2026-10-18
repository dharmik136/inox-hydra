---
type: source
status: live
tags:
  - source
  - extension
  - attribution
code: studio/extension/content.js
---

# Post Permalink Binder

When the creator opens a post's permalink, binds the studio's record of that post to LinkedIn's activity URN by matching the body text.

**Sends to:** `/api/v1/posts/bind-urn`.

**Links:** [[Studio Post]] to [[Own Post]]. Without this bind, attribution in [[Patterns and Attribution]] has nothing to attach to.

The side panel's injected-post record is the other half of this. It was silently refused until [[Fixed - Side panel write refused]].
