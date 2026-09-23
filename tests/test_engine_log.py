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


# ---------------------------------------------------------------------------
# The engine does not outlive an abnormal exit
# ---------------------------------------------------------------------------

def test_the_child_is_tied_to_this_process(source):
    """
    Backend::shutdown covers the ordinary exit. It does not run when the shell
    is killed outright, and the engine then keeps running with no window,
    holding port 8000. Because is_ready correctly reports that engine as
    healthy, the next launch attaches to a process the user cannot see and did
    not knowingly leave behind.
    """
    assert "mod job_object" in source, "nothing ties the engine to the shell's lifetime"
    assert "KILL_ON_JOB_CLOSE" in source
    assert "tie_to_this_process(&child)" in source, (
        "the job object exists but is never applied to the spawned engine"
    )


def test_only_a_backend_we_started_is_tied(source):
    """
    The module's first rule: never terminate a backend this process did not
    spawn. A creator may have the studio running from the tray with a
    scheduler mid post. A job that killed it at our exit would break that
    rule in the worst way, silently and at shutdown.
    """
    spawn_at = source.index("match command.spawn()")
    tie_at = source.index("tie_to_this_process(&child)")
    attached_at = source.index("return Ok(Backend::Attached)")

    assert attached_at < spawn_at < tie_at, (
        "the attach path does not return before the spawn path ties a job, so "
        "an engine we merely attached to could be killed at our exit"
    )


def test_the_job_handle_is_not_closed_after_assignment(source):
    """
    Closing our handle closes the job, and kill-on-close would then take the
    engine down immediately rather than at our exit. The handle is held on
    purpose and the kernel releases it when this process dies.

    The two CloseHandle calls that remain are the failure paths, which run
    before any process has been assigned.
    """
    assign_at = source.index("AssignProcessToJobObject(job, child.as_raw_handle()) == 0")
    tail = source[assign_at:source.index("Where the interpreter lives")]

    # One CloseHandle inside the failed-assignment branch, and none after it.
    branch_end = tail.index("return;")
    assert "CloseHandle" not in tail[branch_end:], (
        "the job handle is closed after the engine was assigned to it, which "
        "kills the engine immediately instead of at our exit"
    )


def test_the_struct_layout_matches_what_windows_expects(source):
    """
    A hand declared struct that is the wrong size makes
    SetInformationJobObject fail with ERROR_INVALID_PARAMETER. The code
    handles that, but silently and without the flag, so the orphan returns and
    nothing says so.

    ctypes follows the same C ABI rules as repr(C), so agreement here is
    agreement there. Verified against the live API: 144 bytes on x64, with
    IoInfo at offset 64.
    """
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    # The Rust field order has to match, field for field, or the flag lands in
    # the wrong slot and means something else entirely.
    rust_fields = [
        "per_process_user_time_limit", "per_job_user_time_limit", "limit_flags",
        "minimum_working_set_size", "maximum_working_set_size",
        "active_process_limit", "affinity", "priority_class", "scheduling_class",
    ]
    declared = source[source.index("struct BasicLimitInformation"):]
    declared = declared[:declared.index("}")]
    found = [name for name in rust_fields if name in declared]
    assert found == rust_fields, (
        f"BasicLimitInformation field order drifted: {found}"
    )

    order_in_source = sorted(rust_fields, key=declared.index)
    assert order_in_source == rust_fields, (
        f"fields are declared out of order, so limit_flags is not where "
        f"Windows reads it: {order_in_source}"
    )


@pytest.mark.skipif(sys.platform != "win32", reason="Job Objects are a Win32 primitive")
def test_windows_accepts_this_exact_layout():
    """
    Not a mirror of the source: the real API is called with the same layout
    and must accept it. This is what proves the size and the information class
    are right, rather than merely self consistent.
    """
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class Io(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class Extended(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", Basic),
            ("IoInfo", Io),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD
    ]

    job = kernel32.CreateJobObjectW(None, None)
    assert job, "could not create a job object at all"
    try:
        info = Extended()
        info.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        accepted = kernel32.SetInformationJobObject(
            job, 9, ctypes.byref(info), ctypes.sizeof(info)
        )
        assert accepted, (
            f"Windows rejected the layout backend.rs declares, error "
            f"{ctypes.get_last_error()}. The Rust call would fail the same "
            f"way and leave the engine unprotected with no message."
        )
    finally:
        kernel32.CloseHandle(job)
