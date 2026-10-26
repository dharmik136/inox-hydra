"""
One chokepoint for everything that leaves this machine.

The product's first constraint is that your work stays local, and for a long
time that was enforced for exactly one destination. `linkedin_client` routed
its three requests through a guard that refuses by default and returns a
visible refusal rather than failing quietly. The other six modules, fourteen
calls between them, reached nine hosts with no guard, no counter, and no way to
say no. The claim was true of the part someone had written a guard for.

So this is that guard, generalised. Every HTTP call this backend makes now
passes through `guard()` before it opens a socket.

What it does not cover
----------------------
Two paths reach the network without coming through here, and saying so is the
difference between a chokepoint and a claim about one.

`browser_launcher` starts the creator's own browser at a LinkedIn URL through
`subprocess`. The machine then contacts LinkedIn, and nothing here sees it, so
the `linkedin` counter can read zero immediately after this studio opened
LinkedIn with the creator's session. That is not a leak to fix by counting: it
is the creator's browser doing what they asked. It is a gap in what the ledger
can honestly claim, which is why the interface now names it.

An MCP source is a program on this machine started by `mcp_client.protocol`.
Its pipe is local, but what it does with the network is its own business: a
fetch or a GitHub server makes requests under no category, in no counter, and
`INOX_NO_EGRESS` cannot stop them. The only honest handling is to say so where
a creator reads the numbers, and to keep the client unable to invoke tools, so
what a source can do stays limited to answering with text it already holds.

What it is not
--------------
This is not a switch that turns the product off. The original guard exists
because the studio was making LinkedIn requests *on your behalf*, unasked, from
a background listener. That is a different act from pressing Generate on an
image and having the prompt go to the engine that renders it. The first needs
refusing by default; the second is a thing you asked for, and refusing it would
only teach you to set a flag and forget it, which buys nothing.

So the policy is per category, and the defaults match how each call is reached:

  linkedin   refuses by default. Unchanged, including its env flag, because
             the reasoning that put it there has not changed.
  model      allowed. Reached only when you have configured a provider key,
             and that key is the consent.
  image      allowed. Reached only when you press Generate, and only for the
             image provider chosen in the Prompt tab. A web UI you run on
             this computer (ComfyUI, AUTOMATIC1111) is not egress: see
             on_this_machine().
  library   allowed. Reached only when you sync or import a bundle.
  updates    allowed here, and already off by default one level up in
             updates.py, which asks before it ever checks.
  ingress    allowed here, and inert unless a Telegram bot is set up under Local security (or, in dev mode, TELEGRAM_BOT_TOKEN is set).

`INOX_NO_EGRESS=1` refuses every category including the ones allowed above,
which is the switch that makes the constraint enforceable rather than
descriptive: one variable, and nothing in this process opens a connection.

What it buys
------------
Enforceability, and an answer to "what has left this machine". Every call is
counted per category with its last destination, so the Local security tab can
report what actually happened rather than repeating a promise.

A refusal is never a silent None, because a request that did not happen must
not look like one that did. It takes one of two shapes: guard() returns a dict
the caller passes back, and require() raises EgressRefused for the fourteen
call sites whose failure path was already an exception. Both count.
"""

import os
import re
import threading
from typing import Any, Dict, Optional
from urllib.parse import quote, quote_plus, urlsplit, urlunsplit

# Categories, their env override, and the default when no override is set.
#
# An override is read on every call rather than cached at import, so a flag set
# by a test or by a launcher after this module loads still applies.
_POLICY = {
    "linkedin": ("INOX_ALLOW_LINKEDIN_EGRESS", False),
    "model": ("INOX_ALLOW_MODEL_EGRESS", True),
    "image": ("INOX_ALLOW_IMAGE_EGRESS", True),
    "library": ("INOX_ALLOW_LIBRARY_EGRESS", True),
    "updates": ("INOX_ALLOW_UPDATE_EGRESS", True),
    "ingress": ("INOX_ALLOW_INGRESS_EGRESS", True),
}

MASTER_OFF_FLAG = "INOX_NO_EGRESS"

_lock = threading.Lock()

# One stats dict per category, created once and never replaced. Identity
# matters: linkedin_client exposes its own as a module attribute and
# tests/test_passive_observer_boundary.py both writes to and reads from that
# object, so handing back a new dict would silently detach the counters.
_stats: Dict[str, Dict[str, Any]] = {
    name: {"refused": 0, "performed": 0, "last_refused_endpoint": None, "last_destination": None}
    for name in _POLICY
}


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def stats_for(category: str) -> Dict[str, Any]:
    """The live counters for one category. The same object every time."""
    return _stats[category]


def master_off() -> bool:
    """True when every category is refused regardless of its own setting."""
    return _truthy(os.environ.get(MASTER_OFF_FLAG, ""))


def allowed(category: str) -> bool:
    """Whether this category may open a connection right now."""
    if master_off():
        return False
    flag, default = _POLICY[category]
    override = os.environ.get(flag)
    if override is None or not override.strip():
        return default
    return _truthy(override)


def on_this_machine(destination: str) -> bool:
    """
    True when a URL names this computer: 127.x, ::1 or localhost.

    A request there does not leave the machine, so it is not egress and no
    switch here refuses it, INOX_NO_EGRESS included. That is what lets a
    creator who turned everything off still render images with a web UI they
    run themselves. A private address on the local network (192.168.x) is
    another machine and is not covered: it goes through require() like
    anything else.

    Callers decide when this applies. The image studio uses it only for the
    providers whose whole purpose is a local address, never for a cloud
    provider, so a cloud endpoint pointed at loopback by a test still meets
    the guard.
    """
    import ipaddress

    try:
        host = urlsplit(str(destination or "")).hostname or ""
    except ValueError:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def public_destination(destination: str) -> str:
    """
    Where a request went, without what it carried.

    Scheme, host and path only. A query string or a user:password@ prefix can
    hold a credential: Gemini took its API key as ?key=, and the ledger stored
    that URL whole, so the Local security tab handed the key to anyone shown
    its data. A destination that is not a URL keeps everything before its
    first ? or #.
    """
    text = str(destination or "")
    try:
        parts = urlsplit(text)
    except ValueError:
        parts = None
    if parts is not None and parts.scheme and parts.netloc:
        host = parts.netloc.rsplit("@", 1)[-1]
        return urlunsplit((parts.scheme, host, parts.path, "", ""))
    return re.split(r"[?#]", text, maxsplit=1)[0]


# Credential shapes, for text on its way to a log line or a response. Request
# libraries quote the URL they failed on, and a header dict printed by mistake
# carries its values, so both are scrubbed as well as the key formats the
# providers issue.
_SECRET_PATTERNS = (
    (re.compile(r"(?i)([?&](?:key|api[_-]?key|access[_-]?token|token)=)[^&#\s'\"]+"), r"\1[redacted]"),
    (
        re.compile(r"(?i)((?:authorization|x-api-key|x-goog-api-key)['\"]?\s*[:=]\s*['\"]?)(?:bearer\s+)?[^\s'\",}]+"),
        r"\1[redacted]",
    ),
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1[redacted]"),
    (re.compile(r"AIza[0-9A-Za-z_-]{16,}"), "[redacted]"),
    (re.compile(r"\b(?:sk|gsk|xai)[-_][A-Za-z0-9_-]{8,}"), "[redacted]"),
)


# Every key this process has been handed, so redact() can replace it by value.
# The patterns above know the providers' key formats; a custom endpoint's or
# Ollama proxy's key can have any shape, and an endpoint that quotes it back in
# its error put it in a response, the Prompt tab and the log.
_known_secrets: set = set()
_MAX_KNOWN_SECRETS = 64


def remember_secret(value: Any) -> None:
    """Registers a key so redact() removes it wherever it appears."""
    secret = str(value or "").strip()
    if len(secret) < 8:
        return
    with _lock:
        if secret not in _known_secrets and len(_known_secrets) < _MAX_KNOWN_SECRETS:
            _known_secrets.add(secret)


def redact(text: Any) -> str:
    """Text with every API key, bearer token and key= value replaced."""
    cleaned = str(text if text is not None else "")
    with _lock:
        known = sorted(_known_secrets, key=len, reverse=True)
    for secret in known:
        for form in {secret, quote(secret, safe=""), quote_plus(secret)}:
            cleaned = cleaned.replace(form, "[redacted]")
    for pattern, replacement in _SECRET_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned


def guard(destination: str, category: str = "linkedin") -> Optional[Dict[str, Any]]:
    """
    Call before any outbound request.

    Returns None when the request may proceed, and a refusal dict when it may
    not. Callers return the refusal to their own caller unchanged, so a request
    that did not happen is visible as a refusal rather than as an empty result.
    """
    if category not in _POLICY:
        raise ValueError(f"unknown egress category: {category!r}")

    stats = _stats[category]
    # Recorded and returned without its query, which is where a key can sit.
    destination = public_destination(destination)
    if allowed(category):
        with _lock:
            stats["performed"] += 1
            stats["last_destination"] = destination
        return None

    with _lock:
        stats["refused"] += 1
        stats["last_refused_endpoint"] = destination

    flag, _default = _POLICY[category]
    reason = (
        f"{MASTER_OFF_FLAG} is set, so nothing in this studio may open a connection."
        if master_off()
        else f"Outbound {category} requests are off. Set {flag}=1 to allow them."
    )
    return {
        "status": "egress_refused",
        # Not healthy and not unhealthy: unknown. Answering True here once let
        # a session health check certify a session it had never looked at.
        # Callers must be able to tell "we did not look" from "we looked and it
        # was fine".
        "healthy": None,
        "checked": False,
        "category": category,
        "endpoint": destination,
        # Every other branch of check_session_health returns this key, and
        # dropping it made callers that read circuit_breaker.state raise.
        "circuit_breaker": None,
        "message": reason,
    }


def describe() -> Dict[str, Any]:
    """
    What has left this machine, and what currently may.

    Read by /api/v1/egress/status so the Local security tab can report the
    real counters instead of restating a promise.
    """
    return {
        "master_off": master_off(),
        "master_flag": MASTER_OFF_FLAG,
        "categories": [
            {
                "name": name,
                "allowed": allowed(name),
                "flag": _POLICY[name][0],
                "default_allowed": _POLICY[name][1],
                "performed": _stats[name]["performed"],
                "refused": _stats[name]["refused"],
                "last_destination": _stats[name]["last_destination"],
                "last_refused_endpoint": _stats[name]["last_refused_endpoint"],
            }
            for name in sorted(_POLICY)
        ],
        "total_performed": sum(s["performed"] for s in _stats.values()),
        "total_refused": sum(s["refused"] for s in _stats.values()),
    }


def reset_for_tests() -> None:
    """Zeroes every counter in place, preserving dict identity."""
    with _lock:
        for stats in _stats.values():
            stats.update(
                {
                    "refused": 0,
                    "performed": 0,
                    "last_refused_endpoint": None,
                    "last_destination": None,
                }
            )


class EgressRefused(RuntimeError):
    """
    Raised by require() when a call may not open a connection.

    A distinct type so a refusal is never mistaken for a network failure by
    anything that cares about the difference, and so the reason travels with
    it. Every call site that raises this already sits inside a handler that
    reports the message, which is what keeps a refused request from looking
    like an empty result.
    """


def require(destination: str, category: str) -> None:
    """
    guard(), for callers whose failure path is an exception rather than a
    returned dict.

    Fourteen call sites across six modules each return a different shape on
    failure, and threading a refusal dict through all of them would have meant
    fourteen bespoke edits to the success paths as well. Raising fails closed,
    counts the refusal the same way, and surfaces the reason through error
    handling those modules already have.
    """
    refusal = guard(destination, category=category)
    if refusal is not None:
        raise EgressRefused(refusal["message"])
