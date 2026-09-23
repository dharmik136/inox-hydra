"""
Which MCP servers exist, and which the creator has actually agreed to.
======================================================================

Two separate facts, deliberately not one. A server can be configured and
switched off, and that is the state everything arrives in.

Adding a server tells the studio a command exists. Enabling it is the creator
saying "read this, and put what you find into my drafts." Collapsing those
into a single step would mean pasting a command from a README and having a
notes directory read on the next generation, which is not a thing anyone
agreed to.

The same reasoning as the rest of this product: a fresh install belongs to
nobody, autostart is off until asked for, the update check is opt in. Absence
of a preference is not consent, and the default is always the one that does
nothing.

Storage is the settings table, as one JSON document under a single key. There
is no migration for this, on purpose: a creator with no MCP servers has a
missing row, reads as an empty list, and nothing anywhere has to know the
feature exists.

Strict Invariants:
- Zero em-dashes in any code, docstring, or comment.
- A newly added server is disabled. There is no parameter to change that.
- Nothing here raises to a caller. An unreadable settings row reads as no
  servers, which grounds nothing, which is the safe direction.
"""

import json
import re
from typing import Any, Dict, List, Optional

try:
    from ..database import get_db
except ImportError:  # pragma: no cover - direct script use
    from database import get_db

SETTINGS_KEY = "mcp_servers"

# A name is a label in the interface and a key in provenance, so it is kept to
# something that reads as a name and cannot be confused for a path or a flag.
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,48}$")

MAX_SERVERS = 12


def _load_raw() -> List[Dict[str, Any]]:
    conn = None
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (SETTINGS_KEY,)
        ).fetchone()
    except Exception:
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    if not row:
        return []
    try:
        parsed = json.loads(row["value"])
    except (ValueError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [entry for entry in parsed if isinstance(entry, dict)]


def _store(servers: List[Dict[str, Any]]) -> bool:
    """True only if the write actually happened."""
    conn = None
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (SETTINGS_KEY, json.dumps(servers)),
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _normalise(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    name = str(entry.get("name") or "").strip()
    if not NAME_PATTERN.match(name):
        return None

    command = entry.get("command")
    if isinstance(command, str):
        # Rejected rather than split. Splitting a string into argv is where
        # quoting bugs and injection both live, and the caller knows the
        # arguments better than a parser here would guess them.
        return None
    if not isinstance(command, list) or not command:
        return None
    command = [str(part) for part in command if str(part).strip()]
    if not command:
        return None

    env = entry.get("env")
    if not isinstance(env, dict):
        env = {}

    return {
        "name": name,
        "command": command,
        "cwd": str(entry.get("cwd") or "") or None,
        "env": {str(k): str(v) for k, v in env.items()},
        "enabled": bool(entry.get("enabled", False)),
        "description": str(entry.get("description") or "")[:200],
    }


def list_servers() -> List[Dict[str, Any]]:
    """Every configured server, enabled or not."""
    normalised = []
    for entry in _load_raw():
        clean = _normalise(entry)
        if clean:
            normalised.append(clean)
    return normalised


def enabled_servers() -> List[Dict[str, Any]]:
    """
    Only the ones the creator switched on.

    This is the function grounding calls. Everything else in this module is
    configuration; this is the consent boundary.
    """
    return [server for server in list_servers() if server.get("enabled")]


def add_server(name: str, command: List[str], cwd: Optional[str] = None,
               env: Optional[Dict[str, str]] = None,
               description: str = "") -> Dict[str, Any]:
    """
    Registers a server, switched off.

    There is deliberately no `enabled` parameter. Adding and agreeing to be
    read are different acts, and a single call that did both would let a
    pasted configuration start reading a creator's files on the next draft.
    """
    candidate = _normalise({
        "name": name,
        "command": command,
        "cwd": cwd,
        "env": env or {},
        "description": description,
        "enabled": False,
    })
    if not candidate:
        return {"status": "error", "message": "A server needs a plain name and a command given as a list of arguments."}

    servers = list_servers()
    if len(servers) >= MAX_SERVERS:
        return {"status": "error", "message": f"At most {MAX_SERVERS} servers."}
    if any(existing["name"].lower() == candidate["name"].lower() for existing in servers):
        return {"status": "error", "message": f"A server named {candidate['name']} already exists."}

    servers.append(candidate)
    if not _store(servers):
        return {"status": "error", "message": "The server could not be saved."}
    return {"status": "success", "server": candidate}


def set_enabled(name: str, enabled: bool) -> Dict[str, Any]:
    """
    Turns a server on or off, and reports the state it achieved.

    Reads back rather than echoing the request, for the reason the queue
    pause was rewritten: a caller that is told "enabled" when the write failed
    believes their drafts are grounded when they are not.
    """
    servers = list_servers()
    target = None
    for server in servers:
        if server["name"].lower() == str(name or "").strip().lower():
            server["enabled"] = bool(enabled)
            target = server
            break

    if target is None:
        return {"status": "error", "message": f"No server named {name}."}

    if not _store(servers):
        return {"status": "error", "message": "The change could not be saved.",
                "enabled": not bool(enabled)}

    current = next(
        (s["enabled"] for s in list_servers() if s["name"].lower() == target["name"].lower()),
        None,
    )
    if current is not bool(enabled):
        return {"status": "error", "message": "The change did not persist.",
                "enabled": bool(current)}

    return {"status": "success", "server": target["name"], "enabled": bool(enabled)}


def remove_server(name: str) -> Dict[str, Any]:
    servers = list_servers()
    remaining = [s for s in servers if s["name"].lower() != str(name or "").strip().lower()]
    if len(remaining) == len(servers):
        return {"status": "error", "message": f"No server named {name}."}
    if not _store(remaining):
        return {"status": "error", "message": "The removal could not be saved."}
    return {"status": "success", "removed": name}
