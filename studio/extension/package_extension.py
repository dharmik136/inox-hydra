"""
Inox Hydra: Chrome MV3 Extension Packaging Utility
=================================================
Automated packaging script that validates Manifest V3 compliance,
verifies all referenced icons and scripts, and bundles the extension
into build_artifacts/inox_hydra_extension.zip for 1-click loading.
"""

import os
import sys
import json
import zipfile

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(EXT_DIR, "..", ".."))
BUILD_DIR = os.path.join(PROJECT_ROOT, "build_artifacts")
OUTPUT_ZIP = os.path.join(BUILD_DIR, "inox_hydra_extension.zip")

REQUIRED_FILES = [
    "manifest.json",
    "background.js",
    "content.js",
    "content.css",
    "popup.html",
    "popup.js",
    "sidepanel.html",
    "sidepanel.js",
    os.path.join("icons", "icon-16.png"),
    os.path.join("icons", "icon-48.png"),
    os.path.join("icons", "icon-128.png"),
]


def validate_manifest(manifest_path: str) -> dict:
    """Validates Manifest V3 specification and mandatory fields."""
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"Missing manifest.json at {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest.get("manifest_version") == 3, "Manifest version must be 3"
    assert manifest.get("name"), "Manifest must specify a name"
    assert manifest.get("version"), "Manifest must specify a version"
    assert "sidePanel" in manifest.get("permissions", []), "sidePanel permission required"
    assert "cookies" in manifest.get("permissions", []), "cookies permission required"
    assert "https://*.linkedin.com/*" in manifest.get("host_permissions", []), "LinkedIn host permission required"

    print(f"✅ Manifest V3 validated: {manifest['name']} v{manifest['version']}")
    return manifest


def package_extension():
    """Validates files and compiles the deployment ZIP archive."""
    print("Packing Inox Hydra Chrome Extension...")
    os.makedirs(BUILD_DIR, exist_ok=True)

    manifest_path = os.path.join(EXT_DIR, "manifest.json")
    validate_manifest(manifest_path)

    # Check all required files exist
    missing_files = []
    for rel_path in REQUIRED_FILES:
        full_path = os.path.join(EXT_DIR, rel_path)
        if not os.path.exists(full_path):
            missing_files.append(rel_path)

    if missing_files:
        raise FileNotFoundError(f"Missing required extension files: {missing_files}")

    # Build ZIP archive
    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(EXT_DIR):
            for file in files:
                if file.endswith((".py", ".pyc")) or "__pycache__" in root:
                    continue
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, EXT_DIR)
                zipf.write(file_path, arcname)
                print(f"   [+] Bundled: {arcname}")

    file_size_kb = os.path.getsize(OUTPUT_ZIP) / 1024
    print(f"\n🎉 Package created successfully: {OUTPUT_ZIP} ({file_size_kb:.1f} KB)")
    return OUTPUT_ZIP


if __name__ == "__main__":
    try:
        package_extension()
    except Exception as e:
        print(f"❌ Packaging failed: {e}", file=sys.stderr)
        sys.exit(1)
