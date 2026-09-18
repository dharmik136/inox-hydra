"""
Tests for Chrome Extension Manifest V3 Compliance and Packaging
==============================================================
Verifies:
1. Manifest V3 compliance, host permissions, and required entrypoints.
2. Extension popup.html and sidepanel.html DOM structure integrity.
3. Automated packaging function and zip archive integrity.
"""

import os
import sys
import json
import zipfile
import pytest

# Paths
EXT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "extension"))
sys.path.insert(0, EXT_DIR)

from package_extension import validate_manifest, package_extension, REQUIRED_FILES, OUTPUT_ZIP


def test_manifest_v3_compliance():
    manifest_path = os.path.join(EXT_DIR, "manifest.json")
    assert os.path.exists(manifest_path), "manifest.json does not exist"
    
    manifest = validate_manifest(manifest_path)
    assert manifest["manifest_version"] == 3
    assert "sidePanel" in manifest["permissions"]
    assert "cookies" in manifest["permissions"]
    assert "https://*.linkedin.com/*" in manifest["host_permissions"]
    assert manifest["background"]["service_worker"] == "background.js"
    assert manifest["side_panel"]["default_path"] == "sidepanel.html"
    assert manifest["action"]["default_popup"] == "popup.html"


def test_required_files_exist():
    for f in REQUIRED_FILES:
        full_path = os.path.join(EXT_DIR, f)
        assert os.path.exists(full_path), f"Required extension asset missing: {f}"


def test_popup_and_sidepanel_dom_integrity():
    popup_path = os.path.join(EXT_DIR, "popup.html")
    sidepanel_path = os.path.join(EXT_DIR, "sidepanel.html")

    with open(popup_path, "r", encoding="utf-8") as f:
        popup_html = f.read()

    with open(sidepanel_path, "r", encoding="utf-8") as f:
        sidepanel_html = f.read()

    # Popup DOM assertions
    assert "session-status" in popup_html or "status-indicator" in popup_html
    assert "btn-sync-now" in popup_html or "sync" in popup_html.lower()

    # Sidepanel DOM assertions
    assert "panel-composer" in sidepanel_html
    assert "panel-queue" in sidepanel_html
    assert "panel-crm" in sidepanel_html
    assert "btn-inject-composer" in sidepanel_html
    assert "sp-text" in sidepanel_html


def test_extension_packaging_zip():
    zip_path = package_extension()
    assert os.path.exists(zip_path), f"ZIP bundle missing at {zip_path}"
    assert zip_path == OUTPUT_ZIP

    with zipfile.ZipFile(zip_path, "r") as z:
        names = z.namelist()
        assert "manifest.json" in names
        assert "background.js" in names
        assert "sidepanel.html" in names
        assert "sidepanel.js" in names
        assert "popup.html" in names
        assert "content.js" in names
        assert any("icon" in n for n in names)
