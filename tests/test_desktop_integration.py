"""
Tests for desktop integration: the things that make this read as an application.
===============================================================================

The gap these close was not functional. The studio worked. It just presented as
a server on a port number: the generic Windows icon in the tray, no way to start
with the machine, nothing stopping a second copy from fighting the first for
port 8000, and no way for a browser to install it as an app.

Validates:
1. The icon exists, carries every size Windows asks for, and is not the
   generic placeholder.
2. Autostart is off by default, reversible, and reports failure honestly.
3. The single instance guard actually refuses a second holder.
4. The web app manifest satisfies the browser installability rules.
5. The service worker caches nothing.
6. The portable build ships the icon.
7. Strict Zero Em-Dash invariant.
"""

import io
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from app import app
import desktop

client = TestClient(app)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FRONTEND = os.path.join(REPO_ROOT, "studio", "frontend")


# ---------------------------------------------------------------------------
# The icon
# ---------------------------------------------------------------------------

def test_the_application_icon_exists():
    """
    Its absence is the single most visible difference between a product and a
    script somebody left running.
    """
    assert os.path.isfile(desktop.get_app_icon_path()), (
        "assets/inox_hydra.ico is missing. Run tools/generate_icons.py."
    )


def test_the_icon_carries_every_size_windows_asks_for():
    """
    The tray asks for a 16 pixel icon and the file dialog asks for 256. One
    frame scaled to both is blurry at one end, so all of them ship.
    """
    from PIL import Image

    with Image.open(desktop.get_app_icon_path()) as img:
        sizes = {size for size in img.info.get("sizes", set())}

    for expected in [(16, 16), (32, 32), (48, 48), (256, 256)]:
        assert expected in sizes, f"the icon has no {expected[0]} pixel frame, sizes present: {sorted(sizes)}"


def test_the_tray_no_longer_loads_the_generic_windows_icon():
    """
    studio_tray used to call LoadIconW(IDI_APPLICATION) unconditionally. The
    constant may remain as a fallback, but it must not be the only path.
    """
    source = io.open(os.path.join(REPO_ROOT, "studio_tray.py"), encoding="utf-8").read()
    assert "load_app_icon" in source
    assert "LoadImageW" in source, "the tray must load the .ico at the size the tray asks for"
    assert "inox_hydra.ico" in source


def test_the_tray_does_not_point_at_a_png():
    """
    The Win32 icon loader cannot read PNG. The old constant pointed at the
    extension's 48 pixel PNG, which is why the fallback always won.
    """
    source = io.open(os.path.join(REPO_ROOT, "studio_tray.py"), encoding="utf-8").read()
    assert "icon-48.png" not in source


# ---------------------------------------------------------------------------
# Autostart
# ---------------------------------------------------------------------------

def test_autostart_is_off_until_asked_for():
    """
    Software that silently adds itself to startup is what this product exists
    to replace, so the default has to be off.
    """
    state = client.get("/api/v1/desktop/integration").json()["desktop"]
    if state["autostart_enabled"]:
        pytest.skip("this machine has autostart enabled, so the default cannot be observed")
    assert state["autostart_enabled"] is False


def test_integration_reports_enough_to_render_the_setting_honestly():
    state = client.get("/api/v1/desktop/integration").json()["desktop"]
    for key in (
        "supported", "app_id", "icon_path", "icon_present",
        "autostart_enabled", "autostart_available", "startup_shortcut_path",
    ):
        assert key in state, f"the Settings screen cannot render without {key}"

    assert state["app_id"] == "InoxHydra.LinkedInStudio"
    assert state["icon_present"] is True


@pytest.mark.skipif(sys.platform != "win32", reason="the .lnk shortcut is the Windows autostart mechanism")
def test_the_startup_shortcut_lands_in_the_users_own_startup_folder():
    """
    A shortcut, not a registry key, so a person can find and delete it without
    a registry editor.

    Gated to Windows because get_startup_shortcut_path now answers per
    platform: a LaunchAgent plist on macOS and an XDG desktop entry on Linux,
    neither of which ends in .lnk. Those two are covered in
    test_macos_linux_support.py. Before the suite ran on more than one
    operating system this assertion was simply always true.
    """
    path = desktop.get_startup_shortcut_path()
    assert path.lower().endswith(".lnk")
    assert "startup" in path.lower()
    assert "Microsoft" in path


@pytest.mark.skipif(sys.platform != "win32", reason="autostart is implemented for Windows only")
def test_autostart_round_trips():
    """
    On, then off, with the state read back from disk each time rather than
    assumed from the call.
    """
    was_enabled = desktop.is_autostart_enabled()
    try:
        result = desktop.enable_autostart()
        assert result["enabled"] is True, f"could not enable autostart: {result.get('reason')}"
        assert os.path.isfile(desktop.get_startup_shortcut_path())
        assert desktop.is_autostart_enabled() is True

        off = desktop.disable_autostart()
        assert off["enabled"] is False
        assert not os.path.isfile(desktop.get_startup_shortcut_path())
    finally:
        if was_enabled:
            desktop.enable_autostart()
        else:
            desktop.disable_autostart()


@pytest.mark.skipif(sys.platform != "win32", reason="autostart is implemented for Windows only")
def test_the_api_reports_the_state_it_achieved_not_the_one_requested():
    """
    A switch that says On while nothing happens at login is worse than one that
    refuses and says why, so the response carries the state read back.
    """
    was_enabled = desktop.is_autostart_enabled()
    try:
        res = client.post("/api/v1/desktop/autostart", json={"enabled": True})
        assert res.status_code == 200
        body = res.json()
        assert body["desktop"]["autostart_enabled"] == os.path.isfile(
            desktop.get_startup_shortcut_path()
        )
    finally:
        if not was_enabled:
            desktop.disable_autostart()


def test_disabling_when_nothing_is_there_is_not_an_error():
    was_enabled = desktop.is_autostart_enabled()
    if was_enabled:
        pytest.skip("autostart is on for this machine")
    result = desktop.disable_autostart()
    assert result["enabled"] is False
    assert result["removed"] is False


# ---------------------------------------------------------------------------
# Single instance
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform != "win32", reason="the mutex is a Win32 primitive")
def test_a_second_instance_is_refused():
    """
    Without this, a second launch starts a second uvicorn that loses the race
    for port 8000, leaving the user with a tray icon controlling nothing.
    """
    name = "Local\\InoxHydra.Test.SingleInstance"
    first = desktop.acquire_single_instance(name)
    assert first is not None, "the first caller must get the lock"
    try:
        second = desktop.acquire_single_instance(name)
        assert second is None, "a second caller must be refused"
    finally:
        import ctypes

        ctypes.windll.kernel32.CloseHandle(first)


def test_the_tray_holds_the_lock_rather_than_dropping_it():
    """
    A mutex lives exactly as long as its handle. Assigning it to a throwaway
    local would release it immediately and silently defeat the guard.
    """
    source = io.open(os.path.join(REPO_ROOT, "studio_tray.py"), encoding="utf-8").read()
    assert "acquire_single_instance" in source
    assert "_INSTANCE_LOCK" in source


# ---------------------------------------------------------------------------
# Installability
# ---------------------------------------------------------------------------

def test_the_manifest_meets_the_browser_install_rules():
    """
    Chrome and Edge require a name, a start url, a standalone display mode and
    both a 192 and a 512 icon before they will offer to install a page.
    """
    manifest = json.load(io.open(os.path.join(FRONTEND, "manifest.webmanifest"), encoding="utf-8"))

    assert manifest["name"]
    assert manifest["short_name"]
    assert manifest["start_url"] == "/"
    assert manifest["display"] == "standalone"

    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert "192x192" in sizes
    assert "512x512" in sizes

    purposes = {icon.get("purpose") for icon in manifest["icons"]}
    assert "maskable" in purposes, "a maskable icon is needed or the platform crops the corners off"


def test_every_manifest_icon_actually_exists():
    manifest = json.load(io.open(os.path.join(FRONTEND, "manifest.webmanifest"), encoding="utf-8"))
    for icon in manifest["icons"]:
        path = os.path.join(FRONTEND, icon["src"])
        assert os.path.isfile(path), f"the manifest points at {icon['src']} which is not there"


def test_the_page_links_the_manifest():
    html = io.open(os.path.join(FRONTEND, "index.html"), encoding="utf-8").read()
    assert 'rel="manifest"' in html
    assert "manifest.webmanifest" in html
    assert 'name="theme-color"' in html


def test_the_service_worker_caches_nothing():
    """
    A cache in front of a local server hides no latency and solves no offline
    case. What it adds is a way to serve a stale app.js after an update.
    """
    import re

    sw = io.open(os.path.join(FRONTEND, "sw.js"), encoding="utf-8").read()
    # Comments are stripped first. The file explains why it must never cache,
    # and that explanation naturally names the call it is ruling out.
    live = re.sub(r"/\*.*?\*/", "", sw, flags=re.DOTALL)
    live = "\n".join(l for l in live.splitlines() if not l.strip().startswith("//"))

    assert "caches.open" not in live
    assert "caches.match" not in live
    assert "addEventListener(\"fetch\"" in live, "installability requires a fetch handler"


def test_the_worker_is_registered():
    app_js = io.open(os.path.join(FRONTEND, "app.js"), encoding="utf-8").read()
    assert "serviceWorker" in app_js
    assert 'register("sw.js")' in app_js


def test_the_manifest_and_icon_are_served():
    """The manifest is fetched by the browser before any token exists."""
    for path in ("/manifest.webmanifest", "/icons/icon-192.png", "/sw.js"):
        res = client.get(path)
        assert res.status_code == 200, f"{path} is not served"


# ---------------------------------------------------------------------------
# Distribution
# ---------------------------------------------------------------------------

def test_the_portable_build_ships_the_icon():
    """
    The build excludes studio/assets deliberately. The application icon lives
    at the repository root instead, so it has to be copied explicitly or the
    shipped artifact falls back to the generic Windows icon.
    """
    builder = io.open(os.path.join(REPO_ROOT, "tools", "build_portable.py"), encoding="utf-8").read()
    assert "inox_hydra.ico" in builder
    assert "generate_icons.py" in builder, "the build should say how to produce a missing icon"


def test_the_icon_generator_is_reproducible():
    """
    Two runs must produce identical bytes, or every build shows a spurious
    diff on a binary file.
    """
    from PIL import Image
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "generate_icons", os.path.join(REPO_ROOT, "tools", "generate_icons.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    first = module.draw_mark(64).tobytes()
    second = module.draw_mark(64).tobytes()
    assert first == second


def test_desktop_integration_holds_the_zero_em_dash_invariant():
    targets = [
        os.path.join(REPO_ROOT, "studio", "backend", "desktop.py"),
        os.path.join(REPO_ROOT, "tools", "generate_icons.py"),
        os.path.join(FRONTEND, "sw.js"),
    ]
    for path in targets:
        content = io.open(path, encoding="utf-8").read()
        # Never typed literally, or this file would break the rule it enforces.
        assert chr(8212) not in content, f"{os.path.basename(path)} contains an em-dash"
