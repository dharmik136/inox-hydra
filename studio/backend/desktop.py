"""
Desktop Integration: The Difference Between A Server And An Application.
========================================================================

The studio has always been a correct local server that a person reached by
opening a browser at a port number. Everything in this module is about the gap
between that and something a person would call an application: it has a name
Windows knows, an icon of its own, it starts when they log in if they asked it
to, and starting it twice does not produce two of it.

None of this changes what the product does. It changes whether it reads as a
product.

Four pieces:

  Identity.
    Windows groups taskbar buttons, toasts and jump lists by an Application
    User Model ID. A process that never sets one inherits whatever the host
    executable is, which for us means a window that says "python". Setting it
    explicitly costs one call and has to happen before any window exists.

  Autostart.
    A per user Startup shortcut, not a Run registry key. Both work, but a
    shortcut is the one a person can find, read and delete without a registry
    editor, and this product's whole argument is that the user owns what
    happens on their machine. It is also off until asked for, and visible in
    Settings once on, because software that silently adds itself to startup is
    the kind of software this is meant to replace.

  Single instance.
    A named mutex. The second launch does not start a competing daemon that
    fights the first one for port 8000.

  Icon.
    Resolved here so the tray, the shortcut and the installer all point at one
    file rather than three guesses.

Everything degrades quietly off Windows or when a call fails, because a desktop
nicety failing must never stop the studio from running.

Strict Invariants:
- Zero em-dashes in any code, docstring, or comment.
- Autostart is opt in, reversible, and visible.
- Nothing here raises into a request handler.
"""

import os
import subprocess
import sys
from typing import Any, Dict, Optional

# Windows groups windows, toasts and jump lists by this string. Reverse domain
# style is the convention. Changing it later orphans pinned taskbar entries, so
# it is treated as fixed.
APP_USER_MODEL_ID = "InoxHydra.LinkedInStudio"

APP_DISPLAY_NAME = "Inox Hydra"
STARTUP_SHORTCUT_NAME = "Inox Hydra.lnk"
# What the Startup shortcut was called before the product had one name. Still
# recognised, so an autostart switched on by an older version reads as on and
# can be switched off, and is replaced when switched on again.
LEGACY_STARTUP_SHORTCUT_NAMES = ("LinkedIn Studio.lnk",)

# The mutex name. The Local prefix scopes it to the logon session, which is
# what we want: two different users on one machine each get their own studio.
SINGLE_INSTANCE_MUTEX = "Local\\InoxHydra.LinkedInStudio.SingleInstance"

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _install_roots():
    """
    Directories that could hold the icon and the launcher, nearest first.

    Two layouts exist and they nest differently. A source checkout puts the
    studio package at <root>/studio, so the root is two levels up from here.
    The portable build puts it at <root>/app/studio, which is three, with the
    launcher sitting at the outer root beside the runtime. Rather than
    encoding which build this is, both are checked and the first hit wins.
    """
    roots = [_REPO_ROOT, os.path.abspath(os.path.join(_REPO_ROOT, ".."))]
    seen = []
    for root in roots:
        if root not in seen:
            seen.append(root)
    return seen


def _find_asset(*relative_parts) -> Optional[str]:
    for root in _install_roots():
        candidate = os.path.join(root, *relative_parts)
        if os.path.exists(candidate):
            return candidate
    return None


def is_windows() -> bool:
    return sys.platform == "win32"


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


MACOS_LAUNCH_AGENT_LABEL = "com.inoxhydra.linkedinstudio"
MACOS_LAUNCH_AGENT_FILE = f"{MACOS_LAUNCH_AGENT_LABEL}.plist"
LINUX_AUTOSTART_FILE = "inox-hydra.desktop"


def get_app_icon_path() -> str:
    """
    The one .ico every surface points at.

    Returns the source checkout path when nothing is found, so callers can
    report a definite location in a diagnostic rather than an empty string.
    """
    found = _find_asset("assets", "inox_hydra.ico")
    return found or os.path.join(_REPO_ROOT, "assets", "inox_hydra.ico")


def set_app_user_model_id(app_id: str = APP_USER_MODEL_ID) -> bool:
    """
    Tells Windows this process is its own application.

    Must run before the process creates a window, otherwise the window is
    already associated with the inherited identity. Returns whether it took.
    """
    if not is_windows():
        return False
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        return True
    except Exception:
        return False


def acquire_single_instance(name: str = SINGLE_INSTANCE_MUTEX):
    """
    Claims the single instance mutex.

    Returns the handle when this process is the first, or None when another
    instance already holds it. The handle is returned rather than discarded
    because the mutex lives exactly as long as it is held, and a local variable
    going out of scope would release it immediately.
    """
    if not is_windows():
        return None
    try:
        import ctypes

        ERROR_ALREADY_EXISTS = 183
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            return None
        if ctypes.GetLastError() == ERROR_ALREADY_EXISTS:
            return None
        return handle
    except Exception:
        return None


def get_startup_dir() -> str:
    """
    Returns the platform-specific autostart directory for the current user.
    Windows: %APPDATA%/Microsoft/Windows/Start Menu/Programs/Startup
    macOS: ~/Library/LaunchAgents
    Linux: ~/.config/autostart (or $XDG_CONFIG_HOME/autostart)
    """
    if is_windows():
        appdata = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
        return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
    if is_macos():
        return os.path.expanduser("~/Library/LaunchAgents")
    config_home = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(config_home, "autostart")


def get_startup_shortcut_path() -> str:
    if is_windows():
        return os.path.join(get_startup_dir(), STARTUP_SHORTCUT_NAME)
    if is_macos():
        return os.path.join(get_startup_dir(), MACOS_LAUNCH_AGENT_FILE)
    return os.path.join(get_startup_dir(), LINUX_AUTOSTART_FILE)


def _legacy_startup_shortcuts():
    if not is_windows():
        return []
    return [os.path.join(get_startup_dir(), name) for name in LEGACY_STARTUP_SHORTCUT_NAMES]


def is_autostart_enabled() -> bool:
    for path in [get_startup_shortcut_path(), *_legacy_startup_shortcuts()]:
        try:
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                return True
        except OSError:
            continue
    return False


def _launcher_target() -> Optional[str]:
    """
    What the Startup shortcut should point at.

    The portable build ships InoxHydra.bat or InoxHydra.sh next to the runtime.
    A source checkout has launch_studio.bat or launch_studio.sh. Whichever exists
    is the thing that knows how to start this installation, so autostart points
    at it rather than reconstructing a command line that would drift from it.
    """
    if is_windows():
        candidates = ["InoxHydra.bat", "launch_studio.bat"]
    else:
        candidates = [
            "Inox Hydra",
            "LinkedIn Studio",  # the desktop shell's name before 2.6
            "InoxHydra",
            "InoxHydra.sh",
            "launch_studio.sh",
            "launch_studio.py",
            "launch_studio.bat",
        ]

    for candidate in candidates:
        found = _find_asset(candidate)
        if found and os.path.isfile(found):
            return found

    # No launcher: say so, on every platform. Off Windows this used to return
    # the bare interpreter, so an installed copy reported autostart enabled
    # with an entry that ran python with no arguments and started nothing.
    return None


def desktop_exec_arg(arg: str) -> str:
    """
    One argument of a desktop entry's Exec line, quoted as the spec requires.

    Unquoted, a path with a space is split into several arguments, so an
    install under "My Apps", or the desktop shell's own "Inox Hydra" binary,
    produced an entry that started nothing while Settings reported it on.
    Inside double quotes, ", `, $ and \\ take a backslash; then the value as a
    whole escapes each backslash again, and % is doubled so it is not read as
    a field code.
    """
    quoted = '"' + "".join("\\" + ch if ch in '"`$\\' else ch for ch in arg) + '"'
    return quoted.replace("\\", "\\\\").replace("%", "%%")


def enable_autostart() -> Dict[str, Any]:
    """
    Enables automatic start on user login.
    Windows: Creates a Startup folder shortcut (.lnk) via PowerShell.
    macOS: Creates a LaunchAgent property list (.plist) in ~/Library/LaunchAgents.
    Linux: Creates an XDG autostart desktop entry (.desktop) in ~/.config/autostart.

    Reports the state achieved on disk rather than what was requested.
    """
    target = _launcher_target()
    if not target:
        return {"enabled": False, "reason": "no launcher script found next to the application"}

    startup_dir = get_startup_dir()
    try:
        os.makedirs(startup_dir, exist_ok=True)
    except OSError as err:
        return {"enabled": False, "reason": f"cannot reach the autostart directory: {err}"}

    shortcut = get_startup_shortcut_path()

    if is_windows():
        icon = get_app_icon_path()

        def ps_quote(value):
            return str(value).replace("'", "''")

        ps_cmd = (
            f"$w = New-Object -ComObject WScript.Shell; "
            f"$s = $w.CreateShortcut('{ps_quote(shortcut)}'); "
            f"$s.TargetPath = '{ps_quote(target)}'; "
            f"$s.WorkingDirectory = '{ps_quote(os.path.dirname(target))}'; "
            f"$s.WindowStyle = 7; "
            f"$s.Description = '{ps_quote(APP_DISPLAY_NAME)} background engine'; "
        )
        if os.path.isfile(icon):
            ps_cmd += f"$s.IconLocation = '{ps_quote(icon)},0'; "
        ps_cmd += "$s.Save()"

        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=15,
            )
        except Exception as err:
            return {"enabled": False, "reason": f"shortcut creation failed: {err}"}

        if result.returncode != 0 and not os.path.isfile(shortcut):
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            return {
                "enabled": False,
                "reason": detail[0] if detail else "PowerShell refused the shortcut command",
            }

        if os.path.isfile(shortcut):
            for legacy in _legacy_startup_shortcuts():
                try:
                    os.remove(legacy)
                except OSError:
                    pass
            return {"enabled": True, "shortcut_path": shortcut, "target": target}
        return {"enabled": False, "reason": "the shortcut was not created"}

    if is_macos():
        import plistlib

        prog_args = [target] if not target.endswith(".py") else [sys.executable, target]
        plist_content = {
            "Label": MACOS_LAUNCH_AGENT_LABEL,
            "ProgramArguments": prog_args,
            "RunAtLoad": True,
            "WorkingDirectory": os.path.dirname(target) if target else os.path.expanduser("~"),
        }
        try:
            with open(shortcut, "wb") as f:
                plistlib.dump(plist_content, f)
        except OSError as err:
            try:
                if os.path.exists(shortcut):
                    os.remove(shortcut)
            except OSError:
                pass
            return {"enabled": False, "reason": f"cannot write LaunchAgent plist: {err}"}

        if os.path.isfile(shortcut):
            return {"enabled": True, "shortcut_path": shortcut, "target": target}
        return {"enabled": False, "reason": "the LaunchAgent plist was not created"}

    if is_linux():
        argv = [target] if not target.endswith(".py") else [sys.executable, target]
        exec_line = " ".join(desktop_exec_arg(arg) for arg in argv)
        icon = get_app_icon_path()
        desktop_entry = "\n".join([
            "[Desktop Entry]",
            "Type=Application",
            "Version=1.0",
            f"Name={APP_DISPLAY_NAME}",
            "Comment=Local creator engine for LinkedIn",
            f"Exec={exec_line}",
            f"Icon={icon}",
            "Terminal=false",
            "StartupNotify=false",
            # Registered categories only: desktop-file-validate rejects others.
            "Categories=Office;",
            "",
        ])
        try:
            with open(shortcut, "w", encoding="utf-8", newline="\n") as f:
                f.write(desktop_entry)
        except OSError as err:
            try:
                if os.path.exists(shortcut):
                    os.remove(shortcut)
            except OSError:
                pass
            return {"enabled": False, "reason": f"cannot write autostart desktop file: {err}"}

        if os.path.isfile(shortcut):
            return {"enabled": True, "shortcut_path": shortcut, "target": target}
        return {"enabled": False, "reason": "the autostart desktop entry was not created"}

    return {"enabled": False, "reason": f"autostart is not supported on {sys.platform}"}


def disable_autostart() -> Dict[str, Any]:
    """
    Removes the autostart entry (shortcut, plist, or desktop file).
    Succeeds when there was nothing to remove, and reports achieved state.
    """
    present = [p for p in [get_startup_shortcut_path(), *_legacy_startup_shortcuts()] if os.path.isfile(p)]
    if not present:
        return {"enabled": False, "removed": False}
    try:
        for shortcut in present:
            os.remove(shortcut)
        still_present = any(os.path.isfile(p) for p in present)
        return {"enabled": still_present, "removed": not still_present}
    except OSError as err:
        return {"enabled": True, "removed": False, "reason": str(err)}


def describe() -> Dict[str, Any]:
    """
    What the Settings screen needs to render the desktop integration section
    truthfully, including the reasons a control is unavailable.
    """
    icon = get_app_icon_path()
    launcher = _launcher_target()
    supported = is_windows() or is_macos() or is_linux()
    return {
        "platform": sys.platform,
        "supported": supported,
        "app_id": APP_USER_MODEL_ID,
        "app_name": APP_DISPLAY_NAME,
        "icon_path": icon,
        "icon_present": os.path.isfile(icon),
        "launcher": launcher,
        "autostart_enabled": is_autostart_enabled(),
        "autostart_available": bool(launcher) and supported,
        "startup_shortcut_path": get_startup_shortcut_path(),
    }


# ---------------------------------------------------------------------------
# Starting the studio: what the portable launchers run
# ---------------------------------------------------------------------------
#
# InoxHydra.bat and InoxHydra.sh used to decide everything in batch and shell:
# any program answering on port 8000 counted as "Already running", and a fixed
# four second wait counted as started. So another app on 8000 was opened in
# place of the studio, and an engine that died at once still printed "Ready."
# and opened a page that could not connect, with no log anywhere.
#
# Both launchers now run `python -m studio.backend.desktop launch`, which holds
# one readiness rule, the desktop shell's: the studio is up when
# /api/v1/health answers with this application's own name.
#
# The port. The browser extension talks to 8000 and nothing else, so 8000 is
# always tried first. When another program holds it, the studio starts on the
# next free port of a small range, and the launcher says plainly that capture
# through the extension needs 8000. Moving the port for good waits for the
# store extension, which can probe the range (phase 3).

STUDIO_HOST = "127.0.0.1"
EXTENSION_PORT = 8000
PORT_RANGE_SIZE = 10
READY_TIMEOUT_SECONDS = 45
ENGINE_WINDOW_TITLE = "Inox Hydra Engine"
ENGINE_LOG_MAX_BYTES = 2 * 1024 * 1024

# Exit codes the launchers read. Anything but 0 keeps the Windows window open
# so its message can be read.
LAUNCH_READY = 0
LAUNCH_FAILED = 1
LAUNCH_READY_ELSEWHERE = 3

# What uvicorn's bind failure says, on Linux, macOS and Windows (10048 in use,
# 10013 a port Windows has reserved).
_PORT_IN_USE_MARKERS = ("address already in use", "only one usage of each socket address",
                        "10048", "10013", "forbidden by its access permissions")


def preferred_port() -> int:
    """8000, unless INOX_HYDRA_PORT names another port to try first."""
    raw = os.environ.get("INOX_HYDRA_PORT", "").strip()
    try:
        port = int(raw)
    except ValueError:
        return EXTENSION_PORT
    return port if 1024 <= port <= 65535 - PORT_RANGE_SIZE else EXTENSION_PORT


def candidate_ports(first: Optional[int] = None):
    first = preferred_port() if first is None else first
    return list(range(first, first + PORT_RANGE_SIZE))


def studio_url(port: int) -> str:
    return f"http://{STUDIO_HOST}:{port}"


def _can_bind(port: int) -> bool:
    """
    Whether the engine could listen here: bound exactly as uvicorn binds.

    On Linux and macOS that is with SO_REUSEADDR (asyncio's default there),
    which still refuses a port another socket is listening on but not one
    whose only traces are TIME_WAIT connections. A plain bind refused those,
    so stopping the studio and starting it again within a minute moved it off
    8000 with "in use by another program". On Windows asyncio binds plainly,
    so this does too: SO_REUSEADDR there would admit a second listener, and
    SO_EXCLUSIVEADDRUSE refuses the lingering connections the same way.
    """
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if not is_windows():
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((STUDIO_HOST, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def probe_port(port: int, timeout: float = 1.5):
    """
    What is on a port: ("studio", version), ("free", None) or ("taken", None).

    "studio" means /api/v1/health answered 200 with this application's name,
    the same test the desktop shell applies. Anything else that answers, or a
    port that refuses a connection and also cannot be bound (one Windows has
    reserved, say), is "taken".
    """
    import http.client
    import json

    connection = http.client.HTTPConnection(STUDIO_HOST, port, timeout=timeout)
    try:
        connection.request("GET", "/api/v1/health", headers={"Connection": "close"})
        response = connection.getresponse()
        body = response.read(8192)
    except ConnectionRefusedError:
        return ("free", None) if _can_bind(port) else ("taken", None)
    except (OSError, http.client.HTTPException):
        return ("taken", None)
    finally:
        connection.close()

    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
    except ValueError:
        payload = None
    if response.status == 200 and isinstance(payload, dict) and payload.get("app") == "inox-hydra":
        return ("studio", str(payload.get("version") or ""))
    return ("taken", None)


def engine_log_path() -> str:
    """logs/engine.log in the app home: the file the desktop shell writes and the diagnostics bundle reads."""
    try:
        from . import paths
    except ImportError:
        import paths
    return os.path.join(paths.get_logs_dir(), "engine.log")


def _log_tail(path: str, lines: int = 12) -> str:
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - 16384))
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    marker = text.rfind("--- engine launch at")
    return "\n".join(text[marker if marker != -1 else 0:].strip().splitlines()[-lines:])


def _engine_command(port: int):
    # -s: the user's own site-packages never shadows what the studio ships.
    return [sys.executable, "-s", "-m", "studio.backend.desktop", "serve", "--port", str(port)]


def spawn_engine(port: int):
    """
    Starts the engine in a process that outlives this launcher.

    On Windows it gets a minimised console window of its own, titled "Inox
    Hydra Engine", because closing that window is how a portable copy is
    stopped. Elsewhere it runs detached in a new session.
    """
    env = {k: v for k, v in os.environ.items() if k != "INOX_DEV_MODE"}
    if is_windows():
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 7  # SW_SHOWMINNOACTIVE: minimised, focus stays here
        return subprocess.Popen(_engine_command(port), cwd=_REPO_ROOT, env=env, startupinfo=startup,
                                creationflags=subprocess.CREATE_NEW_CONSOLE)
    return subprocess.Popen(_engine_command(port), cwd=_REPO_ROOT, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def wait_for_studio(port: int, process, timeout: float = READY_TIMEOUT_SECONDS) -> str:
    """"ready", "exited" (the engine died), "taken" (someone else answers) or "timeout"."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            return "exited"
        state, _ = probe_port(port, timeout=1.0)
        if state == "studio":
            return "ready"
        time.sleep(0.25)
    if process is not None and process.poll() is not None:
        return "exited"
    return "timeout"


def open_studio_window(url: str) -> Optional[str]:
    """
    Opens the studio the way the launchers always have: a Chrome app window
    when Chrome is in its usual place, otherwise the default browser. Returns
    what was used, or None when nothing could be opened.
    """
    import shutil

    def detached(argv):
        kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if not is_windows():
            kwargs["start_new_session"] = True
        subprocess.Popen(argv, **kwargs)

    app_args = [f"--app={url}", "--window-size=1440,920"]
    if is_windows():
        for chrome in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                       r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
            if os.path.isfile(chrome):
                detached([chrome, *app_args])
                return "a Chrome app window"
        try:
            os.startfile(url)
            return "your default browser"
        except OSError:
            return None

    candidates = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                  "brave-browser", "brave"]
    for name in candidates:
        found = shutil.which(name)
        if found:
            detached([found, *app_args])
            return f"an app window ({name})"
    if is_macos():
        for app in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"):
            if os.path.isfile(app):
                detached([app, *app_args])
                return "an app window"
    for opener in ("xdg-open", "open"):
        found = shutil.which(opener)
        if found:
            detached([found, url])
            return "your default browser"
    return None


def _say(message: str = "") -> None:
    print(message, flush=True)


def _port_notice(port: int, states) -> None:
    """Says so whenever the studio is not on the one port the extension talks to."""
    if port == EXTENSION_PORT:
        return
    held = states.get(EXTENSION_PORT) == "taken"
    if held:
        _say(f"[!] Port {EXTENSION_PORT} is in use by another program, so the studio is on port {port} this time.")
    else:
        _say(f"[!] The studio is on port {port}, not {EXTENSION_PORT}.")
    _say(f"    The browser extension only connects on port {EXTENSION_PORT}, so it cannot capture leads or")
    _say("    analytics until the studio runs there.")
    if held:
        _say(f"    To fix it, close the program using port {EXTENSION_PORT}, stop the studio, and start it again.")
    elif states.get(EXTENSION_PORT) == "free":
        _say(f"    Port {EXTENSION_PORT} is free now: stop the studio and start it again to move it there.")


def _opened(port: int, opener) -> None:
    url = studio_url(port)
    used = opener(url)
    if used:
        _say(f"[*] Opened {url} in {used}.")
    else:
        _say(f"[*] Open {url} in your browser.")


def launch(ports=None, opener=None, spawn=None, timeout: float = READY_TIMEOUT_SECONDS) -> int:
    """
    Starts the studio, or finds the one already running, and opens it.

    Returns LAUNCH_READY, LAUNCH_READY_ELSEWHERE (running, on a port other
    than the first one tried) or LAUNCH_FAILED, after saying why.
    """
    ports = list(ports) if ports else candidate_ports()
    opener = opener or open_studio_window
    spawn = spawn or spawn_engine

    # A studio already running anywhere in the range is the one to open. A
    # second engine on the same data would run a second scheduler.
    states = {}
    for port in ports:
        state, version = probe_port(port)
        states[port] = state
        if state == "studio":
            _say(f"[*] Inox Hydra {version} is already running on {studio_url(port)}.".replace("  ", " "))
            _port_notice(port, states)
            _opened(port, opener)
            return LAUNCH_READY if port == ports[0] else LAUNCH_READY_ELSEWHERE

    log = engine_log_path()
    taken = []
    for port in ports:
        if states[port] != "free":
            taken.append(port)
            _say(f"[!] Port {port} is in use by another program, not Inox Hydra.")
            continue

        _say(f"[*] Starting the studio engine on port {port}...")
        process = spawn(port)
        outcome = wait_for_studio(port, process, timeout)
        if outcome == "ready":
            _say(f"[*] The studio is ready at {studio_url(port)}.")
            for held in taken:
                states[held] = "taken"
            _port_notice(port, states)
            _opened(port, opener)
            if is_windows():
                _say(f'[*] To stop the studio, close the minimised "{ENGINE_WINDOW_TITLE}" window.')
            _say(f"    Engine log: {log}")
            return LAUNCH_READY if port == ports[0] else LAUNCH_READY_ELSEWHERE

        tail = _log_tail(log)
        if outcome == "exited" and any(marker in tail.lower() for marker in _PORT_IN_USE_MARKERS):
            # Taken between the check and the start. Try the next one.
            taken.append(port)
            _say(f"[!] Port {port} was taken by another program as the engine started.")
            continue
        if outcome == "taken":
            _say(f"[!] Another program answered on port {port} while the engine was starting.")
        elif outcome == "exited":
            _say("[!] The studio engine stopped while it was starting. No window was opened.")
        else:
            _say(f"[!] The studio engine did not answer within {int(timeout)} seconds. No window was opened.")
            _say(f"    It may still be starting: wait a minute, then open {studio_url(port)}.")
        if tail:
            _say("    Last lines of its log:")
            for line in tail.splitlines():
                _say("      " + line)
        _say(f"    Full log: {log}")
        return LAUNCH_FAILED

    _say(f"[!] Ports {ports[0]} to {ports[-1]} are all in use by other programs, so the studio was not started.")
    _say("    Close one of them, or restart this computer, then start Inox Hydra again.")
    return LAUNCH_FAILED


class _Tee:
    """Writes to the console, when there is one, and to the engine log."""

    def __init__(self, console, log):
        self._console = console
        self._log = log

    def write(self, text):
        for stream in (self._console, self._log):
            if stream is None:
                continue
            try:
                stream.write(text)
                stream.flush()
            except (OSError, ValueError):
                pass
        return len(text)

    def flush(self):
        pass

    def isatty(self):
        return False


def serve(port: int) -> int:
    """
    The engine itself: uvicorn on loopback, its output in the console and in
    logs/engine.log. On Windows this is the "Inox Hydra Engine" window.
    """
    import time

    if is_windows():
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleTitleW(ENGINE_WINDOW_TITLE)
        except Exception:
            pass
    os.environ.pop("INOX_DEV_MODE", None)

    log_path = engine_log_path()
    try:
        if os.path.getsize(log_path) > ENGINE_LOG_MAX_BYTES:
            os.remove(log_path)
    except OSError:
        pass
    try:
        log = open(log_path, "a", encoding="utf-8", errors="replace")
        log.write(f"\n--- engine launch at unix time {int(time.time())} ---\n")
    except OSError:
        log = None
    sys.stdout = _Tee(sys.stdout, log)
    sys.stderr = _Tee(sys.stderr, log)

    print(f"Inox Hydra is starting at {studio_url(port)}")
    if is_windows():
        print("Close this window to stop the studio.")
    print(f"Log: {log_path}")
    print()

    import uvicorn

    uvicorn.run("studio.backend.app:app", host=STUDIO_HOST, port=port, log_level="info")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv[0] if argv else "launch"
    if command == "serve":
        port = int(argv[argv.index("--port") + 1]) if "--port" in argv else preferred_port()
        return serve(port)
    if command == "launch":
        return launch()
    print("usage: python -m studio.backend.desktop [launch | serve --port N]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
