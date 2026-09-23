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
import shlex
import subprocess
import shutil
from typing import Dict, List, Optional, Any
from pathlib import Path

# Paths
BACKEND_DIR = Path(__file__).resolve().parent
STUDIO_DIR = BACKEND_DIR.parent
EXTENSION_DIR = STUDIO_DIR / "extension"

# Where each browser lives, per platform.
#
# This table was Windows only, so detect_installed_browsers returned an empty
# dict on macOS and Linux and a creator there had no assisted way to open a
# browser with the extension loaded. The extension is how this product sees
# LinkedIn at all, so that was half the product missing rather than a cosmetic
# gap.
#
# Linux carries bare command names as well as absolute paths. Distributions
# disagree about where a browser lives, and snap and flatpak put it somewhere
# else again, so PATH is consulted through shutil.which too.
BROWSER_CANDIDATES = [
    {
        "id": "chrome",
        "name": "Google Chrome",
        "reg_key": r"Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
        "paths": {
            "win32": [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            ],
            "darwin": [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            ],
            "linux": [
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/opt/google/chrome/chrome",
            ],
        },
        "commands": ["google-chrome", "google-chrome-stable"],
    },
    {
        "id": "edge",
        "name": "Microsoft Edge",
        "reg_key": r"Software\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
        "paths": {
            "win32": [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
            ],
            "darwin": [
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            ],
            "linux": [
                "/usr/bin/microsoft-edge",
                "/usr/bin/microsoft-edge-stable",
                "/opt/microsoft/msedge/msedge",
            ],
        },
        "commands": ["microsoft-edge", "microsoft-edge-stable"],
    },
    {
        "id": "brave",
        "name": "Brave Browser",
        "reg_key": r"Software\Microsoft\Windows\CurrentVersion\App Paths\brave.exe",
        "paths": {
            "win32": [
                r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
            ],
            "darwin": [
                "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            ],
            "linux": [
                "/usr/bin/brave-browser",
                "/opt/brave.com/brave/brave-browser",
            ],
        },
        "commands": ["brave-browser", "brave"],
    },
    {
        "id": "opera",
        "name": "Opera",
        "reg_key": r"Software\Microsoft\Windows\CurrentVersion\App Paths\opera.exe",
        "paths": {
            "win32": [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\opera.exe"),
                r"C:\Program Files\Opera\opera.exe",
            ],
            "darwin": [
                "/Applications/Opera.app/Contents/MacOS/Opera",
            ],
            "linux": [
                "/usr/bin/opera",
            ],
        },
        "commands": ["opera"],
    },
    {
        "id": "vivaldi",
        "name": "Vivaldi",
        "reg_key": r"Software\Microsoft\Windows\CurrentVersion\App Paths\vivaldi.exe",
        "paths": {
            "win32": [
                os.path.expandvars(r"%LOCALAPPDATA%\Vivaldi\Application\vivaldi.exe"),
                r"C:\Program Files\Vivaldi\Application\vivaldi.exe",
            ],
            "darwin": [
                "/Applications/Vivaldi.app/Contents/MacOS/Vivaldi",
            ],
            "linux": [
                "/usr/bin/vivaldi",
                "/usr/bin/vivaldi-stable",
                "/opt/vivaldi/vivaldi",
            ],
        },
        "commands": ["vivaldi", "vivaldi-stable"],
    },
]


def _platform_key() -> str:
    """Which arm of the path table applies here."""
    if sys.platform == "win32":
        return "win32"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def _candidate_paths(candidate: Dict[str, Any]) -> List[str]:
    """
    The paths to try for this browser on this platform.

    Tolerates the older flat list shape, so a candidate defined elsewhere
    degrades to "no paths for this platform" rather than raising inside
    detection and taking the launcher down with it.
    """
    paths = candidate.get("paths")
    if isinstance(paths, dict):
        return list(paths.get(_platform_key(), []))
    if isinstance(paths, list):
        return list(paths)
    return []


def detect_installed_browsers() -> Dict[str, Dict[str, str]]:
    """
    Scans this machine for installed Chromium browsers.

    Returns a dictionary of browser ID to metadata (name, path, is_available).
    An empty dictionary means none were found, which is a normal answer on a
    server or a CI runner and not an error.
    """
    results = {}

    for candidate in BROWSER_CANDIDATES:
        browser_id = candidate["id"]
        browser_name = candidate["name"]
        found_path = None

        # Check standard disk paths first
        for p in _candidate_paths(candidate):
            if os.path.exists(p):
                found_path = p
                break

        # Then PATH, which is where a snap, a flatpak or a distribution that
        # disagrees with the table above will have put the executable. Skipped
        # on Windows, where the registry below is the better answer and a bare
        # name on PATH is not how these browsers are installed.
        if not found_path and sys.platform != "win32":
            for command in candidate.get("commands", []):
                resolved = shutil.which(command)
                if resolved:
                    found_path = resolved
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
    Resolves the user's Desktop directory.

    Windows needs the registry because OneDrive redirects the folder and the
    literal %USERPROFILE%\\Desktop stops existing. Linux needs xdg-user-dir
    because the folder is localised: a German desktop is ~/Schreibtisch, and
    writing a launcher to an English path there creates a directory nobody
    looks in. macOS has kept ~/Desktop unlocalised at the filesystem level,
    so the plain path is correct there.
    """
    if sys.platform == "darwin":
        return str(Path.home() / "Desktop")

    if sys.platform not in ("win32",):
        try:
            result = subprocess.run(
                ["xdg-user-dir", "DESKTOP"],
                capture_output=True, text=True, timeout=5,
            )
            resolved = (result.stdout or "").strip()
            # xdg-user-dir echoes $HOME when no desktop is configured, which
            # is a headless machine telling us there is nowhere to put this.
            if resolved and os.path.isdir(resolved) and resolved != str(Path.home()):
                return resolved
        except (subprocess.SubprocessError, OSError):
            pass
        fallback = Path.home() / "Desktop"
        return str(fallback) if fallback.is_dir() else str(Path.home())

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


def _posix_launcher(b_id, b_info, desktop_dir, ext_path, safe_url):
    """
    Writes one double clickable launcher on macOS or Linux.

    macOS gets a .command file, which Finder runs in Terminal, because a real
    .app bundle would have to be code signed to open without a Gatekeeper
    prompt and this is the smaller honest thing.

    Linux gets an XDG .desktop entry, which is what a desktop environment
    actually reads. It needs the executable bit and, on GNOME, the metadata
    trust flag, or it renders as an untrusted text file.

    Every interpolated value goes through shlex.quote. The extension path
    contains a space on a default install, and the Windows path already had
    to be fixed once for exactly that: an unquoted path split across two
    arguments and the browser started without the extension, which is the one
    thing the launcher exists to do.
    """
    name = b_info["name"]
    exe = b_info["path"]
    argument = "--load-extension=" + ext_path

    if sys.platform == "darwin":
        path = os.path.join(desktop_dir, f"LinkedIn Studio ({name}).command")
        body = (
            "#!/bin/sh\n"
            "# Opens " + name + " with the Inox Hydra bridge extension loaded.\n"
            "exec " + shlex.quote(exe) + " " + shlex.quote(argument)
            + " " + shlex.quote(safe_url) + "\n"
        )
    else:
        path = os.path.join(desktop_dir, f"inox-hydra-{b_id}.desktop")
        body = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Version=1.0\n"
            f"Name=LinkedIn Studio ({name})\n"
            "Comment=Launch with the Inox Hydra bridge extension loaded\n"
            # Exec is not a shell, so shlex.quote is the wrong tool: the spec
            # wants double quotes around a field containing spaces.
            f'Exec="{exe}" "{argument}" "{safe_url}"\n'
            "Terminal=false\n"
            "Categories=Network;WebBrowser;\n"
        )

    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)
    os.chmod(path, 0o755)

    if sys.platform != "darwin":
        # GNOME refuses to run a .desktop file it does not consider trusted,
        # and shows the raw text instead. Best effort: not every desktop
        # environment ships gio, and the launcher still works from a file
        # manager that does not enforce this.
        try:
            subprocess.run(
                ["gio", "set", path, "metadata::trusted", "true"],
                capture_output=True, timeout=5,
            )
        except (subprocess.SubprocessError, OSError):
            pass

    return path


def create_desktop_shortcuts(
    browsers: Optional[Dict[str, Dict[str, str]]] = None,
    target_url: str = "https://www.linkedin.com/feed/"
) -> List[Dict[str, Any]]:
    """
    Creates a desktop launcher per detected browser, configured with
    --load-extension so the user never has to load the extension by hand.

    A .lnk on Windows, a .command on macOS, an XDG .desktop entry on Linux.
    """
    if browsers is None:
        browsers = detect_installed_browsers()

    desktop_dir = get_desktop_dir()
    created_shortcuts = []
    ext_path = get_extension_dir()

    if sys.platform != "win32":
        safe_url = _validated_target(target_url)
        for b_id, b_info in browsers.items():
            try:
                path = _posix_launcher(b_id, b_info, desktop_dir, ext_path, safe_url)
                created_shortcuts.append({
                    "browser_id": b_id,
                    "browser_name": b_info["name"],
                    "shortcut_path": path,
                    "status": "created" if os.path.exists(path) else "failed",
                })
            except Exception as exc:
                created_shortcuts.append({
                    "browser_id": b_id,
                    "browser_name": b_info["name"],
                    "error": str(exc),
                    "status": "failed",
                })
        return created_shortcuts

    for b_id, b_info in browsers.items():
        b_name = b_info["name"]
        b_path = b_info["path"]
        shortcut_name = f"LinkedIn Studio ({b_name}).lnk"
        shortcut_dest = os.path.join(desktop_dir, shortcut_name)

        # PowerShell escapes a single quote by doubling it, not with "".
        #
        # The previous form emitted --load-extension=""C:\...\Linkedin
        # strategy\studio\extension"", where "" opens and immediately closes
        # a quoted section and leaves the path bare. On any install path
        # containing a space, Chrome received the path split across two
        # arguments and started without the extension, which is the one thing
        # the shortcut exists to do. The API launcher builds an argv list and
        # was always fine, so the two disagreed and only the shortcut failed.
        #
        # Doubling also protects an account name containing an apostrophe,
        # which is legal on Windows and otherwise ends the string early.
        def ps_quote(value):
            return str(value).replace("'", "''")

        safe_url = _validated_target(target_url)
        ps_cmd = (
            f"$w = New-Object -ComObject WScript.Shell; "
            f"$s = $w.CreateShortcut('{ps_quote(shortcut_dest)}'); "
            f"$s.TargetPath = '{ps_quote(b_path)}'; "
            f"$s.Arguments = '--load-extension=\"{ps_quote(ext_path)}\" {ps_quote(safe_url)}'; "
            f"$s.IconLocation = '{ps_quote(b_path)},0'; "
            f"$s.Description = 'Launch {ps_quote(b_name)} with LinkedIn Studio Bridge'; "
            f"$s.WorkingDirectory = '{ps_quote(os.path.dirname(b_path))}'; "
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

    # The result is read, not assumed.
    #
    # This reported success whenever PowerShell merely started, because the
    # return code was discarded. Set-Clipboard needs an interactive desktop
    # with STA clipboard access, so on a machine without one, a service
    # session or a CI runner, it fails while the studio tells the creator the
    # path is copied. They then paste whatever was already on the clipboard
    # into the Load Unpacked dialog and the extension does not load.
    #
    # The path is always returned either way, so the interface can show it for
    # manual copying when the clipboard is unavailable.
    try:
        ps_script = f"Set-Clipboard -Value '{ext_path.replace(chr(39), chr(39) * 2)}'"
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True, text=True, timeout=20,
        )
    except Exception as err:
        return {
            "status": "error",
            "extension_path": ext_path,
            "message": f"Clipboard copy failed: {err}. Copy the path shown above by hand.",
        }

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        return {
            "status": "error",
            "extension_path": ext_path,
            "message": (
                "Could not reach the clipboard on this machine. "
                + (detail[0] if detail else "Copy the path shown above by hand.")
            ),
        }

    return {
        "status": "success",
        "extension_path": ext_path,
        "message": "Extension path copied to clipboard."
    }
