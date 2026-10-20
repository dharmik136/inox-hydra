"""
The Linux and macOS source launcher writes the backend's log under the app
home's logs folder. [PLATFORM-26]

It wrote /tmp/inox_studio_backend.log: outside the app home, so never in the
diagnostics bundle, overwritten on every launch, and shared by every account
on the machine. With protected_regular, a second user's launch could not open
the first user's file, the redirect failed, and the backend never started
while the script said it was starting and opened the browser.

The launcher is run for real, from a copy, on a PATH that holds only stubs and
the few core tools it needs. Nothing here contacts port 8000 or starts a
browser: the port probe, the health check and the window opener are stubs
that record what they were asked.
"""

import os
import shutil
import stat
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LAUNCHER = os.path.join(REPO_ROOT, "launch_studio.sh")

# Run only on Linux. On macOS the launcher also tries browsers by absolute
# path under /Applications, which no stub on PATH can intercept, and a test
# must never open a real browser.
runs_the_launcher = pytest.mark.skipif(
    not sys.platform.startswith("linux") or not os.path.exists("/bin/bash"),
    reason="runs the launcher only where every browser it tries can be stubbed",
)

CORE_TOOLS = ("dirname", "mkdir", "wc", "rm", "date", "sleep", "uname", "seq", "cat", "tr", "nohup")


def _script(path, body):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("#!/bin/sh\n" + body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def sandbox(tmp_path):
    app = tmp_path / "app"
    (app / ".venv" / "bin").mkdir(parents=True)
    shutil.copy(LAUNCHER, app / "launch_studio.sh")
    os.symlink(os.path.join(REPO_ROOT, "studio"), app / "studio")
    calls = tmp_path / "calls.txt"

    # Real Python for the launcher's own questions, a stub for the server.
    _script(app / ".venv" / "bin" / "python", f'''
if [ "$1" = "-m" ] && [ "$2" = "uvicorn" ]; then
  echo "uvicorn stub started $*"
  echo "uvicorn $*" >> "{calls}"
  exit 0
fi
exec "{sys.executable}" "$@"
''')

    stubs = tmp_path / "bin"
    stubs.mkdir()
    for tool in CORE_TOOLS:
        found = shutil.which(tool)
        if found:
            os.symlink(found, stubs / tool)
    _script(stubs / "nc", f'echo "nc $*" >> "{calls}"; exit 1\n')
    _script(stubs / "curl", f'echo "curl $*" >> "{calls}"; exit 0\n')
    _script(stubs / "xdg-open", f'echo "xdg-open $*" >> "{calls}"; exit 0\n')

    home = tmp_path / "home"
    home.mkdir()
    env = {"PATH": str(stubs), "HOME": str(tmp_path / "user"), "INOX_HYDRA_HOME": str(home)}
    return app, home, calls, env


def _run(app, env):
    return subprocess.run(
        ["/bin/bash", str(app / "launch_studio.sh")], env=env, cwd=str(app),
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )


def _log_lines(log, needle, count, timeout=10.0):
    """The launcher starts the server in the background and returns, so its
    first line can land in the log a moment after the launcher exits."""
    import time
    deadline = time.monotonic() + timeout
    while True:
        text = log.read_text(encoding="utf-8") if log.is_file() else ""
        if text.count(needle) >= count or time.monotonic() > deadline:
            return text
        time.sleep(0.1)


@runs_the_launcher
def test_the_log_lands_in_the_app_homes_logs_folder(sandbox):
    app, home, calls, env = sandbox
    result = _run(app, env)
    assert result.returncode == 0, result.stdout + result.stderr

    log = home / "logs" / "engine.log"
    assert log.is_file(), f"no engine log under the app home: {result.stdout}"
    assert "uvicorn stub started" in _log_lines(log, "uvicorn stub started", 1)
    assert str(log) in result.stdout, "the launcher does not say where its log is"

    # A second launch appends, rather than wiping the log of the first.
    _run(app, env)
    assert _log_lines(log, "uvicorn stub started", 2).count("uvicorn stub started") == 2


def test_the_launcher_names_no_shared_temporary_file():
    with open(LAUNCHER, encoding="utf-8") as fh:
        assert "/tmp/" not in fh.read()


@runs_the_launcher
def test_a_backend_that_never_answers_is_reported_and_no_window_opens(sandbox):
    app, home, calls, env = sandbox
    _script(os.path.join(env["PATH"], "curl"), f'echo "curl $*" >> "{calls}"; exit 7\n')
    # The launcher's wait, without the waiting.
    os.remove(os.path.join(env["PATH"], "sleep"))
    _script(os.path.join(env["PATH"], "sleep"), "exit 0\n")
    result = _run(app, env)
    assert result.returncode != 0
    assert "did not start" in result.stdout
    assert "engine.log" in result.stdout
    assert "xdg-open" not in calls.read_text(encoding="utf-8")
