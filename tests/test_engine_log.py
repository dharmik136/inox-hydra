"""
A launch that fails leaves something to read.
=============================================

The shell spawns uvicorn with CREATE_NO_WINDOW, so the child has no console to
write to, and its stdout and stderr were not redirected anywhere. They went
nowhere. A Python process that dies on an import error was therefore
indistinguishable from one still starting: the only signal was the readiness
timeout, the user saw a splash that never resolved, and nothing existed to
inspect afterwards. Release builds set the Windows subsystem, so the shell had
no stderr of its own to fall back on either.

The child's output now goes to a file. The file is deliberately the same one
studio/backend/paths.py already designates, because support.py's diagnostics
bundle tails the newest files in that directory, so an engine that failed to
start is collected by the existing diagnostics path with no further wiring.

These are source-level assertions. There is no Rust toolchain in this suite, so
the compile is proved by the desktop workflow, and what is checked here is the
part a compiler cannot check: that the two implementations of "where does state
live" still agree.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import paths

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_RS = os.path.join(REPO_ROOT, "desktop", "src-tauri", "src", "backend.rs")


@pytest.fixture(scope="module")
def source():
    with open(BACKEND_RS, encoding="utf-8") as handle:
        return handle.read()


def test_the_child_output_is_redirected_rather_than_discarded(source):
    """
    The defect itself. Without a Stdio redirect the handles are inherited, and
    an inherited handle under CREATE_NO_WINDOW is no handle at all.
    """
    assert "Stdio::from" in source, (
        "the child's output is not redirected, so a failed launch still leaves "
        "nothing to read"
    )
    assert ".stderr(" in source, "stderr is not captured, which is the stream that carries the traceback"


def test_the_log_lands_where_the_diagnostics_bundle_already_looks(source):
    """
    support.py tails the last three files in paths.get_logs_dir(). Writing
    anywhere else would mean a second place to look, and the person looking is
    usually someone who cannot reach the machine.
    """
    assert '"logs"' in source, "the shell does not write into the logs directory"
    assert '"engine.log"' in source


def test_the_two_implementations_agree_on_where_state_lives(source):
    """
    paths.py and backend.rs each resolve the application home independently,
    in different languages. A rename on one side would put the log somewhere
    the diagnostics bundle does not read, and nothing would fail loudly.
    """
    assert f'"{paths.APP_DIR_NAME_WINDOWS}"' in source, (
        f"backend.rs does not use {paths.APP_DIR_NAME_WINDOWS}, so the shell "
        f"and the engine disagree about the application directory"
    )
    assert "LOCALAPPDATA" in source


def test_the_home_override_is_honoured_by_the_shell_too(source):
    """
    INOX_HYDRA_HOME redirects every path the Python side resolves. A shell that
    ignored it would write outside a redirected home, which is exactly what
    that variable exists to prevent.
    """
    assert "INOX_HYDRA_HOME" in source, (
        "the shell ignores the home override, so a redirected install still "
        "writes its log to the default location"
    )


def test_the_log_is_bounded(source):
    """
    This runs on machines nobody maintains, and it appends on every launch.
    """
    assert "MAX_LOG_BYTES" in source
    match = re.search(r"MAX_LOG_BYTES:\s*u64\s*=\s*([^;]+);", source)
    assert match, "the bound is not a named constant"

    expression = match.group(1).strip()
    assert eval(expression.replace("_", "")) <= 16 * 1024 * 1024, (
        f"the log may grow to {expression}, which is not a bound anyone wants "
        f"on a user's disk"
    )


def test_logging_never_blocks_the_product_from_starting(source):
    """
    A log file is a diagnostic aid. If the directory is read only or the disk
    is full, the studio must still run: refusing to start because the log
    could not be opened would turn a diagnostic into an outage.
    """
    assert "fn open_engine_log() -> Option<std::fs::File>" in source, (
        "open_engine_log does not return an Option, so a failure to open the "
        "log has nowhere to go but upward"
    )
    assert "if let Some(file) = open_engine_log()" in source, (
        "the call site does not tolerate a missing log"
    )


def test_the_no_console_flag_is_still_set(source):
    """
    The redirect must not have been bought by letting a console flash up
    behind the application on every launch.
    """
    assert "CREATE_NO_WINDOW" in source
    assert "0x0800_0000" in source


def test_the_stale_comment_is_gone(source):
    """
    The old comment said the fix was not done here. A comment that describes a
    gap which has since been closed is worse than no comment.
    """
    assert "is the fix and is not done here" not in source
