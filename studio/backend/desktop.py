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

APP_DISPLAY_NAME = "LinkedIn Studio"
STARTUP_SHORTCUT_NAME = "LinkedIn Studio.lnk"

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


def is_autostart_enabled() -> bool:
    path = get_startup_shortcut_path()
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
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
            "LinkedIn Studio",
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

    if not is_windows():
        return sys.executable

    return None


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
        exec_line = target if not target.endswith(".py") else f"{sys.executable} {target}"
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
            "Categories=Office;Productivity;",
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
    shortcut = get_startup_shortcut_path()
    if not os.path.isfile(shortcut):
        return {"enabled": False, "removed": False}
    try:
        os.remove(shortcut)
        still_present = os.path.isfile(shortcut)
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
