"""
Tests for macOS and Linux platform support.
===========================================

Validates the cross-platform capabilities added for macOS and Linux:
1. ICNS generation with standard and retina layers and Linux PNG icon assets.
2. Tauri configuration bundle targets and icon declarations.
3. Cross-platform runtime staging and path file resolution.
4. macOS Keychain and Linux Secret Service vault backends with honest fallback.
5. macOS LaunchAgent and Linux XDG autostart lifecycles with honest state reporting.
6. CI matrix configuration across Windows, macOS, and Linux runners.
7. Strict Zero Em-Dash invariant across all modified and created files.
"""

import io
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile

import pytest
from PIL import Image

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TAURI = os.path.join(REPO_ROOT, "desktop", "src-tauri")
ICONS_DIR = os.path.join(TAURI, "icons")

sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
import desktop
import vault


def _read(*parts):
    return io.open(os.path.join(*parts), encoding="utf-8").read()


# ---------------------------------------------------------------------------
# 1. Icons: macOS ICNS and Linux PNGs
# ---------------------------------------------------------------------------

def test_macos_icns_icon_exists_and_has_valid_header():
    """
    macOS application bundles require icon.icns. Without it, macOS displays
    a generic default executable icon or fails bundle creation.
    """
    icns_path = os.path.join(ICONS_DIR, "icon.icns")
    assert os.path.isfile(icns_path), "icon.icns is missing from desktop/src-tauri/icons"

    with open(icns_path, "rb") as f:
        header = f.read(4)
    assert header == b"icns", f"icon.icns must start with magic bytes b'icns', got {header!r}"


def test_linux_png_icons_exist_with_required_dimensions():
    """
    Linux desktop environments (GNOME, KDE) expect fixed icon resolutions
    in the hicolor theme hierarchy. Missing any size causes fuzzy scaling.
    """
    expected_sizes = {
        "32x32.png": (32, 32),
        "64x64.png": (64, 64),
        "128x128.png": (128, 128),
        "128x128@2x.png": (256, 256),
        "256x256.png": (256, 256),
        "512x512.png": (512, 512),
        "icon.png": (512, 512),
    }
    for filename, expected_dim in expected_sizes.items():
        icon_path = os.path.join(ICONS_DIR, filename)
        assert os.path.isfile(icon_path), f"Linux icon {filename} is missing"
        with Image.open(icon_path) as img:
            assert img.size == expected_dim, (
                f"Icon {filename} has size {img.size}, expected {expected_dim}"
            )


def test_icns_generation_is_reproducible():
    """
    Two runs of the icon generator must produce bit-for-bit identical output.
    Non-deterministic output causes spurious binary git diffs on every build.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "generate_icons", os.path.join(REPO_ROOT, "tools", "generate_icons.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    first = module.draw_mark(512).tobytes()
    second = module.draw_mark(512).tobytes()
    assert first == second, "draw_mark produced non-deterministic pixel data"


# ---------------------------------------------------------------------------
# 2. Bundle targets in tauri.conf.json
# ---------------------------------------------------------------------------

def test_tauri_bundle_targets_include_macos_and_linux():
    """
    Tauri bundle targets must include macOS (app, dmg) and Linux (deb, appimage)
    alongside Windows nsis, or builds on Unix produce no distributable packages.
    """
    config = json.loads(_read(TAURI, "tauri.conf.json"))
    targets = config.get("bundle", {}).get("targets", [])
    for expected in ("nsis", "app", "dmg", "deb", "appimage"):
        assert expected in targets, f"Tauri bundle target {expected} is missing from tauri.conf.json"


def test_tauri_bundle_icons_include_icns_and_pngs():
    """
    Tauri requires icon.icns for macOS and PNG icons for Linux packages.
    """
    config = json.loads(_read(TAURI, "tauri.conf.json"))
    icons = config.get("bundle", {}).get("icon", [])
    assert "icons/icon.icns" in icons, "icons/icon.icns missing from bundle.icon"
    assert "icons/icon.png" in icons, "icons/icon.png missing from bundle.icon"


# ---------------------------------------------------------------------------
# 3. Payload staging and runtime configuration
# ---------------------------------------------------------------------------

def test_build_portable_defines_cross_platform_path_staging():
    """
    Windows embeddable Python uses python3XX._pth next to python.exe, while
    macOS and Linux isolated runtimes require site-packages/inox_hydra.pth.
    Both must be supported without breaking the Windows layout.
    """
    portable_src = _read(REPO_ROOT, "tools", "build_portable.py")
    stage_src = _read(REPO_ROOT, "tools", "stage_desktop_payload.py")

    assert "inox_hydra.pth" in portable_src
    assert "sitecustomize.py" in portable_src
    assert "get_runtime_interpreter" in portable_src
    assert "fetch_runtime" in stage_src


def test_backend_rs_locates_unix_python_and_engine_log():
    """
    The Rust backend runner must locate bin/python3 on Unix and python.exe
    on Windows, and write engine logs to platform-appropriate application support
    or XDG data directories rather than hardcoded Windows %LOCALAPPDATA%.
    """
    backend_rs = _read(TAURI, "src", "backend.rs")
    assert "bin/python3" in backend_rs or "python3" in backend_rs
    assert "Application Support" in backend_rs
    assert "XDG_DATA_HOME" in backend_rs


# ---------------------------------------------------------------------------
# 4. Vault and keystores
# ---------------------------------------------------------------------------

def test_vault_reports_honest_backend_name():
    """
    get_vault_backend() must return the real active backend name and not
    claim DPAPI or macOS Keychain when running on an unsupported platform.
    """
    backend_name = vault.get_vault_backend()
    assert backend_name in ("DPAPI", "KEYCHAIN", "SECRET_SERVICE", "FILE_KEY")


def test_vault_reports_no_false_hardware_backing():
    """
    The vault status must never claim hardware backing that is not present.
    """
    status = vault.get_vault_status()
    assert status["hardware_backed"] is False
    assert "backend" in status
    assert "keystore_available" in status


def test_vault_macos_keychain_get_and_set_invocations(monkeypatch):
    """
    macOS Keychain integration must invoke /usr/bin/security with the configured
    service (InoxHydra.LinkedInStudio) and account (vault_master_key) arguments.
    """
    commands_executed = []
    test_key = b"0123456789abcdef0123456789abcdef"

    def fake_run(cmd, *args, **kwargs):
        commands_executed.append(list(cmd))
        if "find-generic-password" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=test_key.hex() + "\n", stderr="")
        if "add-generic-password" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="unknown command")

    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(subprocess, "run", fake_run)

    # Test reading
    key = vault._keychain_read()
    assert key == test_key
    find_cmd = commands_executed[-1]
    assert find_cmd[0] == "security"
    assert "find-generic-password" in find_cmd
    assert "-s" in find_cmd and vault._KEYCHAIN_SERVICE in find_cmd
    assert "-a" in find_cmd and vault._KEYCHAIN_ACCOUNT in find_cmd

    # Test writing
    stored = vault._keychain_write(test_key)
    assert stored is True
    add_cmd = commands_executed[-1]
    assert add_cmd[0] == "security"
    assert "add-generic-password" in add_cmd
    assert "-U" in add_cmd
    assert "-s" in add_cmd and vault._KEYCHAIN_SERVICE in add_cmd
    assert "-a" in add_cmd and vault._KEYCHAIN_ACCOUNT in add_cmd


def test_vault_linux_secret_service_get_and_set_invocations(monkeypatch):
    """
    Linux Secret Service integration must invoke secret-tool with the configured
    service (InoxHydra.LinkedInStudio) and account (vault_master_key) attributes.
    """
    commands_executed = []
    test_key = b"aabbccddeeff00112233445566778899"

    def fake_run(cmd, *args, **kwargs):
        commands_executed.append(list(cmd))
        if "lookup" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=test_key.hex() + "\n", stderr="")
        if "store" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="unknown command")

    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(subprocess, "run", fake_run)

    # Test reading
    key = vault._secret_tool_read()
    assert key == test_key
    lookup_cmd = commands_executed[-1]
    assert lookup_cmd[0] == "secret-tool"
    assert "lookup" in lookup_cmd
    assert "service" in lookup_cmd and vault._KEYCHAIN_SERVICE in lookup_cmd
    assert "account" in lookup_cmd and vault._KEYCHAIN_ACCOUNT in lookup_cmd

    # Test writing
    stored = vault._secret_tool_write(test_key)
    assert stored is True
    store_cmd = commands_executed[-1]
    assert store_cmd[0] == "secret-tool"
    assert "store" in store_cmd
    assert "--label=LinkedIn Studio Vault" in store_cmd
    assert "service" in store_cmd and vault._KEYCHAIN_SERVICE in store_cmd
    assert "account" in store_cmd and vault._KEYCHAIN_ACCOUNT in store_cmd


def test_vault_falls_back_to_file_key_when_keystores_fail(monkeypatch):
    """
    When platform keystores fail (tool missing or command exits non-zero),
    vault must fall back to the counter-mode encrypted file key and report
    FILE_KEY honestly.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        monkeypatch.setattr(vault, "_keychain_read", lambda: None)
        monkeypatch.setattr(vault, "_keychain_write", lambda k: False)
        monkeypatch.setattr(vault, "_secret_tool_read", lambda: None)
        monkeypatch.setattr(vault, "_secret_tool_write", lambda k: False)
        monkeypatch.setattr(shutil, "which", lambda name: None)
        monkeypatch.setattr(platform, "system", lambda: "Darwin")

        fake_key_path = os.path.join(temp_dir, "vault_key")
        monkeypatch.setattr(vault, "_file_key", lambda: b"F" * 32)

        key = vault._local_key()
        assert len(key) == 32
        assert vault.get_vault_backend() == "FILE_KEY"


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS Keychain is live on macOS only")
def test_vault_live_macos_keychain():
    """
    Live test of macOS Keychain. Only executes on macOS runners.
    """
    key = vault._local_key()
    assert len(key) == 32
    status = vault.get_vault_status()
    assert status["backend"] in ("KEYCHAIN", "FILE_KEY")


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux Secret Service is live on Linux only")
def test_vault_live_linux_secret_service():
    """
    Live test of Linux Secret Service. Only executes on Linux runners.
    """
    key = vault._local_key()
    assert len(key) == 32
    status = vault.get_vault_status()
    assert status["backend"] in ("SECRET_SERVICE", "FILE_KEY")


# ---------------------------------------------------------------------------
# 5. Autostart: macOS LaunchAgent and Linux XDG
# ---------------------------------------------------------------------------

def test_macos_launch_agent_plist_generation(monkeypatch):
    """
    macOS autostart writes a valid launchd XML plist to
    ~/Library/LaunchAgents/com.inoxhydra.linkedinstudio.plist.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        monkeypatch.setattr(os.path, "expanduser", lambda path: path.replace("~", temp_dir))
        monkeypatch.setattr(sys, "platform", "darwin")

        plist_path = desktop.get_startup_shortcut_path()
        assert plist_path.endswith("com.inoxhydra.linkedinstudio.plist")
        assert "LaunchAgents" in plist_path

        # Initially off
        assert desktop.is_autostart_enabled() is False

        # Enable autostart
        result = desktop.enable_autostart()
        assert result["enabled"] is True
        assert os.path.isfile(plist_path)

        # Parse plist to verify structure
        with open(plist_path, "rb") as f:
            data = plistlib.load(f)
        assert data["Label"] == "com.inoxhydra.linkedinstudio"
        assert data["RunAtLoad"] is True
        assert len(data["ProgramArguments"]) >= 1

        # Verify enabled state
        assert desktop.is_autostart_enabled() is True

        # Disable autostart
        disable_result = desktop.disable_autostart()
        assert disable_result["removed"] is True
        assert not os.path.exists(plist_path)
        assert desktop.is_autostart_enabled() is False


def test_linux_xdg_autostart_desktop_generation(monkeypatch):
    """
    Linux autostart writes an XDG desktop entry to
    ~/.config/autostart/inox-hydra.desktop.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        autostart_dir = os.path.join(temp_dir, "autostart")
        monkeypatch.setattr(desktop, "get_startup_dir", lambda: autostart_dir)
        monkeypatch.setattr(sys, "platform", "linux")

        desktop_path = desktop.get_startup_shortcut_path()
        assert desktop_path.endswith("inox-hydra.desktop")

        # Initially off
        assert desktop.is_autostart_enabled() is False

        # Enable autostart
        result = desktop.enable_autostart()
        assert result["enabled"] is True
        assert os.path.isfile(desktop_path)

        # Verify desktop file content
        content = _read(desktop_path)
        assert "[Desktop Entry]" in content
        assert "Type=Application" in content
        assert "Name=LinkedIn Studio" in content
        assert "Exec=" in content
        assert "Terminal=false" in content

        # Verify enabled state
        assert desktop.is_autostart_enabled() is True

        # Disable autostart
        disable_result = desktop.disable_autostart()
        assert disable_result["removed"] is True
        assert not os.path.exists(desktop_path)
        assert desktop.is_autostart_enabled() is False


def test_autostart_reports_failure_honestly_when_write_fails(monkeypatch):
    """
    If writing the autostart configuration fails, enable_autostart must
    report enabled: False and is_autostart_enabled must return False.
    It must never report success for an unwritten configuration.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        monkeypatch.setattr(os.path, "expanduser", lambda path: path.replace("~", temp_dir))
        monkeypatch.setattr(sys, "platform", "darwin")

        def failing_dump(*args, **kwargs):
            raise OSError("Permission denied")

        monkeypatch.setattr(plistlib, "dump", failing_dump)

        result = desktop.enable_autostart()
        assert result["enabled"] is False
        assert "cannot write launchagent plist" in result["reason"].lower()
        assert desktop.is_autostart_enabled() is False


@pytest.mark.skipif(sys.platform != "darwin", reason="LaunchAgent autostart is live on macOS only")
def test_autostart_live_macos():
    """
    Live test of autostart lifecycle on macOS.
    """
    was_enabled = desktop.is_autostart_enabled()
    try:
        res = desktop.enable_autostart()
        assert res["enabled"] is True
        assert desktop.is_autostart_enabled() is True
    finally:
        if not was_enabled:
            desktop.disable_autostart()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="XDG autostart is live on Linux only")
def test_autostart_live_linux():
    """
    Live test of autostart lifecycle on Linux.
    """
    was_enabled = desktop.is_autostart_enabled()
    try:
        res = desktop.enable_autostart()
        assert res["enabled"] is True
        assert desktop.is_autostart_enabled() is True
    finally:
        if not was_enabled:
            desktop.disable_autostart()


# ---------------------------------------------------------------------------
# 6. CI workflow configuration
# ---------------------------------------------------------------------------

def test_ci_workflow_has_matrix_for_windows_macos_linux():
    """
    desktop.yml must define a matrix across windows-latest, macos-latest,
    and ubuntu-latest, and guard signing to Windows.
    """
    workflow = _read(REPO_ROOT, ".github", "workflows", "desktop.yml")
    assert "windows-latest" in workflow
    assert "macos-latest" in workflow
    assert "ubuntu-latest" in workflow
    assert "libwebkit2gtk-4.1-dev" in workflow
    assert "runner.os == 'Windows'" in workflow


# ---------------------------------------------------------------------------
# 7. Zero Em-Dash invariant check
# ---------------------------------------------------------------------------

def test_all_platform_files_hold_zero_em_dash_invariant():
    """
    House Rule 1: Zero em-dashes (U+2014) anywhere in code, comments,
    docstrings, or documentation across all modified and created files.
    """
    targets = [
        os.path.join(REPO_ROOT, "tools", "generate_icons.py"),
        os.path.join(REPO_ROOT, "tools", "build_portable.py"),
        os.path.join(REPO_ROOT, "tools", "stage_desktop_payload.py"),
        os.path.join(TAURI, "tauri.conf.json"),
        os.path.join(TAURI, "src", "backend.rs"),
        os.path.join(REPO_ROOT, "studio", "backend", "vault.py"),
        os.path.join(REPO_ROOT, "studio", "backend", "desktop.py"),
        os.path.join(REPO_ROOT, ".github", "workflows", "desktop.yml"),
        os.path.join(REPO_ROOT, "docs", "DESKTOP_SHELL.md"),
        os.path.abspath(__file__),
    ]
    # MACOS_LINUX_NOTES.md was in this list and is deliberately not in the
    # repository. It was a handoff note from the agent that wrote this work,
    # folded into the commit message and deleted, so asserting it exists made
    # the suite depend on a scratch file rather than on the product. A test
    # that pins the presence of a working note fails the moment the work is
    # tidied up, which is exactly what happened.
    for path in targets:
        assert os.path.isfile(path), f"Target file does not exist: {path}"
        content = _read(path)
        assert chr(8212) not in content, (
            f"File {os.path.relpath(path, REPO_ROOT)} contains an em-dash (U+2014)"
        )
