"""
Tests for the native desktop shell.
===================================

These exist because of a specific gap: the shell is Rust, it is built on CI,
and no contributor is expected to install a multi gigabyte MSVC toolchain to
change a line of Python. That means the compiler is not available to catch
mistakes locally, and a mismatch between the Rust shell and the Python backend
would surface only after a tagged release.

So everything checkable without a compiler is checked here: the port both sides
agree on, the paths the shell will look for, the icon set the bundler demands,
the payload layout the interpreter's path file depends on, and the invariants
that keep user state out of the install directory.

What these cannot do is prove the shell compiles or runs. That is the CI
workflow's job, and the trade is deliberate.

Validates:
1. The shell and the backend agree on host, port and health route.
2. The Tauri config is coherent and points at files that exist.
3. The bundled payload layout matches what the path file resolves.
4. Version agreement across every surface that states one.
5. The shell never kills a backend it did not start.
6. Close hides the window rather than stopping the scheduler.
7. Strict Zero Em-Dash invariant.
"""

import io
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DESKTOP = os.path.join(REPO_ROOT, "desktop")
TAURI = os.path.join(DESKTOP, "src-tauri")


def read(*parts):
    return io.open(os.path.join(*parts), encoding="utf-8").read()


def live_python(source):
    """
    Source with comments and string literals removed.

    Needed because this codebase explains its decisions in prose next to the
    code implementing them. A file that documents why it does not use a tool
    naturally names that tool, and a naive substring check would read the
    explanation as the thing it rules out.
    """
    import tokenize
    from io import StringIO

    kept = []
    try:
        for token in tokenize.generate_tokens(StringIO(source).readline):
            if token.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            kept.append(token.string)
    except tokenize.TokenError:
        return source
    return " ".join(kept)


@pytest.fixture(scope="module")
def tauri_config():
    return json.loads(read(TAURI, "tauri.conf.json"))


@pytest.fixture(scope="module")
def backend_rs():
    return read(TAURI, "src", "backend.rs")


@pytest.fixture(scope="module")
def lib_rs():
    return read(TAURI, "src", "lib.rs")


# ---------------------------------------------------------------------------
# The two sides agree
# ---------------------------------------------------------------------------

def test_the_shell_and_the_backend_use_the_same_port(backend_rs):
    """
    The port is hardcoded in the browser extension, so a shell that chose a
    different one would silently break LinkedIn capture, which is the single
    thing the product cannot do without.
    """
    match = re.search(r"pub const STUDIO_PORT: u16 = (\d+);", backend_rs)
    assert match, "STUDIO_PORT is not declared in backend.rs"
    shell_port = int(match.group(1))

    app_py = read(REPO_ROOT, "studio", "backend", "app.py")
    assert f"port={shell_port}" in app_py, "the backend does not serve on the port the shell expects"

    extension = read(REPO_ROOT, "studio", "extension", "background.js")
    assert f"127.0.0.1:{shell_port}" in extension, "the extension targets a different port than the shell"


def test_the_shell_probes_a_route_that_exists(backend_rs):
    """
    A readiness probe against a route that answers 404 would report the studio
    as never ready, and the window would sit on the splash forever.
    """
    match = re.search(r"GET (/\S+) HTTP/1\.1", backend_rs)
    assert match, "backend.rs issues no recognisable probe request"
    probe_route = match.group(1)

    app_py = read(REPO_ROOT, "studio", "backend", "app.py")
    assert f'"{probe_route}"' in app_py, f"the shell probes {probe_route}, which the backend does not serve"


def test_the_probe_route_needs_no_token(backend_rs):
    """
    The shell has no token when it probes. If the route were authenticated it
    would answer 401, which the shell reads as not ready.
    """
    import security

    match = re.search(r"GET (/\S+) HTTP/1\.1", backend_rs)
    probe_route = match.group(1)
    assert security.request_is_exempt(probe_route), (
        f"{probe_route} requires a token, which the shell does not have at startup"
    )


def test_the_shell_checks_the_response_is_this_application(backend_rs):
    """
    An open port is not our port. Another program on 8000 must read as not
    ready rather than as a studio to point a window at.
    """
    assert "inox-hydra" in backend_rs
    assert "HTTP/1.1 200" in backend_rs


def test_readiness_is_waited_for_before_the_window_is_shown(lib_rs):
    """
    Binding a port finishes long before migrations do. Showing the window on
    bind means showing a connection error to a user who did nothing wrong.
    """
    assert "wait_until_ready" in lib_rs
    wait_at = lib_rs.index("wait_until_ready")
    show_at = lib_rs.index("window.show()", wait_at)
    assert show_at > wait_at, "the window is revealed before readiness is established"


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def test_the_shell_never_kills_a_backend_it_did_not_start(backend_rs):
    """
    A creator may already be running the studio from the tray with a scheduler
    mid post. Quitting the desktop window must not take that down.
    """
    assert "Attached" in backend_rs, "backend.rs does not model an already running server"

    attached_arm = backend_rs.index("Backend::Attached =>")
    tail = backend_rs[attached_arm: attached_arm + 400]
    assert "kill()" not in tail, "the attached branch terminates a backend it does not own"


def test_closing_the_window_hides_it(lib_rs):
    """
    The studio runs a scheduler. Clicking the X means get this off my screen,
    not stop posting, so close must hide and quitting must be explicit.
    """
    assert "CloseRequested" in lib_rs
    assert "prevent_close()" in lib_rs
    assert "window.hide()" in lib_rs


def test_a_second_launch_surfaces_the_first(lib_rs):
    assert "single_instance" in lib_rs
    assert "show_studio" in lib_rs


def test_the_backend_is_stopped_on_exit(lib_rs):
    assert "shutdown()" in lib_rs
    assert "RunEvent::Exit" in lib_rs


def test_no_console_window_flashes_on_launch(backend_rs):
    """
    Spawning without this gives the user a black box appearing behind their
    application at every start.
    """
    assert "CREATE_NO_WINDOW" in backend_rs
    assert "0x0800_0000" in backend_rs


# ---------------------------------------------------------------------------
# Bundle configuration
# ---------------------------------------------------------------------------

def test_the_config_parses_and_names_the_product(tauri_config):
    assert tauri_config["productName"] == "LinkedIn Studio"
    assert tauri_config["identifier"] == "com.inoxhydra.linkedinstudio"


def test_the_shell_version_tracks_the_product_version(tauri_config):
    """
    A shell reporting a different version than the backend it carries makes
    every support conversation start with a contradiction.
    """
    sys.path.insert(0, REPO_ROOT)
    from studio.__version__ import __version__

    assert tauri_config["version"] == __version__, (
        f"tauri.conf.json says {tauri_config['version']}, studio/__version__.py says {__version__}"
    )

    cargo = read(TAURI, "Cargo.toml")
    assert f'version = "{__version__}"' in cargo, "Cargo.toml disagrees with the product version"


def test_the_window_starts_hidden(tauri_config):
    """It is revealed once the backend answers, not before."""
    window = tauri_config["app"]["windows"][0]
    assert window["visible"] is False
    assert window["label"] == "studio"


def test_the_shell_label_matches_the_rust_constant(lib_rs, tauri_config):
    match = re.search(r'const MAIN_WINDOW: &str = "([^"]+)";', lib_rs)
    assert match, "MAIN_WINDOW is not declared"
    assert match.group(1) == tauri_config["app"]["windows"][0]["label"]


def test_every_configured_icon_exists(tauri_config):
    for relative in tauri_config["bundle"]["icon"]:
        assert os.path.isfile(os.path.join(TAURI, relative)), (
            f"the bundle references {relative}, which is not there. Run tools/generate_icons.py."
        )


def test_the_tray_is_built_once(lib_rs, tauri_config):
    """
    Declared in config AND built in setup gives either two tray icons or a
    duplicate-id failure that aborts startup, so exactly one of the two has to
    own it. The Rust does, because it needs to attach menu and click handlers.
    """
    assert "trayIcon" not in tauri_config["app"], (
        "the declarative tray is back; Tauri instantiates it automatically and "
        "build_tray would then be a second registration of the same id"
    )
    assert "TrayIconBuilder::with_id" in lib_rs
    # It borrows the bundle icon rather than naming a second path that could
    # drift from the one the installer ships.
    assert "default_window_icon()" in lib_rs


def test_the_installer_does_not_require_administrator(tauri_config):
    """
    A per user install keeps this out of Program Files, which matters because
    the product's argument is that the user owns what runs on their machine.
    """
    assert tauri_config["bundle"]["windows"]["nsis"]["installMode"] == "currentUser"


def test_the_bundle_carries_the_python_payload(tauri_config):
    """
    The shell has no Python of its own. Without these three the installer
    produces an application that cannot start an engine.
    """
    resources = tauri_config["bundle"]["resources"]
    targets = set(resources.values())
    assert "runtime/" in targets
    assert "lib/" in targets
    assert "app/" in targets


def test_the_resource_layout_matches_what_the_path_file_resolves(tauri_config):
    """
    runtime/python3XX._pth resolves ..\\lib and ..\\app relative to itself, so
    the three directories have to be siblings once installed. Nesting them
    differently gives an interpreter that cannot import its own package.
    """
    resources = tauri_config["bundle"]["resources"]
    for source, destination in resources.items():
        assert destination.count("/") == 1 and destination.endswith("/"), (
            f"{source} is installed to {destination}, which is not a sibling of runtime/"
        )

    builder = read(REPO_ROOT, "tools", "build_portable.py")
    assert '"..\\\\lib"' in builder and '"..\\\\app"' in builder, (
        "build_portable no longer writes the path entries the shell layout assumes"
    )


def test_the_shell_looks_for_the_interpreter_where_the_bundle_puts_it(backend_rs, tauri_config):
    assert 'join("runtime")' in backend_rs
    assert '"python.exe"' in backend_rs
    assert "runtime/" in set(tauri_config["bundle"]["resources"].values())


# ---------------------------------------------------------------------------
# Staging and build
# ---------------------------------------------------------------------------

def test_the_payload_is_staged_from_the_portable_builder():
    """
    Two artifacts carrying different payloads are two products, and only one of
    them gets tested. The staging script reuses the builder rather than
    reimplementing it.
    """
    staging = read(REPO_ROOT, "tools", "stage_desktop_payload.py")
    assert "import build_portable" in staging
    for reused in ("fetch_runtime", "write_path_file", "vendor_dependencies", "copy_application"):
        assert f"build_portable.{reused}" in staging, f"{reused} is reimplemented instead of reused"


def test_staging_refuses_to_ship_a_data_directory():
    """
    Its absence is what makes user state resolve to the user profile. Shipping
    one would put drafts inside the install directory, where an update deletes
    them.
    """
    staging = read(REPO_ROOT, "tools", "stage_desktop_payload.py")
    assert 'os.path.join(app_dir, "studio", "data")' in staging
    assert "assert not os.path.exists" in staging


def test_pyinstaller_is_not_used():
    """
    The portable builder documents why: an unsigned PyInstaller bootloader
    trips antivirus heuristics and there is no channel to walk a stranger
    through a quarantine. The Tauri sidecar docs assume PyInstaller, and this
    project deliberately does not follow them.
    """
    staging = live_python(read(REPO_ROOT, "tools", "stage_desktop_payload.py"))
    assert "pyinstaller" not in staging.lower(), "the staging script invokes PyInstaller"

    requirements = read(REPO_ROOT, "requirements.txt")
    assert "pyinstaller" not in requirements.lower()

    config = json.loads(read(TAURI, "tauri.conf.json"))
    assert "externalBin" not in json.dumps(config), "externalBin is the PyInstaller sidecar path"


def test_the_workflow_builds_on_windows_and_verifies_the_payload():
    workflow = read(REPO_ROOT, ".github", "workflows", "desktop.yml")
    assert "runs-on: windows-latest" in workflow
    assert "stage_desktop_payload.py" in workflow
    assert "generate_icons.py" in workflow
    assert "Verify The Payload Layout" in workflow
    assert "if-no-files-found: error" in workflow


def test_the_workflow_says_when_signing_is_absent():
    """
    An unsigned installer trips SmartScreen. The build stays green without
    credentials so a fork can still produce an artifact, which makes it easy to
    not notice, so the log has to say so.
    """
    workflow = read(REPO_ROOT, ".github", "workflows", "desktop.yml")
    assert "SmartScreen" in workflow
    assert "AZURE_SIGNING_ENDPOINT" in workflow


def test_build_output_is_not_committed():
    ignored = read(REPO_ROOT, ".gitignore")
    assert "desktop/payload/" in ignored
    assert "desktop/src-tauri/target/" in ignored


# ---------------------------------------------------------------------------
# The splash
# ---------------------------------------------------------------------------

def test_the_splash_needs_no_network():
    """
    It is on screen precisely when something may already be failing. Anything
    it had to fetch would be one more thing that can fail there.
    """
    splash = read(DESKTOP, "ui", "index.html")
    assert "http://" not in splash.replace("http://127.0.0.1", "")
    assert "https://" not in splash
    assert "<img" not in splash


def test_the_splash_says_something_useful_when_the_wait_is_long():
    splash = read(DESKTOP, "ui", "index.html")
    assert "waiting-a-while" in splash
    assert "tray" in splash.lower()


def test_the_config_points_at_the_splash(tauri_config):
    dist = tauri_config["build"]["frontendDist"]
    resolved = os.path.normpath(os.path.join(TAURI, dist))
    assert os.path.isfile(os.path.join(resolved, "index.html")), (
        f"frontendDist is {dist}, which has no index.html"
    )


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------

def test_the_shell_holds_the_zero_em_dash_invariant():
    targets = [
        os.path.join(TAURI, "src", "lib.rs"),
        os.path.join(TAURI, "src", "backend.rs"),
        os.path.join(TAURI, "src", "main.rs"),
        os.path.join(DESKTOP, "ui", "index.html"),
        os.path.join(REPO_ROOT, "tools", "stage_desktop_payload.py"),
        os.path.join(REPO_ROOT, ".github", "workflows", "desktop.yml"),
    ]
    for path in targets:
        content = io.open(path, encoding="utf-8").read()
        # Never typed literally, or this file would break the rule it enforces.
        assert chr(8212) not in content, f"{os.path.basename(path)} contains an em-dash"

# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------

def test_signing_happens_before_the_installer_is_packaged():
    """
    NSIS embeds the application executable. Signing the finished artifacts
    would leave that embedded copy unsigned, so the signature has to be applied
    as Tauri produces each binary, which is what signCommand does.
    """
    workflow = read(REPO_ROOT, ".github", "workflows", "desktop.yml")
    assert "signCommand" in workflow
    assert "trusted-signing-cli" in workflow


def test_an_unsigned_build_says_so_rather_than_passing_quietly():
    workflow = read(REPO_ROOT, ".github", "workflows", "desktop.yml")
    assert "::warning title=Unsigned build::" in workflow
    assert "SmartScreen" in workflow


def test_a_build_that_only_looks_signed_fails():
    """
    The check that matters. A signCommand that silently did nothing, an expired
    certificate, or a credential without the signer role each produce a green
    build and an unsigned artifact. Windows is asked directly.
    """
    workflow = read(REPO_ROOT, ".github", "workflows", "desktop.yml")
    assert "Get-AuthenticodeSignature" in workflow
    assert "Refusing to publish a build that only looks signed" in workflow


def test_the_tracked_config_carries_no_sign_command():
    """
    A signCommand in tauri.conf.json would make every local build reach for a
    signing service that is not configured. The workflow writes it separately.
    """
    config = read(TAURI, "tauri.conf.json")
    assert "signCommand" not in config

    ignored = read(REPO_ROOT, ".gitignore")
    assert "desktop/signing.json" in ignored


def test_no_signing_secret_is_committed():
    """Credentials reach the signer through the environment, never a file."""
    workflow = read(REPO_ROOT, ".github", "workflows", "desktop.yml")
    for secret in ("AZURE_CLIENT_SECRET", "AZURE_TENANT_ID"):
        for line in workflow.splitlines():
            if secret in line and "secrets." not in line and not line.strip().startswith("#"):
                raise AssertionError(f"{secret} appears outside a secrets reference: {line.strip()}")

