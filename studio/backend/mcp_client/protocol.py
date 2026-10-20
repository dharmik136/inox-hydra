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
- No shell. A server command is a list of arguments, never a string. The one
  exception is a Windows .cmd or .bat launcher, which only cmd.exe can run,
  and then any argument cmd.exe would read as an operator is refused.
- A server gets an allowlisted environment, never the studio's keys.
- A stop or a timeout ends the server's whole process group.
- Nothing here raises to a caller. A server that is down degrades grounding to
  nothing, and generation continues without it.
"""

import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Union

try:
    from ..text_cut import clip
except ImportError:  # pragma: no cover - direct script use
    from text_cut import clip

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

# What a server is given of the studio's own environment: enough to find its
# runtime, its home folder and a temporary folder, to read text in the
# creator's language, and to reach the network the way this machine does
# (proxy and certificate settings, without which npx -y fails on a company
# network). Nothing else. It used to be the whole environment, so a
# third-party package registered to read notes was handed every exported
# ANTHROPIC_API_KEY, GEMINI_API_KEY and TELEGRAM_BOT_TOKEN, and the studio's
# own INOX_HYDRA_HOME. A server that needs a variable gets it from its own
# `env` setting, which the creator wrote for it. Names are compared in upper
# case because Windows treats them that way.
INHERITED_VARIABLES = frozenset({
    "PATH", "PATHEXT", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LANGUAGE", "TZ", "TERM",
    "TMPDIR", "TEMP", "TMP",
    "USERPROFILE", "USERNAME", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "COMMONPROGRAMFILES", "COMMONPROGRAMFILES(X86)",
    "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "OS", "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS", "REQUESTS_CA_BUNDLE", "PIP_CERT",
})
INHERITED_PREFIXES = ("LC_", "XDG_", "NPM_CONFIG_")

# Through cmd.exe these characters can end one command and start another, or
# expand a variable, so an argument carrying one is never passed to it.
CMD_METACHARACTERS = frozenset('&|<>^%!"\r\n')

_CREATE_NO_WINDOW = 0x0800_0000
_CREATE_NEW_PROCESS_GROUP = 0x0000_0200


class McpError(Exception):
    """Internal. Never escapes this module; callers get None or an empty list."""


def child_environment(parent: Dict[str, str], own: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """The environment a server starts with: the allowlist above, then its own settings."""
    environment = {
        key: value for key, value in parent.items()
        if key.upper() in INHERITED_VARIABLES or key.upper().startswith(INHERITED_PREFIXES)
    }
    environment.update({str(k): str(v) for k, v in (own or {}).items()})
    return environment


def _variable(environment: Dict[str, str], name: str) -> str:
    for key, value in environment.items():
        if key.upper() == name:
            return value
    return ""


def _find_on_windows(program: str, environment: Dict[str, str]) -> Optional[str]:
    """
    Where Windows would find `program`, trying each extension in PATHEXT.

    Written out rather than shutil.which so it reads the server's PATH and can
    be exercised on any OS.
    """
    extensions = [e for e in (_variable(environment, "PATHEXT") or ".COM;.EXE;.BAT;.CMD").split(";") if e]
    _, given = os.path.splitext(program)
    suffixes = [""] + extensions if given else extensions
    if os.path.dirname(program):
        folders = [""]
    else:
        folders = [f for f in _variable(environment, "PATH").split(";") if f]
    for folder in folders:
        # Windows names are case-insensitive: npx.CMD in PATHEXT finds npx.cmd.
        where = os.path.dirname(program) if not folder else folder
        try:
            present = {entry.lower(): entry for entry in os.listdir(where or ".")}
        except OSError:
            continue
        for suffix in suffixes:
            wanted = (os.path.basename(program) + suffix).lower()
            if wanted in present:
                candidate = os.path.join(where, present[wanted]) if where else present[wanted]
                if os.path.isfile(candidate):
                    return candidate
    return None


def launch_command(command: List[str], environment: Dict[str, str],
                   platform: str = sys.platform) -> Union[List[str], str]:
    """
    What to hand Popen for `command`.

    Elsewhere the list as given. On Windows the program is looked up with
    PATHEXT, because npx and most other launchers are installed as npx.cmd,
    which CreateProcess will not find from "npx" and cannot run by itself. A
    .cmd or .bat is run through cmd.exe, the only thing that can run one, as a
    single quoted command line; an argument that cmd.exe would read as an
    operator is refused rather than passed.
    """
    if platform != "win32":
        return list(command)
    program, arguments = command[0], list(command[1:])
    resolved = _find_on_windows(program, environment)
    if resolved is None:
        raise McpError(f"the command {program} was not found")
    if os.path.splitext(resolved)[1].lower() not in (".cmd", ".bat"):
        return [resolved] + arguments
    for part in [resolved] + arguments:
        if any(ch in CMD_METACHARACTERS for ch in part):
            raise McpError(
                f"{os.path.basename(resolved)} runs through cmd.exe, and an argument holds one of "
                f"& | < > ^ % ! or a quote, which cmd.exe would treat as part of a command"
            )
    shell = _variable(environment, "COMSPEC") or "cmd.exe"
    return f'"{shell}" /d /s /c "{subprocess.list2cmdline([resolved] + arguments)}"'


def _end_group(process: subprocess.Popen, force: bool) -> None:
    """Asks, or with `force` makes, the server and every process it started stop."""
    if sys.platform == "win32":
        if not force and process.poll() is not None:
            return
        try:
            # /T ends the tree the launcher started; TerminateProcess alone
            # would end only the launcher.
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=10, creationflags=_CREATE_NO_WINDOW)
        except Exception:
            pass
        try:
            process.kill()
        except Exception:
            pass
        return
    try:
        # start_new_session made the server the leader of its own group, so
        # its id is the group's id.
        os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass


class McpServer:
    """
    One MCP server, running as a child process, spoken to over its stdio.

    Short lived on purpose. The server is started, asked what it has, read
    from, and stopped. Holding subprocesses open for the life of the studio
    would mean a creator's notes indexer running all day because they once
    generated a post, and a crash leaving orphans behind.

    The server runs in a process group of its own, and every stop or timeout
    ends the whole group. Most servers start through a launcher (npx, uvx, a
    shell script) that runs the real server as its child; killing only the
    launcher left that child running and holding the pipe open. Replies are
    read on a thread of their own, so a request waits on a queue with a
    deadline rather than inside a read that only the server can end.

    `deadline`, a time.monotonic() value, caps every request this server
    makes, so a caller with several servers can give them one budget.
    """

    def __init__(self, name: str, command: List[str], cwd: Optional[str] = None,
                 env: Optional[Dict[str, str]] = None, deadline: Optional[float] = None):
        self.name = name
        self.command = list(command)
        self.cwd = cwd
        self.env = env or {}
        self.deadline = deadline
        # Why the last start or request failed, in words the creator can act on.
        self.last_error: Optional[str] = None
        self._process: Optional[subprocess.Popen] = None
        self._replies: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue()
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
        self.last_error = None
        if not self.command:
            self.last_error = "has no command to run"
            return False

        # A list, never a string, and never shell=True. A server command comes
        # from a settings row, and a settings row is one bad import away from
        # being attacker influenced. The same reasoning that rewrote the
        # browser launcher after a --gpu-launcher argument turned into
        # arbitrary execution. The one exception is a Windows .cmd launcher,
        # which only cmd.exe can run; see launch_command.
        environment = child_environment(dict(os.environ), self.env)

        options: Dict[str, Any] = {}
        if sys.platform == "win32":
            # No console window. A creator generating a post should not see
            # black boxes appear behind the studio.
            options["creationflags"] = _CREATE_NO_WINDOW | _CREATE_NEW_PROCESS_GROUP
        else:
            options["start_new_session"] = True

        try:
            argv = launch_command(self.command, environment)
            self._process = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=self.cwd or None,
                env=environment,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **options,
            )
        except McpError as refused:
            self.last_error = str(refused)
            self._process = None
            return False
        except FileNotFoundError:
            self.last_error = (f"the command {self.command[0]} was not found"
                               + (f" in {self.cwd}" if self.cwd and not os.path.isdir(self.cwd) else ""))
            self._process = None
            return False
        except (OSError, ValueError) as error:
            self.last_error = f"could not be started: {getattr(error, 'strerror', None) or error}"
            self._process = None
            return False

        self._replies = queue.Queue()
        reader = threading.Thread(target=self._read_replies, args=(self._process, self._replies),
                                  name=f"mcp-reader-{self.name}", daemon=True)
        reader.start()

        try:
            result = self._request("initialize", {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
            }, timeout=START_TIMEOUT_SECONDS)
        except McpError as failed:
            self.last_error = str(failed)
            self.stop()
            return False

        if not isinstance(result, dict):
            self.last_error = "answered the handshake with something that is not MCP"
            self.stop()
            return False

        # The handshake is not complete until the client says so. A server is
        # entitled to reject requests sent before this notification.
        self._notify("notifications/initialized", {})
        return True

    def _kill_process(self) -> None:
        """Ends the server and everything it started, without clearing self._process."""
        process = self._process
        if process is None:
            return
        _end_group(process, force=True)

    def stop(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
        except Exception:
            pass
        _end_group(process, force=False)
        try:
            process.wait(timeout=2)
        except Exception:
            pass
        # Whatever ignored the polite request, the launcher's children included.
        _end_group(process, force=True)
        try:
            process.wait(timeout=2)
        except Exception:
            pass

    # -- wire --------------------------------------------------------------

    def _send(self, message: Dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise McpError("is not running")
        try:
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()
        except (OSError, ValueError) as exc:
            raise McpError(f"stopped reading its input ({exc})")

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

        started = time.monotonic()
        stop_at = started + timeout
        if self.deadline is not None:
            stop_at = min(stop_at, self.deadline)
        waited = max(0.0, stop_at - started)

        self._send({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        })

        # Read until the reply with our id arrives. A server may interleave
        # notifications and server-to-client requests, and those are skipped
        # rather than mistaken for the answer. Replies arrive on a queue fed
        # by the reader thread, so running out of time is a queue that stays
        # empty, which this thread notices, rather than a read that never
        # returns. The server is ended then, so it is not left running.
        while True:
            remaining = stop_at - time.monotonic()
            if remaining <= 0:
                self._kill_process()
                raise McpError(f"did not answer {method} within {waited:g} s")
            try:
                message = self._replies.get(timeout=remaining)
            except queue.Empty:
                continue
            if message is None:
                raise McpError(f"closed the connection before answering {method}")
            if message.get("id") != request_id:
                continue
            if "error" in message:
                detail = message["error"]
                if isinstance(detail, dict) and detail.get("message"):
                    detail = detail["message"]
                raise McpError(f"refused {method}: {clip(str(detail), 200)}")
            return message.get("result")

    @staticmethod
    def _read_replies(process: subprocess.Popen, replies: "queue.Queue") -> None:
        """Runs on its own thread: every line the server writes, parsed, then None at the end."""
        stream = process.stdout
        try:
            while stream is not None:
                try:
                    line = stream.readline(MAX_LINE_BYTES)
                except (OSError, ValueError):
                    break
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except (ValueError, TypeError):
                    # A server that writes noise to stdout is common enough to
                    # be worth stepping over rather than failing on.
                    continue
                if isinstance(parsed, dict):
                    replies.put(parsed)
        finally:
            replies.put(None)
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass

    # -- the only two things this client asks for --------------------------

    def list_resources(self) -> List[Dict[str, Any]]:
        """What this server is offering. Never raises."""
        try:
            result = self._request("resources/list", {})
        except McpError as failed:
            self.last_error = str(failed)
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
        except McpError as failed:
            self.last_error = str(failed)
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
            chunk = clip(text, budget)
            collected.append(chunk)
            budget -= len(chunk)
            if budget <= 0:
                break

        if not collected:
            return None
        return "\n".join(collected)
