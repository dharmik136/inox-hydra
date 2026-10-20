"""
The release gate passes the studio's own security gate. [INS-01]

tools/smoke_portable.py is the last check before a portable ZIP and latest.json
are published. It drove the app with a bare TestClient, whose Host is
"testserver" and which carries no token, so the loopback and token gate in
security.py refused every request with 403 and no release could pass it.
verify_package.py was fixed for this in 5fd6fa6; the smoke body was not.

The body is run here exactly as the release runs it, by a separate
interpreter, against the source tree instead of an extracted artifact, so a
change to the gate that breaks the smoke goes red on every commit rather than
on a tag. Outbound connections are refused first, as the sandbox does.

Strict Invariants:
- Zero em-dashes.
"""

import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

import smoke_portable  # noqa: E402

# Refuses every connection that does not stay on this machine, before the app
# is imported, so the smoke cannot reach an AI, image or update service.
SOCKET_GUARD = r'''
import socket as _socket
_real_connect = _socket.socket.connect
def _guarded(self, address):
    host = str(address[0] if isinstance(address, tuple) else address)
    if self.family in (_socket.AF_INET, _socket.AF_INET6) and not host.startswith(("127.", "::1", "localhost")):
        raise ConnectionRefusedError("test: outbound connection refused")
    return _real_connect(self, address)
_socket.socket.connect = _guarded
'''

needs_the_ui = pytest.mark.skipif(
    not os.path.isfile(os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")),
    reason="the interface is not built in this checkout (npm --prefix studio/ui run build)",
)


@needs_the_ui
def test_the_smoke_body_passes_against_the_source_tree(tmp_path):
    script = tmp_path / "smoke.py"
    script.write_text(SOCKET_GUARD + smoke_portable.SMOKE, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("INOX_")}
    env["INOX_SMOKE_SOURCE_TREE"] = "1"
    env["PYTHONPATH"] = REPO_ROOT
    result = subprocess.run(
        [sys.executable, str(script)], cwd=REPO_ROOT, env=env,
        capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, result.stdout + result.stderr[-3000:]
    assert "SMOKE PASSED" in result.stdout
    assert "403" not in result.stdout


def test_the_smoke_client_is_built_as_a_real_caller_is():
    """The same construction verify_package uses: loopback origin and the token."""
    assert 'base_url="http://127.0.0.1:8000"' in smoke_portable.SMOKE
    assert "sec.TOKEN_HEADER: sec.get_or_create_token()" in smoke_portable.SMOKE
    assert "TestClient(m.app) as c" not in smoke_portable.SMOKE


def test_the_smoke_finds_the_interpreter_on_every_platform(tmp_path):
    windows = tmp_path / "win"
    (windows / "runtime").mkdir(parents=True)
    (windows / "runtime" / "python.exe").write_bytes(b"")
    unix = tmp_path / "unix"
    (unix / "runtime" / "bin").mkdir(parents=True)
    (unix / "runtime" / "bin" / "python3").write_bytes(b"")

    assert smoke_portable.find_interpreter(str(windows)).endswith("python.exe")
    assert smoke_portable.find_interpreter(str(unix)).endswith(os.path.join("bin", "python3"))
    with pytest.raises(SystemExit, match="no embedded interpreter"):
        smoke_portable.find_interpreter(str(tmp_path / "empty"))
