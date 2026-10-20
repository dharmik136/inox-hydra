"""
A launch keeps the previous session's log instead of deleting it. [BE-12]

Both launchers checked engine.log only at launch and deleted it whole when it
was over 2 MB, which removed the traceback of the session that had just
crashed, the one thing the log is for, before doctor --bundle could read it.
Now an oversized log is moved to engine.log.1, replacing the older one, and
the session's own growth is bounded by the access log keeping only failures
and changes (see test_qc2_r2_diagnostics.py).
"""

import os
import re
import shutil

import pytest

from test_qc_f2_launcher_log import _log_lines, _run, runs_the_launcher, sandbox  # noqa: F401

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_RS = os.path.join(REPO_ROOT, "desktop", "src-tauri", "src", "backend.rs")


@runs_the_launcher
def test_an_oversized_log_becomes_engine_log_1(sandbox):  # noqa: F811
    app, home, calls, env = sandbox
    os.symlink(shutil.which("mv"), os.path.join(env["PATH"], "mv"))
    logs = home / "logs"
    logs.mkdir()
    log = logs / "engine.log"
    crash = "Traceback (most recent call last):\nRuntimeError: the crash of the last session\n"
    log.write_text("x" * (3 * 1024 * 1024) + "\n" + crash, encoding="utf-8")
    (logs / "engine.log.1").write_text("an older session\n", encoding="utf-8")

    result = _run(app, env)
    assert result.returncode == 0, result.stdout + result.stderr

    kept = logs / "engine.log.1"
    assert kept.is_file(), "the previous session's log was deleted"
    assert kept.read_text(encoding="utf-8").endswith(crash)
    text = _log_lines(log, "uvicorn stub started", 1)
    assert "uvicorn stub started" in text
    assert "the crash of the last session" not in text
    assert log.stat().st_size < 1024 * 1024


@runs_the_launcher
def test_a_small_log_is_appended_to(sandbox):  # noqa: F811
    app, home, calls, env = sandbox
    os.symlink(shutil.which("mv"), os.path.join(env["PATH"], "mv"))
    logs = home / "logs"
    logs.mkdir()
    (logs / "engine.log").write_text("the last session\n", encoding="utf-8")
    _run(app, env)
    text = _log_lines(logs / "engine.log", "uvicorn stub started", 1)
    assert text.startswith("the last session\n")
    assert not (logs / "engine.log.1").exists()


def test_the_shell_launcher_moves_rather_than_deletes():
    with open(os.path.join(REPO_ROOT, "launch_studio.sh"), encoding="utf-8") as handle:
        source = handle.read()
    assert 'rm -f "$LOG_FILE"' not in source
    assert 'mv -f "$LOG_FILE" "$LOG_FILE.1"' in source


def test_the_desktop_shell_moves_rather_than_deletes():
    with open(BACKEND_RS, encoding="utf-8") as handle:
        source = handle.read()
    body = re.search(r"fn open_engine_log\(\)[^{]*\{(.*?)\n\}", source, re.S).group(1)
    assert "remove_file(&path)" not in body
    assert "std::fs::rename(&path, &previous)" in body
    assert 'with_file_name("engine.log.1")' in body
