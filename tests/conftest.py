"""
Global Test Session Sandbox: Guaranteed State Isolation for Tests.
=================================================================
Prevents any test in this suite from mutating the user's live database or assets.

When tests run, application state is redirected to a temporary INOX_HYDRA_HOME.
At session start, the sandboxed database is initialized and seeded with baseline
test fixtures so tests run against clean, predictable data.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import importlib
import os
import shutil
import subprocess
import sys
import tempfile
import types
import pytest

# Ensure studio/backend and studio are importable
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_BACKEND_DIR = os.path.join(_REPO_ROOT, "studio", "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ---------------------------------------------------------------------------
# No test reaches the network
#
# The studio's AI, image, update and LinkedIn paths each have their own HTTP
# client, and a test that forgets to patch one of them sends a real request:
# an image test once called the public image generator from every run. So for
# the whole session every socket connection that is not to the loopback
# interface, and every name lookup for a host that is not loopback, is refused
# before it is made. Installed at import, before any test module loads a
# client, so nothing can hold a reference to the unguarded functions.
# ---------------------------------------------------------------------------
import socket as _socket

_LOOPBACK = ("127.", "::1", "localhost", "0.0.0.0")
_real_connect = _socket.socket.connect
_real_connect_ex = _socket.socket.connect_ex
_real_create_connection = _socket.create_connection
_real_getaddrinfo = _socket.getaddrinfo


class NetworkRefusedInTests(ConnectionRefusedError):
    """A test tried to reach a host that is not this machine."""


# Every refusal is recorded as well as raised, because the code under test
# usually catches a connection error and carries on, so a test that reached
# for the network would otherwise still pass. The autouse fixture below fails
# such a test by name, with the host it tried.
_refused_hosts = []


def _refuse(host, what):
    _refused_hosts.append(host)
    if what == "lookup":
        return _socket.gaierror(f"test suite: name lookup for {host} refused")
    return NetworkRefusedInTests(f"test suite: outbound connection to {host} refused")


def _host_of(address):
    return str(address[0] if isinstance(address, tuple) else address)


def _is_loopback(host):
    return host.startswith(_LOOPBACK)


def _guarded_connect(self, address):
    if self.family in (_socket.AF_INET, _socket.AF_INET6) and not _is_loopback(_host_of(address)):
        raise _refuse(_host_of(address), "connect")
    return _real_connect(self, address)


def _guarded_connect_ex(self, address):
    if self.family in (_socket.AF_INET, _socket.AF_INET6) and not _is_loopback(_host_of(address)):
        raise _refuse(_host_of(address), "connect")
    return _real_connect_ex(self, address)


def _guarded_create_connection(address, *args, **kwargs):
    if not _is_loopback(_host_of(address)):
        raise _refuse(_host_of(address), "connect")
    return _real_create_connection(address, *args, **kwargs)


def _guarded_getaddrinfo(host, *args, **kwargs):
    name = host.decode() if isinstance(host, bytes) else str(host or "")
    if name and not _is_loopback(name):
        raise _refuse(name, "lookup")
    return _real_getaddrinfo(host, *args, **kwargs)


_socket.socket.connect = _guarded_connect
_socket.socket.connect_ex = _guarded_connect_ex
_socket.create_connection = _guarded_create_connection
_socket.getaddrinfo = _guarded_getaddrinfo


@pytest.fixture(autouse=True)
def no_network(request):
    """
    Fails a test that tried to leave this machine, even if the code swallowed
    the refusal. A test whose point is the offline machine says so with
    @pytest.mark.simulates_offline: its attempts are still refused, and only
    the failure is waived.
    """
    already = len(_refused_hosts)
    yield
    tried = _refused_hosts[already:]
    if tried and request.node.get_closest_marker("simulates_offline") is None:
        pytest.fail(
            "this test tried to reach the network ("
            + ", ".join(sorted(set(tried)))
            + "); stub the client instead",
            pytrace=False,
        )


# Track the sandboxed home created for the pytest session
_SESSION_TEST_HOME = None

# Configure INOX_HYDRA_HOME immediately upon module import (before test files are collected/imported)
# if the environment does not already specify an override.
if "INOX_HYDRA_HOME" not in os.environ:
    _SESSION_TEST_HOME = tempfile.mkdtemp(prefix="inox_pytest_sandbox_")
    os.environ["INOX_HYDRA_HOME"] = _SESSION_TEST_HOME

# Fabricated analytics and demographics are opt-in and OFF by default, so a real
# install never shows a creator numbers it invented. The suite needs predictable
# fixtures to assert against, so the sandbox opts in explicitly. Any test that
# cares about the un-seeded state must clear this and re-seed for itself.
os.environ.setdefault("INOX_DEMO_DATA", "1")


def pytest_configure(config):
    """Initializes and seeds the sandboxed database before test execution."""
    config.addinivalue_line(
        "markers",
        "simulates_offline: the test relies on the suite refusing the network, so a refused attempt is expected",
    )
    if _SESSION_TEST_HOME and os.environ.get("INOX_HYDRA_HOME") == _SESSION_TEST_HOME:
        try:
            from database import init_db, seed_initial_data
            init_db()
            seed_initial_data()
        except Exception as e:
            sys.stderr.write(f"Notice: Sandbox database bootstrap encountered: {e}\n")


# ---------------------------------------------------------------------------
# Authenticated test client
#
# The API requires a loopback Host, a permitted Origin and a valid token on
# every call. The suite has to satisfy all three the same way a real caller
# does, because the alternative is a bypass inside the application that exists
# only for tests, and a bypass that ships is a bypass an attacker can use.
#
# So instead of weakening the server, every TestClient is built pointing at the
# real loopback origin and carrying the real token. A test that wants to prove
# the boundary holds simply overrides these per request.
# ---------------------------------------------------------------------------
def _install_authenticated_test_client():
    from fastapi.testclient import TestClient
    from security import get_or_create_token, TOKEN_HEADER

    original_init = TestClient.__init__

    def patched_init(self, *args, **kwargs):
        # Host must name loopback or the rebinding check refuses the request.
        kwargs.setdefault("base_url", "http://127.0.0.1:8000")
        headers = dict(kwargs.get("headers") or {})
        headers.setdefault(TOKEN_HEADER, get_or_create_token())
        kwargs["headers"] = headers
        original_init(self, *args, **kwargs)

    if not getattr(TestClient, "_inox_auth_patched", False):
        TestClient.__init__ = patched_init
        TestClient._inox_auth_patched = True


_install_authenticated_test_client()


# ---------------------------------------------------------------------------
# No test opens a real browser
#
# Routes such as /api/v1/self/sync-all launch the bridge browser, and a test
# that calls them on a workstation with Brave installed started a real Brave
# window, pointed at the creator's live studio, on every run, and left it open.
# Its unpacked extension came from this checkout, so it was also the window in
# which Reload failed on a stray __pycache__.
#
# The launcher reaches the operating system only through its own `subprocess`
# name, so every loaded copy of it gets a stand-in whose Popen records the
# command line and starts nothing. Everything else is the real module. A test
# that inspects the command line still patches Popen itself, and that patch
# lands on the stand-in for the length of the test.
# ---------------------------------------------------------------------------
class _NoRealBrowser(types.ModuleType):
    def __init__(self):
        super().__init__("subprocess")
        self.launched = []

        def Popen(args, *_args, **_kwargs):
            self.launched.append(list(args))
            return types.SimpleNamespace(pid=0, returncode=None, poll=lambda: None)

        self.Popen = Popen

    def __getattr__(self, name):
        return getattr(subprocess, name)


@pytest.fixture(autouse=True)
def no_real_browser(monkeypatch):
    for name in ("browser_launcher", "studio.backend.browser_launcher"):
        importlib.import_module(name)
    stand_in = _NoRealBrowser()
    for name, module in list(sys.modules.items()):
        if name.rsplit(".", 1)[-1] == "browser_launcher" and module is not None:
            monkeypatch.setattr(module, "subprocess", stand_in)
    return stand_in


def pytest_unconfigure(config):
    """Cleans up the temporary session test sandbox."""
    global _SESSION_TEST_HOME
    if _SESSION_TEST_HOME and os.path.isdir(_SESSION_TEST_HOME):
        shutil.rmtree(_SESSION_TEST_HOME, ignore_errors=True)
        _SESSION_TEST_HOME = None


# ---------------------------------------------------------------------------
# What counts as this repository's own content
#
# Several hygiene scans walk the working tree. That is right for studio/ and
# wrong everywhere else, and the asymmetry is load bearing in both directions.
#
# copy_application copies studio/ from the working tree rather than from the
# index, so an untracked file there does reach a user and has to be scanned.
# That is the lesson a ten file credential leak taught this project once
# already.
#
# Nothing outside studio/ ships. The portable build copies only studio/, and
# the wheel declares only studio packages. So an unrelated scratch script left
# in tools/ was failing a check named for shipped files, while CI, which
# clones, stayed green. A suite that is red for a reason that cannot affect a
# user trains people to read red as normal, which costs more than the noise it
# saves.
#
# Shared here rather than copied into each test file, because two copies of a
# rule about what to inspect is how one of them quietly stops matching.
# ---------------------------------------------------------------------------
def _git_tracked_paths(repo_root):
    """Every path git knows about, or None when git cannot answer."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "ls-files"], cwd=repo_root,
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return None
        return {
            line.replace("/", os.sep)
            for line in result.stdout.splitlines()
            if line.strip()
        }
    except Exception:
        return None


def is_repository_content(rel_path, repo_root, _cache={}):
    """
    True for anything that ships, or that git is tracking.

    Everything under studio/ counts whether tracked or not, because the build
    copies that directory from disk. Elsewhere, tracked is the test. When git
    is unavailable the answer is True, so a checkout without git scans more
    rather than less.
    """
    if repo_root not in _cache:
        _cache[repo_root] = _git_tracked_paths(repo_root)
    tracked = _cache[repo_root]

    normalised = str(rel_path).replace("/", os.sep)
    if normalised.startswith("studio" + os.sep):
        return True
    if tracked is None:
        return True
    return normalised in tracked


# The creator a test's captured engagement belongs to.
#
# A lead is someone who engaged with the creator's own post, and the studio
# can only tell whose post it is once the creator has confirmed who they are
# (onboarding.engagement_gate). Tests of lead capture, attribution and DMs
# therefore start from a confirmed creator and say the post is theirs, which is
# the state a real install is in after Setup.
TEST_CREATOR_VANITY = "studio-test-creator"


@pytest.fixture
def confirmed_creator():
    from database import get_db

    conn = get_db()
    try:
        with conn:
            conn.execute("DELETE FROM creator_identity")
            conn.execute(
                "INSERT INTO creator_identity (id, vanity, display_name, confirmed_at) "
                "VALUES (1, ?, 'Studio Test Creator', '2026-09-27T00:00:00+00:00')",
                (TEST_CREATOR_VANITY,),
            )
    finally:
        conn.close()
    yield TEST_CREATOR_VANITY
    conn = get_db()
    try:
        with conn:
            conn.execute("DELETE FROM creator_identity")
    finally:
        conn.close()
