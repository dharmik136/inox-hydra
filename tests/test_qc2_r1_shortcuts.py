"""
The shortcut scripts in the portable ZIP find the launcher it contains. [INS-09]

create_desktop_shortcut.vbs and .sh looked only for launch_studio.bat and
launch_studio.sh, which exist in a source checkout and not in the ZIP. The ZIP
ships both scripts, so the obvious file stopped with "Could not find
launch_studio.sh next to this script." (measured, rc 1) and the help told the
creator to make a shortcut by hand instead.

Both scripts now look for the portable launcher first, then the source one.

Strict Invariants:
- Zero em-dashes.
"""

import os
import shutil
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))


def _read(name):
    with open(os.path.join(REPO_ROOT, name), encoding="utf-8") as handle:
        return handle.read()


def _exec_line(entry):
    for line in entry.read_text(encoding="utf-8").splitlines():
        if line.startswith("Exec="):
            return line[len("Exec="):]
    raise AssertionError("no Exec line")


def test_the_windows_script_looks_for_the_portable_launcher_first():
    vbs = _read("create_desktop_shortcut.vbs")
    portable = vbs.index('"InoxHydra.bat"')
    source = vbs.index('"launch_studio.bat"')
    assert portable < source, "the portable launcher is not tried first"
    assert "Could not find launch_studio.bat next to this script." not in vbs
    assert "inox_hydra.ico" in vbs, "the shortcut would wear the generic batch file icon"


def test_the_portable_build_still_ships_both_scripts():
    import build_portable
    import inspect

    source = inspect.getsource(build_portable.main)
    assert "create_desktop_shortcut.vbs" in source and "create_desktop_shortcut.sh" in source


def _bundle(tmp_path, launcher_name):
    root = tmp_path / "InoxHydra-2.6.0-linux-x86_64"
    root.mkdir()
    shutil.copy2(os.path.join(REPO_ROOT, "create_desktop_shortcut.sh"), root / "create_desktop_shortcut.sh")
    launcher = root / launcher_name
    launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    launcher.chmod(0o755)
    (root / "assets").mkdir()
    (root / "assets" / "inox_hydra.png").write_bytes(b"png")
    home = tmp_path / "home"
    home.mkdir()
    return root, launcher, home


@pytest.mark.skipif(not sys.platform.startswith("linux") or not shutil.which("bash"),
                    reason="the Linux desktop entry")
def test_the_unix_script_in_a_portable_folder_points_at_inoxhydra_sh(tmp_path):
    root, launcher, home = _bundle(tmp_path, "InoxHydra.sh")
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
    done = subprocess.run(["bash", str(root / "create_desktop_shortcut.sh")], env=env,
                          capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stdout + done.stderr
    entry = home / ".local" / "share" / "applications" / "inox-hydra.desktop"
    assert _exec_line(entry) == f'"{launcher}"'
    assert f"Icon={root / 'assets' / 'inox_hydra.png'}" in entry.read_text(encoding="utf-8")


@pytest.mark.skipif(not shutil.which("bash"), reason="the shortcut script is bash")
def test_a_folder_with_no_launcher_still_says_so(tmp_path):
    root, launcher, home = _bundle(tmp_path, "something-else.sh")
    done = subprocess.run(["bash", str(root / "create_desktop_shortcut.sh")],
                          env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
                          capture_output=True, text=True, timeout=30)
    assert done.returncode == 1
    assert "InoxHydra.sh" in done.stdout and "launch_studio.sh" in done.stdout
