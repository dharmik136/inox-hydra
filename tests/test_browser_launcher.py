import pytest
import os
from studio.backend.browser_launcher import (
    detect_installed_browsers,
    get_extension_dir,
    create_desktop_shortcuts,
    copy_extension_path_to_clipboard
)

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

def test_clipboard_copy():
    res = copy_extension_path_to_clipboard()
    assert res["status"] == "success"

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

