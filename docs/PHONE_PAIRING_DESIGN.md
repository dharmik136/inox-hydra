# Phone pairing: the design, before any code

How a phone could reach the studio on this computer without widening what the studio trusts. A design document only: nothing in the code changes in cycle 4 (capture report, programme item 27 and decision D7; the build is item 38, parked after this cycle).

Every check named here is cited as `path:line` followed by the name it points at. Line numbers are this branch's (`qc4/t6-posture`, from `main` at cf0ba9d) when this was written; `tests/test_qc4_t6_pairing_design.py` holds each cited name to its file, so a check that is renamed or removed fails the suite even when lines move.

## What refuses a phone today

The studio binds to loopback and then trusts nothing about that: three checks run on every request, in order, and together they close each other's gaps.

| What | Where | What it does |
| --- | --- | --- |
| The bind | `studio/backend/desktop.py:442` (`STUDIO_HOST`), `studio/backend/app.py:8` (`Binds strictly to 127.0.0.1:8000`) | The server listens on 127.0.0.1:8000 only, so no other device on the network can open a connection to it. |
| The Host check | `studio/backend/security.py:80` (`LOOPBACK_HOSTS`), `studio/backend/security.py:165` (`is_loopback_host`), `studio/backend/app.py:674` (`if not security.is_loopback_host(host_header):`) | Every path, the interface and its assets included, answers 403 "This server answers on loopback only." unless the Host header names a loopback address. This is the defence against DNS rebinding, `studio/backend/security.py:17-22` (`DNS rebinding`). |
| The Origin check | `studio/backend/security.py:135` (`allowed_origins`), `studio/backend/security.py:162` (`EXTENSION_ORIGIN_RE`), `studio/backend/security.py:193` (`is_allowed_origin`), `studio/backend/app.py:684` (`is_allowed_origin`) | With an Origin present, only the studio's own interface on 127.0.0.1 or localhost and the installed extension pass. |
| The token | `studio/backend/security.py:74` (`TOKEN_HEADER`), `studio/backend/security.py:75` (`TOKEN_COOKIE`), `studio/backend/security.py:223` (`constant_time_match`), `studio/backend/app.py:692` (`request.cookies.get(security.TOKEN_COOKIE)`) | An API call carries the studio token as a header or the HttpOnly cookie, compared in constant time, or it gets 401. |
| The exempt list | `studio/backend/security.py:85` (`UNAUTHENTICATED_PREFIXES`), `studio/backend/security.py:237` (`request_is_exempt`) | Exactly two paths answer before a token, matched exactly, never by prefix. |
| The cookie handed to the interface | `studio/backend/app.py:709` (`if not path.startswith("/api") and security.is_loopback_host(host_header):`), `studio/backend/app.py:725` (`max_age=60 * 60 * 24 * 365`) | Every page load on a loopback Host sets the studio token as an HttpOnly, SameSite=Strict cookie for a year. That is the pairing mechanism for the interface and the extension today. |
| The second copy of the decision | `studio/backend/app.py:736` (`_is_trusted_api_request`) | The profile middleware asks the same three questions again, so it does not tell an untrusted caller which profile is active. |
| Revoking | `studio/backend/security.py:126` (`reset_token`) | A new token invalidates every paired client at once. |
| CORS | `studio/backend/app.py:391` (`CORSMiddleware`), `studio/backend/app.py:392` (`allow_origins=sorted(security.allowed_origins())`) | Configured once at startup from the same origin list. |

## The design

### 1. A paired-host list, kept apart from LOOPBACK_HOSTS

A new set, `PAIRED_HOSTS`, persisted beside the token in the vault folder (`paired_hosts.json`, mode 0600 like `api_token`, `studio/backend/security.py:92` (`get_or_create_token`)). Each entry is one exact host and port the creator chose, such as `desk.example-tailnet.ts.net` or `192.168.1.20:8010`, with the device name, when it was paired, and the phone token's digest. It is matched exactly, the way `is_loopback_host` matches, and never by suffix, wildcard or address range.

It is never merged into `LOOPBACK_HOSTS`. Adding a phone's name to the loopback set would hand it everything loopback gets, the studio cookie included (`studio/backend/app.py:709`). The Host check becomes "loopback, or exactly a paired host", and every later step knows which of the two it is.

Both copies of the trust decision change together: `enforce_local_access` (`studio/backend/app.py:646` (`@app.middleware("http")`)) and `_is_trusted_api_request` (`studio/backend/app.py:736` (`_is_trusted_api_request`)). The build should first move the decision into one function in `security.py` that both call, so the two cannot drift apart when the paired path is added.

### 2. A short-lived pairing code through one exempt endpoint

- The desktop interface, on loopback, shows a pairing code when the creator asks for one: eight characters from a cryptographic source, valid for two minutes, single use. Only someone looking at this computer's screen can read it.
- One endpoint, `POST /api/v1/pair`, is added to the exact-match exempt list (`studio/backend/security.py:85` (`UNAUTHENTICATED_PREFIXES`)), and answers only on a paired host. It takes the code and a device name.
- It is rate limited: five attempts a minute per host, and a code is burned after five wrong answers, so the code cannot be guessed in its two minutes.
- On a right answer it issues a phone-scoped token and sets it as a cookie of its own, `inox_phone_token`: HttpOnly, SameSite=Strict, Path=/, Secure whenever the paired origin is https. The token is stored as a digest, never in clear.

### 3. A phone-scoped cookie, never the studio's

- The studio cookie is never set on a paired host. The condition at `studio/backend/app.py:709` stays `is_loopback_host` alone. If it were widened to paired hosts, anyone on the network who opened the address would be paired by loading the page.
- On a paired host, the studio token is refused even when presented, and the phone token is accepted only there, so a copied studio cookie cannot be replayed through the phone's path and a phone cookie means nothing on loopback.
- The phone token reaches a named list of routes: Today, the drafts, adding a draft, and the share target. Not the LinkedIn session, the licence, the settings, backups, export, or anything that sends. A route not on the list answers 403 to a phone.
- Each phone can be revoked alone, from the desktop. `reset_token` (`studio/backend/security.py:126` (`reset_token`)) keeps its meaning: it revokes the extension and the interface, and with them every phone.

### 4. The paired origin added to allowed_origins

`allowed_origins()` (`studio/backend/security.py:135` (`allowed_origins`)) gains each paired origin, so the phone page's same-origin API calls pass `is_allowed_origin` (`studio/backend/security.py:193` (`is_allowed_origin`)). CORS stays as it is, loopback and the extension (`studio/backend/app.py:392` (`allow_origins=sorted(security.allowed_origins())`)): the phone's calls are same-origin, so no cross-origin grant is needed, and the CORS list is fixed at startup while pairing happens at runtime.

## The transport, in order of preference

1. **Tailscale Serve, first.** `tailscale serve` gives this computer an https name inside the creator's tailnet and proxies it to `http://127.0.0.1:8000`. The studio keeps its loopback bind; only the creator's own tailnet devices can connect; the connection is WireGuard-encrypted, and Tailscale's relays cannot read it; the page is https, so the phone cookie is Secure and the studio can be installed as a web app with a share target on Android. Tailscale's coordination server sees device keys and metadata, never content. The identity headers Serve adds (`Tailscale-User-Login` and the like) never replace the phone token: the studio cannot tell from inside a request that it really came through Serve.

   A gate before building: which Host header Serve forwards. If it forwards the tailnet name, that name is the paired host. If it rewrites Host to `127.0.0.1:8000`, Serve is itself a Host-rewriting relay under rule 4 below, every phone request would pass as local and be handed the studio cookie on its first page load, and Serve is refused; WireGuard takes its place. One forwarded request, read once, settles it (capture report, gaps table).

2. **WireGuard, the option with no third party.** A WireGuard tunnel between the phone and this computer, with the studio given a second listener bound to the tunnel's address only (never `0.0.0.0`), beside `STUDIO_HOST` (`studio/backend/desktop.py:442` (`STUDIO_HOST`)). The tunnel encrypts the traffic; the paired host is the tunnel address and port. Plain http inside the tunnel means no Secure flag and no installable web app without a local certificate.

3. **The local network, plain http, only with the code.** A second listener bound to the computer's LAN address only. The phone cookie then crosses the Wi-Fi in clear, so this path is offered only with the pairing code, the phone-scoped token and its route list, and a sentence saying that anyone on the same Wi-Fi could read what the phone sends. It is the last choice, not the default.

4. **Refused: any Host-rewriting relay.** A proxy on this computer that forwards the phone's requests to `127.0.0.1:8000` with Host rewritten to `127.0.0.1:8000` makes every phone request indistinguishable from a DNS-rebinding attack that succeeded, which is exactly the shape the Host check exists to catch (`studio/backend/security.py:17-22` (`DNS rebinding`)). The loopback check would pass, the cookie at `studio/backend/app.py:709` would be set for the phone, and the token would then be meaningless. A relay that preserves the phone's Host is just one of the three options above with an extra hop.

## What does not change

- Nothing new leaves the machine. A phone connecting in is not egress, and `egress.py` counts what the studio opens outward, not what reaches it.
- The extension still talks to `127.0.0.1:8000` and nothing else.
- The rebinding defence, the Origin check and the token stay exactly as they are for loopback.

## What changes when it is built (item 38)

- `security.py`: `PAIRED_HOSTS` and its file, `is_paired_host`, the phone token and its digest, the phone route list, one trust function both middlewares call.
- `app.py`: the Host check admits paired hosts; the token check takes the phone token on a paired host only; the cookie condition at line 709 is untouched; `POST /api/v1/pair`.
- `desktop.py`: a second listener for the WireGuard or LAN options, bound to one address.
- The interface: a Pair a phone panel showing the code and the paired devices with Revoke.
- The privacy policy and the help, before it ships: the policy's "only address" paragraph says the studio answers a paired phone too, and what a phone can and cannot reach.

The tests that must exist before it ships: rebinding is still refused with a paired list present; a paired host with no phone cookie gets nothing but the pairing page; the studio cookie is never set on a paired host; the studio token is refused on a paired host; the phone token is refused on loopback and on any route off its list; a code expires at two minutes, works once, and burns after five wrong answers; a revoked phone is refused; `LOOPBACK_HOSTS` is unchanged.

## Open before building

- Which Host header Tailscale Serve forwards (the gate in transport 1).
- How `studio/frontend_next` builds its API addresses: relative paths work from any origin, an absolute loopback address would make a phone call its own loopback.
- Whether Chrome on Android applies its local network permission to a page addressed by a private IP (transport 3).
