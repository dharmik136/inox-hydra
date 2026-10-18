---
type: source
status: live
tags:
  - source
  - capture
  - ideas
code: studio/backend/ingress.py
---

# Telegram Ingress

Long-polls a Telegram bot (outbound only, no webhook) and accepts messages from the one configured chat.

**Parses:** `Draft:`, `Idea:` and `Schedule <when>:` prefixes and hashtags, and measures the fold on arrival. Voice notes are stored as placeholder text for now.

**Writes:** [[Draft]] and a draft [[Studio Post]].

**Feeds:** the top of the [[Idea Pipeline]].
