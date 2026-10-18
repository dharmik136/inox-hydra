---
type: roadmap
status: risk
tags:
  - roadmap
  - risk
  - release
---

# Risk - Distribution and signing

- Chrome 149 disables sideloaded extensions after a browser update, and branded Chrome 137+ ignores `--load-extension`. The store listing is not optional.
- The extension asks for `cookies` and `webRequest` on linkedin.com; expect review questions. Justify each, or drop what the archive import makes unnecessary.
- Unsigned Windows builds trip SmartScreen; macOS needs notarisation.
- A leaked updater key is code execution on every install: keep it offline, pin CI actions to SHAs, protect the release environment.
