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
1. Lead onboarding with [[LinkedIn Data Archive Import]], LinkedIn's own sanctioned export.
2. Remove "undetectable" and "anti-detection" language everywhere ([[Gap - Claims the code contradicts]]).
3. Make the interceptor an explicit, off-by-default setting with its own disclosure, or retire it if the archive and DOM readers cover the need.
4. Get a lawyer's read on the extension before the public store listing.
