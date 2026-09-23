"""
Speaking MCP to a local server, over stdio.
===========================================

The studio is an MCP *client*. It does not expose itself to an agent; it
reaches out to servers that hold the things a post should be grounded in: the
creator's notes, their repository, their calendar.

That direction is the whole point. A cloud writing tool has never seen your
work and never will, which is why its output reads generic no matter how good
the model is. A local-first product is the only shape that can fix that, and
this is the part that makes it possible.

Why this is hand written rather than the `mcp` SDK
--------------------------------------------------
The SDK is importable on the machine this was written on and is declared in
neither requirements.txt nor pyproject.toml, which is precisely the failure
this project has already been bitten by once: a test passed for weeks against
a pyyaml nobody had declared. `tools/build_portable.py` vendors from
requirements.txt, so an undeclared import is present in development and absent
in the artifact a user runs.

Declaring it would be the other option, and it was weighed. The SDK is
anyio-based and pulls a dependency tree into a product that ships an
embeddable CPython inside an installer people download. The wire format here
is newline-delimited JSON-RPC 2.0 over a pipe, which is a few hundred lines of
standard library, and this codebase already hand writes an HTTP readiness
probe and its Win32 job object calls for the same reason.

What this module refuses to do
------------------------------
It does not call tools. `tools/call` is how an MCP server performs actions:
sending mail, writing files, opening pull requests. Grounding a draft needs
none of that, and a writing assistant that can act on the world is a different
product with a different consent conversation. This client reads resources and
nothing else. The absence is deliberate and is tested.

Strict Invariants:
- Zero em-dashes in any code, docstring, or comment.
- No shell. A server command is a list of arguments, never a string.
- Nothing here raises to a caller. A server that is down degrades grounding to
  nothing, and generation continues without it.
"""

import json
import os
import subprocess
import sys
import threading
from typing import Any, Dict, List, Optional

# The revision of the protocol this client implements. Sent during the
# handshake so a server can refuse or adapt. A server answering with something
# unexpected is logged and dropped rather than guessed at.
PROTOCOL_VERSION = "2024-11-05"

CLIENT_NAME = "inox-hydra"
CLIENT_VERSION = "1"

# A server is a subprocess on the creator's own machine, not a network peer,
# so these are guards against a hung or runaway process rather than against an
# attacker. They are deliberately short: grounding is an enhancement, and a
# writing tool that stalls for a minute because a notes server is wedged has
# made the creator's day worse, not better.
START_TIMEOUT_SECONDS = 10.0
REQUEST_TIMEOUT_SECONDS = 15.0

# One resource that is larger than this is not grounding material, it is a
# file somebody pointed at by mistake. Read in full it would dominate the
# prompt and push out the creator's actual draft.
MAX_RESOURCE_BYTES = 64 * 1024

# A malformed or hostile server could otherwise stream forever into memory.
MAX_LINE_BYTES = 8 * 1024 * 1024


class McpError(Exception):
    """Internal. Never escapes this module; callers get None or an empty list."""


class McpServer:
    """
    One MCP server, running as a child process, spoken to over its stdio.

    Short lived on purpose. The server is started, asked what it has, read
    from, and stopped. Holding subprocesses open for the life of the studio
    would mean a creator's notes indexer running all day because they once
    generated a post, and a crash leaving orphans behind.
    """

    def __init__(self, name: str, command: List[str], cwd: Optional[str] = None,
                 env: Optional[Dict[str, str]] = None):
        self.name = name
        self.command = list(command)
        self.cwd = cwd
        self.env = env or {}
        self._process: Optional[subprocess.Popen] = None
        self._next_id = 0
        self._lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_exc):
        self.stop()
        return False

    def start(self) -> bool:
        """Launches the server and completes the handshake. False if it did not."""
        if not self.command:
            return False

        # A list, never a string, and never shell=True. A server command comes
        # from a settings row, and a settings row is one bad import away from
        # being attacker influenced. The same reasoning that rewrote the
        # browser launcher after a --gpu-launcher argument turned into
        # arbitrary execution.
        environment = os.environ.copy()
        environment.update({str(k): str(v) for k, v in self.env.items()})

        creation_flags = 0
        if sys.platform == "win32":
            # No console window. A creator generating a post should not see
            # black boxes appear behind the studio.
            creation_flags = 0x0800_0000  # CREATE_NO_WINDOW

        try:
            self._process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=self.cwd or None,
                env=environment,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creation_flags,
            )
        except (OSError, ValueError):
            self._process = None
            return False

        try:
            result = self._request("initialize", {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
            }, timeout=START_TIMEOUT_SECONDS)
        except McpError:
            self.stop()
            return False

        if not isinstance(result, dict):
            self.stop()
            return False

        # The handshake is not complete until the client says so. A server is
        # entitled to reject requests sent before this notification.
        self._notify("notifications/initialized", {})
        return True

    def _kill_process(self) -> None:
        """
        Ends the child without clearing self._process.

        Called from the timeout timer thread, where the reader is still parked
        inside readline(). Killing the process closes the pipe, which is what
        returns that read. stop() clears the handle afterwards.
        """
        process = self._process
        if process is None:
            return
        try:
            process.kill()
        except Exception:
            pass

    def stop(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        for close in (process.stdin, process.stdout):
            try:
                if close:
                    close.close()
            except Exception:
                pass
        try:
            process.terminate()
            process.wait(timeout=3)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    # -- wire --------------------------------------------------------------

    def _send(self, message: Dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise McpError("server is not running")
        try:
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()
        except (OSError, ValueError) as exc:
            raise McpError(f"could not write to {self.name}: {exc}")

    def _notify(self, method: str, params: Dict[str, Any]) -> None:
        """Fire and forget. A notification has no id and expects no reply."""
        try:
            self._send({"jsonrpc": "2.0", "method": method, "params": params})
        except McpError:
            pass

    def _request(self, method: str, params: Dict[str, Any],
                 timeout: float = REQUEST_TIMEOUT_SECONDS) -> Any:
        with self._lock:
            self._next_id += 1
            request_id = self._next_id

        self._send({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        })

        # Read until the reply with our id arrives. A server may interleave
        # notifications and server-to-client requests, and those are skipped
        # rather than mistaken for the answer.
        #
        # The timeout kills the process rather than setting a flag. readline()
        # on a pipe blocks, and it does not return to check a flag, so a timer
        # that only set one produced a timeout that never fired and a studio
        # that hung forever on a wedged server. Closing the pipe from under
        # the read is what actually unblocks it: readline returns empty,
        # _read_message returns None, and the loop below reports the failure.
        expired = threading.Event()

        def give_up():
            expired.set()
            self._kill_process()

        timer = threading.Timer(timeout, give_up)
        timer.daemon = True
        timer.start()
        try:
            while True:
                message = self._read_message()
                if message is None:
                    if expired.is_set():
                        raise McpError(f"{self.name} did not answer {method} in {timeout}s")
                    raise McpError(f"{self.name} closed the connection")
                if message.get("id") != request_id:
                    continue
                if "error" in message:
                    detail = message["error"]
                    raise McpError(f"{self.name} refused {method}: {detail}")
                return message.get("result")
        finally:
            timer.cancel()

    def _read_message(self) -> Optional[Dict[str, Any]]:
        process = self._process
        if process is None or process.stdout is None:
            return None
        try:
            line = process.stdout.readline(MAX_LINE_BYTES)
        except (OSError, ValueError):
            return None
        if not line:
            return None
        line = line.strip()
        if not line:
            return {}
        try:
            parsed = json.loads(line)
        except (ValueError, TypeError):
            # A server that writes noise to stdout is common enough to be worth
            # stepping over rather than failing on.
            return {}
        return parsed if isinstance(parsed, dict) else {}

    # -- the only two things this client asks for --------------------------

    def list_resources(self) -> List[Dict[str, Any]]:
        """What this server is offering. Never raises."""
        try:
            result = self._request("resources/list", {})
        except McpError:
            return []
        if not isinstance(result, dict):
            return []
        resources = result.get("resources")
        if not isinstance(resources, list):
            return []
        return [r for r in resources if isinstance(r, dict) and r.get("uri")]

    def read_resource(self, uri: str) -> Optional[str]:
        """
        The text of one resource, truncated at MAX_RESOURCE_BYTES.

        Returns None rather than raising, because a single unreadable note is
        not a reason to abandon a draft.
        """
        if not isinstance(uri, str) or not uri:
            return None
        try:
            result = self._request("resources/read", {"uri": uri})
        except McpError:
            return None
        if not isinstance(result, dict):
            return None

        contents = result.get("contents")
        if not isinstance(contents, list):
            return None

        collected = []
        budget = MAX_RESOURCE_BYTES
        for item in contents:
            if not isinstance(item, dict):
                continue
            # Binary resources carry `blob`. There is nothing useful to say to
            # a language model about a base64 image, so they are skipped.
            text = item.get("text")
            if not isinstance(text, str) or not text:
                continue
            chunk = text[:budget]
            collected.append(chunk)
            budget -= len(chunk)
            if budget <= 0:
                break

        if not collected:
            return None
        return "\n".join(collected)
