"""
The portable launchers say what really happened. [INS-07, INS-08]

InoxHydra.bat and InoxHydra.sh treated any program on port 8000 as the studio
("Already running", then opened the other program's page), and reported
"Ready." after a fixed wait even when the engine had died, with no log
anywhere. Measured in the research: an unrelated http.server on the port was
opened as the studio; an engine that exited at once printed "Ready." after
3009 ms.

Both launchers now run `python -m studio.backend.desktop launch`: the studio is
up only when /api/v1/health answers with this application's name; another
program on 8000 is named, and the studio starts on the next free port of a
small range, with a plain warning that the extension needs 8000; an engine
that dies is reported with the tail of logs/engine.log and no window opens.

No test here touches port 8000 or opens a browser. Ports are chosen from a
free block well away from it, browsers are a recorder, and the end to end
test replaces uvicorn with a stand-in that only answers the health check.

Strict Invariants:
- Zero em-dashes.
"""

import http.server
import json
import os
import random
import shutil
import signal
import stat
import subprocess
import sys
import threading

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from studio.backend import desktop  # noqa: E402
import build_portable  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers: a free block of ports, an unrelated program, a fake studio
# ---------------------------------------------------------------------------

def _free_block(size=4):
    for _ in range(200):
        base = random.randint(20000, 60000)
        ports = list(range(base, base + size))
        if all(desktop._can_bind(port) for port in ports):
            return ports
    pytest.skip("no free block of ports")


class _Server:
    def __init__(self, port, body, content_type="text/html"):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                payload = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


STUDIO_HEALTH = json.dumps({"status": "ok", "app": "inox-hydra", "version": "9.9.9"})


@pytest.fixture
def servers():
    started = []

    def start(port, body="<h1>some other app</h1>", content_type="text/html"):
        server = _Server(port, body, content_type)
        started.append(server)
        return server

    yield start
    for server in started:
        server.close()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


class _Recorder:
    def __init__(self):
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        return "a recorder"


# ---------------------------------------------------------------------------
# The readiness rule
# ---------------------------------------------------------------------------

def test_another_program_on_a_port_is_not_the_studio(servers):
    other, studio, free = _free_block(3)
    servers(other)
    servers(studio, STUDIO_HEALTH, "application/json")
    assert desktop.probe_port(other) == ("taken", None)
    assert desktop.probe_port(studio) == ("studio", "9.9.9")
    assert desktop.probe_port(free) == ("free", None)


def test_the_studio_prefers_8000_and_the_range_is_small(monkeypatch):
    monkeypatch.delenv("INOX_HYDRA_PORT", raising=False)
    ports = desktop.candidate_ports()
    assert ports[0] == desktop.EXTENSION_PORT == 8000
    assert len(ports) == desktop.PORT_RANGE_SIZE <= 10
    monkeypatch.setenv("INOX_HYDRA_PORT", "not a port")
    assert desktop.candidate_ports()[0] == 8000


def test_another_program_on_the_first_port_moves_the_studio_and_says_why(servers, home, capsys):
    taken, free, _, _ = _free_block()
    servers(taken)
    started = []

    def spawn(port):
        started.append(port)
        servers(port, STUDIO_HEALTH, "application/json")
        return None

    opener = _Recorder()
    result = desktop.launch(ports=[taken, free], opener=opener, spawn=spawn, timeout=5)
    out = capsys.readouterr().out

    assert result == desktop.LAUNCH_READY_ELSEWHERE
    assert started == [free]
    assert opener.urls == [f"http://127.0.0.1:{free}"], "the other program's page was opened"
    assert f"Port {taken} is in use by another program, not Inox Hydra." in out
    assert f"only connects on port {desktop.EXTENSION_PORT}" in out


def test_a_studio_already_running_elsewhere_in_the_range_is_reused(servers, home, capsys):
    free, running = _free_block(2)
    servers(running, STUDIO_HEALTH, "application/json")
    opener = _Recorder()

    def spawn(port):
        raise AssertionError("a second engine was started beside the running one")

    result = desktop.launch(ports=[free, running], opener=opener, spawn=spawn, timeout=5)
    assert result == desktop.LAUNCH_READY_ELSEWHERE
    assert opener.urls == [f"http://127.0.0.1:{running}"]
    assert "already running" in capsys.readouterr().out


def test_the_launcher_probes_only_the_ports_it_was_given(servers, home, monkeypatch, capsys):
    free, running = _free_block(2)
    servers(running, STUDIO_HEALTH, "application/json")
    probed = []
    real = desktop.probe_port

    def recording(port, timeout=1.5):
        probed.append(port)
        return real(port, timeout)

    monkeypatch.setattr(desktop, "probe_port", recording)
    desktop.launch(ports=[free, running], opener=_Recorder(), spawn=lambda port: None, timeout=2)
    assert set(probed) <= {free, running}, probed


def test_an_engine_that_dies_is_reported_with_its_log_and_no_window_opens(home, capsys):
    (port,) = _free_block(1)
    log = desktop.engine_log_path()

    def spawn(port):
        with open(log, "a", encoding="utf-8") as handle:
            handle.write("--- engine launch at unix time 1 ---\nModuleNotFoundError: No module named 'fastapi'\n")
        return subprocess.Popen([sys.executable, "-c", "raise SystemExit(1)"])

    opener = _Recorder()
    result = desktop.launch(ports=[port], opener=opener, spawn=spawn, timeout=10)
    out = capsys.readouterr().out
    assert result == desktop.LAUNCH_FAILED
    assert opener.urls == []
    assert "stopped while it was starting" in out
    assert "No module named 'fastapi'" in out
    assert log in out
    assert "Ready" not in out and "ready" not in out


def test_a_port_taken_as_the_engine_binds_moves_to_the_next(servers, home, capsys):
    first, second = _free_block(2)
    log = desktop.engine_log_path()
    calls = []

    def spawn(port):
        calls.append(port)
        if port == first:
            with open(log, "a", encoding="utf-8") as handle:
                handle.write(f"--- engine launch at unix time 2 ---\n[Errno 98] error while attempting to bind "
                             f"on address ('127.0.0.1', {port}): address already in use\n")
            return subprocess.Popen([sys.executable, "-c", "raise SystemExit(1)"])
        servers(port, STUDIO_HEALTH, "application/json")
        return None

    opener = _Recorder()
    result = desktop.launch(ports=[first, second], opener=opener, spawn=spawn, timeout=10)
    assert result == desktop.LAUNCH_READY_ELSEWHERE
    assert calls == [first, second]
    assert opener.urls == [f"http://127.0.0.1:{second}"]


def test_no_free_port_starts_nothing(servers, home, capsys):
    ports = _free_block(2)
    for port in ports:
        servers(port)

    def spawn(port):
        raise AssertionError("an engine was started with every port taken")

    assert desktop.launch(ports=ports, opener=_Recorder(), spawn=spawn, timeout=2) == desktop.LAUNCH_FAILED
    assert "all in use by other programs" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# The launchers that ship
# ---------------------------------------------------------------------------

def test_the_windows_launcher_hands_over_and_keeps_its_message_on_screen():
    bat = build_portable.LAUNCHER
    assert r'"%~dp0runtime\python.exe" -s -m studio.backend.desktop launch' in bat
    assert "Test-NetConnection" not in bat, "any listener would count as the studio again"
    assert "timeout /t" not in bat, "a fixed wait would count as started again"
    after = bat[bat.index("studio.backend.desktop launch"):]
    assert "if errorlevel 1" in after and "pause" in after
    assert "Zero cloud egress" not in bat


def test_the_unix_launcher_never_falls_back_to_the_hosts_python():
    sh = build_portable.UNIX_LAUNCHER
    assert 'exec "$PYTHON_EXE" -s -m studio.backend.desktop launch' in sh
    assert 'PYTHON_EXE="python3"' not in sh
    assert "nc -z" not in sh and "sleep 3" not in sh


def test_the_in_box_readme_promises_only_what_exists():
    """[INS-12] No store link that does not exist, no wrong signing claim, the real launcher behaviour."""
    readme = build_portable.README
    assert "Chrome\nWeb Store link" not in readme and "Web Store link" not in readme
    assert "several hundred dollars" not in readme
    assert "The studio opens in its own window." not in readme
    assert "Port 8000 is in use by another program" in readme
    assert "only connects on port\n      8000" in readme or "only connects on port 8000" in readme
    assert "Install the browser extension that captures leads and analytics" in readme


def test_the_unix_archives_carry_a_readme_of_their_own():
    readme = build_portable.UNIX_README
    assert ".bat" not in readme and "LOCALAPPDATA" not in readme
    assert "./InoxHydra.sh" in readme
    import inspect

    assert "README if platform.system() == \"Windows\" else UNIX_README" in inspect.getsource(build_portable.main)


def test_the_engine_binds_loopback_only():
    import inspect

    assert desktop.STUDIO_HOST == "127.0.0.1"
    assert "host=STUDIO_HOST" in inspect.getsource(desktop.serve)


# ---------------------------------------------------------------------------
# End to end: the shipped InoxHydra.sh, from a copy laid out like the bundle
# ---------------------------------------------------------------------------

FAKE_UVICORN = r'''
"""Stands in for uvicorn: answers the health check and nothing else."""
import http.server, json, os, sys

def run(app, host, port, log_level=None):
    with open(os.path.join(os.environ["INOX_HYDRA_HOME"], "engines.txt"), "a") as handle:
        handle.write(f"{os.getpid()} {port}\n")
    if os.environ.get("FAKE_ENGINE") == "die":
        print("Traceback (most recent call last):\nImportError: the engine could not start", file=sys.stderr)
        raise SystemExit(1)
    print(f"INFO:     Uvicorn running on http://{host}:{port}", file=sys.stderr)
    body = json.dumps({"status": "ok", "app": "inox-hydra", "version": "e2e"}).encode()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    http.server.HTTPServer((host, port), Handler).serve_forever()
'''

runs_the_launcher = pytest.mark.skipif(
    not sys.platform.startswith("linux") or not os.path.exists("/bin/bash"),
    reason="runs the launcher only where every browser it tries can be stubbed",
)


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / "InoxHydra-test-linux-x86_64"
    (root / "runtime" / "bin").mkdir(parents=True)
    # The base interpreter, so the launcher really runs from runtime/bin.
    os.symlink(os.path.realpath(sys.executable), root / "runtime" / "bin" / "python3")
    os.symlink(os.path.join(REPO_ROOT, "studio"), root / "studio")
    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / "uvicorn.py").write_text(FAKE_UVICORN, encoding="utf-8")
    launcher = root / "InoxHydra.sh"
    launcher.write_text(build_portable.UNIX_LAUNCHER, encoding="utf-8")
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

    stubs = tmp_path / "bin"
    stubs.mkdir()
    for tool in ("dirname",):
        os.symlink(shutil.which(tool), stubs / tool)
    calls = tmp_path / "opened.txt"
    for opener in ("xdg-open", "open"):
        script = stubs / opener
        script.write_text(f'#!/bin/sh\necho "{opener} $*" >> "{calls}"\n', encoding="utf-8")
        script.chmod(0o755)

    home = tmp_path / "home"
    home.mkdir()
    env = {
        "PATH": str(stubs),
        "HOME": str(tmp_path / "user"),
        "INOX_HYDRA_HOME": str(home),
        # Stands in for the bundle's sitecustomize, which puts app/ and lib/ on the path.
        "PYTHONPATH": os.pathsep.join([str(fake), REPO_ROOT]),
    }
    yield root, env, calls, home

    engines = home / "engines.txt"
    if engines.exists():
        for line in engines.read_text().splitlines():
            try:
                os.kill(int(line.split()[0]), signal.SIGTERM)
            except (OSError, ValueError):
                pass


def _run(root, env):
    return subprocess.run(["/bin/bash", str(root / "InoxHydra.sh")], cwd=str(root), env=env,
                          capture_output=True, text=True, timeout=90)


@runs_the_launcher
def test_the_shipped_launcher_skips_another_program_and_opens_the_studio(bundle, servers):
    root, env, calls, home = bundle
    taken, free, _, _ = _free_block()
    servers(taken)
    env["INOX_HYDRA_PORT"] = str(taken)

    result = _run(root, env)
    assert result.returncode == desktop.LAUNCH_READY_ELSEWHERE, result.stdout + result.stderr
    assert f"Port {taken} is in use by another program, not Inox Hydra." in result.stdout
    assert f"The studio is ready at http://127.0.0.1:{free}." in result.stdout
    assert calls.read_text().strip() == f"xdg-open http://127.0.0.1:{free}"
    assert desktop.probe_port(free) == ("studio", "e2e")
    assert "Uvicorn running" in (home / "logs" / "engine.log").read_text(encoding="utf-8")

    # A second launch finds it and starts nothing new.
    again = _run(root, env)
    assert "already running" in again.stdout
    assert len((home / "engines.txt").read_text().splitlines()) == 1


@runs_the_launcher
def test_the_shipped_launcher_reports_an_engine_that_dies(bundle):
    root, env, calls, home = bundle
    (port,) = _free_block(1)
    env["INOX_HYDRA_PORT"] = str(port)
    env["FAKE_ENGINE"] = "die"

    result = _run(root, env)
    assert result.returncode == desktop.LAUNCH_FAILED
    assert "stopped while it was starting" in result.stdout
    assert "the engine could not start" in result.stdout
    assert str(home / "logs" / "engine.log") in result.stdout
    assert not calls.exists(), "a window was opened onto an engine that is not there"


@runs_the_launcher
def test_the_shipped_launcher_refuses_a_bundle_without_its_python(bundle):
    root, env, calls, _ = bundle
    os.remove(root / "runtime" / "bin" / "python3")
    result = _run(root, env)
    assert result.returncode == 1
    assert "bundled Python is missing" in result.stdout
