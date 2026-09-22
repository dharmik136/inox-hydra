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
        # A HANDLE is pointer sized. ctypes defaults restype to c_int, which
        # would clip the top half of one on 64 bit Windows.
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
        # Unable to tell. Better to run than to refuse to start.
        return None


def get_startup_dir() -> str:
    """The per user Startup folder, which is where a shortcut has to land."""
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def get_startup_shortcut_path() -> str:
    return os.path.join(get_startup_dir(), STARTUP_SHORTCUT_NAME)


def is_autostart_enabled() -> bool:
    return os.path.isfile(get_startup_shortcut_path())


def _launcher_target() -> Optional[str]:
    """
    What the Startup shortcut should point at.

    The portable build ships InoxHydra.bat next to the runtime. A source
    checkout has launch_studio.bat. Whichever exists is the thing that knows
    how to start this installation, so autostart points at it rather than
    reconstructing a command line that would drift from it.
    """
    for candidate in ("InoxHydra.bat", "launch_studio.bat"):
        found = _find_asset(candidate)
        if found and os.path.isfile(found):
            return found
    return None


def enable_autostart() -> Dict[str, Any]:
    """
    Creates the Startup shortcut.

    Uses the same WScript.Shell approach as the desktop shortcuts in
    browser_launcher, because writing a .lnk by hand means implementing a
    binary shell link format for no benefit.
    """
    if not is_windows():
        return {"enabled": False, "reason": "autostart is implemented for Windows only"}

    target = _launcher_target()
    if not target:
        return {"enabled": False, "reason": "no launcher script found next to the application"}

    startup_dir = get_startup_dir()
    try:
        os.makedirs(startup_dir, exist_ok=True)
    except OSError as err:
        return {"enabled": False, "reason": f"cannot reach the Startup folder: {err}"}

    shortcut = get_startup_shortcut_path()
    icon = get_app_icon_path()

    # Minimised, because the point of autostart is that the daemon is ready in
    # the tray, not that a console window greets the user at every login.
    # PowerShell escapes a single quote by doubling it.
    #
    # I fixed this exact pattern in browser_launcher, verified it, and missed
    # it here. A Windows account name may legally contain an apostrophe, and
    # every one of these paths runs through the user profile, so an account
    # named O'Brien ended the quoted string early and the command failed to
    # parse. Not remotely reachable, but a silent failure for those users.
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

    # The existence check below is the real verdict, but a non zero exit says
    # WHY, which is the difference between a usable message and "it did not
    # work".
    if result.returncode != 0 and not os.path.isfile(shortcut):
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        return {
            "enabled": False,
            "reason": detail[0] if detail else "PowerShell refused the shortcut command",
        }

    if os.path.isfile(shortcut):
        return {"enabled": True, "shortcut_path": shortcut, "target": target}
    return {"enabled": False, "reason": "the shortcut was not created"}


def disable_autostart() -> Dict[str, Any]:
    """Removes the Startup shortcut. Succeeds when there was nothing to remove."""
    shortcut = get_startup_shortcut_path()
    if not os.path.isfile(shortcut):
        return {"enabled": False, "removed": False}
    try:
        os.remove(shortcut)
        return {"enabled": False, "removed": True}
    except OSError as err:
        return {"enabled": True, "removed": False, "reason": str(err)}


def describe() -> Dict[str, Any]:
    """
    What the Settings screen needs to render the desktop integration section
    truthfully, including the reasons a control is unavailable.
    """
    icon = get_app_icon_path()
    launcher = _launcher_target()
    return {
        "platform": sys.platform,
        "supported": is_windows(),
        "app_id": APP_USER_MODEL_ID,
        "app_name": APP_DISPLAY_NAME,
        "icon_path": icon,
        "icon_present": os.path.isfile(icon),
        "launcher": launcher,
        "autostart_enabled": is_autostart_enabled(),
        "autostart_available": bool(launcher) and is_windows(),
        "startup_shortcut_path": get_startup_shortcut_path(),
    }
