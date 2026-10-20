"""
A grounding server can neither hang the studio nor read its keys. [BE-04, BE-05, BE-14, BE-15]

Most MCP servers start through a launcher (npx, uvx, a shell script) that runs
the real server as its own child. The timeout killed only the launcher, the
real server kept the pipe open, and readline waited for it for ever: the
preview never answered, and each press left a process behind. Every server
also inherited the studio's whole environment, provider API keys included.
On Windows, npx is npx.cmd, which CreateProcess cannot start without cmd.exe,
so the command the interface suggests could never start there. And a failed
source showed as "[object Object]".
"""

import json
import os
import signal
import sys
import threading
import time

import pytest

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend"))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from mcp_client import grounding as grounding_module  # noqa: E402
from mcp_client import protocol  # noqa: E402
from mcp_client import servers as servers_module  # noqa: E402
from mcp_client.protocol import McpServer  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "fake_mcp_server.py")
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="the launcher stand-in is a POSIX shell script")


@pytest.fixture(autouse=True)
def clean_servers():
    for existing in servers_module.list_servers():
        servers_module.remove_server(existing["name"])
    yield
    for existing in servers_module.list_servers():
        servers_module.remove_server(existing["name"])


def _alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    # A zombie still answers kill(0); it holds nothing open.
    try:
        with open(f"/proc/{pid}/stat") as handle:
            return handle.read().split()[2] != "Z"
    except OSError:
        return True


def _hanging_launcher(tmp_path, tag="a"):
    """A shell script that runs a server as its child, as npx does, and the server never answers."""
    pidfile = tmp_path / f"server-{tag}.pid"
    server = tmp_path / f"hang-{tag}.py"
    server.write_text(
        "import os, sys, time\n"
        f"open({str(pidfile)!r}, 'w').write(str(os.getpid()))\n"
        "time.sleep(600)\n",
        encoding="utf-8",
    )
    script = tmp_path / f"launcher-{tag}.sh"
    script.write_text(f'#!/bin/sh\n"{sys.executable}" "{server}"\necho "launcher exiting" >&2\n', encoding="utf-8")
    return ["/bin/sh", str(script)], pidfile


def _wait_for(path, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and path.read_text().strip():
            return int(path.read_text().strip())
        time.sleep(0.05)
    raise AssertionError(f"{path} never appeared")


def _kill(pid):
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


@posix_only
def test_a_hanging_server_under_a_launcher_times_out_and_leaves_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(protocol, "START_TIMEOUT_SECONDS", 1.5)
    command, pidfile = _hanging_launcher(tmp_path)
    server = McpServer("wedged", command)
    box = {}
    worker = threading.Thread(target=lambda: box.update(ok=server.start()), daemon=True)
    started = time.monotonic()
    worker.start()
    pid = _wait_for(pidfile)
    try:
        worker.join(timeout=1.5 + 3)
        assert not worker.is_alive(), "start() is still blocked on a server that will never answer"
        assert box["ok"] is False
        assert time.monotonic() - started < 1.5 + 3
        server.stop()
        deadline = time.monotonic() + 3
        while _alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not _alive(pid), "the real server outlived its launcher"
        assert "did not answer" in (server.last_error or "")
    finally:
        _kill(pid)


@posix_only
def test_a_stopped_healthy_server_under_a_launcher_leaves_nothing(tmp_path):
    pidfile = tmp_path / "ok.pid"
    server_py = tmp_path / "ok.py"
    server_py.write_text(
        "import os, runpy, sys\n"
        f"open({str(pidfile)!r}, 'w').write(str(os.getpid()))\n"
        f"sys.argv = [{FIXTURE!r}]\n"
        f"runpy.run_path({FIXTURE!r}, run_name='__main__')\n",
        encoding="utf-8",
    )
    script = tmp_path / "launcher.sh"
    script.write_text(f'#!/bin/sh\n"{sys.executable}" "{server_py}"\n', encoding="utf-8")
    server = McpServer("notes", ["/bin/sh", str(script)])
    assert server.start() is True
    pid = _wait_for(pidfile)
    try:
        assert server.list_resources()
        server.stop()
        deadline = time.monotonic() + 3
        while _alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not _alive(pid)
    finally:
        _kill(pid)


@posix_only
def test_gather_has_one_overall_deadline(tmp_path, monkeypatch):
    monkeypatch.setattr(protocol, "START_TIMEOUT_SECONDS", 30.0)
    monkeypatch.setattr(grounding_module, "GATHER_TIMEOUT_SECONDS", 2.0)
    pids = []
    for tag in ("a", "b", "c"):
        command, pidfile = _hanging_launcher(tmp_path, tag)
        servers_module.add_server(f"Wedged {tag}", command)
        servers_module.set_enabled(f"Wedged {tag}", True)
        pids.append(pidfile)
    started = time.monotonic()
    try:
        result = grounding_module.gather(provider="local_deterministic")
        took = time.monotonic() - started
        assert took < 2.0 + 3, f"gather took {took:.1f}s against a 2 s budget"
        assert result["material"] == []
        assert {e["server"] for e in result["errors"]} == {"Wedged a", "Wedged b", "Wedged c"}
    finally:
        for pidfile in pids:
            if pidfile.exists() and pidfile.read_text().strip():
                _kill(int(pidfile.read_text()))


def test_a_server_never_sees_the_studios_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-notarealkey-PLANTED-IN-ENV")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaPLANTED")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:PLANTED")
    monkeypatch.setenv("INOX_HYDRA_HOME", os.environ["INOX_HYDRA_HOME"])
    dump = tmp_path / "env.json"
    server_py = tmp_path / "envdump.py"
    server_py.write_text(
        "import json, os, runpy, sys\n"
        f"json.dump(dict(os.environ), open({str(dump)!r}, 'w'))\n"
        f"sys.argv = [{FIXTURE!r}]\n"
        f"runpy.run_path({FIXTURE!r}, run_name='__main__')\n",
        encoding="utf-8",
    )
    with McpServer("notes", [sys.executable, str(server_py)], env={"NOTES_DIR": "/notes"}) as server:
        assert server.list_resources()
    seen = json.loads(dump.read_text())
    for planted in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "INOX_HYDRA_HOME"):
        assert planted not in seen, f"the server saw {planted}"
    assert "PLANTED" not in json.dumps(seen)
    assert seen.get("NOTES_DIR") == "/notes", "the server's own settings are still passed"
    assert seen.get("PATH"), "a server still needs PATH to find its runtime"


def test_the_child_environment_is_an_allowlist():
    env = protocol.child_environment(
        {"PATH": "/usr/bin", "HOME": "/home/x", "LANG": "en_IN.UTF-8", "OPENAI_API_KEY": "sk-x",
         "AWS_SECRET_ACCESS_KEY": "y", "SystemRoot": "C:\\Windows"},
        {"NOTES": "1"},
    )
    assert env == {"PATH": "/usr/bin", "HOME": "/home/x", "LANG": "en_IN.UTF-8", "SystemRoot": "C:\\Windows",
                   "NOTES": "1"}


def test_on_windows_a_cmd_shim_runs_through_cmd(tmp_path):
    """npx is npx.cmd on Windows, which CreateProcess cannot start by itself."""
    bin_dir = tmp_path / "nodejs"
    bin_dir.mkdir()
    (bin_dir / "npx.cmd").write_text("@echo off\n", encoding="utf-8")
    env = {"PATH": str(bin_dir), "PATHEXT": ".COM;.EXE;.BAT;.CMD", "COMSPEC": "C:\\Windows\\system32\\cmd.exe"}
    argv = protocol.launch_command(["npx", "-y", "@some/mcp-server"], env, platform="win32")
    assert isinstance(argv, str)
    assert argv.startswith('"C:\\Windows\\system32\\cmd.exe" /d /s /c "')
    assert "npx.cmd" in argv and "-y @some/mcp-server" in argv


def test_on_windows_an_exe_runs_directly(tmp_path):
    bin_dir = tmp_path / "py"
    bin_dir.mkdir()
    (bin_dir / "uvx.exe").write_text("", encoding="utf-8")
    env = {"PATH": str(bin_dir), "PATHEXT": ".COM;.EXE;.BAT;.CMD"}
    argv = protocol.launch_command(["uvx", "notes-server"], env, platform="win32")
    assert isinstance(argv, list)
    assert argv[0].lower().endswith("uvx.exe") and argv[1:] == ["notes-server"]


@pytest.mark.parametrize("risky", ["a&b", "x|y", "<in", "out>", "100%", "^", "!x!", 'say "hi"', "a\nb"])
def test_on_windows_cmd_metacharacters_are_refused(tmp_path, risky):
    """Through cmd.exe an argument could become a second command, so such a server is not started."""
    bin_dir = tmp_path / "nodejs"
    bin_dir.mkdir()
    (bin_dir / "npx.cmd").write_text("@echo off\n", encoding="utf-8")
    env = {"PATH": str(bin_dir), "PATHEXT": ".CMD"}
    with pytest.raises(protocol.McpError) as refused:
        protocol.launch_command(["npx", risky], env, platform="win32")
    assert "cmd.exe" in str(refused.value)


def test_elsewhere_the_command_runs_as_given():
    assert protocol.launch_command(["npx", "-y", "x"], {"PATH": "/usr/bin"}, platform="linux") == ["npx", "-y", "x"]


def test_a_missing_command_says_so():
    server = McpServer("missing", ["a-binary-that-is-not-installed-anywhere"])
    assert server.start() is False
    assert "a-binary-that-is-not-installed-anywhere" in server.last_error
    assert "not found" in server.last_error


def test_the_preview_names_each_failed_source_in_words(confirmed_creator):
    """BE-15: errors are sentences, not objects the interface prints as [object Object]."""
    from fastapi.testclient import TestClient
    from app import app

    servers_module.add_server("Broken", ["a-binary-that-is-not-installed-anywhere"])
    servers_module.set_enabled("Broken", True)
    res = TestClient(app).get("/api/v1/mcp/preview")
    assert res.status_code == 200, res.text
    errors = res.json()["errors"]
    assert errors and all(isinstance(e, str) for e in errors)
    assert errors[0].startswith("Broken: ")
    assert "not found" in errors[0]
