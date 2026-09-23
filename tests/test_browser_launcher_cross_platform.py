"""
The bridge can be opened on macOS and Linux, not only on Windows.
=================================================================

browser_launcher carried Windows paths only: Program Files, %LOCALAPPDATA%,
the App Paths registry key, and .lnk shortcuts. On macOS and Linux
detect_installed_browsers returned an empty dict and create_desktop_shortcuts
produced nothing.

That was not cosmetic. The extension is how this product sees LinkedIn at all,
and the launcher is what opens a browser with it loaded. A creator on macOS or
Linux could install the studio and write posts, and had no assisted path to
the capture half of the product.

The launcher generation is tested here on every platform by pointing
sys.platform at the one under test, rather than only on a runner that happens
to be that platform. A quoting bug in the Linux .desktop file is not something
to discover from a macOS runner's silence.
"""

import os
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from studio.backend import browser_launcher
from studio.backend.browser_launcher import (BROWSER_CANDIDATES,
                                             _candidate_paths,
                                             _platform_key,
                                             create_desktop_shortcuts,
                                             detect_installed_browsers,
                                             get_desktop_dir)

# A path with a space in it, because the default install has one
# ("Linkedin strategy") and that is exactly what broke the Windows shortcut
# once already.
FAKE_BROWSERS = {
    "chrome": {
        "id": "chrome",
        "name": "Google Chrome",
        "path": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "is_available": True,
    }
}


@pytest.fixture
def desktop(monkeypatch):
    """A throwaway Desktop, so a test never writes to the real one."""
    path = tempfile.mkdtemp(prefix="inox_desktop_")
    monkeypatch.setattr(browser_launcher, "get_desktop_dir", lambda: path)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("platform_key", ["win32", "darwin", "linux"])
def test_every_browser_is_locatable_on_every_platform(platform_key):
    """
    A browser with no entry for a platform is invisible to a creator on it,
    which is the defect this replaces.
    """
    for candidate in BROWSER_CANDIDATES:
        paths = candidate["paths"]
        assert platform_key in paths, (
            f"{candidate['id']} has no {platform_key} location, so it can "
            f"never be detected there"
        )
        assert paths[platform_key], f"{candidate['id']} has an empty {platform_key} list"


def test_posix_browsers_are_also_searchable_on_path():
    """
    Distributions disagree about where a browser lives, and snap and flatpak
    put it somewhere else again. An absolute path table alone misses those.
    """
    for candidate in BROWSER_CANDIDATES:
        assert candidate.get("commands"), (
            f"{candidate['id']} has no command name, so a snap or flatpak "
            f"install is undetectable"
        )


def test_the_windows_registry_keys_are_intact():
    """
    These are literal backslash paths and have been mangled by escaping once.
    A broken key silently loses the registry fallback on Windows.
    """
    for candidate in BROWSER_CANDIDATES:
        key = candidate["reg_key"]
        assert key.count(chr(92)) == 5, f"{candidate['id']} registry key is malformed: {key!r}"
        assert key.endswith(".exe")
        assert not any(ord(ch) < 32 for ch in key), (
            f"{candidate['id']} registry key contains a control character, "
            f"which is what a backslash escape leaves behind"
        )


def test_candidate_paths_tolerates_the_older_shape():
    """The helper degrades rather than raising inside detection."""
    assert _candidate_paths({"paths": ["/a", "/b"]}) == ["/a", "/b"]
    assert _candidate_paths({"paths": None}) == []
    assert _candidate_paths({}) == []


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def test_detection_returns_a_shape_on_any_platform():
    """
    Finding nothing is a normal answer on a server or a CI runner. What must
    not happen is raising, or returning something that is not a mapping.
    """
    browsers = detect_installed_browsers()
    assert isinstance(browsers, dict)
    for browser_id, info in browsers.items():
        assert info["id"] == browser_id
        assert info["is_available"] is True
        assert os.path.exists(info["path"])


def test_detection_finds_a_browser_through_path(monkeypatch):
    """
    The snap and flatpak case. Nothing is at the absolute locations, and the
    executable is on PATH under its command name.
    """
    monkeypatch.setattr(browser_launcher.sys, "platform", "linux")
    monkeypatch.setattr(browser_launcher.os.path, "exists", lambda p: p == "/snap/bin/chromium")
    monkeypatch.setattr(
        browser_launcher.shutil, "which",
        lambda name: "/snap/bin/chromium" if name == "google-chrome" else None,
    )

    browsers = detect_installed_browsers()

    assert "chrome" in browsers, "a browser on PATH was not found"
    assert browsers["chrome"]["path"] == "/snap/bin/chromium"


def test_path_is_not_consulted_on_windows(monkeypatch):
    """
    The registry is the better answer there, and these browsers are not
    installed as bare names on PATH.
    """
    called = []
    monkeypatch.setattr(browser_launcher.sys, "platform", "win32")
    monkeypatch.setattr(browser_launcher.os.path, "exists", lambda p: False)
    monkeypatch.setattr(browser_launcher.shutil, "which", lambda n: called.append(n))

    detect_installed_browsers()
    assert called == []


# ---------------------------------------------------------------------------
# The launchers
# ---------------------------------------------------------------------------

def test_macos_launcher_is_a_runnable_command_file(monkeypatch, desktop):
    monkeypatch.setattr(browser_launcher.sys, "platform", "darwin")

    results = create_desktop_shortcuts(FAKE_BROWSERS)

    assert len(results) == 1 and results[0]["status"] == "created"
    path = results[0]["shortcut_path"]
    assert path.endswith(".command"), "Finder only runs .command files directly"

    body = open(path, encoding="utf-8").read()
    assert body.startswith("#!/bin/sh"), "no shebang, so this is not executable as a script"
    assert "--load-extension" in body
    assert os.access(path, os.X_OK), "not marked executable, so double clicking does nothing"


def test_linux_launcher_is_a_valid_desktop_entry(monkeypatch, desktop):
    monkeypatch.setattr(browser_launcher.sys, "platform", "linux")

    results = create_desktop_shortcuts(FAKE_BROWSERS)

    assert len(results) == 1 and results[0]["status"] == "created"
    path = results[0]["shortcut_path"]
    assert path.endswith(".desktop")

    body = open(path, encoding="utf-8").read()
    assert body.startswith("[Desktop Entry]"), "the header must be the first line or nothing reads it"
    for required in ("Type=Application", "Name=", "Exec=", "Terminal=false"):
        assert required in body, f"the entry is missing {required}"
    assert os.access(path, os.X_OK)


@pytest.mark.parametrize("platform_name", ["darwin", "linux"])
def test_a_path_with_a_space_survives_into_the_launcher(monkeypatch, desktop, platform_name):
    """
    The default install path contains a space. An unquoted argument splits
    across two, and the browser starts without the extension, which is the
    one thing the launcher exists to do. The Windows shortcut had to be fixed
    for exactly this.
    """
    monkeypatch.setattr(browser_launcher.sys, "platform", platform_name)
    monkeypatch.setattr(
        browser_launcher, "get_extension_dir",
        lambda: "/home/creator/Linkedin strategy/studio/extension",
    )

    path = create_desktop_shortcuts(FAKE_BROWSERS)[0]["shortcut_path"]
    body = open(path, encoding="utf-8").read()

    assert "Linkedin strategy" in body
    # The space must sit inside a quoted region, not between two arguments.
    line = next(l for l in body.splitlines() if "load-extension" in l)
    assert ("'" in line) or ('"' in line), (
        f"the extension path is unquoted, so it splits on the space: {line}"
    )


def test_a_browser_that_cannot_be_written_is_reported_not_swallowed(monkeypatch, desktop):
    monkeypatch.setattr(browser_launcher.sys, "platform", "linux")
    monkeypatch.setattr(browser_launcher, "get_desktop_dir",
                        lambda: "/nonexistent/directory/that/cannot/be/written")

    results = create_desktop_shortcuts(FAKE_BROWSERS)

    assert results[0]["status"] == "failed"
    assert results[0]["error"], "a failure was recorded with no reason attached"


def test_no_browsers_produces_no_launchers_and_no_error(monkeypatch, desktop):
    monkeypatch.setattr(browser_launcher.sys, "platform", "linux")
    assert create_desktop_shortcuts({}) == []


# ---------------------------------------------------------------------------
# Desktop resolution
# ---------------------------------------------------------------------------

def test_the_desktop_directory_is_a_real_directory():
    assert os.path.isdir(get_desktop_dir())


def test_a_localised_linux_desktop_is_honoured(monkeypatch):
    """
    A German desktop is ~/Schreibtisch. Writing to an English path there
    creates a folder nobody looks in.
    """
    import subprocess as sp
    monkeypatch.setattr(browser_launcher.sys, "platform", "linux")
    monkeypatch.setattr(
        browser_launcher.subprocess, "run",
        lambda *a, **k: sp.CompletedProcess(a, 0, stdout="/home/creator/Schreibtisch\n", stderr=""),
    )
    monkeypatch.setattr(browser_launcher.os.path, "isdir", lambda p: True)

    assert get_desktop_dir() == "/home/creator/Schreibtisch"


def test_a_headless_linux_box_does_not_get_a_desktop_folder(monkeypatch):
    """
    xdg-user-dir echoes $HOME when no desktop is configured. Treating that as
    a Desktop directory would scatter launchers into the home directory.
    """
    import subprocess as sp
    from pathlib import Path

    monkeypatch.setattr(browser_launcher.sys, "platform", "linux")
    monkeypatch.setattr(
        browser_launcher.subprocess, "run",
        lambda *a, **k: sp.CompletedProcess(a, 0, stdout=str(Path.home()) + "\n", stderr=""),
    )
    monkeypatch.setattr(browser_launcher.Path, "is_dir", lambda self: False)

    assert get_desktop_dir() == str(Path.home())
