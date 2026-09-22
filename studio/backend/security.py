"""
Local API Security: Who Is Allowed To Talk To This Machine.
===========================================================

The studio binds to 127.0.0.1, which people reasonably read as "only I can
reach it". That is true of other machines on the network and false of the
browser sitting in front of it. Any page the creator visits can issue
`fetch("http://127.0.0.1:8000/api/v1/crm/leads")` from its own JavaScript, and
with `allow_origins=["*"]` the browser handed that page the response. Their
leads, their drafts and their settings were readable, and writable, by any site
they happened to have open. Nothing about binding to loopback prevented it.

So the boundary is not the network. It is the origin.

Three checks, in this order, on every API request:

  1. Host.
     The Host header must name a loopback address. This is the defence against
     DNS rebinding, where an attacker points evil.example at 127.0.0.1 so that
     their page becomes same-origin with this server. The browser sends
     `Host: evil.example` in that case, which is what gives it away. Without
     this check the origin allowlist below can be walked straight around.

  2. Origin.
     When an Origin header is present it must be one we published to: the
     studio's own interface, or the Chrome extension. A browser will not let a
     page forge this header, which is what makes it worth checking.

     LinkedIn is deliberately NOT on that list, and it is worth being explicit
     about why, because allowing it is the obvious first instinct. The
     extension's content script runs inside the LinkedIn page, so its requests
     used to carry `Origin: https://www.linkedin.com`. Allowing that origin
     would mean trusting every script on linkedin.com with this database:
     LinkedIn's own code, whatever their ad and analytics vendors inject, and
     anything an XSS on their domain could run. That is a larger and less
     trustworthy set of code than the entire rest of this threat model.

     The extension was changed to route its calls through its background
     service worker instead, so requests now carry `chrome-extension://<id>`,
     an origin only the installed extension can speak from.

  3. Token.
     A secret generated on first run and kept in the user's own data directory.
     The interface receives it as an HttpOnly, SameSite=Strict cookie. Strict
     means a browser refuses to attach it to a request started by any other
     site, and HttpOnly means no script on this origin can read it either, so
     an XSS here cannot exfiltrate it. The extension does not need script
     access: chrome.cookies.get is privileged and reads HttpOnly cookies.

Each check alone has a hole. A token alone is beatable by a page that can read
the cookie. An origin check alone is beatable by DNS rebinding. Together they
close each other's gaps, which is the only reason to run all three.

Strict Invariants:
- Zero em-dashes in any code, docstring, or comment.
- Loopback binding is assumed, never relied upon as the boundary.
- The token file lives with user state, never inside the install directory.
"""

import ipaddress
import os
import re
import secrets
from typing import Optional, Set
from urllib.parse import urlsplit

try:
    from . import paths
except ImportError:  # pragma: no cover - direct module execution
    import paths


TOKEN_FILENAME = "api_token"
TOKEN_HEADER = "X-Inox-Token"
TOKEN_COOKIE = "inox_studio_token"

# Loopback names a browser can legitimately put in a Host header for this
# server. Anything else means the request arrived through a name that resolves
# here, which is the shape of a rebinding attack.
LOOPBACK_HOSTS: Set[str] = {"127.0.0.1", "localhost", "::1", "[::1]"}

# Paths that must answer before the caller can possibly hold a token. Kept to
# the absolute minimum: the interface itself, its assets, and the health probe
# the launcher uses to decide whether a server is already running.
UNAUTHENTICATED_PREFIXES = ("/api/v1/health", "/api/health")


def _token_path() -> str:
    return os.path.join(paths.get_vault_dir(), TOKEN_FILENAME)


def get_or_create_token() -> str:
    """
    Reads this installation's API token, generating one on first run.

    Stored beside the other user state rather than in the install directory, so
    replacing the application folder during an update does not invalidate a
    paired extension, and so two installations never share a secret.
    """
    path = _token_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            existing = handle.read().strip()
        if existing:
            return existing
    except (OSError, IOError):
        pass

    token = secrets.token_urlsafe(32)
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(token)
        # Best effort on POSIX. Windows inherits the user profile ACL, which
        # already excludes other users.
        try:
            os.chmod(path, 0o600)
        except (OSError, NotImplementedError):
            pass
    except (OSError, IOError):
        # A read only data directory is a broken install, but refusing to serve
        # would be worse than running with an ephemeral secret for this process.
        pass
    return token


def reset_token() -> str:
    """Issues a new token, invalidating every paired client. Used by the CLI."""
    try:
        os.remove(_token_path())
    except (OSError, IOError):
        pass
    return get_or_create_token()


def allowed_origins(port: int = 8000) -> Set[str]:
    """
    The origins this server publishes an interface to.

    Note what is absent. LinkedIn is not here, and neither is any http or https
    site. The only web origin trusted with this database is the one this server
    serves itself.
    """
    origins = set()
    for host in ("127.0.0.1", "localhost"):
        origins.add(f"http://{host}:{port}")
    return origins


# A Chrome extension origin is chrome-extension://<32 char id>. The id is not
# known at build time for an unpacked load, so the shape is matched instead.
# This is a deliberately weaker check than the exact list above, and the token
# is what carries the weight: an extension can only read the cookie if the user
# granted it host permission for this server, which means they installed it.
EXTENSION_ORIGIN_SCHEME = "chrome-extension://"

# The full shape, not just the scheme. Matching on the prefix alone accepted
# "chrome-extension://", "chrome-extension://evil.com/../.." and anything else
# starting with those characters, and it disagreed with the stricter regex the
# CORS layer uses. Because this middleware runs outside CORSMiddleware, the
# loose check was the one that actually decided, so the strict one was
# decorative. A Chrome extension id is exactly 32 characters, a to p.
EXTENSION_ORIGIN_RE = re.compile(r"^chrome-extension://[a-p]{32}$")


def is_loopback_host(host_header: Optional[str]) -> bool:
    """
    Whether the Host header names this machine.

    A missing Host is refused. HTTP/1.1 requires it, and its absence usually
    means something is talking to this port that is not a browser.
    """
    if not host_header:
        return False

    host = host_header.strip()
    # Strip the port, taking care with the bracketed IPv6 form.
    if host.startswith("["):
        closing = host.find("]")
        hostname = host[: closing + 1] if closing != -1 else host
    else:
        hostname = host.split(":")[0]

    if hostname.lower() in LOOPBACK_HOSTS:
        return True

    # Catches the rest of 127.0.0.0/8, which all routes to this machine.
    try:
        return ipaddress.ip_address(hostname.strip("[]")).is_loopback
    except ValueError:
        return False


def is_allowed_origin(origin: Optional[str], port: int = 8000) -> bool:
    """
    Whether a cross origin caller is one we published to.

    A request with no Origin is not rejected here. Browsers omit it on same
    origin GET navigations, and non browser callers such as the CLI never send
    one. Those requests still have to satisfy the Host and token checks, which
    is what actually protects them. The Origin check exists for the one case it
    is good at: a browser telling us truthfully which page is calling.
    """
    if origin is None:
        return True

    origin = origin.strip()
    if origin == "null":
        # Sandboxed iframes and file:// pages. Nothing legitimate here.
        return False

    if EXTENSION_ORIGIN_RE.match(origin):
        return True

    if origin in allowed_origins(port):
        return True

    # An explicit note for the case somebody will otherwise try to add later.
    # https://www.linkedin.com reaching this port means a page script is
    # calling, not the extension, and no page script should hold this database.
    return False


def constant_time_match(supplied: Optional[str], expected: str) -> bool:
    """Compares without leaking length or prefix through timing."""
    if not supplied:
        return False
    # compare_digest raises TypeError on non-ASCII str. Header values are
    # decoded latin-1 by the server, so any byte above 0x7f in the token header
    # reached it and turned the auth path into an unhandled 500. Compared as
    # bytes instead, which has no such restriction.
    try:
        return secrets.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))
    except (AttributeError, UnicodeError):
        return False


def request_is_exempt(path: str) -> bool:
    """
    Whether a path answers before authentication.

    Matched exactly rather than by prefix. Prefix matching would silently
    exempt the next route that happens to start with these characters, which
    is the kind of accident nobody notices until it is a finding.
    """
    return path in UNAUTHENTICATED_PREFIXES


def extract_port(host_header: Optional[str], default: int = 8000) -> int:
    """Reads the port the caller reached us on, for building the origin list."""
    if not host_header:
        return default
    try:
        parts = urlsplit(f"//{host_header.strip()}")
        return parts.port or default
    except (ValueError, TypeError):
        return default
