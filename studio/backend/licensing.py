"""
Offline Licence: Tiers, Prices, and a Signature the Studio Checks Itself.
=========================================================================
The product promises that nothing leaves the machine, which rules out a
licence server. So a licence is a signed statement, checked here against the
vendor's public key, with no network call ever:

  IHL1.<payload>.<signature>

where payload is base64url JSON ({email, tier, kind, profiles, issued_at,
expires_at, updates_until}) and signature is Ed25519 over the bytes
"IHL1.<payload>", made by tools/licence_keys.py on the vendor's machine.

Tiers and prices (planning/7 Roadmap/Pricing Hypothesis.md, chosen by the
owner on 2026-10-19):

  Free     composer, fold simulator, audit, hooks from templates, export
  Creator  $12 a month billed yearly ($144), or $249 once with a year of
           updates: analytics, leads, Today, patterns, AI with your own key,
           Obsidian export, archive import
  Agency   $39 a month: up to 5 creator profiles, each with its own database

An annual licence that expires falls back to the free tier. Nothing is
deleted and everything stays readable and exportable. A lifetime licence
keeps its tier, and records until when it is owed updates.

What is enforced today: the number of creator profiles. The Creator features
are open to everyone while BETA_OPEN is true, for the design-partner beta;
turning it off at launch is Phase 4 of the roadmap, and FEATURES is the map
that switch will read. A licence entered now is checked and kept either way.

Strict Invariants:
- Zero em-dashes in any code, docstring or comment.
- Zero egress: verification is local, and nothing here opens a socket.
- A bad or unreadable licence never stops the studio: it is reported, and
  the studio runs as the free tier.
"""

import base64
import json
import os
import tempfile
from datetime import date
from typing import Any, Callable, Dict, List, Optional

try:
    from . import ed25519
    from . import paths
except ImportError:
    import ed25519
    import paths

PREFIX = "IHL1"
LICENCE_FILENAME = "licence.key"

# Base64 Ed25519 public keys whose signatures this build accepts. The secret
# halves are kept by the vendor, outside this repository.
PUBLIC_KEYS: List[str] = [
    # The vendor key, made 2026-10-19 with tools/licence_keys.py new-keypair.
    "1sxHVIKfBSlRXgbD3WZdKXDp1qyuJQKj63H/ePbHgrg=",
]

# Creator features are open to every install during the design-partner beta.
BETA_OPEN = True

TIERS: Dict[str, Dict[str, Any]] = {
    "free": {"label": "Free", "profiles": 1},
    "creator": {"label": "Creator", "profiles": 1},
    "agency": {"label": "Agency", "profiles": 5},
}
PAID_TIERS = ("creator", "agency")
_RANK = {"free": 0, "creator": 1, "agency": 2}

PRICES: List[Dict[str, str]] = [
    {"tier": "creator", "label": "Creator",
     "price": "$12 a month, billed yearly ($144), or $249 once with a year of updates",
     "includes": "Analytics, leads, Today, patterns, AI with your own key, the Obsidian export "
                 "and the LinkedIn archive import."},
    {"tier": "agency", "label": "Agency", "price": "$39 a month, for up to 5 creator profiles",
     "includes": "Every Creator feature, for each profile, and each profile with its own database."},
]

# What each feature needs. Read by allows(); enforced once BETA_OPEN is off.
FEATURES: Dict[str, str] = {
    "composer": "free",
    "fold_simulator": "free",
    "audit": "free",
    "template_hooks": "free",
    "export": "free",
    "analytics": "creator",
    "leads": "creator",
    "today": "creator",
    "patterns": "creator",
    "ai": "creator",
    "obsidian_export": "creator",
    "archive_import": "creator",
    "multiple_profiles": "agency",
}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def encode(payload: Dict[str, Any], signer: Callable[[bytes], bytes]) -> str:
    """The licence text for a payload, signed by signer(message) -> signature."""
    body = _b64url(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    signed = f"{PREFIX}.{body}".encode("ascii")
    return f"{PREFIX}.{body}.{_b64url(signer(signed))}"


def _public_keys() -> List[bytes]:
    keys = []
    for text in PUBLIC_KEYS:
        try:
            raw = base64.b64decode(text)
        except (ValueError, TypeError):
            continue
        if len(raw) == 32:
            keys.append(raw)
    return keys


KINDS = ("annual", "monthly", "lifetime")
MAX_PROFILES = 50
MAX_KEY_CHARS = 4000


def _date_or_none(value: Any) -> Optional[str]:
    """An ISO date (YYYY-MM-DD), or None. Raises ValueError for anything else."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("not a date")
    return date.fromisoformat(value[:10]).isoformat()


def _normalise(payload: Any) -> Dict[str, Any]:
    """
    The payload with every field checked and typed, or ValueError.

    Checked even though the signature already vouches for it: a key the vendor
    issued with a bad field must be refused here, not break every screen that
    asks which tier is in effect.
    """
    if not isinstance(payload, dict):
        raise ValueError("not an object")
    tier = payload.get("tier")
    if tier not in PAID_TIERS:
        raise ValueError("unknown tier")
    kind = payload.get("kind", "annual")
    if kind not in KINDS:
        raise ValueError("unknown kind")
    profiles = payload.get("profiles", TIERS[tier]["profiles"])
    if isinstance(profiles, bool) or not isinstance(profiles, int) or not 1 <= profiles <= MAX_PROFILES:
        raise ValueError("bad profile count")
    expires_at = _date_or_none(payload.get("expires_at"))
    if kind != "lifetime" and expires_at is None:
        raise ValueError("a licence that is not lifetime needs an end date")
    return {
        "email": str(payload.get("email") or "")[:200],
        "name": str(payload.get("name") or "")[:200],
        "tier": tier,
        "kind": kind,
        "profiles": profiles,
        "issued_at": _date_or_none(payload.get("issued_at")),
        "expires_at": expires_at,
        "updates_until": _date_or_none(payload.get("updates_until")),
    }


def read_licence_text(text: str) -> Dict[str, Any]:
    """{"valid": bool, "reason": str, "payload": dict or None}. Never raises."""
    text = "".join((text or "").split())
    parts = text.split(".")
    if len(text) > MAX_KEY_CHARS or len(parts) != 3 or parts[0] != PREFIX:
        return {"valid": False, "reason": "This is not an Inox Hydra licence key.", "payload": None}
    try:
        signature = _unb64url(parts[2])
        message = f"{PREFIX}.{parts[1]}".encode("ascii")
    except (ValueError, UnicodeError):
        return {"valid": False, "reason": "The licence key is damaged. Paste it again in full.", "payload": None}
    # The signature first, so nothing an unsigned key carries is ever parsed.
    if not any(ed25519.verify(key, message, signature) for key in _public_keys()):
        return {"valid": False, "reason": "The licence key's signature does not check out.", "payload": None}
    try:
        payload = _normalise(json.loads(_unb64url(parts[1]).decode("utf-8")))
    except (ValueError, UnicodeError, RecursionError, TypeError):
        return {"valid": False, "reason": "The licence key carries details this version cannot read.", "payload": None}
    return {"valid": True, "reason": "", "payload": payload}


def _licence_path() -> str:
    return os.path.join(paths.get_vault_dir(), LICENCE_FILENAME)


def _stored_text() -> Optional[str]:
    """The stored key, None when there is none, or "" when it cannot be read."""
    try:
        with open(_licence_path(), "r", encoding="ascii") as handle:
            return handle.read()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError):
        return ""


def _expired(payload: Dict[str, Any], today: date) -> bool:
    expires = payload.get("expires_at")
    return bool(expires) and date.fromisoformat(expires) < today


def current(today: Optional[date] = None) -> Dict[str, Any]:
    """
    The licence as the studio sees it now. Never raises.

    status is "none", "active", "expired" or "invalid"; tier is the tier in
    effect, which is "free" unless the licence is active.
    """
    today = today or date.today()
    text = _stored_text()
    state: Dict[str, Any] = {
        "status": "none",
        "tier": "free",
        "licence": None,
        "reason": "",
        "beta_open": BETA_OPEN,
        "prices": PRICES,
    }
    if text == "":
        state.update(status="invalid", reason="The stored licence file could not be read. Remove it and paste the key again.")
    elif text:
        read = read_licence_text(text)
        if not read["valid"]:
            state.update(status="invalid", reason=read["reason"])
        else:
            payload = read["payload"]
            state["licence"] = payload
            if _expired(payload, today):
                state.update(status="expired", reason="This licence has ended. Your data is all still here.")
            else:
                state.update(status="active", tier=payload["tier"])
    state["tier_label"] = TIERS[state["tier"]]["label"]
    state["profile_limit"] = _profile_limit(state)
    return state


def _profile_limit(state: Dict[str, Any]) -> int:
    if state["status"] == "active" and state["tier"] == "agency":
        return state["licence"]["profiles"]
    return TIERS["free"]["profiles"]


def profile_limit() -> int:
    """How many creator profiles this install may hold."""
    return current()["profile_limit"]


def allows(feature: str) -> bool:
    """Whether the licence in effect covers a feature in FEATURES."""
    needed = FEATURES.get(feature, "free")
    if BETA_OPEN and needed == "creator":
        return True
    return _RANK[current()["tier"]] >= _RANK[needed]


def install(text: str, today: Optional[date] = None) -> Dict[str, Any]:
    """
    Checks a licence key and keeps it. A bad key is refused and nothing changes.

    A key that has already ended is refused too: accepting it would replace a
    working licence with one that unlocks nothing.
    """
    read = read_licence_text(text)
    if not read["valid"]:
        return {"status": "error", "message": read["reason"]}
    if _expired(read["payload"], today or date.today()):
        return {"status": "error", "message": f"This licence ended on {read['payload']['expires_at']}. Nothing was changed."}
    clean = "".join(text.split())
    vault = paths.get_vault_dir()
    fd, tmp = tempfile.mkstemp(prefix=".licence-", dir=vault)
    try:
        with os.fdopen(fd, "w", encoding="ascii") as handle:
            handle.write(clean + "\n")
        os.replace(tmp, _licence_path())
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return {"status": "success", "licence": current(today)}


def remove() -> Dict[str, Any]:
    try:
        os.remove(_licence_path())
    except FileNotFoundError:
        pass
    return {"status": "success", "licence": current()}
