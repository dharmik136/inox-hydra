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

**Most exposed:** [[Voyager Interceptor]] (wraps fetch inside LinkedIn's page) and the scrolled [[History Import]].

**Mitigations, in order:**
1. Done: Setup leads with [[LinkedIn Data Archive Import]], LinkedIn's own sanctioned export.
2. Done: "undetectable", "anti-detection" and "stealth" language is gone from the README, the extension doc and the interceptor ([[Gap - Claims the code contradicts]]).
3. Done: the interceptor is an explicit, off-by-default setting with its own disclosure. Retire it if the archive and page readers cover the need.
4. Get a lawyer's read on the extension before the public store listing.
