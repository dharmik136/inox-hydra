# Phone pairing: the design, before any code

How a phone could reach the studio on this computer without widening what the studio trusts. A design document only: nothing in the code changes in cycle 4 (capture report, programme item 27 and decision D7; the build is item 38, parked after this cycle).

Every check named here is cited as `path:line` followed by the name it points at. Line numbers are this branch's (`qc4/t6-posture`, from `main` at cf0ba9d) as of its review round; `tests/test_qc4_t6_pairing_design.py` holds each cited name to its file, so a check that is renamed or removed fails the suite even when lines move.

## What refuses a phone today

The studio binds to loopback and then trusts nothing about that: three checks run on every request, in order, and together they close each other's gaps.

| What | Where | What it does |
| --- | --- | --- |
| The bind | `studio/backend/desktop.py:442` (`STUDIO_HOST`), `studio/backend/app.py:8` (`Binds strictly to 127.0.0.1:8000`) | The server listens on 127.0.0.1:8000 only, so no other device on the network can open a connection to it. |
| The Host check | `studio/backend/security.py:80` (`LOOPBACK_HOSTS`), `studio/backend/security.py:165` (`is_loopback_host`), `studio/backend/app.py:692` (`if not security.is_loopback_host(host_header):`) | Every path, the interface and its assets included, answers 403 "This server answers on loopback only." unless the Host header names a loopback address. This is the defence against DNS rebinding, `studio/backend/security.py:17-22` (`DNS rebinding`). |
| The Origin check | `studio/backend/security.py:135` (`allowed_origins`), `studio/backend/security.py:162` (`EXTENSION_ORIGIN_RE`), `studio/backend/security.py:193` (`is_allowed_origin`), `studio/backend/app.py:702` (`is_allowed_origin`) | With an Origin present, only the studio's own interface on 127.0.0.1 or localhost and the installed extension pass. A request with no Origin passes this check, `studio/backend/security.py:197` (`A request with no Origin is not rejected here`), because browsers omit it on same-origin navigations and the CLI never sends one. |
| The token | `studio/backend/security.py:74` (`TOKEN_HEADER`), `studio/backend/security.py:75` (`TOKEN_COOKIE`), `studio/backend/security.py:223` (`constant_time_match`), `studio/backend/app.py:710` (`request.cookies.get(security.TOKEN_COOKIE)`) | An API call carries the studio token as a header or the HttpOnly cookie, compared in constant time, or it gets 401. |
| The exempt list | `studio/backend/security.py:85` (`UNAUTHENTICATED_PREFIXES`), `studio/backend/security.py:237` (`request_is_exempt`) | Exactly two paths answer before a token, matched exactly, never by prefix. |
| The cookie handed to the interface | `studio/backend/app.py:727` (`if not path.startswith("/api") and security.is_loopback_host(host_header):`), `studio/backend/app.py:743` (`max_age=60 * 60 * 24 * 365`) | Every page load on a loopback Host sets the studio token as an HttpOnly, SameSite=Strict cookie for a year. That is the pairing mechanism for the interface and the extension today. |
| What the decision reads | `studio/backend/app.py:683` (`host_header = request.headers.get("host")`) | The Host header. Nothing about the connection itself, the listener it arrived on or the peer that opened it, is read today. With one listener bound to 127.0.0.1 that is enough, because only a process on this computer can open the socket. |
| The second copy of the decision | `studio/backend/app.py:754` (`_is_trusted_api_request`) | The profile middleware asks the same three questions again, so it does not tell an untrusted caller which profile is active. |
| Revoking | `studio/backend/security.py:126` (`reset_token`) | A new token invalidates every paired client at once. |
| CORS | `studio/backend/app.py:409` (`CORSMiddleware`), `studio/backend/app.py:410` (`allow_origins=sorted(security.allowed_origins())`) | Configured once at startup from the same origin list. |

## Why the Host header cannot be the boundary once a second listener exists

A browser cannot forge the Host header, which is why checking it defeats DNS rebinding. Any other client can write whatever Host it likes. While the only listener is bound to 127.0.0.1, that does not matter: a client that can open that socket is already on this computer. The moment the studio listens anywhere else, a client on that network (anyone on the Wi-Fi, for a LAN listener) can connect and send `Host: 127.0.0.1:8000`. Today's checks would class it as local, `studio/backend/app.py:727` would answer its page load with the studio cookie, and with that token, a loopback Host and no Origin it would reach every route: data export, settings, Send to LinkedIn. So the design does not move the boundary; it adds the connection to it.

## The design

### 1. Trust comes from the connection, then the credential

There are two kinds of listener, and a request is judged by the one it arrived on.

- **The loopback listener**, 127.0.0.1:8000, as today. A request on it is local only when three things agree: the Host names a loopback address (the rebinding defence), the peer that opened the socket, `scope["client"]`, is a loopback address, and the listener it arrived on, `scope["server"]`, is this one. Only a local request may present the studio token, and the studio cookie is set only when the Host, the peer and the listener are all loopback. A request on the loopback listener from a peer that is not loopback is refused, whatever its Host says.
- **The paired listener**: the tunnel address for WireGuard, the computer's own LAN address for the local network, or a second loopback port reserved as Tailscale Serve's target. Nothing that arrives on it is ever local. A paired client is admitted only by its pairing credential, the phone-scoped cookie or token, and only to the phone's routes. Its Host must be exactly the paired host it was paired under, which keeps the rebinding defence for the phone's browser; the Host decides nothing else. The studio token is refused there even when presented, and the studio cookie is never set there. A request on the paired listener that claims a loopback Host gets nothing: 403 before any route, and no cookie.

Both copies of today's decision, `enforce_local_access` at `studio/backend/app.py:664` (`@app.middleware("http")`) and `_is_trusted_api_request` at `studio/backend/app.py:754` (`_is_trusted_api_request`), move into one function in `security.py` that takes the listener, the peer and the headers, so the two cannot drift apart when the paired path is added.

### 2. A paired-host list, kept apart from LOOPBACK_HOSTS

A new set, `PAIRED_HOSTS`, persisted beside the token in the vault folder (`paired_hosts.json`, mode 0600 like `api_token`, `studio/backend/security.py:92` (`get_or_create_token`)). Each entry is one exact host and port the creator chose, such as `desk.example-tailnet.ts.net` or `192.168.1.20:8010`, with the device name, when it was paired, and the phone token's digest. It is matched exactly, the way `is_loopback_host` matches, never by suffix, wildcard or address range, and it is consulted only on the paired listener.

It is never merged into `LOOPBACK_HOSTS`, and it never grants anything by itself: it names the Host a paired listener answers to, while admission is the credential's.

### 3. A short-lived pairing code through one exempt endpoint

- The desktop interface, on the loopback listener, shows a pairing code when the creator asks for one: eight characters from a cryptographic source, valid for two minutes, single use. Only someone looking at this computer's screen can read it.
- One endpoint, `POST /api/v1/pair`, is added to the exact-match exempt list (`studio/backend/security.py:85` (`UNAUTHENTICATED_PREFIXES`)), and answers only on the paired listener. It takes the code and a device name.
- It is rate limited: five attempts a minute per listener, and a code is burned after five wrong answers, so the code cannot be guessed in its two minutes.
- On a right answer it issues a phone-scoped token and sets it as a cookie of its own, `inox_phone_token`: HttpOnly, SameSite=Strict, Path=/, Secure whenever the paired origin is https. The token is stored as a digest, never in clear.

### 4. A phone-scoped credential, never the studio's

- The studio cookie is set only by the loopback listener, for a local request as defined in section 1. `studio/backend/app.py:727` gains the peer and the listener as conditions beside the Host.
- On the paired listener the studio token is refused even when presented, and the phone credential is accepted only there, so a copied studio cookie cannot be replayed through the phone's path and a phone credential means nothing on the loopback listener.
- The phone credential reaches a named list of routes: Today, the drafts, adding a draft, and the share target. Not the LinkedIn session, the licence, the settings, backups, export, or anything that sends. A route not on the list answers 403 to a phone.
- Each phone can be revoked alone, from the desktop. `reset_token` (`studio/backend/security.py:126` (`reset_token`)) keeps its meaning: it revokes the extension and the interface, and with them every phone.

### 5. The paired origin added to allowed_origins

`allowed_origins()` (`studio/backend/security.py:135` (`allowed_origins`)) gains each paired origin, so the phone page's same-origin API calls pass `is_allowed_origin` (`studio/backend/security.py:193` (`is_allowed_origin`)). CORS stays as it is, loopback and the extension (`studio/backend/app.py:410` (`allow_origins=sorted(security.allowed_origins())`)): the phone's calls are same-origin, so no cross-origin grant is needed, and the CORS list is fixed at startup while pairing happens at runtime.

## The transport, in order of preference

1. **Tailscale Serve, first.** `tailscale serve` gives this computer an https name inside the creator's tailnet and proxies it to a local port. The studio keeps its loopback bind; only the creator's own tailnet devices can connect; the connection is WireGuard-encrypted, and Tailscale's relays cannot read it; the page is https, so the phone cookie is Secure and the studio can be installed as a web app with a share target on Android. Tailscale's coordination server sees device keys and metadata, never content. The identity headers Serve adds (`Tailscale-User-Login` and the like) never replace the phone credential: the studio cannot tell from inside a request that it really came through Serve.

   Serve's proxy runs on this computer, so the studio sees its requests arrive from a loopback peer, and the peer cannot tell them from local ones. So Serve's target is the paired listener's own loopback port, such as 127.0.0.1:8010, and never 8000: there it is the listener, not the peer, that says the request came through Serve, and nothing on that port is local. Serve never forwards into the loopback listener. Before building, read one forwarded request to settle two things: which Host header Serve forwards, and whether a tailnet client can make Serve forward a Host of its own choosing. On the paired listener these decide only the rebinding check, never trust, because admission is the phone credential's (capture report, gaps table).

2. **WireGuard, the option with no third party.** A WireGuard tunnel between the phone and this computer, with the studio given a paired listener bound to the tunnel's address only (never `0.0.0.0`), beside `STUDIO_HOST` (`studio/backend/desktop.py:442` (`STUDIO_HOST`)). The tunnel encrypts the traffic; peers on it are tunnel addresses, never loopback, and a request there claiming a loopback Host gets nothing. Plain http inside the tunnel means no Secure flag and no installable web app without a local certificate.

3. **The local network, plain http, only with the code.** A paired listener bound to the computer's LAN address only. The phone cookie then crosses the Wi-Fi in clear, so this path is offered only with the pairing code, the phone-scoped credential and its route list, and a sentence saying that anyone on the same Wi-Fi could read what the phone sends. It is the last choice, not the default.

4. **Refused: any relay that forwards into the loopback listener.** A proxy on this computer that forwards the phone's requests to `127.0.0.1:8000`, whether it rewrites Host to `127.0.0.1:8000` or not, delivers them from a loopback peer onto the loopback listener, which is exactly what local means in section 1. Every phone request would then be indistinguishable from a DNS-rebinding attack that succeeded, which is the shape the Host check exists to catch (`studio/backend/security.py:17-22` (`DNS rebinding`)), and the cookie at `studio/backend/app.py:727` would be set for the phone. A relay may forward only into the paired listener, where nothing is local.

## What does not change

- Nothing new leaves the machine. A phone connecting in is not egress, and `egress.py` counts what the studio opens outward, not what reaches it.
- The extension still talks to `127.0.0.1:8000` and nothing else.
- The rebinding defence, the Origin check and the token stay exactly as they are for the loopback listener, with the peer and the listener added to what makes a request local.

## What changes when it is built (item 38)

- `security.py`: one trust function both middlewares call, taking the listener, the peer and the headers; `PAIRED_HOSTS` and its file; the phone credential and its digest; the phone route list.
- `app.py`: the decision reads `scope["server"]` and `scope["client"]` as well as the Host; the studio cookie is set only for a local request; `POST /api/v1/pair` on the paired listener.
- `desktop.py`: the paired listener, bound to one address: the tunnel, the LAN address, or a second loopback port for Serve.
- The interface: a Pair a phone panel showing the code and the paired devices with Revoke.
- The privacy policy and the help, before it ships: the policy's "only address" paragraph says the studio answers a paired phone too, and what a phone can and cannot reach.

The tests that must exist before it ships: a request with `Host: 127.0.0.1:8000 on the paired listener gets 403 and no cookie`; a request on the loopback listener from a peer that is not loopback is refused; the studio cookie is set only for a request whose Host, peer and listener are all loopback; the studio token is refused on the paired listener; rebinding is still refused with a paired list present; a paired listener request with no phone credential gets nothing but the pairing page; the phone credential is refused on the loopback listener and on any route off its list; a code expires at two minutes, works once, and burns after five wrong answers; a revoked phone is refused; `LOOPBACK_HOSTS` is unchanged; Serve's configured target is the paired listener's port, never 8000.

## Open before building

- Which Host header Tailscale Serve forwards, and whether a tailnet client can choose it (the gate in transport 1).
- How `studio/frontend_next` builds its API addresses: relative paths work from any origin, an absolute loopback address would make a phone call its own loopback.
- Whether Chrome on Android applies its local network permission to a page addressed by a private IP (transport 3).
