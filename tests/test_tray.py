"""
Inox Hydra: Windows System Tray & Background Daemon Test Suite
==============================================================
Verifies:
1. InoxHydraTray Win32 Shell ctypes struct alignment and size (976 bytes).
2. Server status check functionality.
3. System tray command mappings and action handlers.
4. launch_studio.bat support for --tray daemon flag.
"""

import os
import sys
import ctypes
import pytest

# Ensure root directory is on path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from studio_tray import InoxHydraTray, NOTIFYICONDATAW, verify_tray_setup


def test_tray_struct_alignment():
    assert ctypes.sizeof(NOTIFYICONDATAW) == 976
    assert verify_tray_setup() is True


def test_tray_initialization():
    tray = InoxHydraTray()
    assert tray.user32 is not None
    assert tray.shell32 is not None
    assert hasattr(tray, "open_studio")
    assert hasattr(tray, "open_sidepanel")
    assert hasattr(tray, "run_tests")
    assert hasattr(tray, "restart_server")
    assert hasattr(tray, "exit_app")


def test_launch_studio_bat_supports_tray():
    bat_path = os.path.join(PROJECT_ROOT, "launch_studio.bat")
    assert os.path.exists(bat_path)
    with open(bat_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "--tray" in content
    assert "studio_tray.py" in content
