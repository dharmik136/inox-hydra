"""
LinkedIn Studio Browser Bridge & Extension Auto-Loader
======================================================
Automates the detection, shortcut creation, and 1-click launching
of Chromium browsers (Google Chrome, Microsoft Edge, Brave, Opera, Vivaldi)
with the LinkedIn Studio Bridge extension pre-loaded.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and user-facing messages.
- Safe detached subprocess execution (non-blocking).
"""

import os
import sys
import subprocess
import shutil
from typing import Dict, List, Optional, Any
from pathlib import Path

# Paths
BACKEND_DIR = Path(__file__).resolve().parent
STUDIO_DIR = BACKEND_DIR.parent
EXTENSION_DIR = STUDIO_DIR / "extension"

BROWSER_CANDIDATES = [
    {
        "id": "chrome",
        "name": "Google Chrome",
        "reg_key": r"Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
        "paths": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
    },
    {
        "id": "edge",
        "name": "Microsoft Edge",
        "reg_key": r"Software\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
        "paths": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        ]
    },
    {
        "id": "brave",
        "name": "Brave Browser",
        "reg_key": r"Software\Microsoft\Windows\CurrentVersion\App Paths\brave.exe",
        "paths": [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        ]
    },
    {
        "id": "opera",
        "name": "Opera",
        "reg_key": r"Software\Microsoft\Windows\CurrentVersion\App Paths\opera.exe",
        "paths": [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\opera.exe"),
            r"C:\Program Files\Opera\opera.exe",
        ]
    },
    {
        "id": "vivaldi",
        "name": "Vivaldi",
        "reg_key": r"Software\Microsoft\Windows\CurrentVersion\App Paths\vivaldi.exe",
        "paths": [
            os.path.expandvars(r"%LOCALAPPDATA%\Vivaldi\Application\vivaldi.exe"),
            r"C:\Program Files\Vivaldi\Application\vivaldi.exe",
        ]
    },
]


def detect_installed_browsers() -> Dict[str, Dict[str, str]]:
    """
    Scans the local Windows machine for installed Chromium browsers.
    Returns a dictionary of browser ID to metadata (name, path, is_available).
    """
    results = {}

    for candidate in BROWSER_CANDIDATES:
        browser_id = candidate["id"]
        browser_name = candidate["name"]
        found_path = None

        # Check standard disk paths first
        for p in candidate["paths"]:
            if os.path.exists(p):
                found_path = p
                break

        # Check Windows Registry if not found on disk
        if not found_path and sys.platform == "win32":
            try:
                import winreg
                for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                    try:
                        with winreg.OpenKey(root, candidate["reg_key"]) as key:
                            val, _ = winreg.QueryValueEx(key, "")
                            if val and os.path.exists(val):
                                found_path = val
                                break
                    except OSError:
                        pass
                    if found_path:
                        break
            except Exception:
                pass

        if found_path:
            results[browser_id] = {
                "id": browser_id,
                "name": browser_name,
                "path": found_path,
                "is_available": True
            }

    return results


def get_extension_dir() -> str:
    """Returns absolute path to the unpacked extension folder."""
    return str(EXTENSION_DIR.resolve())


def get_desktop_dir() -> str:
    """
    Resolves the actual user Desktop directory on Windows,
    handling OneDrive folder redirection and User Shell Folders.
    """
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            ) as key:
                val, _ = winreg.QueryValueEx(key, "Desktop")
                resolved = os.path.expandvars(val)
                if os.path.exists(resolved):
                    return resolved
        except Exception:
            pass

    for candidate in [
        os.path.expandvars(r"%USERPROFILE%\OneDrive\Desktop"),
        os.path.expandvars(r"%USERPROFILE%\Desktop"),
        str(Path.home() / "Desktop")
    ]:
        if os.path.exists(candidate):
            return candidate

    return os.environ.get("USERPROFILE", str(Path.home()))


def create_desktop_shortcuts(
    browsers: Optional[Dict[str, Dict[str, str]]] = None,
    target_url: str = "https://www.linkedin.com/feed/"
) -> List[Dict[str, Any]]:
    """
    Creates Windows Desktop shortcuts (.lnk) for all detected browsers,
    configured with --load-extension so the user never has to manually load it.
    """
    if browsers is None:
        browsers = detect_installed_browsers()

    desktop_dir = get_desktop_dir()
    created_shortcuts = []
    ext_path = get_extension_dir()

    for b_id, b_info in browsers.items():
        b_name = b_info["name"]
        b_path = b_info["path"]
        shortcut_name = f"LinkedIn Studio ({b_name}).lnk"
        shortcut_dest = os.path.join(desktop_dir, shortcut_name)

        # Format single-line PowerShell command
        ps_cmd = (
            f"$w = New-Object -ComObject WScript.Shell; "
            f"$s = $w.CreateShortcut('{shortcut_dest}'); "
            f"$s.TargetPath = '{b_path}'; "
            f"$s.Arguments = '--load-extension=\"\"{ext_path}\"\" {target_url}'; "
            f"$s.IconLocation = '{b_path},0'; "
            f"$s.Description = 'Launch {b_name} with LinkedIn Studio Bridge'; "
            f"$s.WorkingDirectory = '{os.path.dirname(b_path)}'; "
            f"$s.Save()"
        )
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=10
            )
            if os.path.exists(shortcut_dest):
                created_shortcuts.append({
                    "browser_id": b_id,
                    "browser_name": b_name,
                    "shortcut_path": shortcut_dest,
                    "status": "created"
                })
            else:
                created_shortcuts.append({
                    "browser_id": b_id,
                    "browser_name": b_name,
                    "error": res.stderr or res.stdout or "File not created",
                    "status": "failed"
                })
        except Exception as e:
            created_shortcuts.append({
                "browser_id": b_id,
                "browser_name": b_name,
                "error": str(e),
                "status": "failed"
            })

    return created_shortcuts


DEFAULT_TARGET_URL = "https://www.linkedin.com/feed/"

# Hosts this launcher will open. Everything else, including anything that could
# be read as a Chromium switch, falls back to the feed.
ALLOWED_TARGET_HOSTS = ("www.linkedin.com", "linkedin.com")


def _validated_target(target_url):
    """
    Returns a URL that is safe to hand to a browser as argv.

    Falls back to the LinkedIn feed rather than raising, because this is the
    last step of a user action and refusing outright would present a creator
    with an error for something they did not type. Anything rejected here was
    not a URL a person entered, since nothing in the interface sends one.
    """
    from urllib.parse import urlsplit

    candidate = (target_url or "").strip()
    if not candidate or candidate.startswith("-"):
        return DEFAULT_TARGET_URL

    try:
        parts = urlsplit(candidate)
    except ValueError:
        return DEFAULT_TARGET_URL

    if parts.scheme != "https":
        return DEFAULT_TARGET_URL
    if parts.hostname not in ALLOWED_TARGET_HOSTS:
        return DEFAULT_TARGET_URL

    return candidate


def launch_browser_with_extension(
    browser_id: str = "auto",
    target_url: str = "https://www.linkedin.com/feed/"
) -> Dict[str, Any]:
    """
    Spawns the target browser as an independent process with --load-extension.
    If browser_id is 'auto', picks Chrome first, then Edge, then Brave.
    """
    browsers = detect_installed_browsers()
    if not browsers:
        return {
            "status": "error",
            "message": "No supported Chromium browser (Chrome, Edge, Brave, Opera) detected on this PC."
        }

    selected = None
    if browser_id != "auto" and browser_id in browsers:
        selected = browsers[browser_id]
    else:
        # Preference order: Chrome -> Edge -> Brave -> others
        for pref in ["chrome", "edge", "brave", "opera", "vivaldi"]:
            if pref in browsers:
                selected = browsers[pref]
                break

    if not selected:
        selected = next(iter(browsers.values()))

    ext_path = get_extension_dir()
    exe_path = selected["path"]

    # Chromium reads any argv element beginning with "-" as a switch, wherever
    # it sits in the list. So a caller supplied URL is not data here, it is a
    # command line, and a value like "--gpu-launcher=cmd.exe /c whatever" makes
    # the browser execute that program. There is no shell involved and no
    # quoting that would help: the browser itself is the injection point.
    #
    # The allowlist is therefore on the value, not on its characters. This
    # launcher exists to open LinkedIn with the bridge extension loaded, so
    # that is the only thing it will open.
    safe_url = _validated_target(target_url)

    args = [
        exe_path,
        f'--load-extension={ext_path}',
        safe_url
    ]

    try:
        # Launch detached from current process group so it stays open
        if sys.platform == "win32":
            DETACHED_PROCESS = 0x00000008
            subprocess.Popen(
                args,
                creationflags=DETACHED_PROCESS,
                close_fds=True
            )
        else:
            subprocess.Popen(args, close_fds=True)

        return {
            "status": "success",
            "browser": selected["name"],
            "browser_path": exe_path,
            "target_url": target_url,
            "extension_path": ext_path,
            "message": f"Successfully launched {selected['name']} with LinkedIn Studio Bridge loaded."
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to launch browser: {str(e)}"
        }


def copy_extension_path_to_clipboard() -> Dict[str, Any]:
    """
    Copies the extension directory path to the Windows clipboard
    for users wishing to paste into the Load Unpacked file dialog.
    """
    ext_path = get_extension_dir()
    try:
        ps_script = f"Set-Clipboard -Value '{ext_path}'"
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], timeout=5)
        return {
            "status": "success",
            "extension_path": ext_path,
            "message": "Extension path copied to clipboard."
        }
    except Exception as e:
        return {
            "status": "error",
            "extension_path": ext_path,
            "message": f"Clipboard copy failed: {str(e)}"
        }
