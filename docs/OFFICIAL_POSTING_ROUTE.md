# The official posting route: can a desktop app with no server use it?

The written answer to decision D2's open question: whether LinkedIn's authorization-code flow can be completed by a public client, one with no confidential secret, which decides whether the studio could post through LinkedIn's own API without a server of ours. Read from LinkedIn's developer documentation on 26 October 2026. No OAuth code is written in cycle 4; the route itself is capture item 31, parked until this is settled.

## The answer

Yes in LinkedIn's documentation, but not self-serve.

LinkedIn documents two authorization-code flows.

**The standard 3-legged flow needs the client secret.** It is the self-serve flow that Sign In with LinkedIn and Share on LinkedIn use. Its token request lists `client_secret` as required: "client_secret | string | The Secret Key value generated in Step 1." with Required "Yes", beside `grant_type`, `code`, `client_id` and `redirect_uri`, and it warns: "Do not share your Client Secret value with anyone, and **do not** pass it in the URL when making API calls, or URI query-string parameters, or post in support forums, chat, etc." (page "LinkedIn 3-Legged OAuth Flow", dated 2025-11-10, updated 2026-05-15.)

**A native-client flow with PKCE needs no secret, and LinkedIn turns it on per app.** The page "Authenticating with OAuth 2.0 for Native Clients" opens: "For native apps that don't have a reliable way to keep secrets, this documentation will walk you through using Proof Key for Code Exchange (PKCE) support to integrate LinkedIn OAuth 2.0 into your native apps." Its authorization request goes to `https://www.linkedin.com/oauth/native-pkce/authorization` with `code_challenge` and `code_challenge_method` (always `S256`); its token request goes to `https://www.linkedin.com/oauth/v2/accessToken` with `grant_type`, `code`, `redirect_uri`, `client_id` and `code_verifier`, and no `client_secret`. The redirect must be a loopback address: "we will only communicate with loopback IPs ... The lookback IP representation supported for IPv4 is `http://127.0.0.1:{port}` while for IPv6 is `http://[::1]:{port}`." And: "It's a requirement that all native applications use the default browser launched by user's operating system to perform OAuth authorization request, rather than an embedded in-app browser or webview."

The condition is one sentence: "Once you have the app created, please reach out to your point of contact at LinkedIn, and we will enable PKCE OAuth 2 flow for your app." The page sits in LinkedIn's Sales Navigator documentation (its example scope is `r_sales_nav_analytics`), dated 2018-09-07, updated 2023-04-03.

The standard flow's page is consistent with the server accepting PKCE at the same token endpoint: its error table reads "appid/redirect uri/code verifier does not match authorization code", and it points native apps to RFC 8252, OAuth 2.0 for Native Apps, for its extended sign-in options. But no self-serve page enables PKCE for an app.

## What it means for a desktop app with no server

- **Without PKCE enabled for the app**, the only documented token exchange needs the secret. A desktop app can then either ship the secret inside the installed app, where anyone can read it, against "Do not share your Client Secret value with anyone"; or run a token-exchange endpoint, which is a server of ours, against the product's first property ("The extension has no server. Neither does Inox Hydra.", `docs/PRIVACY_POLICY.md`). Neither is acceptable under the product's rules, so the official posting route cannot be built on the self-serve flow.
- **With PKCE enabled for the app**, the flow fits the studio as it is built: the redirect is a loopback address, where the studio already listens; the creator consents in their own default browser; no secret is stored anywhere; the token belongs to the creator, on their disk, sealed like the AI key (`studio/backend/secret_settings.py`); every request goes through `studio/backend/egress.py` under the `linkedin` category, refused by default, and the privacy policy says so before it ships.
- **What none of the pages says**, and an app must show before item 31 is built:
  - whether an app with PKCE enabled can be granted `w_member_social`, the Share on LinkedIn permission ("Required to create a LinkedIn post on behalf of the authenticated member"); the native page's examples are Sales Navigator scopes;
  - whether a "point of contact at LinkedIn" exists for an app without a partner relationship, which is the eligibility question the Community Management application (D8) also meets;
  - whether the registered redirect may be the studio's fixed port: the page says to listen "on a random port of loopback interface", and the studio's port is fixed at 8000 (`studio/backend/desktop.py`, `EXTENSION_PORT`);
  - whether the Posts API accepts a scheduled time. If it does not, the studio posts at the queued time itself, which it can do only while it is running, and LinkedIn's own scheduler, which Send to LinkedIn uses today, is lost.
- **Tokens last 60 days.** Both pages: "Currently, all access tokens are issued with a 60 day lifespan." Refreshing means running the flow again ("Programmatic refresh tokens are available for a limited set of partners"); the consent screen is skipped while the creator is still signed in to linkedin.com in that browser. So about every 60 days the creator passes through LinkedIn's own page once more.
- **The Agency tier.** Under OAuth each creator consents for their own account on LinkedIn's own page, which is the designed use; the first-profile rule of decision D9 answers the cookie-based Send to LinkedIn and could be revisited for an OAuth route, as a later decision.

## Recommendation

1. Keep D2 as adopted: Send to LinkedIn through LinkedIn's private scheduling API stays off by default, acknowledged once per profile, and available in the first profile only (D9). Item 31 stays parked.
2. Owner action, beside D8: register the developer app, ask LinkedIn's contact to enable the native PKCE flow for it, and ask whether `w_member_social` can be granted with it.
3. If LinkedIn enables it, verify before building: one PKCE authorization with a loopback redirect, the token exchange without a secret, and one post to a test account through Share on LinkedIn. Then item 31 replaces the private API with LinkedIn's own, and moves posting from rung 8 of the posture ladder to rung 2.
4. If LinkedIn will not, the official posting route cannot exist under "no server of ours". The choice is then between keeping Send to LinkedIn as it is, off by default and disclosed, or retiring it.

## Sources, read 26 October 2026

- LinkedIn 3-Legged OAuth Flow: https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow (ms.date 2025-11-10, updated 2026-05-15)
- Authenticating with OAuth 2.0 for Native Clients: https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow-native (ms.date 2018-09-07, updated 2023-04-03)
- Authenticating with OAuth 2.0 Overview: https://learn.microsoft.com/en-us/linkedin/shared/authentication/authentication (updated 2022-12-21); it names two flows, member (3-legged) and application (2-legged client credentials), and does not mention PKCE
- Share on LinkedIn: https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin (the `w_member_social` sentence above, as the capture report's research notes quote it)
- RFC 7636, Proof Key for Code Exchange; RFC 8252, OAuth 2.0 for Native Apps
