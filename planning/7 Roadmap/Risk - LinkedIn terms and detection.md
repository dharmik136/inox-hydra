---
type: roadmap
status: risk
tags:
  - roadmap
  - risk
  - legal
---

# Risk - LinkedIn terms and detection

LinkedIn's User Agreement prohibits automated access and scraping. The product reads pages the creator opens rather than crawling, never posts or messages, and gates every request to LinkedIn. That is a defensible personal tool. A commercial product is judged more strictly.

**Most exposed:** [[Voyager Interceptor]] (wraps fetch inside LinkedIn's page), the scrolled [[History Import]], and `linkedin_client.schedule_norm_share` ("Send to LinkedIn").

**Send to LinkedIn, named explicitly (added cycle 3).** `schedule_norm_share` (`linkedin_client.py:954-1030`) POSTs `{"lifecycleState": "SCHEDULED", "commentary": ..., "scheduledAt": ...}` to `https://www.linkedin.com/voyager/api/contentcreation/normShares`, an undocumented private endpoint, authenticated with the member's own `li_at` cookie and `JSESSIONID` as a CSRF token. That is a write, not a read: automated content creation on a personal profile through a private API, outside LinkedIn's published terms, and it could affect the account's standing if LinkedIn's systems treat it as automation. It is off by default (`INOX_ALLOW_LINKEDIN_EGRESS`, `egress.py:84`) and the owner has tested it personally, but it ships, so this register names it rather than relying on the Voyager interceptor and the history import to stand in for every exposure.

**Mitigations, in order:**
1. Done: Setup leads with [[LinkedIn Data Archive Import]], LinkedIn's own sanctioned export.
2. Done: "undetectable", "anti-detection" and "stealth" language is gone from the README, the extension doc and the interceptor ([[Gap - Claims the code contradicts]]).
3. Done: the interceptor is an explicit, off-by-default setting with its own disclosure. Retire it if the archive and page readers cover the need.
4. Done (cycle 3): Send to LinkedIn requires a one-time, logged acknowledgement of the paragraph above before an installation's first send, separate from the per-send confirmation that names the account and the time. `docs/ARCHITECTURE.md` §4 and `docs/EXTENSION_AND_SYNC.md` §2 no longer claim zero automated activity or an unconditional "never click".
5. Get a lawyer's read on the extension before the public store listing.
