"""
Linux Autostart and Shortcuts Start the Studio, Wherever It Is Installed.
=========================================================================

A desktop entry's Exec line is split on spaces unless the path is quoted, so
an install path with a space (including the desktop shell's own "Inox Hydra"
binary) produced an autostart entry that started nothing while Settings said
it was on. Without any launcher next to the code, autostart registered a bare
Python interpreter, which also starts nothing.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import os
import shutil
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from studio.backend import desktop  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="desktop entries are a Linux format")


def _exec_argv(value):
    """The argv a launcher runs for an Exec value, per the Desktop Entry spec."""
    # String level escapes first, then the Exec quoting rules, then field codes.
    unescaped, i = [], 0
    mapping = {"s": " ", "n": "\n", "t": "\t", "r": "\r", "\\": "\\"}
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value) and value[i + 1] in mapping:
            unescaped.append(mapping[value[i + 1]])
            i += 2
            continue
        unescaped.append(value[i])
        i += 1
    text = "".join(unescaped)
    args, current, quoted, i, started = [], [], False, 0, False
    while i < len(text):
        ch = text[i]
        if quoted:
            if ch == "\\" and i + 1 < len(text) and text[i + 1] in '"`$\\':
                current.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                quoted = False
            else:
                current.append(ch)
        elif ch == '"':
            quoted, started = True, True
        elif ch == " ":
            if current or started:
                args.append("".join(current))
            current, started = [], False
        else:
            current.append(ch)
        i += 1
    if current or started:
        args.append("".join(current))
    return [arg.replace("%%", "%") for arg in args]


def _exec_of(entry_path):
    with open(entry_path, encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("Exec="):
                return line[len("Exec="):].rstrip("\n")
    raise AssertionError(f"no Exec line in {entry_path}")


@pytest.fixture
def linux(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(desktop, "get_startup_dir", lambda: str(tmp_path / "autostart"))
    return tmp_path


def _launcher(folder, name):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("#!/bin/sh\nexit 0\n")
    os.chmod(path, 0o755)
    return path


# ---------------------------------------------------------------------------
# PLATFORM-12: a path with a space is quoted in Exec
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("folder, name", [
    ("Shell Install", "Inox Hydra"),
    ("My Apps", "launch_studio.sh"),
    ("odd $HOME `x` \"q\" 100%", "InoxHydra.sh"),
])
def test_autostart_runs_the_launcher_whatever_its_path(linux, monkeypatch, folder, name):
    launcher = _launcher(str(linux / folder), name)
    monkeypatch.setattr(desktop, "_launcher_target", lambda: launcher)

    result = desktop.enable_autostart()
    assert result["enabled"] is True
    entry = desktop.get_startup_shortcut_path()
    assert _exec_argv(_exec_of(entry)) == [launcher]
    if shutil.which("desktop-file-validate"):
        checked = subprocess.run(["desktop-file-validate", entry], capture_output=True, text=True, encoding="utf-8")
        assert "error" not in (checked.stdout + checked.stderr).lower(), checked.stdout + checked.stderr


def test_a_python_launcher_is_run_by_the_interpreter(linux, monkeypatch):
    launcher = _launcher(str(linux / "My Apps"), "launch_studio.py")
    monkeypatch.setattr(desktop, "_launcher_target", lambda: launcher)
    desktop.enable_autostart()
    assert _exec_argv(_exec_of(desktop.get_startup_shortcut_path())) == [sys.executable, launcher]


@pytest.mark.skipif(not shutil.which("bash"), reason="the shortcut script is bash")
def test_the_shortcut_script_quotes_its_launcher(tmp_path):
    install = tmp_path / "My Apps" / "Inox Hydra"
    install.mkdir(parents=True)
    shutil.copy2(os.path.join(REPO_ROOT, "create_desktop_shortcut.sh"), install / "create_desktop_shortcut.sh")
    launcher = _launcher(str(install), "launch_studio.sh")
    home = tmp_path / "home"
    home.mkdir()
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    done = subprocess.run(["bash", str(install / "create_desktop_shortcut.sh")], env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert done.returncode == 0, done.stdout + done.stderr
    if sys.platform == "darwin":
        # macOS gets a .command file on the Desktop that execs the launcher.
        command = (home / "Desktop" / "Inox Hydra.command").read_text(encoding="utf-8")
        assert f'exec "{launcher}"' in command, command
        return
    entry = home / ".local" / "share" / "applications" / "inox-hydra.desktop"
    assert _exec_argv(_exec_of(entry)) == [launcher]


# ---------------------------------------------------------------------------
# PLATFORM-20: no launcher means autostart is unavailable, not bare python
# ---------------------------------------------------------------------------

def test_without_a_launcher_autostart_is_unavailable_and_says_why(linux, monkeypatch):
    empty = linux / "installed-copy"
    empty.mkdir()
    monkeypatch.setattr(desktop, "_install_roots", lambda: [str(empty)])

    assert desktop.describe()["autostart_available"] is False
    result = desktop.enable_autostart()
    assert result["enabled"] is False and result["reason"]
    assert not os.path.exists(desktop.get_startup_shortcut_path()), "an entry that starts nothing was written"
