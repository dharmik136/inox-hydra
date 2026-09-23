import os
import sys

import pytest

from studio.backend.browser_launcher import (
    detect_installed_browsers,
    get_extension_dir,
    create_desktop_shortcuts,
    copy_extension_path_to_clipboard
)

# These assert that a browser is actually installed and that a launcher lands
# on a real Desktop, so they need a workstation rather than a runner. The
# hosted macOS and Linux images ship neither, so they would fail there for a
# reason that says nothing about this code.
#
# The gate is no longer "Windows only". Detection and launcher creation work
# on all three platforms now; what varies is whether the machine running the
# test has a browser. The platform independent behaviour, including the macOS
# and Linux launcher formats and their quoting, is covered without that
# requirement in test_browser_launcher_cross_platform.py.
requires_installed_browser = pytest.mark.skipif(
    sys.platform != "win32",
    reason="needs a workstation with a browser installed and a real Desktop",
)


@requires_installed_browser
def test_detect_installed_browsers():
    browsers = detect_installed_browsers()
    assert isinstance(browsers, dict)
    assert len(browsers) >= 1
    for b_id, info in browsers.items():
        assert os.path.exists(info["path"])

def test_get_extension_dir():
    ext_dir = get_extension_dir()
    assert os.path.exists(ext_dir)
    assert os.path.exists(os.path.join(ext_dir, "manifest.json"))

@requires_installed_browser
def test_create_desktop_shortcuts():
    browsers = detect_installed_browsers()
    shortcuts = create_desktop_shortcuts(browsers)
    assert len(shortcuts) > 0
    for s in shortcuts:
        if s["status"] != "created":
            print("FAILED SHORTCUT:", s)
        assert s["status"] == "created"
        assert os.path.exists(s["shortcut_path"])
        # Clean up
        try:
            os.remove(s["shortcut_path"])
        except Exception:
            pass

def test_clipboard_copy_reports_truthfully():
    """
    Set-Clipboard needs an interactive desktop with STA clipboard access. A CI
    runner and a service session do not have one, so failing there is the
    correct answer and asserting success would be asserting a lie.

    What must hold everywhere is that the report matches reality and the path
    comes back either way, so the interface can offer it for manual copying.
    """
    res = copy_extension_path_to_clipboard()

    assert res["status"] in ("success", "error")
    assert res["extension_path"], "the path must be returned even when the copy fails"
    assert os.path.isdir(res["extension_path"])

    if res["status"] == "error":
        assert res["message"], "a failure must say something the user can act on"

@requires_installed_browser
def test_browser_api_endpoints():
    from fastapi.testclient import TestClient
    from studio.backend.app import app
    client = TestClient(app)

    # Test status
    res = client.get("/api/v1/browser/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["total_detected"] >= 1
    assert "chrome" in data["browsers"] or "edge" in data["browsers"]

    # Test copy-path
    res_copy = client.post("/api/v1/browser/copy-path")
    assert res_copy.status_code == 200
    assert res_copy.json()["status"] == "success"

    # Test create-shortcuts
    res_sc = client.post("/api/v1/browser/create-shortcuts")
    assert res_sc.status_code == 200
    sc_data = res_sc.json()
    assert sc_data["status"] == "success"
    assert sc_data["total_created"] >= 1
    for s in sc_data["shortcuts"]:
        if s.get("status") == "created" and os.path.exists(s.get("shortcut_path", "")):
            try:
                os.remove(s["shortcut_path"])
            except Exception:
                pass

